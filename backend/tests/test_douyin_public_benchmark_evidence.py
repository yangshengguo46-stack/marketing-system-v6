from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from langchain.tools import ToolRuntime
from langchain_core.messages import ToolMessage

from deerflow.tools.builtins.douyin_public_benchmark_evidence import (
    collect_public_douyin_benchmark,
)

NOW = datetime(2026, 8, 20, 1, 0, tzinfo=UTC)


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
        tool_call_id="strategy-call-1",
        store=None,
    )


def _manifest() -> dict[str, Any]:
    return {
        "domain": "public_evidence",
        "tool_name": "douyin_public_evidence",
        "children": [{"name": name, "callable": True} for name in ("search_videos", "get_user_info", "get_user_posts")],
        "manifest_version": "public-manifest-v1",
    }


def _domain_result(child_tool: str, data: dict[str, Any]) -> dict[str, Any]:
    return {
        "data": data,
        "warnings": [],
        "metadata": {
            "domain": "public_evidence",
            "child_tool": child_tool,
            "manifest_version": "public-manifest-v1",
            "catalog_version": "catalog-v1",
        },
    }


def _receipt(*, returned: int) -> dict[str, Any]:
    return {
        "provider": "authenticated_public_web",
        "revision": "fixture-v1",
        "collection": "authenticated_public_web",
        "requested": 6,
        "returned": returned,
        "limitations": ["bounded public observation"],
    }


def _post(
    aweme_id: str,
    *,
    sec_uid: str,
    nickname: str,
    likes: int,
) -> dict[str, Any]:
    return {
        "aweme_id": aweme_id,
        "title": f"题目 {aweme_id}",
        "description": "可见公开视频文本",
        "created_at": "1787184000",
        "duration_ms": 15000,
        "aweme_type": "0",
        "author": {"nickname": nickname, "sec_uid": sec_uid},
        "metrics": {
            "likes": likes,
            "comments": 3,
            "shares": 2,
            "collections": 1,
            "plays": 100,
        },
        "image_count": 0,
        "is_ai_generated": False,
    }


class _FakePublicEvidenceTool:
    name = "douyin_public_evidence"
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
async def test_public_benchmark_uses_one_manifest_and_stable_author_post_list() -> None:
    tool = _FakePublicEvidenceTool(
        [
            _manifest(),
            _domain_result(
                "search_videos",
                {
                    "success": True,
                    "query": "人们如何用礼组织人与人的相处",
                    "cursor": "10",
                    "has_more": True,
                    "results": [
                        _post("search-a", sec_uid="account-a", nickname="甲", likes=10),
                        _post("search-b", sec_uid="account-b", nickname="乙", likes=80),
                        _post("search-c", sec_uid="account-b", nickname="乙", likes=20),
                    ],
                    "receipt": _receipt(returned=3),
                    "error": "",
                },
            ),
            _domain_result(
                "get_user_info",
                {
                    "success": True,
                    "user": {
                        "sec_uid": "account-b",
                        "nickname": "乙",
                        "description": "长期讲人际关系",
                        "region": "中国",
                        "gender": "",
                        "following": 12,
                        "fans": 345,
                        "total_interactions": 678,
                        "videos_count": 90,
                    },
                    "receipt": _receipt(returned=1),
                    "error": "",
                },
            ),
            _domain_result(
                "get_user_posts",
                {
                    "success": True,
                    "account_sec_uid": "account-b",
                    "posts": [
                        _post("post-1", sec_uid="account-b", nickname="乙", likes=50),
                        _post("post-2", sec_uid="account-b", nickname="乙", likes=40),
                    ],
                    "pagination": {"max_cursor": "20", "has_more": True},
                    "receipt": _receipt(returned=2),
                    "error": "",
                },
            ),
        ]
    )

    snapshot = await collect_public_douyin_benchmark(
        _runtime(tool),
        query="人们如何用礼组织人与人的相处",
        max_posts=6,
        clock=lambda: NOW,
    )

    assert snapshot is not None
    assert snapshot.profile.external_account_id == "account-b"
    assert snapshot.profile.display_name == "乙"
    assert [post.external_post_id for post in snapshot.posts] == ["post-1", "post-2"]
    assert all(post.author_external_account_id == "account-b" for post in snapshot.posts)
    assert snapshot.coverage.returned_count == 2
    assert [call["args"].get("child_tool") for call in tool.calls] == [
        None,
        "search_videos",
        "get_user_info",
        "get_user_posts",
    ]
    assert tool.calls[1]["args"]["arguments"] == {
        "keyword": "人们如何用礼组织人与人的相处",
        "count": 10,
    }


@pytest.mark.asyncio
async def test_public_benchmark_rejects_a_post_list_from_another_author() -> None:
    tool = _FakePublicEvidenceTool(
        [
            _manifest(),
            _domain_result(
                "search_videos",
                {
                    "success": True,
                    "query": "关系",
                    "cursor": "",
                    "has_more": False,
                    "results": [_post("search-a", sec_uid="account-a", nickname="甲", likes=10)],
                    "receipt": _receipt(returned=1),
                    "error": "",
                },
            ),
            _domain_result(
                "get_user_info",
                {
                    "success": True,
                    "user": {"sec_uid": "account-a", "nickname": "甲"},
                    "receipt": _receipt(returned=1),
                    "error": "",
                },
            ),
            _domain_result(
                "get_user_posts",
                {
                    "success": True,
                    "account_sec_uid": "account-a",
                    "posts": [_post("post-x", sec_uid="account-x", nickname="冒名", likes=1)],
                    "pagination": {"max_cursor": "", "has_more": False},
                    "receipt": _receipt(returned=1),
                    "error": "",
                },
            ),
        ]
    )

    snapshot = await collect_public_douyin_benchmark(
        _runtime(tool),
        query="关系",
        clock=lambda: NOW,
    )

    assert snapshot is None


@pytest.mark.asyncio
async def test_public_benchmark_requires_more_than_one_author_consistent_post() -> None:
    tool = _FakePublicEvidenceTool(
        [
            _manifest(),
            _domain_result(
                "search_videos",
                {
                    "success": True,
                    "query": "关系",
                    "cursor": "",
                    "has_more": False,
                    "results": [_post("search-a", sec_uid="account-a", nickname="甲", likes=10)],
                    "receipt": _receipt(returned=1),
                    "error": "",
                },
            ),
            _domain_result(
                "get_user_info",
                {
                    "success": True,
                    "user": {"sec_uid": "account-a", "nickname": "甲"},
                    "receipt": _receipt(returned=1),
                    "error": "",
                },
            ),
            _domain_result(
                "get_user_posts",
                {
                    "success": True,
                    "account_sec_uid": "account-a",
                    "posts": [_post("post-1", sec_uid="account-a", nickname="甲", likes=1)],
                    "pagination": {"max_cursor": "", "has_more": False},
                    "receipt": _receipt(returned=1),
                    "error": "",
                },
            ),
        ]
    )

    snapshot = await collect_public_douyin_benchmark(
        _runtime(tool),
        query="关系",
        clock=lambda: NOW,
    )

    assert snapshot is None
