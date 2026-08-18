from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from deerflow.incubation import ArtifactEnvelope, ProjectRef
from deerflow.incubation.account_strategy import (
    confirm_account_strategy,
    select_current_account_strategy,
)
from deerflow.incubation.account_strategy_presentation import render_account_strategy
from deerflow.incubation.brief_runtime import build_minimal_incubation_brief
from deerflow.incubation.judgment import (
    AccountPresentationPlan,
    AccountRouteOption,
    AudienceHypothesis,
    IncubationJudgment,
    MonetizationHypothesis,
    PersonaDecision,
    PositioningDecision,
    seal_incubation_judgment,
)

NOW = datetime(2026, 8, 18, 10, 0, tzinfo=UTC)
PROJECT = ProjectRef(owner_user_id="user-1", project_id="gift-project")


class _MemoryRepository:
    def __init__(self, artifacts: tuple[ArtifactEnvelope, ...]) -> None:
        self.artifacts = {artifact.artifact_id: artifact for artifact in artifacts}

    async def put_artifact(self, artifact: ArtifactEnvelope) -> ArtifactEnvelope:
        self.artifacts[artifact.artifact_id] = artifact
        return artifact

    async def list_artifacts(
        self,
        project: ProjectRef,
        *,
        artifact_type: str | None = None,
        evidence_role: str | None = None,
    ) -> list[ArtifactEnvelope]:
        return [artifact for artifact in self.artifacts.values() if artifact.project == project and (artifact_type is None or artifact.artifact_type == artifact_type) and (evidence_role is None or artifact.evidence_role == evidence_role)]


def _positioning(label: str, *, basis_ids: tuple[str, ...]) -> PositioningDecision:
    return PositioningDecision(
        decision=f"{label}账号",
        audience_promise=f"长期用{label}理解人与人如何相处。",
        rationale=f"{label}与当前内容世界相符。",
        basis_artifact_ids=basis_ids,
    )


def _audience(label: str, *, basis_ids: tuple[str, ...]) -> AudienceHypothesis:
    return AudienceHypothesis(
        people=f"愿意看{label}的人",
        recurring_interest="人情、礼节和关系判断",
        why_return="每次都能带走一个具体判断。",
        rationale="这是待真实反馈校正的受众假设。",
        basis_artifact_ids=basis_ids,
    )


def _persona(label: str, *, basis_ids: tuple[str, ...]) -> PersonaDecision:
    return PersonaDecision(
        account_role=f"用{label}观察人情世界的礼品从业者",
        trust_basis=("用户自述经营黄金礼品。",),
        boundaries=("不冒充历史学者。",),
        rationale="保留真实从业位置。",
        basis_artifact_ids=basis_ids,
    )


def _presentation(form: str, *, basis_ids: tuple[str, ...]) -> AccountPresentationPlan:
    return AccountPresentationPlan(
        primary_forms=(form,),
        rationale=f"{form}是这条路线的长期表现形式。",
        basis_artifact_ids=basis_ids,
    )


def _monetization(label: str, *, basis_ids: tuple[str, ...]) -> tuple[MonetizationHypothesis, ...]:
    return (
        MonetizationHypothesis(
            path=f"先通过{label}建立信任，再承接礼品需求。",
            trust_required="观众相信账号懂人情与礼节。",
            rationale="只是待验证的变现假设。",
            basis_artifact_ids=basis_ids,
        ),
    )


def _route(
    option_id: str,
    label: str,
    form: str,
    *,
    basis_ids: tuple[str, ...],
) -> AccountRouteOption:
    return AccountRouteOption(
        option_id=option_id,
        name=label,
        positioning=_positioning(label, basis_ids=basis_ids),
        audience=_audience(label, basis_ids=basis_ids),
        persona=_persona(label, basis_ids=basis_ids),
        presentation=_presentation(form, basis_ids=basis_ids),
        monetization=_monetization(label, basis_ids=basis_ids),
        business_connection="用户的礼品从业位置提供观察角度，业务只在需要时承接。",
        recommendation_rationale=f"{label}与当前已知业务和资源更匹配。",
        resource_requirements=(f"持续生产{form}所需的基础素材",),
        tradeoffs=(f"{form}的制作成本需要后续确认。",),
    )


def _parents() -> tuple[ArtifactEnvelope, ArtifactEnvelope]:
    brief = build_minimal_incubation_brief(
        project=PROJECT,
        verbatim_user_request="我是做黄金礼品的，我要怎么起号？",
        source_object="黄金礼品",
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-1",
    )
    world = ArtifactEnvelope.seal(
        project=PROJECT,
        artifact_type="content_map_candidate",
        version=1,
        payload={
            "content_map_version_id": "map-relations-v1",
            "content_root": "人与人如何相处",
            "editorial_promise": "借具体人物和事件理解人情与礼。",
            "recurring_lens": "从时间、地方、人物和事件展开。",
            "drift_boundaries": ["不退回黄金产品目录。"],
            "dimensions": [],
        },
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-1",
    )
    return brief, world


def _proposal() -> tuple[ArtifactEnvelope, ArtifactEnvelope, ArtifactEnvelope]:
    brief, world = _parents()
    basis_ids = (brief.artifact_id, world.artifact_id)
    routes = (
        _route("route_a", "真人故事", "真人出镜口述", basis_ids=basis_ids),
        _route("route_b", "AI情景叙事", "AI情景剧", basis_ids=basis_ids),
    )
    proposal = IncubationJudgment(
        decision_status="proposed",
        content_map_version_id="map-relations-v1",
        route_options=routes,
        recommended_option_id="route_a",
        positioning=routes[0].positioning,
        audience=routes[0].audience,
        persona=routes[0].persona,
        presentation=routes[0].presentation,
        monetization=routes[0].monetization,
        unknowns=("尚未确认用户是否愿意出镜。",),
    )
    artifact = seal_incubation_judgment(
        project=PROJECT,
        judgment=proposal,
        brief_artifact=brief,
        content_world_artifact=world,
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-1",
    )
    return brief, world, artifact


def test_new_account_strategy_proposal_requires_multiple_distinct_routes() -> None:
    brief, world = _parents()
    basis_ids = (brief.artifact_id, world.artifact_id)
    route = _route("route_a", "真人故事", "真人出镜口述", basis_ids=basis_ids)

    with pytest.raises(ValidationError, match="route_options"):
        IncubationJudgment(
            decision_status="proposed",
            content_map_version_id="map-relations-v1",
            route_options=(route,),
            recommended_option_id="route_a",
        )


def test_recommendation_is_not_treated_as_user_confirmation() -> None:
    _, _, proposal = _proposal()
    judgment = IncubationJudgment.model_validate(proposal.payload)

    assert judgment.decision_status == "proposed"
    assert judgment.recommended_option_id == "route_a"
    assert judgment.selected_option_id is None
    assert (
        select_current_account_strategy(
            [proposal],
            content_map_version_id="map-relations-v1",
            require_confirmed=True,
        )
        is None
    )


def test_account_strategy_proposal_renders_each_route_and_waits_for_the_user() -> None:
    _, _, proposal = _proposal()

    rendered = render_account_strategy(IncubationJudgment.model_validate(proposal.payload))

    assert rendered.startswith("# 账号路线候选")
    assert "## 1. 真人故事（推荐）" in rendered
    assert "## 2. AI情景叙事" in rendered
    assert "**主要表现形式：** 真人出镜口述" in rendered
    assert "**主要表现形式：** AI情景剧" in rendered
    assert "**与业务如何连接：** 用户的礼品从业位置提供观察角度" in rendered
    assert "推荐只是建议，在你确认之前不会进入下一步" in rendered


@pytest.mark.asyncio
async def test_user_can_confirm_a_non_recommended_route_without_a_platform_account() -> None:
    brief, world, proposal = _proposal()
    repository = _MemoryRepository((brief, world, proposal))

    confirmed = await confirm_account_strategy(
        project=PROJECT,
        repository=repository,
        option_id="route_b",
        created_at=NOW,
        source_thread_id="thread-2",
        source_run_id="run-2",
    )

    assert confirmed.judgment.decision_status == "confirmed"
    assert confirmed.judgment.selected_option_id == "route_b"
    assert confirmed.judgment.recommended_option_id == "route_a"
    assert confirmed.judgment.positioning.decision == "AI情景叙事账号"
    assert confirmed.judgment.presentation.primary_forms == ("AI情景剧",)
    assert confirmed.judgment_artifact.account is None
    assert confirmed.judgment_artifact.version == 2
    assert proposal.to_parent_ref() in confirmed.judgment_artifact.parents


@pytest.mark.asyncio
async def test_account_strategy_confirmation_rejects_an_unknown_route() -> None:
    brief, world, proposal = _proposal()
    repository = _MemoryRepository((brief, world, proposal))

    with pytest.raises(ValueError, match="unknown account route option"):
        await confirm_account_strategy(
            project=PROJECT,
            repository=repository,
            option_id="route_missing",
            created_at=NOW,
            source_thread_id="thread-2",
            source_run_id="run-2",
        )


@pytest.mark.asyncio
async def test_replaying_the_same_confirmation_reuses_the_confirmed_revision() -> None:
    brief, world, proposal = _proposal()
    repository = _MemoryRepository((brief, world, proposal))

    first = await confirm_account_strategy(
        project=PROJECT,
        repository=repository,
        option_id="route_a",
        created_at=NOW,
        source_thread_id="thread-2",
        source_run_id="run-2",
    )
    repeated = await confirm_account_strategy(
        project=PROJECT,
        repository=repository,
        option_id="route_a",
        created_at=NOW,
        source_thread_id="thread-3",
        source_run_id="run-3",
    )

    assert repeated.reused is True
    assert repeated.judgment_artifact.artifact_id == first.judgment_artifact.artifact_id
    assert repeated.judgment.revision_number == 2
    assert sum(artifact.artifact_type == "incubation_judgment" for artifact in repository.artifacts.values()) == 2
