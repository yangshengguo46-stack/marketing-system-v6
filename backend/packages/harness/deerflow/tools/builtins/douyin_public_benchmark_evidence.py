from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote

from langchain_core.messages import ToolMessage

from deerflow.incubation import (
    BenchmarkCoverageReceipt,
    BenchmarkPostObservation,
    BenchmarkProfileObservation,
    BenchmarkRouteReceipt,
    BenchmarkSnapshot,
)
from deerflow.tools.mcp_metadata import is_mcp_tool
from deerflow.tools.types import Runtime

logger = logging.getLogger(__name__)

_TOOL_NAME = "douyin_public_evidence"
_REQUIRED_CHILDREN = frozenset({"search_videos", "get_user_info", "get_user_posts"})


class _PublicEvidenceClient:
    def __init__(self, runtime: Runtime) -> None:
        self._runtime = runtime
        self._tool: Any | None = None
        self._manifest_version: str | None = None
        self._catalog_version: str | None = None
        self._call_sequence = 0
        self._manifest_lock = asyncio.Lock()

    @property
    def manifest_version(self) -> str | None:
        return self._manifest_version

    @property
    def catalog_version(self) -> str | None:
        return self._catalog_version

    async def discover(self) -> bool:
        async with self._manifest_lock:
            self._tool = _find_runtime_tool(self._runtime)
            if self._tool is None:
                return False
            manifest = await self._call_raw({})
            if not isinstance(manifest, dict) or manifest.get("domain") != "public_evidence":
                return False
            children = {item.get("name") for item in manifest.get("children", ()) if isinstance(item, dict) and item.get("callable") is True}
            version = _non_empty_text(manifest.get("manifest_version"))
            if version is None or not _REQUIRED_CHILDREN.issubset(children):
                return False
            self._manifest_version = version
            self._catalog_version = _non_empty_text(manifest.get("catalog_version"))
            return True

    async def call(self, child_tool: str, arguments: dict[str, Any]) -> dict[str, Any] | None:
        if self._manifest_version is None:
            return None
        payload = await self._call_raw(
            {
                "child_tool": child_tool,
                "arguments": arguments,
                "manifest_version": self._manifest_version,
            }
        )
        if not isinstance(payload, dict) or isinstance(payload.get("error"), dict):
            return None
        metadata = payload.get("metadata")
        data = payload.get("data")
        if not isinstance(metadata, dict) or not isinstance(data, dict):
            return None
        if metadata.get("domain") != "public_evidence" or metadata.get("child_tool") != child_tool:
            return None
        self._catalog_version = _non_empty_text(metadata.get("catalog_version")) or self._catalog_version
        return data

    async def _call_raw(self, arguments: dict[str, Any]) -> dict[str, Any] | None:
        if self._tool is None:
            return None
        self._call_sequence += 1
        result = await self._tool.ainvoke(
            {
                "name": self._tool.name,
                "args": {**arguments, "runtime": self._runtime},
                "id": f"{self._runtime.tool_call_id}:douyin-benchmark:{self._call_sequence}",
                "type": "tool_call",
            }
        )
        if not isinstance(result, ToolMessage) or not isinstance(result.artifact, dict):
            return None
        structured = result.artifact.get("structured_content")
        return structured if isinstance(structured, dict) else None


async def collect_public_douyin_benchmark(
    runtime: Runtime,
    *,
    query: str,
    max_posts: int = 6,
    clock: Callable[[], datetime] | None = None,
) -> BenchmarkSnapshot | None:
    """Collect one stable, author-consistent public Douyin account sample."""

    normalized_query = query.strip()[:200]
    requested_posts = max(2, min(int(max_posts), 12))
    if not normalized_query:
        return None

    client = _PublicEvidenceClient(runtime)
    try:
        if not await client.discover():
            return None
        search = await client.call(
            "search_videos",
            {"keyword": normalized_query, "count": 10},
        )
        selected_account_id = _select_account_id(search)
        if selected_account_id is None:
            return None
        profile_result, posts_result = await asyncio.gather(
            client.call("get_user_info", {"sec_user_id": selected_account_id}),
            client.call(
                "get_user_posts",
                {"sec_user_id": selected_account_id, "count": requested_posts},
            ),
        )
        return _build_snapshot(
            query=normalized_query,
            selected_account_id=selected_account_id,
            profile_result=profile_result,
            posts_result=posts_result,
            requested_posts=requested_posts,
            manifest_version=client.manifest_version,
            catalog_version=client.catalog_version,
            captured_at=(clock or (lambda: datetime.now(UTC)))(),
        )
    except Exception as exc:
        logger.warning(
            "Douyin public benchmark evidence was unavailable: %s",
            type(exc).__name__,
        )
        return None


def _select_account_id(search: dict[str, Any] | None) -> str | None:
    if not isinstance(search, dict) or search.get("success") is not True:
        return None
    grouped: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for order, item in enumerate(search.get("results", ())):
        if not isinstance(item, dict):
            continue
        author = item.get("author")
        if not isinstance(author, dict):
            continue
        account_id = _non_empty_text(author.get("sec_uid"))
        if account_id is None:
            continue
        grouped[account_id].append((order, _engagement_total(item.get("metrics"))))
    if not grouped:
        return None
    return min(
        grouped,
        key=lambda account_id: (
            -len(grouped[account_id]),
            -sum(engagement for _, engagement in grouped[account_id]),
            min(order for order, _ in grouped[account_id]),
            account_id,
        ),
    )


def _build_snapshot(
    *,
    query: str,
    selected_account_id: str,
    profile_result: dict[str, Any] | None,
    posts_result: dict[str, Any] | None,
    requested_posts: int,
    manifest_version: str | None,
    catalog_version: str | None,
    captured_at: datetime,
) -> BenchmarkSnapshot | None:
    if captured_at.tzinfo is None or captured_at.utcoffset() is None:
        captured_at = captured_at.replace(tzinfo=UTC)
    captured_at = captured_at.astimezone(UTC)
    if not _successful(profile_result) or not _successful(posts_result):
        return None
    profile_data = profile_result.get("user")
    if not isinstance(profile_data, dict):
        return None
    if _non_empty_text(profile_data.get("sec_uid")) != selected_account_id:
        return None
    if _non_empty_text(posts_result.get("account_sec_uid")) != selected_account_id:
        return None

    posts: list[BenchmarkPostObservation] = []
    excluded_count = 0
    seen_post_ids: set[str] = set()
    for item in posts_result.get("posts", ()):
        post = _post_observation(
            item,
            expected_account_id=selected_account_id,
            captured_at=captured_at,
        )
        if post is None or post.external_post_id in seen_post_ids:
            excluded_count += 1
            continue
        seen_post_ids.add(post.external_post_id)
        posts.append(post)
    if len(posts) < 2:
        return None

    pagination = posts_result.get("pagination")
    has_more = pagination.get("has_more") if isinstance(pagination, dict) else None
    receipt = posts_result.get("receipt")
    receipt_limitations = _string_tuple(receipt.get("limitations")) if isinstance(receipt, dict) else ()
    profile = BenchmarkProfileObservation(
        platform="douyin",
        external_account_id=selected_account_id,
        canonical_url=f"https://www.douyin.com/user/{quote(selected_account_id, safe='')}",
        display_name=_non_empty_text(profile_data.get("nickname")),
        bio=_non_empty_text(profile_data.get("description")),
        visible_post_count=_non_negative_int(profile_data.get("videos_count")),
        captured_at=captured_at,
        public_metrics=_numeric_metrics(
            profile_data,
            names=("following", "fans", "total_interactions"),
        ),
    )
    route_payload = {
        "query": query,
        "account_id": selected_account_id,
        "requested_posts": requested_posts,
        "returned_posts": len(posts),
    }
    return BenchmarkSnapshot(
        provider=(_non_empty_text(receipt.get("provider")) if isinstance(receipt, dict) else None) or "douyin_authenticated_public_web",
        collection_method="authenticated_public_search_then_account_posts",
        captured_at=captured_at,
        rights_basis="Locally authenticated observation of bounded public Douyin profile and post fields.",
        requested_url=f"https://www.douyin.com/search/{quote(query, safe='')}",
        profile=profile,
        posts=tuple(posts),
        coverage=BenchmarkCoverageReceipt(
            population_scope="public_posts_from_one_selected_creator",
            requested_count=requested_posts,
            returned_count=len(posts),
            excluded_count=excluded_count,
            has_more=has_more if isinstance(has_more, bool) else None,
            sample_basis="One stable creator identity selected from the bounded public search result, followed by its author-qualified public post list.",
            limitations=receipt_limitations,
        ),
        route_receipt=BenchmarkRouteReceipt(
            adapter="deerflow-capability-mcp",
            capability_version=(_non_empty_text(receipt.get("revision")) if isinstance(receipt, dict) else None) or "public-evidence-v1",
            route="public_evidence.search_videos->get_user_info+get_user_posts",
            manifest_version=manifest_version,
            catalog_version=catalog_version,
            request_receipt_sha256=hashlib.sha256(
                json.dumps(
                    route_payload,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest(),
        ),
        limitations=(
            "This is a bounded public account sample, not proof of audience composition, success cause, or copyability.",
            "Search ranking selected the candidate account; the account was not endorsed as the only or best benchmark.",
        ),
    )


def _post_observation(
    item: Any,
    *,
    expected_account_id: str,
    captured_at: datetime,
) -> BenchmarkPostObservation | None:
    if not isinstance(item, dict):
        return None
    author = item.get("author")
    if not isinstance(author, dict):
        return None
    if _non_empty_text(author.get("sec_uid")) != expected_account_id:
        return None
    post_id = _non_empty_text(item.get("aweme_id"))
    if post_id is None:
        return None
    published_at = _parse_timestamp(item.get("created_at"))
    if published_at is not None and published_at > captured_at:
        published_at = None
    caption_parts = tuple(
        value
        for value in (
            _non_empty_text(item.get("title")),
            _non_empty_text(item.get("description")),
        )
        if value is not None
    )
    return BenchmarkPostObservation(
        platform="douyin",
        external_post_id=post_id,
        author_external_account_id=expected_account_id,
        canonical_url=f"https://www.douyin.com/video/{quote(post_id, safe='')}",
        caption="\n".join(dict.fromkeys(caption_parts))[:4000] or None,
        published_at=published_at,
        captured_at=captured_at,
        public_metrics=_numeric_metrics(
            item.get("metrics"),
            names=("likes", "comments", "shares", "collections", "plays"),
        ),
    )


def _find_runtime_tool(runtime: Runtime) -> Any | None:
    for candidate in runtime.tools or ():
        if getattr(candidate, "name", None) == _TOOL_NAME and is_mcp_tool(candidate):
            return candidate
    from deerflow.mcp.cache import get_cached_mcp_tools

    return next(
        (candidate for candidate in get_cached_mcp_tools() if candidate.name == _TOOL_NAME and is_mcp_tool(candidate)),
        None,
    )


def _successful(value: Any) -> bool:
    return isinstance(value, dict) and value.get("success") is True


def _non_empty_text(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


def _non_negative_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        return None
    return int(value)


def _numeric_metrics(value: Any, *, names: tuple[str, ...]) -> dict[str, int | float]:
    if not isinstance(value, dict):
        return {}
    return {name: metric for name in names if isinstance((metric := value.get(name)), (int, float)) and not isinstance(metric, bool) and metric >= 0}


def _engagement_total(value: Any) -> int:
    return int(sum(_numeric_metrics(value, names=("likes", "comments", "shares", "collections")).values()))


def _parse_timestamp(value: Any) -> datetime | None:
    text = _non_empty_text(value)
    if text is None:
        return None
    try:
        return datetime.fromtimestamp(float(text), tz=UTC)
    except (OverflowError, ValueError):
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return None
        return parsed.astimezone(UTC)


def _string_tuple(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(item.strip() for item in value if isinstance(item, str) and item.strip())


__all__ = ["collect_public_douyin_benchmark"]
