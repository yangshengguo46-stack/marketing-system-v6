"""Small, sourced, user-scoped profile revisions for Lead collaboration.

The profile contains only stable cross-project user facts and collaboration
preferences. Project/account truth belongs to the incubation ledger, while
permissions remain deterministic runtime policy. Each write creates one
immutable, content-addressed revision under the effective user's directory.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from deerflow.config.paths import Paths, get_paths

USER_PROFILE_SCHEMA_VERSION = "v6-user-profile-v1"
MAX_USER_PROFILE_ITEMS = 16
MAX_USER_PROFILE_STATEMENT_CHARS = 500

type UserProfileKind = Literal[
    "background",
    "communication_preference",
    "collaboration_preference",
    "stable_constraint",
]
type UserProfileAction = Literal["remember", "replace", "forget"]


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _validate_sha256(value: str) -> str:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError("expected a lowercase SHA-256 digest")
    return value


class UserProfileConflict(RuntimeError):
    """A concurrent or stale mutation targeted a different profile revision."""


class UserProfileMutationSource(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    thread_id: str | None = Field(default=None, max_length=128)
    run_id: str | None = Field(default=None, max_length=128)
    message_id: str | None = Field(default=None, max_length=128)
    message_sha256: str
    excerpt_sha256: str
    recorded_at: datetime

    _message_digest = field_validator("message_sha256")(_validate_sha256)
    _excerpt_digest = field_validator("excerpt_sha256")(_validate_sha256)

    @field_validator("recorded_at")
    @classmethod
    def _timezone_required(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("recorded_at must be timezone-aware")
        return value


class UserProfileItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    item_id: str = Field(pattern=r"^upi_[0-9a-f]{16}$")
    kind: UserProfileKind
    statement: str = Field(min_length=1, max_length=MAX_USER_PROFILE_STATEMENT_CHARS)
    source: UserProfileMutationSource
    created_at: datetime
    updated_at: datetime

    @field_validator("statement")
    @classmethod
    def _clean_statement(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("statement must not be blank")
        return stripped

    @model_validator(mode="after")
    def _valid_timestamps(self) -> UserProfileItem:
        for name, value in (("created_at", self.created_at), ("updated_at", self.updated_at)):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"{name} must be timezone-aware")
        if self.updated_at < self.created_at:
            raise ValueError("updated_at cannot precede created_at")
        return self


class UserProfileChange(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    action: UserProfileAction
    item_id: str = Field(pattern=r"^upi_[0-9a-f]{16}$")
    source: UserProfileMutationSource


class UserProfileRevision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["v6-user-profile-v1"] = USER_PROFILE_SCHEMA_VERSION
    owner_user_id: str = Field(min_length=1, max_length=128)
    version: int = Field(ge=1)
    previous_content_sha256: str | None = None
    items: tuple[UserProfileItem, ...] = Field(max_length=MAX_USER_PROFILE_ITEMS)
    change: UserProfileChange
    created_at: datetime
    content_sha256: str

    @field_validator("previous_content_sha256", "content_sha256")
    @classmethod
    def _digest(cls, value: str | None) -> str | None:
        return _validate_sha256(value) if value is not None else None

    @model_validator(mode="after")
    def _verify_revision(self) -> UserProfileRevision:
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
        item_ids = [item.item_id for item in self.items]
        if len(item_ids) != len(set(item_ids)):
            raise ValueError("profile item_id values must be unique")
        if self.content_sha256 != self.calculate_content_sha256():
            raise ValueError("content_sha256 does not match the revision payload")
        return self

    def calculate_content_sha256(self) -> str:
        payload = self.model_dump(mode="json", exclude={"content_sha256"})
        return hashlib.sha256(_canonical_json_bytes(payload)).hexdigest()

    @classmethod
    def create(
        cls,
        *,
        owner_user_id: str,
        version: int,
        previous_content_sha256: str | None,
        items: tuple[UserProfileItem, ...],
        change: UserProfileChange,
        created_at: datetime,
    ) -> UserProfileRevision:
        payload = {
            "schema_version": USER_PROFILE_SCHEMA_VERSION,
            "owner_user_id": owner_user_id,
            "version": version,
            "previous_content_sha256": previous_content_sha256,
            "items": items,
            "change": change,
            "created_at": created_at,
        }
        # Hash Pydantic's canonical JSON projection, including its UTC `Z`
        # normalization, so creation and later file validation use identical
        # bytes rather than two subtly different datetime encodings.
        draft = cls.model_construct(**payload, content_sha256="0" * 64)
        return cls(**payload, content_sha256=draft.calculate_content_sha256())


class UserProfileWriteResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    revision: UserProfileRevision
    item_id: str
    changed: bool


class FileUserProfileStore:
    """Append-only per-user profile revisions with optimistic concurrency."""

    def __init__(self, paths: Paths | None = None) -> None:
        self._paths = paths or get_paths()

    def load(self, user_id: str) -> UserProfileRevision | None:
        revisions_dir = self._paths.user_profile_revisions_dir(user_id)
        if not revisions_dir.exists():
            return None
        candidates = sorted(path for path in revisions_dir.glob("*.json") if path.stem.isdigit())
        if not candidates:
            return None
        latest_path = candidates[-1]
        revision = UserProfileRevision.model_validate_json(latest_path.read_text(encoding="utf-8"))
        if revision.owner_user_id != user_id:
            raise ValueError("profile revision owner_user_id does not match its storage scope")
        if latest_path.stem != f"{revision.version:08d}":
            raise ValueError("profile revision filename does not match its version")
        return revision

    def remember(
        self,
        user_id: str,
        *,
        kind: UserProfileKind,
        statement: str,
        source: UserProfileMutationSource,
        expected_version: int | None = None,
    ) -> UserProfileWriteResult:
        current = self._current_for_write(user_id, expected_version)
        clean_statement = statement.strip()
        if current is not None:
            for item in current.items:
                if item.kind == kind and item.statement == clean_statement:
                    return UserProfileWriteResult(revision=current, item_id=item.item_id, changed=False)
            if len(current.items) >= MAX_USER_PROFILE_ITEMS:
                raise ValueError(f"a user profile may contain at most {MAX_USER_PROFILE_ITEMS} active items")
            items = list(current.items)
        else:
            items = []
        now = source.recorded_at
        item = UserProfileItem(
            item_id=f"upi_{uuid.uuid4().hex[:16]}",
            kind=kind,
            statement=clean_statement,
            source=source,
            created_at=now,
            updated_at=now,
        )
        items.append(item)
        revision = self._revision(user_id, current, tuple(items), action="remember", item_id=item.item_id, source=source)
        self._commit(revision)
        return UserProfileWriteResult(revision=revision, item_id=item.item_id, changed=True)

    def replace(
        self,
        user_id: str,
        *,
        item_id: str,
        kind: UserProfileKind,
        statement: str,
        source: UserProfileMutationSource,
        expected_version: int | None = None,
    ) -> UserProfileWriteResult:
        current = self._current_for_write(user_id, expected_version)
        if current is None:
            raise KeyError(f"user profile item {item_id!r} does not exist")
        items = list(current.items)
        for index, existing in enumerate(items):
            if existing.item_id != item_id:
                continue
            clean_statement = statement.strip()
            if existing.kind == kind and existing.statement == clean_statement:
                return UserProfileWriteResult(revision=current, item_id=item_id, changed=False)
            items[index] = UserProfileItem(
                item_id=item_id,
                kind=kind,
                statement=clean_statement,
                source=source,
                created_at=existing.created_at,
                updated_at=source.recorded_at,
            )
            break
        else:
            raise KeyError(f"user profile item {item_id!r} does not exist")
        revision = self._revision(user_id, current, tuple(items), action="replace", item_id=item_id, source=source)
        self._commit(revision)
        return UserProfileWriteResult(revision=revision, item_id=item_id, changed=True)

    def forget(
        self,
        user_id: str,
        *,
        item_id: str,
        source: UserProfileMutationSource,
        expected_version: int | None = None,
    ) -> UserProfileWriteResult:
        current = self._current_for_write(user_id, expected_version)
        if current is None or not any(item.item_id == item_id for item in current.items):
            raise KeyError(f"user profile item {item_id!r} does not exist")
        items = tuple(item for item in current.items if item.item_id != item_id)
        revision = self._revision(user_id, current, items, action="forget", item_id=item_id, source=source)
        self._commit(revision)
        return UserProfileWriteResult(revision=revision, item_id=item_id, changed=True)

    def _current_for_write(self, user_id: str, expected_version: int | None) -> UserProfileRevision | None:
        current = self.load(user_id)
        actual_version = current.version if current is not None else 0
        if expected_version is not None and expected_version != actual_version:
            raise UserProfileConflict(f"expected profile version {expected_version}, found {actual_version}")
        return current

    @staticmethod
    def _revision(
        user_id: str,
        current: UserProfileRevision | None,
        items: tuple[UserProfileItem, ...],
        *,
        action: UserProfileAction,
        item_id: str,
        source: UserProfileMutationSource,
    ) -> UserProfileRevision:
        return UserProfileRevision.create(
            owner_user_id=user_id,
            version=(current.version + 1 if current is not None else 1),
            previous_content_sha256=(current.content_sha256 if current is not None else None),
            items=items,
            change=UserProfileChange(action=action, item_id=item_id, source=source),
            created_at=source.recorded_at,
        )

    def _commit(self, revision: UserProfileRevision) -> None:
        revisions_dir = self._paths.user_profile_revisions_dir(revision.owner_user_id)
        revisions_dir.mkdir(parents=True, exist_ok=True)
        destination = revisions_dir / f"{revision.version:08d}.json"
        payload = revision.model_dump_json(indent=2) + "\n"
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                dir=revisions_dir,
                prefix=".profile-",
                suffix=".tmp",
                delete=False,
            ) as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
                temporary = Path(handle.name)
            try:
                os.link(temporary, destination)
            except FileExistsError as exc:
                raise UserProfileConflict(f"profile version {revision.version} was committed concurrently") from exc
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)


def get_user_profile_store() -> FileUserProfileStore:
    return FileUserProfileStore()


__all__ = [
    "MAX_USER_PROFILE_ITEMS",
    "MAX_USER_PROFILE_STATEMENT_CHARS",
    "USER_PROFILE_SCHEMA_VERSION",
    "FileUserProfileStore",
    "UserProfileAction",
    "UserProfileConflict",
    "UserProfileItem",
    "UserProfileKind",
    "UserProfileMutationSource",
    "UserProfileRevision",
    "UserProfileWriteResult",
    "get_user_profile_store",
]
