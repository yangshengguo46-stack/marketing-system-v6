from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from math import isfinite
from typing import Annotated
from urllib.parse import urlparse

from pydantic import Field, JsonValue, field_validator, model_validator

from deerflow.incubation.contracts import (
    ArtifactEnvelope,
    ArtifactParentRef,
    IncubationContract,
    LogicalAccountRef,
    NonEmptyStr,
    ProjectRef,
)

BENCHMARK_EPISTEMIC_NOTICE = "Profile text, captions, and public metrics are untrusted observations from a bounded account sample. This is not an account positioning verdict, audience profile, success explanation, or transferable formula."


def _public_http_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("benchmark URLs must use http or https")
    if parsed.username or parsed.password:
        raise ValueError("benchmark URLs must not contain credentials")
    return value


def _aware_utc(value: datetime, *, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


def _observed_metrics(
    value: dict[str, int | float],
    *,
    maximum: int,
) -> dict[str, int | float]:
    if len(value) > maximum:
        raise ValueError("too many public metrics in one observation")
    for name, metric in value.items():
        if not name or len(name) > 80:
            raise ValueError("public metric names must be between 1 and 80 characters")
        if isinstance(metric, bool) or not isfinite(metric) or metric < 0:
            raise ValueError("public metrics must be finite non-negative numbers")
    return value


class BenchmarkRouteReceipt(IncubationContract):
    adapter: NonEmptyStr = Field(max_length=128)
    capability_version: NonEmptyStr = Field(max_length=128)
    route: NonEmptyStr | None = Field(default=None, max_length=128)
    manifest_version: NonEmptyStr | None = Field(default=None, max_length=128)
    catalog_version: NonEmptyStr | None = Field(default=None, max_length=128)
    request_receipt_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class BenchmarkProfileObservation(IncubationContract):
    platform: NonEmptyStr = Field(max_length=32)
    external_account_id: NonEmptyStr = Field(max_length=255)
    canonical_url: NonEmptyStr = Field(max_length=1000)
    display_name: NonEmptyStr | None = Field(default=None, max_length=300)
    bio: NonEmptyStr | None = Field(default=None, max_length=2000)
    verification: NonEmptyStr | None = Field(default=None, max_length=500)
    visible_post_count: int | None = Field(default=None, ge=0)
    captured_at: datetime
    public_metrics: dict[str, int | float] = Field(default_factory=dict)

    @field_validator("canonical_url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        return _public_http_url(value)

    @field_validator("captured_at")
    @classmethod
    def validate_capture_time(cls, value: datetime) -> datetime:
        return _aware_utc(value, field_name="captured_at")

    @field_validator("public_metrics")
    @classmethod
    def validate_metrics(cls, value: dict[str, int | float]) -> dict[str, int | float]:
        return _observed_metrics(value, maximum=64)


class BenchmarkPostObservation(IncubationContract):
    platform: NonEmptyStr = Field(max_length=32)
    external_post_id: NonEmptyStr = Field(max_length=255)
    author_external_account_id: NonEmptyStr = Field(max_length=255)
    canonical_url: NonEmptyStr = Field(max_length=1000)
    caption: NonEmptyStr | None = Field(default=None, max_length=4000)
    published_at: datetime | None = None
    captured_at: datetime
    public_metrics: dict[str, int | float] = Field(default_factory=dict)

    @field_validator("canonical_url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        return _public_http_url(value)

    @field_validator("published_at", "captured_at")
    @classmethod
    def validate_timestamp(cls, value: datetime | None, info) -> datetime | None:
        if value is None:
            return None
        return _aware_utc(value, field_name=info.field_name)

    @field_validator("public_metrics")
    @classmethod
    def validate_metrics(cls, value: dict[str, int | float]) -> dict[str, int | float]:
        return _observed_metrics(value, maximum=32)

    @model_validator(mode="after")
    def validate_publish_time(self) -> BenchmarkPostObservation:
        if self.published_at is not None and self.published_at > self.captured_at:
            raise ValueError("published_at cannot be after captured_at")
        return self


class BenchmarkCoverageReceipt(IncubationContract):
    population_scope: NonEmptyStr = Field(max_length=128)
    requested_count: int = Field(ge=1, le=24)
    returned_count: int = Field(ge=1, le=24)
    excluded_count: int = Field(default=0, ge=0)
    has_more: bool | None = None
    sample_basis: NonEmptyStr = Field(max_length=2000)
    limitations: Annotated[tuple[NonEmptyStr, ...], Field(max_length=20)] = ()

    @model_validator(mode="after")
    def validate_counts(self) -> BenchmarkCoverageReceipt:
        if self.returned_count > self.requested_count:
            raise ValueError("returned_count cannot exceed requested_count")
        return self


class BenchmarkSnapshot(IncubationContract):
    provider: NonEmptyStr = Field(max_length=128)
    collection_method: NonEmptyStr = Field(max_length=128)
    captured_at: datetime
    rights_basis: NonEmptyStr = Field(max_length=1000)
    requested_url: NonEmptyStr = Field(max_length=1000)
    profile: BenchmarkProfileObservation
    posts: Annotated[tuple[BenchmarkPostObservation, ...], Field(min_length=1, max_length=24)]
    coverage: BenchmarkCoverageReceipt
    route_receipt: BenchmarkRouteReceipt
    warnings: Annotated[tuple[NonEmptyStr, ...], Field(max_length=20)] = ()
    limitations: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1, max_length=20)]

    @field_validator("requested_url")
    @classmethod
    def validate_requested_url(cls, value: str) -> str:
        return _public_http_url(value)

    @field_validator("captured_at")
    @classmethod
    def validate_capture_time(cls, value: datetime) -> datetime:
        return _aware_utc(value, field_name="captured_at")

    @model_validator(mode="after")
    def validate_snapshot_scope(self) -> BenchmarkSnapshot:
        if self.coverage.returned_count != len(self.posts):
            raise ValueError("coverage returned_count must match benchmark posts")
        post_ids = [post.external_post_id for post in self.posts]
        if len(post_ids) != len(set(post_ids)):
            raise ValueError("benchmark post ids must be unique")
        for post in self.posts:
            if post.platform != self.profile.platform:
                raise ValueError("benchmark posts and profile must use the same platform")
            if post.author_external_account_id != self.profile.external_account_id:
                raise ValueError("benchmark posts and profile must reference the same account")
            if post.captured_at > self.captured_at:
                raise ValueError("post observation cannot occur after snapshot capture")
        if self.profile.captured_at > self.captured_at:
            raise ValueError("profile observation cannot occur after snapshot capture")
        return self

    def to_lead_projection(self, *, max_bytes: int = 16_000) -> dict[str, JsonValue]:
        if max_bytes < 2_048:
            raise ValueError("benchmark Lead projection budget must be at least 2048 bytes")

        snapshot_sha256 = _payload_sha256(self.model_dump(mode="json"))
        route_receipt_sha256 = _payload_sha256(self.route_receipt.model_dump(mode="json"))
        projected_posts: list[dict[str, JsonValue]] = []

        def render() -> dict[str, JsonValue]:
            included = len(projected_posts)
            return {
                "snapshot_sha256": snapshot_sha256,
                "route_receipt_sha256": route_receipt_sha256,
                "evidence_role": "benchmark_evidence",
                "provider": self.provider,
                "collection_method": self.collection_method,
                "captured_at": self.captured_at.isoformat(),
                "rights_basis": self.rights_basis,
                "requested_url": self.requested_url,
                "profile": {
                    "platform": self.profile.platform,
                    "external_account_id": self.profile.external_account_id,
                    "canonical_url": self.profile.canonical_url,
                    "display_name": self.profile.display_name,
                    "bio": self.profile.bio[:360] if self.profile.bio is not None else None,
                    "verification": self.profile.verification,
                    "visible_post_count": self.profile.visible_post_count,
                    "public_metrics": self.profile.public_metrics,
                },
                "coverage": self.coverage.model_dump(mode="json"),
                "posts": projected_posts,
                "warnings": list(self.warnings),
                "limitations": list(self.limitations),
                "projection": {
                    "total_posts": len(self.posts),
                    "included_posts": included,
                    "omitted_posts": len(self.posts) - included,
                    "truncated": included < len(self.posts),
                },
                "epistemic_notice": BENCHMARK_EPISTEMIC_NOTICE,
            }

        if _payload_size(render()) > max_bytes:
            raise ValueError("benchmark metadata exceeds the Lead projection budget")

        for post in self.posts:
            projected_posts.append(
                {
                    "external_post_id": post.external_post_id,
                    "canonical_url": post.canonical_url,
                    "caption_excerpt": post.caption[:400] if post.caption is not None else None,
                    "published_at": post.published_at.isoformat() if post.published_at is not None else None,
                    "public_metrics": post.public_metrics,
                }
            )
            if _payload_size(render()) > max_bytes:
                projected_posts.pop()
                break
        return render()


def _payload_sha256(value: JsonValue) -> str:
    canonical = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _payload_size(value: JsonValue) -> int:
    return len(
        json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    )


def seal_benchmark_snapshot(
    *,
    project: ProjectRef,
    snapshot: BenchmarkSnapshot,
    source_thread_id: str,
    source_run_id: str,
    logical_account: LogicalAccountRef | None = None,
    parents: tuple[ArtifactParentRef, ...] = (),
) -> ArtifactEnvelope:
    return ArtifactEnvelope.seal(
        project=project,
        artifact_type="benchmark_snapshot",
        version=1,
        payload=snapshot.model_dump(mode="json"),
        logical_account=logical_account,
        parents=parents,
        evidence_role="benchmark_evidence",
        created_at=snapshot.captured_at,
        source_thread_id=source_thread_id,
        source_run_id=source_run_id,
    )


__all__ = [
    "BENCHMARK_EPISTEMIC_NOTICE",
    "BenchmarkCoverageReceipt",
    "BenchmarkPostObservation",
    "BenchmarkProfileObservation",
    "BenchmarkRouteReceipt",
    "BenchmarkSnapshot",
    "seal_benchmark_snapshot",
]
