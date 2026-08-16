"""durable task submission intents.

Revision ID: 0013_mcp_task_submission_intent
Revises: 0012_incubation_ledger
Create Date: 2026-08-17
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013_mcp_task_submission_intent"
down_revision: str | Sequence[str] | None = "0012_incubation_ledger"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("mcp_tasks"):
        return
    columns = {column["name"]: column for column in inspector.get_columns("mcp_tasks")}
    with op.batch_alter_table("mcp_tasks", schema=None) as batch_op:
        if "submit_arguments" not in columns:
            batch_op.add_column(sa.Column("submit_arguments", sa.JSON(), nullable=True))
        if not columns["remote_task_id"]["nullable"]:
            batch_op.alter_column(
                "remote_task_id",
                existing_type=sa.String(length=255),
                nullable=True,
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("mcp_tasks"):
        return
    columns = {column["name"]: column for column in inspector.get_columns("mcp_tasks")}
    if columns["remote_task_id"]["nullable"]:
        pending_rows = bind.execute(sa.text("SELECT id FROM mcp_tasks WHERE remote_task_id IS NULL")).fetchall()
        for (task_id,) in pending_rows:
            bind.execute(
                sa.text("UPDATE mcp_tasks SET remote_task_id = :remote_task_id WHERE id = :task_id"),
                {"remote_task_id": f"orphaned:{task_id}", "task_id": task_id},
            )
    with op.batch_alter_table("mcp_tasks", schema=None) as batch_op:
        if "submit_arguments" in columns:
            batch_op.drop_column("submit_arguments")
        if columns["remote_task_id"]["nullable"]:
            batch_op.alter_column(
                "remote_task_id",
                existing_type=sa.String(length=255),
                nullable=False,
            )
