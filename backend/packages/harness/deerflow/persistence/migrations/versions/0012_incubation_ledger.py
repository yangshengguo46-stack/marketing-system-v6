"""owner-scoped incubation artifact ledger.

Revision ID: 0012_incubation_ledger
Revises: 0011_mcp_tasks
Create Date: 2026-08-16
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012_incubation_ledger"
down_revision: str | Sequence[str] | None = "0011_mcp_tasks"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing = set(inspector.get_table_names())

    if "incubation_projects" not in existing:
        op.create_table(
            "incubation_projects",
            sa.Column("owner_user_id", sa.String(length=64), nullable=False),
            sa.Column("project_id", sa.String(length=64), nullable=False),
            sa.Column("display_name", sa.String(length=255), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("owner_user_id", "project_id"),
        )
        op.create_index(
            "ix_incubation_projects_owner_updated",
            "incubation_projects",
            ["owner_user_id", "updated_at"],
            unique=False,
        )

    if "incubation_platform_accounts" not in existing:
        op.create_table(
            "incubation_platform_accounts",
            sa.Column("owner_user_id", sa.String(length=64), nullable=False),
            sa.Column("project_id", sa.String(length=64), nullable=False),
            sa.Column("account_id", sa.String(length=64), nullable=False),
            sa.Column("platform", sa.String(length=32), nullable=False),
            sa.Column("external_account_id", sa.String(length=255), nullable=False),
            sa.Column("display_name", sa.String(length=255), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(
                ["owner_user_id", "project_id"],
                ["incubation_projects.owner_user_id", "incubation_projects.project_id"],
                name="fk_incubation_accounts_project",
                ondelete="CASCADE",
            ),
            sa.PrimaryKeyConstraint("owner_user_id", "project_id", "account_id"),
        )
        op.create_index(
            "ix_incubation_accounts_owner_platform",
            "incubation_platform_accounts",
            ["owner_user_id", "platform"],
            unique=False,
        )

    if "incubation_artifacts" not in existing:
        op.create_table(
            "incubation_artifacts",
            sa.Column("artifact_id", sa.String(length=80), nullable=False),
            sa.Column("owner_user_id", sa.String(length=64), nullable=False),
            sa.Column("project_id", sa.String(length=64), nullable=False),
            sa.Column("account_id", sa.String(length=64), nullable=True),
            sa.Column("account_platform", sa.String(length=32), nullable=True),
            sa.Column("artifact_type", sa.String(length=128), nullable=False),
            sa.Column("artifact_version", sa.Integer(), nullable=False),
            sa.Column("payload_json", sa.JSON(), nullable=False),
            sa.Column("content_sha256", sa.String(length=64), nullable=False),
            sa.Column("parents_json", sa.JSON(), nullable=False),
            sa.Column("evidence_role", sa.String(length=64), nullable=True),
            sa.Column("source_thread_id", sa.String(length=64), nullable=False),
            sa.Column("source_run_id", sa.String(length=64), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("stored_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(
                ["owner_user_id", "project_id", "account_id"],
                [
                    "incubation_platform_accounts.owner_user_id",
                    "incubation_platform_accounts.project_id",
                    "incubation_platform_accounts.account_id",
                ],
                name="fk_incubation_artifacts_account",
                ondelete="RESTRICT",
            ),
            sa.ForeignKeyConstraint(
                ["owner_user_id", "project_id"],
                ["incubation_projects.owner_user_id", "incubation_projects.project_id"],
                name="fk_incubation_artifacts_project",
                ondelete="CASCADE",
            ),
            sa.PrimaryKeyConstraint("artifact_id"),
        )
        op.create_index(
            "ix_incubation_artifacts_project_created",
            "incubation_artifacts",
            ["owner_user_id", "project_id", "created_at"],
            unique=False,
        )
        op.create_index(
            "ix_incubation_artifacts_project_type",
            "incubation_artifacts",
            ["owner_user_id", "project_id", "artifact_type"],
            unique=False,
        )
        op.create_index(
            "ix_incubation_artifacts_project_evidence_role",
            "incubation_artifacts",
            ["owner_user_id", "project_id", "evidence_role"],
            unique=False,
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing = set(inspector.get_table_names())
    if "incubation_artifacts" in existing:
        op.drop_table("incubation_artifacts")
    if "incubation_platform_accounts" in existing:
        op.drop_table("incubation_platform_accounts")
    if "incubation_projects" in existing:
        op.drop_table("incubation_projects")
