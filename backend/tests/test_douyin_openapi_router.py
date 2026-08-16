from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import pytest

from deerflow.community.douyin_openapi import catalog as catalog_module
from deerflow.community.douyin_openapi.catalog import load_official_catalog
from deerflow.community.douyin_openapi.contracts import CapabilityContext
from deerflow.community.douyin_openapi.domains import DOMAIN_DEFINITIONS
from deerflow.community.douyin_openapi.router import DomainRouter
from deerflow.community.douyin_openapi.server import build_server

Handler = Callable[[dict[str, Any], CapabilityContext], Awaitable[dict[str, Any]]]


def _context(
    *,
    scopes: set[str] | None = None,
    auth_modes: set[str] | None = None,
    generation: str = "test-generation",
) -> CapabilityContext:
    return CapabilityContext(
        granted_scopes=frozenset(scopes or set()),
        configured_auth_modes=frozenset(auth_modes or set()),
        capability_generation=generation,
    )


async def _valid_video_handler(arguments: dict[str, Any], context: CapabilityContext) -> dict[str, Any]:
    del context
    return {
        "query": arguments["query"],
        "provider": "douyin_open_platform",
        "evidence_role": "topic_evidence",
        "total_results": 0,
        "cursor": 0,
        "has_more": False,
        "results": [],
    }


def _router(handler: Handler | None = _valid_video_handler) -> DomainRouter:
    handlers = {"search.video_search": handler} if handler is not None else {}
    return DomainRouter(load_official_catalog(), handlers=handlers)


def test_official_catalog_snapshot_covers_every_directory_row_once() -> None:
    catalog = load_official_catalog()

    assert catalog.source_row_count == 119
    assert len(catalog.entries) == 119
    assert len({entry.capability_id for entry in catalog.entries}) == 119
    assert len({entry.documentation_url for entry in catalog.entries}) == 119
    assert {entry.domain for entry in catalog.entries} <= set(DOMAIN_DEFINITIONS)
    assert sum(catalog.section_counts.values()) == 119
    assert catalog.section_counts == {
        "个人资料": 6,
        "关系能力": 7,
        "内容能力": 8,
        "搜索能力": 2,
        "私信群聊": 7,
        "数据开放服务": 7,
        "抖音生活服务接口": 27,
        "小程序接口": 31,
        "工具能力": 7,
        "服务市场开放能力": 4,
        "小程序推广计划": 10,
        "分身技能数据": 1,
        "汽水音乐": 2,
    }


def test_catalog_loader_rejects_snapshot_content_hash_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = Path(catalog_module.__file__).with_name("catalog_snapshot.json")
    payload = json.loads(source.read_text(encoding="utf-8"))
    payload["entries"][0]["description_zh"] = "tampered catalog entry"
    snapshot = tmp_path / "catalog_snapshot.json"
    snapshot.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(catalog_module, "_SNAPSHOT_PATH", snapshot)
    load_official_catalog.cache_clear()

    try:
        with pytest.raises(ValueError, match="content hash"):
            load_official_catalog()
    finally:
        load_official_catalog.cache_clear()


def test_domain_surface_is_bounded_and_responsibilities_are_explicit() -> None:
    catalog = load_official_catalog()
    tools = catalog.list_domain_tools()

    assert 8 <= len(tools) <= 20
    assert len({tool["name"] for tool in tools}) == len(tools)
    assert "douyin_capabilities" not in {tool["name"] for tool in tools}
    assert len(json.dumps(tools, ensure_ascii=False).encode("utf-8")) <= 24 * 1024
    assert all(tool["includes"] and tool["excludes"] for tool in tools)
    assert all(len([entry for entry in catalog.entries if entry.domain == domain_id]) <= 32 for domain_id in DOMAIN_DEFINITIONS)


def test_discovery_hides_ungranted_children() -> None:
    manifest = _router().discover("search", _context())

    assert manifest["children"] == []
    assert manifest["metadata"]["catalog_entries"] == 2
    assert manifest["metadata"]["disclosed_children"] == 0


def test_discovery_keeps_authorized_but_unavailable_child_with_reason() -> None:
    manifest = _router(handler=None).discover(
        "search",
        _context(scopes={"aweme.dy.video_search"}, auth_modes={"client_token"}),
    )

    assert [child["name"] for child in manifest["children"]] == ["video_search"]
    assert manifest["children"][0]["callable"] is False
    assert manifest["children"][0]["unavailable_reason"] == "adapter_not_registered"


def test_search_domain_can_disclose_both_reviewed_search_children() -> None:
    async def experience_handler(arguments: dict[str, Any], context: CapabilityContext) -> dict[str, Any]:
        del context
        return {
            "query": arguments["query"],
            "provider": "douyin_open_platform",
            "evidence_role": "topic_evidence",
            "total_results": 0,
            "cursor": 0,
            "has_more": False,
            "results": [],
        }

    router = DomainRouter(
        load_official_catalog(),
        handlers={
            "search.video_search": _valid_video_handler,
            "search.experience_search": experience_handler,
        },
    )
    manifest = router.discover(
        "search",
        _context(
            scopes={"aweme.dy.video_search", "aweme.experience.search"},
            auth_modes={"client_token"},
        ),
    )

    assert [child["name"] for child in manifest["children"]] == [
        "video_search",
        "experience_search",
    ]
    assert all(child["callable"] for child in manifest["children"])


def test_discovery_marks_missing_auth_without_exposing_credentials() -> None:
    raw = json.dumps(
        _router().discover(
            "search",
            _context(scopes={"aweme.dy.video_search"}),
        ),
        ensure_ascii=False,
    )
    manifest = json.loads(raw)

    assert manifest["children"][0]["callable"] is False
    assert manifest["children"][0]["unavailable_reason"] == "auth_not_configured"
    assert "client_secret" not in raw
    assert "access_token" not in raw


@pytest.mark.asyncio
async def test_exact_child_dispatch_revalidates_manifest_and_schemas() -> None:
    router = _router()
    context = _context(
        scopes={"aweme.dy.video_search"},
        auth_modes={"client_token"},
    )
    manifest = router.discover("search", context)

    result = await router.dispatch(
        domain_id="search",
        child_tool="video_search",
        arguments={"query": "人情往来 送礼", "max_results": 5},
        manifest_version=manifest["manifest_version"],
        context=context,
    )

    assert result["data"]["query"] == "人情往来 送礼"
    assert result["metadata"] == {
        "domain": "search",
        "child_tool": "video_search",
        "manifest_version": manifest["manifest_version"],
        "catalog_version": load_official_catalog().catalog_version,
    }


@pytest.mark.asyncio
async def test_stale_manifest_is_rejected_before_handler_runs() -> None:
    calls = 0

    async def handler(arguments: dict[str, Any], context: CapabilityContext) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        return await _valid_video_handler(arguments, context)

    router = _router(handler)
    old_context = _context(
        scopes={"aweme.dy.video_search"},
        auth_modes={"client_token"},
        generation="generation-one",
    )
    old_manifest = router.discover("search", old_context)

    result = await router.dispatch(
        domain_id="search",
        child_tool="video_search",
        arguments={"query": "腕表 历史"},
        manifest_version=old_manifest["manifest_version"],
        context=_context(
            scopes={"aweme.dy.video_search"},
            auth_modes={"client_token"},
            generation="generation-two",
        ),
    )

    assert result["error"]["code"] == "stale_manifest"
    assert calls == 0


@pytest.mark.asyncio
async def test_invalid_child_input_is_rejected_before_handler_runs() -> None:
    calls = 0

    async def handler(arguments: dict[str, Any], context: CapabilityContext) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        return await _valid_video_handler(arguments, context)

    router = _router(handler)
    context = _context(
        scopes={"aweme.dy.video_search"},
        auth_modes={"client_token"},
    )
    manifest = router.discover("search", context)

    result = await router.dispatch(
        domain_id="search",
        child_tool="video_search",
        arguments={"query": "", "made_up_parameter": True},
        manifest_version=manifest["manifest_version"],
        context=context,
    )

    assert result["error"]["code"] == "input_schema_invalid"
    assert calls == 0


@pytest.mark.asyncio
async def test_invalid_child_output_is_rejected_without_leaking_payload() -> None:
    async def invalid_handler(arguments: dict[str, Any], context: CapabilityContext) -> dict[str, Any]:
        del arguments, context
        return {"private_access_token": "act.must-not-leak"}

    router = _router(invalid_handler)
    context = _context(
        scopes={"aweme.dy.video_search"},
        auth_modes={"client_token"},
    )
    manifest = router.discover("search", context)

    raw = json.dumps(
        await router.dispatch(
            domain_id="search",
            child_tool="video_search",
            arguments={"query": "海鲜 饮食文化"},
            manifest_version=manifest["manifest_version"],
            context=context,
        ),
        ensure_ascii=False,
    )

    assert json.loads(raw)["error"]["code"] == "output_schema_invalid"
    assert "act.must-not-leak" not in raw


@pytest.mark.asyncio
async def test_mcp_server_exposes_only_domain_tools() -> None:
    context = _context(
        scopes={"aweme.dy.video_search"},
        auth_modes={"client_token"},
    )
    server = build_server(router=_router(), context_provider=lambda: context)

    tools = await server.list_tools()
    names = {tool.name for tool in tools}

    assert names == {definition.tool_name for definition in DOMAIN_DEFINITIONS.values()}
    assert "douyin_capabilities" not in names
