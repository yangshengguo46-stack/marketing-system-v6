from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, BigInteger, CheckConstraint, DateTime, ForeignKeyConstraint, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from deerflow.persistence.base import Base


def _utc_now() -> datetime:
    return datetime.now(UTC)


class IncubationProjectRow(Base):
    __tablename__ = "incubation_projects"

    owner_user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        onupdate=_utc_now,
    )

    __table_args__ = (Index("ix_incubation_projects_owner_updated", "owner_user_id", "updated_at"),)


class IncubationLogicalAccountRow(Base):
    __tablename__ = "incubation_logical_accounts"

    owner_user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    logical_account_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        onupdate=_utc_now,
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["owner_user_id", "project_id"],
            ["incubation_projects.owner_user_id", "incubation_projects.project_id"],
            name="fk_incubation_logical_accounts_project",
            ondelete="CASCADE",
        ),
        Index(
            "ix_incubation_logical_accounts_project_updated",
            "owner_user_id",
            "project_id",
            "updated_at",
        ),
    )


class IncubationPlatformAccountRow(Base):
    __tablename__ = "incubation_platform_accounts"

    owner_user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    account_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    logical_account_id: Mapped[str] = mapped_column(String(64), nullable=False)
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    external_account_id: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        onupdate=_utc_now,
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["owner_user_id", "project_id"],
            ["incubation_projects.owner_user_id", "incubation_projects.project_id"],
            name="fk_incubation_accounts_project",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["owner_user_id", "project_id", "logical_account_id"],
            [
                "incubation_logical_accounts.owner_user_id",
                "incubation_logical_accounts.project_id",
                "incubation_logical_accounts.logical_account_id",
            ],
            name="fk_incubation_platform_accounts_logical_account",
            ondelete="RESTRICT",
        ),
        Index(
            "ix_incubation_accounts_owner_platform",
            "owner_user_id",
            "platform",
        ),
    )


class IncubationArtifactRow(Base):
    __tablename__ = "incubation_artifacts"

    artifact_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    owner_user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    project_id: Mapped[str] = mapped_column(String(64), nullable=False)
    logical_account_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    account_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    account_platform: Mapped[str | None] = mapped_column(String(32), nullable=True)
    artifact_type: Mapped[str] = mapped_column(String(128), nullable=False)
    artifact_version: Mapped[int] = mapped_column(Integer, nullable=False)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    parents_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    evidence_role: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_thread_id: Mapped[str] = mapped_column(String(64), nullable=False)
    source_run_id: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    stored_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utc_now)

    __table_args__ = (
        ForeignKeyConstraint(
            ["owner_user_id", "project_id"],
            ["incubation_projects.owner_user_id", "incubation_projects.project_id"],
            name="fk_incubation_artifacts_project",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["owner_user_id", "project_id", "logical_account_id"],
            [
                "incubation_logical_accounts.owner_user_id",
                "incubation_logical_accounts.project_id",
                "incubation_logical_accounts.logical_account_id",
            ],
            name="fk_incubation_artifacts_logical_account",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["owner_user_id", "project_id", "account_id"],
            [
                "incubation_platform_accounts.owner_user_id",
                "incubation_platform_accounts.project_id",
                "incubation_platform_accounts.account_id",
            ],
            name="fk_incubation_artifacts_account",
            ondelete="RESTRICT",
        ),
        Index(
            "ix_incubation_artifacts_project_created",
            "owner_user_id",
            "project_id",
            "created_at",
        ),
        Index(
            "ix_incubation_artifacts_project_type",
            "owner_user_id",
            "project_id",
            "artifact_type",
        ),
        Index(
            "ix_incubation_artifacts_logical_account_type",
            "owner_user_id",
            "project_id",
            "logical_account_id",
            "artifact_type",
        ),
        Index(
            "ix_incubation_artifacts_project_evidence_role",
            "owner_user_id",
            "project_id",
            "evidence_role",
        ),
    )


class IncubationApprovalGrantRow(Base):
    __tablename__ = "incubation_approval_grants"

    grant_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    owner_user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    project_id: Mapped[str] = mapped_column(String(64), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    operation_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    maximum_amount_micros: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    bound_local_task_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    bound_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    stored_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utc_now)

    __table_args__ = (
        ForeignKeyConstraint(
            ["owner_user_id", "project_id"],
            ["incubation_projects.owner_user_id", "incubation_projects.project_id"],
            name="fk_incubation_approval_grants_project",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "kind IN ('cloud_processing','fee_authorization')",
            name="ck_incubation_approval_grants_kind",
        ),
        CheckConstraint(
            "(kind = 'cloud_processing' AND currency IS NULL AND maximum_amount_micros IS NULL) OR (kind = 'fee_authorization' AND currency IS NOT NULL AND maximum_amount_micros > 0)",
            name="ck_incubation_approval_grants_fee_shape",
        ),
        CheckConstraint(
            "(bound_local_task_id IS NULL AND bound_at IS NULL) OR (bound_local_task_id IS NOT NULL AND bound_at IS NOT NULL)",
            name="ck_incubation_approval_grants_binding",
        ),
        CheckConstraint(
            "NOT (revoked_at IS NOT NULL AND bound_local_task_id IS NOT NULL)",
            name="ck_incubation_approval_grants_revocation",
        ),
        CheckConstraint(
            "expires_at > issued_at",
            name="ck_incubation_approval_grants_expiry",
        ),
        Index(
            "ix_incubation_approval_grants_project_issued",
            "owner_user_id",
            "project_id",
            "issued_at",
        ),
        Index(
            "ix_incubation_approval_grants_operation",
            "owner_user_id",
            "project_id",
            "operation_sha256",
        ),
    )
