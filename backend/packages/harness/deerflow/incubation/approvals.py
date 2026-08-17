from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import Field, field_validator, model_validator

from deerflow.incubation.contracts import IncubationContract, NonEmptyStr, ProjectRef

ApprovalKind = Literal["cloud_processing", "fee_authorization"]


def _aware_utc(value: datetime, *, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value.astimezone(UTC)


class ApprovalGrant(IncubationContract):
    """One immutable user decision plus its one-task execution binding."""

    grant_id: NonEmptyStr = Field(max_length=80, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
    project: ProjectRef
    kind: ApprovalKind
    operation_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    maximum_amount_micros: int | None = Field(default=None, gt=0)
    issued_at: datetime
    expires_at: datetime
    revoked_at: datetime | None = None
    bound_local_task_id: NonEmptyStr | None = Field(default=None, max_length=64)
    bound_at: datetime | None = None

    @field_validator("issued_at", "expires_at", "revoked_at", "bound_at")
    @classmethod
    def normalize_timestamps(cls, value: datetime | None, info) -> datetime | None:
        if value is None:
            return None
        return _aware_utc(value, name=info.field_name)

    @model_validator(mode="after")
    def validate_grant_shape(self) -> ApprovalGrant:
        if self.expires_at <= self.issued_at:
            raise ValueError("approval expires_at must be after issued_at")
        if self.kind == "cloud_processing":
            if self.currency is not None or self.maximum_amount_micros is not None:
                raise ValueError("cloud_processing approval cannot carry a fee limit")
        elif self.currency is None or self.maximum_amount_micros is None:
            raise ValueError("fee_authorization approval requires a currency and positive maximum amount")

        if (self.bound_local_task_id is None) != (self.bound_at is None):
            raise ValueError("approval task binding requires both task id and bound_at")
        if self.bound_at is not None and self.bound_at < self.issued_at:
            raise ValueError("approval bound_at cannot precede issued_at")
        if self.revoked_at is not None:
            if self.revoked_at < self.issued_at:
                raise ValueError("approval revoked_at cannot precede issued_at")
            if self.bound_local_task_id is not None:
                raise ValueError("a bound approval cannot also be revoked")
        return self

    @classmethod
    def issue(
        cls,
        *,
        grant_id: str,
        project: ProjectRef,
        kind: ApprovalKind,
        operation_sha256: str,
        issued_at: datetime,
        expires_at: datetime,
        currency: str | None = None,
        maximum_amount_micros: int | None = None,
    ) -> ApprovalGrant:
        return cls(
            grant_id=grant_id,
            project=project,
            kind=kind,
            operation_sha256=operation_sha256,
            currency=currency,
            maximum_amount_micros=maximum_amount_micros,
            issued_at=issued_at,
            expires_at=expires_at,
        )


__all__ = ["ApprovalGrant", "ApprovalKind"]
