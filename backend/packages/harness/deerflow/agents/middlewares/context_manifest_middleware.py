"""Read-only accounting for the final model request.

The manifest records sizes, identities, and capability names only. It never
copies message bodies, tool descriptions, tool arguments, secrets, Skill paths,
or provider error text. The middleware is deliberately innermost among request
transformers so one event describes each physical provider call after context
injection, schema filtering, coalescing, and terminal-response recovery.
"""

from __future__ import annotations

import hashlib
import html
import json
import logging
import posixpath
import re
import secrets
import threading
from collections.abc import Awaitable, Callable, Mapping
from typing import Any, Literal, override

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ModelCallResult, ModelRequest, ModelResponse
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.utils.function_calling import convert_to_openai_tool

from deerflow.agents.lead_agent.identity import PRODUCT_IDENTITY_ASSET
from deerflow.runtime.secret_context import (
    CONTEXT_MANIFEST_COUNTER_CONTEXT_KEY,
    read_agent_skill_source_path,
    read_slash_skill_source_path,
    read_user_profile_projection,
)

logger = logging.getLogger(__name__)

CONTEXT_MANIFEST_VERSION = 1
_DEFAULT_AGENT_NAME = "the user's new-media operations teammate"
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_ACTIVE_SKILL_TAG_PATTERN = re.compile(r'^<active_skill_context\s+name="(?P<name>[^"]*)"\s+path="[^"]*"\s+sha256="(?P<sha256>[0-9a-f]{64})"\s+mode="(?P<mode>slash|agent)">')

type _Outcome = Literal["success", "error"]


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=lambda item: f"<{type(item).__module__}.{type(item).__qualname__}>",
    ).encode("utf-8")


def _content_utf8_bytes(content: Any) -> int:
    if isinstance(content, str):
        return len(content.encode("utf-8"))
    if isinstance(content, bytes):
        return len(content)
    return len(_canonical_json_bytes(content))


def _message_payload(message: Any) -> Any:
    if isinstance(message, BaseMessage):
        return message.model_dump(mode="json", exclude_none=True)
    if isinstance(message, Mapping):
        return dict(message)
    return {"type": type(message).__name__}


def _message_content(message: Any) -> Any:
    if isinstance(message, Mapping):
        return message.get("content", "")
    return getattr(message, "content", "")


def _message_role(message: Any) -> str:
    if isinstance(message, SystemMessage):
        return "system"
    if isinstance(message, HumanMessage):
        return "human"
    if isinstance(message, AIMessage):
        return "ai"
    if isinstance(message, ToolMessage):
        return "tool"
    raw = message.get("type") if isinstance(message, Mapping) else getattr(message, "type", None)
    return raw if isinstance(raw, str) and raw else "other"


def _additional_kwargs(message: Any) -> Mapping[str, Any]:
    raw = message.get("additional_kwargs") if isinstance(message, Mapping) else getattr(message, "additional_kwargs", None)
    return raw if isinstance(raw, Mapping) else {}


def _message_name(message: Any) -> str | None:
    raw = message.get("name") if isinstance(message, Mapping) else getattr(message, "name", None)
    return raw if isinstance(raw, str) and raw else None


def _role_account(messages: list[Any]) -> tuple[dict[str, dict[str, int]], int, int]:
    by_role: dict[str, dict[str, int]] = {}
    total_content_bytes = 0
    total_canonical_bytes = 0
    for message in messages:
        role = _message_role(message)
        content_bytes = _content_utf8_bytes(_message_content(message))
        canonical_bytes = len(_canonical_json_bytes(_message_payload(message)))
        account = by_role.setdefault(
            role,
            {"count": 0, "content_utf8_bytes": 0, "canonical_utf8_bytes": 0},
        )
        account["count"] += 1
        account["content_utf8_bytes"] += content_bytes
        account["canonical_utf8_bytes"] += canonical_bytes
        total_content_bytes += content_bytes
        total_canonical_bytes += canonical_bytes
    return by_role, total_content_bytes, total_canonical_bytes


def _tool_schema(tool: Any) -> dict[str, Any]:
    try:
        converted = convert_to_openai_tool(tool)
    except Exception:
        name = getattr(tool, "name", None)
        return {
            "type": "function",
            "function": {
                "name": name if isinstance(name, str) and name else type(tool).__name__,
                "schema_unavailable": True,
            },
        }
    return converted if isinstance(converted, dict) else {"schema_type": type(converted).__name__}


def _tool_name(tool: Any, schema: Mapping[str, Any]) -> str:
    direct = getattr(tool, "name", None)
    if isinstance(direct, str) and direct:
        return direct
    function = schema.get("function")
    if isinstance(function, Mapping):
        name = function.get("name")
        if isinstance(name, str) and name:
            return name
    raw_name = schema.get("name")
    if isinstance(raw_name, str) and raw_name:
        return raw_name
    return type(tool).__name__


def _tool_account(tools: list[Any]) -> tuple[list[dict[str, Any]], int, str]:
    schemas: list[dict[str, Any]] = []
    projected: list[dict[str, Any]] = []
    for tool in tools:
        schema = _tool_schema(tool)
        encoded = _canonical_json_bytes(schema)
        schemas.append(schema)
        projected.append(
            {
                "name": _tool_name(tool, schema),
                "schema_utf8_bytes": len(encoded),
                "schema_sha256": hashlib.sha256(encoded).hexdigest(),
            }
        )
    catalog_bytes = _canonical_json_bytes(schemas)
    return projected, len(catalog_bytes), hashlib.sha256(catalog_bytes).hexdigest()


def _response_format_schema(response_format: Any) -> Any:
    if response_format is None:
        return None
    schema = getattr(response_format, "schema", response_format)
    if isinstance(schema, type) and hasattr(schema, "model_json_schema"):
        try:
            return schema.model_json_schema()
        except Exception:
            return {"schema_type": schema.__name__, "schema_unavailable": True}
    if hasattr(schema, "model_json_schema"):
        try:
            return schema.model_json_schema()
        except Exception:
            return {"schema_type": type(schema).__name__, "schema_unavailable": True}
    if isinstance(schema, (Mapping, list, tuple, str, int, float, bool)):
        return schema
    return {"schema_type": type(schema).__name__, "schema_unavailable": True}


def _response_format_account(response_format: Any) -> dict[str, Any]:
    if response_format is None:
        return {
            "present": False,
            "kind": None,
            "schema_utf8_bytes": 0,
            "schema_sha256": None,
        }
    schema = _response_format_schema(response_format)
    encoded = _canonical_json_bytes(schema)
    return {
        "present": True,
        "kind": type(response_format).__name__,
        "schema_utf8_bytes": len(encoded),
        "schema_sha256": hashlib.sha256(encoded).hexdigest(),
    }


def _model_projection(model: Any, model_settings: Any) -> dict[str, Any]:
    name = None
    for attribute in ("model_name", "model", "model_id"):
        candidate = getattr(model, attribute, None)
        if isinstance(candidate, str) and candidate:
            name = candidate
            break
    settings_keys = sorted(str(key) for key in model_settings) if isinstance(model_settings, Mapping) else []
    return {
        "name": name or type(model).__name__,
        "class": type(model).__name__,
        "settings_keys": settings_keys,
    }


def _empty_layer() -> dict[str, int]:
    return {"message_count": 0, "content_utf8_bytes": 0}


def _context_layers(messages: list[Any], system_message: Any | None) -> tuple[dict[str, dict[str, Any]], int, int]:
    layers: dict[str, dict[str, Any]] = {
        "dynamic_system": _empty_layer(),
        "memory": _empty_layer(),
        "user_profile": _empty_layer(),
        "active_skill": _empty_layer(),
        "durable_context": _empty_layer(),
        "progress_hint": _empty_layer(),
        "terminal_recovery": _empty_layer(),
        "other_hidden": _empty_layer(),
    }
    system_kwargs = _additional_kwargs(system_message) if system_message is not None else {}
    if system_kwargs.get("dynamic_context_reminder"):
        # Coalescing merges the date reminder into the static system prompt, so
        # its isolated byte size is no longer knowable at this final boundary.
        layers["dynamic_system"] = {
            "message_count": 1,
            "content_utf8_bytes": 0,
            "coalesced_into_system": True,
        }

    hidden_count = 0
    hidden_content_bytes = 0
    for message in messages:
        kwargs = _additional_kwargs(message)
        if kwargs.get("hide_from_ui") is not True:
            continue
        hidden_count += 1
        size = _content_utf8_bytes(_message_content(message))
        hidden_content_bytes += size
        name = _message_name(message)
        if kwargs.get("active_skill_context"):
            layer = "active_skill"
        elif kwargs.get("user_profile_context"):
            layer = "user_profile"
        elif kwargs.get("durable_context_data"):
            layer = "durable_context"
        elif kwargs.get("dynamic_context_reminder") and isinstance(message, HumanMessage):
            layer = "memory"
        elif name == "progress_hint":
            layer = "progress_hint"
        elif name == "terminal_response_recovery":
            layer = "terminal_recovery"
        else:
            layer = "other_hidden"
        layers[layer]["message_count"] += 1
        layers[layer]["content_utf8_bytes"] += size
    return layers, hidden_count, hidden_content_bytes


def _state_projection(state: Any) -> dict[str, Any]:
    if not isinstance(state, Mapping):
        state = {}
    summary = state.get("summary_text")
    delegations = state.get("delegations")
    inspected_skills = state.get("skill_context")
    return {
        "summary_present": isinstance(summary, str) and bool(summary),
        "summary_utf8_bytes": len(summary.encode("utf-8")) if isinstance(summary, str) else 0,
        "delegation_count": len(delegations) if isinstance(delegations, list) else 0,
        "inspected_skill_count": len(inspected_skills) if isinstance(inspected_skills, list) else 0,
    }


def _active_skill_metadata(messages: list[Any]) -> tuple[str | None, str | None, str | None]:
    for message in messages:
        if _additional_kwargs(message).get("active_skill_context") is not True:
            continue
        content = _message_content(message)
        if not isinstance(content, str):
            continue
        match = _ACTIVE_SKILL_TAG_PATTERN.match(content)
        if match is None:
            continue
        return html.unescape(match.group("name")), match.group("sha256"), match.group("mode")
    return None, None, None


def _skill_name_from_path(path: str | None) -> str | None:
    if not path:
        return None
    parent = posixpath.basename(posixpath.dirname(posixpath.normpath(path)))
    return parent or None


def _skill_activation(request: ModelRequest, owner_token: str) -> dict[str, Any]:
    context = getattr(getattr(request, "runtime", None), "context", None)
    slash_path = read_slash_skill_source_path(context, owner_token=owner_token)
    agent_path = read_agent_skill_source_path(context, owner_token=owner_token)
    if slash_path is not None:
        mode, path = "slash", slash_path
    elif agent_path is not None:
        mode, path = "agent", agent_path
    else:
        return {"mode": "none", "skill_name": None, "content_sha256": None}

    injected_name, content_sha256, injected_mode = _active_skill_metadata(list(request.messages))
    if injected_mode != mode or not isinstance(content_sha256, str) or _SHA256_PATTERN.fullmatch(content_sha256) is None:
        content_sha256 = None
    return {
        "mode": mode,
        "skill_name": injected_name or _skill_name_from_path(path),
        "content_sha256": content_sha256,
    }


def _identity_projection(system_message: Any | None, agent_name: str | None) -> dict[str, Any]:
    content = _message_content(system_message) if system_message is not None else ""
    expected = PRODUCT_IDENTITY_ASSET.content.format(agent_name=agent_name or _DEFAULT_AGENT_NAME)
    return {
        "present": isinstance(content, str) and expected in content,
        "source": PRODUCT_IDENTITY_ASSET.source,
        "version": PRODUCT_IDENTITY_ASSET.version,
        "sha256": PRODUCT_IDENTITY_ASSET.sha256,
    }


def _user_profile_projection(request: ModelRequest, owner_token: str | None) -> dict[str, Any]:
    absent = {
        "present": False,
        "version": None,
        "content_sha256": None,
        "item_count": 0,
        "projected_item_count": 0,
        "omitted_item_count": 0,
    }
    if not owner_token:
        return absent
    context = getattr(getattr(request, "runtime", None), "context", None)
    projection = read_user_profile_projection(context, owner_token=owner_token)
    if projection is None:
        return absent
    return {"present": True, **projection}


def build_context_manifest(
    request: ModelRequest,
    *,
    call_index: int,
    agent_name: str | None,
    activation_owner_token: str,
    user_profile_owner_token: str | None = None,
    outcome: _Outcome,
    response_usage: dict[str, int] | None = None,
    error_type: str | None = None,
) -> dict[str, Any]:
    """Build a content-free diagnostic projection for one physical model call."""
    messages = list(request.messages)
    messages_with_system = [request.system_message, *messages] if request.system_message is not None else messages
    by_role, content_bytes, canonical_message_bytes = _role_account(messages_with_system)
    tools, tool_schema_bytes, tool_catalog_sha256 = _tool_account(list(request.tools or []))
    response_format = _response_format_account(request.response_format)
    context_layers, hidden_count, hidden_content_bytes = _context_layers(messages, request.system_message)

    manifest: dict[str, Any] = {
        "version": CONTEXT_MANIFEST_VERSION,
        "call_index": call_index,
        "outcome": outcome,
        "identity": _identity_projection(request.system_message, agent_name),
        "model": _model_projection(request.model, request.model_settings),
        "request": {
            "message_count": len(messages_with_system),
            "content_utf8_bytes": content_bytes,
            "canonical_message_utf8_bytes": canonical_message_bytes,
            "by_role": by_role,
            "hidden_message_count": hidden_count,
            "hidden_content_utf8_bytes": hidden_content_bytes,
            "tool_count": len(tools),
            "tool_schema_utf8_bytes": tool_schema_bytes,
            "tool_catalog_sha256": tool_catalog_sha256,
            "tools": tools,
            "response_format": response_format,
            "estimated_payload_utf8_bytes": canonical_message_bytes + tool_schema_bytes + response_format["schema_utf8_bytes"],
        },
        "context_layers": context_layers,
        "state_projection": _state_projection(request.state),
        "skill_activation": _skill_activation(request, activation_owner_token),
        "user_profile": _user_profile_projection(request, user_profile_owner_token),
        "response_usage": response_usage,
    }
    if error_type:
        manifest["error_type"] = error_type
    return manifest


def _nonnegative_int(value: Any) -> int:
    return value if type(value) is int and value >= 0 else 0


def _response_usage(response: Any) -> dict[str, int] | None:
    input_tokens = 0
    output_tokens = 0
    total_tokens = 0
    cache_read_tokens = 0
    found = False
    for message in getattr(response, "result", []) or []:
        usage = getattr(message, "usage_metadata", None)
        if not isinstance(usage, Mapping):
            continue
        found = True
        input_tokens += _nonnegative_int(usage.get("input_tokens"))
        output_tokens += _nonnegative_int(usage.get("output_tokens"))
        total_tokens += _nonnegative_int(usage.get("total_tokens"))
        details = usage.get("input_token_details")
        if isinstance(details, Mapping):
            cache_read_tokens += _nonnegative_int(details.get("cache_read"))
        cache_read_tokens += _nonnegative_int(usage.get("cache_read_tokens"))
    if not found:
        return None
    if total_tokens == 0:
        total_tokens = input_tokens + output_tokens
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "cache_read_tokens": cache_read_tokens,
    }


class ContextManifestMiddleware(AgentMiddleware[AgentState]):
    """Persist a content-free manifest for every physical Lead model call."""

    def __init__(
        self,
        *,
        agent_name: str | None,
        activation_owner_token: str,
        user_profile_owner_token: str | None = None,
    ) -> None:
        super().__init__()
        if not isinstance(activation_owner_token, str) or not activation_owner_token:
            raise ValueError("activation_owner_token must be a non-empty string")
        self._agent_name = agent_name
        self._activation_owner_token = activation_owner_token
        self._user_profile_owner_token = user_profile_owner_token
        self._counter_owner_token = secrets.token_urlsafe(24)
        self._counter_lock = threading.Lock()

    def _next_call_index(self, request: ModelRequest) -> int:
        context = getattr(getattr(request, "runtime", None), "context", None)
        if not isinstance(context, dict):
            return 1
        with self._counter_lock:
            counter = context.get(CONTEXT_MANIFEST_COUNTER_CONTEXT_KEY)
            previous = 0
            if isinstance(counter, dict) and counter.get("owner_token") == self._counter_owner_token:
                previous = _nonnegative_int(counter.get("count"))
            current = previous + 1
            context[CONTEXT_MANIFEST_COUNTER_CONTEXT_KEY] = {
                "owner_token": self._counter_owner_token,
                "count": current,
            }
            return current

    @staticmethod
    def _record(request: ModelRequest, manifest: dict[str, Any]) -> None:
        context = getattr(getattr(request, "runtime", None), "context", None)
        journal = context.get("__run_journal") if isinstance(context, dict) else None
        if journal is None:
            return
        try:
            journal.record_context_manifest(manifest)
        except Exception:
            logger.debug("Failed to record context manifest", exc_info=True)

    def _base_manifest(self, request: ModelRequest, call_index: int) -> dict[str, Any]:
        return build_context_manifest(
            request,
            call_index=call_index,
            agent_name=self._agent_name,
            activation_owner_token=self._activation_owner_token,
            user_profile_owner_token=self._user_profile_owner_token,
            outcome="success",
        )

    @override
    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelCallResult:
        manifest = self._base_manifest(request, self._next_call_index(request))
        try:
            response = handler(request)
        except Exception as exc:
            manifest["outcome"] = "error"
            manifest["error_type"] = type(exc).__name__
            self._record(request, manifest)
            raise
        manifest["response_usage"] = _response_usage(response)
        self._record(request, manifest)
        return response

    @override
    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelCallResult:
        manifest = self._base_manifest(request, self._next_call_index(request))
        try:
            response = await handler(request)
        except Exception as exc:
            manifest["outcome"] = "error"
            manifest["error_type"] = type(exc).__name__
            self._record(request, manifest)
            raise
        manifest["response_usage"] = _response_usage(response)
        self._record(request, manifest)
        return response
