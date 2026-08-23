from __future__ import annotations

import asyncio
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic import command
from sqlalchemy.ext.asyncio import create_async_engine

from deerflow.incubation.contracts import ArtifactEnvelope, LogicalAccountRef, ProjectRef
from deerflow.persistence.bootstrap import _get_alembic_config

pytestmark = pytest.mark.asyncio

REVISION_0016 = "0016_mcp_task_submission_policy"
REVISION_0017 = "0017_account_launch_plan_unique"
INDEX_NAME = "uq_incubation_artifacts_account_launch_plan_version"
NOW = datetime(2026, 8, 22, 12, 0, tzinfo=UTC)
PROJECT = ProjectRef(owner_user_id="owner-1", project_id="project-1")
LOGICAL_ACCOUNT = LogicalAccountRef(
    owner_user_id=PROJECT.owner_user_id,
    project_id=PROJECT.project_id,
    logical_account_id="logical-account-1",
)


async def _migrate(db_path: Path, revision: str, *, downgrade: bool = False) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path.as_posix()}")
    try:
        config = _get_alembic_config(engine)
        operation = command.downgrade if downgrade else command.upgrade
        await asyncio.to_thread(operation, config, revision)
    finally:
        await engine.dispose()


def _artifact(*, payload: dict[str, str], version: int = 1, artifact_type: str = "account_launch_plan") -> ArtifactEnvelope:
    return ArtifactEnvelope.seal(
        project=PROJECT,
        logical_account=LOGICAL_ACCOUNT,
        artifact_type=artifact_type,
        version=version,
        payload=payload,
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-1",
    )


def _seed_scope(connection: sqlite3.Connection) -> None:
    timestamp = NOW.isoformat(sep=" ")
    connection.execute(
        "INSERT INTO incubation_projects (owner_user_id, project_id, display_name, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        (
            PROJECT.owner_user_id,
            PROJECT.project_id,
            "Launch project",
            timestamp,
            timestamp,
        ),
    )
    connection.execute(
        "INSERT INTO incubation_logical_accounts (owner_user_id, project_id, logical_account_id, display_name, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
        (
            LOGICAL_ACCOUNT.owner_user_id,
            LOGICAL_ACCOUNT.project_id,
            LOGICAL_ACCOUNT.logical_account_id,
            "Launch account",
            timestamp,
            timestamp,
        ),
    )


def _insert_artifact(connection: sqlite3.Connection, artifact: ArtifactEnvelope) -> None:
    timestamp = NOW.isoformat(sep=" ")
    connection.execute(
        "INSERT INTO incubation_artifacts "
        "(artifact_id, owner_user_id, project_id, logical_account_id, account_id, "
        "account_platform, artifact_type, artifact_version, payload_json, content_sha256, "
        "parents_json, evidence_role, source_thread_id, source_run_id, created_at, stored_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            artifact.artifact_id,
            artifact.project.owner_user_id,
            artifact.project.project_id,
            artifact.logical_account.logical_account_id if artifact.logical_account is not None else None,
            None,
            None,
            artifact.artifact_type,
            artifact.version,
            json.dumps(artifact.payload, ensure_ascii=False, separators=(",", ":")),
            artifact.content_sha256,
            "[]",
            artifact.evidence_role,
            artifact.source_thread_id,
            artifact.source_run_id,
            timestamp,
            timestamp,
        ),
    )


async def test_0017_enforces_launch_plan_version_uniqueness_and_downgrade_preserves_artifacts(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "account-launch-plan-unique.db"
    await _migrate(db_path, REVISION_0016)
    first = _artifact(payload={"plan": "first"})
    conflicting = _artifact(payload={"plan": "conflicting"})
    second_version = _artifact(payload={"plan": "version two"}, version=2)
    unrelated = _artifact(payload={"plan": "not a launch plan"}, artifact_type="topic_brief")
    with sqlite3.connect(db_path) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        _seed_scope(connection)
        _insert_artifact(connection, first)
        _insert_artifact(connection, unrelated)

    await _migrate(db_path, REVISION_0017)

    with sqlite3.connect(db_path) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        version = connection.execute("SELECT version_num FROM alembic_version").fetchone()
        indexes = {row[1]: row for row in connection.execute("PRAGMA index_list(incubation_artifacts)").fetchall()}
        index_sql = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'index' AND name = ?",
            (INDEX_NAME,),
        ).fetchone()[0]
        assert version == (REVISION_0017,)
        assert indexes[INDEX_NAME][2] == 1
        assert "WHERE artifact_type = 'account_launch_plan'" in index_sql
        with pytest.raises(sqlite3.IntegrityError):
            _insert_artifact(connection, conflicting)
        _insert_artifact(connection, second_version)

    await _migrate(db_path, REVISION_0016, downgrade=True)

    with sqlite3.connect(db_path) as connection:
        version = connection.execute("SELECT version_num FROM alembic_version").fetchone()
        indexes = {row[1] for row in connection.execute("PRAGMA index_list(incubation_artifacts)").fetchall()}
        retained = connection.execute("SELECT artifact_id FROM incubation_artifacts ORDER BY artifact_id").fetchall()
        assert version == (REVISION_0016,)
        assert INDEX_NAME not in indexes
        assert retained == sorted([(first.artifact_id,), (second_version.artifact_id,), (unrelated.artifact_id,)])
        _insert_artifact(connection, conflicting)


async def test_0017_upgrade_fails_closed_when_existing_launch_plans_are_duplicated(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "account-launch-plan-duplicate.db"
    await _migrate(db_path, REVISION_0016)
    first = _artifact(payload={"plan": "first duplicate"})
    conflicting = _artifact(payload={"plan": "second duplicate"})
    with sqlite3.connect(db_path) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        _seed_scope(connection)
        _insert_artifact(connection, first)
        _insert_artifact(connection, conflicting)

    with pytest.raises(RuntimeError, match="duplicate account_launch_plan version"):
        await _migrate(db_path, REVISION_0017)

    with sqlite3.connect(db_path) as connection:
        version = connection.execute("SELECT version_num FROM alembic_version").fetchone()
        indexes = {row[1] for row in connection.execute("PRAGMA index_list(incubation_artifacts)").fetchall()}
        retained = connection.execute("SELECT artifact_id FROM incubation_artifacts WHERE artifact_type = 'account_launch_plan' ORDER BY artifact_id").fetchall()

    assert version == (REVISION_0016,)
    assert INDEX_NAME not in indexes
    assert retained == sorted([(first.artifact_id,), (conflicting.artifact_id,)])
