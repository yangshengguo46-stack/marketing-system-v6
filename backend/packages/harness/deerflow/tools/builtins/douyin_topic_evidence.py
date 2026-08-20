from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote

from langchain_core.messages import ToolMessage

from deerflow.content_intelligence import ResearchSearchResult
from deerflow.incubation import EvidenceCoverageReceipt, EvidenceItem, EvidenceSnapshot
from deerflow.tools.mcp_metadata import is_mcp_tool
from deerflow.tools.types import Runtime

logger = logging.getLogger(__name__)

_TOOL_NAME = "douyin_public_evidence"
_DOMAIN = "public_evidence"
_CHILD_TOOL = "search_videos"


class DouyinMcpTopicEvidenceSearch:
    """Use the configured Douyin domain MCP as one bounded research provider."""

    def __init__(
        self,
        runtime: Runtime,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._runtime = runtime
        self._clock = clock or (lambda: datetime.now(UTC))
        self._manifest_lock = asyncio.Lock()
        self._manifest_discovered = False
        self._manifest_version: str | None = None
        self._tool: Any | None = None
        self._call_sequence = 0
        self._snapshots: list[EvidenceSnapshot] = []

    @property
    def snapshots(self) -> tuple[EvidenceSnapshot, ...]:
        return tuple(self._snapshots)

    async def __call__(
        self,
        query: str,
        max_results: int,
    ) -> tuple[ResearchSearchResult, ...]:
        try:
            await self._discover()
            if self._tool is None or self._manifest_version is None:
                return ()
            domain_result = await self._call(
                {
                    "child_tool": _CHILD_TOOL,
                    "arguments": {
                        "keyword": query,
                        "count": max(1, min(int(max_results), 20)),
                    },
                    "manifest_version": self._manifest_version,
                }
            )
            if _error_code(domain_result) == "stale_manifest":
                self._manifest_discovered = False
                self._manifest_version = None
                await self._discover()
                if self._manifest_version is None:
                    return ()
                domain_result = await self._call(
                    {
                        "child_tool": _CHILD_TOOL,
                        "arguments": {
                            "keyword": query,
                            "count": max(1, min(int(max_results), 20)),
                        },
                        "manifest_version": self._manifest_version,
                    }
                )
            if not isinstance(domain_result, dict) or "error" in domain_result:
                return ()
            snapshot = _build_topic_snapshot(
                domain_result,
                requested_count=max(1, min(int(max_results), 20)),
                captured_at=self._clock(),
            )
            if snapshot is None:
                return ()
        except Exception as exc:
            logger.warning(
                "Douyin MCP topic evidence was unavailable: %s",
                type(exc).__name__,
            )
            return ()

        self._snapshots.append(snapshot)
        return tuple(
            ResearchSearchResult(
                title=item.title,
                url=item.public_uri or "",
                content=item.excerpt,
            )
            for item in snapshot.items
            if item.public_uri is not None
        )

    async def _discover(self) -> None:
        if self._manifest_discovered:
            return
        async with self._manifest_lock:
            if self._manifest_discovered:
                return
            self._tool = _find_runtime_douyin_search_tool(self._runtime)
            if self._tool is None:
                return
            manifest = await self._call({})
            if not isinstance(manifest, dict) or manifest.get("domain") != _DOMAIN:
                return
            self._manifest_discovered = True
            child = next(
                (item for item in manifest.get("children", ()) if isinstance(item, dict) and item.get("name") == _CHILD_TOOL),
                None,
            )
            version = manifest.get("manifest_version")
            if child is None or child.get("callable") is not True:
                return
            if not isinstance(version, str) or not version:
                return
            self._manifest_version = version

    async def _call(self, arguments: dict[str, Any]) -> dict[str, Any] | None:
        if self._tool is None:
            return None
        self._call_sequence += 1
        call_id = f"{self._runtime.tool_call_id}:douyin-topic:{self._call_sequence}"
        result = await self._tool.ainvoke(
            {
                "name": self._tool.name,
                "args": {
                    **arguments,
                    "runtime": self._runtime,
                },
                "id": call_id,
                "type": "tool_call",
            }
        )
        if not isinstance(result, ToolMessage):
            return None
        artifact = result.artifact
        if not isinstance(artifact, dict):
            return None
        structured = artifact.get("structured_content")
        return structured if isinstance(structured, dict) else None


def _find_runtime_douyin_search_tool(runtime: Runtime) -> Any | None:
    for candidate in runtime.tools or ():
        if getattr(candidate, "name", None) == _TOOL_NAME and is_mcp_tool(candidate):
            return candidate

    from deerflow.mcp.cache import get_cached_mcp_tools

    return next(
        (candidate for candidate in get_cached_mcp_tools() if candidate.name == _TOOL_NAME and is_mcp_tool(candidate)),
        None,
    )


def _build_topic_snapshot(
    domain_result: dict[str, Any],
    *,
    requested_count: int,
    captured_at: datetime,
) -> EvidenceSnapshot | None:
    metadata = domain_result.get("metadata")
    data = domain_result.get("data")
    if not isinstance(metadata, dict) or not isinstance(data, dict):
        return None
    if metadata.get("domain") != _DOMAIN or metadata.get("child_tool") != _CHILD_TOOL:
        return None
    if data.get("success") is not True:
        return None

    items: list[EvidenceItem] = []
    seen_ids: set[str] = set()
    for raw in data.get("results", ()):
        if not isinstance(raw, dict):
            continue
        item_id = _non_empty_text(raw.get("aweme_id"))
        if item_id is None or item_id in seen_ids:
            continue
        title = _non_empty_text(raw.get("title")) or _non_empty_text(raw.get("description"))
        excerpt = _non_empty_text(raw.get("description")) or title
        if title is None or excerpt is None:
            continue
        author = raw.get("author")
        metrics = raw.get("metrics")
        observed_values = {name: value for name in ("likes", "comments", "shares", "collections", "plays") if (value := _non_negative_int(metrics.get(name) if isinstance(metrics, dict) else None)) is not None}
        seen_ids.add(item_id)
        items.append(
            EvidenceItem(
                source_ref=f"douyin:video:{item_id}",
                source_type="douyin_video",
                title=title[:500],
                excerpt=excerpt[:4000],
                provenance="observed",
                public_uri=f"https://www.douyin.com/video/{quote(item_id, safe='')}",
                actor_label=(_non_empty_text(author.get("nickname")) if isinstance(author, dict) else None),
                observed_values=observed_values,
            )
        )

    if not items:
        return None
    receipt = data.get("receipt")
    receipt = receipt if isinstance(receipt, dict) else {}
    limitations = _string_tuple(receipt.get("limitations"))
    return EvidenceSnapshot(
        provider=_non_empty_text(receipt.get("provider")) or "douyin_authenticated_public_web",
        collection_method="authenticated_public_search",
        evidence_role="topic_evidence",
        captured_at=captured_at,
        rights_basis="Locally authenticated observation of bounded public Douyin search fields.",
        query=_non_empty_text(data.get("query")),
        items=tuple(items),
        coverage=EvidenceCoverageReceipt(
            population_scope="public_video_search_results",
            requested_count=requested_count,
            returned_count=len(items),
            has_more=data.get("has_more") if isinstance(data.get("has_more"), bool) else None,
            cursor=data.get("cursor") if isinstance(data.get("cursor"), (int, str)) else None,
            limitations=limitations or ("Search ranking and visible fields are bounded by the local public-evidence child.",),
        ),
        route_receipt={
            "domain": _DOMAIN,
            "child_tool": _CHILD_TOOL,
            "manifest_version": _non_empty_text(metadata.get("manifest_version")) or "unknown",
            "catalog_version": _non_empty_text(metadata.get("catalog_version")) or "unknown",
            "capability_revision": _non_empty_text(receipt.get("revision")) or "unknown",
        },
        warnings=_string_tuple(domain_result.get("warnings")),
        limitations=(
            "This snapshot is bounded topic evidence, not a benchmark-account analysis.",
            "A search result cannot establish account positioning, audience, success cause, or copyability.",
            *(limitations or ("The collector exposed no additional source limitation.",)),
        ),
    )


def _non_empty_text(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


def _non_negative_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value >= 0:
        return value
    return None


def _string_tuple(value: Any) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(text for item in value if (text := _non_empty_text(item)) is not None)


def _error_code(payload: dict[str, Any] | None) -> str | None:
    if not isinstance(payload, dict):
        return None
    error = payload.get("error")
    if not isinstance(error, dict):
        return None
    code = error.get("code")
    return code if isinstance(code, str) else None


__all__ = ["DouyinMcpTopicEvidenceSearch"]
