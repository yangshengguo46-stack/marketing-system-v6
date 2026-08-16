from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from langchain.tools import ToolRuntime
from langchain_core.messages import ToolMessage

from deerflow.tools.builtins.douyin_topic_evidence import DouyinMcpTopicEvidenceSearch

NOW = datetime(2026, 8, 17, 16, 0, tzinfo=UTC)


def _runtime(tool: Any) -> ToolRuntime:
    return ToolRuntime(
        state={},
        context={
            "thread_id": "thread-1",
            "run_id": "run-1",
            "user_id": "user-1",
        },
        config={"configurable": {"thread_id": "thread-1"}},
        stream_writer=lambda _: None,
        tools=[tool],
        tool_call_id="content-world-call-1",
        store=None,
    )


def _manifest(*, callable_now: bool = True, version: str = "manifest-v1") -> dict[str, Any]:
    child: dict[str, Any] = {
        "name": "video_search",
        "callable": callable_now,
    }
    if not callable_now:
        child["unavailable_reason"] = "auth_not_configured"
    return {
        "domain": "search",
        "tool_name": "douyin_search",
        "children": [child],
        "manifest_version": version,
    }


def _domain_result(*, evidence_role: str = "topic_evidence") -> dict[str, Any]:
    return {
        "data": {
            "query": "人情往来 送礼",
            "provider": "douyin_open_platform",
            "evidence_role": evidence_role,
            "total_results": 1,
            "cursor": 1,
            "has_more": False,
            "search_id": "search-session-id",
            "results": [
                {
                    "title": "礼尚往来为什么不是等价交换",
                    "url": "https://www.douyin.com/video/123",
                    "content": "一条经过官方接口投影的公开视频文本。",
                    "source_type": "douyin_video",
                    "item_id": "123",
                    "nickname": "人情观察",
                    "digg_count": 88,
                }
            ],
        },
        "warnings": [],
        "metadata": {
            "domain": "search",
            "child_tool": "video_search",
            "manifest_version": "manifest-v1",
            "catalog_version": "catalog-v1",
        },
    }


class _FakeDouyinSearchTool:
    name = "douyin_search"
    metadata = {"deerflow_mcp": True}

    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self.responses = responses
        self.calls: list[dict[str, Any]] = []

    async def ainvoke(self, call: dict[str, Any]) -> ToolMessage:
        self.calls.append(call)
        payload = self.responses.pop(0)
        return ToolMessage(
            content=[{"type": "text", "text": "bounded MCP result"}],
            artifact={"structured_content": payload},
            tool_call_id=call["id"],
            name=self.name,
        )


@pytest.mark.asyncio
async def test_topic_research_discovers_and_calls_exact_douyin_mcp_child() -> None:
    tool = _FakeDouyinSearchTool([_manifest(), _domain_result()])
    search = DouyinMcpTopicEvidenceSearch(_runtime(tool), clock=lambda: NOW)

    results = await search("人情往来 送礼", 3)

    assert len(tool.calls) == 2
    discovery_args = tool.calls[0]["args"]
    execution_args = tool.calls[1]["args"]
    assert set(discovery_args) == {"runtime"}
    assert execution_args["child_tool"] == "video_search"
    assert execution_args["manifest_version"] == "manifest-v1"
    assert execution_args["arguments"] == {
        "query": "人情往来 送礼",
        "purpose": "topic_research",
        "max_results": 3,
    }
    assert execution_args["runtime"] is discovery_args["runtime"]
    assert [result.url for result in results] == ["https://www.douyin.com/video/123"]
    assert len(search.snapshots) == 1
    assert search.snapshots[0].evidence_role == "topic_evidence"
    assert search.snapshots[0].collection_method == "official_openapi"
    assert search.snapshots[0].route_receipt["manifest_version"] == "manifest-v1"


@pytest.mark.asyncio
async def test_topic_research_stops_at_manifest_when_douyin_auth_is_unavailable() -> None:
    tool = _FakeDouyinSearchTool([_manifest(callable_now=False)])
    search = DouyinMcpTopicEvidenceSearch(_runtime(tool), clock=lambda: NOW)

    results = await search("人情往来 送礼", 3)

    assert results == ()
    assert search.snapshots == ()
    assert len(tool.calls) == 1


@pytest.mark.asyncio
async def test_topic_research_rejects_a_benchmark_role_from_the_mcp_route() -> None:
    tool = _FakeDouyinSearchTool(
        [
            _manifest(),
            _domain_result(evidence_role="benchmark_account_candidate"),
        ]
    )
    search = DouyinMcpTopicEvidenceSearch(_runtime(tool), clock=lambda: NOW)

    results = await search("人情往来 送礼", 3)

    assert results == ()
    assert search.snapshots == ()


@pytest.mark.asyncio
async def test_topic_research_refreshes_a_stale_manifest_once() -> None:
    stale = {
        "error": {
            "code": "stale_manifest",
            "message": "Discover the current Manifest and retry.",
        }
    }
    tool = _FakeDouyinSearchTool(
        [
            _manifest(version="manifest-v1"),
            stale,
            _manifest(version="manifest-v2"),
            _domain_result(),
        ]
    )
    search = DouyinMcpTopicEvidenceSearch(_runtime(tool), clock=lambda: NOW)

    results = await search("人情往来 送礼", 3)

    assert [call["args"].get("manifest_version") for call in tool.calls] == [
        None,
        "manifest-v1",
        None,
        "manifest-v2",
    ]
    assert [result.url for result in results] == ["https://www.douyin.com/video/123"]


@pytest.mark.asyncio
async def test_topic_research_can_retry_discovery_after_a_transient_mcp_failure() -> None:
    class _TransientFailureTool(_FakeDouyinSearchTool):
        async def ainvoke(self, call: dict[str, Any]) -> ToolMessage:
            self.calls.append(call)
            if len(self.calls) == 1:
                raise ConnectionError("temporary MCP transport failure")
            payload = self.responses.pop(0)
            return ToolMessage(
                content=[{"type": "text", "text": "bounded MCP result"}],
                artifact={"structured_content": payload},
                tool_call_id=call["id"],
                name=self.name,
            )

    tool = _TransientFailureTool([_manifest(), _domain_result()])
    search = DouyinMcpTopicEvidenceSearch(_runtime(tool), clock=lambda: NOW)

    first = await search("人情往来 送礼", 3)
    second = await search("人情往来 送礼", 3)

    assert first == ()
    assert [result.url for result in second] == ["https://www.douyin.com/video/123"]
    assert len(tool.calls) == 3
