from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import ROUND_CEILING, Decimal
from typing import Any

from pydantic import Field, field_validator, model_validator

from deerflow.incubation.contracts import ArtifactEnvelope, IncubationContract, NonEmptyStr, ProjectRef
from deerflow.incubation.media import MediaObservationSnapshot

from .driver import mediakit_cloud_operation_sha256
from .enhance_video import MediaKitFeeQuote


def _canonical_sha256(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _aware_utc(value: datetime, *, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value.astimezone(UTC)


class MediaKitCloudApprovalRequest(IncubationContract):
    """One server-generated MediaKit quote that a user may explicitly approve."""

    operation_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    capability_domain: NonEmptyStr = Field(max_length=64)
    capability_tool: NonEmptyStr = Field(max_length=64)
    capability_schema_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    capability_arguments_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    pricing_evidence_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    fee_quote_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_duration_milliseconds: int = Field(gt=0)
    output_resolution_tier: NonEmptyStr = Field(max_length=16)
    output_fps: float = Field(gt=0)
    tool_version: NonEmptyStr = Field(max_length=64)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    amount_micros_per_minute: int = Field(gt=0)
    estimated_amount_micros: int = Field(gt=0)
    maximum_amount_micros: int = Field(gt=0)
    provider_hard_cap_supported: bool
    quoted_at: datetime
    valid_until: datetime

    @field_validator("quoted_at", "valid_until")
    @classmethod
    def normalize_timestamps(cls, value: datetime, info) -> datetime:
        return _aware_utc(value, name=info.field_name)

    @model_validator(mode="after")
    def validate_quote_window(self) -> MediaKitCloudApprovalRequest:
        if self.valid_until <= self.quoted_at:
            raise ValueError("MediaKit approval request must expire after it is quoted")
        if self.estimated_amount_micros > self.maximum_amount_micros:
            raise ValueError("MediaKit fee estimate exceeds the approval maximum")
        return self

    @classmethod
    def from_quote(
        cls,
        *,
        project: ProjectRef,
        quote: MediaKitFeeQuote,
        operation_arguments: Mapping[str, Any],
        source_content_sha256: str,
        quoted_at: datetime,
    ) -> MediaKitCloudApprovalRequest:
        if not isinstance(project, ProjectRef):
            raise ValueError("project must be a typed project reference")
        if not isinstance(quote, MediaKitFeeQuote):
            raise ValueError("quote must be a server-generated MediaKit fee quote")
        arguments = dict(operation_arguments)
        capability_arguments = arguments.get("capability_arguments")
        if not isinstance(capability_arguments, Mapping):
            raise ValueError("MediaKit operation requires capability arguments")
        if any(arguments.get(name) != value for name, value in quote.as_operation_fields().items()):
            raise ValueError("MediaKit operation does not match quote fields")
        expected_identity = {
            "project_id": project.project_id,
            "source_content_sha256": source_content_sha256,
            "capability_domain": quote.output_policy.capability_domain,
            "capability_tool": quote.output_policy.capability_tool,
            "expected_schema_sha256": quote.capability_schema_sha256,
            "currency": quote.currency,
            "maximum_amount_micros": quote.maximum_amount_micros,
        }
        if any(arguments.get(name) != value for name, value in expected_identity.items()):
            raise ValueError("MediaKit operation identity does not match the quote")
        if _canonical_sha256(dict(capability_arguments)) != quote.capability_arguments_sha256:
            raise ValueError("MediaKit capability arguments do not match the quote")
        return cls(
            operation_sha256=mediakit_cloud_operation_sha256(arguments),
            capability_domain=quote.output_policy.capability_domain,
            capability_tool=quote.output_policy.capability_tool,
            capability_schema_sha256=quote.capability_schema_sha256,
            capability_arguments_sha256=quote.capability_arguments_sha256,
            pricing_evidence_sha256=quote.pricing_evidence_sha256,
            fee_quote_sha256=quote.fee_quote_sha256,
            source_content_sha256=source_content_sha256,
            source_duration_milliseconds=quote.source_duration_milliseconds,
            output_resolution_tier=quote.output_resolution_tier,
            output_fps=quote.output_fps,
            tool_version=quote.tool_version,
            currency=quote.currency,
            amount_micros_per_minute=quote.amount_micros_per_minute,
            estimated_amount_micros=quote.estimated_amount_micros,
            maximum_amount_micros=quote.maximum_amount_micros,
            provider_hard_cap_supported=quote.provider_hard_cap_supported,
            quoted_at=quoted_at,
            valid_until=quote.valid_until,
        )


def seal_mediakit_cloud_approval_request(
    *,
    project: ProjectRef,
    request: MediaKitCloudApprovalRequest,
    media_observation_artifact: ArtifactEnvelope,
    source_thread_id: str,
    source_run_id: str,
) -> ArtifactEnvelope:
    request = MediaKitCloudApprovalRequest.model_validate(request.model_dump(mode="python"))
    if media_observation_artifact.project != project:
        raise ValueError("MediaKit approval request project must match its observation")
    if media_observation_artifact.artifact_type != "media_observation":
        raise ValueError("MediaKit approval request requires a media observation")
    if media_observation_artifact.evidence_role != "user_material":
        raise ValueError("MediaKit cloud approval requires user-authorized material")
    if len(media_observation_artifact.parents) != 1 or media_observation_artifact.parents[0].artifact_type != "media_source_receipt":
        raise ValueError("MediaKit observation requires source receipt lineage")
    observation = MediaObservationSnapshot.model_validate(media_observation_artifact.payload)
    if observation.execution.source_content_sha256 != request.source_content_sha256:
        raise ValueError("MediaKit approval source content does not match its observation")
    duration_milliseconds = int((Decimal(str(observation.observation.format_meta.duration)) * Decimal(1000)).to_integral_value(rounding=ROUND_CEILING))
    if duration_milliseconds != request.source_duration_milliseconds:
        raise ValueError("MediaKit approval duration does not match its observation")
    if request.quoted_at < observation.observed_at:
        raise ValueError("MediaKit approval cannot predate its observation")
    return ArtifactEnvelope.seal(
        project=project,
        artifact_type="mediakit_cloud_approval_request",
        version=1,
        payload=request.model_dump(mode="json"),
        parents=(media_observation_artifact.to_parent_ref(),),
        created_at=request.quoted_at,
        source_thread_id=source_thread_id,
        source_run_id=source_run_id,
    )


__all__ = [
    "MediaKitCloudApprovalRequest",
    "seal_mediakit_cloud_approval_request",
]
