from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field, field_validator, model_validator

from deerflow.incubation.adapted_draft import AdaptedDraft
from deerflow.incubation.contracts import (
    ArtifactEnvelope,
    ArtifactParentRef,
    IncubationContract,
    NonEmptyStr,
    ProjectRef,
)
from deerflow.incubation.format_decision import FormatChoice, FormatDecision

ProductionPlanStatus = Literal["provisional", "ready"]
ProductionAssetKind = Literal[
    "video",
    "audio",
    "image",
    "text_graphic",
    "subtitle",
    "other",
]
ProductionAssetSource = Literal[
    "existing_user_material",
    "to_capture",
    "to_record",
    "to_create",
    "derived_from_adapted_draft",
]
ProductionActionKind = Literal[
    "capture_video",
    "capture_image",
    "record_audio",
    "text_layout",
    "select_existing",
    "media_generation",
    "performance_blocking",
    "scene_blocking",
]

_NARRATIVE_FORMATS = frozenset({"micro_drama", "situational_drama"})
_NON_PERFORMANCE_FORMATS = frozenset({"image_text", "material_only"})
_PERFORMANCE_ACTIONS = frozenset({"performance_blocking", "scene_blocking"})


def _canonical_ids(value: tuple[str, ...], *, name: str) -> tuple[str, ...]:
    if len(set(value)) != len(value):
        raise ValueError(f"{name} must be unique")
    return tuple(sorted(value))


class ProductionAssetRequirement(IncubationContract):
    asset_id: NonEmptyStr = Field(max_length=128)
    kind: ProductionAssetKind
    purpose: NonEmptyStr = Field(max_length=2000)
    source: ProductionAssetSource
    basis_artifact_ids: tuple[NonEmptyStr, ...] = ()

    @field_validator("basis_artifact_ids")
    @classmethod
    def canonicalize_basis_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _canonical_ids(value, name="material basis artifact IDs")

    @model_validator(mode="after")
    def bind_existing_material_to_evidence(self) -> ProductionAssetRequirement:
        if self.source == "existing_user_material":
            if not self.basis_artifact_ids:
                raise ValueError("existing user material requires a user_material basis artifact")
        elif self.basis_artifact_ids:
            raise ValueError("only existing user material may cite material basis artifacts")
        return self


class ProductionAction(IncubationContract):
    action_id: NonEmptyStr = Field(max_length=128)
    kind: ProductionActionKind
    instruction: NonEmptyStr = Field(max_length=3000)
    asset_ids: tuple[NonEmptyStr, ...] = Field(min_length=1)

    @field_validator("asset_ids")
    @classmethod
    def canonicalize_asset_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _canonical_ids(value, name="production action asset IDs")


class AssemblyStep(IncubationContract):
    step_id: NonEmptyStr = Field(max_length=128)
    instruction: NonEmptyStr = Field(max_length=3000)
    input_asset_ids: tuple[NonEmptyStr, ...] = Field(min_length=1)

    @field_validator("input_asset_ids")
    @classmethod
    def canonicalize_input_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _canonical_ids(value, name="assembly input asset IDs")


class ProductionPlanDraft(IncubationContract):
    """Execution translation below immutable content and format decisions."""

    status: ProductionPlanStatus = "provisional"
    asset_requirements: tuple[ProductionAssetRequirement, ...] = ()
    production_actions: tuple[ProductionAction, ...] = ()
    assembly_steps: tuple[AssemblyStep, ...] = ()
    resource_gaps: tuple[NonEmptyStr, ...] = ()
    unknowns: tuple[NonEmptyStr, ...] = ()
    limitations: tuple[NonEmptyStr, ...] = ()
    narrative_execution_hint: NonEmptyStr | None = Field(default=None, max_length=3000)

    @model_validator(mode="after")
    def validate_execution_graph(self) -> ProductionPlanDraft:
        asset_ids = [asset.asset_id for asset in self.asset_requirements]
        action_ids = [action.action_id for action in self.production_actions]
        step_ids = [step.step_id for step in self.assembly_steps]
        if len(set(asset_ids)) != len(asset_ids):
            raise ValueError("production asset IDs must be unique")
        if len(set(action_ids)) != len(action_ids):
            raise ValueError("production action IDs must be unique")
        if len(set(step_ids)) != len(step_ids):
            raise ValueError("assembly step IDs must be unique")

        known_assets = set(asset_ids)
        for action in self.production_actions:
            unknown = set(action.asset_ids) - known_assets
            if unknown:
                raise ValueError("production action references an unknown asset")
        for step in self.assembly_steps:
            unknown = set(step.input_asset_ids) - known_assets
            if unknown:
                raise ValueError("assembly step references an unknown asset")
        return self


class ProductionPlan(ProductionPlanDraft):
    adapted_draft_ref: ArtifactParentRef
    adapted_body_sha256: NonEmptyStr
    format_decision_ref: ArtifactParentRef
    selected_format: FormatChoice
    user_material_refs: tuple[ArtifactParentRef, ...] = ()

    @field_validator("adapted_body_sha256")
    @classmethod
    def validate_adapted_body_sha256(cls, value: str) -> str:
        if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
            raise ValueError("adapted body hash must be lowercase SHA-256")
        return value

    @field_validator("user_material_refs")
    @classmethod
    def canonicalize_material_refs(
        cls,
        value: tuple[ArtifactParentRef, ...],
    ) -> tuple[ArtifactParentRef, ...]:
        if len({item.artifact_id for item in value}) != len(value):
            raise ValueError("user material references must be unique")
        return tuple(sorted(value, key=lambda item: item.artifact_id))

    @model_validator(mode="after")
    def validate_format_and_material_bindings(self) -> ProductionPlan:
        claimed_material_ids = {artifact_id for requirement in self.asset_requirements if requirement.source == "existing_user_material" for artifact_id in requirement.basis_artifact_ids}
        bound_material_ids = {item.artifact_id for item in self.user_material_refs}
        if claimed_material_ids != bound_material_ids:
            raise ValueError("existing material claims must exactly match bound user_material parents")

        format_kind = self.selected_format.kind
        if self.narrative_execution_hint is not None and format_kind not in _NARRATIVE_FORMATS:
            raise ValueError("narrative execution hints require a narrative format")
        if format_kind in _NON_PERFORMANCE_FORMATS and any(action.kind in _PERFORMANCE_ACTIONS for action in self.production_actions):
            raise ValueError("image-text and material-only plans cannot force performance actions")
        return self


def _require_artifact(
    artifact: ArtifactEnvelope,
    *,
    project: ProjectRef,
    artifact_type: str,
) -> None:
    if artifact.project != project:
        raise ValueError(f"{artifact_type} parent project must match production plan project")
    if artifact.artifact_type != artifact_type:
        raise ValueError(f"expected {artifact_type} parent")


def validate_production_plan_parents(
    *,
    project: ProjectRef,
    adapted_draft_artifact: ArtifactEnvelope,
    format_decision_artifact: ArtifactEnvelope,
    user_material_artifacts: tuple[ArtifactEnvelope, ...] = (),
) -> tuple[AdaptedDraft, FormatDecision]:
    """Validate exact immutable production lineage before any model call."""

    _require_artifact(
        adapted_draft_artifact,
        project=project,
        artifact_type="adapted_draft",
    )
    _require_artifact(
        format_decision_artifact,
        project=project,
        artifact_type="format_decision",
    )
    adapted = AdaptedDraft.model_validate(adapted_draft_artifact.payload)
    decision = FormatDecision.model_validate(format_decision_artifact.payload)
    exact_format_ref = format_decision_artifact.to_parent_ref()
    if adapted.format_decision_ref != exact_format_ref or exact_format_ref not in adapted_draft_artifact.parents:
        raise ValueError("production plan requires an adapted draft from the exact format decision")
    if adapted.selected_format != decision.selected_format or adapted.base_draft_binding != decision.base_draft_binding:
        raise ValueError("adapted draft content lineage must match the exact format decision")

    base_binding = adapted.base_draft_binding
    expected_base_ref = ArtifactParentRef(
        owner_user_id=project.owner_user_id,
        project_id=project.project_id,
        artifact_id=base_binding.artifact_id,
        artifact_type="draft_version",
        content_sha256=base_binding.artifact_content_sha256,
    )
    if expected_base_ref not in adapted_draft_artifact.parents or expected_base_ref not in format_decision_artifact.parents:
        raise ValueError("adapted draft and format decision must retain the exact base draft parent")

    message_binding = decision.message_plan_binding
    expected_message_ref = ArtifactParentRef(
        owner_user_id=project.owner_user_id,
        project_id=project.project_id,
        artifact_id=message_binding.artifact_id,
        artifact_type="message_plan",
        content_sha256=message_binding.artifact_content_sha256,
    )
    if expected_message_ref not in format_decision_artifact.parents:
        raise ValueError("format decision must retain the exact message plan parent")

    format_material_refs = set(decision.resource_evidence_refs)
    if any(ref not in format_decision_artifact.parents for ref in format_material_refs):
        raise ValueError("format decision must retain every exact resource evidence parent")

    material_ids: set[str] = set()
    for artifact in user_material_artifacts:
        if artifact.project != project:
            raise ValueError("user material parent project must match production plan project")
        if artifact.artifact_type != "media_observation":
            raise ValueError("production material requires a media_observation parent")
        if artifact.evidence_role != "user_material":
            raise ValueError("production material requires a user_material evidence parent")
        if artifact.artifact_id in material_ids:
            raise ValueError("user material artifacts must be unique")
        material_ids.add(artifact.artifact_id)
        if artifact.to_parent_ref() not in format_material_refs:
            raise ValueError("existing material must have been reviewed by the exact format decision")

    return adapted, decision


def seal_production_plan(
    *,
    project: ProjectRef,
    draft: ProductionPlanDraft,
    adapted_draft_artifact: ArtifactEnvelope,
    format_decision_artifact: ArtifactEnvelope,
    created_at: datetime,
    source_thread_id: str,
    source_run_id: str,
    user_material_artifacts: tuple[ArtifactEnvelope, ...] = (),
) -> ArtifactEnvelope:
    """Seal executable production instructions without reopening content choices."""

    adapted, decision = validate_production_plan_parents(
        project=project,
        adapted_draft_artifact=adapted_draft_artifact,
        format_decision_artifact=format_decision_artifact,
        user_material_artifacts=user_material_artifacts,
    )
    exact_format_ref = format_decision_artifact.to_parent_ref()
    material_ids = {artifact.artifact_id for artifact in user_material_artifacts}

    claimed_material_ids = {artifact_id for requirement in draft.asset_requirements if requirement.source == "existing_user_material" for artifact_id in requirement.basis_artifact_ids}
    if claimed_material_ids != material_ids:
        raise ValueError("existing material claims must exactly match user_material parents")

    material_refs = tuple(
        artifact.to_parent_ref()
        for artifact in sorted(
            user_material_artifacts,
            key=lambda item: item.artifact_id,
        )
    )
    plan = ProductionPlan(
        **draft.model_dump(),
        adapted_draft_ref=adapted_draft_artifact.to_parent_ref(),
        adapted_body_sha256=adapted.adapted_body_sha256,
        format_decision_ref=exact_format_ref,
        selected_format=decision.selected_format,
        user_material_refs=material_refs,
    )
    return ArtifactEnvelope.seal(
        project=project,
        artifact_type="production_plan",
        version=1,
        payload=plan.model_dump(mode="json"),
        parents=(
            adapted_draft_artifact.to_parent_ref(),
            exact_format_ref,
            *material_refs,
        ),
        created_at=created_at,
        source_thread_id=source_thread_id,
        source_run_id=source_run_id,
    )


__all__ = [
    "AssemblyStep",
    "ProductionAction",
    "ProductionActionKind",
    "ProductionAssetKind",
    "ProductionAssetRequirement",
    "ProductionAssetSource",
    "ProductionPlan",
    "ProductionPlanDraft",
    "ProductionPlanStatus",
    "seal_production_plan",
    "validate_production_plan_parents",
]
