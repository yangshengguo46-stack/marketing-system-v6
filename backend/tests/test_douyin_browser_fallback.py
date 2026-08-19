from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from deerflow.community.douyin_browser import (
    BrowserCapture,
    BrowserPageState,
    BrowserTarget,
    DouyinBrowserAccountRequest,
    DouyinBrowserUnavailable,
    _decode_length_prefixed_json_stream,
    _detect_page_state,
    _query_from_content_search_url,
    _response_url_is_relevant,
    collect_browser_benchmark_account,
    collect_browser_benchmark_candidate,
    load_douyin_storage_state,
)
from deerflow.community.douyin_openapi import BenchmarkCandidateRequest

NOW = datetime(2026, 8, 19, 14, 0, tzinfo=UTC)
COOKIE_SECRET = "browser-cookie-must-stay-local"


class _Runner:
    def __init__(self, *captures: BrowserCapture) -> None:
        self._captures = list(captures)
        self.calls: list[dict[str, object]] = []

    async def capture(self, **kwargs: object) -> BrowserCapture:
        self.calls.append(kwargs)
        return self._captures.pop(0)


def _storage_state() -> dict[str, object]:
    return {
        "cookies": [
            {
                "name": "sessionid",
                "value": COOKIE_SECRET,
                "domain": ".douyin.com",
                "path": "/",
            }
        ],
        "origins": [],
    }


def test_local_storage_state_filters_other_sites_and_keeps_secrets_out_of_repr(
    tmp_path: Path,
) -> None:
    state_path = tmp_path / "storage-state.json"
    state_path.write_text(
        json.dumps(
            {
                "cookies": [
                    *_storage_state()["cookies"],
                    {
                        "name": "foreign",
                        "value": "must-not-cross-platform",
                        "domain": ".example.com",
                        "path": "/",
                    },
                ],
                "origins": [
                    {
                        "origin": "https://www.douyin.com",
                        "localStorage": [{"name": "local-session", "value": COOKIE_SECRET}],
                    },
                    {
                        "origin": "https://example.com",
                        "localStorage": [{"name": "foreign", "value": "must-not-cross-platform"}],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    credentials = load_douyin_storage_state(state_path)

    assert credentials.playwright_storage_state()["cookies"] == _storage_state()["cookies"]
    assert [item["origin"] for item in credentials.playwright_storage_state()["origins"]] == ["https://www.douyin.com"]
    assert COOKIE_SECRET not in repr(credentials)
    assert "must-not-cross-platform" not in repr(credentials)


def test_empty_storage_state_collections_are_normalized_without_leaking_errors(
    tmp_path: Path,
) -> None:
    state_path = tmp_path / "storage-state.json"
    state_path.write_text(
        json.dumps({"cookies": None, "origins": None}),
        encoding="utf-8",
    )

    credentials = load_douyin_storage_state(state_path)

    assert credentials.playwright_storage_state() == {"cookies": [], "origins": []}


def test_captcha_interstitial_title_is_not_misreported_as_a_ready_empty_page() -> None:
    assert (
        _detect_page_state(
            "https://www.douyin.com/search/watch",
            "",
            "验证码中间页",
        )
        is BrowserPageState.RESTRICTED
    )


def test_content_search_url_preserves_the_exact_unicode_query_for_ui_submission() -> None:
    assert _query_from_content_search_url("https://www.douyin.com/search/%E5%A4%A7%E8%83%BD%20%E8%85%95%E8%A1%A8?type=video") == "大能 腕表"


def test_length_prefixed_search_stream_decodes_json_frames_by_bytes() -> None:
    frames = [
        {"status_code": 0, "data": [{"aweme_info": {"desc": "腕表"}}]},
        {"status_code": 0, "has_more": 0},
    ]
    body = b"".join(str(len(encoded)).encode("ascii") + b"\r\n" + encoded + b"\r\n" for frame in frames for encoded in [json.dumps(frame, ensure_ascii=False).encode("utf-8")])

    assert _decode_length_prefixed_json_stream(body) == tuple(frames)


def test_malformed_length_prefixed_search_stream_is_rejected() -> None:
    assert _decode_length_prefixed_json_stream(b'20\r\n{"partial":true}') == ()


def test_content_network_probe_keeps_search_stream_and_drops_home_feed_noise() -> None:
    assert _response_url_is_relevant(
        "https://www.douyin.com/aweme/v1/web/general/search/stream/",
        BrowserTarget.CONTENT,
    )
    assert _response_url_is_relevant(
        "https://www.douyin.com/aweme/v1/web/general/search/single/",
        BrowserTarget.CONTENT,
    )
    assert not _response_url_is_relevant(
        "https://www.douyin.com/aweme/v1/web/search/sug/",
        BrowserTarget.CONTENT,
    )
    assert not _response_url_is_relevant(
        "https://www.douyin.com/aweme/v1/web/hot/search/list/",
        BrowserTarget.CONTENT,
    )
    assert not _response_url_is_relevant(
        "https://www.douyin.com/aweme/v1/web/solution/resource/list/",
        BrowserTarget.CONTENT,
    )


@pytest.mark.asyncio
async def test_browser_candidate_uses_cookie_locally_and_returns_whitelisted_evidence() -> None:
    runner = _Runner(
        BrowserCapture(
            captured_at=NOW,
            final_url="https://www.douyin.com/search/%E5%A4%A7%E8%83%BD%20%E8%85%95%E8%A1%A8?type=video",
            page_state=BrowserPageState.READY,
            response_payloads=(
                {
                    "data": [
                        {
                            "aweme_info": {
                                "aweme_id": "watch-1",
                                "desc": "手表为什么不只是看时间",
                                "author": {
                                    "sec_uid": "watch-account",
                                    "nickname": "大能",
                                },
                                "statistics": {
                                    "digg_count": 88,
                                    "comment_count": 7,
                                },
                                "raw_cookie": COOKIE_SECRET,
                            }
                        },
                        {
                            "aweme_info": {
                                "aweme_id": "other-1",
                                "desc": "推荐流中的其他作者",
                                "author": {
                                    "sec_uid": "other-account",
                                    "nickname": "其他人",
                                },
                            }
                        },
                    ]
                },
            ),
        )
    )

    snapshot = await collect_browser_benchmark_candidate(
        BenchmarkCandidateRequest(
            query="大能 腕表",
            actor_label="大能",
            max_posts=12,
        ),
        runner=runner,
        storage_state=_storage_state(),
    )

    assert runner.calls[0]["target"] is BrowserTarget.CONTENT
    assert runner.calls[0]["storage_state"] == _storage_state()
    assert snapshot.provider == "douyin_authenticated_browser"
    assert snapshot.collection_method == "authenticated_browser_network_capture"
    assert [item.source_ref for item in snapshot.items] == ["douyin:video:watch-1"]
    assert snapshot.items[0].actor_label == "大能"
    assert snapshot.items[0].observed_values == {
        "author_external_account_id": "watch-account",
        "likes": 88,
        "comments": 7,
    }
    assert COOKIE_SECRET not in snapshot.model_dump_json()
    assert "other-1" not in snapshot.model_dump_json()


@pytest.mark.asyncio
async def test_direct_account_link_builds_author_consistent_benchmark_snapshot() -> None:
    runner = _Runner(
        BrowserCapture(
            captured_at=NOW,
            final_url="https://www.douyin.com/user/watch-account",
            page_state=BrowserPageState.READY,
            response_payloads=(
                {
                    "status_code": 0,
                    "user": {
                        "sec_uid": "watch-account",
                        "nickname": "大能",
                        "signature": "腕表内容创作者",
                        "follower_count": 9_000_000,
                        "aweme_count": 572,
                    },
                },
                {
                    "status_code": 0,
                    "aweme_list": [
                        {
                            "aweme_id": "watch-1",
                            "desc": "一只表如何变成纪念物",
                            "author": {
                                "sec_uid": "watch-account",
                                "nickname": "大能",
                            },
                            "statistics": {
                                "digg_count": 88,
                                "comment_count": 7,
                            },
                        },
                        {
                            "aweme_id": "recommended-1",
                            "desc": "页面推荐作品",
                            "author": {
                                "sec_uid": "another-account",
                                "nickname": "其他人",
                            },
                        },
                    ],
                },
            ),
        )
    )

    snapshot = await collect_browser_benchmark_account(
        DouyinBrowserAccountRequest(
            requested_url="https://www.douyin.com/user/watch-account?from=share",
            max_posts=12,
        ),
        runner=runner,
        storage_state=_storage_state(),
    )

    assert runner.calls == [
        {
            "url": "https://www.douyin.com/user/watch-account",
            "target": BrowserTarget.ACCOUNT_POSTS,
            "page_size": 12,
            "storage_state": _storage_state(),
        }
    ]
    assert snapshot.profile.external_account_id == "watch-account"
    assert snapshot.profile.display_name == "大能"
    assert snapshot.profile.public_metrics == {"followers": 9_000_000}
    assert snapshot.profile.visible_post_count == 572
    assert [post.external_post_id for post in snapshot.posts] == ["watch-1"]
    assert snapshot.posts[0].author_external_account_id == "watch-account"
    assert snapshot.coverage.excluded_count == 1
    assert snapshot.route_receipt.adapter == "douyin.browser.network_capture"
    assert "recommended-1" not in snapshot.model_dump_json()
    assert COOKIE_SECRET not in snapshot.model_dump_json()


@pytest.mark.asyncio
async def test_login_page_fails_with_stable_non_secret_error() -> None:
    runner = _Runner(
        BrowserCapture(
            captured_at=NOW,
            final_url="https://www.douyin.com/login",
            page_state=BrowserPageState.NEEDS_LOGIN,
        )
    )

    with pytest.raises(DouyinBrowserUnavailable, match="login_required"):
        await collect_browser_benchmark_candidate(
            BenchmarkCandidateRequest(
                query="大能 腕表",
                actor_label="大能",
                max_posts=12,
            ),
            runner=runner,
            storage_state=_storage_state(),
        )


@pytest.mark.asyncio
async def test_no_exact_actor_match_returns_a_bounded_warning_instead_of_crashing() -> None:
    runner = _Runner(
        BrowserCapture(
            captured_at=NOW,
            final_url="https://www.douyin.com/search/watch?type=video",
            page_state=BrowserPageState.READY,
            response_payloads=({"data": []},),
        )
    )

    snapshot = await collect_browser_benchmark_candidate(
        BenchmarkCandidateRequest(
            query="大能 腕表",
            actor_label="大能",
            max_posts=12,
        ),
        runner=runner,
        storage_state=_storage_state(),
    )

    assert snapshot.items == ()
    assert snapshot.warnings == ("No exact actor display-name match appeared in the bounded browser response.",)


@pytest.mark.asyncio
async def test_ready_page_without_a_search_response_is_not_reported_as_success() -> None:
    runner = _Runner(
        BrowserCapture(
            captured_at=NOW,
            final_url="https://www.douyin.com/jingxuan/search/watch",
            page_state=BrowserPageState.READY,
        )
    )

    with pytest.raises(DouyinBrowserUnavailable, match="search_response_not_observed"):
        await collect_browser_benchmark_candidate(
            BenchmarkCandidateRequest(
                query="大能 腕表",
                actor_label="大能",
                max_posts=12,
            ),
            runner=runner,
            storage_state=_storage_state(),
        )
