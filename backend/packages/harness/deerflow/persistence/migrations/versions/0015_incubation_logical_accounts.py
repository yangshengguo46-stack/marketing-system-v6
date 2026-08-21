"""Add logical-account scope to the incubation ledger.

Revision ID: 0015_incubation_logical_accounts
Revises: 0014_incubation_approval_grants
Create Date: 2026-08-21
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015_incubation_logical_accounts"
down_revision: str | Sequence[str] | None = "0014_incubation_approval_grants"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LOGICAL_ACCOUNTS_TABLE = "incubation_logical_accounts"
PLATFORM_ACCOUNTS_TABLE = "incubation_platform_accounts"
ARTIFACTS_TABLE = "incubation_artifacts"

FK_LOGICAL_ACCOUNT_PROJECT = "fk_incubation_logical_accounts_project"
FK_PLATFORM_LOGICAL_ACCOUNT = "fk_incubation_platform_accounts_logical_account"
FK_ARTIFACT_LOGICAL_ACCOUNT = "fk_incubation_artifacts_logical_account"

IX_LOGICAL_ACCOUNT_PROJECT_UPDATED = "ix_incubation_logical_accounts_project_updated"
IX_ARTIFACT_LOGICAL_ACCOUNT_TYPE = "ix_incubation_artifacts_logical_account_type"


def _legacy_logical_account_id(owner_user_id: str, project_id: str) -> str:
    identity = f"incubation-logical-account:v1\0{owner_user_id}\0{project_id}"
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:48]
    return f"legacy-{digest}"


def _table_names() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _column_metadata(table_name: str) -> dict[str, dict]:
    return {column["name"]: column for column in sa.inspect(op.get_bind()).get_columns(table_name)}


def _index_names(table_name: str) -> set[str]:
    return {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table_name) if index.get("name")}


def _foreign_key_names(table_name: str) -> set[str]:
    return {foreign_key["name"] for foreign_key in sa.inspect(op.get_bind()).get_foreign_keys(table_name) if foreign_key.get("name")}


def _create_logical_accounts_table() -> None:
    if LOGICAL_ACCOUNTS_TABLE in _table_names():
        return
    op.create_table(
        LOGICAL_ACCOUNTS_TABLE,
        sa.Column("owner_user_id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("logical_account_id", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["owner_user_id", "project_id"],
            [
                "incubation_projects.owner_user_id",
                "incubation_projects.project_id",
            ],
            name=FK_LOGICAL_ACCOUNT_PROJECT,
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "owner_user_id",
            "project_id",
            "logical_account_id",
        ),
    )


def _add_nullable_scope_columns() -> None:
    if PLATFORM_ACCOUNTS_TABLE in _table_names():
        columns = _column_metadata(PLATFORM_ACCOUNTS_TABLE)
        if "logical_account_id" not in columns:
            with op.batch_alter_table(
                PLATFORM_ACCOUNTS_TABLE,
                schema=None,
            ) as batch_op:
                batch_op.add_column(
                    sa.Column(
                        "logical_account_id",
                        sa.String(length=64),
                        nullable=True,
                    )
                )

    if ARTIFACTS_TABLE in _table_names():
        columns = _column_metadata(ARTIFACTS_TABLE)
        if "logical_account_id" not in columns:
            with op.batch_alter_table(ARTIFACTS_TABLE, schema=None) as batch_op:
                batch_op.add_column(
                    sa.Column(
                        "logical_account_id",
                        sa.String(length=64),
                        nullable=True,
                    )
                )


def _backfill_legacy_logical_accounts() -> None:
    """Create one legacy account per project and attach platform bindings only.

    Existing artifacts must remain project-scoped: logical-account scope is
    part of their canonical identity, so backfilling it would invalidate both
    their artifact IDs and any parent references to them.
    """

    bind = op.get_bind()
    projects = bind.execute(sa.text("SELECT owner_user_id, project_id, display_name, created_at, updated_at FROM incubation_projects")).mappings()
    for project in projects:
        owner_user_id = project["owner_user_id"]
        project_id = project["project_id"]
        logical_account_id = _legacy_logical_account_id(
            owner_user_id,
            project_id,
        )
        exists = bind.execute(
            sa.text(f"SELECT 1 FROM {LOGICAL_ACCOUNTS_TABLE} WHERE owner_user_id = :owner_user_id AND project_id = :project_id AND logical_account_id = :logical_account_id"),
            {
                "owner_user_id": owner_user_id,
                "project_id": project_id,
                "logical_account_id": logical_account_id,
            },
        ).first()
        if exists is None:
            bind.execute(
                sa.text(
                    f"INSERT INTO {LOGICAL_ACCOUNTS_TABLE} "
                    "(owner_user_id, project_id, logical_account_id, display_name, "
                    "created_at, updated_at) VALUES (:owner_user_id, :project_id, "
                    ":logical_account_id, :display_name, :created_at, :updated_at)"
                ),
                {
                    "owner_user_id": owner_user_id,
                    "project_id": project_id,
                    "logical_account_id": logical_account_id,
                    "display_name": project["display_name"],
                    "created_at": project["created_at"],
                    "updated_at": project["updated_at"],
                },
            )

        if PLATFORM_ACCOUNTS_TABLE in _table_names():
            bind.execute(
                sa.text(f"UPDATE {PLATFORM_ACCOUNTS_TABLE} SET logical_account_id = :logical_account_id WHERE owner_user_id = :owner_user_id AND project_id = :project_id AND logical_account_id IS NULL"),
                {
                    "owner_user_id": owner_user_id,
                    "project_id": project_id,
                    "logical_account_id": logical_account_id,
                },
            )


def _constrain_scope_columns() -> None:
    bind = op.get_bind()
    if PLATFORM_ACCOUNTS_TABLE in _table_names():
        unscoped_count = bind.execute(sa.text(f"SELECT COUNT(*) FROM {PLATFORM_ACCOUNTS_TABLE} WHERE logical_account_id IS NULL")).scalar_one()
        if unscoped_count:
            raise RuntimeError(f"Cannot make incubation platform-account scope non-null: {unscoped_count} row(s) have no matching incubation project")

        columns = _column_metadata(PLATFORM_ACCOUNTS_TABLE)
        foreign_keys = _foreign_key_names(PLATFORM_ACCOUNTS_TABLE)
        needs_not_null = columns["logical_account_id"]["nullable"]
        needs_foreign_key = FK_PLATFORM_LOGICAL_ACCOUNT not in foreign_keys
        if needs_not_null or needs_foreign_key:
            with op.batch_alter_table(
                PLATFORM_ACCOUNTS_TABLE,
                schema=None,
            ) as batch_op:
                if needs_not_null:
                    batch_op.alter_column(
                        "logical_account_id",
                        existing_type=sa.String(length=64),
                        nullable=False,
                    )
                if needs_foreign_key:
                    batch_op.create_foreign_key(
                        FK_PLATFORM_LOGICAL_ACCOUNT,
                        LOGICAL_ACCOUNTS_TABLE,
                        ["owner_user_id", "project_id", "logical_account_id"],
                        ["owner_user_id", "project_id", "logical_account_id"],
                        ondelete="RESTRICT",
                    )

    if ARTIFACTS_TABLE in _table_names():
        foreign_keys = _foreign_key_names(ARTIFACTS_TABLE)
        if FK_ARTIFACT_LOGICAL_ACCOUNT not in foreign_keys:
            with op.batch_alter_table(ARTIFACTS_TABLE, schema=None) as batch_op:
                batch_op.create_foreign_key(
                    FK_ARTIFACT_LOGICAL_ACCOUNT,
                    LOGICAL_ACCOUNTS_TABLE,
                    ["owner_user_id", "project_id", "logical_account_id"],
                    ["owner_user_id", "project_id", "logical_account_id"],
                    ondelete="RESTRICT",
                )


def _create_indexes() -> None:
    if LOGICAL_ACCOUNTS_TABLE in _table_names():
        indexes = _index_names(LOGICAL_ACCOUNTS_TABLE)
        if IX_LOGICAL_ACCOUNT_PROJECT_UPDATED not in indexes:
            op.create_index(
                IX_LOGICAL_ACCOUNT_PROJECT_UPDATED,
                LOGICAL_ACCOUNTS_TABLE,
                ["owner_user_id", "project_id", "updated_at"],
                unique=False,
            )
    if ARTIFACTS_TABLE in _table_names():
        indexes = _index_names(ARTIFACTS_TABLE)
        if IX_ARTIFACT_LOGICAL_ACCOUNT_TYPE not in indexes:
            op.create_index(
                IX_ARTIFACT_LOGICAL_ACCOUNT_TYPE,
                ARTIFACTS_TABLE,
                [
                    "owner_user_id",
                    "project_id",
                    "logical_account_id",
                    "artifact_type",
                ],
                unique=False,
            )


def upgrade() -> None:
    if "incubation_projects" not in _table_names():
        return
    _create_logical_accounts_table()
    _add_nullable_scope_columns()
    _backfill_legacy_logical_accounts()
    _constrain_scope_columns()
    _create_indexes()


def _drop_index_if_present(table_name: str, index_name: str) -> None:
    if table_name in _table_names() and index_name in _index_names(table_name):
        op.drop_index(index_name, table_name=table_name)


def _drop_scope_column(
    table_name: str,
    foreign_key_name: str,
) -> None:
    if table_name not in _table_names():
        return
    columns = _column_metadata(table_name)
    if "logical_account_id" not in columns:
        return
    foreign_keys = _foreign_key_names(table_name)
    with op.batch_alter_table(table_name, schema=None) as batch_op:
        if foreign_key_name in foreign_keys:
            batch_op.drop_constraint(foreign_key_name, type_="foreignkey")
        batch_op.drop_column("logical_account_id")


def downgrade() -> None:
    _drop_index_if_present(
        ARTIFACTS_TABLE,
        IX_ARTIFACT_LOGICAL_ACCOUNT_TYPE,
    )
    _drop_scope_column(ARTIFACTS_TABLE, FK_ARTIFACT_LOGICAL_ACCOUNT)
    _drop_scope_column(PLATFORM_ACCOUNTS_TABLE, FK_PLATFORM_LOGICAL_ACCOUNT)
    if LOGICAL_ACCOUNTS_TABLE in _table_names():
        op.drop_table(LOGICAL_ACCOUNTS_TABLE)
