from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

from deerflow.incubation.media import EphemeralMediaSource

ExecutionMode = Literal["auto", "local", "cloud"]
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_ARTIFACT_REFERENCE = re.compile(r"^artifact://[A-Za-z0-9][A-Za-z0-9._:-]*(?:/[A-Za-z0-9][A-Za-z0-9._:-]*)*$")


def _bounded_text(value: str, *, name: str, maximum: int) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string")
    normalized = value.strip()
    if not normalized or len(normalized) > maximum:
        raise ValueError(f"{name} must contain between 1 and {maximum} characters")
    return normalized


@dataclass(frozen=True, slots=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str
    stdout_truncated: bool = False
    stderr_truncated: bool = False


@dataclass(frozen=True, slots=True)
class MediaKitCapability:
    domain: str
    tool: str
    name: str
    description: str
    cli_version: str
    schema_sha256: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    notices: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True, repr=False)
class PreparedMediaKitCall:
    capability: MediaKitCapability
    source: EphemeralMediaSource
    mode: ExecutionMode
    command: tuple[str, ...] = field(repr=False)
    input_sha256: str
    client_token_sha256: str | None = None

    def __repr__(self) -> str:
        return f"PreparedMediaKitCall(domain={self.capability.domain!r}, tool={self.capability.tool!r}, mode={self.mode!r}, source_ref={self.source.source_ref!r}, input_sha256={self.input_sha256!r}, command='<redacted>')"


@dataclass(frozen=True, slots=True, repr=False)
class MediaKitExecutionResult:
    """Execution-only result; callers must project it before persistence."""

    prepared: PreparedMediaKitCall = field(repr=False)
    output: dict[str, Any] = field(repr=False)
    output_sha256: str
    source_content_sha256: str
    executed_at: datetime
    notices: tuple[str, ...] = ()

    def __repr__(self) -> str:
        capability = self.prepared.capability
        return f"MediaKitExecutionResult(domain={capability.domain!r}, tool={capability.tool!r}, mode={self.prepared.mode!r}, source_ref={self.prepared.source.source_ref!r}, output_sha256={self.output_sha256!r}, output='<redacted>')"


@dataclass(frozen=True, slots=True, repr=False)
class MediaKitCloudSubmissionResult:
    remote_task_id: str
    request_id_sha256: str | None
    submitted_at: datetime
    notices: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "remote_task_id",
            _bounded_text(self.remote_task_id, name="remote_task_id", maximum=255),
        )
        if self.request_id_sha256 is not None and not _SHA256.fullmatch(self.request_id_sha256):
            raise ValueError("request_id_sha256 must be a SHA-256 digest")

    def __repr__(self) -> str:
        return f"MediaKitCloudSubmissionResult(remote_task_id='<redacted>', request_id_sha256={self.request_id_sha256!r}, submitted_at={self.submitted_at!r})"


@dataclass(frozen=True, slots=True, repr=False)
class MediaKitCloudQueryResult:
    remote_task_id: str
    provider_status: str
    provider_output: Mapping[str, Any] = field(repr=False)
    provider_output_sha256: str
    query_schema_sha256: str
    notices: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "remote_task_id",
            _bounded_text(self.remote_task_id, name="remote_task_id", maximum=255),
        )
        object.__setattr__(
            self,
            "provider_status",
            _bounded_text(self.provider_status, name="provider_status", maximum=64).casefold(),
        )
        for name in ("provider_output_sha256", "query_schema_sha256"):
            if not _SHA256.fullmatch(getattr(self, name)):
                raise ValueError(f"{name} must be a SHA-256 digest")

    def __repr__(self) -> str:
        return f"MediaKitCloudQueryResult(remote_task_id='<redacted>', provider_status={self.provider_status!r}, provider_output_sha256={self.provider_output_sha256!r}, provider_output='<redacted>')"


@dataclass(frozen=True, slots=True)
class MediaKitCloudAuthorizationContext:
    user_id: str
    project_id: str
    local_task_id: str
    source_ref: str
    rights_ref: str
    source_content_sha256: str
    capability_domain: str
    capability_tool: str
    operation_sha256: str
    cloud_processing_approval_ref: str
    fee_authorization_ref: str
    currency: str
    maximum_amount_micros: int
    pricing_evidence_sha256: str
    fee_quote_sha256: str
    estimated_amount_micros: int
    fee_quote_valid_until: datetime


@dataclass(frozen=True, slots=True)
class MediaKitCloudSourceContext:
    user_id: str
    project_id: str
    local_task_id: str
    source_ref: str
    rights_ref: str
    source_content_sha256: str


@dataclass(frozen=True, slots=True)
class MediaKitCloudOutputPolicy:
    capability_domain: str
    capability_tool: str
    url_field: Literal["video_url", "audio_url"]
    media_kind: Literal["video", "audio"]
    maximum_bytes: int

    def __post_init__(self) -> None:
        for name in ("capability_domain", "capability_tool"):
            object.__setattr__(
                self,
                name,
                _bounded_text(getattr(self, name), name=name, maximum=64),
            )
        if self.url_field not in {"video_url", "audio_url"}:
            raise ValueError("url_field must be video_url or audio_url")
        expected_kind = self.url_field.removesuffix("_url")
        if self.media_kind != expected_kind:
            raise ValueError("url_field and media_kind must agree")
        if not isinstance(self.maximum_bytes, int) or isinstance(self.maximum_bytes, bool) or self.maximum_bytes <= 0:
            raise ValueError("maximum_bytes must be a positive integer")


@dataclass(frozen=True, slots=True)
class MediaKitLocalOutputPolicy:
    capability_domain: str
    capability_tool: str
    path_field: Literal["video_url", "audio_url"]
    media_kind: Literal["video", "audio"]
    maximum_bytes: int

    def __post_init__(self) -> None:
        for name in ("capability_domain", "capability_tool"):
            object.__setattr__(
                self,
                name,
                _bounded_text(getattr(self, name), name=name, maximum=64),
            )
        expected_kind = self.path_field.removesuffix("_url")
        if self.media_kind != expected_kind:
            raise ValueError("path_field and media_kind must agree")
        if not isinstance(self.maximum_bytes, int) or isinstance(self.maximum_bytes, bool) or self.maximum_bytes <= 0:
            raise ValueError("maximum_bytes must be a positive integer")


@dataclass(frozen=True, slots=True, repr=False)
class MediaKitLocalMaterializationContext:
    operation_id: str
    user_id: str
    project_id: str
    production_plan_artifact_id: str
    production_plan_content_sha256: str
    source_ref: str
    source_content_sha256: str
    capability_domain: str
    capability_tool: str
    capability_schema_sha256: str
    request_sha256: str
    output_field: Literal["video_url", "audio_url"]
    maximum_output_bytes: int
    provider_output: Mapping[str, Any] = field(repr=False)
    provider_output_sha256: str
    executed_at: datetime

    def __post_init__(self) -> None:
        for name, maximum in (
            ("operation_id", 128),
            ("user_id", 64),
            ("project_id", 64),
            ("production_plan_artifact_id", 80),
            ("source_ref", 255),
            ("capability_domain", 64),
            ("capability_tool", 64),
        ):
            object.__setattr__(
                self,
                name,
                _bounded_text(getattr(self, name), name=name, maximum=maximum),
            )
        for name in (
            "production_plan_content_sha256",
            "source_content_sha256",
            "capability_schema_sha256",
            "request_sha256",
            "provider_output_sha256",
        ):
            if not _SHA256.fullmatch(getattr(self, name)):
                raise ValueError(f"{name} must be a SHA-256 digest")
        if not isinstance(self.maximum_output_bytes, int) or isinstance(self.maximum_output_bytes, bool) or self.maximum_output_bytes <= 0:
            raise ValueError("maximum_output_bytes must be a positive integer")
        if self.executed_at.tzinfo is None or self.executed_at.utcoffset() is None:
            raise ValueError("executed_at must be timezone-aware")

    def __repr__(self) -> str:
        return (
            "MediaKitLocalMaterializationContext("
            f"operation_id={self.operation_id!r}, source_ref={self.source_ref!r}, "
            f"capability={self.capability_domain!r}/{self.capability_tool!r}, "
            f"provider_output_sha256={self.provider_output_sha256!r}, provider_output='<redacted>')"
        )


@dataclass(frozen=True, slots=True)
class MediaKitLocalMaterializedOutput:
    artifact_ref: str
    content_sha256: str
    content_type: str
    size_bytes: int
    execution_output_sha256: str
    completed_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "artifact_ref",
            _bounded_text(self.artifact_ref, name="artifact_ref", maximum=1024),
        )
        if not _ARTIFACT_REFERENCE.fullmatch(self.artifact_ref):
            raise ValueError("artifact reference must be a stable internal artifact:// reference")
        object.__setattr__(
            self,
            "content_type",
            _bounded_text(self.content_type, name="content_type", maximum=128),
        )
        if not _SHA256.fullmatch(self.content_sha256):
            raise ValueError("content_sha256 must be a SHA-256 digest")
        if not _SHA256.fullmatch(self.execution_output_sha256):
            raise ValueError("execution_output_sha256 must be a SHA-256 digest")
        if not isinstance(self.size_bytes, int) or isinstance(self.size_bytes, bool) or self.size_bytes <= 0:
            raise ValueError("size_bytes must be a positive integer")
        if self.completed_at.tzinfo is None or self.completed_at.utcoffset() is None:
            raise ValueError("completed_at must be timezone-aware")

    def as_result(self) -> dict[str, Any]:
        return {
            "artifact_ref": self.artifact_ref,
            "content_sha256": self.content_sha256,
            "content_type": self.content_type,
            "size_bytes": self.size_bytes,
            "execution_output_sha256": self.execution_output_sha256,
            "completed_at": self.completed_at.isoformat(),
        }


@dataclass(frozen=True, slots=True, repr=False)
class MediaKitCloudMaterializationContext:
    local_task_id: str
    user_id: str
    project_id: str
    thread_id: str
    remote_task_id: str = field(repr=False)
    source_ref: str
    rights_ref: str
    source_content_sha256: str
    capability_domain: str
    capability_tool: str
    cli_version: str
    capability_schema_sha256: str
    request_sha256: str
    operation_sha256: str
    client_token_sha256: str
    cloud_processing_approval_ref: str
    fee_authorization_ref: str
    currency: str
    maximum_amount_micros: int
    pricing_evidence_sha256: str
    fee_quote_sha256: str
    estimated_amount_micros: int
    fee_quote_valid_until: datetime
    provider_output: Mapping[str, Any] = field(repr=False)
    provider_output_sha256: str

    def __repr__(self) -> str:
        return (
            "MediaKitCloudMaterializationContext("
            f"local_task_id={self.local_task_id!r}, source_ref={self.source_ref!r}, "
            f"capability={self.capability_domain!r}/{self.capability_tool!r}, "
            f"provider_output_sha256={self.provider_output_sha256!r}, provider_output='<redacted>')"
        )


@dataclass(frozen=True, slots=True)
class MediaKitCloudMaterializedOutput:
    artifact_ref: str
    content_sha256: str
    content_type: str
    size_bytes: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "artifact_ref",
            _bounded_text(self.artifact_ref, name="artifact_ref", maximum=1024),
        )
        if not _ARTIFACT_REFERENCE.fullmatch(self.artifact_ref):
            raise ValueError("artifact reference must be a stable internal artifact:// reference")
        object.__setattr__(
            self,
            "content_type",
            _bounded_text(self.content_type, name="content_type", maximum=128),
        )
        if not _SHA256.fullmatch(self.content_sha256):
            raise ValueError("content_sha256 must be a SHA-256 digest")
        if not isinstance(self.size_bytes, int) or isinstance(self.size_bytes, bool) or self.size_bytes < 0:
            raise ValueError("size_bytes must be a non-negative integer")

    def as_result(self) -> dict[str, Any]:
        return {
            "artifact_ref": self.artifact_ref,
            "content_sha256": self.content_sha256,
            "content_type": self.content_type,
            "size_bytes": self.size_bytes,
        }


__all__ = [
    "CommandResult",
    "ExecutionMode",
    "MediaKitCapability",
    "MediaKitCloudAuthorizationContext",
    "MediaKitCloudMaterializationContext",
    "MediaKitCloudMaterializedOutput",
    "MediaKitCloudOutputPolicy",
    "MediaKitCloudQueryResult",
    "MediaKitCloudSourceContext",
    "MediaKitCloudSubmissionResult",
    "MediaKitExecutionResult",
    "MediaKitLocalMaterializationContext",
    "MediaKitLocalMaterializedOutput",
    "MediaKitLocalOutputPolicy",
    "PreparedMediaKitCall",
]
