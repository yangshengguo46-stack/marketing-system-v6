from __future__ import annotations

import json
import os
import unicodedata
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol
from urllib.parse import quote, urlsplit

from pydantic import Field, field_validator, model_validator

from deerflow.incubation.contracts import IncubationContract, NonEmptyStr
from deerflow.incubation.evidence import (
    EvidenceCoverageReceipt,
    EvidenceItem,
    EvidenceSnapshot,
)

_STORAGE_STATE_ENV = "TIKTOK_BROWSER_STORAGE_STATE_PATH"
_MAX_STORAGE_STATE_BYTES = 2_000_000
_MAX_HYDRATION_BYTES = 2_000_000
_MAX_HYDRATION_DOCUMENTS = 8
_MAX_CAPTURED_ACCOUNTS = 64
_MAX_CAPTURED_POSTS = 256
_SESSION_COOKIE_NAMES = frozenset(
    {
        "sessionid",
        "sessionid_ss",
        "sid_guard",
        "sid_tt",
    }
)
_METRIC_KEYS = frozenset({"views", "likes", "comments", "shares", "saves"})


class TikTokBenchmarkNeedsLogin(RuntimeError):
    """The local TikTok browser state is missing or no longer authenticated."""


class TikTokBenchmarkUnavailable(RuntimeError):
    """TikTok candidate discovery is unavailable for a non-login reason."""


def _is_tiktok_url(value: str) -> bool:
    parsed = urlsplit(value)
    host = (parsed.hostname or "").rstrip(".").casefold()
    return parsed.scheme == "https" and (host == "tiktok.com" or host.endswith(".tiktok.com"))


def _normalize_text(value: str | None) -> str:
    normalized = unicodedata.normalize("NFKC", value or "")
    return "".join(normalized.split()).casefold()


def _normalize_username(value: str | None) -> str:
    return _normalize_text(value).lstrip("@")


class TikTokBenchmarkRequest(IncubationContract):
    query: NonEmptyStr = Field(max_length=500)
    max_accounts: int = Field(default=5, ge=1, le=8)
    representative_posts_per_account: int = Field(default=3, ge=1, le=6)

    @field_validator("query")
    @classmethod
    def normalize_query(cls, value: str) -> str:
        return " ".join(value.split())


class TikTokAccountCandidateCapture(IncubationContract):
    observed_account_id: NonEmptyStr | None = Field(default=None, max_length=255)
    username: NonEmptyStr | None = Field(default=None, max_length=200)
    display_name: NonEmptyStr | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def require_identity(self) -> TikTokAccountCandidateCapture:
        if not any((self.observed_account_id, self.username, self.display_name)):
            raise ValueError("TikTok account capture requires an observed identity")
        return self


class TikTokPostCapture(IncubationContract):
    observed_post_id: NonEmptyStr = Field(max_length=255)
    observed_account_id: NonEmptyStr | None = Field(default=None, max_length=255)
    author_username: NonEmptyStr | None = Field(default=None, max_length=200)
    author_display_name: NonEmptyStr | None = Field(default=None, max_length=200)
    caption: NonEmptyStr | None = Field(default=None, max_length=4000)
    public_uri: NonEmptyStr = Field(max_length=1000)
    published_at: datetime | None = None
    public_metrics: dict[str, int | float] = Field(default_factory=dict)

    @field_validator("public_uri")
    @classmethod
    def require_tiktok_uri(cls, value: str) -> str:
        if not _is_tiktok_url(value):
            raise ValueError("TikTok post URI must use tiktok.com")
        return value

    @field_validator("published_at")
    @classmethod
    def normalize_published_at(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("published_at must be timezone-aware")
        return value.astimezone(UTC)

    @field_validator("public_metrics")
    @classmethod
    def validate_public_metrics(
        cls,
        value: dict[str, int | float],
    ) -> dict[str, int | float]:
        if any(key not in _METRIC_KEYS for key in value):
            raise ValueError("unsupported TikTok public metric")
        if any(metric < 0 for metric in value.values()):
            raise ValueError("TikTok public metrics must be non-negative")
        return value

    @model_validator(mode="after")
    def require_author_identity(self) -> TikTokPostCapture:
        if not any(
            (
                self.observed_account_id,
                self.author_username,
                self.author_display_name,
            )
        ):
            raise ValueError("TikTok post capture requires an observed author identity")
        return self


class TikTokBenchmarkCapture(IncubationContract):
    captured_at: datetime
    final_url: NonEmptyStr = Field(max_length=1000)
    authenticated: bool
    login_required: bool
    search_observed: bool
    account_candidates: tuple[TikTokAccountCandidateCapture, ...] = Field(
        default=(),
        max_length=_MAX_CAPTURED_ACCOUNTS,
    )
    posts: tuple[TikTokPostCapture, ...] = Field(
        default=(),
        max_length=_MAX_CAPTURED_POSTS,
    )

    @field_validator("captured_at")
    @classmethod
    def normalize_captured_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("captured_at must be timezone-aware")
        return value.astimezone(UTC)

    @field_validator("final_url")
    @classmethod
    def require_tiktok_final_url(cls, value: str) -> str:
        if not _is_tiktok_url(value):
            raise ValueError("TikTok final URL must use tiktok.com")
        return value

    @model_validator(mode="after")
    def validate_authentication_flags(self) -> TikTokBenchmarkCapture:
        if self.authenticated and self.login_required:
            raise ValueError("authenticated and login_required cannot both be true")
        return self


class TikTokBenchmarkRunner(Protocol):
    async def capture(
        self,
        *,
        query: str,
        max_accounts: int,
        representative_posts_per_account: int,
    ) -> TikTokBenchmarkCapture: ...


class _CandidateGroup:
    def __init__(
        self,
        *,
        identity_basis: str,
        observed_account_id: str | None,
        username: str | None,
        display_name: str | None,
        first_seen: int,
    ) -> None:
        self.identity_basis = identity_basis
        self.observed_account_id = observed_account_id
        self.username = username
        self.display_name = display_name
        self.first_seen = first_seen
        self.posts: list[TikTokPostCapture] = []

    def observe_identity(
        self,
        *,
        observed_account_id: str | None,
        username: str | None,
        display_name: str | None,
    ) -> None:
        self.observed_account_id = self.observed_account_id or observed_account_id
        self.username = self.username or username
        self.display_name = self.display_name or display_name


def _identity_tokens(
    *,
    observed_account_id: str | None,
    username: str | None,
    display_name: str | None,
) -> tuple[str | None, str | None, str | None]:
    account_key = _normalize_text(observed_account_id)
    username_key = _normalize_username(username)
    display_key = _normalize_text(display_name)
    return (
        f"id:{account_key}" if account_key else None,
        f"username:{username_key}" if username_key else None,
        f"display:{display_key}" if display_key else None,
    )


def _identity_indexes(
    capture: TikTokBenchmarkCapture,
) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    username_to_ids: dict[str, set[str]] = defaultdict(set)
    display_to_ids: dict[str, set[str]] = defaultdict(set)
    observations = [
        (
            account.observed_account_id,
            account.username,
            account.display_name,
        )
        for account in capture.account_candidates
    ]
    observations.extend(
        (
            post.observed_account_id,
            post.author_username,
            post.author_display_name,
        )
        for post in capture.posts
    )
    for account_id, username, display_name in observations:
        id_key, username_key, display_key = _identity_tokens(
            observed_account_id=account_id,
            username=username,
            display_name=display_name,
        )
        if id_key is None:
            continue
        if username_key is not None:
            username_to_ids[username_key].add(id_key)
        if display_key is not None:
            display_to_ids[display_key].add(id_key)
    return username_to_ids, display_to_ids


def _resolve_identity_key(
    *,
    observed_account_id: str | None,
    username: str | None,
    display_name: str | None,
    username_to_ids: Mapping[str, set[str]],
    display_to_ids: Mapping[str, set[str]],
) -> tuple[str, str]:
    id_key, username_key, display_key = _identity_tokens(
        observed_account_id=observed_account_id,
        username=username,
        display_name=display_name,
    )
    if id_key is not None:
        return id_key, "observed_account_id"
    if username_key is not None:
        matching_ids = username_to_ids.get(username_key, set())
        if len(matching_ids) == 1:
            return next(iter(matching_ids)), "observed_account_id"
        return username_key, "normalized_username"
    if display_key is not None:
        matching_ids = display_to_ids.get(display_key, set())
        if len(matching_ids) == 1:
            return next(iter(matching_ids)), "observed_account_id"
        return display_key, "normalized_display_name"
    raise TikTokBenchmarkUnavailable("candidate_identity_missing")


def _group_capture(
    capture: TikTokBenchmarkCapture,
) -> tuple[list[_CandidateGroup], int]:
    username_to_ids, display_to_ids = _identity_indexes(capture)
    groups: dict[str, _CandidateGroup] = {}
    order = 0

    def group_for(
        *,
        observed_account_id: str | None,
        username: str | None,
        display_name: str | None,
    ) -> _CandidateGroup:
        nonlocal order
        key, basis = _resolve_identity_key(
            observed_account_id=observed_account_id,
            username=username,
            display_name=display_name,
            username_to_ids=username_to_ids,
            display_to_ids=display_to_ids,
        )
        group = groups.get(key)
        if group is None:
            group = _CandidateGroup(
                identity_basis=basis,
                observed_account_id=observed_account_id,
                username=username,
                display_name=display_name,
                first_seen=order,
            )
            groups[key] = group
            order += 1
        else:
            group.observe_identity(
                observed_account_id=observed_account_id,
                username=username,
                display_name=display_name,
            )
        return group

    for account in capture.account_candidates:
        group_for(
            observed_account_id=account.observed_account_id,
            username=account.username,
            display_name=account.display_name,
        )

    duplicate_count = 0
    seen_posts: set[str] = set()
    for post in capture.posts:
        post_key = _normalize_text(post.observed_post_id) or post.public_uri
        if post_key in seen_posts:
            duplicate_count += 1
            continue
        seen_posts.add(post_key)
        group_for(
            observed_account_id=post.observed_account_id,
            username=post.author_username,
            display_name=post.author_display_name,
        ).posts.append(post)

    ordered = sorted(
        groups.values(),
        key=lambda group: (-len(group.posts), group.first_seen),
    )
    return ordered, duplicate_count


def _identity_status(groups: Sequence[_CandidateGroup]) -> str:
    if not groups:
        return "no_candidate_identity_observed"
    bases = {group.identity_basis for group in groups}
    if bases == {"observed_account_id"}:
        return "multiple_observed_account_id_candidates"
    if "observed_account_id" in bases:
        return "mixed_observed_id_and_normalized_username_candidates"
    return "normalized_username_or_display_name_candidates"


def _candidate_summary(
    group: _CandidateGroup,
    *,
    sample_count: int,
) -> dict[str, str | int]:
    summary: dict[str, str | int] = {
        "identity_basis": group.identity_basis,
        "sample_count": sample_count,
        "observed_distinct_post_count": len(group.posts),
    }
    if group.observed_account_id is not None:
        summary["observed_account_id"] = group.observed_account_id
    if group.username is not None:
        summary["username"] = group.username
    if group.display_name is not None:
        summary["display_name"] = group.display_name
    return summary


def _evidence_item(
    post: TikTokPostCapture,
    group: _CandidateGroup,
) -> EvidenceItem:
    observed_values: dict[str, str | int | float] = dict(post.public_metrics)
    if group.observed_account_id is not None:
        observed_values["observed_account_id"] = group.observed_account_id
    if group.username is not None:
        observed_values["author_username"] = group.username
    if post.published_at is not None:
        observed_values["published_at"] = post.published_at.isoformat()
    caption = post.caption or f"TikTok video {post.observed_post_id}"
    actor_label = group.display_name or group.username or group.observed_account_id or "TikTok creator"
    return EvidenceItem(
        source_ref=f"tiktok:video:{post.observed_post_id}",
        source_type="tiktok_video",
        title=caption[:500],
        excerpt=caption[:4000],
        provenance="observed",
        public_uri=post.public_uri,
        actor_label=actor_label,
        observed_values=observed_values,
    )


async def discover_tiktok_benchmark_candidates(
    request: TikTokBenchmarkRequest,
    *,
    runner: TikTokBenchmarkRunner | None = None,
) -> EvidenceSnapshot:
    """Return bounded candidate evidence from a local authenticated TikTok search.

    This primitive discovers possible benchmark accounts only. It does not
    establish a formal, author-complete ``BenchmarkSnapshot``.
    """

    selected_runner = runner or PlaywrightTikTokBenchmarkRunner()
    try:
        capture = await selected_runner.capture(
            query=request.query,
            max_accounts=request.max_accounts,
            representative_posts_per_account=(request.representative_posts_per_account),
        )
    except (TikTokBenchmarkNeedsLogin, TikTokBenchmarkUnavailable):
        raise
    except Exception:
        raise TikTokBenchmarkUnavailable("runner_failed") from None

    if not isinstance(capture, TikTokBenchmarkCapture):
        raise TikTokBenchmarkUnavailable("invalid_capture")
    if capture.login_required:
        raise TikTokBenchmarkNeedsLogin("login_required")
    if not capture.authenticated:
        raise TikTokBenchmarkNeedsLogin("authentication_not_confirmed")
    if not capture.search_observed:
        raise TikTokBenchmarkUnavailable("structured_search_not_observed")

    groups, duplicate_count = _group_capture(capture)
    selected_groups = groups[: request.max_accounts]
    evidence_items: list[EvidenceItem] = []
    summaries: list[dict[str, str | int]] = []
    for group in selected_groups:
        selected_posts = group.posts[: request.representative_posts_per_account]
        evidence_items.extend(_evidence_item(post, group) for post in selected_posts)
        summaries.append(_candidate_summary(group, sample_count=len(selected_posts)))

    distinct_posts = sum(len(group.posts) for group in groups)
    excluded_count = max(0, distinct_posts - len(evidence_items))
    has_more = excluded_count > 0 or len(groups) > len(selected_groups)
    warnings = ("The authenticated bounded search returned no structured account candidates or posts.",) if not groups else ()
    return EvidenceSnapshot(
        provider="tiktok_authenticated_browser",
        collection_method="authenticated_browser_hydration_json",
        evidence_role="benchmark_account_candidate",
        captured_at=capture.captured_at,
        rights_basis=("public pages viewed through the user's local authenticated TikTok browser session"),
        query=request.query,
        items=tuple(evidence_items),
        coverage=EvidenceCoverageReceipt(
            population_scope="bounded_authenticated_tiktok_search_candidates",
            requested_count=(request.max_accounts * request.representative_posts_per_account),
            returned_count=len(evidence_items),
            excluded_count=excluded_count,
            duplicate_count=duplicate_count,
            has_more=has_more,
            limitations=("Coverage describes one bounded search capture, not complete creator account histories.",),
        ),
        route_receipt={
            "adapter": "tiktok.local_browser.hydration_json",
            "capability_version": "tiktok-benchmark-candidate-v1",
            "target_identity_status": _identity_status(selected_groups),
            "candidate_summaries": summaries,
            "authenticated": True,
            "login_required": False,
            "final_url": capture.final_url,
            "max_accounts": request.max_accounts,
            "representative_posts_per_account": (request.representative_posts_per_account),
        },
        warnings=warnings,
        limitations=(
            "Stable observed account IDs are preferred; normalized usernames or display names remain candidate identities when IDs are absent.",
            "This is benchmark-account discovery evidence, not a formal BenchmarkSnapshot.",
            "Public posts and metrics are observations, not positioning, audience, causality, or copyability conclusions.",
        ),
    )


def _filtered_storage_state(payload: object) -> dict[str, object]:
    if not isinstance(payload, Mapping):
        raise TikTokBenchmarkNeedsLogin("storage_state_invalid")
    cookies: list[dict[str, object]] = []
    for cookie in payload.get("cookies") or ():
        if not isinstance(cookie, Mapping):
            continue
        domain = str(cookie.get("domain") or "").lstrip(".")
        if not _is_tiktok_url(f"https://{domain}/"):
            continue
        cookies.append(dict(cookie))
    origins: list[dict[str, object]] = []
    for origin in payload.get("origins") or ():
        if not isinstance(origin, Mapping):
            continue
        if _is_tiktok_url(str(origin.get("origin") or "")):
            origins.append(dict(origin))
    if not _has_session_cookie(cookies):
        raise TikTokBenchmarkNeedsLogin("login_state_missing")
    return {"cookies": cookies, "origins": origins}


def _has_session_cookie(value: object) -> bool:
    if not isinstance(value, Sequence) or isinstance(
        value,
        (str, bytes, bytearray),
    ):
        return False
    return any(isinstance(cookie, Mapping) and str(cookie.get("name") or "").casefold() in _SESSION_COOKIE_NAMES for cookie in value)


def _load_storage_state() -> dict[str, object]:
    configured_path = os.environ.get(_STORAGE_STATE_ENV, "").strip()
    if not configured_path:
        raise TikTokBenchmarkNeedsLogin("storage_state_not_configured")
    path = Path(configured_path).expanduser()
    try:
        if path.stat().st_size > _MAX_STORAGE_STATE_BYTES:
            raise TikTokBenchmarkNeedsLogin("storage_state_invalid")
        payload = json.loads(path.read_text(encoding="utf-8"))
    except TikTokBenchmarkNeedsLogin:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        raise TikTokBenchmarkNeedsLogin("storage_state_invalid") from None
    return _filtered_storage_state(payload)


def _walk_mappings(value: object):
    if isinstance(value, Mapping):
        yield value
        for child in value.values():
            yield from _walk_mappings(child)
    elif isinstance(value, Sequence) and not isinstance(
        value,
        (str, bytes, bytearray),
    ):
        for child in value:
            yield from _walk_mappings(child)


def _text(value: object, *, limit: int) -> str | None:
    if not isinstance(value, (str, int)):
        return None
    result = " ".join(str(value).split())
    return result[:limit] or None


def _number(value: object) -> int | float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and value >= 0:
        return value
    if isinstance(value, str):
        try:
            parsed = float(value)
        except ValueError:
            return None
        if parsed >= 0:
            return int(parsed) if parsed.is_integer() else parsed
    return None


def _timestamp(value: object) -> datetime | None:
    number = _number(value)
    if number is None:
        return None
    try:
        return datetime.fromtimestamp(float(number), tz=UTC)
    except (OverflowError, OSError, ValueError):
        return None


def _account_from_mapping(
    value: Mapping[str, object],
) -> TikTokAccountCandidateCapture | None:
    username = _text(
        value.get("uniqueId") or value.get("unique_id") or value.get("username"),
        limit=200,
    )
    display_name = _text(
        value.get("nickname") or value.get("nickName"),
        limit=200,
    )
    if username is None and display_name is None:
        return None
    account_id = _text(
        value.get("secUid") or value.get("sec_uid") or value.get("uid") or value.get("userId") or value.get("id"),
        limit=255,
    )
    return TikTokAccountCandidateCapture(
        observed_account_id=account_id,
        username=username,
        display_name=display_name,
    )


def _post_from_mapping(
    value: Mapping[str, object],
) -> TikTokPostCapture | None:
    post_id = _text(
        value.get("itemId") or value.get("aweme_id") or value.get("id"),
        limit=255,
    )
    author_value = value.get("author")
    author = author_value if isinstance(author_value, Mapping) else {}
    author_username = _text(
        author.get("uniqueId") or author.get("unique_id") or (author_value if isinstance(author_value, str) else value.get("authorUniqueId")),
        limit=200,
    )
    author_display_name = _text(
        author.get("nickname") or value.get("authorNickname"),
        limit=200,
    )
    account_id = _text(
        value.get("authorId") or author.get("secUid") or author.get("id") or author.get("uid"),
        limit=255,
    )
    caption = _text(
        value.get("desc") or value.get("description") or value.get("text"),
        limit=4000,
    )
    stats = value.get("stats")
    if not isinstance(stats, Mapping):
        stats = value.get("statistics")
    if not isinstance(stats, Mapping):
        stats = {}
    if post_id is None or not any((account_id, author_username, author_display_name)):
        return None
    if caption is None and not stats:
        return None
    if author_username is None:
        return None
    metrics: dict[str, int | float] = {}
    aliases = {
        "views": ("playCount", "play_count"),
        "likes": ("diggCount", "digg_count"),
        "comments": ("commentCount", "comment_count"),
        "shares": ("shareCount", "share_count"),
        "saves": ("collectCount", "collect_count"),
    }
    for key, names in aliases.items():
        for name in names:
            metric = _number(stats.get(name))
            if metric is not None:
                metrics[key] = metric
                break
    return TikTokPostCapture(
        observed_post_id=post_id,
        observed_account_id=account_id,
        author_username=author_username,
        author_display_name=author_display_name,
        caption=caption,
        public_uri=(f"https://www.tiktok.com/@{quote(author_username.lstrip('@'), safe='')}/video/{quote(post_id, safe='')}"),
        published_at=_timestamp(value.get("createTime") or value.get("create_time")),
        public_metrics=metrics,
    )


def _extract_hydration_capture(
    payloads: Sequence[object],
    *,
    captured_at: datetime,
    final_url: str,
    authenticated: bool,
) -> TikTokBenchmarkCapture:
    accounts: list[TikTokAccountCandidateCapture] = []
    posts: list[TikTokPostCapture] = []
    seen_accounts: set[tuple[str, str, str]] = set()
    seen_posts: set[str] = set()
    for payload in payloads:
        for node in _walk_mappings(payload):
            account = _account_from_mapping(node)
            if account is not None:
                key = (
                    _normalize_text(account.observed_account_id),
                    _normalize_username(account.username),
                    _normalize_text(account.display_name),
                )
                if key not in seen_accounts and len(accounts) < _MAX_CAPTURED_ACCOUNTS:
                    seen_accounts.add(key)
                    accounts.append(account)
            post = _post_from_mapping(node)
            if post is not None and post.observed_post_id not in seen_posts and len(posts) < _MAX_CAPTURED_POSTS:
                seen_posts.add(post.observed_post_id)
                posts.append(post)
    return TikTokBenchmarkCapture(
        captured_at=captured_at,
        final_url=final_url,
        authenticated=authenticated,
        login_required=False,
        search_observed=bool(payloads),
        account_candidates=tuple(accounts),
        posts=tuple(posts),
    )


class PlaywrightTikTokBenchmarkRunner:
    """Visible local Playwright runner that emits only whitelisted capture data."""

    def __init__(self, *, headless: bool = False) -> None:
        self.headless = headless

    async def capture(
        self,
        *,
        query: str,
        max_accounts: int,
        representative_posts_per_account: int,
    ) -> TikTokBenchmarkCapture:
        del max_accounts, representative_posts_per_account
        storage_state = _load_storage_state()
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            raise TikTokBenchmarkUnavailable("playwright_unavailable") from None

        search_url = f"https://www.tiktok.com/search/video?q={quote(query, safe='')}"
        payloads: list[object] = []
        captured_at = datetime.now(UTC)
        try:
            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch(headless=self.headless)
                try:
                    context = await browser.new_context(
                        storage_state=storage_state,
                    )
                    page = await context.new_page()

                    async def guard(route: object) -> None:
                        request_url = str(route.request.url)
                        scheme = urlsplit(request_url).scheme.casefold()
                        if scheme in {"about", "blob", "data"} or _is_tiktok_url(request_url):
                            await route.continue_()
                        else:
                            await route.abort()

                    await page.route("**/*", guard)
                    await page.goto(
                        search_url,
                        wait_until="domcontentloaded",
                        timeout=30_000,
                    )
                    final_url = page.url
                    if not _is_tiktok_url(final_url):
                        raise TikTokBenchmarkUnavailable("domain_not_allowed")
                    path = urlsplit(final_url).path.casefold()
                    if any(marker in path for marker in ("/login", "/signup")):
                        raise TikTokBenchmarkNeedsLogin("login_required")
                    if any(marker in path for marker in ("/captcha", "/verify", "/challenge")):
                        raise TikTokBenchmarkUnavailable("platform_blocked")
                    active_cookies = await context.cookies("https://www.tiktok.com")
                    if not _has_session_cookie(active_cookies):
                        raise TikTokBenchmarkNeedsLogin("login_required")
                    selectors = (
                        "script#__UNIVERSAL_DATA_FOR_REHYDRATION__",
                        "script#SIGI_STATE",
                    )
                    for selector in selectors:
                        for text in await page.locator(selector).all_text_contents():
                            encoded = text.encode("utf-8")
                            if not encoded or len(encoded) > _MAX_HYDRATION_BYTES or len(payloads) >= _MAX_HYDRATION_DOCUMENTS:
                                continue
                            try:
                                payloads.append(json.loads(text))
                            except json.JSONDecodeError:
                                continue
                finally:
                    await browser.close()
        except (TikTokBenchmarkNeedsLogin, TikTokBenchmarkUnavailable):
            raise
        except Exception:
            raise TikTokBenchmarkUnavailable("browser_capture_failed") from None

        return _extract_hydration_capture(
            payloads,
            captured_at=captured_at,
            final_url=final_url,
            authenticated=True,
        )


__all__ = [
    "PlaywrightTikTokBenchmarkRunner",
    "TikTokAccountCandidateCapture",
    "TikTokBenchmarkCapture",
    "TikTokBenchmarkNeedsLogin",
    "TikTokBenchmarkRequest",
    "TikTokBenchmarkRunner",
    "TikTokBenchmarkUnavailable",
    "TikTokPostCapture",
    "discover_tiktok_benchmark_candidates",
]
