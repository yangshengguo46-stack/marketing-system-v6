from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime
from math import isfinite
from typing import Annotated, Literal

from pydantic import Field, JsonValue, field_validator, model_validator

from deerflow.incubation.contracts import (
    ArtifactEnvelope,
    IncubationContract,
    NonEmptyStr,
    PlatformAccountRef,
    ProjectRef,
)
from deerflow.incubation.evidence import (
    EvidenceCoverageReceipt,
    EvidenceItem,
    EvidenceSnapshot,
)

HLLM_UPSTREAM_COMMIT = "864f17221c04a2d3082d9a072df00616bc7e6dab"
HLLM_ADAPTER_VERSION = "v6-hllm-audience-bridge-v1"
MAX_HLLM_SEQUENCE_EVENTS = 50
_ACTOR_REF_PATTERN = r"^actor://hmac-sha256/[0-9a-f]{64}$"

type AudiencePopulationScope = Literal[
    "followers",
    "content_viewers",
    "content_engagers",
    "live_viewers",
    "purchasers",
]
type ObservedAudienceRole = Literal[
    "owned_audience_observation",
    "benchmark_audience_observation",
]
type AudienceEvidenceRole = ObservedAudienceRole
type AudienceSubjectRelationship = Literal[
    "owned_or_client_account",
    "benchmark_account",
]
type HLLMSequenceBasis = Literal[
    "audience_interaction_sequence",
    "follower_behavior_sequence",
]
type HLLMBehaviorAction = Literal[
    "view",
    "like",
    "comment",
    "reply",
    "share",
    "save",
    "follow",
    "live_enter",
    "live_chat",
    "product_click",
    "add_to_cart",
    "purchase",
]

_OBSERVED_AUDIENCE_ROLES = frozenset(
    {
        "owned_audience_observation",
        "benchmark_audience_observation",
    }
)


def _canonical_sha256(value: JsonValue) -> str:
    canonical = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _aware_utc(value: datetime, *, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


def _unique_in_order(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


def pseudonymize_audience_actor(
    *,
    raw_actor_id: str,
    project: ProjectRef,
    platform: str,
    account_id: str,
    secret: bytes,
) -> str:
    """Create a project/account-scoped actor reference without retaining the raw id."""

    project = ProjectRef.model_validate(project.model_dump(mode="python"))
    raw_actor_id = raw_actor_id.strip()
    platform = platform.strip()
    account_id = account_id.strip()
    if not raw_actor_id or not platform or not account_id:
        raise ValueError("raw actor id, platform, and account id are required")
    if len(secret) < 32:
        raise ValueError("audience pseudonym secret must be at least 32 bytes")
    scoped_value = json.dumps(
        {
            "owner_user_id": project.owner_user_id,
            "project_id": project.project_id,
            "platform": platform,
            "account_id": account_id,
            "raw_actor_id": raw_actor_id,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    digest = hmac.new(secret, scoped_value, hashlib.sha256).hexdigest()
    return f"actor://hmac-sha256/{digest}"


class AudienceEvidenceSnapshot(EvidenceSnapshot):
    """A formal observed audience snapshot accepted by the incubation ledger."""

    evidence_role: AudienceEvidenceRole


class AudienceEvidenceArtifact(ArtifactEnvelope):
    """An observed audience artifact with an explicit population scope."""

    evidence_role: AudienceEvidenceRole


class ObservedAudienceSlice(IncubationContract):
    source_ref: NonEmptyStr = Field(max_length=255)
    dimension: NonEmptyStr = Field(max_length=128)
    label: NonEmptyStr = Field(max_length=255)
    value: int | float | str
    value_kind: Literal["count", "ratio", "index", "category"]

    @model_validator(mode="after")
    def validate_value_semantics(self) -> ObservedAudienceSlice:
        if isinstance(self.value, bool):
            raise ValueError("observed audience values cannot be boolean")
        if self.value_kind == "category":
            if not isinstance(self.value, str):
                raise ValueError("category audience values must be strings")
            return self
        if not isinstance(self.value, (int, float)):
            raise ValueError(f"{self.value_kind} audience values must be numeric")
        if not isfinite(self.value) or self.value < 0:
            raise ValueError("numeric audience values must be finite and non-negative")
        if self.value_kind == "count" and not float(self.value).is_integer():
            raise ValueError("count audience values must be integers")
        if self.value_kind == "ratio" and self.value > 1:
            raise ValueError("ratio audience values cannot exceed 1")
        return self


class ObservedAudienceProfile(IncubationContract):
    schema_version: Literal["v6-observed-audience-profile-v1"] = "v6-observed-audience-profile-v1"
    provider: NonEmptyStr = Field(max_length=128)
    collection_method: NonEmptyStr = Field(max_length=128)
    source_authority: Literal["official_platform"]
    access_mode: Literal[
        "account_authorized",
        "authenticated_research",
        "public_official",
    ]
    evidence_role: ObservedAudienceRole
    platform: NonEmptyStr = Field(max_length=32)
    subject_account_id: NonEmptyStr = Field(max_length=255)
    subject_relationship: AudienceSubjectRelationship
    population_scope: AudiencePopulationScope
    status: Literal["observed"]
    profile_scope: Literal["platform_observed_audience"]
    captured_at: datetime
    rights_basis: NonEmptyStr = Field(max_length=255)
    slices: Annotated[
        tuple[ObservedAudienceSlice, ...],
        Field(min_length=1, max_length=200),
    ]
    requested_count: int = Field(ge=1, le=10_000)
    excluded_count: int = Field(default=0, ge=0)
    duplicate_count: int = Field(default=0, ge=0)
    has_more: bool | None = None
    limitations: Annotated[
        tuple[NonEmptyStr, ...],
        Field(min_length=1, max_length=20),
    ]

    @field_validator("captured_at")
    @classmethod
    def validate_captured_at(cls, value: datetime) -> datetime:
        return _aware_utc(value, field_name="captured_at")

    @model_validator(mode="after")
    def validate_profile_scope(self) -> ObservedAudienceProfile:
        expected_relationship: AudienceSubjectRelationship
        if self.evidence_role == "owned_audience_observation":
            expected_relationship = "owned_or_client_account"
            if self.access_mode != "account_authorized":
                raise ValueError("owned audience observation requires account-authorized access")
        else:
            expected_relationship = "benchmark_account"
        if self.subject_relationship != expected_relationship:
            raise ValueError("audience observation role and subject relationship do not match")
        if self.requested_count < len(self.slices):
            raise ValueError("requested_count cannot be smaller than returned slices")
        source_refs = [item.source_ref for item in self.slices]
        if len(source_refs) != len(set(source_refs)):
            raise ValueError("observed audience slice source refs must be unique")
        slice_keys = [(item.dimension, item.label) for item in self.slices]
        if len(slice_keys) != len(set(slice_keys)):
            raise ValueError("observed audience slices must be unique")
        return self


def _validate_observed_account_binding(
    *,
    project: ProjectRef,
    evidence_role: ObservedAudienceRole,
    platform: str,
    subject_account_id: str,
    account: PlatformAccountRef | None,
) -> None:
    if evidence_role == "owned_audience_observation":
        if account is None:
            raise ValueError("owned audience observation requires a PlatformAccountRef")
        if account.owner_user_id != project.owner_user_id or account.project_id != project.project_id:
            raise ValueError("owned audience account must belong to the same project")
        if account.platform != platform:
            raise ValueError("owned audience account platform does not match profile")
        if account.account_id != subject_account_id:
            raise ValueError("owned audience account id does not match profile subject")
        return
    if account is not None:
        raise ValueError("benchmark audience observation cannot carry a client account reference")


def seal_observed_audience_evidence(
    *,
    project: ProjectRef,
    profile: ObservedAudienceProfile,
    source_thread_id: str,
    source_run_id: str,
    account: PlatformAccountRef | None = None,
) -> AudienceEvidenceArtifact:
    """Seal one official observed profile without changing its population."""

    project = ProjectRef.model_validate(project.model_dump(mode="python"))
    profile = ObservedAudienceProfile.model_validate(profile.model_dump(mode="python"))
    if account is not None:
        account = PlatformAccountRef.model_validate(account.model_dump(mode="python"))
    _validate_observed_account_binding(
        project=project,
        evidence_role=profile.evidence_role,
        platform=profile.platform,
        subject_account_id=profile.subject_account_id,
        account=account,
    )

    items = tuple(
        EvidenceItem(
            source_ref=slice_.source_ref,
            source_type="official_audience_profile_slice",
            title=f"{slice_.dimension}: {slice_.label}",
            excerpt=(f"Official observed {profile.population_scope} slice {slice_.dimension}/{slice_.label}={slice_.value}."),
            provenance="observed",
            observed_values={
                "status": "observed",
                "profile_scope": profile.profile_scope,
                "population_scope": profile.population_scope,
                "platform": profile.platform,
                "subject_account_id": profile.subject_account_id,
                "subject_relationship": profile.subject_relationship,
                "dimension": slice_.dimension,
                "label": slice_.label,
                "value": slice_.value,
                "value_kind": slice_.value_kind,
            },
        )
        for slice_ in profile.slices
    )
    snapshot = AudienceEvidenceSnapshot(
        provider=profile.provider,
        collection_method=profile.collection_method,
        evidence_role=profile.evidence_role,
        captured_at=profile.captured_at,
        rights_basis=profile.rights_basis,
        items=items,
        coverage=EvidenceCoverageReceipt(
            population_scope=profile.population_scope,
            requested_count=profile.requested_count,
            returned_count=len(items),
            excluded_count=profile.excluded_count,
            duplicate_count=profile.duplicate_count,
            has_more=profile.has_more,
            limitations=profile.limitations,
        ),
        route_receipt={
            "source_authority": profile.source_authority,
            "access_mode": profile.access_mode,
            "platform": profile.platform,
            "subject_account_id": profile.subject_account_id,
            "subject_relationship": profile.subject_relationship,
            "population_scope": profile.population_scope,
            "status": "observed",
        },
        limitations=profile.limitations,
    )
    artifact = AudienceEvidenceArtifact.seal(
        project=project,
        artifact_type="evidence_snapshot",
        version=1,
        payload=snapshot.model_dump(mode="json"),
        account=account,
        evidence_role=profile.evidence_role,
        created_at=profile.captured_at,
        source_thread_id=source_thread_id,
        source_run_id=source_run_id,
    )
    return AudienceEvidenceArtifact.model_validate(artifact.model_dump(mode="python"))


class HLLMBehaviorEvent(IncubationContract):
    event_id: NonEmptyStr = Field(max_length=255)
    platform: NonEmptyStr = Field(max_length=32)
    account_id: NonEmptyStr = Field(max_length=255)
    actor_ref: str = Field(pattern=_ACTOR_REF_PATTERN)
    population_scope: AudiencePopulationScope
    action: HLLMBehaviorAction
    item_id: NonEmptyStr = Field(max_length=255)
    item_text: NonEmptyStr = Field(max_length=4_000)
    interaction_text: NonEmptyStr | None = Field(default=None, max_length=4_000)
    occurred_at: datetime
    captured_at: datetime
    support_ref: NonEmptyStr = Field(max_length=255)

    @field_validator("occurred_at", "captured_at")
    @classmethod
    def validate_times(cls, value: datetime, info) -> datetime:
        return _aware_utc(value, field_name=info.field_name)

    @model_validator(mode="after")
    def validate_event(self) -> HLLMBehaviorEvent:
        if self.captured_at < self.occurred_at:
            raise ValueError("captured_at cannot precede occurred_at")
        if self.action in {"comment", "reply", "live_chat"} and not self.interaction_text:
            raise ValueError("text interactions require interaction_text")
        return self


class HLLMInferenceEvent(IncubationContract):
    """Privacy-safe event projection sent to an external HLLM runtime."""

    event_id: NonEmptyStr = Field(max_length=255)
    platform: NonEmptyStr = Field(max_length=32)
    account_id: NonEmptyStr = Field(max_length=255)
    actor_ref: str = Field(pattern=_ACTOR_REF_PATTERN)
    population_scope: AudiencePopulationScope
    action: HLLMBehaviorAction
    item_id: NonEmptyStr = Field(max_length=255)
    public_item_summary: NonEmptyStr = Field(max_length=4_000)
    occurred_at: datetime
    captured_at: datetime
    support_ref: NonEmptyStr = Field(max_length=255)

    @field_validator("occurred_at", "captured_at")
    @classmethod
    def validate_times(cls, value: datetime, info) -> datetime:
        return _aware_utc(value, field_name=info.field_name)

    @model_validator(mode="after")
    def validate_event(self) -> HLLMInferenceEvent:
        if self.captured_at < self.occurred_at:
            raise ValueError("captured_at cannot precede occurred_at")
        return self

    @classmethod
    def from_observed_event(cls, event: HLLMBehaviorEvent) -> HLLMInferenceEvent:
        """Deliberately omit interaction_text from the external request."""

        event = HLLMBehaviorEvent.model_validate(event.model_dump(mode="python"))
        return cls(
            event_id=event.event_id,
            platform=event.platform,
            account_id=event.account_id,
            actor_ref=event.actor_ref,
            population_scope=event.population_scope,
            action=event.action,
            item_id=event.item_id,
            public_item_summary=event.item_text,
            occurred_at=event.occurred_at,
            captured_at=event.captured_at,
            support_ref=event.support_ref,
        )


class ObservedAudienceBehaviorBatch(IncubationContract):
    """Observed, pseudonymized interactions before any HLLM inference."""

    schema_version: Literal["v6-observed-audience-behavior-v1"] = "v6-observed-audience-behavior-v1"
    provider: NonEmptyStr = Field(max_length=128)
    collection_method: NonEmptyStr = Field(max_length=128)
    source_authority: Literal["official_platform"]
    access_mode: Literal[
        "account_authorized",
        "authenticated_research",
        "public_official",
    ]
    evidence_role: ObservedAudienceRole
    platform: NonEmptyStr = Field(max_length=32)
    subject_account_id: NonEmptyStr = Field(max_length=255)
    subject_relationship: AudienceSubjectRelationship
    population_scope: AudiencePopulationScope
    status: Literal["observed"]
    captured_at: datetime
    rights_basis: NonEmptyStr = Field(max_length=255)
    events: Annotated[
        tuple[HLLMBehaviorEvent, ...],
        Field(min_length=1, max_length=500),
    ]
    requested_count: int = Field(ge=1, le=10_000)
    excluded_count: int = Field(default=0, ge=0)
    duplicate_count: int = Field(default=0, ge=0)
    has_more: bool | None = None
    limitations: Annotated[
        tuple[NonEmptyStr, ...],
        Field(min_length=1, max_length=20),
    ]

    @field_validator("captured_at")
    @classmethod
    def validate_captured_at(cls, value: datetime) -> datetime:
        return _aware_utc(value, field_name="captured_at")

    @model_validator(mode="after")
    def validate_batch(self) -> ObservedAudienceBehaviorBatch:
        expected_relationship: AudienceSubjectRelationship
        if self.evidence_role == "owned_audience_observation":
            expected_relationship = "owned_or_client_account"
            if self.access_mode != "account_authorized":
                raise ValueError("owned audience behavior requires account-authorized access")
        else:
            expected_relationship = "benchmark_account"
        if self.subject_relationship != expected_relationship:
            raise ValueError("audience behavior role and subject relationship do not match")
        if self.requested_count < len(self.events):
            raise ValueError("requested_count cannot be smaller than returned events")
        event_ids = [event.event_id for event in self.events]
        if len(event_ids) != len(set(event_ids)):
            raise ValueError("observed audience behavior event ids must be unique")
        support_refs = [event.support_ref for event in self.events]
        if len(support_refs) != len(set(support_refs)):
            raise ValueError("observed audience behavior support refs must be unique")
        for event in self.events:
            if event.platform != self.platform:
                raise ValueError("observed audience behavior crosses platform")
            if event.account_id != self.subject_account_id:
                raise ValueError("observed audience behavior crosses account")
            if event.population_scope != self.population_scope:
                raise ValueError("observed audience behavior crosses population scope")
            if event.captured_at > self.captured_at:
                raise ValueError("batch captured_at cannot precede an event capture")
        return self


def seal_observed_audience_behavior_evidence(
    *,
    project: ProjectRef,
    batch: ObservedAudienceBehaviorBatch,
    source_thread_id: str,
    source_run_id: str,
    account: PlatformAccountRef | None = None,
) -> AudienceEvidenceArtifact:
    """Seal actor-linked observations separately from aggregate profile slices."""

    project = ProjectRef.model_validate(project.model_dump(mode="python"))
    batch = ObservedAudienceBehaviorBatch.model_validate(batch.model_dump(mode="python"))
    if account is not None:
        account = PlatformAccountRef.model_validate(account.model_dump(mode="python"))
    _validate_observed_account_binding(
        project=project,
        evidence_role=batch.evidence_role,
        platform=batch.platform,
        subject_account_id=batch.subject_account_id,
        account=account,
    )

    items = tuple(
        EvidenceItem(
            source_ref=event.support_ref,
            source_type="audience_behavior_event",
            title=f"Observed pseudonymous audience {event.action}",
            excerpt=(f"Observed {event.population_scope} action {event.action} on item {event.item_id}."),
            provenance="observed",
            observed_values={
                "status": "observed",
                "event_id": event.event_id,
                "actor_ref": event.actor_ref,
                "platform": event.platform,
                "account_id": event.account_id,
                "population_scope": event.population_scope,
                "action": event.action,
                "item_id": event.item_id,
                "item_text": event.item_text,
                "interaction_text_present": event.interaction_text is not None,
                "interaction_text_sha256": (hashlib.sha256(event.interaction_text.encode("utf-8")).hexdigest() if event.interaction_text is not None else None),
                "occurred_at": event.occurred_at.isoformat(),
                "captured_at": event.captured_at.isoformat(),
            },
        )
        for event in batch.events
    )
    snapshot = AudienceEvidenceSnapshot(
        provider=batch.provider,
        collection_method=batch.collection_method,
        evidence_role=batch.evidence_role,
        captured_at=batch.captured_at,
        rights_basis=batch.rights_basis,
        items=items,
        coverage=EvidenceCoverageReceipt(
            population_scope=batch.population_scope,
            requested_count=batch.requested_count,
            returned_count=len(items),
            excluded_count=batch.excluded_count,
            duplicate_count=batch.duplicate_count,
            has_more=batch.has_more,
            limitations=batch.limitations,
        ),
        route_receipt={
            "source_authority": batch.source_authority,
            "access_mode": batch.access_mode,
            "evidence_kind": "audience_behavior_events",
            "platform": batch.platform,
            "subject_account_id": batch.subject_account_id,
            "subject_relationship": batch.subject_relationship,
            "population_scope": batch.population_scope,
            "status": "observed",
        },
        limitations=batch.limitations,
    )
    artifact = AudienceEvidenceArtifact.seal(
        project=project,
        artifact_type="audience_behavior_snapshot",
        version=1,
        payload=snapshot.model_dump(mode="json"),
        account=account,
        evidence_role=batch.evidence_role,
        created_at=batch.captured_at,
        source_thread_id=source_thread_id,
        source_run_id=source_run_id,
    )
    return AudienceEvidenceArtifact.model_validate(artifact.model_dump(mode="python"))


class HLLMBehaviorSequence(IncubationContract):
    sequence_id: NonEmptyStr = Field(max_length=255)
    platform: NonEmptyStr = Field(max_length=32)
    account_id: NonEmptyStr = Field(max_length=255)
    actor_ref: str = Field(pattern=_ACTOR_REF_PATTERN)
    population_scope: AudiencePopulationScope
    basis: HLLMSequenceBasis
    events: Annotated[
        tuple[HLLMBehaviorEvent, ...],
        Field(min_length=1, max_length=500),
    ]
    limitations: Annotated[
        tuple[NonEmptyStr, ...],
        Field(min_length=1, max_length=20),
    ]

    @model_validator(mode="after")
    def validate_sequence(self) -> HLLMBehaviorSequence:
        if self.basis == "follower_behavior_sequence" and self.population_scope != "followers":
            raise ValueError("follower behavior sequence requires followers population")
        event_ids = [event.event_id for event in self.events]
        if len(event_ids) != len(set(event_ids)):
            raise ValueError("HLLM behavior event ids must be unique")
        for event in self.events:
            if event.platform != self.platform:
                raise ValueError("HLLM behavior sequence crosses platform")
            if event.account_id != self.account_id:
                raise ValueError("HLLM behavior sequence crosses account")
            if event.actor_ref != self.actor_ref:
                raise ValueError("HLLM behavior sequence crosses actor")
            if event.population_scope != self.population_scope:
                raise ValueError("HLLM behavior sequence crosses population scope")
        return self


class HLLMInferenceRequest(IncubationContract):
    schema_version: Literal["v6-hllm-audience-request-v1"] = "v6-hllm-audience-request-v1"
    platform: NonEmptyStr = Field(max_length=32)
    account_id: NonEmptyStr = Field(max_length=255)
    actor_ref: str = Field(pattern=_ACTOR_REF_PATTERN)
    population_scope: AudiencePopulationScope
    sequence_id: NonEmptyStr = Field(max_length=255)
    basis: HLLMSequenceBasis
    events: Annotated[
        tuple[HLLMInferenceEvent, ...],
        Field(min_length=1, max_length=MAX_HLLM_SEQUENCE_EVENTS),
    ]
    source_artifact_id: NonEmptyStr = Field(max_length=80)
    source_artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_evidence_role: ObservedAudienceRole
    supporting_evidence_refs: Annotated[
        tuple[NonEmptyStr, ...],
        Field(min_length=1, max_length=MAX_HLLM_SEQUENCE_EVENTS),
    ]
    limitations: Annotated[
        tuple[NonEmptyStr, ...],
        Field(min_length=1, max_length=20),
    ]
    model_family: Literal["bytedance_hllm_creator"] = "bytedance_hllm_creator"
    upstream_commit: Literal["864f17221c04a2d3082d9a072df00616bc7e6dab"] = HLLM_UPSTREAM_COMMIT
    adapter_version: Literal["v6-hllm-audience-bridge-v1"] = HLLM_ADAPTER_VERSION
    input_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_request(self) -> HLLMInferenceRequest:
        if self.basis == "follower_behavior_sequence" and self.population_scope != "followers":
            raise ValueError("follower behavior sequence requires followers population")
        event_ids = [event.event_id for event in self.events]
        if len(event_ids) != len(set(event_ids)):
            raise ValueError("HLLM request event ids must be unique")
        for event in self.events:
            if event.platform != self.platform:
                raise ValueError("HLLM request event crosses platform")
            if event.account_id != self.account_id:
                raise ValueError("HLLM request event crosses account")
            if event.actor_ref != self.actor_ref:
                raise ValueError("HLLM request event crosses actor")
            if event.population_scope != self.population_scope:
                raise ValueError("HLLM request event crosses population scope")
        expected_support_refs = _unique_in_order(tuple(event.support_ref for event in self.events))
        if self.supporting_evidence_refs != expected_support_refs:
            raise ValueError("HLLM request support refs must match its events")
        payload = self.model_dump(mode="json", exclude={"input_sha256"})
        if _canonical_sha256(payload) != self.input_sha256:
            raise ValueError("HLLM request input hash does not match its payload")
        return self


def _validate_observed_source(
    *,
    project: ProjectRef,
    source_artifact: ArtifactEnvelope,
) -> tuple[ArtifactEnvelope, EvidenceSnapshot]:
    source_artifact = ArtifactEnvelope.model_validate(source_artifact.model_dump(mode="python"))
    if source_artifact.project != project:
        raise ValueError("source audience evidence must belong to the same project")
    if source_artifact.artifact_type != "audience_behavior_snapshot":
        raise ValueError("HLLM source artifact must be an audience_behavior_snapshot")
    if source_artifact.evidence_role not in _OBSERVED_AUDIENCE_ROLES:
        raise ValueError("HLLM source artifact must be observed audience evidence")
    source_snapshot = EvidenceSnapshot.model_validate(source_artifact.payload)
    if source_snapshot.evidence_role != source_artifact.evidence_role:
        raise ValueError("source evidence role does not match its artifact envelope")
    if any(item.provenance != "observed" for item in source_snapshot.items):
        raise ValueError("HLLM source audience items must remain observed evidence")
    return source_artifact, source_snapshot


def _validate_behavior_event_supports(
    *,
    source_snapshot: EvidenceSnapshot,
    events: tuple[HLLMInferenceEvent, ...],
) -> None:
    items_by_ref = {item.source_ref: item for item in source_snapshot.items}
    for event in events:
        item = items_by_ref.get(event.support_ref)
        if item is None:
            raise ValueError("HLLM event support ref is missing from source snapshot")
        if item.source_type != "audience_behavior_event":
            raise ValueError("HLLM support must reference an audience_behavior_event, not an aggregate audience profile slice")
        expected_values: dict[str, JsonValue] = {
            "status": "observed",
            "event_id": event.event_id,
            "actor_ref": event.actor_ref,
            "platform": event.platform,
            "account_id": event.account_id,
            "population_scope": event.population_scope,
            "action": event.action,
            "item_id": event.item_id,
            "item_text": event.public_item_summary,
            "occurred_at": event.occurred_at.isoformat(),
            "captured_at": event.captured_at.isoformat(),
        }
        for field_name, expected in expected_values.items():
            if item.observed_values.get(field_name) != expected:
                raise ValueError(f"HLLM behavior event does not match its observed support for {field_name}")


def build_hllm_inference_request(
    *,
    project: ProjectRef,
    source_artifact: ArtifactEnvelope,
    sequence: HLLMBehaviorSequence,
) -> HLLMInferenceRequest:
    """Bind the latest 50 real pseudonymous events to one observed snapshot."""

    project = ProjectRef.model_validate(project.model_dump(mode="python"))
    sequence = HLLMBehaviorSequence.model_validate(sequence.model_dump(mode="python"))
    source_artifact, source_snapshot = _validate_observed_source(
        project=project,
        source_artifact=source_artifact,
    )
    if source_snapshot.coverage.population_scope != sequence.population_scope:
        raise ValueError("source and sequence population scopes do not match")
    if source_snapshot.route_receipt.get("platform") != sequence.platform:
        raise ValueError("source and sequence platforms do not match")
    if source_snapshot.route_receipt.get("subject_account_id") != sequence.account_id:
        raise ValueError("source and sequence accounts do not match")

    ordered_observed_events = sorted(
        sequence.events,
        key=lambda event: (event.occurred_at, event.captured_at, event.event_id),
    )
    observed_events = tuple(ordered_observed_events[-MAX_HLLM_SEQUENCE_EVENTS:])
    events = tuple(HLLMInferenceEvent.from_observed_event(event) for event in observed_events)
    supporting_evidence_refs = _unique_in_order(tuple(event.support_ref for event in events))
    _validate_behavior_event_supports(
        source_snapshot=source_snapshot,
        events=events,
    )

    values = {
        "schema_version": "v6-hllm-audience-request-v1",
        "platform": sequence.platform,
        "account_id": sequence.account_id,
        "actor_ref": sequence.actor_ref,
        "population_scope": sequence.population_scope,
        "sequence_id": sequence.sequence_id,
        "basis": sequence.basis,
        "events": events,
        "source_artifact_id": source_artifact.artifact_id,
        "source_artifact_sha256": source_artifact.content_sha256,
        "source_evidence_role": source_snapshot.evidence_role,
        "supporting_evidence_refs": supporting_evidence_refs,
        "limitations": sequence.limitations,
        "model_family": "bytedance_hllm_creator",
        "upstream_commit": HLLM_UPSTREAM_COMMIT,
        "adapter_version": HLLM_ADAPTER_VERSION,
    }
    draft = HLLMInferenceRequest.model_construct(
        **values,
        input_sha256="0" * 64,
    )
    input_sha256 = _canonical_sha256(draft.model_dump(mode="json", exclude={"input_sha256"}))
    return HLLMInferenceRequest(**values, input_sha256=input_sha256)


class HLLMInferenceReceipt(IncubationContract):
    model_family: Literal["bytedance_hllm_creator"]
    upstream_commit: Literal["864f17221c04a2d3082d9a072df00616bc7e6dab"]
    adapter_version: Literal["v6-hllm-audience-bridge-v1"]
    output_kind: Literal["user_representation", "cluster_assignment"]
    checkpoint_id: NonEmptyStr = Field(max_length=255)
    checkpoint_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    input_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    output_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    generated_at: datetime

    @field_validator("generated_at")
    @classmethod
    def validate_generated_at(cls, value: datetime) -> datetime:
        return _aware_utc(value, field_name="generated_at")


__all__ = [
    "HLLM_ADAPTER_VERSION",
    "HLLM_UPSTREAM_COMMIT",
    "MAX_HLLM_SEQUENCE_EVENTS",
    "AudienceEvidenceArtifact",
    "AudienceEvidenceSnapshot",
    "AudiencePopulationScope",
    "HLLMBehaviorEvent",
    "HLLMBehaviorSequence",
    "HLLMInferenceEvent",
    "HLLMInferenceReceipt",
    "HLLMInferenceRequest",
    "ObservedAudienceBehaviorBatch",
    "ObservedAudienceProfile",
    "ObservedAudienceRole",
    "ObservedAudienceSlice",
    "build_hllm_inference_request",
    "pseudonymize_audience_actor",
    "seal_observed_audience_behavior_evidence",
    "seal_observed_audience_evidence",
]
