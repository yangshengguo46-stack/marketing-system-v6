from __future__ import annotations

import asyncio
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from deerflow.persistence.bootstrap import _get_alembic_config, bootstrap_schema
from deerflow.persistence.mcp_tasks import McpTaskRepository

pytestmark = pytest.mark.asyncio


def _create_0015_mcp_tasks(engine: sa.Engine) -> sa.Table:
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
        sa.Column("remote_task_id", sa.String(255)),
        sa.Column("task_name", sa.String(255), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("submit_arguments", sa.JSON()),
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


async def test_0016_backfills_idempotent_policy_and_adds_submission_boundary(tmp_path: Path) -> None:
    db_path = tmp_path / "from-0015.db"
    sync_engine = sa.create_engine(f"sqlite:///{db_path.as_posix()}")
    now = datetime.now(UTC)
    try:
        task_table = _create_0015_mcp_tasks(sync_engine)
        with sync_engine.begin() as connection:
            connection.execute(sa.text("CREATE TABLE alembic_version (version_num VARCHAR(64) NOT NULL)"))
            connection.execute(sa.text("INSERT INTO alembic_version (version_num) VALUES ('0015_incubation_logical_accounts')"))
            connection.execute(
                task_table.insert().values(
                    id="existing-task",
                    user_id="user-1",
                    thread_id="thread-1",
                    run_id=None,
                    tool_call_id=None,
                    server_name="reports",
                    driver_name="fake",
                    remote_task_id="remote-1",
                    task_name="Existing task",
                    status="working",
                    submit_arguments=None,
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
        row = connection.execute("SELECT submission_policy, submission_started_at FROM mcp_tasks WHERE id = 'existing-task'").fetchone()
        table_sql = connection.execute("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'mcp_tasks'").fetchone()[0]

    assert version == ("0017_account_launch_plan_unique",)
    assert columns["submission_policy"][3] == 1
    assert columns["submission_started_at"][3] == 0
    assert row == ("idempotent_retry", None)
    assert "ck_mcp_tasks_submission_policy" in table_sql
    assert "at_most_once" in table_sql


async def test_0016_downgrade_restores_0015_mcp_task_shape(tmp_path: Path) -> None:
    db_path = tmp_path / "downgrade.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path.as_posix()}")
    try:
        config = _get_alembic_config(engine)
        await asyncio.to_thread(command.upgrade, config, "0016_mcp_task_submission_policy")
        await asyncio.to_thread(command.downgrade, config, "0015_incubation_logical_accounts")
    finally:
        await engine.dispose()

    with sqlite3.connect(db_path) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(mcp_tasks)").fetchall()}
        version = connection.execute("SELECT version_num FROM alembic_version").fetchone()

    assert version == ("0015_incubation_logical_accounts",)
    assert "submission_policy" not in columns
    assert "submission_started_at" not in columns


async def test_0016_downgrade_terminalizes_at_most_once_submission_intents(tmp_path: Path) -> None:
    db_path = tmp_path / "downgrade-cost-fence.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path.as_posix()}")
    now = datetime.now(UTC)
    try:
        config = _get_alembic_config(engine)
        await asyncio.to_thread(command.upgrade, config, "0016_mcp_task_submission_policy")
        repository = McpTaskRepository(async_sessionmaker(engine, expire_on_commit=False))
        for task_id in ("queued-at-most-once", "started-at-most-once"):
            await repository.create_submission_intent(
                task_id=task_id,
                user_id="user-1",
                thread_id="thread-1",
                run_id=None,
                tool_call_id=None,
                server_name="ark",
                driver_name="ark-generation",
                task_name="Generate one plan-bound video",
                submit_arguments={"operation_sha256": "a" * 64},
                next_poll_at=now,
                submission_policy="at_most_once",
            )
        async with engine.begin() as connection:
            await connection.execute(
                sa.text(
                    """
                    UPDATE mcp_tasks
                    SET submission_started_at = :started_at,
                        lease_owner = 'worker-1',
                        lease_expires_at = :lease_expires_at
                    WHERE id = 'started-at-most-once'
                    """
                ),
                {"started_at": now, "lease_expires_at": now},
            )

        await asyncio.to_thread(command.downgrade, config, "0015_incubation_logical_accounts")
    finally:
        await engine.dispose()

    with sqlite3.connect(db_path) as connection:
        rows = connection.execute(
            """
            SELECT id, status, submit_arguments, next_poll_at, lease_owner,
                   completed_at, notification_status, error
            FROM mcp_tasks
            WHERE id IN ('queued-at-most-once', 'started-at-most-once')
            ORDER BY id
            """
        ).fetchall()

    assert len(rows) == 2
    for row in rows:
        assert row[1] == "submission_unknown"
        assert row[2] is None
        assert row[3] is None
        assert row[4] is None
        assert row[5] is not None
        assert row[6] == "pending"
        assert "automatic submission is disabled" in row[7]
