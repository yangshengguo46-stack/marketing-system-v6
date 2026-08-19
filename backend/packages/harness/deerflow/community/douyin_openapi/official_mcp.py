from __future__ import annotations

import asyncio
import os
import re
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Any, Protocol
from urllib.parse import urlencode

from mcp import ClientSession
from mcp.client.sse import sse_client
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import CallToolResult, Tool

from deerflow.community.douyin_openapi.client_token import (
    TokenRequester,
    get_stable_client_token,
    request_stable_client_token,
)

_OFFICIAL_SSE_ENDPOINT = "https://open.douyin.com/sse"
_MAX_TOOL_PAGES = 20
_MAX_TOOLS = 256
_TOOL_GROUP_AID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


class _RemoteSession(Protocol):
    async def initialize(self) -> object: ...

    async def list_tools(self, cursor: str | None = None) -> Any: ...

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> CallToolResult: ...


TokenProvider = Callable[[], Awaitable[str]]
SessionFactory = Callable[[str], AbstractAsyncContextManager[_RemoteSession]]


class DouyinOfficialMCPError(RuntimeError):
    """A credential-safe failure from the official Douyin MCP bridge."""


class DouyinOfficialMCPToolApprovalRequired(DouyinOfficialMCPError):
    """Raised when provider metadata explicitly marks a tool as mutating."""


def parse_tool_group_aids(value: str | Sequence[str] | None) -> tuple[str, ...]:
    if value is None:
        return ()
    raw_values = value.split(",") if isinstance(value, str) else value
    normalized: list[str] = []
    for raw in raw_values:
        aid = str(raw).strip()
        if not aid:
            continue
        if not _TOOL_GROUP_AID.fullmatch(aid):
            raise ValueError("Douyin MCP tool_group_aid contains an invalid value")
        if aid not in normalized:
            normalized.append(aid)
    return tuple(normalized)


def build_official_sse_url(
    token: str,
    *,
    tool_group_aids: Sequence[str] = (),
) -> str:
    token = token.strip()
    if not token:
        raise ValueError("Douyin MCP token is empty")
    query: dict[str, str] = {"token": token}
    groups = parse_tool_group_aids(tool_group_aids)
    if groups:
        query["tool_group_aid"] = ",".join(groups)
    return f"{_OFFICIAL_SSE_ENDPOINT}?{urlencode(query)}"


_request_client_token = request_stable_client_token


class DouyinClientTokenProvider:
    """Read the process-wide stable application token used by official MCP."""

    def __init__(
        self,
        *,
        client_key: str,
        client_secret: str,
        request_token: TokenRequester = _request_client_token,
    ) -> None:
        if not client_key.strip() or not client_secret.strip():
            raise ValueError("DOUYIN_CLIENT_KEY and DOUYIN_CLIENT_SECRET are required")
        self._client_key = client_key.strip()
        self._client_secret = client_secret.strip()
        self._request_token = request_token

    async def __call__(self) -> str:
        return await get_stable_client_token(
            self._client_key,
            self._client_secret,
            request_token=self._request_token,
        )


@asynccontextmanager
async def _default_session_factory(url: str) -> AsyncIterator[ClientSession]:
    async with sse_client(url, timeout=20, sse_read_timeout=300) as (read, write):
        async with ClientSession(read, write) as session:
            yield session


def _requires_local_approval(tool: Tool) -> bool:
    annotations = tool.annotations
    return bool(annotations is None or annotations.readOnlyHint is not True or annotations.destructiveHint is True)


class DouyinOfficialMCPProxy:
    """Turn Douyin's token-in-query remote SSE service into a local MCP source."""

    def __init__(
        self,
        *,
        token_provider: TokenProvider,
        session_factory: SessionFactory = _default_session_factory,
        tool_group_aids: Sequence[str] = (),
    ) -> None:
        self._token_provider = token_provider
        self._session_factory = session_factory
        self._tool_group_aids = parse_tool_group_aids(tool_group_aids)

    @classmethod
    def from_environment(cls) -> DouyinOfficialMCPProxy:
        token_provider = DouyinClientTokenProvider(
            client_key=os.getenv("DOUYIN_CLIENT_KEY", ""),
            client_secret=os.getenv("DOUYIN_CLIENT_SECRET", ""),
        )
        return cls(
            token_provider=token_provider,
            tool_group_aids=parse_tool_group_aids(os.getenv("DOUYIN_MCP_TOOL_GROUP_AIDS", "")),
        )

    @asynccontextmanager
    async def _session(self) -> AsyncIterator[_RemoteSession]:
        try:
            token = await self._token_provider()
            url = build_official_sse_url(token, tool_group_aids=self._tool_group_aids)
            async with self._session_factory(url) as session:
                await session.initialize()
                yield session
        except DouyinOfficialMCPError:
            raise
        except Exception:
            raise DouyinOfficialMCPError("Douyin official MCP connection failed") from None

    async def _list_session_tools(self, session: _RemoteSession) -> list[Tool]:
        tools: list[Tool] = []
        cursor: str | None = None
        seen_cursors: set[str] = set()
        for _ in range(_MAX_TOOL_PAGES):
            result = await session.list_tools(cursor=cursor)
            page_tools = list(result.tools)
            tools.extend(page_tools)
            if len(tools) > _MAX_TOOLS:
                raise DouyinOfficialMCPError("Douyin official MCP returned too many tools")
            next_cursor = getattr(result, "nextCursor", None)
            if not next_cursor:
                return tools
            if next_cursor in seen_cursors:
                raise DouyinOfficialMCPError("Douyin official MCP tool pagination repeated a cursor")
            seen_cursors.add(next_cursor)
            cursor = next_cursor
        raise DouyinOfficialMCPError("Douyin official MCP tool pagination exceeded its limit")

    async def list_tools(self) -> list[Tool]:
        async with self._session() as session:
            return await self._list_session_tools(session)

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> CallToolResult:
        async with self._session() as session:
            tools = await self._list_session_tools(session)
            matching = [tool for tool in tools if tool.name == name]
            if len(matching) != 1:
                raise DouyinOfficialMCPError("Douyin official MCP tool is unavailable or ambiguous")
            tool = matching[0]
            if _requires_local_approval(tool):
                raise DouyinOfficialMCPToolApprovalRequired("Douyin official MCP tool is not verified read-only; use a reviewed domain adapter with business approval")
            return await session.call_tool(name, arguments)


def build_official_proxy_server(
    proxy: DouyinOfficialMCPProxy | None = None,
) -> Server[Any]:
    resolved_proxy = proxy or DouyinOfficialMCPProxy.from_environment()
    server: Server[Any] = Server(
        "Douyin official MCP bridge",
        instructions=("Tools are discovered live from the official Douyin MCP service marketplace. Only tools explicitly marked read-only by the provider are callable through this generic bridge."),
    )

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return await resolved_proxy.list_tools()

    @server.call_tool(validate_input=True)
    async def call_tool(name: str, arguments: dict[str, Any]) -> CallToolResult:
        return await resolved_proxy.call_tool(name, arguments)

    return server


async def _run_stdio_server() -> None:
    server = build_official_proxy_server()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


def main() -> None:
    asyncio.run(_run_stdio_server())


if __name__ == "__main__":
    main()
