"""Enforce one account launch plan per logical-account revision.

Revision ID: 0017_account_launch_plan_unique
Revises: 0016_mcp_task_submission_policy
Create Date: 2026-08-22
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017_account_launch_plan_unique"
down_revision: str | Sequence[str] | None = "0016_mcp_task_submission_policy"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_INDEX_NAME = "uq_incubation_artifacts_account_launch_plan_version"


def _require_clean_launch_plan_versions() -> None:
    """Fail closed instead of choosing which immutable artifact to retain."""
    duplicate = (
        op.get_bind()
        .execute(
            sa.text(
                """
                SELECT owner_user_id,
                       project_id,
                       logical_account_id,
                       artifact_version,
                       COUNT(*) AS artifact_count
                FROM incubation_artifacts
                WHERE artifact_type = 'account_launch_plan'
                  AND logical_account_id IS NOT NULL
                GROUP BY owner_user_id,
                         project_id,
                         logical_account_id,
                         artifact_version
                HAVING COUNT(*) > 1
                LIMIT 1
                """
            )
        )
        .mappings()
        .first()
    )
    if duplicate is None:
        return
    raise RuntimeError(
        "migration 0017 found duplicate account_launch_plan version "
        f"{duplicate['artifact_version']!r} for owner {duplicate['owner_user_id']!r}, "
        f"project {duplicate['project_id']!r}, logical account {duplicate['logical_account_id']!r} "
        f"({duplicate['artifact_count']} immutable artifacts); refusing to choose or delete one"
    )


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("incubation_artifacts"):
        return
    existing = {index["name"] for index in inspector.get_indexes("incubation_artifacts")}
    if _INDEX_NAME in existing:
        return
    _require_clean_launch_plan_versions()
    op.create_index(
        _INDEX_NAME,
        "incubation_artifacts",
        [
            "owner_user_id",
            "project_id",
            "logical_account_id",
            "artifact_version",
        ],
        unique=True,
        sqlite_where=sa.text("artifact_type = 'account_launch_plan'"),
        postgresql_where=sa.text("artifact_type = 'account_launch_plan'"),
    )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("incubation_artifacts"):
        return
    existing = {index["name"] for index in inspector.get_indexes("incubation_artifacts")}
    if _INDEX_NAME in existing:
        op.drop_index(_INDEX_NAME, table_name="incubation_artifacts")
