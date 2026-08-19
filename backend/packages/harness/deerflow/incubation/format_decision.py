from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator

from deerflow.incubation.contracts import (
    ArtifactEnvelope,
    ArtifactParentRef,
    IncubationContract,
    NonEmptyStr,
    ProjectRef,
)

FormatKind = Literal[
    "spoken_delivery",
    "micro_drama",
    "situational_drama",
    "image_text",
    "material_only",
    "interview",
    "documentary_observation",
    "custom",
]
FormatDecisionStatus = Literal["provisional", "confirmed"]

_NARRATIVE_FORMATS = frozenset({"micro_drama", "situational_drama"})
_CONTENT_SOURCE_LABELS = frozenset(
    {
        "historicalstory",
        "realcase",
        "历史故事",
        "真实案例",
    }
)
_PROTECTED_MESSAGE_PLAN_FIELDS = (
    "topic_title",
    "focal_subject",
    "concrete_event_or_question",
    "point_of_view",
)
_EVIDENCE_BOUNDARY_FIELDS = (
    "evidence_refs",
    "limitations",
    "unknown_refs",
    "research_needed",
)


def _canonical_sha256(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _normalized_label(value: str) -> str:
    return re.sub(r"[\s_-]+", "", value.casefold())


def _canonical_ids(value: tuple[str, ...]) -> tuple[str, ...]:
    if len(set(value)) != len(value):
        raise ValueError("artifact references must be unique")
    return tuple(sorted(value))


class FormatChoice(IncubationContract):
    kind: FormatKind
    custom_name: NonEmptyStr | None = None

    @model_validator(mode="after")
    def validate_custom_form(self) -> FormatChoice:
        if self.kind == "custom":
            if self.custom_name is None:
                raise ValueError("custom form requires custom_name")
            if _normalized_label(self.custom_name) in _CONTENT_SOURCE_LABELS:
                raise ValueError("a content source is not a presentation form")
        elif self.custom_name is not None:
            raise ValueError("custom_name is only valid for a custom form")
        return self


class ResourceMatch(IncubationContract):
    resource: NonEmptyStr
    fit: NonEmptyStr
    basis_artifact_ids: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1)]

    @field_validator("basis_artifact_ids")
    @classmethod
    def canonicalize_basis_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _canonical_ids(value)


class FormatAlternative(IncubationContract):
    format: FormatChoice
    rationale: NonEmptyStr
    tradeoffs: tuple[NonEmptyStr, ...] = ()


class MessagePlanBinding(IncubationContract):
    artifact_id: NonEmptyStr
    artifact_content_sha256: NonEmptyStr
    message_plan_id: NonEmptyStr
    record_id: NonEmptyStr
    protected_content_sha256: NonEmptyStr
    evidence_boundary_sha256: NonEmptyStr

    @field_validator(
        "artifact_content_sha256",
        "protected_content_sha256",
        "evidence_boundary_sha256",
    )
    @classmethod
    def validate_sha256(cls, value: str) -> str:
        if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
            raise ValueError("message plan binding hashes must be lowercase SHA-256")
        return value


class BaseDraftBinding(IncubationContract):
    artifact_id: NonEmptyStr
    artifact_content_sha256: NonEmptyStr
    draft_id: NonEmptyStr
    message_plan_id: NonEmptyStr
    stage: Literal["base"]
    body_sha256: NonEmptyStr

    @field_validator("artifact_content_sha256", "body_sha256")
    @classmethod
    def validate_sha256(cls, value: str) -> str:
        if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
            raise ValueError("base draft binding hashes must be lowercase SHA-256")
        return value


class FormatDecisionDraft(IncubationContract):
    """A format-only proposal with no fields that can rewrite the selected topic."""

    status: FormatDecisionStatus = "provisional"
    selected_format: FormatChoice
    selection_rationale: NonEmptyStr
    resource_matches: tuple[ResourceMatch, ...] = ()
    resource_gaps: tuple[NonEmptyStr, ...] = ()
    sustainability_risks: tuple[NonEmptyStr, ...] = ()
    alternatives: tuple[FormatAlternative, ...] = ()
    unknowns: tuple[NonEmptyStr, ...] = ()
    narrative_method_hint: NonEmptyStr | None = None

    @field_validator("narrative_method_hint", mode="before")
    @classmethod
    def normalize_explicit_json_null_literal(cls, value: object) -> object:
        if isinstance(value, str) and value.strip() == "null":
            return None
        return value

    @model_validator(mode="after")
    def keep_narrative_method_optional_and_downstream(self) -> FormatDecisionDraft:
        if self.narrative_method_hint is not None and self.selected_format.kind not in _NARRATIVE_FORMATS:
            raise ValueError("narrative method hint requires a narrative presentation form")
        return self


class FormatDecision(FormatDecisionDraft):
    message_plan_binding: MessagePlanBinding
    base_draft_binding: BaseDraftBinding
    incubation_judgment_ref: ArtifactParentRef | None = None
    resource_evidence_refs: tuple[ArtifactParentRef, ...] = ()

    @field_validator("resource_evidence_refs")
    @classmethod
    def canonicalize_resource_refs(
        cls,
        value: tuple[ArtifactParentRef, ...],
    ) -> tuple[ArtifactParentRef, ...]:
        if len({item.artifact_id for item in value}) != len(value):
            raise ValueError("resource evidence references must be unique")
        return tuple(sorted(value, key=lambda item: item.artifact_id))


def _require_parent(
    artifact: ArtifactEnvelope,
    *,
    project: ProjectRef,
    artifact_type: str | None = None,
) -> None:
    if artifact.project != project:
        raise ValueError("parent project must match format decision project")
    if artifact_type is not None and artifact.artifact_type != artifact_type:
        raise ValueError(f"expected {artifact_type} parent")


def _required_text(payload: dict[str, object], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"message plan requires a non-empty {field}")
    return value


def _message_plan_binding(message_plan_artifact: ArtifactEnvelope) -> MessagePlanBinding:
    payload = message_plan_artifact.payload
    protected_fields = {field: _required_text(payload, field) for field in _PROTECTED_MESSAGE_PLAN_FIELDS}
    evidence_boundary: dict[str, object] = {}
    for field in _EVIDENCE_BOUNDARY_FIELDS:
        value = payload.get(field)
        if not isinstance(value, list):
            raise ValueError(f"message plan requires an explicit {field} boundary")
        evidence_boundary[field] = value

    return MessagePlanBinding(
        artifact_id=message_plan_artifact.artifact_id,
        artifact_content_sha256=message_plan_artifact.content_sha256,
        message_plan_id=_required_text(payload, "message_plan_id"),
        record_id=_required_text(payload, "record_id"),
        protected_content_sha256=_canonical_sha256(protected_fields),
        evidence_boundary_sha256=_canonical_sha256(evidence_boundary),
    )


def _base_draft_binding(
    base_draft_artifact: ArtifactEnvelope,
    *,
    message_plan_artifact: ArtifactEnvelope,
) -> BaseDraftBinding:
    payload = base_draft_artifact.payload
    draft_id = _required_text(payload, "draft_id")
    message_plan_id = _required_text(payload, "message_plan_id")
    text = _required_text(payload, "text")
    stage = _required_text(payload, "stage")
    if stage != "base":
        raise ValueError("format decision requires a draft_version at base stage")
    expected_message_plan_id = _required_text(message_plan_artifact.payload, "message_plan_id")
    if message_plan_id != expected_message_plan_id:
        raise ValueError("base draft message_plan_id must match the exact message plan")
    if message_plan_artifact.to_parent_ref() not in base_draft_artifact.parents:
        raise ValueError("base draft must descend from the exact message plan")
    return BaseDraftBinding(
        artifact_id=base_draft_artifact.artifact_id,
        artifact_content_sha256=base_draft_artifact.content_sha256,
        draft_id=draft_id,
        message_plan_id=message_plan_id,
        stage="base",
        body_sha256=_canonical_sha256(text),
    )


def validate_format_decision_parents(
    *,
    project: ProjectRef,
    message_plan_artifact: ArtifactEnvelope,
    base_draft_artifact: ArtifactEnvelope,
    incubation_judgment_artifact: ArtifactEnvelope | None = None,
    resource_evidence_artifacts: tuple[ArtifactEnvelope, ...] = (),
) -> tuple[MessagePlanBinding, BaseDraftBinding]:
    """Validate and bind the immutable inputs before any format model call."""

    _require_parent(
        message_plan_artifact,
        project=project,
        artifact_type="message_plan",
    )
    _require_parent(
        base_draft_artifact,
        project=project,
        artifact_type="draft_version",
    )
    if incubation_judgment_artifact is not None:
        _require_parent(
            incubation_judgment_artifact,
            project=project,
            artifact_type="incubation_judgment",
        )
    for artifact in resource_evidence_artifacts:
        _require_parent(
            artifact,
            project=project,
            artifact_type="media_observation",
        )
        if artifact.evidence_role != "user_material":
            raise ValueError("format resource evidence requires a user_material media_observation parent")

    parent_artifacts = (
        message_plan_artifact,
        base_draft_artifact,
        *((incubation_judgment_artifact,) if incubation_judgment_artifact is not None else ()),
        *resource_evidence_artifacts,
    )
    if len({artifact.artifact_id for artifact in parent_artifacts}) != len(parent_artifacts):
        raise ValueError("format decision parent artifacts must be unique")
    return (
        _message_plan_binding(message_plan_artifact),
        _base_draft_binding(
            base_draft_artifact,
            message_plan_artifact=message_plan_artifact,
        ),
    )


def seal_format_decision(
    *,
    project: ProjectRef,
    draft: FormatDecisionDraft,
    message_plan_artifact: ArtifactEnvelope,
    base_draft_artifact: ArtifactEnvelope,
    created_at: datetime,
    source_thread_id: str,
    source_run_id: str,
    incubation_judgment_artifact: ArtifactEnvelope | None = None,
    resource_evidence_artifacts: tuple[ArtifactEnvelope, ...] = (),
) -> ArtifactEnvelope:
    """Bind one presentation decision below an immutable message plan."""

    message_plan_binding, base_draft_binding = validate_format_decision_parents(
        project=project,
        message_plan_artifact=message_plan_artifact,
        base_draft_artifact=base_draft_artifact,
        incubation_judgment_artifact=incubation_judgment_artifact,
        resource_evidence_artifacts=resource_evidence_artifacts,
    )

    resource_ids = {artifact.artifact_id for artifact in resource_evidence_artifacts}
    if len(resource_ids) != len(resource_evidence_artifacts):
        raise ValueError("resource evidence artifacts must be unique")
    used_resource_ids = {artifact_id for match in draft.resource_matches for artifact_id in match.basis_artifact_ids}
    if not used_resource_ids.issubset(resource_ids):
        raise ValueError("every resource basis artifact must be included as a parent")

    resource_refs = tuple(
        artifact.to_parent_ref()
        for artifact in sorted(
            resource_evidence_artifacts,
            key=lambda item: item.artifact_id,
        )
    )
    judgment_ref = incubation_judgment_artifact.to_parent_ref() if incubation_judgment_artifact is not None else None
    decision = FormatDecision(
        **draft.model_dump(),
        message_plan_binding=message_plan_binding,
        base_draft_binding=base_draft_binding,
        incubation_judgment_ref=judgment_ref,
        resource_evidence_refs=resource_refs,
    )
    parents = (
        message_plan_artifact.to_parent_ref(),
        base_draft_artifact.to_parent_ref(),
        *((judgment_ref,) if judgment_ref is not None else ()),
        *resource_refs,
    )
    return ArtifactEnvelope.seal(
        project=project,
        artifact_type="format_decision",
        version=1,
        payload=decision.model_dump(mode="json"),
        parents=parents,
        created_at=created_at,
        source_thread_id=source_thread_id,
        source_run_id=source_run_id,
    )


__all__ = [
    "BaseDraftBinding",
    "FormatAlternative",
    "FormatChoice",
    "FormatDecision",
    "FormatDecisionDraft",
    "FormatDecisionStatus",
    "FormatKind",
    "MessagePlanBinding",
    "ResourceMatch",
    "seal_format_decision",
    "validate_format_decision_parents",
]
