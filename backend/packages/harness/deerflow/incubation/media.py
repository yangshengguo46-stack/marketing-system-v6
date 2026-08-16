from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, Never
from urllib.parse import urlparse

from pydantic import Field, field_validator, model_validator

from deerflow.incubation.contracts import (
    ArtifactEnvelope,
    ArtifactParentRef,
    IncubationContract,
    NonEmptyStr,
    ProjectRef,
)

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


def seal_media_source_receipt(
    *,
    project: ProjectRef,
    receipt: MediaSourceReceipt,
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
        created_at=receipt.resolved_at,
        source_thread_id=source_thread_id,
        source_run_id=source_run_id,
    )


__all__ = [
    "EphemeralMediaSource",
    "MediaKind",
    "MediaSourceReceipt",
    "MediaTransport",
    "seal_media_source_receipt",
]
