from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from deerflow.incubation import ArtifactEnvelope, ProjectRef
from deerflow.incubation.media import MediaObservationSnapshot, MediaSourceReceipt

from .approval_request import MediaKitCloudApprovalRequest, seal_mediakit_cloud_approval_request
from .enhance_video import (
    MediaKitEnhanceVideoPreflight,
    MediaKitPricingEvidence,
    MediaKitPricingRate,
)
from .router import MediaKitCapabilityRouter

_MAX_PRICING_DOCUMENT_BYTES = 64 * 1024


class MediaKitPricingConfigurationError(RuntimeError):
    """Bounded failure for missing, invalid, or drifted pricing configuration."""


class _PricingRateDocument(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    tool_version: str = Field(min_length=1, max_length=64)
    resolution_tier: str = Field(min_length=1, max_length=16)
    maximum_fps: float = Field(gt=0)
    amount_micros_per_minute: int = Field(gt=0)


class _PricingEvidenceDocument(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    provider: str = Field(min_length=1, max_length=128)
    capability_domain: str = Field(min_length=1, max_length=64)
    capability_tool: str = Field(min_length=1, max_length=64)
    currency: str = Field(pattern=r"^[A-Za-z]{3}$")
    source_url: str = Field(min_length=1, max_length=2048)
    document_id: str = Field(min_length=1, max_length=128)
    document_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    document_updated_at: datetime
    checked_at: datetime
    valid_until: datetime
    provider_hard_cap_supported: bool
    rates: tuple[_PricingRateDocument, ...] = Field(min_length=1, max_length=64)

    @field_validator("document_updated_at", "checked_at", "valid_until")
    @classmethod
    def require_aware_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("pricing timestamps must be timezone-aware")
        return value.astimezone(UTC)

    def to_evidence(self) -> MediaKitPricingEvidence:
        return MediaKitPricingEvidence(
            provider=self.provider,
            capability_domain=self.capability_domain,
            capability_tool=self.capability_tool,
            currency=self.currency,
            source_url=self.source_url,
            document_id=self.document_id,
            document_sha256=self.document_sha256,
            document_updated_at=self.document_updated_at,
            checked_at=self.checked_at,
            valid_until=self.valid_until,
            provider_hard_cap_supported=self.provider_hard_cap_supported,
            rates=tuple(
                MediaKitPricingRate(
                    tool_version=rate.tool_version,
                    resolution_tier=rate.resolution_tier,
                    maximum_fps=rate.maximum_fps,
                    amount_micros_per_minute=rate.amount_micros_per_minute,
                )
                for rate in self.rates
            ),
        )


def _read_pricing_evidence(path: Path) -> MediaKitPricingEvidence:
    try:
        stat = path.stat()
        if not path.is_file() or stat.st_size <= 0 or stat.st_size > _MAX_PRICING_DOCUMENT_BYTES:
            raise MediaKitPricingConfigurationError("MediaKit pricing evidence is unavailable")
        payload = json.loads(path.read_text(encoding="utf-8"))
        document = _PricingEvidenceDocument.model_validate(payload)
        return document.to_evidence()
    except MediaKitPricingConfigurationError:
        raise
    except (OSError, UnicodeError):
        raise MediaKitPricingConfigurationError("MediaKit pricing evidence is unavailable") from None
    except (json.JSONDecodeError, ValidationError, TypeError, ValueError):
        raise MediaKitPricingConfigurationError("MediaKit pricing evidence is invalid") from None


class MediaKitEnhanceVideoQuoteService:
    """Create an immutable approval request without uploading or starting work."""

    def __init__(
        self,
        *,
        capability_router: MediaKitCapabilityRouter,
        pricing_evidence_path: str | Path,
        expected_schema_sha256: str,
        allowed_tool_versions: set[str],
        allowed_resolution_tiers: set[str],
        minimum_fps: float,
        maximum_fps: float,
        maximum_output_bytes: int,
    ) -> None:
        self._capability_router = capability_router
        self._pricing_evidence_path = Path(pricing_evidence_path).expanduser().resolve()
        self._expected_schema_sha256 = expected_schema_sha256
        self._allowed_tool_versions = frozenset(allowed_tool_versions)
        self._allowed_resolution_tiers = frozenset(allowed_resolution_tiers)
        self._minimum_fps = minimum_fps
        self._maximum_fps = maximum_fps
        self._maximum_output_bytes = maximum_output_bytes

    @property
    def pricing_evidence_path(self) -> Path:
        return self._pricing_evidence_path

    async def prepare_approval_request(
        self,
        *,
        project: ProjectRef,
        media_observation_artifact: ArtifactEnvelope,
        source_receipt_artifact: ArtifactEnvelope,
        capability_arguments: dict[str, Any],
        maximum_amount_micros: int,
        quoted_at: datetime,
        source_run_id: str,
    ) -> ArtifactEnvelope:
        observation = self._validate_lineage(
            project=project,
            media_observation_artifact=media_observation_artifact,
            source_receipt_artifact=source_receipt_artifact,
        )
        source_receipt = MediaSourceReceipt.model_validate(source_receipt_artifact.payload)
        pricing = await asyncio.to_thread(
            _read_pricing_evidence,
            self._pricing_evidence_path,
        )
        capability = await self._capability_router.discover_capability(
            "video",
            "enhance-video",
        )
        if capability.schema_sha256 != self._expected_schema_sha256:
            raise MediaKitPricingConfigurationError("MediaKit capability schema changed")
        preflight = MediaKitEnhanceVideoPreflight(
            expected_schema_sha256=self._expected_schema_sha256,
            pricing=pricing,
            allowed_tool_versions=self._allowed_tool_versions,
            allowed_resolution_tiers=self._allowed_resolution_tiers,
            minimum_fps=self._minimum_fps,
            maximum_fps=self._maximum_fps,
            maximum_output_bytes=self._maximum_output_bytes,
        )
        arguments = dict(capability_arguments)
        quote = preflight.quote(
            capability=capability,
            source_metadata=observation.observation,
            capability_arguments=arguments,
            maximum_amount_micros=maximum_amount_micros,
            now=quoted_at,
        )
        source_content_sha256 = observation.execution.source_content_sha256
        if source_content_sha256 is None:
            raise ValueError("MediaKit quote requires observed source content")
        operation_arguments = {
            "project_id": project.project_id,
            "source_ref": source_receipt.source_ref,
            "source_content_sha256": source_content_sha256,
            "rights_ref": source_receipt.rights_ref,
            "capability_domain": capability.domain,
            "capability_tool": capability.tool,
            "capability_arguments": arguments,
            "expected_schema_sha256": capability.schema_sha256,
            "currency": quote.currency,
            "maximum_amount_micros": quote.maximum_amount_micros,
            **quote.as_operation_fields(),
        }
        request = MediaKitCloudApprovalRequest.from_quote(
            project=project,
            quote=quote,
            operation_arguments=operation_arguments,
            source_content_sha256=source_content_sha256,
            quoted_at=quoted_at,
        )
        return seal_mediakit_cloud_approval_request(
            project=project,
            request=request,
            media_observation_artifact=media_observation_artifact,
            source_thread_id=media_observation_artifact.source_thread_id,
            source_run_id=source_run_id,
        )

    @staticmethod
    def _validate_lineage(
        *,
        project: ProjectRef,
        media_observation_artifact: ArtifactEnvelope,
        source_receipt_artifact: ArtifactEnvelope,
    ) -> MediaObservationSnapshot:
        if media_observation_artifact.project != project or source_receipt_artifact.project != project:
            raise ValueError("MediaKit quote project does not match its source")
        if media_observation_artifact.artifact_type != "media_observation" or media_observation_artifact.version != 1:
            raise ValueError("MediaKit quote requires a media observation")
        if source_receipt_artifact.artifact_type != "media_source_receipt" or source_receipt_artifact.version != 1:
            raise ValueError("MediaKit quote requires a media source receipt")
        if media_observation_artifact.evidence_role != "user_material" or source_receipt_artifact.evidence_role != "user_material":
            raise ValueError("MediaKit cloud quote requires user-authorized material")
        if media_observation_artifact.parents != (source_receipt_artifact.to_parent_ref(),):
            raise ValueError("MediaKit quote source receipt does not match its observation")
        observation = MediaObservationSnapshot.model_validate(media_observation_artifact.payload)
        source_receipt = MediaSourceReceipt.model_validate(source_receipt_artifact.payload)
        if observation.source_ref != source_receipt.source_ref:
            raise ValueError("MediaKit quote source receipt does not match its observation")
        return observation


__all__ = [
    "MediaKitEnhanceVideoQuoteService",
    "MediaKitPricingConfigurationError",
]
