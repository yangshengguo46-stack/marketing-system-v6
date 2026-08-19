from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

import pytest
from mcp.types import CallToolResult, ListToolsResult, TextContent, Tool, ToolAnnotations

from deerflow.community.douyin_openapi.official_mcp import (
    DouyinClientTokenProvider,
    DouyinOfficialMCPProxy,
    DouyinOfficialMCPToolApprovalRequired,
    build_official_sse_url,
    parse_tool_group_aids,
)


def _tool(
    name: str,
    *,
    read_only: bool | None = True,
    destructive: bool | None = False,
) -> Tool:
    return Tool(
        name=name,
        description=f"Official tool {name}",
        inputSchema={"type": "object", "properties": {"query": {"type": "string"}}},
        annotations=ToolAnnotations(
            readOnlyHint=read_only,
            destructiveHint=destructive,
        ),
    )


class _RemoteSession:
    def __init__(self, pages: dict[str | None, ListToolsResult]) -> None:
        self.pages = pages
        self.initialized = 0
        self.list_cursors: list[str | None] = []
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def initialize(self) -> object:
        self.initialized += 1
        return object()

    async def list_tools(self, cursor: str | None = None) -> ListToolsResult:
        self.list_cursors.append(cursor)
        return self.pages[cursor]

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> CallToolResult:
        self.calls.append((name, arguments))
        return CallToolResult(content=[TextContent(type="text", text="ok")], isError=False)


def test_parse_tool_group_aids_normalizes_and_rejects_unsafe_values() -> None:
    assert parse_tool_group_aids("search-aid, content.aid,search-aid") == ("search-aid", "content.aid")
    assert parse_tool_group_aids("") == ()

    with pytest.raises(ValueError, match="invalid"):
        parse_tool_group_aids("safe,contains space")


def test_build_official_sse_url_uses_query_token_and_optional_groups() -> None:
    url = build_official_sse_url(
        "client-token-value",
        tool_group_aids=("search-aid", "content-aid"),
    )

    assert url.startswith("https://open.douyin.com/sse?")
    assert "token=client-token-value" in url
    assert "tool_group_aid=search-aid%2Ccontent-aid" in url


@pytest.mark.asyncio
async def test_client_token_provider_caches_token_until_refresh_window() -> None:
    requests: list[tuple[str, str]] = []

    async def request_token(client_key: str, client_secret: str) -> tuple[str, int]:
        requests.append((client_key, client_secret))
        return "private-client-token", 7200

    provider = DouyinClientTokenProvider(
        client_key="client-key",
        client_secret="client-secret",
        request_token=request_token,
    )

    assert await provider() == "private-client-token"
    assert await provider() == "private-client-token"
    assert requests == [("client-key", "client-secret")]


@pytest.mark.asyncio
async def test_proxy_lists_all_remote_pages_without_exposing_token() -> None:
    session = _RemoteSession(
        {
            None: ListToolsResult(tools=[_tool("video_search")], nextCursor="next"),
            "next": ListToolsResult(tools=[_tool("image_text_search")]),
        }
    )
    seen_urls: list[str] = []

    @asynccontextmanager
    async def session_factory(url: str):
        seen_urls.append(url)
        yield session

    proxy = DouyinOfficialMCPProxy(
        token_provider=lambda: _async_value("private-client-token"),
        session_factory=session_factory,
    )

    tools = await proxy.list_tools()

    assert [tool.name for tool in tools] == ["video_search", "image_text_search"]
    assert session.initialized == 1
    assert session.list_cursors == [None, "next"]
    assert len(seen_urls) == 1
    assert "private-client-token" in seen_urls[0]
    assert "private-client-token" not in repr(tools)


@pytest.mark.asyncio
async def test_proxy_calls_exact_read_only_remote_tool() -> None:
    session = _RemoteSession({None: ListToolsResult(tools=[_tool("video_search")])})

    @asynccontextmanager
    async def session_factory(url: str):
        assert url.startswith("https://open.douyin.com/sse?")
        yield session

    proxy = DouyinOfficialMCPProxy(
        token_provider=lambda: _async_value("private-client-token"),
        session_factory=session_factory,
    )

    result = await proxy.call_tool("video_search", {"query": "火锅"})

    assert result.isError is False
    assert session.calls == [("video_search", {"query": "火锅"})]


@pytest.mark.asyncio
async def test_proxy_blocks_explicit_write_tool_without_local_approval() -> None:
    session = _RemoteSession({None: ListToolsResult(tools=[_tool("create_business_task", read_only=False, destructive=True)])})

    @asynccontextmanager
    async def session_factory(url: str):
        del url
        yield session

    proxy = DouyinOfficialMCPProxy(
        token_provider=lambda: _async_value("private-client-token"),
        session_factory=session_factory,
    )

    with pytest.raises(DouyinOfficialMCPToolApprovalRequired):
        await proxy.call_tool("create_business_task", {})

    assert session.calls == []


@pytest.mark.asyncio
async def test_proxy_blocks_tool_without_read_only_metadata_until_reviewed() -> None:
    session = _RemoteSession({None: ListToolsResult(tools=[_tool("provider_tool_without_hints", read_only=None, destructive=None)])})

    @asynccontextmanager
    async def session_factory(url: str):
        del url
        yield session

    proxy = DouyinOfficialMCPProxy(
        token_provider=lambda: _async_value("private-client-token"),
        session_factory=session_factory,
    )

    with pytest.raises(DouyinOfficialMCPToolApprovalRequired):
        await proxy.call_tool("provider_tool_without_hints", {})


async def _async_value(value: str) -> str:
    return value
