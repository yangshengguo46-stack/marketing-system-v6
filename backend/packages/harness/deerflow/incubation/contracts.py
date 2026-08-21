from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator, model_validator

NonEmptyStr = Annotated[str, Field(min_length=1)]
EvidenceRole = Literal[
    "project_fact",
    "user_material",
    "topic_evidence",
    "benchmark_evidence",
    "benchmark_account_candidate",
    "owned_account_observation",
    "owned_audience_observation",
    "benchmark_audience_observation",
    "published_outcome",
    "platform_rule",
]

# Server-controlled thread metadata and runtime-context key. Clients may read
# the selected project but can only change it through the owner-checked
# incubation binding API.
INCUBATION_PROJECT_ID_KEY = "incubation_project_id"
INCUBATION_LOGICAL_ACCOUNT_ID_KEY = "incubation_logical_account_id"

_SENSITIVE_FIELD_NAMES = frozenset(
    {
        "apikey",
        "clientsecret",
        "accesstoken",
        "refreshtoken",
        "cookie",
        "cookies",
        "storagestate",
        "localstorage",
        "temporaryurl",
        "tempurl",
        "localpath",
    }
)


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _normalized_field_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.casefold())


def _reject_sensitive_fields(value: JsonValue, *, path: tuple[str, ...] = ()) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if _normalized_field_name(key) in _SENSITIVE_FIELD_NAMES:
                location = ".".join((*path, key))
                raise ValueError(f"sensitive field {location!r} cannot enter the incubation ledger")
            _reject_sensitive_fields(child, path=(*path, key))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_sensitive_fields(child, path=(*path, str(index)))


class IncubationContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class ProjectRef(IncubationContract):
    owner_user_id: NonEmptyStr = Field(max_length=64)
    project_id: NonEmptyStr = Field(max_length=64)


class LogicalAccountRef(ProjectRef):
    logical_account_id: NonEmptyStr = Field(max_length=64)


class PlatformAccountRef(ProjectRef):
    account_id: NonEmptyStr = Field(max_length=64)
    platform: NonEmptyStr = Field(max_length=32)


class ArtifactParentRef(ProjectRef):
    artifact_id: NonEmptyStr = Field(max_length=80)
    artifact_type: NonEmptyStr = Field(max_length=128)
    content_sha256: str = Field(min_length=64, max_length=64)
    logical_account_id: NonEmptyStr | None = Field(default=None, max_length=64)

    @field_validator("content_sha256")
    @classmethod
    def validate_digest(cls, value: str) -> str:
        if any(character not in "0123456789abcdef" for character in value):
            raise ValueError("content_sha256 must be lowercase hexadecimal")
        return value


class ProjectRecord(IncubationContract):
    project: ProjectRef
    display_name: NonEmptyStr = Field(max_length=255)
    created_at: datetime
    updated_at: datetime


class LogicalAccountRecord(IncubationContract):
    logical_account: LogicalAccountRef
    display_name: NonEmptyStr = Field(max_length=255)
    created_at: datetime
    updated_at: datetime


class PlatformAccountRecord(IncubationContract):
    account: PlatformAccountRef
    logical_account: LogicalAccountRef
    external_account_id: NonEmptyStr = Field(max_length=255)
    display_name: NonEmptyStr = Field(max_length=255)
    created_at: datetime
    updated_at: datetime


class ArtifactEnvelope(IncubationContract):
    artifact_id: NonEmptyStr = Field(max_length=80)
    project: ProjectRef
    artifact_type: NonEmptyStr = Field(max_length=128)
    version: int = Field(ge=1)
    payload: dict[str, JsonValue]
    content_sha256: str = Field(min_length=64, max_length=64)
    logical_account: LogicalAccountRef | None = None
    account: PlatformAccountRef | None = None
    parents: tuple[ArtifactParentRef, ...] = ()
    evidence_role: EvidenceRole | None = None
    created_at: datetime
    source_thread_id: NonEmptyStr = Field(max_length=64)
    source_run_id: NonEmptyStr = Field(max_length=64)

    @field_validator("parents")
    @classmethod
    def canonicalize_parents(cls, value: tuple[ArtifactParentRef, ...]) -> tuple[ArtifactParentRef, ...]:
        if len({parent.artifact_id for parent in value}) != len(value):
            raise ValueError("artifact parents must be unique")
        return tuple(sorted(value, key=lambda parent: parent.artifact_id))

    @field_validator("created_at")
    @classmethod
    def require_aware_created_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_integrity(self) -> ArtifactEnvelope:
        _reject_sensitive_fields(self.payload)
        if self.logical_account is not None and (self.logical_account.owner_user_id != self.project.owner_user_id or self.logical_account.project_id != self.project.project_id):
            raise ValueError("logical account owner and project must match artifact project")
        if self.account is not None and (self.account.owner_user_id != self.project.owner_user_id or self.account.project_id != self.project.project_id):
            raise ValueError("account owner and project must match artifact project")
        for parent in self.parents:
            if parent.owner_user_id != self.project.owner_user_id or parent.project_id != self.project.project_id:
                raise ValueError("parent owner and project must match artifact project")
            if parent.logical_account_id is not None and (self.logical_account is None or parent.logical_account_id != self.logical_account.logical_account_id):
                raise ValueError("parent logical account must match artifact logical account")

        expected_content_sha = _sha256(self.payload)
        if self.content_sha256 != expected_content_sha:
            raise ValueError("content_sha256 does not match artifact payload")
        expected_artifact_id = self._identity_id(
            project=self.project,
            artifact_type=self.artifact_type,
            version=self.version,
            content_sha256=self.content_sha256,
            logical_account=self.logical_account,
            account=self.account,
            parents=self.parents,
            evidence_role=self.evidence_role,
        )
        if self.artifact_id != expected_artifact_id:
            raise ValueError("artifact_id does not match canonical artifact identity")
        return self

    @classmethod
    def seal(
        cls,
        *,
        project: ProjectRef,
        artifact_type: str,
        version: int,
        payload: dict[str, JsonValue],
        created_at: datetime,
        source_thread_id: str,
        source_run_id: str,
        account: PlatformAccountRef | None = None,
        logical_account: LogicalAccountRef | None = None,
        parents: tuple[ArtifactParentRef, ...] = (),
        evidence_role: EvidenceRole | None = None,
    ) -> ArtifactEnvelope:
        canonical_parents = tuple(sorted(parents, key=lambda parent: parent.artifact_id))
        content_sha256 = _sha256(payload)
        artifact_id = cls._identity_id(
            project=project,
            artifact_type=artifact_type,
            version=version,
            content_sha256=content_sha256,
            logical_account=logical_account,
            account=account,
            parents=canonical_parents,
            evidence_role=evidence_role,
        )
        return cls(
            artifact_id=artifact_id,
            project=project,
            artifact_type=artifact_type,
            version=version,
            payload=payload,
            content_sha256=content_sha256,
            logical_account=logical_account,
            account=account,
            parents=canonical_parents,
            evidence_role=evidence_role,
            created_at=created_at,
            source_thread_id=source_thread_id,
            source_run_id=source_run_id,
        )

    @staticmethod
    def _identity_id(
        *,
        project: ProjectRef,
        artifact_type: str,
        version: int,
        content_sha256: str,
        logical_account: LogicalAccountRef | None,
        account: PlatformAccountRef | None,
        parents: tuple[ArtifactParentRef, ...],
        evidence_role: EvidenceRole | None,
    ) -> str:
        identity: dict[str, Any] = {
            "project": project.model_dump(mode="json"),
            "artifact_type": artifact_type.strip(),
            "version": version,
            "content_sha256": content_sha256,
            "account": account.model_dump(mode="json") if account is not None else None,
            "parents": [parent.model_dump(mode="json", exclude_none=True) for parent in parents],
            "evidence_role": evidence_role,
        }
        if logical_account is not None:
            identity["logical_account"] = logical_account.model_dump(mode="json")
        return f"artifact_{_sha256(identity)}"

    def to_parent_ref(self) -> ArtifactParentRef:
        return ArtifactParentRef(
            owner_user_id=self.project.owner_user_id,
            project_id=self.project.project_id,
            artifact_id=self.artifact_id,
            artifact_type=self.artifact_type,
            content_sha256=self.content_sha256,
            logical_account_id=(self.logical_account.logical_account_id if self.logical_account is not None else None),
        )
