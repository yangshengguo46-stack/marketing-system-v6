from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from langchain_core.messages import ToolMessage

from deerflow.community.douyin_openapi.evidence import build_video_search_evidence_snapshot
from deerflow.content_intelligence import ResearchSearchResult
from deerflow.incubation import EvidenceSnapshot
from deerflow.tools.mcp_metadata import is_mcp_tool
from deerflow.tools.types import Runtime

logger = logging.getLogger(__name__)


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
                    "child_tool": "video_search",
                    "arguments": {
                        "query": query,
                        "purpose": "topic_research",
                        "max_results": max(1, min(int(max_results), 20)),
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
                        "child_tool": "video_search",
                        "arguments": {
                            "query": query,
                            "purpose": "topic_research",
                            "max_results": max(1, min(int(max_results), 20)),
                        },
                        "manifest_version": self._manifest_version,
                    }
                )
            if not isinstance(domain_result, dict) or "error" in domain_result:
                return ()
            snapshot = build_video_search_evidence_snapshot(
                domain_result,
                requested_count=max(1, min(int(max_results), 20)),
                captured_at=self._clock(),
            )
            if snapshot.evidence_role != "topic_evidence":
                logger.warning("Douyin content research rejected a non-topic evidence role")
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
            if not isinstance(manifest, dict) or manifest.get("domain") != "search":
                return
            self._manifest_discovered = True
            child = next(
                (item for item in manifest.get("children", ()) if isinstance(item, dict) and item.get("name") == "video_search"),
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
        if getattr(candidate, "name", None) == "douyin_search" and is_mcp_tool(candidate):
            return candidate

    from deerflow.mcp.cache import get_cached_mcp_tools

    return next(
        (candidate for candidate in get_cached_mcp_tools() if candidate.name == "douyin_search" and is_mcp_tool(candidate)),
        None,
    )


def _error_code(payload: dict[str, Any] | None) -> str | None:
    if not isinstance(payload, dict):
        return None
    error = payload.get("error")
    if not isinstance(error, dict):
        return None
    code = error.get("code")
    return code if isinstance(code, str) else None


__all__ = ["DouyinMcpTopicEvidenceSearch"]
