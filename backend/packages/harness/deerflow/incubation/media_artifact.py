from __future__ import annotations

import hashlib
import json
import re
from typing import Literal

from pydantic import Field, field_validator, model_validator

from deerflow.incubation.contracts import (
    ArtifactEnvelope,
    ArtifactParentRef,
    IncubationContract,
    NonEmptyStr,
    ProjectRef,
)
from deerflow.incubation.media import (
    MediaKitExecutionReceipt,
    MediaObservationSnapshot,
)
from deerflow.incubation.production_plan import ProductionPlan

MediaArtifactStage = Literal["intermediate", "final"]
MediaQCCheckStatus = Literal["passed", "warning", "failed"]
MediaQCSummary = Literal["passed", "passed_with_warnings", "failed", "not_run"]

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_ARTIFACT_REF = re.compile(r"^artifact://[A-Za-z0-9][A-Za-z0-9._:-]*(?:/[A-Za-z0-9][A-Za-z0-9._:-]*)*$")
_MIME_TYPE = re.compile(r"^[a-z0-9][a-z0-9!#$&^_.+-]*/[a-z0-9][a-z0-9!#$&^_.+-]*$")


def _canonical_sha256(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _validate_sha256(value: str, *, name: str) -> str:
    if not _SHA256.fullmatch(value):
        raise ValueError(f"{name} must be a lowercase SHA-256 digest")
    return value


class MediaQCCheck(IncubationContract):
    name: NonEmptyStr = Field(max_length=128)
    status: MediaQCCheckStatus
    observation: NonEmptyStr = Field(max_length=2000)


class MediaArtifactDraft(IncubationContract):
    """Deterministic output metadata and QC, without execution locators."""

    stage: MediaArtifactStage
    storage_ref: NonEmptyStr = Field(max_length=1024)
    media_sha256: NonEmptyStr
    mime_type: NonEmptyStr = Field(max_length=128)
    size_bytes: int = Field(gt=0)
    duration_seconds: float | None = Field(default=None, ge=0)
    qc_status: MediaQCSummary = "not_run"
    qc_checks: tuple[MediaQCCheck, ...] = ()
    limitations: tuple[NonEmptyStr, ...] = ()

    @field_validator("storage_ref")
    @classmethod
    def require_stable_internal_reference(cls, value: str) -> str:
        if not _ARTIFACT_REF.fullmatch(value):
            raise ValueError("storage_ref must be a stable artifact:// reference")
        return value

    @field_validator("media_sha256")
    @classmethod
    def validate_media_sha256(cls, value: str) -> str:
        return _validate_sha256(value, name="media_sha256")

    @field_validator("mime_type")
    @classmethod
    def normalize_mime_type(cls, value: str) -> str:
        normalized = value.casefold()
        if not _MIME_TYPE.fullmatch(normalized):
            raise ValueError("mime_type must be a valid MIME type without parameters")
        return normalized

    @model_validator(mode="after")
    def validate_qc_summary(self) -> MediaArtifactDraft:
        statuses = {check.status for check in self.qc_checks}
        if self.qc_status == "not_run":
            if self.qc_checks:
                raise ValueError("not-run QC cannot contain completed checks")
        elif self.qc_status == "passed":
            if not self.qc_checks or statuses != {"passed"}:
                raise ValueError("passed QC requires only passed checks")
        elif self.qc_status == "passed_with_warnings":
            if "warning" not in statuses or "failed" in statuses:
                raise ValueError("warning QC requires a warning and no failed checks")
        elif "failed" not in statuses:
            raise ValueError("failed QC requires at least one failed check")
        return self


class MediaInputBinding(IncubationContract):
    artifact_ref: ArtifactParentRef
    media_sha256: NonEmptyStr

    @field_validator("media_sha256")
    @classmethod
    def validate_media_sha256(cls, value: str) -> str:
        return _validate_sha256(value, name="input media_sha256")


class MediaArtifact(MediaArtifactDraft):
    content_sha256: NonEmptyStr
    production_plan_ref: ArtifactParentRef
    input_assets: tuple[MediaInputBinding, ...] = ()
    input_set_sha256: NonEmptyStr
    execution: MediaKitExecutionReceipt

    @field_validator("content_sha256", "input_set_sha256")
    @classmethod
    def validate_content_hashes(cls, value: str, info) -> str:
        return _validate_sha256(value, name=info.field_name)

    @field_validator("input_assets")
    @classmethod
    def canonicalize_inputs(
        cls,
        value: tuple[MediaInputBinding, ...],
    ) -> tuple[MediaInputBinding, ...]:
        if len({item.artifact_ref.artifact_id for item in value}) != len(value):
            raise ValueError("media input artifacts must be unique")
        return tuple(sorted(value, key=lambda item: item.artifact_ref.artifact_id))

    @model_validator(mode="after")
    def validate_input_set_digest(self) -> MediaArtifact:
        expected = _canonical_sha256([item.model_dump(mode="json") for item in self.input_assets])
        if self.input_set_sha256 != expected:
            raise ValueError("input_set_sha256 does not match exact input bindings")
        return self


def _input_media_sha256(artifact: ArtifactEnvelope) -> str:
    if artifact.artifact_type == "media_observation":
        observation = MediaObservationSnapshot.model_validate(artifact.payload)
        digest = observation.execution.source_content_sha256
        if digest is None:
            raise ValueError("media observation input requires a source content hash")
        return digest
    if artifact.artifact_type == "media_artifact":
        return MediaArtifact.model_validate(artifact.payload).media_sha256
    raise ValueError("media input must be a media_observation or media_artifact")


def seal_media_artifact(
    *,
    project: ProjectRef,
    draft: MediaArtifactDraft,
    production_plan_artifact: ArtifactEnvelope,
    execution: MediaKitExecutionReceipt,
    source_thread_id: str,
    source_run_id: str,
    input_asset_artifacts: tuple[ArtifactEnvelope, ...] = (),
) -> ArtifactEnvelope:
    """Seal a produced media receipt without exposing execution-only locators."""

    if production_plan_artifact.project != project:
        raise ValueError("production plan parent project must match media artifact project")
    if production_plan_artifact.artifact_type != "production_plan":
        raise ValueError("media artifact requires a production_plan parent")
    plan = ProductionPlan.model_validate(production_plan_artifact.payload)
    plan_parent_refs = set(production_plan_artifact.parents)
    required_plan_refs = {
        plan.adapted_draft_ref,
        plan.format_decision_ref,
        *plan.user_material_refs,
    }
    if not required_plan_refs.issubset(plan_parent_refs):
        raise ValueError("production plan envelope is missing an exact declared parent")

    input_bindings: list[MediaInputBinding] = []
    seen_ids: set[str] = set()
    for artifact in input_asset_artifacts:
        if artifact.project != project:
            raise ValueError("media input project must match media artifact project")
        if artifact.artifact_id in seen_ids:
            raise ValueError("media input artifacts must be unique")
        seen_ids.add(artifact.artifact_id)
        artifact_ref = artifact.to_parent_ref()
        if artifact.artifact_type == "media_observation":
            if artifact.evidence_role != "user_material":
                raise ValueError("media observation input requires the user_material evidence role")
            if artifact_ref not in plan.user_material_refs:
                raise ValueError("media observation input is not authorized by the production plan")
        elif artifact.artifact_type == "media_artifact":
            prior_output = MediaArtifact.model_validate(artifact.payload)
            if prior_output.production_plan_ref != production_plan_artifact.to_parent_ref():
                raise ValueError("media artifact input must come from the same production plan")
        input_bindings.append(
            MediaInputBinding(
                artifact_ref=artifact_ref,
                media_sha256=_input_media_sha256(artifact),
            )
        )
    canonical_inputs = tuple(sorted(input_bindings, key=lambda item: item.artifact_ref.artifact_id))
    input_hashes = {item.media_sha256 for item in canonical_inputs}
    if canonical_inputs:
        if execution.source_content_sha256 not in input_hashes:
            raise ValueError("execution source content hash must match an exact input asset")
    elif execution.source_content_sha256 is not None:
        raise ValueError("execution source content hash requires an exact input asset")

    artifact = MediaArtifact(
        **draft.model_dump(),
        content_sha256=plan.adapted_body_sha256,
        production_plan_ref=production_plan_artifact.to_parent_ref(),
        input_assets=canonical_inputs,
        input_set_sha256=_canonical_sha256([item.model_dump(mode="json") for item in canonical_inputs]),
        execution=execution,
    )
    return ArtifactEnvelope.seal(
        project=project,
        artifact_type="media_artifact",
        version=1,
        payload=artifact.model_dump(mode="json"),
        parents=(
            production_plan_artifact.to_parent_ref(),
            *(item.artifact_ref for item in canonical_inputs),
        ),
        created_at=execution.completed_at,
        source_thread_id=source_thread_id,
        source_run_id=source_run_id,
    )


__all__ = [
    "MediaArtifact",
    "MediaArtifactDraft",
    "MediaArtifactStage",
    "MediaInputBinding",
    "MediaQCCheck",
    "MediaQCCheckStatus",
    "MediaQCSummary",
    "seal_media_artifact",
]
