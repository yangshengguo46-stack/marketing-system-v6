from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, Never
from urllib.parse import urlparse

from pydantic import Field, field_validator, model_validator

from deerflow.incubation.contracts import (
    ArtifactEnvelope,
    ArtifactParentRef,
    EvidenceRole,
    IncubationContract,
    NonEmptyStr,
    ProjectRef,
)

if TYPE_CHECKING:
    from deerflow.community.mediakit.contracts import MediaKitExecutionResult

MediaKind = Literal["video"]
MediaTransport = Literal["direct_http", "local_file"]


def _require_text(value: str, *, name: str, maximum: int) -> str:
    normalized = value.strip()
    if not normalized or len(normalized) > maximum:
        raise ValueError(f"{name} must contain between 1 and {maximum} characters")
    return normalized


def _aware_utc(value: datetime, *, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value.astimezone(UTC)


@dataclass(frozen=True, slots=True, repr=False)
class EphemeralMediaSource:
    """An execution-only locator that must never enter model or ledger payloads."""

    source_ref: str
    transport: MediaTransport
    locator: str = field(repr=False)
    rights_ref: str
    resolver: str
    content_type: str | None = None
    expires_at: datetime | None = None
    media_kind: MediaKind = "video"

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "source_ref",
            _require_text(self.source_ref, name="source_ref", maximum=255),
        )
        object.__setattr__(
            self,
            "rights_ref",
            _require_text(self.rights_ref, name="rights_ref", maximum=255),
        )
        object.__setattr__(
            self,
            "resolver",
            _require_text(self.resolver, name="resolver", maximum=128),
        )
        if self.transport == "direct_http":
            parsed = urlparse(self.locator)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ValueError("direct media locator must use http or https")
            if parsed.username or parsed.password:
                raise ValueError("direct media locator must not contain credentials")
            content_type = (self.content_type or "").split(";", maxsplit=1)[0].strip().casefold()
            if not content_type.startswith("video/"):
                raise ValueError("direct media locator requires a verified video content type")
            object.__setattr__(self, "content_type", content_type)
        elif self.transport == "local_file":
            path = Path(self.locator).expanduser()
            if not path.is_absolute() or not path.is_file():
                raise ValueError("local media locator must be an existing absolute file")
            object.__setattr__(self, "locator", str(path.resolve()))
        else:
            raise ValueError("unsupported media transport")
        if self.expires_at is not None:
            object.__setattr__(
                self,
                "expires_at",
                _aware_utc(self.expires_at, name="expires_at"),
            )

    @classmethod
    def direct_http(
        cls,
        *,
        source_ref: str,
        locator: str,
        rights_ref: str,
        resolver: str,
        content_type: str,
        expires_at: datetime | None = None,
    ) -> EphemeralMediaSource:
        return cls(
            source_ref=source_ref,
            transport="direct_http",
            locator=locator,
            rights_ref=rights_ref,
            resolver=resolver,
            content_type=content_type,
            expires_at=expires_at,
        )

    @classmethod
    def local_file(
        cls,
        *,
        source_ref: str,
        locator: str | Path,
        rights_ref: str,
        resolver: str,
    ) -> EphemeralMediaSource:
        return cls(
            source_ref=source_ref,
            transport="local_file",
            locator=str(Path(locator).expanduser()),
            rights_ref=rights_ref,
            resolver=resolver,
        )

    @classmethod
    def platform_page(
        cls,
        *,
        source_ref: str,
        locator: str,
        rights_ref: str,
    ) -> Never:
        del source_ref, locator, rights_ref
        raise ValueError("MediaKit requires a resolved direct media URL or local file; a platform page is evidence for a resolver")

    @property
    def locator_sha256(self) -> str:
        return hashlib.sha256(self.locator.encode("utf-8")).hexdigest()

    def __repr__(self) -> str:
        return f"EphemeralMediaSource(source_ref={self.source_ref!r}, transport={self.transport!r}, resolver={self.resolver!r}, locator_sha256={self.locator_sha256!r})"


class MediaSourceReceipt(IncubationContract):
    source_ref: NonEmptyStr = Field(max_length=255)
    media_kind: MediaKind
    transport: MediaTransport
    resolver: NonEmptyStr = Field(max_length=128)
    rights_ref: NonEmptyStr = Field(max_length=255)
    content_type: NonEmptyStr | None = Field(default=None, max_length=128)
    locator_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    resolved_at: datetime
    expires_at: datetime | None = None
    limitations: tuple[NonEmptyStr, ...] = ("The raw media locator is execution-only and is not retained in this receipt.",)

    @field_validator("resolved_at", "expires_at")
    @classmethod
    def normalize_timestamps(cls, value: datetime | None, info) -> datetime | None:
        if value is None:
            return None
        return _aware_utc(value, name=info.field_name)

    @model_validator(mode="after")
    def validate_expiry(self) -> MediaSourceReceipt:
        if self.expires_at is not None and self.expires_at <= self.resolved_at:
            raise ValueError("expires_at must be after resolved_at")
        return self

    @classmethod
    def from_ephemeral(
        cls,
        source: EphemeralMediaSource,
        *,
        resolved_at: datetime,
    ) -> MediaSourceReceipt:
        return cls(
            source_ref=source.source_ref,
            media_kind=source.media_kind,
            transport=source.transport,
            resolver=source.resolver,
            rights_ref=source.rights_ref,
            content_type=source.content_type,
            locator_sha256=source.locator_sha256,
            resolved_at=resolved_at,
            expires_at=source.expires_at,
        )


class VideoFormatMetadata(IncubationContract):
    container: NonEmptyStr = Field(max_length=255)
    duration: float = Field(ge=0)
    size: int = Field(ge=0)
    bitrate: int | None = Field(default=None, ge=0)
    md5: str | None = Field(default=None, pattern=r"^[0-9a-fA-F]{32}$")


class VideoStreamMetadata(IncubationContract):
    codec: NonEmptyStr = Field(max_length=128)
    duration: float = Field(ge=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    fps: float = Field(gt=0)
    bitrate: int | None = Field(default=None, ge=0)
    dynamic_range: NonEmptyStr | None = Field(default=None, max_length=128)


class AudioStreamMetadata(IncubationContract):
    codec: NonEmptyStr = Field(max_length=128)
    duration: float = Field(ge=0)
    channels: int = Field(gt=0)
    sample_rate: int = Field(gt=0)
    bitrate: int | None = Field(default=None, ge=0)


class VideoMetadataObservation(IncubationContract):
    format_meta: VideoFormatMetadata
    video_stream_meta: VideoStreamMetadata | None = None
    audio_stream_meta: AudioStreamMetadata | None = None

    @model_validator(mode="after")
    def require_a_media_stream(self) -> VideoMetadataObservation:
        if self.video_stream_meta is None and self.audio_stream_meta is None:
            raise ValueError("video metadata requires at least one media stream")
        return self

    @classmethod
    def from_mediakit_output(cls, payload: dict[str, Any]) -> VideoMetadataObservation:
        format_meta = payload.get("format_meta")
        if not isinstance(format_meta, dict):
            raise ValueError("MediaKit video metadata output requires format_meta")
        video_stream_meta = payload.get("video_stream_meta")
        audio_stream_meta = payload.get("audio_stream_meta")
        if video_stream_meta is not None and not isinstance(video_stream_meta, dict):
            raise ValueError("MediaKit video_stream_meta must be an object")
        if audio_stream_meta is not None and not isinstance(audio_stream_meta, dict):
            raise ValueError("MediaKit audio_stream_meta must be an object")
        return cls(
            format_meta=VideoFormatMetadata.model_validate(format_meta),
            video_stream_meta=(VideoStreamMetadata.model_validate(video_stream_meta) if video_stream_meta is not None else None),
            audio_stream_meta=(AudioStreamMetadata.model_validate(audio_stream_meta) if audio_stream_meta is not None else None),
        )


class MediaKitExecutionReceipt(IncubationContract):
    capability_domain: NonEmptyStr = Field(max_length=64)
    capability_tool: NonEmptyStr = Field(max_length=64)
    cli_version: NonEmptyStr = Field(max_length=64)
    schema_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    execution_mode: Literal["local", "cloud"]
    request_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_content_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    client_token_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    task_id_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    output_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    completed_at: datetime
    cloud_processing_approved: bool
    fee_authorization_ref: NonEmptyStr | None = Field(default=None, max_length=255)
    status: Literal["completed"] = "completed"
    limitations: tuple[NonEmptyStr, ...] = ("The receipt proves deterministic execution lineage; MediaKit observations are not marketing conclusions.",)

    @field_validator("completed_at")
    @classmethod
    def normalize_completed_at(cls, value: datetime) -> datetime:
        return _aware_utc(value, name="completed_at")

    @model_validator(mode="after")
    def validate_execution_authorization(self) -> MediaKitExecutionReceipt:
        if self.execution_mode == "local":
            if self.cloud_processing_approved:
                raise ValueError("local MediaKit execution cannot claim cloud approval")
            if self.fee_authorization_ref is not None or self.task_id_sha256 is not None:
                raise ValueError("local MediaKit execution cannot carry cloud task authorization")
        elif not self.cloud_processing_approved or self.fee_authorization_ref is None:
            raise ValueError("cloud MediaKit execution requires cloud and fee authorization")
        return self

    @classmethod
    def from_local_execution(
        cls,
        execution: MediaKitExecutionResult,
    ) -> MediaKitExecutionReceipt:
        if execution.prepared.mode != "local":
            raise ValueError("local execution receipt requires local mode")
        capability = execution.prepared.capability
        return cls(
            capability_domain=capability.domain,
            capability_tool=capability.tool,
            cli_version=capability.cli_version,
            schema_sha256=capability.schema_sha256,
            execution_mode="local",
            request_sha256=execution.prepared.input_sha256,
            source_content_sha256=execution.source_content_sha256,
            client_token_sha256=execution.prepared.client_token_sha256,
            output_sha256=execution.output_sha256,
            completed_at=execution.executed_at,
            cloud_processing_approved=False,
        )


class MediaObservationSnapshot(IncubationContract):
    source_ref: NonEmptyStr = Field(max_length=255)
    observation_kind: Literal["video_metadata"]
    observed_at: datetime
    observation: VideoMetadataObservation
    execution: MediaKitExecutionReceipt
    limitations: tuple[NonEmptyStr, ...] = ("Machine observations may be incomplete or wrong and require downstream evidence review.",)

    @field_validator("observed_at")
    @classmethod
    def normalize_observed_at(cls, value: datetime) -> datetime:
        return _aware_utc(value, name="observed_at")

    @model_validator(mode="after")
    def require_matching_completion_time(self) -> MediaObservationSnapshot:
        if self.observed_at != self.execution.completed_at:
            raise ValueError("media observation time must match execution completion time")
        return self


def seal_media_source_receipt(
    *,
    project: ProjectRef,
    receipt: MediaSourceReceipt,
    evidence_role: EvidenceRole,
    source_thread_id: str,
    source_run_id: str,
    parents: tuple[ArtifactParentRef, ...] = (),
) -> ArtifactEnvelope:
    return ArtifactEnvelope.seal(
        project=project,
        artifact_type="media_source_receipt",
        version=1,
        payload=receipt.model_dump(mode="json"),
        parents=parents,
        evidence_role=evidence_role,
        created_at=receipt.resolved_at,
        source_thread_id=source_thread_id,
        source_run_id=source_run_id,
    )


def seal_media_observation_snapshot(
    *,
    project: ProjectRef,
    snapshot: MediaObservationSnapshot,
    source_receipt_artifact: ArtifactEnvelope,
    source_thread_id: str,
    source_run_id: str,
) -> ArtifactEnvelope:
    if source_receipt_artifact.project != project:
        raise ValueError("media source receipt project must match observation project")
    if source_receipt_artifact.artifact_type != "media_source_receipt":
        raise ValueError("media observation requires a media source receipt parent")
    if source_receipt_artifact.evidence_role is None:
        raise ValueError("media source receipt requires an evidence role")
    if source_receipt_artifact.payload.get("source_ref") != snapshot.source_ref:
        raise ValueError("media observation source_ref must match its source receipt")
    return ArtifactEnvelope.seal(
        project=project,
        artifact_type="media_observation",
        version=1,
        payload=snapshot.model_dump(mode="json"),
        parents=(source_receipt_artifact.to_parent_ref(),),
        evidence_role=source_receipt_artifact.evidence_role,
        created_at=snapshot.observed_at,
        source_thread_id=source_thread_id,
        source_run_id=source_run_id,
    )


__all__ = [
    "EphemeralMediaSource",
    "MediaKitExecutionReceipt",
    "MediaKind",
    "MediaObservationSnapshot",
    "MediaSourceReceipt",
    "MediaTransport",
    "VideoMetadataObservation",
    "seal_media_observation_snapshot",
    "seal_media_source_receipt",
]
