from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable
from contextlib import asynccontextmanager
from typing import Any

from mcp.server.fastmcp import FastMCP

from deerflow.community.douyin_search.tools import douyin_video_search_tool

from .adapters.search import search_experiences
from .contracts import CapabilityContext
from .domains import DOMAIN_DEFINITIONS, DomainDefinition
from .gateway_catalog import PUBLIC_EVIDENCE_CHILD_NAMES, load_gateway_catalog
from .public_evidence import (
    PUBLIC_EVIDENCE_AUTH_MODE,
    PublicEvidenceRuntime,
    StdioPublicEvidenceRuntime,
    public_evidence_runtime_is_configured,
)
from .router import CapabilityHandler, DomainRouter


def _parse_csv_env(name: str) -> frozenset[str]:
    value = os.getenv(name, "")
    return frozenset(part.strip() for part in value.split(",") if part.strip())


def context_from_environment() -> CapabilityContext:
    auth_modes: set[str] = set()
    if os.getenv("DOUYIN_CLIENT_KEY") and os.getenv("DOUYIN_CLIENT_SECRET"):
        auth_modes.add("client_token")
    public_evidence_configured = public_evidence_runtime_is_configured()
    if public_evidence_configured:
        auth_modes.add(PUBLIC_EVIDENCE_AUTH_MODE)
    scopes = _parse_csv_env("DOUYIN_APPROVED_SCOPES")
    generation_payload = {
        "auth_modes": sorted(auth_modes),
        "scopes": sorted(scopes),
        "public_evidence_configured": public_evidence_configured,
        "policy_generation": os.getenv("DOUYIN_POLICY_GENERATION", "default"),
    }
    generation = hashlib.sha256(json.dumps(generation_payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return CapabilityContext(
        granted_scopes=scopes,
        configured_auth_modes=frozenset(auth_modes),
        capability_generation=generation,
    )


async def _video_search_handler(arguments: dict[str, Any], context: CapabilityContext) -> dict[str, Any]:
    del context
    raw = await douyin_video_search_tool.ainvoke(arguments)
    payload = json.loads(raw)
    return payload if isinstance(payload, dict) else {"error": "Invalid provider receipt", "query": arguments.get("query", "")}


async def _experience_search_handler(arguments: dict[str, Any], context: CapabilityContext) -> dict[str, Any]:
    del context
    return await search_experiences(**arguments)


def _public_evidence_handler(
    runtime: PublicEvidenceRuntime,
    child_tool: str,
) -> CapabilityHandler:
    async def handler(
        arguments: dict[str, Any],
        context: CapabilityContext,
    ) -> dict[str, Any]:
        del context
        return await runtime.call(child_tool, arguments)

    return handler


def build_default_router(
    *,
    public_evidence_runtime: PublicEvidenceRuntime | None = None,
) -> DomainRouter:
    handlers: dict[str, CapabilityHandler] = {
        "search.video_search": _video_search_handler,
        "search.experience_search": _experience_search_handler,
    }
    resolved_public_runtime = public_evidence_runtime
    if resolved_public_runtime is None and public_evidence_runtime_is_configured():
        resolved_public_runtime = StdioPublicEvidenceRuntime.from_environment()
    if resolved_public_runtime is not None:
        for child_tool in PUBLIC_EVIDENCE_CHILD_NAMES:
            handlers[f"public_evidence.{child_tool}"] = _public_evidence_handler(
                resolved_public_runtime,
                child_tool,
            )
    return DomainRouter(load_gateway_catalog(), handlers=handlers)


def _register_domain_tool(
    server: FastMCP,
    router: DomainRouter,
    definition: DomainDefinition,
    context_provider: Callable[[], CapabilityContext],
) -> None:
    async def domain_tool(
        child_tool: str | None = None,
        arguments: dict[str, Any] | None = None,
        manifest_version: str | None = None,
    ) -> dict[str, Any]:
        return await router.invoke(
            domain_id=definition.domain_id,
            child_tool=child_tool,
            arguments=arguments,
            manifest_version=manifest_version,
            context=context_provider(),
        )

    server.tool(
        name=definition.tool_name,
        description=definition.description,
        structured_output=True,
    )(domain_tool)


def build_server(
    *,
    router: DomainRouter | None = None,
    context_provider: Callable[[], CapabilityContext] = context_from_environment,
    lifespan: Any = None,
) -> FastMCP:
    resolved_router = router or build_default_router()
    server = FastMCP(
        "DeerFlow capability gateway",
        instructions=(
            "Choose one best-matching capability domain. Call it with no arguments to "
            "discover its authorized Child Manifest, then call one exact child with "
            "arguments and the returned manifest_version. Child runtimes are internal "
            "providers; never request credentials or raw provider payloads."
        ),
        lifespan=lifespan,
    )
    for definition in DOMAIN_DEFINITIONS.values():
        _register_domain_tool(server, resolved_router, definition, context_provider)
    return server


def main() -> None:
    runtime = StdioPublicEvidenceRuntime.from_environment() if public_evidence_runtime_is_configured() else None
    router = build_default_router(public_evidence_runtime=runtime)

    if runtime is None:
        lifespan = None
    else:

        @asynccontextmanager
        async def lifespan(_server: FastMCP):
            try:
                yield {}
            finally:
                await runtime.close()

    build_server(router=router, lifespan=lifespan).run(transport="stdio")


if __name__ == "__main__":
    main()
