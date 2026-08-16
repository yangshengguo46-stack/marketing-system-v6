from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Annotated, Literal
from urllib.parse import urlparse

from pydantic import Field, JsonValue, field_validator, model_validator

from deerflow.incubation.contracts import (
    ArtifactEnvelope,
    ArtifactParentRef,
    EvidenceRole,
    IncubationContract,
    NonEmptyStr,
    PlatformAccountRef,
    ProjectRef,
)

EvidenceProvenance = Literal[
    "observed",
    "locally_derived",
    "third_party_estimate",
    "model_inference",
]


class EvidenceItem(IncubationContract):
    source_ref: NonEmptyStr = Field(max_length=255)
    source_type: NonEmptyStr = Field(max_length=64)
    title: NonEmptyStr = Field(max_length=500)
    excerpt: NonEmptyStr = Field(max_length=4000)
    provenance: EvidenceProvenance
    public_uri: NonEmptyStr | None = Field(default=None, max_length=1000)
    actor_label: NonEmptyStr | None = Field(default=None, max_length=200)
    observed_values: dict[str, JsonValue] = Field(default_factory=dict)

    @field_validator("public_uri")
    @classmethod
    def require_public_http_uri(cls, value: str | None) -> str | None:
        if value is None:
            return None
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("evidence public_uri must use http or https")
        return value


class EvidenceCoverageReceipt(IncubationContract):
    population_scope: NonEmptyStr = Field(max_length=128)
    requested_count: int | None = Field(default=None, ge=1)
    returned_count: int = Field(ge=0)
    excluded_count: int = Field(default=0, ge=0)
    duplicate_count: int = Field(default=0, ge=0)
    has_more: bool | None = None
    cursor: int | str | None = None
    limitations: tuple[NonEmptyStr, ...] = ()


class EvidenceSnapshot(IncubationContract):
    provider: NonEmptyStr = Field(max_length=128)
    collection_method: NonEmptyStr = Field(max_length=128)
    evidence_role: EvidenceRole
    captured_at: datetime
    rights_basis: NonEmptyStr = Field(max_length=255)
    query: NonEmptyStr | None = Field(default=None, max_length=500)
    items: tuple[EvidenceItem, ...] = ()
    coverage: EvidenceCoverageReceipt
    route_receipt: dict[str, JsonValue] = Field(default_factory=dict)
    warnings: tuple[NonEmptyStr, ...] = ()
    limitations: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1)]

    @field_validator("captured_at")
    @classmethod
    def require_aware_capture_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("captured_at must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_coverage(self) -> EvidenceSnapshot:
        if self.coverage.returned_count != len(self.items):
            raise ValueError("coverage returned_count must match evidence items")
        source_refs = [item.source_ref for item in self.items]
        if len(source_refs) != len(set(source_refs)):
            raise ValueError("evidence source_ref values must be unique")
        return self

    def to_lead_projection(self, *, max_bytes: int = 16_000) -> dict[str, JsonValue]:
        if max_bytes < 2_048:
            raise ValueError("evidence Lead projection budget must be at least 2048 bytes")

        full_payload = self.model_dump(mode="json")
        snapshot_sha256 = _payload_sha256(full_payload)
        route_receipt_sha256 = _payload_sha256(self.route_receipt)
        projected_items: list[dict[str, JsonValue]] = []

        def render() -> dict[str, JsonValue]:
            included = len(projected_items)
            return {
                "snapshot_sha256": snapshot_sha256,
                "route_receipt_sha256": route_receipt_sha256,
                "provider": self.provider,
                "collection_method": self.collection_method,
                "evidence_role": self.evidence_role,
                "captured_at": self.captured_at.isoformat(),
                "rights_basis": self.rights_basis,
                "query": self.query,
                "coverage": self.coverage.model_dump(mode="json"),
                "items": projected_items,
                "warnings": list(self.warnings),
                "limitations": list(self.limitations),
                "projection": {
                    "total_items": len(self.items),
                    "included_items": included,
                    "omitted_items": len(self.items) - included,
                    "truncated": included < len(self.items),
                },
            }

        if _payload_size(render()) > max_bytes:
            raise ValueError("evidence metadata exceeds the Lead projection budget")

        for item in self.items:
            projected_items.append(
                {
                    "source_ref": item.source_ref,
                    "source_type": item.source_type,
                    "title": item.title,
                    "excerpt": item.excerpt[:800],
                    "provenance": item.provenance,
                    "public_uri": item.public_uri,
                    "actor_label": item.actor_label,
                    "observed_values": item.observed_values,
                }
            )
            if _payload_size(render()) > max_bytes:
                projected_items.pop()
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


def seal_evidence_snapshot(
    *,
    project: ProjectRef,
    snapshot: EvidenceSnapshot,
    source_thread_id: str,
    source_run_id: str,
    account: PlatformAccountRef | None = None,
    parents: tuple[ArtifactParentRef, ...] = (),
) -> ArtifactEnvelope:
    return ArtifactEnvelope.seal(
        project=project,
        artifact_type="evidence_snapshot",
        version=1,
        payload=snapshot.model_dump(mode="json"),
        account=account,
        parents=parents,
        evidence_role=snapshot.evidence_role,
        created_at=snapshot.captured_at,
        source_thread_id=source_thread_id,
        source_run_id=source_run_id,
    )
