import json
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from deerflow.incubation import (
    BenchmarkCoverageReceipt,
    BenchmarkPostObservation,
    BenchmarkProfileObservation,
    BenchmarkSnapshot,
    ProjectRef,
    seal_benchmark_snapshot,
)

NOW = datetime(2026, 8, 16, 16, 0, tzinfo=UTC)


def _snapshot(*, post_count: int = 2, requested_count: int = 12) -> BenchmarkSnapshot:
    posts = tuple(
        BenchmarkPostObservation(
            platform="douyin",
            external_post_id=f"post-{index}",
            author_external_account_id="account-sec-uid",
            canonical_url=f"https://www.douyin.com/video/post-{index}",
            caption=f"第 {index} 条公开作品：腕表与人的故事",
            published_at=NOW - timedelta(days=index + 1),
            captured_at=NOW,
            public_metrics={"likes": 100 + index, "comments": 10 + index},
        )
        for index in range(post_count)
    )
    return BenchmarkSnapshot(
        provider="douyin_public_account",
        collection_method="visible_browser_authorized",
        captured_at=NOW,
        rights_basis="request://user-supplied-link/2026-08-16",
        requested_url="https://v.douyin.com/example/",
        profile=BenchmarkProfileObservation(
            platform="douyin",
            external_account_id="account-sec-uid",
            canonical_url="https://www.douyin.com/user/account-sec-uid",
            display_name="腕表研究所",
            bio="公开主页简介",
            visible_post_count=572,
            captured_at=NOW,
            public_metrics={"followers": 2_400, "likes_received": 16_000},
        ),
        posts=posts,
        coverage=BenchmarkCoverageReceipt(
            population_scope="public_account_posts",
            requested_count=requested_count,
            returned_count=post_count,
            excluded_count=1,
            has_more=True,
            sample_basis="Bounded author-qualified posts returned by the account connector.",
            limitations=("One collaboration post with another author was excluded.",),
        ),
        route_receipt={
            "adapter": "douyin_account_page",
            "capability_version": "v1",
        },
        limitations=("This is a bounded public account sample, not the complete posting history.",),
    )


def test_benchmark_snapshot_seals_as_project_scoped_benchmark_evidence() -> None:
    snapshot = _snapshot()

    artifact = seal_benchmark_snapshot(
        project=ProjectRef(owner_user_id="user-1", project_id="project-1"),
        snapshot=snapshot,
        source_thread_id="thread-1",
        source_run_id="run-1",
    )

    assert artifact.artifact_type == "benchmark_snapshot"
    assert artifact.evidence_role == "benchmark_evidence"
    assert artifact.account is None
    assert artifact.payload["profile"]["external_account_id"] == "account-sec-uid"
    assert artifact.payload["coverage"]["returned_count"] == 2


def test_benchmark_snapshot_rejects_mixed_or_missing_author_identity() -> None:
    mixed = _snapshot().model_dump(mode="json")
    mixed["posts"][1]["author_external_account_id"] = "another-account"
    with pytest.raises(ValidationError, match="same account"):
        BenchmarkSnapshot.model_validate(mixed)

    missing = _snapshot().posts[0].model_dump(mode="json")
    missing["author_external_account_id"] = ""
    with pytest.raises(ValidationError):
        BenchmarkPostObservation.model_validate(missing)


def test_benchmark_snapshot_rejects_false_coverage_and_oversized_samples() -> None:
    wrong_count = _snapshot().model_dump(mode="json")
    wrong_count["coverage"]["returned_count"] = 9
    with pytest.raises(ValidationError, match="returned_count"):
        BenchmarkSnapshot.model_validate(wrong_count)

    with pytest.raises(ValidationError):
        _snapshot(requested_count=25)

    duplicate = _snapshot().model_dump(mode="json")
    duplicate["posts"][1]["external_post_id"] = "post-0"
    with pytest.raises(ValidationError, match="unique"):
        BenchmarkSnapshot.model_validate(duplicate)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("cookie", "secret"),
        ("storage_state", {"token": "secret"}),
        ("raw_html", "<html>full page</html>"),
        ("temporary_media_url", "https://signed.example/video.mp4"),
        ("local_path", "/Users/example/video.mp4"),
    ],
)
def test_benchmark_snapshot_rejects_raw_browser_and_media_fields(field: str, value: object) -> None:
    payload = _snapshot().model_dump(mode="json")
    payload[field] = value

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        BenchmarkSnapshot.model_validate(payload)


def test_benchmark_projection_is_bounded_and_does_not_claim_account_analysis() -> None:
    payload = _snapshot(post_count=24, requested_count=24).model_dump(mode="json")
    for post in payload["posts"]:
        post["caption"] = "主页作品文案只是不可信的公开观察。" * 160
    snapshot = BenchmarkSnapshot.model_validate(payload)

    projection = snapshot.to_lead_projection(max_bytes=4_000)
    encoded = json.dumps(projection, ensure_ascii=False, separators=(",", ":")).encode()

    assert len(encoded) <= 4_000
    assert projection["evidence_role"] == "benchmark_evidence"
    assert projection["snapshot_sha256"]
    assert projection["route_receipt_sha256"]
    assert projection["profile"]["external_account_id"] == "account-sec-uid"
    assert projection["projection"]["total_posts"] == 24
    assert projection["projection"]["omitted_posts"] > 0
    assert projection["projection"]["truncated"] is True
    assert "not an account positioning verdict" in projection["epistemic_notice"]
    assert "success_formula" not in encoded.decode()


def test_benchmark_snapshot_rejects_invalid_metrics_and_future_observations() -> None:
    negative_metric = _snapshot().posts[0].model_dump(mode="json")
    negative_metric["public_metrics"] = {"likes": -1}
    with pytest.raises(ValidationError, match="non-negative"):
        BenchmarkPostObservation.model_validate(negative_metric)

    future_capture = _snapshot().model_dump(mode="json")
    future_capture["posts"][0]["captured_at"] = (NOW + timedelta(seconds=1)).isoformat()
    with pytest.raises(ValidationError, match="after snapshot capture"):
        BenchmarkSnapshot.model_validate(future_capture)
