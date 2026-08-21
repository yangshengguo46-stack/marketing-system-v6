from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from deerflow.incubation import ArtifactEnvelope, LogicalAccountRef, ProjectRef
from deerflow.incubation.account_direction import (
    AccountDirectionOptionDraft,
    AccountDirectionProposalDraft,
    confirm_account_direction,
    propose_account_direction,
    select_current_account_direction,
)

NOW = datetime(2026, 8, 22, 10, 0, tzinfo=UTC)
PROJECT = ProjectRef(owner_user_id="user-1", project_id="project-1")
ACCOUNT = LogicalAccountRef(
    owner_user_id="user-1",
    project_id="project-1",
    logical_account_id="account-1",
)
OTHER_ACCOUNT = LogicalAccountRef(
    owner_user_id="user-1",
    project_id="project-1",
    logical_account_id="account-2",
)


class _MemoryRepository:
    def __init__(self, artifacts: tuple[ArtifactEnvelope, ...] = ()) -> None:
        self.artifacts = {artifact.artifact_id: artifact for artifact in artifacts}

    async def put_artifact(self, artifact: ArtifactEnvelope) -> ArtifactEnvelope:
        existing = self.artifacts.get(artifact.artifact_id)
        if existing is not None:
            return existing
        self.artifacts[artifact.artifact_id] = artifact
        return artifact

    async def list_artifacts(
        self,
        project: ProjectRef,
        *,
        logical_account: LogicalAccountRef | None = None,
        artifact_type: str | None = None,
        evidence_role: str | None = None,
    ) -> list[ArtifactEnvelope]:
        return sorted(
            (
                artifact
                for artifact in self.artifacts.values()
                if artifact.project == project
                and (logical_account is None or artifact.logical_account == logical_account)
                and (artifact_type is None or artifact.artifact_type == artifact_type)
                and (evidence_role is None or artifact.evidence_role == evidence_role)
            ),
            key=lambda artifact: (artifact.created_at, artifact.artifact_id),
        )


class _SlowReadRepository(_MemoryRepository):
    def __init__(self) -> None:
        super().__init__()
        self.active_reads = 0
        self.max_active_reads = 0

    async def list_artifacts(self, *args, **kwargs) -> list[ArtifactEnvelope]:
        self.active_reads += 1
        self.max_active_reads = max(self.max_active_reads, self.active_reads)
        await asyncio.sleep(0.02)
        try:
            return await super().list_artifacts(*args, **kwargs)
        finally:
            self.active_reads -= 1


def _option(
    name: str = "人情世故观察者",
    *,
    content_subject: str = "人与人之间的相处与人情世故",
) -> AccountDirectionOptionDraft:
    return AccountDirectionOptionDraft(
        name=name,
        long_term_content_subject=content_subject,
        rationale="礼品只是业务入口，长期内容应观察人与人如何相处。",
        content_audience_hypothesis="关心关系分寸、礼节与人情判断的人",
        audience_promise="用具体人物与事件讲清关系、分寸与人性",
        account_role="从礼品生意观察人情世界的经营者",
    )


def _draft(
    *options: AccountDirectionOptionDraft,
    revision_reason: str | None = None,
    basis_artifact_ids: tuple[str, ...] = (),
) -> AccountDirectionProposalDraft:
    return AccountDirectionProposalDraft(
        marketing_subject="黄金礼品",
        business_goal="让更多潜在用户先认可账号懂人情与送礼",
        direction_options=options or (_option(),),
        recommended_option_number=1,
        basis_artifact_ids=basis_artifact_ids,
        revision_reason=revision_reason,
    )


async def _propose(
    repository: _MemoryRepository,
    draft: AccountDirectionProposalDraft | None = None,
    *,
    created_at: datetime = NOW,
):
    return await propose_account_direction(
        project=PROJECT,
        logical_account=ACCOUNT,
        repository=repository,
        draft=draft or _draft(),
        source_user_text="我是做黄金礼品的，我要怎么起号？",
        created_at=created_at,
        source_thread_id="thread-1",
        source_run_id="run-1",
    )


@pytest.mark.asyncio
async def test_one_incomplete_direction_can_be_proposed_without_a_map_or_evidence() -> None:
    repository = _MemoryRepository()
    minimal = AccountDirectionOptionDraft(
        name="水果世界讲述者",
        long_term_content_subject="水果及其连接的自然、地域与生活世界",
        rationale="这是当前可用的长期方向，具体受众和形式仍待确认。",
    )

    prepared = await _propose(
        repository,
        AccountDirectionProposalDraft(
            marketing_subject="水果店",
            direction_options=(minimal,),
            recommended_option_number=1,
            unknowns=("目标受众与持续表现形式仍未知",),
        ),
    )

    assert prepared.proposal_artifact.artifact_type == "account_direction_proposal"
    assert prepared.proposal_artifact.version == 1
    assert prepared.proposal_artifact.parents == ()
    assert prepared.proposal.source_user_text == "我是做黄金礼品的，我要怎么起号？"
    assert prepared.proposal.recommended_option_id == "direction_1"
    assert prepared.proposal.direction_options[0].content_audience_hypothesis is None
    assert (
        select_current_account_direction(
            await repository.list_artifacts(PROJECT, logical_account=ACCOUNT),
            logical_account=ACCOUNT,
        )
        is None
    )


@pytest.mark.asyncio
async def test_identical_proposal_replay_reuses_the_content_addressed_artifact() -> None:
    repository = _MemoryRepository()

    first = await _propose(repository)
    replay = await _propose(repository, created_at=NOW + timedelta(seconds=1))

    assert replay.proposal_artifact.artifact_id == first.proposal_artifact.artifact_id
    assert replay.reused is True


@pytest.mark.asyncio
async def test_confirmation_requires_the_exact_latest_proposal_and_option() -> None:
    repository = _MemoryRepository()
    stale = await _propose(repository)
    latest = await _propose(
        repository,
        _draft(_option("礼与关系观察者")),
        created_at=NOW + timedelta(seconds=1),
    )

    with pytest.raises(ValueError, match="latest"):
        await confirm_account_direction(
            project=PROJECT,
            logical_account=ACCOUNT,
            repository=repository,
            proposal_artifact_id=stale.proposal_artifact.artifact_id,
            option_id="direction_1",
            confirmation_user_text="我选择第一个方向",
            created_at=NOW + timedelta(seconds=2),
            source_thread_id="thread-1",
            source_run_id="run-confirm",
        )
    with pytest.raises(ValueError, match="option"):
        await confirm_account_direction(
            project=PROJECT,
            logical_account=ACCOUNT,
            repository=repository,
            proposal_artifact_id=latest.proposal_artifact.artifact_id,
            option_id="direction_9",
            confirmation_user_text="我选择不存在的方向",
            created_at=NOW + timedelta(seconds=2),
            source_thread_id="thread-1",
            source_run_id="run-confirm",
        )


@pytest.mark.asyncio
async def test_confirmation_is_idempotent_and_creates_the_only_effective_direction() -> None:
    repository = _MemoryRepository()
    proposal = await _propose(repository)

    confirmed = await confirm_account_direction(
        project=PROJECT,
        logical_account=ACCOUNT,
        repository=repository,
        proposal_artifact_id=proposal.proposal_artifact.artifact_id,
        option_id="direction_1",
        confirmation_user_text="我选择第一个方向",
        created_at=NOW + timedelta(seconds=1),
        source_thread_id="thread-1",
        source_run_id="run-confirm",
    )
    replay = await confirm_account_direction(
        project=PROJECT,
        logical_account=ACCOUNT,
        repository=repository,
        proposal_artifact_id=proposal.proposal_artifact.artifact_id,
        option_id="direction_1",
        confirmation_user_text="我选择第一个方向",
        created_at=NOW + timedelta(seconds=5),
        source_thread_id="thread-1",
        source_run_id="run-confirm-replay",
    )

    assert confirmed.direction_artifact.artifact_type == "account_direction_version"
    assert confirmed.direction.revision_number == 1
    assert confirmed.direction.selected_option.option_id == "direction_1"
    assert {parent.artifact_id for parent in confirmed.direction_artifact.parents} == {proposal.proposal_artifact.artifact_id}
    assert replay.direction_artifact.artifact_id == confirmed.direction_artifact.artifact_id
    assert replay.reused is True
    selected = select_current_account_direction(
        await repository.list_artifacts(PROJECT, logical_account=ACCOUNT),
        logical_account=ACCOUNT,
    )
    assert selected is not None
    assert selected.direction_artifact.artifact_id == confirmed.direction_artifact.artifact_id


@pytest.mark.asyncio
async def test_current_direction_fails_closed_on_conflicting_artifacts_for_one_revision() -> None:
    repository = _MemoryRepository()
    proposal = await _propose(repository)
    confirmed = await confirm_account_direction(
        project=PROJECT,
        logical_account=ACCOUNT,
        repository=repository,
        proposal_artifact_id=proposal.proposal_artifact.artifact_id,
        option_id="direction_1",
        confirmation_user_text="我选择第一个方向",
        created_at=NOW + timedelta(seconds=1),
        source_thread_id="thread-1",
        source_run_id="run-confirm",
    )
    conflicting_direction = confirmed.direction.model_copy(update={"confirmation_user_text": "另一条冲突确认"})
    conflict = ArtifactEnvelope.seal(
        project=PROJECT,
        logical_account=ACCOUNT,
        artifact_type="account_direction_version",
        version=1,
        payload=conflicting_direction.model_dump(mode="json"),
        parents=confirmed.direction_artifact.parents,
        created_at=NOW + timedelta(seconds=2),
        source_thread_id="thread-1",
        source_run_id="run-conflict",
    )

    with pytest.raises(ValueError, match="conflicting"):
        select_current_account_direction(
            [confirmed.direction_artifact, conflict],
            logical_account=ACCOUNT,
        )


@pytest.mark.asyncio
async def test_conflicting_confirmations_are_serialized_per_proposal() -> None:
    repository = _SlowReadRepository()
    proposal = await _propose(
        repository,
        _draft(
            _option("人情世故观察者"),
            _option("礼与秩序观察者", content_subject="礼、秩序与社会关系"),
        ),
    )
    repository.max_active_reads = 0

    async def confirm(option_id: str):
        return await confirm_account_direction(
            project=PROJECT,
            logical_account=ACCOUNT,
            repository=repository,
            proposal_artifact_id=proposal.proposal_artifact.artifact_id,
            option_id=option_id,
            confirmation_user_text=f"我选择 {option_id}",
            created_at=NOW + timedelta(seconds=1),
            source_thread_id="thread-1",
            source_run_id=f"run-{option_id}",
        )

    results = await asyncio.gather(
        confirm("direction_1"),
        confirm("direction_2"),
        return_exceptions=True,
    )

    assert repository.max_active_reads == 1
    assert sum(not isinstance(result, Exception) for result in results) == 1
    assert sum(isinstance(result, ValueError) for result in results) == 1
    stored_directions = [artifact for artifact in repository.artifacts.values() if artifact.artifact_type == "account_direction_version"]
    assert len(stored_directions) == 1


@pytest.mark.asyncio
async def test_revision_requires_a_reason_and_cannot_store_an_exact_noop() -> None:
    repository = _MemoryRepository()
    proposal = await _propose(repository)
    confirmed = await confirm_account_direction(
        project=PROJECT,
        logical_account=ACCOUNT,
        repository=repository,
        proposal_artifact_id=proposal.proposal_artifact.artifact_id,
        option_id="direction_1",
        confirmation_user_text="我选择第一个方向",
        created_at=NOW + timedelta(seconds=1),
        source_thread_id="thread-1",
        source_run_id="run-confirm",
    )

    with pytest.raises(ValueError, match="revision reason"):
        await _propose(repository, _draft(), created_at=NOW + timedelta(seconds=2))
    with pytest.raises(ValueError, match="unchanged"):
        await _propose(
            repository,
            _draft(revision_reason="用户希望复核方向"),
            created_at=NOW + timedelta(seconds=2),
        )

    revised = await _propose(
        repository,
        _draft(
            _option(
                "礼与社会关系观察者",
                content_subject="礼、秩序及人与人之间的相处",
            ),
            revision_reason="用户希望把礼与社会秩序纳入长期观察",
        ),
        created_at=NOW + timedelta(seconds=3),
    )
    assert revised.proposal.target_revision_number == 2
    assert confirmed.direction_artifact.artifact_id in {parent.artifact_id for parent in revised.proposal_artifact.parents}


@pytest.mark.asyncio
async def test_basis_artifacts_cannot_cross_logical_accounts() -> None:
    foreign = ArtifactEnvelope.seal(
        project=PROJECT,
        logical_account=OTHER_ACCOUNT,
        artifact_type="benchmark_snapshot",
        version=1,
        payload={"label": "foreign"},
        created_at=NOW,
        source_thread_id="thread-2",
        source_run_id="run-2",
    )
    repository = _MemoryRepository((foreign,))

    with pytest.raises(ValueError, match="basis"):
        await _propose(
            repository,
            _draft(basis_artifact_ids=(foreign.artifact_id,)),
        )
