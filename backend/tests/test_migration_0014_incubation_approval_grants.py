from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from deerflow.persistence.bootstrap import bootstrap_schema

pytestmark = pytest.mark.asyncio


async def test_0014_adds_incubation_approval_grants_to_versioned_database(tmp_path: Path) -> None:
    db_path = tmp_path / "from-0013.db"
    sync_engine = sa.create_engine(f"sqlite:///{db_path.as_posix()}")
    try:
        with sync_engine.begin() as connection:
            connection.execute(sa.text("CREATE TABLE alembic_version (version_num VARCHAR(64) NOT NULL)"))
            connection.execute(sa.text("INSERT INTO alembic_version (version_num) VALUES ('0013_mcp_task_submission_intent')"))
            connection.execute(
                sa.text(
                    "CREATE TABLE incubation_projects ("
                    "owner_user_id VARCHAR(64) NOT NULL, "
                    "project_id VARCHAR(64) NOT NULL, "
                    "display_name VARCHAR(255) NOT NULL, "
                    "created_at DATETIME NOT NULL, "
                    "updated_at DATETIME NOT NULL, "
                    "PRIMARY KEY (owner_user_id, project_id))"
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
        version = connection.execute("SELECT version_num FROM alembic_version").fetchone()
        columns = {row[1]: row for row in connection.execute("PRAGMA table_info(incubation_approval_grants)").fetchall()}
        foreign_keys = connection.execute("PRAGMA foreign_key_list(incubation_approval_grants)").fetchall()

    assert version == ("0015_incubation_logical_accounts",)
    assert {
        "grant_id",
        "owner_user_id",
        "project_id",
        "kind",
        "operation_sha256",
        "currency",
        "maximum_amount_micros",
        "issued_at",
        "expires_at",
        "revoked_at",
        "bound_local_task_id",
        "bound_at",
        "stored_at",
    } <= set(columns)
    assert {(row[2], row[3]) for row in foreign_keys} == {
        ("incubation_projects", "owner_user_id"),
        ("incubation_projects", "project_id"),
    }
