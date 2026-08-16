from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from deerflow.community.douyin_search import tools


def _config(**extras):
    return SimpleNamespace(model_extra=extras)


@pytest.fixture(autouse=True)
def _clear_token_cache() -> None:
    tools._reset_token_cache_for_tests()


@pytest.mark.asyncio
async def test_douyin_video_search_uses_stable_token_cache_and_normalizes_public_receipt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        tools,
        "get_app_config",
        lambda: SimpleNamespace(
            get_tool_config=lambda name: _config(
                client_key="douyin-client-key",
                client_secret="douyin-client-secret",
                device_id=123456789,
            )
        ),
    )
    token_calls: list[tuple[str, str]] = []
    search_calls: list[tuple[str, dict[str, object]]] = []

    async def request_token(client_key: str, client_secret: str) -> tuple[str, int]:
        token_calls.append((client_key, client_secret))
        return "clt.private-token", 7200

    async def request_search(access_token: str, params: dict[str, object]) -> dict[str, object]:
        search_calls.append((access_token, params))
        return {
            "err_no": 0,
            "err_msg": "success",
            "log_id": "douyin-log-id",
            "data": {
                "data": {
                    "cursor": 2,
                    "has_more": True,
                    "search_id": "search-session-id",
                    "video_list": [
                        {
                            "item_id": "7471252140422401337",
                            "title": "送礼为什么最怕用力过猛",
                            "high_quality_text": "礼物真正传递的是关系中的分寸。",
                            "nickname": "礼物研究所",
                            "create_time": 1739536450,
                            "statistics": {"digg_count": 9254},
                            "link": "https://www.douyin.com/video/7471252140422401337",
                            "cover": "https://signed.example/temporary-cover",
                            "avatar": "https://signed.example/temporary-avatar",
                        }
                    ],
                }
            },
        }

    monkeypatch.setattr(tools, "_request_stable_client_token", request_token)
    monkeypatch.setattr(tools, "_request_video_search", request_search)

    first_raw = await tools.douyin_video_search_tool.ainvoke(
        {
            "query": "人情往来 送礼",
            "max_results": 5,
            "cursor": 0,
            "publish_time": 0,
            "sort_type": 0,
        }
    )
    second_raw = await tools.douyin_video_search_tool.ainvoke(
        {
            "query": "人情往来 送礼",
            "max_results": 5,
        }
    )
    first = json.loads(first_raw)

    assert token_calls == [("douyin-client-key", "douyin-client-secret")]
    assert len(search_calls) == 2
    assert search_calls[0] == (
        "clt.private-token",
        {
            "keyword": "人情往来 送礼",
            "count": 5,
            "cursor": 0,
            "device_id": 123456789,
            "publish_time": 0,
            "sort_type": 0,
        },
    )
    assert first == {
        "query": "人情往来 送礼",
        "provider": "douyin_open_platform",
        "evidence_role": "topic_evidence",
        "total_results": 1,
        "cursor": 2,
        "has_more": True,
        "search_id": "search-session-id",
        "results": [
            {
                "title": "送礼为什么最怕用力过猛",
                "url": "https://www.douyin.com/video/7471252140422401337",
                "content": "礼物真正传递的是关系中的分寸。",
                "source_type": "douyin_video",
                "item_id": "7471252140422401337",
                "nickname": "礼物研究所",
                "create_time": 1739536450,
                "digg_count": 9254,
            }
        ],
    }
    assert "douyin-client-secret" not in first_raw
    assert "clt.private-token" not in first_raw
    assert "temporary-cover" not in first_raw
    assert "temporary-avatar" not in first_raw
    assert json.loads(second_raw)["total_results"] == 1


@pytest.mark.asyncio
async def test_douyin_video_search_refreshes_once_after_expired_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        tools,
        "get_app_config",
        lambda: SimpleNamespace(
            get_tool_config=lambda name: _config(
                client_key="douyin-client-key",
                client_secret="douyin-client-secret",
            )
        ),
    )
    tokens = iter(("clt.expired", "clt.fresh"))
    token_calls = 0
    search_tokens: list[str] = []

    async def request_token(client_key: str, client_secret: str) -> tuple[str, int]:
        nonlocal token_calls
        token_calls += 1
        return next(tokens), 7200

    async def request_search(access_token: str, params: dict[str, object]) -> dict[str, object]:
        search_tokens.append(access_token)
        if access_token == "clt.expired":
            return {"err_no": 28001008, "err_msg": "access_token expired", "log_id": "expired-log"}
        return {
            "err_no": 0,
            "err_msg": "success",
            "log_id": "fresh-log",
            "data": {"data": {"cursor": 0, "has_more": False, "video_list": []}},
        }

    monkeypatch.setattr(tools, "_request_stable_client_token", request_token)
    monkeypatch.setattr(tools, "_request_video_search", request_search)

    raw = await tools.douyin_video_search_tool.ainvoke(
        {
            "query": "火锅 历史",
            "max_results": 3,
        }
    )

    assert token_calls == 2
    assert search_tokens == ["clt.expired", "clt.fresh"]
    assert json.loads(raw)["total_results"] == 0


@pytest.mark.asyncio
async def test_douyin_video_search_requires_local_credentials_without_leaking_other_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DOUYIN_CLIENT_KEY", raising=False)
    monkeypatch.delenv("DOUYIN_CLIENT_SECRET", raising=False)
    monkeypatch.setenv("VOLCENGINE_API_KEY", "unrelated-model-key")
    monkeypatch.setattr(
        tools,
        "get_app_config",
        lambda: SimpleNamespace(get_tool_config=lambda name: _config()),
    )

    raw = await tools.douyin_video_search_tool.ainvoke(
        {
            "query": "海鲜 饮食文化",
            "max_results": 3,
        }
    )
    payload = json.loads(raw)

    assert payload == {
        "error": "DOUYIN_CLIENT_KEY and DOUYIN_CLIENT_SECRET are not configured",
        "query": "海鲜 饮食文化",
    }
    assert "unrelated-model-key" not in raw


@pytest.mark.asyncio
async def test_douyin_video_search_returns_bounded_error_for_invalid_device_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        tools,
        "get_app_config",
        lambda: SimpleNamespace(
            get_tool_config=lambda name: _config(
                client_key="douyin-client-key",
                client_secret="douyin-client-secret",
                device_id="not-a-number",
            )
        ),
    )

    raw = await tools.douyin_video_search_tool.ainvoke(
        {
            "query": "海鲜 饮食文化",
            "max_results": 3,
        }
    )

    assert json.loads(raw) == {
        "error": "Douyin video search request failed",
        "query": "海鲜 饮食文化",
    }


@pytest.mark.asyncio
async def test_douyin_video_search_surfaces_permission_error_as_bounded_receipt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        tools,
        "get_app_config",
        lambda: SimpleNamespace(
            get_tool_config=lambda name: _config(
                client_key="douyin-client-key",
                client_secret="douyin-client-secret",
            )
        ),
    )

    async def request_token(client_key: str, client_secret: str) -> tuple[str, int]:
        return "clt.private-token", 7200

    async def request_search(access_token: str, params: dict[str, object]) -> dict[str, object]:
        return {
            "err_no": 28001018,
            "err_msg": "应用未获得该能力",
            "log_id": "permission-log-id",
        }

    monkeypatch.setattr(tools, "_request_stable_client_token", request_token)
    monkeypatch.setattr(tools, "_request_video_search", request_search)

    raw = await tools.douyin_video_search_tool.ainvoke(
        {
            "query": "腕表 历史人物",
            "max_results": 3,
        }
    )

    assert json.loads(raw) == {
        "error": "Douyin video search error 28001018",
        "message": "应用未获得该能力",
        "log_id": "permission-log-id",
        "query": "腕表 历史人物",
    }
    assert "clt.private-token" not in raw
