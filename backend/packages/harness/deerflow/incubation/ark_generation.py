from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import ConfigDict, Field, field_validator, model_validator

from deerflow.incubation.contracts import (
    ArtifactEnvelope,
    ArtifactParentRef,
    IncubationContract,
    NonEmptyStr,
)
from deerflow.incubation.production_plan import ProductionPlan

ArkGenerationStatus = Literal[
    "queued",
    "running",
    "succeeded",
    "failed",
    "cancelled",
]

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_STABLE_PROVIDER_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,254}$")
_SAFE_PARAMETER_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,31}$")
_LOCATOR = re.compile(
    r"(?:https?://|(?:s3|gs|oss|cos|obs|r2|az|tos|file)://|data:)|"
    r"(?<!\S)(?:/Users/|/home/|/tmp/|/var/|/private/|/mnt/|/opt/|/etc/|/root/|/srv/|/Volumes/|~/|\./|\.\./|\\\\|[A-Za-z]:[\\/])\S+",
    re.IGNORECASE,
)
_CREDENTIAL = re.compile(
    r"(?:\bBearer\s+\S+)|"
    r"(?:(?:\b(?:api[\s_-]?key|access[\s_-]?key|secret|token|password|authorization)\b|(?:访问)?(?:密钥|令牌|口令))"
    r"\s*(?::|=|\bis\b|是|为)\s*\S+)",
    re.IGNORECASE,
)
_REFERENCE_FILE = re.compile(
    r"@\S+\.(?:avif|gif|jpe?g|m4a|mov|mp3|mp4|png|wav|webm|webp)\b",
    re.IGNORECASE,
)
_SECRET_TOKEN = re.compile(
    r"\b(?:ark|sk)-[A-Za-z0-9_-]{8,}\b",
    re.IGNORECASE,
)
_ASCII_SECRET_CANDIDATE = re.compile(r"(?<![A-Za-z0-9_-])[A-Za-z0-9_-]{32,128}(?![A-Za-z0-9_-])")


def _contains_credential(value: str) -> bool:
    if _CREDENTIAL.search(value) or _SECRET_TOKEN.search(value):
        return True
    return any(any(character.isupper() for character in token) and any(character.islower() for character in token) and any(character.isdigit() for character in token) for token in _ASCII_SECRET_CANDIDATE.findall(value))


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


def _validate_provider_id(value: str, *, name: str) -> str:
    if _contains_credential(value):
        raise ValueError(f"{name} cannot contain a credential")
    if not _STABLE_PROVIDER_ID.fullmatch(value):
        raise ValueError(f"{name} must be a stable non-locator identifier")
    return value


class ArkTextToVideoParameters(IncubationContract):
    """Closed V1 parameter projection; provider escape hatches are absent by design."""

    model_config = ConfigDict(hide_input_in_errors=True)

    ratio: str = Field(max_length=32)
    resolution: str = Field(max_length=32)
    duration: int = Field(ge=1, le=60)
    seed: int | None = Field(default=None, ge=0, le=4_294_967_295)
    watermark: bool | None = None
    generate_audio: bool | None = None
    camera_fixed: bool | None = None
    draft: bool | None = None
    priority: int | None = Field(default=None, ge=0, le=9)

    @field_validator("ratio", "resolution")
    @classmethod
    def validate_safe_tokens(cls, value: str, info) -> str:
        if not _SAFE_PARAMETER_TOKEN.fullmatch(value):
            raise ValueError(f"{info.field_name} must be a bounded provider parameter token")
        return value

    def supplied(self) -> dict[str, str | int | bool]:
        return self.model_dump(mode="python", exclude_none=True)


class ArkTextToVideoOperationDraft(IncubationContract):
    model_config = ConfigDict(hide_input_in_errors=True)

    schema_version: Literal["v6-ark-text-to-video-operation-v1"] = "v6-ark-text-to-video-operation-v1"
    operation_id: NonEmptyStr = Field(max_length=128)
    production_action_id: NonEmptyStr = Field(max_length=128)
    plan_asset_id: NonEmptyStr = Field(max_length=128)
    assembly_step_id: NonEmptyStr = Field(max_length=128)
    prompt: NonEmptyStr = Field(max_length=12_000)
    model: NonEmptyStr = Field(max_length=255)
    parameters: ArkTextToVideoParameters

    @field_validator("prompt")
    @classmethod
    def reject_execution_only_prompt_material(cls, value: str) -> str:
        if _LOCATOR.search(value) or _REFERENCE_FILE.search(value) or _contains_credential(value):
            raise ValueError("Ark prompt cannot contain execution-only material")
        return value

    @field_validator("model")
    @classmethod
    def validate_model_identifier(cls, value: str) -> str:
        if _contains_credential(value):
            raise ValueError("Ark model cannot contain a credential")
        return _validate_provider_id(value, name="Ark model")


class ArkTextToVideoOperation(ArkTextToVideoOperationDraft):
    production_plan_ref: ArtifactParentRef
    operation_sha256: str

    @field_validator("operation_sha256")
    @classmethod
    def validate_operation_sha256(cls, value: str) -> str:
        return _validate_sha256(value, name="operation_sha256")

    @model_validator(mode="after")
    def validate_operation_digest(self) -> ArkTextToVideoOperation:
        expected = _canonical_sha256(
            self.model_dump(
                mode="json",
                exclude={"operation_sha256"},
            )
        )
        if self.operation_sha256 != expected:
            raise ValueError("operation_sha256 does not match the exact Ark operation")
        return self

    @classmethod
    def seal(cls, **values: Any) -> ArkTextToVideoOperation:
        allowed = set(ArkTextToVideoOperationDraft.model_fields) | {"production_plan_ref"}
        if set(values) != allowed:
            raise ValueError("Ark operation seal input has an invalid contract")
        draft = ArkTextToVideoOperationDraft.model_validate({name: values[name] for name in ArkTextToVideoOperationDraft.model_fields})
        plan_ref = ArtifactParentRef.model_validate(values["production_plan_ref"])
        payload = {
            **draft.model_dump(mode="json"),
            "production_plan_ref": plan_ref.model_dump(mode="json"),
        }
        return cls.model_validate(
            {
                **payload,
                "operation_sha256": _canonical_sha256(payload),
            }
        )


class ArkGenerationTaskSnapshot(IncubationContract):
    """Durable-safe provider projection; raw output locators never enter it."""

    model_config = ConfigDict(hide_input_in_errors=True)

    schema_version: Literal["v6-ark-generation-task-snapshot-v1"] = "v6-ark-generation-task-snapshot-v1"
    operation_sha256: str
    provider_task_id: NonEmptyStr = Field(max_length=255)
    selected_model: NonEmptyStr = Field(max_length=255)
    status: ArkGenerationStatus
    provider_result_sha256: str
    updated_at: datetime

    @field_validator("operation_sha256", "provider_result_sha256")
    @classmethod
    def validate_digests(cls, value: str, info) -> str:
        return _validate_sha256(value, name=info.field_name)

    @field_validator("provider_task_id", "selected_model")
    @classmethod
    def validate_provider_identifiers(cls, value: str, info) -> str:
        return _validate_provider_id(value, name=info.field_name)

    @field_validator("updated_at")
    @classmethod
    def normalize_updated_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("updated_at must be timezone-aware")
        return value.astimezone(UTC)


def prepare_ark_text_to_video_operation(
    *,
    production_plan_artifact: ArtifactEnvelope,
    draft: ArkTextToVideoOperationDraft,
) -> ArkTextToVideoOperation:
    """Bind one text-to-video request to the exact, closed V1 plan graph."""

    if production_plan_artifact.artifact_type != "production_plan":
        raise ValueError("Ark generation requires a ProductionPlan artifact")
    plan = ProductionPlan.model_validate(production_plan_artifact.payload)
    if plan.status != "ready":
        raise ValueError("Ark generation requires a ready ProductionPlan")
    if plan.user_material_refs:
        raise ValueError("Ark text-to-video V1 cannot use reference materials")

    if len(plan.asset_requirements) != 1:
        raise ValueError("Ark text-to-video V1 requires exactly one asset")
    if len(plan.production_actions) != 1:
        raise ValueError("Ark text-to-video V1 requires exactly one production action")
    if len(plan.assembly_steps) != 1:
        raise ValueError("Ark text-to-video V1 requires exactly one assembly step")

    asset = plan.asset_requirements[0]
    action = plan.production_actions[0]
    step = plan.assembly_steps[0]
    if asset.kind != "video":
        raise ValueError("Ark text-to-video V1 requires one video asset")
    if asset.source != "to_create":
        raise ValueError("Ark text-to-video V1 asset must use to_create")
    if action.kind != "media_generation":
        raise ValueError("Ark text-to-video V1 action must use media_generation")
    if action.asset_ids != (asset.asset_id,):
        raise ValueError("Ark media_generation action must bind only the generated video asset")
    if step.input_asset_ids != (asset.asset_id,):
        raise ValueError("Ark assembly step must bind only the generated video asset")

    if draft.production_action_id != action.action_id:
        raise ValueError("Ark operation must select the exact production action")
    if draft.plan_asset_id != asset.asset_id:
        raise ValueError("Ark operation must select the exact plan asset")
    if draft.assembly_step_id != step.step_id:
        raise ValueError("Ark operation must select the exact assembly step")

    expected_parents = {plan.adapted_draft_ref, plan.format_decision_ref}
    if set(production_plan_artifact.parents) != expected_parents:
        raise ValueError("Ark ProductionPlan must retain its exact parents")

    return ArkTextToVideoOperation.seal(
        **draft.model_dump(mode="python"),
        production_plan_ref=production_plan_artifact.to_parent_ref(),
    )


__all__ = [
    "ArkGenerationStatus",
    "ArkGenerationTaskSnapshot",
    "ArkTextToVideoOperation",
    "ArkTextToVideoOperationDraft",
    "ArkTextToVideoParameters",
    "prepare_ark_text_to_video_operation",
]
