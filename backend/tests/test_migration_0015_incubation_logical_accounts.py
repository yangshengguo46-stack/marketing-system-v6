from __future__ import annotations

import asyncio
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic import command
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from deerflow.incubation.contracts import (
    ArtifactEnvelope,
    PlatformAccountRef,
    ProjectRef,
)
from deerflow.persistence.bootstrap import _get_alembic_config
from deerflow.persistence.incubation_ledger.sql import IncubationLedgerRepository

pytestmark = pytest.mark.asyncio

REVISION_0014 = "0014_incubation_approval_grants"
REVISION_0015 = "0015_incubation_logical_accounts"
LEGACY_ACCOUNT_A = "legacy-358fb058385a0778f0edcfba48dd8196f7934e16ca25abfa"
LEGACY_ACCOUNT_B = "legacy-174d49d0aba59829d6514842aadc9b929572ee7cb8d90115"
CREATED_AT = datetime(2026, 8, 20, 8, 0, tzinfo=UTC)
STORED_AT = datetime(2026, 8, 20, 9, 0, tzinfo=UTC)
PROJECT_A = ProjectRef(owner_user_id="owner-a", project_id="shared-project")
PROJECT_B = ProjectRef(owner_user_id="owner-b", project_id="shared-project")
PLATFORM_ACCOUNT_A = PlatformAccountRef(
    owner_user_id="owner-a",
    project_id="shared-project",
    account_id="douyin-a",
    platform="douyin",
)

LEGACY_ACCOUNT_ARTIFACT = ArtifactEnvelope.seal(
    project=PROJECT_A,
    account=PLATFORM_ACCOUNT_A,
    artifact_type="account_strategy",
    version=1,
    payload={"content_root": "礼与人与人相处"},
    created_at=CREATED_AT,
    source_thread_id="thread-a",
    source_run_id="run-a",
)
LEGACY_CHILD_ARTIFACT = ArtifactEnvelope.seal(
    project=PROJECT_A,
    artifact_type="topic_brief",
    version=1,
    payload={"topic": "一次送礼为什么改变了两个人的关系"},
    parents=(LEGACY_ACCOUNT_ARTIFACT.to_parent_ref(),),
    created_at=CREATED_AT,
    source_thread_id="thread-a",
    source_run_id="run-a",
)
LEGACY_PROJECT_ARTIFACT = ArtifactEnvelope.seal(
    project=PROJECT_B,
    artifact_type="content_world",
    version=1,
    payload={"content_root": "海鲜世界"},
    created_at=CREATED_AT,
    source_thread_id="thread-b",
    source_run_id="run-b",
)
LEGACY_ARTIFACTS = (
    LEGACY_ACCOUNT_ARTIFACT,
    LEGACY_CHILD_ARTIFACT,
    LEGACY_PROJECT_ARTIFACT,
)


async def _migrate(db_path: Path, revision: str, *, downgrade: bool = False) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path.as_posix()}")
    try:
        config = _get_alembic_config(engine)
        operation = command.downgrade if downgrade else command.upgrade
        await asyncio.to_thread(operation, config, revision)
    finally:
        await engine.dispose()


def _artifact_row(artifact: ArtifactEnvelope) -> tuple[object, ...]:
    return (
        artifact.artifact_id,
        artifact.project.owner_user_id,
        artifact.project.project_id,
        artifact.account.account_id if artifact.account is not None else None,
        artifact.account.platform if artifact.account is not None else None,
        artifact.artifact_type,
        artifact.version,
        json.dumps(artifact.payload, ensure_ascii=False, separators=(",", ":")),
        artifact.content_sha256,
        json.dumps(
            [parent.model_dump(mode="json", exclude_none=True) for parent in artifact.parents],
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        artifact.evidence_role,
        artifact.source_thread_id,
        artifact.source_run_id,
        artifact.created_at.isoformat(sep=" "),
        STORED_AT.isoformat(sep=" "),
    )


def _seed_0014_rows(db_path: Path) -> None:
    created_at = CREATED_AT.isoformat(sep=" ")
    updated_at = STORED_AT.isoformat(sep=" ")
    with sqlite3.connect(db_path) as connection:
        connection.executemany(
            "INSERT INTO incubation_projects (owner_user_id, project_id, display_name, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            [
                ("owner-a", "shared-project", "Golden gifts", created_at, updated_at),
                ("owner-b", "shared-project", "Seafood", created_at, updated_at),
            ],
        )
        connection.executemany(
            "INSERT INTO incubation_platform_accounts (owner_user_id, project_id, account_id, platform, external_account_id, display_name, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    "owner-a",
                    "shared-project",
                    "douyin-a",
                    "douyin",
                    "external-a",
                    "Douyin A",
                    created_at,
                    updated_at,
                ),
                (
                    "owner-b",
                    "shared-project",
                    "tiktok-b",
                    "tiktok",
                    "external-b",
                    "TikTok B",
                    created_at,
                    updated_at,
                ),
            ],
        )
        connection.executemany(
            "INSERT INTO incubation_artifacts "
            "(artifact_id, owner_user_id, project_id, account_id, account_platform, "
            "artifact_type, artifact_version, payload_json, content_sha256, parents_json, "
            "evidence_role, source_thread_id, source_run_id, created_at, stored_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [_artifact_row(artifact) for artifact in LEGACY_ARTIFACTS],
        )


def _foreign_key_groups(connection: sqlite3.Connection, table_name: str) -> list[dict[str, object]]:
    groups: dict[int, dict[str, object]] = {}
    for row in connection.execute(f"PRAGMA foreign_key_list({table_name})").fetchall():
        group = groups.setdefault(
            row[0],
            {
                "table": row[2],
                "from": [],
                "to": [],
                "on_delete": row[6],
            },
        )
        group["from"].append(row[3])
        group["to"].append(row[4])
    return list(groups.values())


async def test_0015_backfills_stable_logical_accounts_and_schema_boundaries(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "from-0014.db"
    await _migrate(db_path, REVISION_0014)
    _seed_0014_rows(db_path)

    await _migrate(db_path, REVISION_0015)

    with sqlite3.connect(db_path) as connection:
        version = connection.execute("SELECT version_num FROM alembic_version").fetchone()
        logical_accounts = connection.execute("SELECT owner_user_id, project_id, logical_account_id, display_name FROM incubation_logical_accounts ORDER BY owner_user_id").fetchall()
        platform_rows = connection.execute("SELECT owner_user_id, logical_account_id FROM incubation_platform_accounts ORDER BY owner_user_id").fetchall()
        artifact_rows = connection.execute("SELECT artifact_id, owner_user_id, logical_account_id FROM incubation_artifacts ORDER BY artifact_id").fetchall()
        platform_columns = {row[1]: row for row in connection.execute("PRAGMA table_info(incubation_platform_accounts)").fetchall()}
        artifact_columns = {row[1]: row for row in connection.execute("PRAGMA table_info(incubation_artifacts)").fetchall()}
        logical_indexes = {row[1] for row in connection.execute("PRAGMA index_list(incubation_logical_accounts)").fetchall()}
        artifact_indexes = {row[1] for row in connection.execute("PRAGMA index_list(incubation_artifacts)").fetchall()}
        logical_fks = _foreign_key_groups(connection, "incubation_logical_accounts")
        platform_fks = _foreign_key_groups(connection, "incubation_platform_accounts")
        artifact_fks = _foreign_key_groups(connection, "incubation_artifacts")

    assert version == (REVISION_0015,)
    assert logical_accounts == [
        ("owner-a", "shared-project", LEGACY_ACCOUNT_A, "Golden gifts"),
        ("owner-b", "shared-project", LEGACY_ACCOUNT_B, "Seafood"),
    ]
    assert LEGACY_ACCOUNT_A != LEGACY_ACCOUNT_B
    assert len(LEGACY_ACCOUNT_A) <= 64
    assert len(LEGACY_ACCOUNT_B) <= 64
    assert platform_rows == [
        ("owner-a", LEGACY_ACCOUNT_A),
        ("owner-b", LEGACY_ACCOUNT_B),
    ]
    assert artifact_rows == sorted(
        (
            artifact.artifact_id,
            artifact.project.owner_user_id,
            None,
        )
        for artifact in LEGACY_ARTIFACTS
    )
    assert platform_columns["logical_account_id"][3] == 1
    assert artifact_columns["logical_account_id"][3] == 0
    assert "ix_incubation_logical_accounts_project_updated" in logical_indexes
    assert "ix_incubation_artifacts_logical_account_type" in artifact_indexes
    assert {
        "table": "incubation_projects",
        "from": ["owner_user_id", "project_id"],
        "to": ["owner_user_id", "project_id"],
        "on_delete": "CASCADE",
    } in logical_fks
    assert {
        "table": "incubation_logical_accounts",
        "from": ["owner_user_id", "project_id", "logical_account_id"],
        "to": ["owner_user_id", "project_id", "logical_account_id"],
        "on_delete": "RESTRICT",
    } in platform_fks
    assert {
        "table": "incubation_logical_accounts",
        "from": ["owner_user_id", "project_id", "logical_account_id"],
        "to": ["owner_user_id", "project_id", "logical_account_id"],
        "on_delete": "RESTRICT",
    } in artifact_fks


async def test_0015_enforces_platform_scope_and_allows_project_artifacts(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "constraints.db"
    await _migrate(db_path, REVISION_0014)
    _seed_0014_rows(db_path)
    await _migrate(db_path, REVISION_0015)

    with sqlite3.connect(db_path) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("UPDATE incubation_platform_accounts SET logical_account_id = NULL WHERE account_id = 'douyin-a'")
        connection.execute(
            "UPDATE incubation_artifacts SET logical_account_id = NULL WHERE artifact_id = ?",
            (LEGACY_PROJECT_ARTIFACT.artifact_id,),
        )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE incubation_artifacts SET logical_account_id = 'missing' WHERE artifact_id = ?",
                (LEGACY_ACCOUNT_ARTIFACT.artifact_id,),
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("DELETE FROM incubation_logical_accounts WHERE owner_user_id = 'owner-a'")


async def test_0015_preserves_legacy_artifact_identity_and_parent_refs(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "legacy-artifacts.db"
    await _migrate(db_path, REVISION_0014)
    _seed_0014_rows(db_path)
    await _migrate(db_path, REVISION_0015)

    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path.as_posix()}")
    try:
        repository = IncubationLedgerRepository(async_sessionmaker(engine, expire_on_commit=False))
        restored = []
        for expected in LEGACY_ARTIFACTS:
            artifact = await repository.get_artifact(
                expected.artifact_id,
                owner_user_id=expected.project.owner_user_id,
            )
            assert artifact is not None
            restored.append(artifact)
            assert artifact == expected
            assert artifact.logical_account is None
        assert restored[1].parents == (LEGACY_ACCOUNT_ARTIFACT.to_parent_ref(),)
    finally:
        await engine.dispose()


async def test_0015_downgrade_restores_0014_shape_without_data_loss(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "downgrade.db"
    await _migrate(db_path, REVISION_0014)
    _seed_0014_rows(db_path)
    await _migrate(db_path, REVISION_0015)

    await _migrate(db_path, REVISION_0014, downgrade=True)

    with sqlite3.connect(db_path) as connection:
        version = connection.execute("SELECT version_num FROM alembic_version").fetchone()
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()}
        platform_columns = {row[1] for row in connection.execute("PRAGMA table_info(incubation_platform_accounts)").fetchall()}
        artifact_columns = {row[1] for row in connection.execute("PRAGMA table_info(incubation_artifacts)").fetchall()}
        platform_rows = connection.execute("SELECT owner_user_id, project_id, account_id FROM incubation_platform_accounts ORDER BY owner_user_id").fetchall()
        artifact_rows = connection.execute("SELECT artifact_id, owner_user_id, project_id FROM incubation_artifacts ORDER BY artifact_id").fetchall()

    assert version == (REVISION_0014,)
    assert "incubation_logical_accounts" not in tables
    assert "logical_account_id" not in platform_columns
    assert "logical_account_id" not in artifact_columns
    assert platform_rows == [
        ("owner-a", "shared-project", "douyin-a"),
        ("owner-b", "shared-project", "tiktok-b"),
    ]
    assert artifact_rows == sorted(
        (
            artifact.artifact_id,
            artifact.project.owner_user_id,
            artifact.project.project_id,
        )
        for artifact in LEGACY_ARTIFACTS
    )
