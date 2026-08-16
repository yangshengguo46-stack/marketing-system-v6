from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from jsonschema import Draft202012Validator

from .catalog import OfficialCatalog
from .contracts import CapabilityContext, CapabilityEntry
from .domains import DOMAIN_DEFINITIONS

logger = logging.getLogger(__name__)

CapabilityHandler = Callable[[dict[str, Any], CapabilityContext], Awaitable[dict[str, Any]]]

_MAX_MANIFEST_BYTES = 64 * 1024
_MAX_RESULT_BYTES = 64 * 1024


def _error(code: str, message: str) -> dict[str, Any]:
    return {"error": {"code": code, "message": message}}


class DomainRouter:
    def __init__(
        self,
        catalog: OfficialCatalog,
        *,
        handlers: Mapping[str, CapabilityHandler] | None = None,
    ) -> None:
        self._catalog = catalog
        self._handlers = dict(handlers or {})

    def _availability(self, entry: CapabilityEntry, context: CapabilityContext) -> tuple[bool, str | None]:
        if entry.review_status != "adopted":
            return False, "contract_not_adopted"
        if entry.interaction_direction != "outbound":
            return False, "not_an_outbound_api"
        if entry.auth_mode and entry.auth_mode not in context.configured_auth_modes:
            return False, "auth_not_configured"
        if entry.risk_level in {"write", "irreversible", "chargeable"} and (entry.capability_id not in context.approved_capabilities):
            return False, "approval_required"
        if not entry.handler_key or entry.handler_key not in self._handlers:
            return False, "adapter_not_registered"
        return True, None

    def discover(self, domain_id: str, context: CapabilityContext) -> dict[str, Any]:
        definition = DOMAIN_DEFINITIONS.get(domain_id)
        if definition is None:
            return _error("unknown_domain", "The requested Douyin domain is unknown")

        domain_entries = self._catalog.entries_for_domain(domain_id)
        children: list[dict[str, Any]] = []
        for entry in domain_entries:
            if not entry.is_child_contract:
                continue
            if not set(entry.required_scopes).issubset(context.granted_scopes):
                continue
            callable_now, reason = self._availability(entry, context)
            child = {
                "name": entry.child_name,
                "title": entry.name_zh,
                "description": entry.description_zh,
                "documentation_url": entry.documentation_url,
                "risk_level": entry.risk_level,
                "callable": callable_now,
                "input_schema": entry.input_schema,
                "output_schema": entry.output_schema,
            }
            if reason:
                child["unavailable_reason"] = reason
            children.append(child)

        generation_hash = hashlib.sha256(context.capability_generation.encode()).hexdigest()
        manifest_body = {
            "domain": domain_id,
            "tool_name": definition.tool_name,
            "responsibility": {
                "includes": definition.includes,
                "excludes": definition.excludes,
            },
            "children": children,
            "metadata": {
                "catalog_version": self._catalog.catalog_version,
                "catalog_entries": len(domain_entries),
                "disclosed_children": len(children),
                "capability_generation_hash": generation_hash,
            },
        }
        manifest_version = hashlib.sha256(
            json.dumps(
                manifest_body,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        manifest = {**manifest_body, "manifest_version": manifest_version}
        if len(json.dumps(manifest, ensure_ascii=False, separators=(",", ":")).encode()) > _MAX_MANIFEST_BYTES:
            raise ValueError(f"Douyin domain {domain_id} manifest exceeds its byte budget")
        return manifest

    async def dispatch(
        self,
        *,
        domain_id: str,
        child_tool: str,
        arguments: dict[str, Any],
        manifest_version: str,
        context: CapabilityContext,
    ) -> dict[str, Any]:
        current = self.discover(domain_id, context)
        if "error" in current:
            return current
        if manifest_version != current["manifest_version"]:
            return _error(
                "stale_manifest",
                "Douyin capabilities changed; rediscover this domain before calling it",
            )

        visible = {child["name"]: child for child in current["children"] if isinstance(child.get("name"), str)}
        child = visible.get(child_tool)
        if child is None:
            return _error(
                "child_not_authorized_or_unknown",
                "The child is not disclosed for this domain and capability context",
            )
        if not child["callable"]:
            return _error(
                "child_unavailable",
                str(child.get("unavailable_reason") or "The child is unavailable"),
            )

        entry = next(
            (candidate for candidate in self._catalog.entries_for_domain(domain_id) if candidate.child_name == child_tool),
            None,
        )
        if entry is None or entry.input_schema is None or entry.output_schema is None:
            return _error("contract_missing", "The child contract is incomplete")

        input_errors = sorted(
            Draft202012Validator(entry.input_schema).iter_errors(arguments),
            key=lambda error: list(error.absolute_path),
        )
        if input_errors:
            return _error(
                "input_schema_invalid",
                "Child arguments do not match the current input schema",
            )

        handler = self._handlers[entry.handler_key]
        try:
            output = await handler(arguments, context)
        except Exception as exc:
            logger.warning(
                "Douyin child handler failed: domain=%s child=%s type=%s",
                domain_id,
                child_tool,
                type(exc).__name__,
            )
            return _error("provider_request_failed", "The Douyin provider request failed")

        output_errors = sorted(
            Draft202012Validator(entry.output_schema).iter_errors(output),
            key=lambda error: list(error.absolute_path),
        )
        if output_errors:
            logger.warning(
                "Douyin child output failed schema validation: domain=%s child=%s",
                domain_id,
                child_tool,
            )
            return _error(
                "output_schema_invalid",
                "The provider response did not match the reviewed output contract",
            )
        if len(json.dumps(output, ensure_ascii=False, separators=(",", ":")).encode()) > _MAX_RESULT_BYTES:
            return _error(
                "output_too_large",
                "The provider response exceeded the bounded result contract",
            )

        return {
            "data": output,
            "warnings": [],
            "metadata": {
                "domain": domain_id,
                "child_tool": child_tool,
                "manifest_version": current["manifest_version"],
                "catalog_version": self._catalog.catalog_version,
            },
        }

    async def invoke(
        self,
        *,
        domain_id: str,
        child_tool: str | None,
        arguments: dict[str, Any] | None,
        manifest_version: str | None,
        context: CapabilityContext,
    ) -> dict[str, Any]:
        if child_tool is None:
            if arguments not in (None, {}) or manifest_version is not None:
                return _error(
                    "invalid_discovery_request",
                    "Domain discovery accepts an empty request only",
                )
            return self.discover(domain_id, context)
        if manifest_version is None:
            return _error(
                "manifest_version_required",
                "Rediscover the domain and provide its manifest_version",
            )
        if not isinstance(arguments, dict):
            return _error("arguments_required", "Child arguments must be an object")
        return await self.dispatch(
            domain_id=domain_id,
            child_tool=child_tool,
            arguments=arguments,
            manifest_version=manifest_version,
            context=context,
        )
