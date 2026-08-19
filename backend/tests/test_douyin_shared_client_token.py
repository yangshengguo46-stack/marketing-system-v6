from __future__ import annotations

import pytest

from deerflow.community.douyin_openapi import client_token as client_token_module
from deerflow.community.douyin_openapi.client_token import (
    get_stable_client_token,
    invalidate_stable_client_token,
    request_stable_client_token,
    reset_stable_client_token_cache_for_tests,
)
from deerflow.community.douyin_openapi.official_mcp import DouyinClientTokenProvider
from deerflow.community.douyin_search import tools as search_tools


@pytest.fixture(autouse=True)
def _reset_token_caches() -> None:
    reset_stable_client_token_cache_for_tests()
    search_tools._reset_token_cache_for_tests()


@pytest.mark.asyncio
async def test_stable_client_token_is_shared_within_process_across_search_and_official_mcp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[tuple[str, str]] = []

    async def request_once(client_key: str, client_secret: str) -> tuple[str, int]:
        requests.append((client_key, client_secret))
        return "clt.shared-private-token", 7200

    async def unexpected_request(client_key: str, client_secret: str) -> tuple[str, int]:
        raise AssertionError(f"unexpected token refresh for {client_key}:{client_secret}")

    provider = DouyinClientTokenProvider(
        client_key="shared-client-key",
        client_secret="shared-client-secret",
        request_token=request_once,
    )
    assert await provider() == "clt.shared-private-token"

    monkeypatch.setattr(search_tools, "_request_stable_client_token", unexpected_request)
    assert await search_tools._get_client_token("shared-client-key", "shared-client-secret") == ("clt.shared-private-token")
    assert requests == [("shared-client-key", "shared-client-secret")]


@pytest.mark.asyncio
async def test_stable_client_token_request_uses_the_idempotent_official_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[dict[str, object]] = []

    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "data": {
                    "access_token": "clt.private-token",
                    "error_code": 0,
                    "expires_in": 7200,
                }
            }

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback) -> None:
            del exc_type, exc, traceback

        async def post(self, url: str, **kwargs):
            requests.append({"url": url, **kwargs})
            return Response()

    monkeypatch.setattr(client_token_module.httpx, "AsyncClient", lambda **kwargs: Client())

    token, expires_in = await request_stable_client_token(
        "client-key",
        "client-secret",
    )

    assert token == "clt.private-token"
    assert expires_in == 7200
    assert requests == [
        {
            "url": "https://open.douyin.com/oauth/stable_client_token/",
            "headers": {"content-type": "application/json"},
            "json": {
                "client_key": "client-key",
                "client_secret": "client-secret",
                "grant_type": "client_credential",
            },
        }
    ]


@pytest.mark.asyncio
async def test_stable_client_token_cache_isolates_test_and_production_credentials() -> None:
    requests: list[str] = []

    async def request_token(client_key: str, client_secret: str) -> tuple[str, int]:
        del client_secret
        requests.append(client_key)
        return f"clt.{client_key}", 7200

    production = await get_stable_client_token(
        "production-client-key",
        "production-client-secret",
        request_token=request_token,
    )
    test = await get_stable_client_token(
        "test-client-key",
        "test-client-secret",
        request_token=request_token,
    )

    assert production == "clt.production-client-key"
    assert test == "clt.test-client-key"
    assert requests == ["production-client-key", "test-client-key"]


@pytest.mark.asyncio
async def test_stable_client_token_refreshes_only_after_exact_token_invalidation() -> None:
    tokens = iter(("clt.first-private-token", "clt.second-private-token"))
    request_count = 0

    async def request_token(client_key: str, client_secret: str) -> tuple[str, int]:
        nonlocal request_count
        del client_key, client_secret
        request_count += 1
        return next(tokens), 7200

    first = await get_stable_client_token(
        "client-key",
        "client-secret",
        request_token=request_token,
    )
    await invalidate_stable_client_token("client-key", "client-secret", "clt.not-current")
    still_first = await get_stable_client_token(
        "client-key",
        "client-secret",
        request_token=request_token,
    )
    await invalidate_stable_client_token("client-key", "client-secret", first)
    second = await get_stable_client_token(
        "client-key",
        "client-secret",
        request_token=request_token,
    )

    assert first == still_first == "clt.first-private-token"
    assert second == "clt.second-private-token"
    assert request_count == 2
