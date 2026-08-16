from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import secrets
import time
from dataclasses import dataclass
from typing import Any, Literal

import httpx
from langchain.tools import tool

from deerflow.config import get_app_config

logger = logging.getLogger(__name__)

_STABLE_TOKEN_URL = "https://open.douyin.com/oauth/stable_client_token/"
_VIDEO_SEARCH_URL = "https://open.douyin.com/dy_open_api/v2/search/video/"
_MAX_RESULTS = 20
_TOKEN_REFRESH_SKEW_SECONDS = 60
_TOKEN_RETRY_ERROR_CODES = {28001003, 28001008}
_EPHEMERAL_DEVICE_ID = secrets.randbelow(8_000_000_000_000_000) + 1_000_000_000_000_000


@dataclass(frozen=True)
class _TokenEntry:
    access_token: str
    expires_at: float


_token_cache: dict[str, _TokenEntry] = {}
_token_lock = asyncio.Lock()


def _tool_extras() -> dict[str, Any]:
    config = get_app_config().get_tool_config("douyin_video_search")
    if config is None:
        return {}
    return config.model_extra or {}


def _configured_text(extras: dict[str, Any], name: str, env_name: str) -> str | None:
    value = extras.get(name) or os.getenv(env_name)
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


def _credential_fingerprint(client_key: str, client_secret: str) -> str:
    return hashlib.sha256(f"{client_key}\0{client_secret}".encode()).hexdigest()


def _coerce_max_results(value: Any) -> int:
    try:
        count = int(value)
    except (TypeError, ValueError):
        count = 5
    return max(1, min(count, _MAX_RESULTS))


def _coerce_non_negative_int(value: Any, *, default: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(0, number)


def _coerce_choice(value: Any, *, allowed: set[int], default: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return number if number in allowed else default


def _device_id(extras: dict[str, Any]) -> int:
    value = extras.get("device_id") or os.getenv("DOUYIN_DEVICE_ID")
    if value in {None, ""}:
        return _EPHEMERAL_DEVICE_ID
    try:
        device_id = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("DOUYIN_DEVICE_ID must be a positive integer") from exc
    if device_id <= 0:
        raise ValueError("DOUYIN_DEVICE_ID must be a positive integer")
    return device_id


async def _request_stable_client_token(client_key: str, client_secret: str) -> tuple[str, int]:
    body = {
        "client_key": client_key,
        "client_secret": client_secret,
        "grant_type": "client_credential",
    }
    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0), trust_env=True) as client:
        response = await client.post(
            _STABLE_TOKEN_URL,
            headers={"content-type": "application/json"},
            json=body,
        )
        response.raise_for_status()
        payload = response.json()

    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        raise ValueError("Douyin token response did not contain data")
    error_code = _coerce_non_negative_int(data.get("error_code"), default=-1)
    access_token = data.get("access_token")
    expires_in = _coerce_non_negative_int(data.get("expires_in"), default=0)
    if error_code != 0 or not isinstance(access_token, str) or not access_token.strip() or expires_in <= 0:
        raise ValueError(f"Douyin token error {error_code}")
    return access_token.strip(), expires_in


async def _request_video_search(access_token: str, params: dict[str, object]) -> dict[str, object]:
    headers = {
        "access-token": access_token,
        "content-type": "application/json",
    }
    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0), trust_env=True) as client:
        response = await client.get(_VIDEO_SEARCH_URL, headers=headers, params=params)
        response.raise_for_status()
        payload = response.json()
    return payload if isinstance(payload, dict) else {}


async def _get_client_token(client_key: str, client_secret: str) -> str:
    cache_key = _credential_fingerprint(client_key, client_secret)
    now = time.monotonic()
    cached = _token_cache.get(cache_key)
    if cached is not None and cached.expires_at - _TOKEN_REFRESH_SKEW_SECONDS > now:
        return cached.access_token

    async with _token_lock:
        now = time.monotonic()
        cached = _token_cache.get(cache_key)
        if cached is not None and cached.expires_at - _TOKEN_REFRESH_SKEW_SECONDS > now:
            return cached.access_token
        access_token, expires_in = await _request_stable_client_token(client_key, client_secret)
        _token_cache[cache_key] = _TokenEntry(
            access_token=access_token,
            expires_at=now + expires_in,
        )
        return access_token


async def _invalidate_client_token(client_key: str, client_secret: str, access_token: str) -> None:
    cache_key = _credential_fingerprint(client_key, client_secret)
    async with _token_lock:
        cached = _token_cache.get(cache_key)
        if cached is not None and cached.access_token == access_token:
            _token_cache.pop(cache_key, None)


def _reset_token_cache_for_tests() -> None:
    _token_cache.clear()


def _provider_error_code(payload: dict[str, object]) -> int:
    try:
        return int(payload.get("err_no", -1))
    except (TypeError, ValueError):
        return -1


def _bounded_provider_text(value: Any, *, limit: int = 300) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())[:limit]


def _optional_int(value: Any) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def _normalize_video_results(
    payload: dict[str, object],
    *,
    query: str,
    purpose: Literal["topic_research", "benchmark_discovery"],
) -> dict[str, object]:
    error_code = _provider_error_code(payload)
    if error_code != 0:
        receipt: dict[str, object] = {
            "error": f"Douyin video search error {error_code}",
            "message": _bounded_provider_text(payload.get("err_msg")),
            "log_id": _bounded_provider_text(payload.get("log_id")),
            "query": query,
        }
        return {key: value for key, value in receipt.items() if value is not None and value != ""}

    outer_data = payload.get("data")
    inner_data = outer_data.get("data") if isinstance(outer_data, dict) else None
    data = inner_data if isinstance(inner_data, dict) else {}
    video_list = data.get("video_list")
    normalized: list[dict[str, object]] = []
    for item in video_list if isinstance(video_list, list) else []:
        if not isinstance(item, dict):
            continue
        item_id = _bounded_provider_text(item.get("item_id"), limit=80)
        title = _bounded_provider_text(item.get("title"), limit=500)
        link = _bounded_provider_text(item.get("link"), limit=1000)
        content = _bounded_provider_text(item.get("high_quality_text"), limit=4000) or title
        if not item_id or not title or not link or not content:
            continue
        result: dict[str, object] = {
            "title": title,
            "url": link,
            "content": content,
            "source_type": "douyin_video",
            "item_id": item_id,
        }
        nickname = _bounded_provider_text(item.get("nickname"), limit=200)
        create_time = _optional_int(item.get("create_time"))
        statistics = item.get("statistics")
        digg_count = _optional_int(statistics.get("digg_count")) if isinstance(statistics, dict) else None
        if nickname:
            result["nickname"] = nickname
        if create_time is not None:
            result["create_time"] = create_time
        if digg_count is not None:
            result["digg_count"] = digg_count
        normalized.append(result)

    receipt = {
        "query": query,
        "provider": "douyin_open_platform",
        "evidence_role": ("benchmark_account_candidate" if purpose == "benchmark_discovery" else "topic_evidence"),
        "total_results": len(normalized),
        "cursor": _coerce_non_negative_int(data.get("cursor"), default=0),
        "has_more": bool(data.get("has_more")),
        "search_id": _bounded_provider_text(data.get("search_id"), limit=200),
        "results": normalized,
    }
    return {key: value for key, value in receipt.items() if value is not None and value != ""}


@tool("douyin_video_search", parse_docstring=True)
async def douyin_video_search_tool(
    query: str,
    purpose: Literal["topic_research", "benchmark_discovery"] = "topic_research",
    max_results: int = 5,
    cursor: int = 0,
    publish_time: int = 0,
    sort_type: int = 0,
    search_id: str | None = None,
) -> str:
    """Search public Douyin videos through the official Douyin Open Platform.

    Results are bounded topic evidence or benchmark-account candidate evidence. A search
    result is never a complete competitor-account analysis and does not establish an
    account's identity, audience, positioning, or performance.

    Args:
        query: Search keywords describing the public Douyin videos to find.
        purpose: Use topic_research for subjects or benchmark_discovery to find candidate accounts.
        max_results: Maximum normalized results to return, capped at 20.
        cursor: Pagination cursor. Use 0 for the first page.
        publish_time: Publish window: 0 any time, 1 one day, 7 seven days, 180 half-year.
        sort_type: Sort order: 0 relevance, 1 most liked, 2 newest.
        search_id: Search session ID returned by the first page when loading more results.
    """
    query = query.strip()
    if not query:
        return json.dumps({"error": "query is empty", "query": query}, ensure_ascii=False)

    extras = _tool_extras()
    client_key = _configured_text(extras, "client_key", "DOUYIN_CLIENT_KEY")
    client_secret = _configured_text(extras, "client_secret", "DOUYIN_CLIENT_SECRET")
    if client_key is None or client_secret is None:
        return json.dumps(
            {
                "error": "DOUYIN_CLIENT_KEY and DOUYIN_CLIENT_SECRET are not configured",
                "query": query,
            },
            ensure_ascii=False,
        )

    try:
        configured_count = extras.get("max_results", max_results)
        params: dict[str, object] = {
            "keyword": query,
            "count": _coerce_max_results(configured_count),
            "cursor": _coerce_non_negative_int(cursor, default=0),
            "device_id": _device_id(extras),
            "publish_time": _coerce_choice(publish_time, allowed={0, 1, 7, 180}, default=0),
            "sort_type": _coerce_choice(sort_type, allowed={0, 1, 2}, default=0),
        }
        if isinstance(search_id, str) and search_id.strip():
            params["search_id"] = search_id.strip()

        access_token = await _get_client_token(client_key, client_secret)
        payload = await _request_video_search(access_token, params)
        if _provider_error_code(payload) in _TOKEN_RETRY_ERROR_CODES:
            await _invalidate_client_token(client_key, client_secret, access_token)
            access_token = await _get_client_token(client_key, client_secret)
            payload = await _request_video_search(access_token, params)
    except Exception as exc:
        logger.warning("Douyin Open Platform video search failed: %s", type(exc).__name__)
        return json.dumps(
            {
                "error": "Douyin video search request failed",
                "query": query,
            },
            ensure_ascii=False,
        )

    return json.dumps(
        _normalize_video_results(payload, query=query, purpose=purpose),
        ensure_ascii=False,
    )
