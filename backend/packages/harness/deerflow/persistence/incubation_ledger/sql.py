from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from deerflow.incubation.contracts import (
    ArtifactEnvelope,
    ArtifactParentRef,
    EvidenceRole,
    PlatformAccountRecord,
    PlatformAccountRef,
    ProjectRecord,
    ProjectRef,
)
from deerflow.persistence.incubation_ledger.model import (
    IncubationArtifactRow,
    IncubationPlatformAccountRow,
    IncubationProjectRow,
)


class IncubationLedgerError(RuntimeError):
    """Base error for incubation truth-ledger invariants."""


class MissingProjectError(IncubationLedgerError):
    """The artifact or account references a project that does not exist."""


class MissingAccountError(IncubationLedgerError):
    """The artifact references an account that is not bound to the project."""


class MissingParentArtifactError(IncubationLedgerError):
    """The artifact lineage references a missing or mismatched parent."""


class ArtifactConflictError(IncubationLedgerError):
    """A content address already exists with different canonical content."""


class ProjectConflictError(IncubationLedgerError):
    """A project identity was replayed with conflicting metadata."""


class AccountConflictError(IncubationLedgerError):
    """An account identity was replayed with conflicting metadata."""


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class IncubationLedgerRepository:
    """Owner-scoped source of truth for incubation artifacts and lineage."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def create_project(self, project: ProjectRef, *, display_name: str) -> ProjectRecord:
        normalized_name = display_name.strip()
        if not normalized_name:
            raise ValueError("project display_name cannot be empty")
        async with self._sf() as session:
            row = await session.get(
                IncubationProjectRow,
                (project.owner_user_id, project.project_id),
            )
            if row is not None:
                if row.display_name != normalized_name:
                    raise ProjectConflictError("project identity already exists with different metadata")
                return self._project_record(row)
            now = datetime.now(UTC)
            row = IncubationProjectRow(
                owner_user_id=project.owner_user_id,
                project_id=project.project_id,
                display_name=normalized_name,
                created_at=now,
                updated_at=now,
            )
            session.add(row)
            await session.commit()
            return self._project_record(row)

    async def get_project(self, project: ProjectRef) -> ProjectRecord | None:
        async with self._sf() as session:
            row = await session.get(
                IncubationProjectRow,
                (project.owner_user_id, project.project_id),
            )
            return self._project_record(row) if row is not None else None

    async def list_projects(
        self,
        owner_user_id: str,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ProjectRecord]:
        if not owner_user_id.strip():
            raise ValueError("owner_user_id cannot be empty")
        if limit < 1 or limit > 1000 or offset < 0:
            raise ValueError("project pagination is out of range")
        stmt = (
            select(IncubationProjectRow)
            .where(IncubationProjectRow.owner_user_id == owner_user_id)
            .order_by(
                IncubationProjectRow.updated_at.desc(),
                IncubationProjectRow.project_id.desc(),
            )
            .limit(limit)
            .offset(offset)
        )
        async with self._sf() as session:
            result = await session.execute(stmt)
            return [self._project_record(row) for row in result.scalars()]

    async def connect_account(
        self,
        account: PlatformAccountRef,
        *,
        external_account_id: str,
        display_name: str,
    ) -> PlatformAccountRecord:
        normalized_external_id = external_account_id.strip()
        normalized_name = display_name.strip()
        if not normalized_external_id or not normalized_name:
            raise ValueError("account external_account_id and display_name cannot be empty")
        async with self._sf() as session:
            if (
                await session.get(
                    IncubationProjectRow,
                    (account.owner_user_id, account.project_id),
                )
                is None
            ):
                raise MissingProjectError(f"project {account.project_id!r} does not exist for owner")
            key = (account.owner_user_id, account.project_id, account.account_id)
            row = await session.get(IncubationPlatformAccountRow, key)
            if row is not None:
                expected = (account.platform, normalized_external_id, normalized_name)
                actual = (row.platform, row.external_account_id, row.display_name)
                if actual != expected:
                    raise AccountConflictError("account identity already exists with different metadata")
                return self._account_record(row)
            now = datetime.now(UTC)
            row = IncubationPlatformAccountRow(
                owner_user_id=account.owner_user_id,
                project_id=account.project_id,
                account_id=account.account_id,
                platform=account.platform,
                external_account_id=normalized_external_id,
                display_name=normalized_name,
                created_at=now,
                updated_at=now,
            )
            session.add(row)
            await session.commit()
            return self._account_record(row)

    async def get_account(self, account: PlatformAccountRef) -> PlatformAccountRecord | None:
        async with self._sf() as session:
            row = await session.get(
                IncubationPlatformAccountRow,
                (account.owner_user_id, account.project_id, account.account_id),
            )
            if row is None or row.platform != account.platform:
                return None
            return self._account_record(row)

    async def put_artifact(self, artifact: ArtifactEnvelope) -> ArtifactEnvelope:
        # Frozen Pydantic models do not deep-freeze nested dicts. Revalidate the
        # full envelope before opening a transaction so a stale content hash can
        # never be committed after an in-memory payload mutation.
        artifact = ArtifactEnvelope.model_validate(artifact.model_dump(mode="python"))
        async with self._sf() as session:
            await self._require_project(session, artifact.project)
            if artifact.account is not None:
                await self._require_account(session, artifact.account)
            await self._require_parents(session, artifact)

            existing = await session.get(IncubationArtifactRow, artifact.artifact_id)
            if existing is not None:
                stored = self._artifact_contract(existing)
                if self._artifact_identity(stored) != self._artifact_identity(artifact):
                    raise ArtifactConflictError(f"artifact id {artifact.artifact_id!r} has conflicting canonical content")
                return stored

            row = IncubationArtifactRow(
                artifact_id=artifact.artifact_id,
                owner_user_id=artifact.project.owner_user_id,
                project_id=artifact.project.project_id,
                account_id=artifact.account.account_id if artifact.account is not None else None,
                account_platform=artifact.account.platform if artifact.account is not None else None,
                artifact_type=artifact.artifact_type,
                artifact_version=artifact.version,
                payload_json=artifact.payload,
                content_sha256=artifact.content_sha256,
                parents_json=[parent.model_dump(mode="json") for parent in artifact.parents],
                evidence_role=artifact.evidence_role,
                source_thread_id=artifact.source_thread_id,
                source_run_id=artifact.source_run_id,
                created_at=artifact.created_at,
                stored_at=datetime.now(UTC),
            )
            session.add(row)
            await session.commit()
            return self._artifact_contract(row)

    async def get_artifact(
        self,
        artifact_id: str,
        *,
        owner_user_id: str,
    ) -> ArtifactEnvelope | None:
        async with self._sf() as session:
            row = await session.get(IncubationArtifactRow, artifact_id)
            if row is None or row.owner_user_id != owner_user_id:
                return None
            return self._artifact_contract(row)

    async def list_artifacts(
        self,
        project: ProjectRef,
        *,
        artifact_type: str | None = None,
        evidence_role: EvidenceRole | None = None,
    ) -> list[ArtifactEnvelope]:
        stmt = select(IncubationArtifactRow).where(
            IncubationArtifactRow.owner_user_id == project.owner_user_id,
            IncubationArtifactRow.project_id == project.project_id,
        )
        if artifact_type is not None:
            stmt = stmt.where(IncubationArtifactRow.artifact_type == artifact_type)
        if evidence_role is not None:
            stmt = stmt.where(IncubationArtifactRow.evidence_role == evidence_role)
        stmt = stmt.order_by(
            IncubationArtifactRow.created_at.asc(),
            IncubationArtifactRow.artifact_id.asc(),
        )
        async with self._sf() as session:
            result = await session.execute(stmt)
            return [self._artifact_contract(row) for row in result.scalars()]

    @staticmethod
    async def _require_project(session: AsyncSession, project: ProjectRef) -> None:
        if (
            await session.get(
                IncubationProjectRow,
                (project.owner_user_id, project.project_id),
            )
            is None
        ):
            raise MissingProjectError(f"project {project.project_id!r} does not exist for owner")

    @staticmethod
    async def _require_account(session: AsyncSession, account: PlatformAccountRef) -> None:
        row = await session.get(
            IncubationPlatformAccountRow,
            (account.owner_user_id, account.project_id, account.account_id),
        )
        if row is None or row.platform != account.platform:
            raise MissingAccountError(f"account {account.account_id!r} is not bound to the project")

    @staticmethod
    async def _require_parents(session: AsyncSession, artifact: ArtifactEnvelope) -> None:
        for parent in artifact.parents:
            row = await session.get(IncubationArtifactRow, parent.artifact_id)
            if row is None or (row.owner_user_id != parent.owner_user_id or row.project_id != parent.project_id or row.artifact_type != parent.artifact_type or row.content_sha256 != parent.content_sha256):
                raise MissingParentArtifactError(f"parent artifact {parent.artifact_id!r} is missing or mismatched")

    @staticmethod
    def _artifact_identity(artifact: ArtifactEnvelope) -> tuple[object, ...]:
        return (
            artifact.artifact_id,
            artifact.project,
            artifact.account,
            artifact.artifact_type,
            artifact.version,
            artifact.content_sha256,
            artifact.parents,
            artifact.evidence_role,
        )

    @staticmethod
    def _project_record(row: IncubationProjectRow) -> ProjectRecord:
        return ProjectRecord(
            project=ProjectRef(
                owner_user_id=row.owner_user_id,
                project_id=row.project_id,
            ),
            display_name=row.display_name,
            created_at=_aware(row.created_at),
            updated_at=_aware(row.updated_at),
        )

    @staticmethod
    def _account_record(row: IncubationPlatformAccountRow) -> PlatformAccountRecord:
        return PlatformAccountRecord(
            account=PlatformAccountRef(
                owner_user_id=row.owner_user_id,
                project_id=row.project_id,
                account_id=row.account_id,
                platform=row.platform,
            ),
            external_account_id=row.external_account_id,
            display_name=row.display_name,
            created_at=_aware(row.created_at),
            updated_at=_aware(row.updated_at),
        )

    @staticmethod
    def _artifact_contract(row: IncubationArtifactRow) -> ArtifactEnvelope:
        account = None
        if row.account_id is not None and row.account_platform is not None:
            account = PlatformAccountRef(
                owner_user_id=row.owner_user_id,
                project_id=row.project_id,
                account_id=row.account_id,
                platform=row.account_platform,
            )
        return ArtifactEnvelope(
            artifact_id=row.artifact_id,
            project=ProjectRef(
                owner_user_id=row.owner_user_id,
                project_id=row.project_id,
            ),
            artifact_type=row.artifact_type,
            version=row.artifact_version,
            payload=row.payload_json,
            content_sha256=row.content_sha256,
            account=account,
            parents=tuple(ArtifactParentRef.model_validate(parent) for parent in row.parents_json),
            evidence_role=row.evidence_role,
            created_at=_aware(row.created_at),
            source_thread_id=row.source_thread_id,
            source_run_id=row.source_run_id,
        )
