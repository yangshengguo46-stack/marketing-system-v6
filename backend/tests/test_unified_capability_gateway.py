from __future__ import annotations

import json
import tomllib
from pathlib import Path
from typing import Any

import pytest
from mcp.types import CallToolResult

from deerflow.community.douyin_openapi.contracts import CapabilityContext
from deerflow.community.douyin_openapi.gateway_catalog import (
    PUBLIC_EVIDENCE_CHILD_NAMES,
    load_gateway_catalog,
)
from deerflow.community.douyin_openapi.public_evidence import (
    PublicEvidenceRuntime,
    PublicEvidenceUnavailable,
    StdioPublicEvidenceRuntime,
)
from deerflow.community.douyin_openapi.server import build_default_router, build_server

ROOT = Path(__file__).resolve().parents[2]


class _FakePublicEvidenceRuntime(PublicEvidenceRuntime):
    def __init__(self, responses: dict[str, dict[str, Any]]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def call(self, child_tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((child_tool, arguments))
        return self.responses[child_tool]


class _FakeChildSession:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
    ) -> CallToolResult:
        self.calls.append((name, arguments))
        return CallToolResult(
            content=[],
            structuredContent=_search_response(),
            isError=False,
        )


class _FakeSessionPool:
    def __init__(self) -> None:
        self.session = _FakeChildSession()
        self.get_calls: list[tuple[str, str, dict[str, Any]]] = []
        self.closed: list[str] = []

    async def get_session(
        self,
        server_name: str,
        scope_key: str,
        connection: dict[str, Any],
    ) -> _FakeChildSession:
        self.get_calls.append((server_name, scope_key, connection))
        return self.session

    async def close_server(self, server_name: str) -> None:
        self.closed.append(server_name)


def _context() -> CapabilityContext:
    return CapabilityContext(
        configured_auth_modes=frozenset({"authenticated_public_web"}),
        capability_generation="public-evidence-test",
    )


def _search_response() -> dict[str, Any]:
    return {
        "success": True,
        "query": "腕表",
        "cursor": "10",
        "has_more": True,
        "results": [
            {
                "aweme_id": "123",
                "title": "一块腕表如何记录主人",
                "description": "",
                "created_at": "1700000000",
                "duration_ms": 15000,
                "aweme_type": "0",
                "author": {"nickname": "大能", "sec_uid": "stable-account"},
                "metrics": {
                    "likes": 11,
                    "comments": 12,
                    "shares": 13,
                    "collections": 14,
                    "plays": 15,
                },
                "image_count": 0,
                "is_ai_generated": False,
            }
        ],
        "receipt": {
            "provider": "authenticated_public_web",
            "revision": "test-revision",
            "collection": "authenticated_public_web",
            "requested": 5,
            "returned": 1,
            "limitations": ["bounded public observation"],
        },
        "error": "",
    }


def test_gateway_catalog_keeps_official_inventory_and_adds_reviewed_children() -> None:
    catalog = load_gateway_catalog()

    assert catalog.source_row_count == 119
    assert len(catalog.entries) == 119 + len(PUBLIC_EVIDENCE_CHILD_NAMES)
    public_entries = catalog.entries_for_domain("public_evidence")
    assert {entry.child_name for entry in public_entries} == PUBLIC_EVIDENCE_CHILD_NAMES
    assert all(entry.review_status == "adopted" for entry in public_entries)
    assert all(entry.risk_level == "read" for entry in public_entries)
    assert all(entry.auth_mode == "authenticated_public_web" for entry in public_entries)


@pytest.mark.asyncio
async def test_gateway_exposes_domains_only_and_discovers_public_children() -> None:
    runtime = _FakePublicEvidenceRuntime({"search_videos": _search_response()})
    router = build_default_router(public_evidence_runtime=runtime)
    server = build_server(router=router, context_provider=_context)

    tools = await server.list_tools()
    names = {tool.name for tool in tools}

    assert "douyin_public_evidence" in names
    assert names.isdisjoint(PUBLIC_EVIDENCE_CHILD_NAMES)

    manifest = router.discover("public_evidence", _context())
    assert {child["name"] for child in manifest["children"]} == PUBLIC_EVIDENCE_CHILD_NAMES
    assert all(child["callable"] for child in manifest["children"])


@pytest.mark.asyncio
async def test_public_child_dispatch_is_manifest_bound_and_schema_checked() -> None:
    runtime = _FakePublicEvidenceRuntime({"search_videos": _search_response()})
    router = build_default_router(public_evidence_runtime=runtime)
    context = _context()
    manifest = router.discover("public_evidence", context)

    result = await router.dispatch(
        domain_id="public_evidence",
        child_tool="search_videos",
        arguments={"keyword": "腕表", "count": 5},
        manifest_version=manifest["manifest_version"],
        context=context,
    )

    assert result["data"]["results"][0]["author"]["nickname"] == "大能"
    assert result["metadata"]["domain"] == "public_evidence"
    assert runtime.calls == [("search_videos", {"keyword": "腕表", "count": 5})]


@pytest.mark.asyncio
async def test_public_child_rejects_unreviewed_output_without_leaking_it() -> None:
    runtime = _FakePublicEvidenceRuntime({"search_videos": {"success": True, "private_cookie": "must-not-leak"}})
    router = build_default_router(public_evidence_runtime=runtime)
    context = _context()
    manifest = router.discover("public_evidence", context)

    result = await router.dispatch(
        domain_id="public_evidence",
        child_tool="search_videos",
        arguments={"keyword": "腕表"},
        manifest_version=manifest["manifest_version"],
        context=context,
    )

    raw = json.dumps(result, ensure_ascii=False)
    assert result["error"]["code"] == "output_schema_invalid"
    assert "must-not-leak" not in raw
    assert "private_cookie" not in raw


@pytest.mark.asyncio
async def test_child_runtime_reuses_the_gateway_session_pool_and_allowlists_tools(
    tmp_path: Path,
) -> None:
    pool = _FakeSessionPool()
    runtime = StdioPublicEvidenceRuntime(
        root=tmp_path,
        uv="uv",
        session_pool=pool,  # type: ignore[arg-type]
    )

    first = await runtime.call("search_videos", {"keyword": "腕表"})
    second = await runtime.call("search_videos", {"keyword": "雪茄"})

    assert first["success"] is True
    assert second["success"] is True
    assert len(pool.get_calls) == 2
    assert pool.get_calls[0][0:2] == (
        "douyin-public-evidence-child",
        "gateway-process",
    )
    assert pool.session.calls == [
        ("search_videos", {"keyword": "腕表"}),
        ("search_videos", {"keyword": "雪茄"}),
    ]

    with pytest.raises(PublicEvidenceUnavailable, match="not reviewed"):
        await runtime.call("delete_video", {})
    assert len(pool.get_calls) == 2


def test_distribution_has_one_first_party_capability_mcp_entrypoint() -> None:
    pyproject = tomllib.loads((ROOT / "backend/packages/harness/pyproject.toml").read_text(encoding="utf-8"))
    scripts = pyproject["project"]["scripts"]

    assert scripts["deerflow-capability-mcp"] == ("deerflow.community.douyin_openapi.server:main")
    assert "douyin-openapi-mcp" not in scripts
    assert "douyin-official-mcp" not in scripts


def test_example_config_registers_only_the_unified_first_party_gateway() -> None:
    payload = json.loads((ROOT / "extensions_config.example.json").read_text(encoding="utf-8"))
    servers = payload["mcpServers"]

    assert "deerflow_capabilities" in servers
    assert servers["deerflow_capabilities"]["command"] == "deerflow-capability-mcp"
    assert "douyin_openapi" not in servers
    assert "douyin_official_mcp" not in servers
    assert "douyin_community_evidence" not in servers
