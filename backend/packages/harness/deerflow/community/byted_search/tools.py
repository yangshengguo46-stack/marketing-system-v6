# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
# Licensed under the Apache License, Version 2.0.

from __future__ import annotations

import json
import logging
import os
from typing import Any

import httpx
from langchain.tools import tool

from deerflow.config import get_app_config

logger = logging.getLogger(__name__)

_SEARCH_URL = "https://open.feedcoopapi.com/search_api/web_search"
_TRAFFIC_TAG_HEADER = "X-Traffic-Tag"
_TRAFFIC_TAG_VALUE = "deerflow_content_research"
_MAX_RESULTS = 50


def _tool_extras() -> dict[str, Any]:
    config = get_app_config().get_tool_config("web_search")
    if config is None:
        return {}
    return config.model_extra or {}


def _api_key(extras: dict[str, Any]) -> str | None:
    value = extras.get("api_key") or os.getenv("WEB_SEARCH_API_KEY")
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


def _coerce_max_results(value: Any) -> int:
    try:
        count = int(value)
    except (TypeError, ValueError):
        count = 5
    return max(1, min(count, _MAX_RESULTS))


def _build_body(query: str, max_results: int, extras: dict[str, Any]) -> dict[str, Any]:
    body: dict[str, Any] = {
        "Query": query,
        "SearchType": "web",
        "Count": max_results,
        "NeedSummary": True,
    }
    time_range = extras.get("time_range")
    if isinstance(time_range, str) and time_range.strip():
        body["TimeRange"] = time_range.strip()
    auth_level = extras.get("auth_level")
    if auth_level in {1, "1"}:
        body["Filter"] = {"AuthInfoLevel": 1}
    if extras.get("query_rewrite") is True:
        body["QueryControl"] = {"QueryRewrite": True}
    return body


async def _post_search(api_key: str, body: dict[str, Any]) -> dict[str, Any]:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        _TRAFFIC_TAG_HEADER: _TRAFFIC_TAG_VALUE,
    }
    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0), trust_env=True) as client:
        response = await client.post(_SEARCH_URL, headers=headers, json=body)
        response.raise_for_status()
        payload = response.json()
    return payload if isinstance(payload, dict) else {}


def _text(item: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


@tool("web_search", parse_docstring=True)
async def web_search_tool(query: str, max_results: int = 5) -> str:
    """Search public web information through the official ByteDance/Volcengine search API.

    Args:
        query: Search keywords describing the information to find.
        max_results: Maximum number of normalized web results to return, capped at 50.
    """
    query = query.strip()
    if not query:
        return json.dumps({"error": "query is empty", "query": query}, ensure_ascii=False)

    extras = _tool_extras()
    api_key = _api_key(extras)
    if api_key is None:
        return json.dumps(
            {
                "error": "WEB_SEARCH_API_KEY is not configured",
                "query": query,
            },
            ensure_ascii=False,
        )

    configured_count = extras.get("max_results", max_results)
    count = _coerce_max_results(configured_count)
    try:
        payload = await _post_search(api_key, _build_body(query, count, extras))
    except Exception as exc:
        logger.warning("Byted Web Search request failed: %s", type(exc).__name__)
        return json.dumps(
            {
                "error": "Byted Web Search request failed",
                "query": query,
            },
            ensure_ascii=False,
        )

    provider_error = (payload.get("ResponseMetadata") or {}).get("Error")
    if isinstance(provider_error, dict):
        code = str(provider_error.get("Code") or "unknown")
        return json.dumps(
            {
                "error": f"Byted Web Search error {code}",
                "query": query,
            },
            ensure_ascii=False,
        )

    result = payload.get("Result")
    web_results = result.get("WebResults") if isinstance(result, dict) else None
    normalized = []
    for item in web_results if isinstance(web_results, list) else []:
        if not isinstance(item, dict):
            continue
        title = _text(item, "Title", "title")
        url = _text(item, "Url", "url")
        content = _text(item, "Summary", "Snippet", "Content", "summary", "snippet", "content")
        if title and url and content:
            normalized.append({"title": title, "url": url, "content": content})
        if len(normalized) >= count:
            break

    return json.dumps(
        {
            "query": query,
            "total_results": len(normalized),
            "results": normalized,
        },
        ensure_ascii=False,
    )
