from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

from mcp.types import TextContent

from deerflow.mcp.session_pool import MCPSessionPool

PUBLIC_EVIDENCE_AUTH_MODE = "authenticated_public_web"
PUBLIC_EVIDENCE_ROOT_ENV = "DOUYIN_PUBLIC_EVIDENCE_ROOT"
PUBLIC_EVIDENCE_UV_ENV = "DOUYIN_PUBLIC_EVIDENCE_UV"

_MAX_CHILD_RESULT_BYTES = 64 * 1024
_ALLOWED_CHILDREN = frozenset(
    {
        "search_videos",
        "get_video_detail",
        "get_video_comments",
        "get_sub_comments",
        "get_user_info",
        "get_user_posts",
        "resolve_share_url",
    }
)


class PublicEvidenceUnavailable(RuntimeError):
    """A credential-safe failure from the authenticated public-web runtime."""


class PublicEvidenceRuntime:
    async def call(
        self,
        child_tool: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        raise NotImplementedError


def _resolved_runtime_settings() -> tuple[Path, str] | None:
    configured_root = os.getenv(PUBLIC_EVIDENCE_ROOT_ENV, "").strip()
    if not configured_root:
        return None
    root = Path(configured_root).expanduser().resolve()
    server_path = root / "readonly_server.py"
    configured_uv = os.getenv(PUBLIC_EVIDENCE_UV_ENV, "").strip()
    uv = configured_uv or shutil.which("uv") or ""
    if not root.is_dir() or not server_path.is_file() or not uv:
        return None
    return root, uv


def public_evidence_runtime_is_configured() -> bool:
    return _resolved_runtime_settings() is not None


def _decode_child_result(result: object) -> dict[str, Any]:
    if bool(getattr(result, "isError", False)):
        raise PublicEvidenceUnavailable("The public-evidence child returned an error")

    structured = getattr(result, "structuredContent", None)
    if isinstance(structured, dict):
        payload: object = structured
    else:
        text_blocks = [item.text for item in getattr(result, "content", ()) if isinstance(item, TextContent)]
        if len(text_blocks) != 1:
            raise PublicEvidenceUnavailable("The public-evidence child returned an unsupported result")
        encoded = text_blocks[0].encode("utf-8")
        if len(encoded) > _MAX_CHILD_RESULT_BYTES:
            raise PublicEvidenceUnavailable("The public-evidence child exceeded its result budget")
        try:
            payload = json.loads(text_blocks[0])
        except json.JSONDecodeError as exc:
            raise PublicEvidenceUnavailable("The public-evidence child returned invalid JSON") from exc

    if not isinstance(payload, dict):
        raise PublicEvidenceUnavailable("The public-evidence child returned an invalid object")
    if (
        len(
            json.dumps(
                payload,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
        )
        > _MAX_CHILD_RESULT_BYTES
    ):
        raise PublicEvidenceUnavailable("The public-evidence child exceeded its result budget")
    return payload


class StdioPublicEvidenceRuntime(PublicEvidenceRuntime):
    """Run a reviewed child MCP behind the single domain gateway."""

    _SERVER_NAME = "douyin-public-evidence-child"
    _SCOPE_KEY = "gateway-process"

    def __init__(
        self,
        *,
        root: Path,
        uv: str,
        session_pool: MCPSessionPool | None = None,
    ) -> None:
        self._root = root
        self._uv = uv
        self._session_pool = session_pool or MCPSessionPool()
        self._connection = {
            "transport": "stdio",
            "command": self._uv,
            "args": [
                "--directory",
                str(self._root),
                "run",
                "readonly_server.py",
            ],
        }

    @classmethod
    def from_environment(cls) -> StdioPublicEvidenceRuntime:
        settings = _resolved_runtime_settings()
        if settings is None:
            raise PublicEvidenceUnavailable("The authenticated public-evidence runtime is not configured")
        root, uv = settings
        return cls(root=root, uv=uv)

    async def call(
        self,
        child_tool: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        if child_tool not in _ALLOWED_CHILDREN:
            raise PublicEvidenceUnavailable("The requested public-evidence child is not reviewed")
        try:
            session = await self._session_pool.get_session(
                self._SERVER_NAME,
                self._SCOPE_KEY,
                self._connection,
            )
            result = await session.call_tool(child_tool, arguments)
            return _decode_child_result(result)
        except PublicEvidenceUnavailable:
            raise
        except Exception:
            await self._session_pool.close_server(self._SERVER_NAME)
            raise PublicEvidenceUnavailable("The authenticated public-evidence runtime failed") from None

    async def close(self) -> None:
        await self._session_pool.close_server(self._SERVER_NAME)


__all__ = [
    "PUBLIC_EVIDENCE_AUTH_MODE",
    "PUBLIC_EVIDENCE_ROOT_ENV",
    "PUBLIC_EVIDENCE_UV_ENV",
    "PublicEvidenceRuntime",
    "PublicEvidenceUnavailable",
    "StdioPublicEvidenceRuntime",
    "public_evidence_runtime_is_configured",
]
