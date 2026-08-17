from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from deerflow.incubation.benchmark import (
    BenchmarkCoverageReceipt,
    BenchmarkPostObservation,
    BenchmarkProfileObservation,
    BenchmarkRouteReceipt,
    BenchmarkSnapshot,
    seal_benchmark_snapshot,
)
from deerflow.incubation.contracts import ArtifactEnvelope, ProjectRef
from deerflow.incubation.evidence import (
    EvidenceCoverageReceipt,
    EvidenceItem,
    EvidenceSnapshot,
    seal_evidence_snapshot,
)
from deerflow.incubation.project_evidence import (
    MAX_AUDIENCE_JUDGMENT_EVIDENCE,
    MAX_BENCHMARK_JUDGMENT_EVIDENCE,
    select_project_judgment_evidence,
)

NOW = datetime(2026, 8, 18, 9, 0, tzinfo=UTC)
PROJECT = ProjectRef(owner_user_id="user-1", project_id="project-1")
OTHER_PROJECT = ProjectRef(owner_user_id="user-2", project_id="project-2")


def _benchmark(
    *,
    suffix: str,
    created_at: datetime = NOW,
    project: ProjectRef = PROJECT,
) -> ArtifactEnvelope:
    account_id = f"benchmark-{suffix}"
    snapshot = BenchmarkSnapshot(
        provider="douyin-openapi",
        collection_method="authorized-public-search",
        captured_at=created_at,
        rights_basis="public-account-research",
        requested_url=f"https://www.douyin.com/user/{account_id}",
        profile=BenchmarkProfileObservation(
            platform="douyin",
            external_account_id=account_id,
            canonical_url=f"https://www.douyin.com/user/{account_id}",
            display_name=f"对标账号 {suffix}",
            captured_at=created_at,
        ),
        posts=(
            BenchmarkPostObservation(
                platform="douyin",
                external_post_id=f"post-{suffix}",
                author_external_account_id=account_id,
                canonical_url=f"https://www.douyin.com/video/{suffix}",
                caption=f"对标观察 {suffix}",
                captured_at=created_at,
            ),
        ),
        coverage=BenchmarkCoverageReceipt(
            population_scope="public account posts",
            requested_count=1,
            returned_count=1,
            sample_basis="bounded recent public sample",
            limitations=("不能代表账号全部历史。",),
        ),
        route_receipt=BenchmarkRouteReceipt(
            adapter="douyin-openapi",
            capability_version="v2",
        ),
        limitations=("不能直接证明账号定位、受众或成功原因。",),
    )
    return seal_benchmark_snapshot(
        project=project,
        snapshot=snapshot,
        source_thread_id="thread-1",
        source_run_id="run-1",
    )


def _audience(
    *,
    suffix: str,
    role: str = "owned_audience_observation",
    created_at: datetime = NOW,
    project: ProjectRef = PROJECT,
) -> ArtifactEnvelope:
    snapshot = EvidenceSnapshot(
        provider="authorized-audience-source",
        collection_method="bounded-observation",
        evidence_role=role,
        captured_at=created_at,
        rights_basis="account-owner-authorization",
        items=(
            EvidenceItem(
                source_ref=f"audience-{suffix}",
                source_type="audience_observation",
                title=f"受众观察 {suffix}",
                excerpt=f"受众证据 {suffix}",
                provenance="observed",
            ),
        ),
        coverage=EvidenceCoverageReceipt(
            population_scope="authorized audience sample",
            requested_count=1,
            returned_count=1,
            limitations=("不能代表全部受众。",),
        ),
        limitations=("不能代表全部受众。",),
    )
    return seal_evidence_snapshot(
        project=project,
        snapshot=snapshot,
        source_thread_id="thread-1",
        source_run_id="run-1",
    )


def _other_artifact(
    *,
    artifact_type: str,
    evidence_role: str | None,
    suffix: str,
    project: ProjectRef = PROJECT,
) -> ArtifactEnvelope:
    return ArtifactEnvelope.seal(
        project=project,
        artifact_type=artifact_type,
        version=1,
        payload={"kind": suffix, "text": "不属于正式孵化判断证据。"},
        evidence_role=evidence_role,
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-1",
    )


def test_selects_only_formal_benchmark_and_audience_evidence() -> None:
    benchmark = _benchmark(suffix="formal")
    owned_audience = _audience(suffix="owned")
    benchmark_audience = _audience(
        suffix="benchmark",
        role="benchmark_audience_observation",
    )
    excluded = (
        _other_artifact(
            artifact_type="evidence_snapshot",
            evidence_role="topic_evidence",
            suffix="topic",
        ),
        _other_artifact(
            artifact_type="media_observation",
            evidence_role="user_material",
            suffix="material",
        ),
        _other_artifact(
            artifact_type="browser_snapshot",
            evidence_role=None,
            suffix="browser-raw",
        ),
        _other_artifact(
            artifact_type="content_reading",
            evidence_role=None,
            suffix="reading",
        ),
        _other_artifact(
            artifact_type="evidence_snapshot",
            evidence_role="benchmark_account_candidate",
            suffix="candidate",
        ),
    )

    selected = select_project_judgment_evidence(
        project=PROJECT,
        artifacts=(benchmark, owned_audience, benchmark_audience, *excluded),
    )

    assert selected.benchmark_evidence_artifacts == (benchmark,)
    assert {item.artifact_id for item in selected.audience_evidence_artifacts} == {
        owned_audience.artifact_id,
        benchmark_audience.artifact_id,
    }
    assert selected.missing == ()


def test_rejects_any_cross_project_input_before_selection() -> None:
    with pytest.raises(ValueError, match="same project"):
        select_project_judgment_evidence(
            project=PROJECT,
            artifacts=(
                _benchmark(suffix="formal"),
                _other_artifact(
                    artifact_type="content_reading",
                    evidence_role=None,
                    suffix="foreign",
                    project=OTHER_PROJECT,
                ),
            ),
        )


def test_missing_evidence_is_reported_without_becoming_a_gate() -> None:
    selected = select_project_judgment_evidence(
        project=PROJECT,
        artifacts=(
            _other_artifact(
                artifact_type="content_reading",
                evidence_role=None,
                suffix="reading",
            ),
        ),
    )

    assert selected.benchmark_evidence_artifacts == ()
    assert selected.audience_evidence_artifacts == ()
    assert selected.missing == ("benchmark_evidence", "audience_evidence")
    assert any("proceed" in limitation for limitation in selected.limitations)


def test_excludes_near_misses_that_do_not_satisfy_the_existing_contracts() -> None:
    malformed_benchmark = _other_artifact(
        artifact_type="benchmark_snapshot",
        evidence_role="benchmark_evidence",
        suffix="malformed-benchmark",
    )
    wrong_benchmark_envelope = _other_artifact(
        artifact_type="evidence_snapshot",
        evidence_role="benchmark_evidence",
        suffix="wrong-benchmark-envelope",
    )
    wrong_audience_envelope = _other_artifact(
        artifact_type="browser_snapshot",
        evidence_role="owned_audience_observation",
        suffix="browser-audience",
    )

    selected = select_project_judgment_evidence(
        project=PROJECT,
        artifacts=(
            malformed_benchmark,
            wrong_benchmark_envelope,
            wrong_audience_envelope,
        ),
    )

    assert selected.benchmark_evidence_artifacts == ()
    assert selected.audience_evidence_artifacts == ()
    assert selected.rejected_formal_candidate_count == 3
    assert any("formal evidence contracts" in item for item in selected.limitations)


def test_deduplicates_and_sorts_newest_first_with_a_stable_id_tiebreak() -> None:
    old = _benchmark(suffix="old", created_at=NOW - timedelta(days=2))
    same_time_a = _benchmark(suffix="same-a", created_at=NOW)
    same_time_b = _benchmark(suffix="same-b", created_at=NOW)

    selected_one = select_project_judgment_evidence(
        project=PROJECT,
        artifacts=(old, same_time_b, same_time_a, same_time_b),
    )
    selected_two = select_project_judgment_evidence(
        project=PROJECT,
        artifacts=(same_time_b, old, same_time_b, same_time_a),
    )

    expected_same_time = tuple(sorted((same_time_a, same_time_b), key=lambda item: item.artifact_id))
    expected = expected_same_time[:MAX_BENCHMARK_JUDGMENT_EVIDENCE]
    assert selected_one.benchmark_evidence_artifacts == expected
    assert selected_two.benchmark_evidence_artifacts == expected
    assert selected_one.duplicate_count == 1
    assert selected_two.duplicate_count == 1


def test_applies_hard_caps_and_reports_truncation() -> None:
    benchmarks = tuple(_benchmark(suffix=str(index), created_at=NOW + timedelta(minutes=index)) for index in range(MAX_BENCHMARK_JUDGMENT_EVIDENCE + 2))
    audiences = tuple(_audience(suffix=str(index), created_at=NOW + timedelta(minutes=index)) for index in range(MAX_AUDIENCE_JUDGMENT_EVIDENCE + 2))

    selected = select_project_judgment_evidence(
        project=PROJECT,
        artifacts=(*benchmarks, *audiences),
    )

    assert len(selected.benchmark_evidence_artifacts) == MAX_BENCHMARK_JUDGMENT_EVIDENCE
    assert len(selected.audience_evidence_artifacts) == MAX_AUDIENCE_JUDGMENT_EVIDENCE
    assert selected.truncated_benchmark_count == 2
    assert selected.truncated_audience_count == 2
    assert sum("newest" in item for item in selected.limitations) == 2
