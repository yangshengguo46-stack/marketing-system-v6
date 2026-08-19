from __future__ import annotations

import asyncio
import hashlib
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import httpx

_STABLE_CLIENT_TOKEN_URL = "https://open.douyin.com/oauth/stable_client_token/"
_TOKEN_REFRESH_SKEW_SECONDS = 60

TokenRequester = Callable[[str, str], Awaitable[tuple[str, int]]]


class DouyinClientTokenError(RuntimeError):
    """A credential-safe failure while obtaining an application token."""


@dataclass(frozen=True)
class _TokenEntry:
    access_token: str
    expires_at: float


_token_cache: dict[str, _TokenEntry] = {}
_token_lock = asyncio.Lock()


def _credential_fingerprint(client_key: str, client_secret: str) -> str:
    return hashlib.sha256(f"{client_key}\0{client_secret}".encode()).hexdigest()


def _validated_credentials(client_key: str, client_secret: str) -> tuple[str, str]:
    normalized_key = client_key.strip()
    normalized_secret = client_secret.strip()
    if not normalized_key or not normalized_secret:
        raise ValueError("DOUYIN_CLIENT_KEY and DOUYIN_CLIENT_SECRET are required")
    return normalized_key, normalized_secret


def _positive_int(value: object) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return 0
    return number if number > 0 else 0


async def request_stable_client_token(
    client_key: str,
    client_secret: str,
) -> tuple[str, int]:
    """Request Douyin's idempotent application token without exposing credentials."""

    client_key, client_secret = _validated_credentials(client_key, client_secret)
    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0), trust_env=True) as client:
        response = await client.post(
            _STABLE_CLIENT_TOKEN_URL,
            headers={"content-type": "application/json"},
            json={
                "client_key": client_key,
                "client_secret": client_secret,
                "grant_type": "client_credential",
            },
        )
        response.raise_for_status()
        payload = response.json()

    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        raise DouyinClientTokenError("Douyin stable client token response was invalid")
    try:
        error_code = int(data.get("error_code", -1))
    except (TypeError, ValueError) as exc:
        raise DouyinClientTokenError("Douyin stable client token response was invalid") from exc
    access_token = data.get("access_token")
    expires_in = _positive_int(data.get("expires_in"))
    if error_code != 0 or not isinstance(access_token, str) or not access_token.strip() or expires_in == 0:
        raise DouyinClientTokenError(f"Douyin stable client token request failed with provider code {error_code}")
    return access_token.strip(), expires_in


async def get_stable_client_token(
    client_key: str,
    client_secret: str,
    *,
    request_token: TokenRequester | None = None,
) -> str:
    """Return one process-wide stable token shared by all Douyin app clients."""

    client_key, client_secret = _validated_credentials(client_key, client_secret)
    cache_key = _credential_fingerprint(client_key, client_secret)
    now = time.monotonic()
    cached = _token_cache.get(cache_key)
    if cached is not None and cached.expires_at - _TOKEN_REFRESH_SKEW_SECONDS > now:
        return cached.access_token

    requester = request_token or request_stable_client_token
    async with _token_lock:
        now = time.monotonic()
        cached = _token_cache.get(cache_key)
        if cached is not None and cached.expires_at - _TOKEN_REFRESH_SKEW_SECONDS > now:
            return cached.access_token
        access_token, expires_in = await requester(client_key, client_secret)
        if not access_token.strip() or expires_in <= 0:
            raise DouyinClientTokenError("Douyin stable client token response was invalid")
        _token_cache[cache_key] = _TokenEntry(
            access_token=access_token.strip(),
            expires_at=now + expires_in,
        )
        return access_token.strip()


async def invalidate_stable_client_token(
    client_key: str,
    client_secret: str,
    access_token: str,
) -> None:
    """Invalidate only the failed token so a stale response cannot evict a newer one."""

    client_key, client_secret = _validated_credentials(client_key, client_secret)
    cache_key = _credential_fingerprint(client_key, client_secret)
    async with _token_lock:
        cached = _token_cache.get(cache_key)
        if cached is not None and cached.access_token == access_token:
            _token_cache.pop(cache_key, None)


def reset_stable_client_token_cache_for_tests() -> None:
    _token_cache.clear()
