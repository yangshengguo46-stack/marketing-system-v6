from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from deerflow.community.byted_search import tools


def _config(**extras):
    return SimpleNamespace(model_extra=extras)


@pytest.mark.asyncio
async def test_byted_search_uses_separate_search_key_and_normalizes_official_receipt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("WEB_SEARCH_API_KEY", "search-key-for-test")
    monkeypatch.setattr(
        tools,
        "get_app_config",
        lambda: SimpleNamespace(get_tool_config=lambda name: _config(query_rewrite=True)),
    )
    captured: dict[str, object] = {}

    async def post_search(api_key: str, body: dict[str, object]) -> dict[str, object]:
        captured["api_key"] = api_key
        captured["body"] = body
        return {
            "Result": {
                "ResultCount": 2,
                "WebResults": [
                    {
                        "Title": "First source",
                        "Url": "https://example.com/first",
                        "Summary": "First summary.",
                    },
                    {
                        "Title": "Second source",
                        "Url": "https://example.com/second",
                        "Snippet": "Second snippet.",
                    },
                ],
            }
        }

    monkeypatch.setattr(tools, "_post_search", post_search)

    raw = await tools.web_search_tool.ainvoke(
        {
            "query": "人情往来 送礼 历史事件",
            "max_results": 2,
        }
    )
    payload = json.loads(raw)

    assert captured["api_key"] == "search-key-for-test"
    assert captured["body"] == {
        "Query": "人情往来 送礼 历史事件",
        "SearchType": "web",
        "Count": 2,
        "NeedSummary": True,
        "QueryControl": {"QueryRewrite": True},
    }
    assert payload == {
        "query": "人情往来 送礼 历史事件",
        "total_results": 2,
        "results": [
            {
                "title": "First source",
                "url": "https://example.com/first",
                "content": "First summary.",
            },
            {
                "title": "Second source",
                "url": "https://example.com/second",
                "content": "Second snippet.",
            },
        ],
    }


@pytest.mark.asyncio
async def test_byted_search_does_not_reuse_an_ark_model_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("WEB_SEARCH_API_KEY", raising=False)
    monkeypatch.setenv("VOLCENGINE_API_KEY", "ark-model-key")
    monkeypatch.setattr(
        tools,
        "get_app_config",
        lambda: SimpleNamespace(get_tool_config=lambda name: _config()),
    )

    raw = await tools.web_search_tool.ainvoke({"query": "test query", "max_results": 2})
    payload = json.loads(raw)

    assert payload["error"] == "WEB_SEARCH_API_KEY is not configured"
    assert payload["query"] == "test query"


@pytest.mark.asyncio
async def test_byted_search_surfaces_provider_error_without_search_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("WEB_SEARCH_API_KEY", "search-key-for-test")
    monkeypatch.setattr(
        tools,
        "get_app_config",
        lambda: SimpleNamespace(get_tool_config=lambda name: _config()),
    )

    async def post_search(api_key: str, body: dict[str, object]) -> dict[str, object]:
        return {
            "ResponseMetadata": {
                "Error": {
                    "Code": "10403",
                    "Message": "permission denied",
                }
            }
        }

    monkeypatch.setattr(tools, "_post_search", post_search)

    raw = await tools.web_search_tool.ainvoke({"query": "test query", "max_results": 2})
    payload = json.loads(raw)

    assert payload == {
        "error": "Byted Web Search error 10403",
        "query": "test query",
    }
