from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from deerflow.persistence.bootstrap import bootstrap_schema

pytestmark = pytest.mark.asyncio


def _create_0012_mcp_tasks(engine: sa.Engine) -> sa.Table:
    metadata = sa.MetaData()
    table = sa.Table(
        "mcp_tasks",
        metadata,
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.String(64), nullable=False),
        sa.Column("thread_id", sa.String(64), nullable=False),
        sa.Column("run_id", sa.String(64)),
        sa.Column("tool_call_id", sa.String(128)),
        sa.Column("server_name", sa.String(128), nullable=False),
        sa.Column("driver_name", sa.String(64), nullable=False),
        sa.Column("remote_task_id", sa.String(255), nullable=False),
        sa.Column("task_name", sa.String(255), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("result", sa.JSON()),
        sa.Column("error", sa.Text()),
        sa.Column("input_required", sa.JSON()),
        sa.Column("driver_data", sa.JSON(), nullable=False),
        sa.Column("notification_status", sa.String(16), nullable=False),
        sa.Column("next_poll_at", sa.DateTime(timezone=True)),
        sa.Column("last_polled_at", sa.DateTime(timezone=True)),
        sa.Column("last_poll_error", sa.Text()),
        sa.Column("poll_attempt_count", sa.Integer(), nullable=False),
        sa.Column("consecutive_poll_error_count", sa.Integer(), nullable=False),
        sa.Column("lease_owner", sa.String(128)),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("cancel_requested_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "user_id",
            "server_name",
            "remote_task_id",
            name="uq_mcp_tasks_user_server_remote",
        ),
    )
    metadata.create_all(engine)
    return table


async def test_0012_database_adds_recoverable_submission_intent_fields(tmp_path: Path) -> None:
    db_path = tmp_path / "from-0012.db"
    sync_engine = sa.create_engine(f"sqlite:///{db_path.as_posix()}")
    now = datetime.now(UTC)
    try:
        task_table = _create_0012_mcp_tasks(sync_engine)
        with sync_engine.begin() as connection:
            connection.execute(sa.text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
            connection.execute(sa.text("INSERT INTO alembic_version (version_num) VALUES ('0012_incubation_ledger')"))
            connection.execute(
                task_table.insert().values(
                    id="existing-task",
                    user_id="user-1",
                    thread_id="thread-1",
                    run_id="run-1",
                    tool_call_id="call-1",
                    server_name="reports",
                    driver_name="fake",
                    remote_task_id="remote-1",
                    task_name="Existing task",
                    status="working",
                    result=None,
                    error=None,
                    input_required=None,
                    driver_data={},
                    notification_status="none",
                    next_poll_at=now,
                    last_polled_at=None,
                    last_poll_error=None,
                    poll_attempt_count=0,
                    consecutive_poll_error_count=0,
                    lease_owner=None,
                    lease_expires_at=None,
                    cancel_requested_at=None,
                    completed_at=None,
                    created_at=now,
                    updated_at=now,
                )
            )
    finally:
        sync_engine.dispose()

    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path.as_posix()}")
    try:
        await bootstrap_schema(engine, backend="sqlite")
    finally:
        await engine.dispose()

    with sqlite3.connect(db_path) as connection:
        columns = {row[1]: row for row in connection.execute("PRAGMA table_info(mcp_tasks)").fetchall()}
        version = connection.execute("SELECT version_num FROM alembic_version").fetchone()
        row = connection.execute("SELECT remote_task_id, submit_arguments FROM mcp_tasks WHERE id = 'existing-task'").fetchone()

    assert version == ("0013_mcp_task_submission_intent",)
    assert columns["remote_task_id"][3] == 0
    assert "submit_arguments" in columns
    assert row == ("remote-1", None)
