from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable
from typing import Any

from mcp.server.fastmcp import FastMCP

from deerflow.community.douyin_search.tools import douyin_video_search_tool

from .adapters.search import search_experiences
from .catalog import load_official_catalog
from .contracts import CapabilityContext
from .domains import DOMAIN_DEFINITIONS, DomainDefinition
from .router import CapabilityHandler, DomainRouter


def _parse_csv_env(name: str) -> frozenset[str]:
    value = os.getenv(name, "")
    return frozenset(part.strip() for part in value.split(",") if part.strip())


def context_from_environment() -> CapabilityContext:
    auth_modes: set[str] = set()
    if os.getenv("DOUYIN_CLIENT_KEY") and os.getenv("DOUYIN_CLIENT_SECRET"):
        auth_modes.add("client_token")
    scopes = _parse_csv_env("DOUYIN_APPROVED_SCOPES")
    generation_payload = {
        "auth_modes": sorted(auth_modes),
        "scopes": sorted(scopes),
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


def build_default_router() -> DomainRouter:
    handlers: dict[str, CapabilityHandler] = {
        "search.video_search": _video_search_handler,
        "search.experience_search": _experience_search_handler,
    }
    return DomainRouter(load_official_catalog(), handlers=handlers)


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
) -> FastMCP:
    resolved_router = router or build_default_router()
    server = FastMCP(
        "Douyin OpenAPI capability gateway",
        instructions=(
            "Choose one best-matching Douyin domain. Call it with no arguments to discover its authorized child manifest, then call one exact child with arguments and the returned manifest_version. Do not open unrelated domains."
        ),
    )
    for definition in DOMAIN_DEFINITIONS.values():
        _register_domain_tool(server, resolved_router, definition, context_provider)
    return server


def main() -> None:
    build_server().run(transport="stdio")


if __name__ == "__main__":
    main()
