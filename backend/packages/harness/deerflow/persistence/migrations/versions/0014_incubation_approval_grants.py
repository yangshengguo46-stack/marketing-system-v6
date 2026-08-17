"""Add exact one-task incubation approval grants.

Revision ID: 0014_incubation_approval_grants
Revises: 0013_mcp_task_submission_intent
Create Date: 2026-08-17
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014_incubation_approval_grants"
down_revision: str | Sequence[str] | None = "0013_mcp_task_submission_intent"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "incubation_approval_grants" in set(inspector.get_table_names()):
        return
    op.create_table(
        "incubation_approval_grants",
        sa.Column("grant_id", sa.String(length=80), nullable=False),
        sa.Column("owner_user_id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("operation_sha256", sa.String(length=64), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("maximum_amount_micros", sa.BigInteger(), nullable=True),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("bound_local_task_id", sa.String(length=64), nullable=True),
        sa.Column("bound_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stored_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "kind IN ('cloud_processing','fee_authorization')",
            name="ck_incubation_approval_grants_kind",
        ),
        sa.CheckConstraint(
            "(kind = 'cloud_processing' AND currency IS NULL AND maximum_amount_micros IS NULL) OR (kind = 'fee_authorization' AND currency IS NOT NULL AND maximum_amount_micros > 0)",
            name="ck_incubation_approval_grants_fee_shape",
        ),
        sa.CheckConstraint(
            "(bound_local_task_id IS NULL AND bound_at IS NULL) OR (bound_local_task_id IS NOT NULL AND bound_at IS NOT NULL)",
            name="ck_incubation_approval_grants_binding",
        ),
        sa.CheckConstraint(
            "NOT (revoked_at IS NOT NULL AND bound_local_task_id IS NOT NULL)",
            name="ck_incubation_approval_grants_revocation",
        ),
        sa.CheckConstraint(
            "expires_at > issued_at",
            name="ck_incubation_approval_grants_expiry",
        ),
        sa.ForeignKeyConstraint(
            ["owner_user_id", "project_id"],
            ["incubation_projects.owner_user_id", "incubation_projects.project_id"],
            name="fk_incubation_approval_grants_project",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("grant_id"),
    )
    op.create_index(
        "ix_incubation_approval_grants_project_issued",
        "incubation_approval_grants",
        ["owner_user_id", "project_id", "issued_at"],
        unique=False,
    )
    op.create_index(
        "ix_incubation_approval_grants_operation",
        "incubation_approval_grants",
        ["owner_user_id", "project_id", "operation_sha256"],
        unique=False,
    )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "incubation_approval_grants" in set(inspector.get_table_names()):
        op.drop_table("incubation_approval_grants")
