from __future__ import annotations

import logging
import os
from typing import Any

import httpx

from deerflow.community.douyin_search.tools import (
    _TOKEN_RETRY_ERROR_CODES,
    _bounded_provider_text,
    _device_id,
    _get_client_token,
    _invalidate_client_token,
    _optional_int,
    _provider_error_code,
)

logger = logging.getLogger(__name__)

_EXPERIENCE_SEARCH_URL = "https://open.douyin.com/dy_open_api/v1/search/experience/"


async def _request_experience_search(access_token: str, params: dict[str, object]) -> dict[str, object]:
    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0), trust_env=True) as client:
        response = await client.get(
            _EXPERIENCE_SEARCH_URL,
            headers={
                "access-token": access_token,
                "content-type": "application/json",
            },
            params=params,
        )
        response.raise_for_status()
        payload = response.json()
    return payload if isinstance(payload, dict) else {}


def _coerce_count(value: Any) -> int:
    try:
        count = int(value)
    except (TypeError, ValueError):
        count = 5
    return max(1, min(count, 10))


def _coerce_non_negative(value: Any) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, number)


def _coerce_choice(value: Any, choices: set[int], default: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return number if number in choices else default


def _normalize_experience_results(payload: dict[str, object], *, query: str) -> dict[str, object]:
    error_code = _provider_error_code(payload)
    if error_code != 0:
        receipt: dict[str, object] = {
            "error": f"Douyin experience search error {error_code}",
            "message": _bounded_provider_text(payload.get("err_msg")),
            "log_id": _bounded_provider_text(payload.get("log_id")),
            "query": query,
        }
        return {key: value for key, value in receipt.items() if value is not None and value != ""}

    data = payload.get("data")
    data = data if isinstance(data, dict) else {}
    raw_results = data.get("data")
    normalized: list[dict[str, object]] = []
    for item in raw_results if isinstance(raw_results, list) else []:
        if not isinstance(item, dict):
            continue
        item_id = _bounded_provider_text(item.get("item_id"), limit=80)
        title = _bounded_provider_text(item.get("title"), limit=500)
        if not item_id or not title:
            continue
        result: dict[str, object] = {
            "title": title,
            "source_type": "douyin_experience",
            "item_id": item_id,
        }
        content_type = _optional_int(item.get("content_type"))
        duration = _optional_int(item.get("duration"))
        nickname = _bounded_provider_text(item.get("nickname"), limit=200)
        if content_type in {1, 2}:
            result["content_type"] = content_type
        if duration is not None:
            result["duration"] = duration
        if nickname:
            result["nickname"] = nickname
        normalized.append(result)

    receipt: dict[str, object] = {
        "query": query,
        "provider": "douyin_open_platform",
        "evidence_role": "topic_evidence",
        "total_results": len(normalized),
        "cursor": _coerce_non_negative(data.get("cursor")),
        "has_more": bool(data.get("has_more")),
        "search_id": _bounded_provider_text(data.get("search_id"), limit=200),
        "results": normalized,
    }
    return {key: value for key, value in receipt.items() if value is not None and value != ""}


async def search_experiences(
    *,
    query: str,
    max_results: int = 5,
    cursor: int = 0,
    content_type: int | None = None,
    sort_type: int = 0,
    search_id: str | None = None,
) -> dict[str, object]:
    query = query.strip()
    if not query:
        return {"error": "query is empty", "query": query}
    client_key = os.getenv("DOUYIN_CLIENT_KEY", "").strip()
    client_secret = os.getenv("DOUYIN_CLIENT_SECRET", "").strip()
    if not client_key or not client_secret:
        return {
            "error": "DOUYIN_CLIENT_KEY and DOUYIN_CLIENT_SECRET are not configured",
            "query": query,
        }

    try:
        params: dict[str, object] = {
            "keyword": query,
            "count": _coerce_count(max_results),
            "cursor": _coerce_non_negative(cursor),
            "device_id": _device_id({}),
            "sort_type": _coerce_choice(sort_type, {0, 1, 2}, 0),
        }
        if content_type is not None:
            params["content_type"] = _coerce_choice(content_type, {1, 2}, 1)
        if isinstance(search_id, str) and search_id.strip():
            params["search_id"] = search_id.strip()

        access_token = await _get_client_token(client_key, client_secret)
        payload = await _request_experience_search(access_token, params)
        if _provider_error_code(payload) in _TOKEN_RETRY_ERROR_CODES:
            await _invalidate_client_token(client_key, client_secret, access_token)
            access_token = await _get_client_token(client_key, client_secret)
            payload = await _request_experience_search(access_token, params)
    except Exception as exc:
        logger.warning("Douyin experience search failed: %s", type(exc).__name__)
        return {"error": "Douyin experience search request failed", "query": query}

    return _normalize_experience_results(payload, query=query)
