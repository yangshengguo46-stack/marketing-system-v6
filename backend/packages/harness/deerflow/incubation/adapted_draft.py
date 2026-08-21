from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Literal

from pydantic import Field, field_validator, model_validator

from deerflow.incubation.contracts import (
    ArtifactEnvelope,
    ArtifactParentRef,
    IncubationContract,
    LogicalAccountRef,
    NonEmptyStr,
    ProjectRef,
)
from deerflow.incubation.format_decision import (
    BaseDraftBinding,
    FormatChoice,
    FormatDecision,
)

PresentationMode = Literal[
    "spoken_line",
    "voiceover",
    "on_screen_text",
    "visual_only",
    "interview_prompt",
    "interview_response",
    "observed_action",
    "dialogue",
    "narration",
]

_NARRATIVE_FORMATS = frozenset({"micro_drama", "situational_drama"})
_NARRATIVE_ONLY_MODES = frozenset({"dialogue"})


def _canonical_sha256(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _required_text(payload: dict[str, object], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"base draft requires a non-empty {field}")
    return value


class NarrativeTreatment(IncubationContract):
    """High-level staging below a narrative format, never a new story source."""

    scene_purpose: NonEmptyStr = Field(max_length=3000)
    performance_intent: NonEmptyStr = Field(max_length=3000)


class PresentationUnitDraft(IncubationContract):
    """One ordered expression unit anchored to exact BaseDraft language."""

    unit_id: NonEmptyStr = Field(max_length=128)
    mode: PresentationMode
    adapted_expression: NonEmptyStr = Field(max_length=12_000)
    source_excerpts: tuple[NonEmptyStr, ...] = Field(min_length=1)
    visual_treatment: NonEmptyStr | None = Field(default=None, max_length=3000)
    narrative_treatment: NarrativeTreatment | None = None

    @field_validator("source_excerpts")
    @classmethod
    def keep_source_excerpts_ordered_and_unique(
        cls,
        value: tuple[str, ...],
    ) -> tuple[str, ...]:
        if len(set(value)) != len(value):
            raise ValueError("source excerpts within one presentation unit must be unique")
        return value


class AdaptedDraftDraft(IncubationContract):
    """A format translation with no fields that can reopen content decisions."""

    units: tuple[PresentationUnitDraft, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def require_unique_unit_ids(self) -> AdaptedDraftDraft:
        unit_ids = [unit.unit_id for unit in self.units]
        if len(set(unit_ids)) != len(unit_ids):
            raise ValueError("presentation unit IDs must be unique")
        return self


class SourceExcerptAnchor(IncubationContract):
    excerpt: NonEmptyStr
    start_char: int = Field(ge=0)
    end_char: int = Field(gt=0)

    @model_validator(mode="after")
    def bind_offsets_to_excerpt_length(self) -> SourceExcerptAnchor:
        if self.end_char <= self.start_char:
            raise ValueError("source excerpt end must follow its start")
        if self.end_char - self.start_char != len(self.excerpt):
            raise ValueError("source excerpt offsets must exactly span the excerpt")
        return self


class PresentationUnit(IncubationContract):
    unit_id: NonEmptyStr = Field(max_length=128)
    mode: PresentationMode
    adapted_expression: NonEmptyStr = Field(max_length=12_000)
    source_anchors: tuple[SourceExcerptAnchor, ...] = Field(min_length=1)
    visual_treatment: NonEmptyStr | None = Field(default=None, max_length=3000)
    narrative_treatment: NarrativeTreatment | None = None


class AdaptedDraft(IncubationContract):
    base_draft_binding: BaseDraftBinding
    format_decision_ref: ArtifactParentRef
    selected_format: FormatChoice
    units: tuple[PresentationUnit, ...] = Field(min_length=1)
    adapted_body: NonEmptyStr
    adapted_body_sha256: NonEmptyStr

    @field_validator("adapted_body_sha256")
    @classmethod
    def validate_sha256(cls, value: str) -> str:
        if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
            raise ValueError("adapted body hash must be lowercase SHA-256")
        return value

    @model_validator(mode="after")
    def validate_body_and_units(self) -> AdaptedDraft:
        unit_ids = [unit.unit_id for unit in self.units]
        if len(set(unit_ids)) != len(unit_ids):
            raise ValueError("presentation unit IDs must be unique")
        expected_body = "\n\n".join(unit.adapted_expression for unit in self.units)
        if self.adapted_body != expected_body:
            raise ValueError("adapted body must preserve presentation unit order")
        if self.adapted_body_sha256 != _canonical_sha256(self.adapted_body):
            raise ValueError("adapted body hash does not match adapted body")
        return self


def _require_artifact(
    artifact: ArtifactEnvelope,
    *,
    project: ProjectRef,
    artifact_type: str,
) -> None:
    if artifact.project != project:
        raise ValueError(f"{artifact_type} parent project must match adapted draft project")
    if artifact.artifact_type != artifact_type:
        raise ValueError(f"expected {artifact_type} parent")


def validate_adapted_draft_parents(
    *,
    project: ProjectRef,
    base_draft_artifact: ArtifactEnvelope,
    format_decision_artifact: ArtifactEnvelope,
) -> tuple[BaseDraftBinding, FormatChoice, str]:
    """Validate exact immutable lineage before an adaptation model is called."""

    _require_artifact(
        base_draft_artifact,
        project=project,
        artifact_type="draft_version",
    )
    _require_artifact(
        format_decision_artifact,
        project=project,
        artifact_type="format_decision",
    )
    decision = FormatDecision.model_validate(format_decision_artifact.payload)
    binding = decision.base_draft_binding
    if binding.artifact_id != base_draft_artifact.artifact_id or binding.artifact_content_sha256 != base_draft_artifact.content_sha256 or base_draft_artifact.to_parent_ref() not in format_decision_artifact.parents:
        raise ValueError("adapted draft requires the exact base draft bound by the format decision")

    payload = base_draft_artifact.payload
    draft_id = _required_text(payload, "draft_id")
    message_plan_id = _required_text(payload, "message_plan_id")
    body = _required_text(payload, "text")
    stage = _required_text(payload, "stage")
    if stage != "base" or binding.stage != "base":
        raise ValueError("adapted draft requires a base-stage draft")
    if draft_id != binding.draft_id or message_plan_id != binding.message_plan_id:
        raise ValueError("adapted draft base identity must match the exact format binding")
    if _canonical_sha256(body) != binding.body_sha256:
        raise ValueError("adapted draft base body must match the exact format binding")
    return binding, decision.selected_format, body


def validate_adapted_draft_output(
    *,
    draft: AdaptedDraftDraft,
    base_body: str,
    selected_format: FormatChoice,
) -> tuple[PresentationUnit, ...]:
    """Bind every proposed expression unit to contiguous BaseDraft excerpts."""

    narrative_format = selected_format.kind in _NARRATIVE_FORMATS
    bound_units: list[PresentationUnit] = []
    for unit in draft.units:
        if unit.narrative_treatment is not None and not narrative_format:
            raise ValueError("narrative treatment requires a narrative presentation format")
        if unit.mode in _NARRATIVE_ONLY_MODES and not narrative_format:
            raise ValueError("dialogue requires a narrative presentation format")

        anchors: list[SourceExcerptAnchor] = []
        for excerpt in unit.source_excerpts:
            start = base_body.find(excerpt)
            if start < 0:
                raise ValueError(f"presentation unit {unit.unit_id!r} requires a contiguous verbatim BaseDraft excerpt")
            anchors.append(
                SourceExcerptAnchor(
                    excerpt=excerpt,
                    start_char=start,
                    end_char=start + len(excerpt),
                )
            )
        bound_units.append(
            PresentationUnit(
                unit_id=unit.unit_id,
                mode=unit.mode,
                adapted_expression=unit.adapted_expression,
                source_anchors=tuple(anchors),
                visual_treatment=unit.visual_treatment,
                narrative_treatment=unit.narrative_treatment,
            )
        )
    return tuple(bound_units)


def seal_adapted_draft(
    *,
    project: ProjectRef,
    draft: AdaptedDraftDraft,
    base_draft_artifact: ArtifactEnvelope,
    format_decision_artifact: ArtifactEnvelope,
    created_at: datetime,
    source_thread_id: str,
    source_run_id: str,
    logical_account: LogicalAccountRef | None = None,
) -> ArtifactEnvelope:
    """Seal one format translation without reopening topic or evidence choices."""

    binding, selected_format, base_body = validate_adapted_draft_parents(
        project=project,
        base_draft_artifact=base_draft_artifact,
        format_decision_artifact=format_decision_artifact,
    )
    units = validate_adapted_draft_output(
        draft=draft,
        base_body=base_body,
        selected_format=selected_format,
    )
    adapted_body = "\n\n".join(unit.adapted_expression for unit in units)
    adapted = AdaptedDraft(
        base_draft_binding=binding,
        format_decision_ref=format_decision_artifact.to_parent_ref(),
        selected_format=selected_format,
        units=units,
        adapted_body=adapted_body,
        adapted_body_sha256=_canonical_sha256(adapted_body),
    )
    return ArtifactEnvelope.seal(
        project=project,
        artifact_type="adapted_draft",
        version=1,
        payload=adapted.model_dump(mode="json"),
        logical_account=logical_account,
        parents=(
            base_draft_artifact.to_parent_ref(),
            format_decision_artifact.to_parent_ref(),
        ),
        created_at=created_at,
        source_thread_id=source_thread_id,
        source_run_id=source_run_id,
    )


__all__ = [
    "AdaptedDraft",
    "AdaptedDraftDraft",
    "NarrativeTreatment",
    "PresentationMode",
    "PresentationUnit",
    "PresentationUnitDraft",
    "SourceExcerptAnchor",
    "seal_adapted_draft",
    "validate_adapted_draft_output",
    "validate_adapted_draft_parents",
]
