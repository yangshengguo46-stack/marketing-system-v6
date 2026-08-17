from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from deerflow.incubation.audience_intelligence import (
    HLLM_ADAPTER_VERSION,
    HLLM_UPSTREAM_COMMIT,
    AudienceEvidenceArtifact,
    HLLMBehaviorEvent,
    HLLMBehaviorSequence,
    HLLMInferenceReceipt,
    ObservedAudienceBehaviorBatch,
    ObservedAudienceProfile,
    ObservedAudienceSlice,
    build_hllm_inference_request,
    pseudonymize_audience_actor,
    seal_observed_audience_behavior_evidence,
    seal_observed_audience_evidence,
)
from deerflow.incubation.contracts import PlatformAccountRef, ProjectRef
from deerflow.incubation.evidence import EvidenceSnapshot
from deerflow.incubation.project_evidence import select_project_judgment_evidence

NOW = datetime(2026, 8, 18, 10, 0, tzinfo=UTC)
PROJECT = ProjectRef(owner_user_id="user-1", project_id="project-1")
OTHER_PROJECT = ProjectRef(owner_user_id="user-2", project_id="project-2")
OWNED_ACCOUNT = PlatformAccountRef(
    owner_user_id="user-1",
    project_id="project-1",
    account_id="account-1",
    platform="douyin",
)
ACTOR_REF = pseudonymize_audience_actor(
    raw_actor_id="platform-user-1",
    project=PROJECT,
    platform="douyin",
    account_id="account-1",
    secret=b"test-only-project-secret-that-is-at-least-32-bytes",
)
CHECKPOINT_SHA256 = "b" * 64


def _slices(count: int = 1) -> tuple[ObservedAudienceSlice, ...]:
    return tuple(
        ObservedAudienceSlice(
            source_ref=f"support-{index}",
            dimension="interest",
            label=f"interest-{index}",
            value=round((index + 1) / (count + 1), 6),
            value_kind="ratio",
        )
        for index in range(count)
    )


def _observed_profile(
    *,
    evidence_role: str = "owned_audience_observation",
    population_scope: str = "content_engagers",
    subject_relationship: str = "owned_or_client_account",
    subject_account_id: str = "account-1",
    slices: tuple[ObservedAudienceSlice, ...] | None = None,
) -> ObservedAudienceProfile:
    return ObservedAudienceProfile(
        provider="douyin_open_platform",
        collection_method="authorized_official_profile",
        source_authority="official_platform",
        access_mode="account_authorized",
        evidence_role=evidence_role,
        platform="douyin",
        subject_account_id=subject_account_id,
        subject_relationship=subject_relationship,
        population_scope=population_scope,
        status="observed",
        profile_scope="platform_observed_audience",
        captured_at=NOW,
        rights_basis="account-owner-authorization",
        slices=slices or _slices(),
        requested_count=len(slices or _slices()),
        limitations=("The bounded official profile does not represent every audience member.",),
    )


def _seal_observed(
    *,
    profile: ObservedAudienceProfile | None = None,
    project: ProjectRef = PROJECT,
    account: PlatformAccountRef | None = OWNED_ACCOUNT,
) -> AudienceEvidenceArtifact:
    return seal_observed_audience_evidence(
        project=project,
        profile=profile or _observed_profile(),
        source_thread_id="thread-1",
        source_run_id="run-1",
        account=account,
    )


def _event(
    index: int,
    *,
    population_scope: str = "content_engagers",
    platform: str = "douyin",
    account_id: str = "account-1",
    actor_ref: str = ACTOR_REF,
) -> HLLMBehaviorEvent:
    occurred_at = NOW + timedelta(minutes=index)
    return HLLMBehaviorEvent(
        event_id=f"event-{index}",
        platform=platform,
        account_id=account_id,
        actor_ref=actor_ref,
        population_scope=population_scope,
        action="comment",
        item_id=f"post-{index}",
        item_text=f"content-{index}",
        interaction_text=f"comment-{index}",
        occurred_at=occurred_at,
        captured_at=occurred_at + timedelta(seconds=5),
        support_ref=f"support-{index}",
    )


def _behavior_batch(
    *,
    event_count: int = 1,
    events: tuple[HLLMBehaviorEvent, ...] | None = None,
    evidence_role: str = "owned_audience_observation",
    population_scope: str = "content_engagers",
    subject_relationship: str = "owned_or_client_account",
    subject_account_id: str = "account-1",
) -> ObservedAudienceBehaviorBatch:
    behavior_events = events or tuple(_event(index, population_scope=population_scope) for index in range(event_count))
    return ObservedAudienceBehaviorBatch(
        provider="douyin_open_platform",
        collection_method="authorized_audience_interactions",
        source_authority="official_platform",
        access_mode="account_authorized",
        evidence_role=evidence_role,
        platform="douyin",
        subject_account_id=subject_account_id,
        subject_relationship=subject_relationship,
        population_scope=population_scope,
        status="observed",
        captured_at=max(event.captured_at for event in behavior_events),
        rights_basis="account-owner-authorization",
        events=behavior_events,
        requested_count=len(behavior_events),
        limitations=("Only bounded, pseudonymous audience behavior is represented.",),
    )


def _seal_behavior(
    *,
    batch: ObservedAudienceBehaviorBatch | None = None,
    project: ProjectRef = PROJECT,
    account: PlatformAccountRef | None = OWNED_ACCOUNT,
) -> AudienceEvidenceArtifact:
    return seal_observed_audience_behavior_evidence(
        project=project,
        batch=batch or _behavior_batch(),
        source_thread_id="thread-1",
        source_run_id="run-behavior-1",
        account=account,
    )


def _sequence(
    *,
    event_count: int = 1,
    population_scope: str = "content_engagers",
    basis: str = "audience_interaction_sequence",
) -> HLLMBehaviorSequence:
    return HLLMBehaviorSequence(
        sequence_id="sequence-1",
        platform="douyin",
        account_id="account-1",
        actor_ref=ACTOR_REF,
        population_scope=population_scope,
        basis=basis,
        events=tuple(_event(index, population_scope=population_scope) for index in range(event_count)),
        limitations=("Only the bounded, pseudonymous behavior sequence is represented.",),
    )


def _request(
    *,
    source: AudienceEvidenceArtifact | None = None,
    sequence: HLLMBehaviorSequence | None = None,
):
    source = source or _seal_behavior()
    return build_hllm_inference_request(
        project=PROJECT,
        source_artifact=source,
        sequence=sequence or _sequence(),
    )


@pytest.mark.parametrize(
    "population_scope",
    [
        "followers",
        "content_viewers",
        "content_engagers",
        "live_viewers",
        "purchasers",
    ],
)
def test_observed_profile_preserves_each_population_scope_and_enters_a68(
    population_scope: str,
) -> None:
    artifact = _seal_observed(
        profile=_observed_profile(population_scope=population_scope),
    )
    snapshot = EvidenceSnapshot.model_validate(artifact.payload)

    assert snapshot.coverage.population_scope == population_scope
    assert all(item.provenance == "observed" for item in snapshot.items)
    assert all(item.observed_values["population_scope"] == population_scope for item in snapshot.items)

    selection = select_project_judgment_evidence(
        project=PROJECT,
        artifacts=(artifact,),
    )
    assert tuple(item.artifact_id for item in selection.audience_evidence_artifacts) == (artifact.artifact_id,)


def test_observed_role_and_subject_relationship_cannot_impersonate_each_other() -> None:
    with pytest.raises(ValidationError, match="inference|evidence_role"):
        _observed_profile(evidence_role="owned_audience_inference")

    with pytest.raises(ValidationError, match="relationship"):
        _observed_profile(
            evidence_role="benchmark_audience_observation",
            subject_relationship="owned_or_client_account",
        )

    benchmark = _observed_profile(
        evidence_role="benchmark_audience_observation",
        subject_relationship="benchmark_account",
        subject_account_id="benchmark-1",
    )
    with pytest.raises(ValueError, match="benchmark.*account reference"):
        _seal_observed(profile=benchmark, account=OWNED_ACCOUNT)

    owned = _observed_profile()
    with pytest.raises(ValueError, match="owned.*PlatformAccountRef"):
        _seal_observed(profile=owned, account=None)


def test_benchmark_observation_remains_distinct_and_is_selectable() -> None:
    profile = _observed_profile(
        evidence_role="benchmark_audience_observation",
        subject_relationship="benchmark_account",
        subject_account_id="benchmark-1",
    )
    artifact = _seal_observed(profile=profile, account=None)

    assert artifact.account is None
    assert artifact.evidence_role == "benchmark_audience_observation"
    selection = select_project_judgment_evidence(
        project=PROJECT,
        artifacts=(artifact,),
    )
    assert tuple(item.artifact_id for item in selection.audience_evidence_artifacts) == (artifact.artifact_id,)


def test_behavior_contract_rejects_raw_ids_and_cross_scope_sequences() -> None:
    values = _event(0).model_dump(mode="python")
    values["raw_user_id"] = "raw-platform-user-id"
    with pytest.raises(ValidationError, match="raw_user_id|extra"):
        HLLMBehaviorEvent.model_validate(values)

    with pytest.raises(ValidationError, match="actor_ref"):
        HLLMBehaviorEvent.model_validate({**_event(0).model_dump(mode="python"), "actor_ref": "raw-user-123"})

    with pytest.raises(ValidationError, match="population"):
        HLLMBehaviorSequence(
            sequence_id="mixed-population",
            platform="douyin",
            account_id="account-1",
            actor_ref=ACTOR_REF,
            population_scope="followers",
            basis="follower_behavior_sequence",
            events=(_event(0, population_scope="content_engagers"),),
            limitations=("bounded",),
        )

    with pytest.raises(ValidationError, match="platform"):
        HLLMBehaviorSequence(
            sequence_id="mixed-platform",
            platform="douyin",
            account_id="account-1",
            actor_ref=ACTOR_REF,
            population_scope="content_engagers",
            basis="audience_interaction_sequence",
            events=(_event(0, platform="xiaohongshu"),),
            limitations=("bounded",),
        )


def test_observed_behavior_evidence_is_typed_and_keeps_only_pseudonymous_identity() -> None:
    artifact = _seal_behavior()
    snapshot = EvidenceSnapshot.model_validate(artifact.payload)
    item = snapshot.items[0]

    assert artifact.artifact_type == "audience_behavior_snapshot"
    assert item.source_type == "audience_behavior_event"
    assert item.provenance == "observed"
    assert item.observed_values["actor_ref"] == ACTOR_REF
    assert item.observed_values["platform"] == "douyin"
    assert item.observed_values["account_id"] == "account-1"
    assert item.observed_values["population_scope"] == "content_engagers"
    assert item.observed_values["action"] == "comment"
    assert item.observed_values["item_id"] == "post-0"
    assert item.observed_values["occurred_at"] == NOW.isoformat()
    artifact_json = json.dumps(artifact.model_dump(mode="json"), ensure_ascii=False)
    assert "raw_user_id" not in artifact_json
    assert "comment-0" not in artifact_json
    assert item.observed_values["interaction_text_present"] is True
    assert len(item.observed_values["interaction_text_sha256"]) == 64

    selection = select_project_judgment_evidence(
        project=PROJECT,
        artifacts=(artifact,),
    )
    assert selection.audience_evidence_artifacts == ()
    assert selection.rejected_formal_candidate_count == 0


def test_hllm_request_uses_only_the_latest_fifty_events_and_exact_source_refs() -> None:
    source = _seal_behavior(batch=_behavior_batch(event_count=60))
    request = _request(source=source, sequence=_sequence(event_count=60))

    assert len(request.events) == 50
    assert request.events[0].event_id == "event-10"
    assert request.events[-1].event_id == "event-59"
    assert request.source_artifact_id == source.artifact_id
    assert request.source_artifact_sha256 == source.content_sha256
    assert request.source_evidence_role == "owned_audience_observation"
    assert request.supporting_evidence_refs == tuple(f"support-{index}" for index in range(10, 60))
    request_json = json.dumps(request.model_dump(mode="json"), ensure_ascii=False)
    assert "raw_user_id" not in request_json
    assert "interaction_text" not in request_json
    assert "comment-10" not in request_json
    assert PROJECT.owner_user_id not in request_json
    assert PROJECT.project_id not in request_json

    tampered = request.model_dump(mode="python")
    tampered["input_sha256"] = "0" * 64
    with pytest.raises(ValidationError, match="input hash"):
        type(request).model_validate(tampered)


def test_hllm_request_rejects_aggregate_profile_even_when_support_refs_match() -> None:
    aggregate = _seal_observed()

    with pytest.raises(ValueError, match="audience_behavior_snapshot"):
        build_hllm_inference_request(
            project=PROJECT,
            source_artifact=aggregate,
            sequence=_sequence(),
        )


def test_hllm_rejects_creator_history_proxy_and_wrong_follower_scope() -> None:
    with pytest.raises(ValidationError, match="basis"):
        HLLMBehaviorSequence.model_validate(
            {
                **_sequence().model_dump(mode="python"),
                "basis": "account_content_performance_proxy",
            }
        )

    with pytest.raises(ValidationError, match="followers"):
        _sequence(
            population_scope="content_engagers",
            basis="follower_behavior_sequence",
        )


def test_receipt_rejects_generic_chat_model_fake_commit_and_naive_time() -> None:
    request = _request()
    valid = HLLMInferenceReceipt(
        model_family="bytedance_hllm_creator",
        upstream_commit=HLLM_UPSTREAM_COMMIT,
        adapter_version=HLLM_ADAPTER_VERSION,
        output_kind="user_representation",
        checkpoint_id="hllm-creator-representation-1",
        checkpoint_sha256=CHECKPOINT_SHA256,
        input_sha256=request.input_sha256,
        output_sha256="c" * 64,
        generated_at=NOW + timedelta(hours=2),
    ).model_dump(mode="python")

    for field, value in (
        ("model_family", "generic_chat_model"),
        ("upstream_commit", "0" * 40),
        ("adapter_version", "unverified-adapter"),
        ("output_kind", "natural_language_audience_profile"),
    ):
        with pytest.raises(ValidationError, match=field):
            HLLMInferenceReceipt.model_validate({**valid, field: value})

    with pytest.raises(ValidationError, match="timezone-aware"):
        HLLMInferenceReceipt.model_validate({**valid, "generated_at": datetime(2026, 8, 18, 12, 0)})


def test_actor_pseudonym_is_keyed_and_project_scoped() -> None:
    secret = b"test-only-project-secret-that-is-at-least-32-bytes"
    first = pseudonymize_audience_actor(
        raw_actor_id="platform-user-1",
        project=PROJECT,
        platform="douyin",
        account_id="account-1",
        secret=secret,
    )
    repeated = pseudonymize_audience_actor(
        raw_actor_id="platform-user-1",
        project=PROJECT,
        platform="douyin",
        account_id="account-1",
        secret=secret,
    )
    other_project = pseudonymize_audience_actor(
        raw_actor_id="platform-user-1",
        project=OTHER_PROJECT,
        platform="douyin",
        account_id="account-1",
        secret=secret,
    )

    assert first == repeated
    assert first != other_project
    assert "platform-user-1" not in first
    assert secret.decode() not in first

    with pytest.raises(ValueError, match="at least 32 bytes"):
        pseudonymize_audience_actor(
            raw_actor_id="platform-user-1",
            project=PROJECT,
            platform="douyin",
            account_id="account-1",
            secret=b"too-short",
        )
