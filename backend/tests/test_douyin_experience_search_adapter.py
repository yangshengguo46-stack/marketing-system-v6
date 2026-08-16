from __future__ import annotations

import json

import pytest

from deerflow.community.douyin_openapi.adapters import search


@pytest.mark.asyncio
async def test_experience_search_uses_app_token_and_returns_bounded_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DOUYIN_CLIENT_KEY", "douyin-client-key")
    monkeypatch.setenv("DOUYIN_CLIENT_SECRET", "douyin-client-secret")
    monkeypatch.setenv("DOUYIN_DEVICE_ID", "123456789")
    token_calls: list[tuple[str, str]] = []
    request_calls: list[tuple[str, dict[str, object]]] = []

    async def get_token(client_key: str, client_secret: str) -> str:
        token_calls.append((client_key, client_secret))
        return "clt.private-token"

    async def request(access_token: str, params: dict[str, object]) -> dict[str, object]:
        request_calls.append((access_token, params))
        return {
            "err_no": 0,
            "err_msg": "success",
            "log_id": "experience-log-id",
            "data": {
                "cursor": 1,
                "has_more": True,
                "search_id": "experience-session-id",
                "data": [
                    {
                        "item_id": "7495016836209233211",
                        "title": "在重庆吃火锅的一百种方式",
                        "content_type": 2,
                        "duration": 0,
                        "nickname": "火锅研究所",
                        "cover": {"url_list": ["https://signed.example/temporary-cover"]},
                    }
                ],
            },
        }

    monkeypatch.setattr(search, "_get_client_token", get_token)
    monkeypatch.setattr(search, "_request_experience_search", request)

    receipt = await search.search_experiences(
        query="火锅 饮食文化",
        max_results=10,
        cursor=0,
        content_type=2,
        sort_type=0,
    )
    raw = json.dumps(receipt, ensure_ascii=False)

    assert token_calls == [("douyin-client-key", "douyin-client-secret")]
    assert request_calls == [
        (
            "clt.private-token",
            {
                "keyword": "火锅 饮食文化",
                "count": 10,
                "cursor": 0,
                "device_id": 123456789,
                "content_type": 2,
                "sort_type": 0,
            },
        )
    ]
    assert receipt == {
        "query": "火锅 饮食文化",
        "provider": "douyin_open_platform",
        "evidence_role": "topic_evidence",
        "total_results": 1,
        "cursor": 1,
        "has_more": True,
        "search_id": "experience-session-id",
        "results": [
            {
                "title": "在重庆吃火锅的一百种方式",
                "source_type": "douyin_experience",
                "item_id": "7495016836209233211",
                "content_type": 2,
                "duration": 0,
                "nickname": "火锅研究所",
            }
        ],
    }
    assert "clt.private-token" not in raw
    assert "temporary-cover" not in raw
    assert "123456789" not in raw


@pytest.mark.asyncio
async def test_experience_search_rejects_missing_credentials_without_requesting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DOUYIN_CLIENT_KEY", raising=False)
    monkeypatch.delenv("DOUYIN_CLIENT_SECRET", raising=False)

    async def unexpected_request(access_token: str, params: dict[str, object]) -> dict[str, object]:
        raise AssertionError((access_token, params))

    monkeypatch.setattr(search, "_request_experience_search", unexpected_request)

    receipt = await search.search_experiences(query="医美 变美")

    assert receipt == {
        "error": "DOUYIN_CLIENT_KEY and DOUYIN_CLIENT_SECRET are not configured",
        "query": "医美 变美",
    }
