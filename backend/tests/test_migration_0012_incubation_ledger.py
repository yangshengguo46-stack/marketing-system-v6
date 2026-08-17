from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from deerflow.persistence.bootstrap import bootstrap_schema

pytestmark = pytest.mark.asyncio


async def test_0011_database_upgrades_to_owner_scoped_incubation_ledger(tmp_path: Path) -> None:
    db_path = tmp_path / "from-0011.db"
    sync_engine = sa.create_engine(f"sqlite:///{db_path.as_posix()}")
    try:
        with sync_engine.begin() as connection:
            connection.execute(sa.text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
            connection.execute(sa.text("INSERT INTO alembic_version (version_num) VALUES ('0011_mcp_tasks')"))
    finally:
        sync_engine.dispose()

    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path.as_posix()}")
    try:
        await bootstrap_schema(engine, backend="sqlite")
    finally:
        await engine.dispose()

    with sqlite3.connect(db_path) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()}
        version = connection.execute("SELECT version_num FROM alembic_version").fetchone()
        project_pk = [row[1] for row in connection.execute("PRAGMA table_info(incubation_projects)").fetchall() if row[5]]
        account_fks = connection.execute("PRAGMA foreign_key_list(incubation_platform_accounts)").fetchall()
        artifact_fks = connection.execute("PRAGMA foreign_key_list(incubation_artifacts)").fetchall()

    assert version == ("0014_incubation_approval_grants",)
    assert {
        "incubation_projects",
        "incubation_platform_accounts",
        "incubation_artifacts",
    } <= tables
    assert project_pk == ["owner_user_id", "project_id"]
    assert account_fks
    assert artifact_fks
