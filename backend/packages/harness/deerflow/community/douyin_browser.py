from __future__ import annotations

import asyncio
import html
import json
import os
import re
import unicodedata
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Protocol
from urllib.parse import quote, unquote, urlsplit

from pydantic import Field, field_validator

from deerflow.incubation.benchmark import (
    BenchmarkCoverageReceipt,
    BenchmarkPostObservation,
    BenchmarkProfileObservation,
    BenchmarkRouteReceipt,
    BenchmarkSnapshot,
)
from deerflow.incubation.contracts import IncubationContract, NonEmptyStr
from deerflow.incubation.evidence import (
    EvidenceCoverageReceipt,
    EvidenceItem,
    EvidenceSnapshot,
)

_DOUYIN_HOSTS = ("douyin.com", "iesdouyin.com")
_MAX_STORAGE_STATE_BYTES = 2_000_000
_MAX_RESPONSE_PAYLOADS = 24


class DouyinBrowserUnavailable(RuntimeError):
    """A stable browser-collection failure that contains no local credentials."""


class BrowserTarget(StrEnum):
    CONTENT = "content"
    ACCOUNT_POSTS = "account_posts"


class BrowserPageState(StrEnum):
    READY = "ready"
    NEEDS_LOGIN = "needs_login"
    RESTRICTED = "restricted"


@dataclass(frozen=True, slots=True)
class BrowserCapture:
    captured_at: datetime
    final_url: str
    page_state: BrowserPageState
    response_payloads: tuple[object, ...] = ()

    def __post_init__(self) -> None:
        if self.captured_at.tzinfo is None or self.captured_at.utcoffset() is None:
            raise ValueError("captured_at must be timezone-aware")
        _clean_douyin_url(self.final_url)
        if len(self.response_payloads) > _MAX_RESPONSE_PAYLOADS:
            raise ValueError("too many browser response payloads")


class BrowserRunner(Protocol):
    async def capture(
        self,
        *,
        url: str,
        target: BrowserTarget,
        page_size: int,
        storage_state: Mapping[str, object],
    ) -> BrowserCapture: ...


@dataclass(frozen=True, slots=True, repr=False)
class DouyinBrowserCredentials:
    _storage_state: dict[str, object]

    def playwright_storage_state(self) -> dict[str, object]:
        return json.loads(json.dumps(self._storage_state, ensure_ascii=False))

    def __repr__(self) -> str:
        cookies = self._storage_state.get("cookies")
        origins = self._storage_state.get("origins")
        return f"DouyinBrowserCredentials(cookie_count={len(cookies) if isinstance(cookies, list) else 0}, origin_count={len(origins) if isinstance(origins, list) else 0}, storage_state=<redacted>)"


class DouyinBrowserAccountRequest(IncubationContract):
    requested_url: NonEmptyStr = Field(max_length=1000)
    max_posts: int = Field(default=12, ge=1, le=24)

    @field_validator("requested_url")
    @classmethod
    def validate_requested_url(cls, value: str) -> str:
        return _clean_douyin_url(value)


@dataclass(frozen=True, slots=True)
class _PostObservation:
    post_id: str
    caption: str | None
    author_id: str | None
    author_name: str | None
    published_at: datetime | None
    captured_at: datetime
    public_metrics: dict[str, int | float]

    @property
    def canonical_url(self) -> str:
        return f"https://www.douyin.com/video/{quote(self.post_id, safe='')}"


@dataclass(frozen=True, slots=True)
class _ProfileObservation:
    account_id: str
    display_name: str | None
    bio: str | None
    verification: str | None
    visible_post_count: int | None
    public_metrics: dict[str, int | float]


def _host_matches(value: str) -> bool:
    host = (urlsplit(value).hostname or "").lower().strip(".")
    return any(host == domain or host.endswith(f".{domain}") for domain in _DOUYIN_HOSTS)


def _clean_douyin_url(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Douyin URL must be an absolute http or https URL")
    if parsed.username or parsed.password or not _host_matches(value):
        raise ValueError("URL must belong to Douyin and contain no credentials")
    return parsed._replace(fragment="").geturl()


def _canonical_navigation_url(value: str) -> str:
    cleaned = _clean_douyin_url(value)
    parsed = urlsplit(cleaned)
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) >= 2 and parts[-2] == "user" and parts[-1]:
        return f"https://www.douyin.com/user/{quote(parts[-1], safe='')}"
    return parsed._replace(query="", fragment="").geturl().rstrip("/")


def _account_id_from_url(value: str) -> str | None:
    parsed = urlsplit(value)
    if not _host_matches(value):
        return None
    match = re.search(r"/(?:share/)?user/([^/?#]+)", parsed.path)
    if match is None:
        return None
    account_id = match.group(1).strip()
    return account_id or None


def _query_from_content_search_url(value: str) -> str:
    parsed = urlsplit(_clean_douyin_url(value))
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 2 or parts[-2] != "search":
        raise ValueError("content search URL does not contain a query")
    query = unquote(parts[-1]).strip()
    if not query:
        raise ValueError("content search query must not be blank")
    return query


def _filter_storage_state(payload: object) -> dict[str, object]:
    if not isinstance(payload, Mapping):
        raise DouyinBrowserUnavailable("invalid_storage_state")
    raw_cookies = payload.get("cookies")
    raw_origins = payload.get("origins")
    cookie_rows = raw_cookies if isinstance(raw_cookies, Sequence) and not isinstance(raw_cookies, (str, bytes, bytearray)) else ()
    origin_rows = raw_origins if isinstance(raw_origins, Sequence) and not isinstance(raw_origins, (str, bytes, bytearray)) else ()
    cookies = [dict(item) for item in cookie_rows if isinstance(item, Mapping) and _host_matches(f"https://{str(item.get('domain') or '').lstrip('.')}")]
    origins = [dict(item) for item in origin_rows if isinstance(item, Mapping) and isinstance(item.get("origin"), str) and _host_matches(str(item["origin"]))]
    return {"cookies": cookies, "origins": origins}


def load_douyin_storage_state(path: Path | str | None = None) -> DouyinBrowserCredentials:
    configured = path or os.environ.get("DOUYIN_BROWSER_STORAGE_STATE_PATH")
    if configured is None or not str(configured).strip():
        raise DouyinBrowserUnavailable("session_not_connected")
    state_path = Path(configured).expanduser().resolve()
    try:
        if state_path.stat().st_size > _MAX_STORAGE_STATE_BYTES:
            raise DouyinBrowserUnavailable("invalid_storage_state")
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except DouyinBrowserUnavailable:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise DouyinBrowserUnavailable("session_not_connected") from exc
    return DouyinBrowserCredentials(_filter_storage_state(payload))


def _plain_text(value: object, *, limit: int) -> str | None:
    if value is None:
        return None
    plain = re.sub(r"<[^>]+>", "", html.unescape(str(value)))
    normalized = re.sub(r"\s+", " ", plain).strip()
    return normalized[:limit] or None


def _number(value: object) -> int | float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value if value >= 0 else None
    raw = str(value).strip().replace(",", "").replace("，", "")
    if not raw:
        return None
    multipliers = {"万": 10_000, "w": 10_000, "W": 10_000}
    multiplier = multipliers.get(raw[-1], 1)
    if multiplier != 1:
        raw = raw[:-1]
    match = re.search(r"\d+(?:\.\d+)?", raw)
    if match is None:
        return None
    number = float(match.group(0)) * multiplier
    return int(number) if number.is_integer() else number


def _timestamp(value: object) -> datetime | None:
    if value in {None, ""}:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if numeric > 10_000_000_000:
        numeric /= 1000
    try:
        return datetime.fromtimestamp(numeric, tz=UTC)
    except (OverflowError, OSError, ValueError):
        return None


def _metrics(source: object, aliases: Mapping[str, Sequence[str]]) -> dict[str, int | float]:
    if not isinstance(source, Mapping):
        return {}
    result: dict[str, int | float] = {}
    for normalized, names in aliases.items():
        for name in names:
            metric = _number(source.get(name))
            if metric is not None:
                result[normalized] = metric
                break
    if result.get("plays") == 0:
        result.pop("plays")
    return result


def _walk_dicts(value: object):
    if isinstance(value, Mapping):
        yield value
        for child in value.values():
            yield from _walk_dicts(child)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for child in value:
            yield from _walk_dicts(child)


def _post_completeness(post: _PostObservation) -> tuple[int, int]:
    return (
        sum(
            value is not None
            for value in (
                post.caption,
                post.author_id,
                post.author_name,
                post.published_at,
            )
        )
        + len(post.public_metrics),
        len(post.caption or ""),
    )


def _extract_posts(
    payloads: Sequence[object],
    *,
    captured_at: datetime,
) -> tuple[_PostObservation, ...]:
    by_id: dict[str, _PostObservation] = {}
    order: list[str] = []
    for payload in payloads:
        if isinstance(payload, Mapping) and payload.get("status_code") not in {None, 0}:
            continue
        for node in _walk_dicts(payload):
            aweme = node.get("aweme_info")
            if not isinstance(aweme, Mapping) and node.get("aweme_id") and isinstance(node.get("author"), Mapping):
                aweme = node
            if not isinstance(aweme, Mapping):
                continue
            post_id = str(aweme.get("aweme_id") or aweme.get("id") or "").strip()
            if not post_id:
                continue
            author = aweme.get("author") if isinstance(aweme.get("author"), Mapping) else {}
            observation = _PostObservation(
                post_id=post_id,
                caption=_plain_text(aweme.get("desc"), limit=4000),
                author_id=str(author.get("sec_uid") or author.get("uid") or "").strip() or None,
                author_name=_plain_text(author.get("nickname"), limit=300),
                published_at=_timestamp(aweme.get("create_time")),
                captured_at=captured_at,
                public_metrics=_metrics(
                    aweme.get("statistics") or aweme.get("stats"),
                    {
                        "plays": ("play_count",),
                        "likes": ("digg_count",),
                        "comments": ("comment_count",),
                        "shares": ("share_count",),
                        "favorites": ("collect_count",),
                    },
                ),
            )
            current = by_id.get(post_id)
            if current is None:
                by_id[post_id] = observation
                order.append(post_id)
            elif _post_completeness(observation) > _post_completeness(current):
                by_id[post_id] = observation
    return tuple(by_id[post_id] for post_id in order)


def _extract_profile(payloads: Sequence[object]) -> _ProfileObservation | None:
    for payload in payloads:
        if not isinstance(payload, Mapping) or payload.get("status_code") not in {None, 0}:
            continue
        user = payload.get("user")
        if not isinstance(user, Mapping):
            continue
        account_id = str(user.get("sec_uid") or user.get("uid") or "").strip()
        if not account_id:
            continue
        visible_post_count = _number(user.get("aweme_count"))
        return _ProfileObservation(
            account_id=account_id,
            display_name=_plain_text(user.get("nickname"), limit=300),
            bio=_plain_text(user.get("signature"), limit=2000),
            verification=_plain_text(
                user.get("custom_verify") or user.get("enterprise_verify_reason"),
                limit=500,
            ),
            visible_post_count=(int(visible_post_count) if isinstance(visible_post_count, (int, float)) else None),
            public_metrics=_metrics(
                user,
                {
                    "followers": ("follower_count", "fans_count"),
                    "following": ("following_count",),
                    "likes_received": ("total_favorited",),
                },
            ),
        )
    return None


def _actor_key(value: str | None) -> str:
    normalized = unicodedata.normalize("NFKC", value or "")
    return "".join(normalized.split()).casefold()


def _capture_ready(capture: BrowserCapture) -> None:
    if capture.page_state is BrowserPageState.NEEDS_LOGIN:
        raise DouyinBrowserUnavailable("login_required")
    if capture.page_state is BrowserPageState.RESTRICTED:
        raise DouyinBrowserUnavailable("platform_restricted")


def _storage_state(value: Mapping[str, object] | None) -> dict[str, object]:
    if value is not None:
        return _filter_storage_state(value)
    return load_douyin_storage_state().playwright_storage_state()


async def collect_browser_benchmark_candidate(
    request: object,
    *,
    runner: BrowserRunner | None = None,
    storage_state: Mapping[str, object] | None = None,
) -> EvidenceSnapshot:
    query = str(getattr(request, "query", "")).strip()
    actor_label = str(getattr(request, "actor_label", "")).strip()
    max_posts = int(getattr(request, "max_posts", 12))
    if not query or not actor_label or not 1 <= max_posts <= 24:
        raise ValueError("invalid browser benchmark candidate request")
    capture = await (runner or PlaywrightDouyinBrowserRunner()).capture(
        url=f"https://www.douyin.com/search/{quote(query, safe='')}?type=video",
        target=BrowserTarget.CONTENT,
        page_size=max_posts,
        storage_state=_storage_state(storage_state),
    )
    _capture_ready(capture)
    if not capture.response_payloads:
        raise DouyinBrowserUnavailable("search_response_not_observed")
    posts = _extract_posts(capture.response_payloads, captured_at=capture.captured_at)
    target_key = _actor_key(actor_label)
    selected = [post for post in posts if _actor_key(post.author_name) == target_key][:max_posts]
    evidence_items: list[EvidenceItem] = []
    for post in selected:
        observed_values: dict[str, str | int | float] = dict(post.public_metrics)
        if post.author_id is not None:
            observed_values["author_external_account_id"] = post.author_id
        if post.published_at is not None:
            observed_values["published_at"] = post.published_at.isoformat()
        evidence_items.append(
            EvidenceItem(
                source_ref=f"douyin:video:{post.post_id}",
                source_type="douyin_video",
                title=post.caption or f"Douyin video {post.post_id}",
                excerpt=post.caption or "Public Douyin video without a visible caption.",
                provenance="observed",
                public_uri=post.canonical_url,
                actor_label=post.author_name,
                observed_values=observed_values,
            )
        )
    limitations = (
        "Authenticated browser search is ranked and bounded; it is not a complete account post list.",
        "Display-name matching remains candidate evidence until a stable account page is collected.",
        "Public captions and counts are observations, not positioning, audience, causality, or copyability conclusions.",
    )
    return EvidenceSnapshot(
        provider="douyin_authenticated_browser",
        collection_method="authenticated_browser_network_capture",
        evidence_role="benchmark_account_candidate",
        captured_at=capture.captured_at,
        rights_basis="public pages viewed through the user's local authenticated Douyin browser session",
        query=query,
        items=tuple(evidence_items),
        coverage=EvidenceCoverageReceipt(
            population_scope="bounded_authenticated_video_search_matching_actor_display_name",
            requested_count=max_posts,
            returned_count=len(evidence_items),
            excluded_count=max(0, len(posts) - len(selected)),
            has_more=None,
            limitations=("Coverage describes captured search responses, not the creator's complete account.",),
        ),
        route_receipt={
            "adapter": "douyin.browser.network_capture",
            "capability_version": "douyin-browser-fallback-v1",
            "target_identity_status": "display_name_candidate_with_observed_author_id",
            "authenticated": True,
        },
        warnings=(("No exact actor display-name match appeared in the bounded browser response.",) if not evidence_items else ()),
        limitations=limitations,
    )


def _single_author(posts: Sequence[_PostObservation]) -> tuple[str, str | None]:
    author_ids = {post.author_id for post in posts if post.author_id}
    if any(post.author_id is None for post in posts) or len(author_ids) != 1:
        raise DouyinBrowserUnavailable("author_identity_not_stable")
    account_id = next(iter(author_ids))
    names = Counter(post.author_name.strip() for post in posts if post.author_name and post.author_id == account_id)
    return account_id, names.most_common(1)[0][0] if names else None


async def collect_browser_benchmark_account(
    request: DouyinBrowserAccountRequest,
    *,
    runner: BrowserRunner | None = None,
    storage_state: Mapping[str, object] | None = None,
) -> BenchmarkSnapshot:
    navigation_url = _canonical_navigation_url(request.requested_url)
    capture = await (runner or PlaywrightDouyinBrowserRunner()).capture(
        url=navigation_url,
        target=BrowserTarget.ACCOUNT_POSTS,
        page_size=request.max_posts,
        storage_state=_storage_state(storage_state),
    )
    _capture_ready(capture)
    all_posts = _extract_posts(capture.response_payloads, captured_at=capture.captured_at)
    profile = _extract_profile(capture.response_payloads)
    expected_account_id = profile.account_id if profile is not None else _account_id_from_url(capture.final_url)
    if expected_account_id is not None:
        posts = tuple(post for post in all_posts if post.author_id == expected_account_id)[: request.max_posts]
    else:
        posts = all_posts[: request.max_posts]
    if not posts:
        raise DouyinBrowserUnavailable("no_author_qualified_posts")
    account_id, display_name = _single_author(posts)
    if profile is not None and profile.account_id != account_id:
        raise DouyinBrowserUnavailable("profile_post_identity_mismatch")
    if profile is None:
        profile = _ProfileObservation(
            account_id=account_id,
            display_name=display_name,
            bio=None,
            verification=None,
            visible_post_count=None,
            public_metrics={},
        )
    excluded_count = len(all_posts) - len(posts)
    canonical_profile_url = f"https://www.douyin.com/user/{quote(account_id, safe='')}"
    post_observations = tuple(
        BenchmarkPostObservation(
            platform="douyin",
            external_post_id=post.post_id,
            author_external_account_id=account_id,
            canonical_url=post.canonical_url,
            caption=post.caption,
            published_at=post.published_at,
            captured_at=post.captured_at,
            public_metrics=post.public_metrics,
        )
        for post in posts
    )
    return BenchmarkSnapshot(
        provider="douyin_authenticated_browser",
        collection_method="authenticated_browser_network_capture",
        captured_at=capture.captured_at,
        rights_basis="public account pages viewed through the user's local authenticated Douyin browser session",
        requested_url=request.requested_url,
        profile=BenchmarkProfileObservation(
            platform="douyin",
            external_account_id=account_id,
            canonical_url=canonical_profile_url,
            display_name=profile.display_name or display_name,
            bio=profile.bio,
            verification=profile.verification,
            visible_post_count=profile.visible_post_count,
            captured_at=capture.captured_at,
            public_metrics=profile.public_metrics,
        ),
        posts=post_observations,
        coverage=BenchmarkCoverageReceipt(
            population_scope="author_qualified_posts_visible_on_the_bounded_account_page",
            requested_count=request.max_posts,
            returned_count=len(post_observations),
            excluded_count=excluded_count,
            has_more=(profile.visible_post_count > len(post_observations) if profile.visible_post_count is not None else None),
            sample_basis=f"Bounded local browser capture requested at most {request.max_posts} author-qualified posts.",
            limitations=("The visible account page may not expose every historical post or metric.",),
        ),
        route_receipt=BenchmarkRouteReceipt(
            adapter="douyin.browser.network_capture",
            capability_version="douyin-browser-fallback-v1",
            route="account_posts",
        ),
        limitations=(
            "Only author-qualified structured responses were retained; recommendations and raw pages were discarded.",
            "Public captions and metrics are point-in-time observations, not audience or success-cause conclusions.",
        ),
    )


def _response_url_is_relevant(url: str, target: BrowserTarget) -> bool:
    if not _host_matches(url):
        return False
    path = urlsplit(url).path.casefold()
    if target is BrowserTarget.CONTENT:
        return any(
            marker in path
            for marker in (
                "/general/search/stream/",
                "/general/search/single/",
            )
        )
    return any(
        marker in path
        for marker in (
            "/aweme/post/",
            "/user/profile/",
            "/user/detail/",
        )
    )


def _decode_length_prefixed_json_stream(body: bytes) -> tuple[object, ...]:
    if not body or len(body) > _MAX_STORAGE_STATE_BYTES:
        return ()
    frames: list[object] = []
    offset = 0
    while offset < len(body) and len(frames) < _MAX_RESPONSE_PAYLOADS:
        while body[offset : offset + 2] == b"\r\n":
            offset += 2
            if offset >= len(body):
                return tuple(frames)
        separator = body.find(b"\r\n", offset)
        if separator < 0:
            return ()
        length_text = body[offset:separator]
        if not length_text.isdigit() or len(length_text) > 10:
            return ()
        frame_length = int(length_text)
        frame_start = separator + 2
        frame_end = frame_start + frame_length
        if frame_length <= 0 or frame_end > len(body):
            return ()
        try:
            frames.append(json.loads(body[frame_start:frame_end]))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return ()
        offset = frame_end
    if body[offset:].strip(b"\r\n"):
        return ()
    return tuple(frames)


async def _read_response_json(
    response: object,
    *,
    target: BrowserTarget,
) -> object | None:
    url = str(getattr(response, "url", ""))
    if not _response_url_is_relevant(url, target):
        return None
    try:
        headers = await response.all_headers()
        content_type = str(headers.get("content-type", "")).casefold()
        content_length = _number(headers.get("content-length"))
        if "json" not in content_type:
            return None
        if content_length is not None and content_length > _MAX_STORAGE_STATE_BYTES:
            return None
        try:
            return await response.json()
        except Exception:
            body = await response.body()
            frames = _decode_length_prefixed_json_stream(body)
            return frames or None
    except Exception:
        return None


def _detect_page_state(
    final_url: str,
    body_text: str,
    page_title: str = "",
) -> BrowserPageState:
    normalized = re.sub(r"\s+", " ", f"{page_title} {body_text}").casefold()
    if any(
        marker in normalized
        for marker in (
            "captcha",
            "verify you are human",
            "访问频繁",
            "安全验证",
            "验证码",
            "完成验证",
            "操作频繁",
        )
    ):
        return BrowserPageState.RESTRICTED
    if "login" in final_url.casefold() or any(marker in normalized for marker in ("扫码登录", "手机号登录", "登录后查看")):
        return BrowserPageState.NEEDS_LOGIN
    return BrowserPageState.READY


class PlaywrightDouyinBrowserRunner:
    """Capture bounded Douyin JSON responses without returning raw page state."""

    def __init__(
        self,
        *,
        headless: bool | None = None,
        navigation_timeout_ms: int = 60_000,
        settle_ms: int = 1_500,
    ) -> None:
        if headless is None:
            headless = os.environ.get("DOUYIN_BROWSER_HEADLESS", "0").strip() in {
                "1",
                "true",
                "yes",
            }
        self._headless = headless
        self._navigation_timeout_ms = navigation_timeout_ms
        self._settle_ms = settle_ms

    async def capture(
        self,
        *,
        url: str,
        target: BrowserTarget,
        page_size: int,
        storage_state: Mapping[str, object],
    ) -> BrowserCapture:
        _clean_douyin_url(url)
        try:
            from playwright.async_api import TimeoutError as PlaywrightTimeoutError
            from playwright.async_api import async_playwright
        except ImportError as exc:
            raise DouyinBrowserUnavailable("playwright_not_installed") from exc

        captured_at = datetime.now(UTC)
        payloads: list[object] = []
        pending: set[asyncio.Task[None]] = set()
        payload_ready = asyncio.Event()
        try:
            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch(headless=self._headless)
                try:
                    context = await browser.new_context(storage_state=dict(storage_state))
                    page = await context.new_page()

                    async def read_response(response: object) -> None:
                        if len(payloads) >= _MAX_RESPONSE_PAYLOADS:
                            return
                        payload = await _read_response_json(
                            response,
                            target=target,
                        )
                        if payload is not None:
                            payloads.append(payload)
                            payload_ready.set()

                    def on_response(response: object) -> None:
                        task = asyncio.create_task(read_response(response))
                        pending.add(task)
                        task.add_done_callback(pending.discard)

                    page.on("response", on_response)
                    if target is BrowserTarget.CONTENT:
                        query = _query_from_content_search_url(url)
                        await page.goto(
                            "https://www.douyin.com/",
                            wait_until="domcontentloaded",
                            timeout=self._navigation_timeout_ms,
                        )
                        try:
                            for _ in range(3):
                                dismiss = page.get_by_text("取消", exact=True)
                                if await dismiss.count() and await dismiss.first.is_visible():
                                    await dismiss.first.click()
                                    await page.wait_for_timeout(500)
                                search_input = page.locator('input[placeholder*="搜索"]').first
                                await search_input.fill(query)
                                await page.get_by_role(
                                    "button",
                                    name="搜索",
                                    exact=True,
                                ).click()
                                try:
                                    await page.wait_for_url(
                                        "**/search/**",
                                        wait_until="domcontentloaded",
                                        timeout=5_000,
                                    )
                                    break
                                except PlaywrightTimeoutError:
                                    if "/search/" in page.url:
                                        break
                            if "/search/" not in page.url:
                                raise DouyinBrowserUnavailable("browser_search_navigation_failed")
                            dismiss = page.get_by_text("取消", exact=True)
                            if await dismiss.count() and await dismiss.first.is_visible():
                                await dismiss.first.click()
                            try:
                                await asyncio.wait_for(
                                    payload_ready.wait(),
                                    timeout=20.0,
                                )
                            except TimeoutError as exc:
                                raise DouyinBrowserUnavailable("search_response_not_observed") from exc
                        except Exception as exc:
                            if isinstance(exc, DouyinBrowserUnavailable):
                                raise
                            raise DouyinBrowserUnavailable("browser_search_ui_changed") from exc
                    else:
                        await page.goto(
                            url,
                            wait_until="domcontentloaded",
                            timeout=self._navigation_timeout_ms,
                        )
                        canonical = _canonical_navigation_url(page.url)
                        if _account_id_from_url(canonical) is not None and canonical != page.url.split("?", 1)[0].rstrip("/"):
                            await page.goto(
                                canonical,
                                wait_until="domcontentloaded",
                                timeout=self._navigation_timeout_ms,
                            )
                    await page.wait_for_timeout(self._settle_ms)
                    scrolls = min(12, max(2, (page_size + 9) // 10))
                    for _ in range(scrolls):
                        await page.evaluate("window.scrollBy(0, Math.max(900, innerHeight))")
                        await page.wait_for_timeout(600)
                    if pending:
                        _, unfinished = await asyncio.wait(tuple(pending), timeout=5.0)
                        for task in unfinished:
                            task.cancel()
                        if unfinished:
                            await asyncio.gather(*unfinished, return_exceptions=True)
                    body_text = await page.locator("body").inner_text(timeout=5_000)
                    page_title = await page.title()
                    return BrowserCapture(
                        captured_at=captured_at,
                        final_url=page.url,
                        page_state=_detect_page_state(
                            page.url,
                            body_text[:20_000],
                            page_title[:500],
                        ),
                        response_payloads=tuple(payloads),
                    )
                finally:
                    await browser.close()
        except DouyinBrowserUnavailable:
            raise
        except Exception as exc:
            raise DouyinBrowserUnavailable("browser_runtime_failed") from exc


__all__ = [
    "BrowserCapture",
    "BrowserPageState",
    "BrowserRunner",
    "BrowserTarget",
    "DouyinBrowserAccountRequest",
    "DouyinBrowserCredentials",
    "DouyinBrowserUnavailable",
    "PlaywrightDouyinBrowserRunner",
    "collect_browser_benchmark_account",
    "collect_browser_benchmark_candidate",
    "load_douyin_storage_state",
]
