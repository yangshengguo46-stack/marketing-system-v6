from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from deerflow.community.tiktok_benchmark import (
    PlaywrightTikTokBenchmarkRunner,
    TikTokAccountCandidateCapture,
    TikTokBenchmarkCapture,
    TikTokBenchmarkNeedsLogin,
    TikTokBenchmarkRequest,
    TikTokBenchmarkUnavailable,
    TikTokPostCapture,
    discover_tiktok_benchmark_candidates,
)

NOW = datetime(2026, 8, 20, 9, 0, tzinfo=UTC)


class _Runner:
    def __init__(self, capture: TikTokBenchmarkCapture | Exception) -> None:
        self._capture = capture
        self.calls: list[dict[str, object]] = []

    async def capture(self, **kwargs: object) -> TikTokBenchmarkCapture:
        self.calls.append(kwargs)
        if isinstance(self._capture, Exception):
            raise self._capture
        return self._capture


def _capture(
    *,
    authenticated: bool = True,
    login_required: bool = False,
    search_observed: bool = True,
    accounts: tuple[TikTokAccountCandidateCapture, ...] = (),
    posts: tuple[TikTokPostCapture, ...] = (),
) -> TikTokBenchmarkCapture:
    return TikTokBenchmarkCapture(
        captured_at=NOW,
        final_url="https://www.tiktok.com/search/video?q=TikTok%20LIVE%20MENA",
        authenticated=authenticated,
        login_required=login_required,
        search_observed=search_observed,
        account_candidates=accounts,
        posts=posts,
    )


def _post(
    post_id: str,
    *,
    account_id: str | None = None,
    username: str | None = None,
    display_name: str | None = None,
    caption: str | None = None,
    views: int = 100,
) -> TikTokPostCapture:
    author = username or "unknown"
    return TikTokPostCapture(
        observed_post_id=post_id,
        observed_account_id=account_id,
        author_username=username,
        author_display_name=display_name,
        caption=caption or f"Public post {post_id}",
        public_uri=f"https://www.tiktok.com/@{author}/video/{post_id}",
        published_at=NOW,
        public_metrics={"views": views, "likes": 10},
    )


def test_request_bounds_are_explicit() -> None:
    request = TikTokBenchmarkRequest(
        query="TikTok LIVE agency MENA",
        max_accounts=8,
        representative_posts_per_account=6,
    )

    assert request.max_accounts == 8
    assert request.representative_posts_per_account == 6

    with pytest.raises(ValidationError):
        TikTokBenchmarkRequest(query="TikTok LIVE", max_accounts=0)
    with pytest.raises(ValidationError):
        TikTokBenchmarkRequest(query="TikTok LIVE", max_accounts=9)
    with pytest.raises(ValidationError):
        TikTokBenchmarkRequest(
            query="TikTok LIVE",
            representative_posts_per_account=0,
        )
    with pytest.raises(ValidationError):
        TikTokBenchmarkRequest(
            query="TikTok LIVE",
            representative_posts_per_account=7,
        )


@pytest.mark.asyncio
async def test_discovery_prefers_observed_ids_then_normalized_usernames_and_bounds_posts() -> None:
    runner = _Runner(
        _capture(
            accounts=(
                TikTokAccountCandidateCapture(
                    observed_account_id="stable-1",
                    username="MenaAgency",
                    display_name="MENA Agency",
                ),
                TikTokAccountCandidateCapture(
                    username="CreatorHub",
                    display_name="Creator Hub",
                ),
                TikTokAccountCandidateCapture(display_name="ＣＣＡ　Live"),
            ),
            posts=(
                _post(
                    "101",
                    account_id="stable-1",
                    username="menaagency",
                    display_name="MENA Agency",
                ),
                _post(
                    "102",
                    account_id="stable-1",
                    username="MenaAgency",
                    display_name="MENA Agency",
                ),
                _post(
                    "103",
                    account_id="stable-1",
                    username="MENAAGENCY",
                    display_name="MENA Agency",
                ),
                _post("201", username="creatorhub", display_name="Creator Hub"),
                _post("202", username="＠CreatorHub", display_name="Creator Hub"),
                _post("301", display_name="CCA Live"),
                _post(
                    "101",
                    account_id="stable-1",
                    username="MenaAgency",
                    display_name="MENA Agency",
                    views=999_999,
                ),
            ),
        )
    )

    snapshot = await discover_tiktok_benchmark_candidates(
        TikTokBenchmarkRequest(
            query="TikTok LIVE agency MENA",
            max_accounts=2,
            representative_posts_per_account=2,
        ),
        runner=runner,
    )

    assert runner.calls == [
        {
            "query": "TikTok LIVE agency MENA",
            "max_accounts": 2,
            "representative_posts_per_account": 2,
        }
    ]
    assert snapshot.evidence_role == "benchmark_account_candidate"
    assert snapshot.provider == "tiktok_authenticated_browser"
    assert snapshot.collection_method == "authenticated_browser_hydration_json"
    assert [item.source_ref for item in snapshot.items] == [
        "tiktok:video:101",
        "tiktok:video:102",
        "tiktok:video:201",
        "tiktok:video:202",
    ]
    assert {item.actor_label for item in snapshot.items} == {
        "MENA Agency",
        "Creator Hub",
    }
    assert snapshot.coverage.requested_count == 4
    assert snapshot.coverage.returned_count == 4
    assert snapshot.coverage.duplicate_count == 1
    assert snapshot.coverage.excluded_count == 2
    assert snapshot.coverage.has_more is True
    assert snapshot.route_receipt["target_identity_status"] == ("mixed_observed_id_and_normalized_username_candidates")
    assert snapshot.route_receipt["candidate_summaries"] == [
        {
            "identity_basis": "observed_account_id",
            "observed_account_id": "stable-1",
            "username": "MenaAgency",
            "display_name": "MENA Agency",
            "sample_count": 2,
            "observed_distinct_post_count": 3,
        },
        {
            "identity_basis": "normalized_username",
            "username": "CreatorHub",
            "display_name": "Creator Hub",
            "sample_count": 2,
            "observed_distinct_post_count": 2,
        },
    ]
    assert snapshot.route_receipt["authenticated"] is True
    assert snapshot.route_receipt["login_required"] is False
    assert snapshot.route_receipt["final_url"].startswith("https://www.tiktok.com/")
    assert "BenchmarkSnapshot" in " ".join(snapshot.limitations)


@pytest.mark.asyncio
async def test_normalized_display_name_is_the_last_identity_fallback() -> None:
    runner = _Runner(
        _capture(
            accounts=(TikTokAccountCandidateCapture(display_name="ＣＣＡ　Live"),),
            posts=(
                _post("301", display_name="CCA Live"),
                _post("302", display_name="ＣＣＡLive"),
            ),
        )
    )

    snapshot = await discover_tiktok_benchmark_candidates(
        TikTokBenchmarkRequest(query="CCA LIVE guild", max_accounts=1),
        runner=runner,
    )

    assert [item.source_ref for item in snapshot.items] == [
        "tiktok:video:301",
        "tiktok:video:302",
    ]
    assert snapshot.route_receipt["target_identity_status"] == ("normalized_username_or_display_name_candidates")
    assert snapshot.route_receipt["candidate_summaries"][0]["identity_basis"] == ("normalized_display_name")


@pytest.mark.asyncio
async def test_login_required_has_a_dedicated_fail_closed_exception() -> None:
    runner = _Runner(
        _capture(
            authenticated=False,
            login_required=True,
            search_observed=False,
        )
    )

    with pytest.raises(TikTokBenchmarkNeedsLogin, match="login_required"):
        await discover_tiktok_benchmark_candidates(
            TikTokBenchmarkRequest(query="TikTok LIVE MENA"),
            runner=runner,
        )


@pytest.mark.asyncio
async def test_missing_local_storage_state_maps_to_needs_login(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TIKTOK_BROWSER_STORAGE_STATE_PATH", raising=False)
    runner = PlaywrightTikTokBenchmarkRunner()

    assert runner.headless is False
    with pytest.raises(TikTokBenchmarkNeedsLogin, match="storage_state_not_configured"):
        await discover_tiktok_benchmark_candidates(
            TikTokBenchmarkRequest(query="TikTok LIVE MENA"),
            runner=runner,
        )


@pytest.mark.asyncio
async def test_platform_block_and_missing_structured_capture_are_unavailable() -> None:
    with pytest.raises(TikTokBenchmarkUnavailable, match="platform_blocked"):
        await discover_tiktok_benchmark_candidates(
            TikTokBenchmarkRequest(query="TikTok LIVE MENA"),
            runner=_Runner(TikTokBenchmarkUnavailable("platform_blocked")),
        )

    with pytest.raises(
        TikTokBenchmarkUnavailable,
        match="structured_search_not_observed",
    ):
        await discover_tiktok_benchmark_candidates(
            TikTokBenchmarkRequest(query="TikTok LIVE MENA"),
            runner=_Runner(_capture(search_observed=False)),
        )


@pytest.mark.asyncio
async def test_unknown_runner_errors_are_redacted_and_not_empty_successes() -> None:
    runner = _Runner(RuntimeError("browser failed cookie=secret-value storage_state=/private/file"))

    with pytest.raises(TikTokBenchmarkUnavailable) as exc_info:
        await discover_tiktok_benchmark_candidates(
            TikTokBenchmarkRequest(query="TikTok LIVE MENA"),
            runner=runner,
        )

    assert str(exc_info.value) == "runner_failed"
    assert "secret-value" not in str(exc_info.value)
    assert "/private/file" not in str(exc_info.value)


@pytest.mark.asyncio
async def test_runner_must_return_the_whitelisted_capture_contract() -> None:
    class _InvalidRunner:
        async def capture(self, **kwargs: object) -> object:
            del kwargs
            return {
                "authenticated": True,
                "login_required": False,
                "cookies": [{"name": "sessionid", "value": "secret-value"}],
            }

    with pytest.raises(TikTokBenchmarkUnavailable) as exc_info:
        await discover_tiktok_benchmark_candidates(
            TikTokBenchmarkRequest(query="TikTok LIVE MENA"),
            runner=_InvalidRunner(),  # type: ignore[arg-type]
        )

    assert str(exc_info.value) == "invalid_capture"
    assert "secret-value" not in str(exc_info.value)


@pytest.mark.asyncio
async def test_authenticated_observed_empty_search_is_explicitly_bounded() -> None:
    snapshot = await discover_tiktok_benchmark_candidates(
        TikTokBenchmarkRequest(query="no matching creator"),
        runner=_Runner(_capture()),
    )

    assert snapshot.items == ()
    assert snapshot.coverage.returned_count == 0
    assert snapshot.warnings == ("The authenticated bounded search returned no structured account candidates or posts.",)


def test_capture_contract_rejects_credentials_raw_dom_and_foreign_hosts() -> None:
    payload = _capture().model_dump(mode="python")
    payload["cookies"] = [{"name": "sessionid", "value": "secret-value"}]
    with pytest.raises(ValidationError):
        TikTokBenchmarkCapture.model_validate(payload)

    payload = _capture().model_dump(mode="python")
    payload["raw_dom"] = "<html>secret-value</html>"
    with pytest.raises(ValidationError):
        TikTokBenchmarkCapture.model_validate(payload)

    with pytest.raises(ValidationError, match="tiktok.com"):
        TikTokBenchmarkCapture(
            captured_at=NOW,
            final_url="https://example.com/search/video",
            authenticated=True,
            login_required=False,
            search_observed=True,
        )
