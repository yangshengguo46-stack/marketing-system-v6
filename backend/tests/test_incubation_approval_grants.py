from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from pydantic import ValidationError

from deerflow.config.database_config import DatabaseConfig
from deerflow.incubation import (
    ApprovalGrant,
    ApprovalGrantRejectedError,
    IncubationLedgerRepository,
    ProjectRef,
)
from deerflow.persistence.engine import close_engine, get_session_factory, init_engine_from_config

NOW = datetime(2026, 8, 17, 12, 0, tzinfo=UTC)
OPERATION_SHA256 = "a" * 64


@pytest_asyncio.fixture(autouse=True)
async def _close_persistence_engine():
    yield
    await close_engine()


async def _make_repo(tmp_path) -> IncubationLedgerRepository:
    await init_engine_from_config(DatabaseConfig(backend="sqlite", sqlite_dir=str(tmp_path)))
    session_factory = get_session_factory()
    assert session_factory is not None
    return IncubationLedgerRepository(session_factory)


def _project(*, owner: str = "user-1", project_id: str = "project-1") -> ProjectRef:
    return ProjectRef(owner_user_id=owner, project_id=project_id)


def _cloud_grant(
    *,
    grant_id: str = "approval-cloud-1",
    project: ProjectRef | None = None,
    operation_sha256: str = OPERATION_SHA256,
    expires_at: datetime | None = None,
) -> ApprovalGrant:
    return ApprovalGrant.issue(
        grant_id=grant_id,
        project=project or _project(),
        kind="cloud_processing",
        operation_sha256=operation_sha256,
        issued_at=NOW,
        expires_at=expires_at or NOW + timedelta(minutes=30),
    )


def _fee_grant(
    *,
    grant_id: str = "approval-fee-1",
    project: ProjectRef | None = None,
    operation_sha256: str = OPERATION_SHA256,
    expires_at: datetime | None = None,
    maximum_amount_micros: int = 1_000_000,
) -> ApprovalGrant:
    return ApprovalGrant.issue(
        grant_id=grant_id,
        project=project or _project(),
        kind="fee_authorization",
        operation_sha256=operation_sha256,
        issued_at=NOW,
        expires_at=expires_at or NOW + timedelta(minutes=30),
        currency="CNY",
        maximum_amount_micros=maximum_amount_micros,
    )


def test_approval_grant_contract_keeps_cloud_consent_and_fee_limit_distinct() -> None:
    cloud = _cloud_grant()
    fee = _fee_grant()

    assert cloud.currency is None
    assert cloud.maximum_amount_micros is None
    assert fee.currency == "CNY"
    assert fee.maximum_amount_micros == 1_000_000

    with pytest.raises(ValidationError, match="cloud_processing"):
        ApprovalGrant.issue(
            grant_id="approval-invalid-cloud",
            project=_project(),
            kind="cloud_processing",
            operation_sha256=OPERATION_SHA256,
            issued_at=NOW,
            expires_at=NOW + timedelta(minutes=5),
            currency="CNY",
            maximum_amount_micros=1,
        )
    with pytest.raises(ValidationError, match="fee_authorization"):
        ApprovalGrant.issue(
            grant_id="approval-invalid-fee",
            project=_project(),
            kind="fee_authorization",
            operation_sha256=OPERATION_SHA256,
            issued_at=NOW,
            expires_at=NOW + timedelta(minutes=5),
        )


@pytest.mark.asyncio
async def test_approval_pair_binds_atomically_and_same_task_can_recover_after_expiry(tmp_path) -> None:
    repo = await _make_repo(tmp_path)
    project = _project()
    await repo.create_project(project, display_name="Media project")
    await repo.issue_approval_grant(_cloud_grant())
    await repo.issue_approval_grant(_fee_grant())

    first = await repo.authorize_approval_pair(
        project=project,
        cloud_processing_grant_id="approval-cloud-1",
        fee_authorization_grant_id="approval-fee-1",
        operation_sha256=OPERATION_SHA256,
        local_task_id="mcp-task-1",
        currency="CNY",
        maximum_amount_micros=1_000_000,
        now=NOW + timedelta(minutes=1),
    )
    recovered = await repo.authorize_approval_pair(
        project=project,
        cloud_processing_grant_id="approval-cloud-1",
        fee_authorization_grant_id="approval-fee-1",
        operation_sha256=OPERATION_SHA256,
        local_task_id="mcp-task-1",
        currency="CNY",
        maximum_amount_micros=1_000_000,
        now=NOW + timedelta(hours=1),
    )

    assert {grant.kind for grant in first} == {"cloud_processing", "fee_authorization"}
    assert all(grant.bound_local_task_id == "mcp-task-1" for grant in first)
    assert [grant.model_dump() for grant in recovered] == [grant.model_dump() for grant in first]

    with pytest.raises(ApprovalGrantRejectedError):
        await repo.authorize_approval_pair(
            project=project,
            cloud_processing_grant_id="approval-cloud-1",
            fee_authorization_grant_id="approval-fee-1",
            operation_sha256=OPERATION_SHA256,
            local_task_id="mcp-task-2",
            currency="CNY",
            maximum_amount_micros=1_000_000,
            now=NOW + timedelta(minutes=2),
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("operation_sha256", "currency", "maximum_amount_micros", "now"),
    [
        ("b" * 64, "CNY", 1_000_000, NOW + timedelta(minutes=1)),
        (OPERATION_SHA256, "USD", 1_000_000, NOW + timedelta(minutes=1)),
        (OPERATION_SHA256, "CNY", 1_000_001, NOW + timedelta(minutes=1)),
        (OPERATION_SHA256, "CNY", 1_000_000, NOW + timedelta(hours=1)),
    ],
)
async def test_rejected_pair_never_partially_consumes_a_grant(
    tmp_path,
    operation_sha256: str,
    currency: str,
    maximum_amount_micros: int,
    now: datetime,
) -> None:
    repo = await _make_repo(tmp_path)
    project = _project()
    await repo.create_project(project, display_name="Media project")
    await repo.issue_approval_grant(_cloud_grant())
    await repo.issue_approval_grant(_fee_grant())

    with pytest.raises(ApprovalGrantRejectedError):
        await repo.authorize_approval_pair(
            project=project,
            cloud_processing_grant_id="approval-cloud-1",
            fee_authorization_grant_id="approval-fee-1",
            operation_sha256=operation_sha256,
            local_task_id="mcp-task-1",
            currency=currency,
            maximum_amount_micros=maximum_amount_micros,
            now=now,
        )

    cloud = await repo.get_approval_grant("approval-cloud-1", owner_user_id="user-1")
    fee = await repo.get_approval_grant("approval-fee-1", owner_user_id="user-1")
    assert cloud is not None and cloud.bound_local_task_id is None
    assert fee is not None and fee.bound_local_task_id is None


@pytest.mark.asyncio
async def test_approval_refs_are_owner_and_project_scoped(tmp_path) -> None:
    repo = await _make_repo(tmp_path)
    alice = _project(owner="alice", project_id="shared")
    bob = _project(owner="bob", project_id="shared")
    await repo.create_project(alice, display_name="Alice")
    await repo.create_project(bob, display_name="Bob")
    await repo.issue_approval_grant(_cloud_grant(project=alice))
    await repo.issue_approval_grant(_fee_grant(project=alice))

    with pytest.raises(ApprovalGrantRejectedError):
        await repo.authorize_approval_pair(
            project=bob,
            cloud_processing_grant_id="approval-cloud-1",
            fee_authorization_grant_id="approval-fee-1",
            operation_sha256=OPERATION_SHA256,
            local_task_id="mcp-task-1",
            currency="CNY",
            maximum_amount_micros=1_000_000,
            now=NOW + timedelta(minutes=1),
        )

    assert await repo.get_approval_grant("approval-cloud-1", owner_user_id="bob") is None


@pytest.mark.asyncio
async def test_only_one_concurrent_task_can_bind_an_approval_pair(tmp_path) -> None:
    repo = await _make_repo(tmp_path)
    project = _project()
    await repo.create_project(project, display_name="Media project")
    await repo.issue_approval_grant(_cloud_grant())
    await repo.issue_approval_grant(_fee_grant())

    async def bind(task_id: str):
        return await repo.authorize_approval_pair(
            project=project,
            cloud_processing_grant_id="approval-cloud-1",
            fee_authorization_grant_id="approval-fee-1",
            operation_sha256=OPERATION_SHA256,
            local_task_id=task_id,
            currency="CNY",
            maximum_amount_micros=1_000_000,
            now=NOW + timedelta(minutes=1),
        )

    results = await asyncio.gather(bind("mcp-task-a"), bind("mcp-task-b"), return_exceptions=True)

    assert sum(not isinstance(result, Exception) for result in results) == 1
    assert sum(isinstance(result, ApprovalGrantRejectedError) for result in results) == 1


@pytest.mark.asyncio
async def test_unbound_grant_can_be_revoked_but_bound_grant_cannot_be_rewritten(tmp_path) -> None:
    repo = await _make_repo(tmp_path)
    project = _project()
    await repo.create_project(project, display_name="Media project")
    await repo.issue_approval_grant(_cloud_grant())
    await repo.issue_approval_grant(_fee_grant())

    revoked = await repo.revoke_approval_grant(
        "approval-cloud-1",
        owner_user_id="user-1",
        now=NOW + timedelta(minutes=1),
    )
    assert revoked.revoked_at == NOW + timedelta(minutes=1)

    with pytest.raises(ApprovalGrantRejectedError):
        await repo.authorize_approval_pair(
            project=project,
            cloud_processing_grant_id="approval-cloud-1",
            fee_authorization_grant_id="approval-fee-1",
            operation_sha256=OPERATION_SHA256,
            local_task_id="mcp-task-1",
            currency="CNY",
            maximum_amount_micros=1_000_000,
            now=NOW + timedelta(minutes=2),
        )

    replacement = _cloud_grant(grant_id="approval-cloud-2")
    await repo.issue_approval_grant(replacement)
    await repo.authorize_approval_pair(
        project=project,
        cloud_processing_grant_id="approval-cloud-2",
        fee_authorization_grant_id="approval-fee-1",
        operation_sha256=OPERATION_SHA256,
        local_task_id="mcp-task-2",
        currency="CNY",
        maximum_amount_micros=1_000_000,
        now=NOW + timedelta(minutes=2),
    )
    with pytest.raises(ApprovalGrantRejectedError):
        await repo.revoke_approval_grant(
            "approval-cloud-2",
            owner_user_id="user-1",
            now=NOW + timedelta(minutes=3),
        )
