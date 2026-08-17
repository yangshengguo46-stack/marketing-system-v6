from __future__ import annotations

import hashlib
import json
import math
from typing import Literal

from pydantic import Field, JsonValue, field_validator, model_validator

from deerflow.community.mediakit.contracts import (
    MediaKitCloudSourceContext,
    MediaKitLocalMaterializationContext,
)
from deerflow.community.mediakit.router import (
    MediaKitCapabilityRouter,
    MediaKitCommandError,
)
from deerflow.community.mediakit.trusted_io import (
    MediaKitLocalResultMaterializer,
    MediaKitTrustedSourceStore,
)
from deerflow.incubation.contracts import (
    ArtifactEnvelope,
    IncubationContract,
    NonEmptyStr,
    ProjectRef,
)
from deerflow.incubation.media import (
    MediaKitExecutionReceipt,
    MediaObservationSnapshot,
    MediaSourceReceipt,
)
from deerflow.incubation.media_artifact import (
    MediaArtifactDraft,
    MediaQCCheck,
    build_media_production_binding,
    seal_media_artifact,
)
from deerflow.incubation.production_plan import ProductionPlan

_MAX_LOCAL_OUTPUT_BYTES = 20 * 1024 * 1024 * 1024
_RESERVED_ARGUMENT_NAMES = frozenset(
    {
        "audio_url",
        "callback_args",
        "client_token",
        "image_url",
        "subtitle_url",
        "video_url",
    }
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


class MediaKitLocalProductionOperation(IncubationContract):
    """One reviewed local MediaKit step below an immutable ProductionPlan."""

    schema_version: Literal["v6-mediakit-local-production-operation-v1"] = "v6-mediakit-local-production-operation-v1"
    operation_id: NonEmptyStr = Field(max_length=128)
    production_action_ids: tuple[NonEmptyStr, ...] = Field(min_length=1, max_length=32)
    assembly_step_ids: tuple[NonEmptyStr, ...] = Field(min_length=1, max_length=32)
    plan_asset_ids: tuple[NonEmptyStr, ...] = Field(min_length=1, max_length=32)
    capability_domain: Literal["editing"] = "editing"
    capability_tool: Literal["trim-video"] = "trim-video"
    expected_schema_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    arguments: dict[NonEmptyStr, JsonValue] = Field(default_factory=dict, max_length=32)
    output_field: Literal["video_url"] = "video_url"
    stage: Literal["intermediate", "final"]
    maximum_output_bytes: int = Field(gt=0, le=_MAX_LOCAL_OUTPUT_BYTES)

    @field_validator(
        "production_action_ids",
        "assembly_step_ids",
        "plan_asset_ids",
    )
    @classmethod
    def canonicalize_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(value)) != len(value):
            raise ValueError("MediaKit production operation IDs must be unique")
        return tuple(sorted(value))

    @field_validator("arguments")
    @classmethod
    def reject_execution_locators(
        cls,
        value: dict[str, JsonValue],
    ) -> dict[str, JsonValue]:
        for name in value:
            normalized = name.casefold()
            if normalized in _RESERVED_ARGUMENT_NAMES or normalized.endswith(("_url", "_path", "_file", "_files")) or "locator" in normalized:
                raise ValueError("MediaKit operation arguments cannot carry a locator")
        _canonical_sha256(value)
        return value

    @model_validator(mode="after")
    def validate_trim_arguments(self) -> MediaKitLocalProductionOperation:
        allowed = {"start_time", "end_time"}
        unknown = set(self.arguments) - allowed
        if unknown:
            raise ValueError("trim-video accepts only start_time and end_time")
        if not self.arguments:
            raise ValueError("trim-video requires a start_time or end_time")
        start = self.arguments.get("start_time", 0)
        end = self.arguments.get("end_time")
        if isinstance(start, bool) or not isinstance(start, (int, float)) or not math.isfinite(start) or start < 0:
            raise ValueError("trim-video start_time must be a finite non-negative number")
        if end is not None:
            if isinstance(end, bool) or not isinstance(end, (int, float)) or not math.isfinite(end) or end <= start:
                raise ValueError("trim-video end_time must be greater than start_time")
        return self

    @property
    def arguments_sha256(self) -> str:
        return _canonical_sha256(self.arguments)


def _validate_plan_operation(
    *,
    plan: ProductionPlan,
    input_asset_artifact: ArtifactEnvelope,
    operation: MediaKitLocalProductionOperation,
) -> None:
    if operation.stage == "final" and plan.status != "ready":
        raise ValueError("a provisional production plan cannot produce a final media artifact")
    action_by_id = {action.action_id: action for action in plan.production_actions}
    step_by_id = {step.step_id: step for step in plan.assembly_steps}
    asset_by_id = {asset.asset_id: asset for asset in plan.asset_requirements}
    if not set(operation.production_action_ids).issubset(action_by_id):
        raise ValueError("MediaKit operation references an unknown production action")
    if not set(operation.assembly_step_ids).issubset(step_by_id):
        raise ValueError("MediaKit operation references an unknown assembly step")
    if not set(operation.plan_asset_ids).issubset(asset_by_id):
        raise ValueError("MediaKit operation references an unknown plan asset")
    selected_assets = set(operation.plan_asset_ids)
    if any(not selected_assets.intersection(action_by_id[action_id].asset_ids) for action_id in operation.production_action_ids):
        raise ValueError("MediaKit production action is not connected to the bound plan asset")
    if any(not selected_assets.intersection(step_by_id[step_id].input_asset_ids) for step_id in operation.assembly_step_ids):
        raise ValueError("MediaKit assembly step is not connected to the bound plan asset")
    if not any(input_asset_artifact.artifact_id in asset_by_id[asset_id].basis_artifact_ids for asset_id in operation.plan_asset_ids):
        raise ValueError("MediaKit input artifact is not the bound plan asset")


def _validate_source_lineage(
    *,
    project: ProjectRef,
    plan: ProductionPlan,
    input_asset_artifact: ArtifactEnvelope,
    source_receipt_artifact: ArtifactEnvelope,
) -> tuple[MediaObservationSnapshot, MediaSourceReceipt]:
    if input_asset_artifact.project != project or source_receipt_artifact.project != project:
        raise ValueError("MediaKit local production input must belong to the same project")
    if input_asset_artifact.artifact_type != "media_observation" or input_asset_artifact.evidence_role != "user_material":
        raise ValueError("MediaKit local production requires user_material media observation")
    if input_asset_artifact.to_parent_ref() not in plan.user_material_refs:
        raise ValueError("MediaKit input was not approved by the exact production plan")
    if source_receipt_artifact.artifact_type != "media_source_receipt" or source_receipt_artifact.evidence_role != "user_material":
        raise ValueError("MediaKit local production requires a user_material source receipt")
    if input_asset_artifact.parents != (source_receipt_artifact.to_parent_ref(),):
        raise ValueError("MediaKit source receipt does not match the input observation")
    observation = MediaObservationSnapshot.model_validate(input_asset_artifact.payload)
    receipt = MediaSourceReceipt.model_validate(source_receipt_artifact.payload)
    if observation.source_ref != receipt.source_ref:
        raise ValueError("MediaKit source identity does not match its receipt")
    expected_source_sha256 = observation.execution.source_content_sha256
    if expected_source_sha256 is None:
        raise ValueError("MediaKit input observation requires a source content hash")
    return observation, receipt


async def execute_local_media_operation(
    *,
    project: ProjectRef,
    production_plan_artifact: ArtifactEnvelope,
    input_asset_artifact: ArtifactEnvelope,
    source_receipt_artifact: ArtifactEnvelope,
    operation: MediaKitLocalProductionOperation,
    router: MediaKitCapabilityRouter,
    source_store: MediaKitTrustedSourceStore,
    materializer: MediaKitLocalResultMaterializer,
    source_thread_id: str,
    source_run_id: str,
) -> ArtifactEnvelope:
    """Execute and seal one exact, reversible local production operation."""

    project = ProjectRef.model_validate(project.model_dump(mode="python"))
    operation = MediaKitLocalProductionOperation.model_validate(operation.model_dump(mode="python"))
    if production_plan_artifact.project != project or production_plan_artifact.artifact_type != "production_plan":
        raise ValueError("MediaKit local production requires a same-project ProductionPlan")
    plan = ProductionPlan.model_validate(production_plan_artifact.payload)
    observation, receipt = _validate_source_lineage(
        project=project,
        plan=plan,
        input_asset_artifact=input_asset_artifact,
        source_receipt_artifact=source_receipt_artifact,
    )
    _validate_plan_operation(
        plan=plan,
        input_asset_artifact=input_asset_artifact,
        operation=operation,
    )
    materializer.validate_operation(
        capability_domain=operation.capability_domain,
        capability_tool=operation.capability_tool,
        output_field=operation.output_field,
        maximum_output_bytes=operation.maximum_output_bytes,
    )
    expected_source_sha256 = observation.execution.source_content_sha256
    assert expected_source_sha256 is not None
    source_context = MediaKitCloudSourceContext(
        user_id=project.owner_user_id,
        project_id=project.project_id,
        local_task_id=operation.operation_id,
        source_ref=receipt.source_ref,
        rights_ref=receipt.rights_ref,
        source_content_sha256=expected_source_sha256,
    )
    source = await source_store.resolve(source_context)
    await source_store.verify(source_context, source)
    workspace = await materializer.create_output_workspace(
        user_id=project.owner_user_id,
        production_plan_artifact_id=production_plan_artifact.artifact_id,
        operation_id=operation.operation_id,
    )
    try:
        prepared = await router.prepare_video_call(
            domain=operation.capability_domain,
            tool=operation.capability_tool,
            source=source,
            mode="local",
            arguments=operation.arguments,
            output_path=workspace,
        )
        if prepared.capability.schema_sha256 != operation.expected_schema_sha256:
            raise MediaKitCommandError("MediaKit local production schema changed")
        execution = await router.execute_local(prepared)
        if execution.source_content_sha256 != expected_source_sha256:
            raise MediaKitCommandError("MediaKit local production source content changed")

        materialized = await materializer(
            MediaKitLocalMaterializationContext(
                operation_id=operation.operation_id,
                user_id=project.owner_user_id,
                project_id=project.project_id,
                production_plan_artifact_id=production_plan_artifact.artifact_id,
                production_plan_content_sha256=production_plan_artifact.content_sha256,
                source_ref=receipt.source_ref,
                source_content_sha256=execution.source_content_sha256,
                capability_domain=prepared.capability.domain,
                capability_tool=prepared.capability.tool,
                capability_schema_sha256=prepared.capability.schema_sha256,
                request_sha256=prepared.input_sha256,
                output_field=operation.output_field,
                maximum_output_bytes=operation.maximum_output_bytes,
                provider_output=execution.output,
                provider_output_sha256=execution.output_sha256,
                executed_at=execution.executed_at,
            ),
            expected_output_root=workspace,
        )
    finally:
        await materializer.cleanup_output_workspace(workspace)
    execution_receipt = MediaKitExecutionReceipt(
        capability_domain=prepared.capability.domain,
        capability_tool=prepared.capability.tool,
        cli_version=prepared.capability.cli_version,
        schema_sha256=prepared.capability.schema_sha256,
        execution_mode="local",
        request_sha256=prepared.input_sha256,
        source_content_sha256=expected_source_sha256,
        client_token_sha256=prepared.client_token_sha256,
        output_sha256=materialized.execution_output_sha256,
        completed_at=materialized.completed_at,
        cloud_processing_approved=False,
    )
    production_binding = build_media_production_binding(
        production_plan_artifact=production_plan_artifact,
        operation_id=operation.operation_id,
        production_action_ids=operation.production_action_ids,
        assembly_step_ids=operation.assembly_step_ids,
        plan_asset_ids=operation.plan_asset_ids,
        capability_domain=operation.capability_domain,
        capability_tool=operation.capability_tool,
        expected_schema_sha256=operation.expected_schema_sha256,
        arguments_sha256=operation.arguments_sha256,
        input_asset_artifacts=(input_asset_artifact,),
    )
    draft = MediaArtifactDraft(
        stage=operation.stage,
        storage_ref=materialized.artifact_ref,
        media_sha256=materialized.content_sha256,
        mime_type=materialized.content_type,
        size_bytes=materialized.size_bytes,
        duration_seconds=None,
        qc_status="passed",
        qc_checks=(
            MediaQCCheck(
                name="mediakit-local-output-readable",
                status="passed",
                observation="The copied local output passed the configured media quality check.",
            ),
        ),
        limitations=("The local artifact still requires review in its target platform presentation.",),
    )
    return seal_media_artifact(
        project=project,
        draft=draft,
        production_plan_artifact=production_plan_artifact,
        execution=execution_receipt,
        source_thread_id=source_thread_id,
        source_run_id=source_run_id,
        input_asset_artifacts=(input_asset_artifact,),
        production_binding=production_binding,
    )


__all__ = [
    "MediaKitLocalProductionOperation",
    "execute_local_media_operation",
]
