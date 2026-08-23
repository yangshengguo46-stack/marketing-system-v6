"""Add durable MCP task submission policies.

Revision ID: 0016_mcp_task_submission_policy
Revises: 0015_incubation_logical_accounts
Create Date: 2026-08-22
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016_mcp_task_submission_policy"
down_revision: str | Sequence[str] | None = "0015_incubation_logical_accounts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_POLICY_CONSTRAINT = "ck_mcp_tasks_submission_policy"
_DOWNGRADE_FENCE_ERROR = "At-most-once task requires manual review after schema downgrade; automatic submission is disabled"


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("mcp_tasks"):
        return
    columns = {column["name"] for column in inspector.get_columns("mcp_tasks")}
    constraints = {constraint["name"] for constraint in inspector.get_check_constraints("mcp_tasks") if constraint.get("name")}
    with op.batch_alter_table("mcp_tasks", schema=None) as batch_op:
        if "submission_policy" not in columns:
            batch_op.add_column(
                sa.Column(
                    "submission_policy",
                    sa.String(length=32),
                    nullable=False,
                    server_default="idempotent_retry",
                )
            )
        if "submission_started_at" not in columns:
            batch_op.add_column(
                sa.Column(
                    "submission_started_at",
                    sa.DateTime(timezone=True),
                    nullable=True,
                )
            )
        if _POLICY_CONSTRAINT not in constraints:
            batch_op.create_check_constraint(
                _POLICY_CONSTRAINT,
                "submission_policy IN ('idempotent_retry', 'at_most_once')",
            )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("mcp_tasks"):
        return
    columns = {column["name"] for column in inspector.get_columns("mcp_tasks")}
    constraints = {constraint["name"] for constraint in inspector.get_check_constraints("mcp_tasks") if constraint.get("name")}
    if "submission_policy" in columns:
        # 0015 workers do not know about submission policies. If a queued
        # at-most-once row survived the downgrade as ``submission_pending``,
        # an old worker could claim and resubmit it after the cost fence column
        # disappears. Terminalize every such intent before dropping metadata;
        # this is conservative even when the provider call has not started.
        op.get_bind().execute(
            sa.text(
                """
                UPDATE mcp_tasks
                SET status = 'submission_unknown',
                    submit_arguments = NULL,
                    result = NULL,
                    error = :fence_error,
                    input_required = NULL,
                    notification_status = 'pending',
                    next_poll_at = NULL,
                    last_poll_error = :fence_error,
                    lease_owner = NULL,
                    lease_expires_at = NULL,
                    completed_at = COALESCE(completed_at, CURRENT_TIMESTAMP),
                    updated_at = CURRENT_TIMESTAMP
                WHERE submission_policy = 'at_most_once'
                  AND status = 'submission_pending'
                """
            ),
            {"fence_error": _DOWNGRADE_FENCE_ERROR},
        )
    with op.batch_alter_table("mcp_tasks", schema=None) as batch_op:
        if _POLICY_CONSTRAINT in constraints:
            batch_op.drop_constraint(_POLICY_CONSTRAINT, type_="check")
        if "submission_started_at" in columns:
            batch_op.drop_column("submission_started_at")
        if "submission_policy" in columns:
            batch_op.drop_column("submission_policy")
