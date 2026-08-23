from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from deerflow.incubation import ArtifactEnvelope, LogicalAccountRef, ProjectRef
from deerflow.incubation.account_direction import (
    AccountDirectionOption,
    AccountDirectionProposal,
    AccountDirectionVersion,
)
from deerflow.incubation.account_launch_plan import (
    account_launch_plan_confirmation_text,
    confirm_account_launch_plan,
    prepare_account_launch_plan,
    select_current_account_launch_plan,
)
from deerflow.incubation.account_launch_plan_presentation import render_account_launch_plan
from deerflow.incubation.judgment import (
    AccountPresentationPlan,
    AccountRouteOption,
    AudienceHypothesis,
    IncubationJudgment,
    PersonaDecision,
    PositioningDecision,
)
from deerflow.incubation.launch_plan import (
    AccountLaunchPlan,
    FirstWeekDay,
    LaunchCapacity,
    LaunchCheckpoint,
    LaunchPhase,
    LaunchSeries,
    PlannedTopicSeed,
    seal_account_launch_plan,
)

NOW = datetime(2026, 8, 21, 12, 0, tzinfo=UTC)
PROJECT = ProjectRef(owner_user_id="user-1", project_id="golden-gift")
LOGICAL_ACCOUNT = LogicalAccountRef(
    owner_user_id="user-1",
    project_id="golden-gift",
    logical_account_id="account-golden-gift",
)
SECOND_LOGICAL_ACCOUNT = LogicalAccountRef(
    owner_user_id="user-1",
    project_id="golden-gift",
    logical_account_id="account-seafood",
)


class _MemoryRepository:
    def __init__(self, artifacts: tuple[ArtifactEnvelope, ...] = ()) -> None:
        self.artifacts = {artifact.artifact_id: artifact for artifact in artifacts}

    async def put_artifact(self, artifact: ArtifactEnvelope) -> ArtifactEnvelope:
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
        return [
            artifact
            for artifact in self.artifacts.values()
            if artifact.project == project
            and (logical_account is None or artifact.logical_account == logical_account)
            and (artifact_type is None or artifact.artifact_type == artifact_type)
            and (evidence_role is None or artifact.evidence_role == evidence_role)
        ]


def _map_artifact(
    *,
    logical_account: LogicalAccountRef = LOGICAL_ACCOUNT,
    direction_artifact: ArtifactEnvelope | None = None,
) -> ArtifactEnvelope:
    return ArtifactEnvelope.seal(
        project=PROJECT,
        artifact_type="content_map_candidate",
        version=1,
        payload={
            "content_map_version_id": "content-map-relations-v1",
            "content_root": "人与人之间的相处与人情世故",
            "editorial_promise": "借具体人物与事件理解关系、分寸与秩序。",
            "recurring_lens": "从人物、时间、地方和事件观察人与人如何相处。",
            "drift_boundaries": ["不退回黄金产品目录。"],
            "dimensions": [
                {
                    "name": "人物与公共事件",
                    "rationale": "用具体行动观察关系如何形成。",
                    "paths": [
                        {
                            "path_id": "path-public-gift",
                            "steps": [
                                {
                                    "from_label": "人与人之间的相处与人情世故",
                                    "relation": "在公共交往中通过赠与表达关系",
                                    "to_label": "国与国如何借礼物表达态度",
                                    "basis_refs": [],
                                    "status": "candidate",
                                    "verification_needed": True,
                                }
                            ],
                            "rationale": "可从已取证的公共赠与事件进入人情判断。",
                        },
                        {
                            "path_id": "path-workplace-relations",
                            "steps": [
                                {
                                    "from_label": "人与人之间的相处与人情世故",
                                    "relation": "在组织中通过行动表达分寸",
                                    "to_label": "职场关系中的人情判断",
                                    "basis_refs": [],
                                    "status": "candidate",
                                    "verification_needed": True,
                                }
                            ],
                            "rationale": "可用用户亲历或明确虚构情景呈现。",
                        },
                    ],
                }
            ],
        },
        logical_account=logical_account,
        parents=((direction_artifact.to_parent_ref(),) if direction_artifact is not None else ()),
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-1",
    )


def _route(option_id: str, name: str) -> AccountRouteOption:
    common = {"rationale": "来自当前候选地图。", "confidence": "low"}
    return AccountRouteOption(
        option_id=option_id,
        name=name,
        positioning=PositioningDecision(
            decision="从具体事件观察人与人如何相处",
            audience_promise="每次借一个具体人物或事件讲清一个人情判断。",
            **common,
        ),
        audience=AudienceHypothesis(
            people="关心关系、礼节和处世分寸的人",
            recurring_interest="真实事件中的人情判断",
            why_return="持续获得可讨论的具体判断。",
            **common,
        ),
        persona=PersonaDecision(
            account_role="从礼品生意出发观察人情世界的从业者",
            **common,
        ),
        presentation=AccountPresentationPlan(
            primary_forms=("真人口述与公开素材叙事",),
            **common,
        ),
        business_connection="礼品业务提供观察入口，内容不围着产品目录展开。",
        recommendation_rationale="最贴合已确认内容世界。",
    )


def _strategy_artifact(
    *,
    confirmed: bool = True,
    logical_account: LogicalAccountRef = LOGICAL_ACCOUNT,
) -> ArtifactEnvelope:
    world = _map_artifact(logical_account=logical_account)
    if confirmed:
        judgment = IncubationJudgment(
            content_map_version_id="content-map-relations-v1",
            positioning=_route("route_a", "事件观察").positioning,
            audience=_route("route_a", "事件观察").audience,
            persona=_route("route_a", "事件观察").persona,
            presentation=_route("route_a", "事件观察").presentation,
        )
    else:
        routes = (_route("route_a", "事件观察"), _route("route_b", "情景故事"))
        judgment = IncubationJudgment(
            content_map_version_id="content-map-relations-v1",
            decision_status="proposed",
            route_options=routes,
            recommended_option_id="route_a",
            positioning=routes[0].positioning,
            audience=routes[0].audience,
            persona=routes[0].persona,
            presentation=routes[0].presentation,
        )
    return ArtifactEnvelope.seal(
        project=PROJECT,
        artifact_type="incubation_judgment",
        version=1,
        payload=judgment.model_dump(mode="json"),
        logical_account=logical_account,
        parents=(world.to_parent_ref(),),
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-1",
    )


def _direction_lineage(
    *,
    content_root: str | None = "人与人之间的相处与人情世故",
    logical_account: LogicalAccountRef = LOGICAL_ACCOUNT,
) -> tuple[ArtifactEnvelope, ArtifactEnvelope]:
    option = AccountDirectionOption(
        option_id="direction_1",
        name="从礼赠观察关系",
        content_root=content_root,
        long_term_content_subject="人与人之间的相处与人情世故：从具体人物、事件和生活选择观察关系。",
        rationale="业务提供观察入口，内容根保持在人与人的关系。",
        content_audience_hypothesis="关心关系、礼节和处世分寸的人。",
        audience_promise="每次讲清一个具体的人情判断。",
        account_role="从礼赠行业出发观察关系的人。",
        presentation_directions=("真人口述与公开素材叙事",),
        business_connection="用户理解关系后，在礼赠需求出现时能自然回到业务。",
    )
    proposal = AccountDirectionProposal(
        target_revision_number=1,
        source_user_text="我们做黄金礼赠，想从人与人的关系切入长期内容。",
        marketing_subject="黄金礼赠业务",
        business_goal="通过长期内容建立信任。",
        direction_options=(option,),
        recommended_option_id=option.option_id,
    )
    proposal_artifact = ArtifactEnvelope.seal(
        project=PROJECT,
        artifact_type="account_direction_proposal",
        version=1,
        payload=proposal.model_dump(mode="json"),
        logical_account=logical_account,
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-direction-proposal",
    )
    direction = AccountDirectionVersion(
        revision_number=1,
        proposal_artifact_id=proposal_artifact.artifact_id,
        source_user_text="我们做黄金礼赠，想从人与人的关系切入长期内容。",
        confirmation_user_text="确认第一个方向。",
        marketing_subject="黄金礼赠业务",
        business_goal="通过长期内容建立信任。",
        selected_option=option,
    )
    direction_artifact = ArtifactEnvelope.seal(
        project=PROJECT,
        artifact_type="account_direction_version",
        version=1,
        payload=direction.model_dump(mode="json"),
        logical_account=logical_account,
        parents=(proposal_artifact.to_parent_ref(),),
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-direction",
    )
    return proposal_artifact, direction_artifact


def _plan(*, strategy_artifact_id: str, status: str = "proposed") -> AccountLaunchPlan:
    topics = (
        PlannedTopicSeed(
            seed_id="seed-evan-kail",
            series_id="series-public-gifts",
            map_path_id="path-public-gift",
            content_role="trust",
            focal_subject="埃文·凯尔捐赠相册事件",
            concrete_event_or_question="一份跨国赠与为什么会改变两个人群对彼此的理解？",
            account_viewpoint="礼物的分量常来自对关系和归属的理解，而不只来自价格。",
            source_kind="public_evidence",
            evidence_need="执行前核验人物、时间、捐赠与回赠的公开来源。",
            presentation_hint="公开素材叙事",
        ),
        PlannedTopicSeed(
            seed_id="seed-workplace-gift",
            series_id="series-everyday-relations",
            map_path_id="path-workplace-relations",
            content_role="understanding",
            focal_subject="职场中两种不同送礼选择",
            concrete_event_or_question="为什么礼物更贵的人反而可能把关系送远？",
            account_viewpoint="送礼的关键不是价格，而是是否理解关系、边界和对方处境。",
            source_kind="creative_hypothesis",
            evidence_need="只能明确标为虚构情景，不能冒充真实客户案例。",
            presentation_hint="情景故事",
        ),
    )
    first_week = tuple(
        FirstWeekDay(
            day=day,
            focus=("核验首个公共事件" if day == 1 else f"完成第 {day} 天运营动作"),
            actions=(("研究并封存证据",) if day == 1 else ("按当前产能推进一项内容动作",)),
            topic_seed_ids=(("seed-evan-kail",) if day in {1, 2, 3} else ()),
            publish=(day == 3),
            observation_questions=(("观众能否复述账号在讲人情而不是黄金？",) if day == 7 else ()),
        )
        for day in range(1, 8)
    )
    return AccountLaunchPlan(
        revision_number=1,
        decision_status=status,
        strategy_artifact_id=strategy_artifact_id,
        content_map_version_id="content-map-relations-v1",
        planning_request="给我一个7天和30天起号计划",
        capacity=LaunchCapacity(
            status="provisional",
            cadence_summary="第一周先完成一次完整发布，其余频率在验证制作耗时后调整。",
            planned_publish_days=(3, 10, 17, 24),
            basis="用户尚未说明每周可投入时间，因此只是可修改安排。",
            production_assumptions=("首轮以真人口述和公开素材叙事二选一完成。",),
            adjustment_trigger="实际制作耗时或素材条件不支持时立即降低频率。",
        ),
        series=(
            LaunchSeries(
                series_id="series-public-gifts",
                name="一份礼物如何改变关系",
                purpose="借已取证公共事件建立账号的人情观察能力。",
                map_path_ids=("path-public-gift",),
                repeatable_question="这份赠与发生在谁与谁之间，它真正改变了什么？",
                topic_sources=("公开历史与当代事件",),
            ),
            LaunchSeries(
                series_id="series-everyday-relations",
                name="关系里的分寸",
                purpose="用明确虚构或用户确认的日常情景表达判断。",
                map_path_ids=("path-workplace-relations",),
                repeatable_question="当事人想达到什么，哪一步让关系发生变化？",
                topic_sources=("用户亲历", "明确标注的创意情景"),
            ),
        ),
        topic_seeds=topics,
        first_week=first_week,
        later_phases=(
            LaunchPhase(
                start_day=8,
                end_day=14,
                objective="根据第一周反馈修改栏目和表现形式。",
                series_ids=("series-public-gifts", "series-everyday-relations"),
                topic_seed_ids=("seed-workplace-gift",),
                actions=("执行一个新的已取证题眼。",),
                review_questions=("哪种栏目让观众正确理解账号承诺？",),
            ),
            LaunchPhase(
                start_day=15,
                end_day=30,
                objective="形成可以继续滚动的第一版栏目组合。",
                series_ids=("series-public-gifts", "series-everyday-relations"),
                topic_seed_ids=(),
                actions=("从地图、用户案例、公开事件和历史反馈补充题眼。",),
                review_questions=("哪些机制重复有效，哪些仍只是单条猜测？",),
            ),
        ),
        checkpoints=(
            LaunchCheckpoint(
                day=7,
                questions=("什么真的拍得出来？", "观众是否正确理解账号？"),
                possible_adjustments=("保留", "修改", "暂停", "扩展"),
            ),
            LaunchCheckpoint(
                day=30,
                questions=("哪些栏目形成了可重复机制？", "下一版计划应改什么？"),
                possible_adjustments=("保留", "修改", "暂停", "扩展"),
            ),
        ),
        unknowns=("用户真实周产能未知。",),
    )


def _draft_payload(*, planning_request: str = "给我一个7天和30天起号计划") -> dict[str, object]:
    plan = _plan(strategy_artifact_id="server-owned-placeholder")
    payload = plan.model_dump(mode="json")
    payload["planning_request"] = planning_request
    for field in (
        "revision_number",
        "supersedes_plan_artifact_id",
        "revision_reason",
        "decision_status",
        "confirmation_user_text",
        "strategy_artifact_id",
        "direction_artifact_id",
        "content_map_version_id",
        "horizon_days",
        "first_sprint_days",
    ):
        payload.pop(field)
    return payload


def test_launch_plan_allows_non_publish_days_but_requires_full_time_coverage() -> None:
    plan = _plan(strategy_artifact_id="strategy-1")

    assert [day.day for day in plan.first_week] == list(range(1, 8))
    assert [day.day for day in plan.first_week if day.publish] == [3]
    assert [(phase.start_day, phase.end_day) for phase in plan.later_phases] == [(8, 14), (15, 30)]
    assert {checkpoint.day for checkpoint in plan.checkpoints} >= {7, 30}

    with pytest.raises(ValidationError, match="at least 7"):
        _plan(strategy_artifact_id="strategy-1").model_copy(update={"first_week": plan.first_week[:-1]}).__class__.model_validate(
            {**plan.model_dump(mode="json"), "first_week": [item.model_dump(mode="json") for item in plan.first_week[:-1]]}
        )


def test_launch_plan_rejects_unknown_series_and_topic_references() -> None:
    plan = _plan(strategy_artifact_id="strategy-1")
    broken_seed = plan.topic_seeds[0].model_copy(update={"series_id": "missing-series"})

    with pytest.raises(ValidationError, match="unknown series"):
        AccountLaunchPlan.model_validate(
            {
                **plan.model_dump(mode="json"),
                "topic_seeds": [broken_seed.model_dump(mode="json"), plan.topic_seeds[1].model_dump(mode="json")],
            }
        )


def test_confirmed_launch_plan_requires_a_versioned_confirmation_receipt() -> None:
    proposed = _plan(strategy_artifact_id="strategy-1")
    payload = {
        **proposed.model_dump(mode="json"),
        "revision_number": 2,
        "supersedes_plan_artifact_id": "plan-proposal-1",
        "revision_reason": "用户确认。",
        "decision_status": "confirmed",
    }

    with pytest.raises(ValidationError, match="confirmation text"):
        AccountLaunchPlan.model_validate(payload)

    payload["revision_number"] = 1
    payload["supersedes_plan_artifact_id"] = None
    payload["revision_reason"] = None
    payload["confirmation_user_text"] = account_launch_plan_confirmation_text("plan-proposal-1")
    with pytest.raises(ValidationError, match="revision 2"):
        AccountLaunchPlan.model_validate(payload)


def test_launch_plan_projection_exposes_exact_seed_and_confirmation_receipts() -> None:
    proposal = _plan(strategy_artifact_id="strategy-1")
    proposal_id = "artifact_plan_proposal"

    rendered = render_account_launch_plan(proposal, artifact_id=proposal_id)

    assert f"计划提案编号：** `{proposal_id}`" in rendered
    assert f"`{account_launch_plan_confirmation_text(proposal_id)}`" in rendered
    assert "`seed-evan-kail`" in rendered
    assert "来源：public_evidence" in rendered
    assert "执行前取证" in rendered

    confirmed = AccountLaunchPlan.model_validate(
        {
            **proposal.model_dump(mode="json"),
            "revision_number": 2,
            "supersedes_plan_artifact_id": proposal_id,
            "revision_reason": "用户以精确口令确认。",
            "decision_status": "confirmed",
            "confirmation_user_text": account_launch_plan_confirmation_text(proposal_id),
        }
    )
    confirmed_rendered = render_account_launch_plan(
        confirmed,
        artifact_id="artifact_plan_confirmed",
    )
    assert "已确认回执编号：** `artifact_plan_confirmed`" in confirmed_rendered
    assert "计划提案编号：** `artifact_plan_confirmed`" not in confirmed_rendered


def test_launch_plan_seal_binds_confirmed_strategy_and_real_map_paths() -> None:
    world = _map_artifact()
    strategy = _strategy_artifact()
    plan = _plan(strategy_artifact_id=strategy.artifact_id)

    artifact = seal_account_launch_plan(
        project=PROJECT,
        logical_account=LOGICAL_ACCOUNT,
        plan=plan,
        strategy_artifact=strategy,
        content_world_artifact=world,
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-2",
    )

    assert artifact.artifact_type == "account_launch_plan"
    assert artifact.logical_account == LOGICAL_ACCOUNT
    assert set(artifact.parents) == {strategy.to_parent_ref(), world.to_parent_ref()}

    broken_series = plan.series[0].model_copy(update={"map_path_ids": ("invented-path",)})
    broken_seed = plan.topic_seeds[0].model_copy(update={"map_path_id": "invented-path"})
    broken_plan = AccountLaunchPlan.model_validate(
        {
            **plan.model_dump(mode="json"),
            "series": [broken_series.model_dump(mode="json"), plan.series[1].model_dump(mode="json")],
            "topic_seeds": [broken_seed.model_dump(mode="json"), plan.topic_seeds[1].model_dump(mode="json")],
        }
    )
    with pytest.raises(ValueError, match="candidate map path"):
        seal_account_launch_plan(
            project=PROJECT,
            logical_account=LOGICAL_ACCOUNT,
            plan=broken_plan,
            strategy_artifact=strategy,
            content_world_artifact=world,
            created_at=NOW,
            source_thread_id="thread-1",
            source_run_id="run-2",
        )


def test_direction_launch_plan_seal_rejects_same_root_map_without_exact_link() -> None:
    direction_proposal, direction = _direction_lineage()
    world = _map_artifact()
    plan = AccountLaunchPlan.model_validate(
        {
            **_plan(strategy_artifact_id="placeholder").model_dump(mode="json"),
            "strategy_artifact_id": None,
            "direction_artifact_id": direction.artifact_id,
        }
    )

    with pytest.raises(ValueError, match="exact account direction proposal basis"):
        seal_account_launch_plan(
            project=PROJECT,
            logical_account=LOGICAL_ACCOUNT,
            plan=plan,
            direction_artifact=direction,
            direction_proposal_artifact=direction_proposal,
            content_world_artifact=world,
            created_at=NOW,
            source_thread_id="thread-1",
            source_run_id="run-2",
        )


@pytest.mark.asyncio
async def test_prepare_launch_plan_requires_confirmed_strategy_and_keeps_request_verbatim() -> None:
    world = _map_artifact()
    proposal = _strategy_artifact(confirmed=False)
    repository = _MemoryRepository((world, proposal))

    async def should_not_run(schema, messages):
        raise AssertionError("model must not run before route confirmation")

    with pytest.raises(ValueError, match="confirmed account strategy"):
        await prepare_account_launch_plan(
            project=PROJECT,
            logical_account=LOGICAL_ACCOUNT,
            repository=repository,
            planning_request="给我做7天和30天起号计划",
            structured_model=should_not_run,
            created_at=NOW,
            source_thread_id="thread-1",
            source_run_id="run-2",
        )

    strategy = _strategy_artifact()
    repository = _MemoryRepository((world, strategy))
    seen_input: dict[str, object] = {}

    async def structured_model(schema, messages):
        nonlocal seen_input
        seen_input = json.loads(messages[1].content)
        return _draft_payload(planning_request="给我做7天和30天起号计划")

    prepared = await prepare_account_launch_plan(
        project=PROJECT,
        logical_account=LOGICAL_ACCOUNT,
        repository=repository,
        planning_request="给我做7天和30天起号计划",
        structured_model=structured_model,
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-2",
    )

    assert seen_input["planning_request"] == "给我做7天和30天起号计划"
    assert seen_input["allowed_content_map_path_ids"] == ["path-public-gift", "path-workplace-relations"]
    assert prepared.plan.decision_status == "proposed"
    assert prepared.plan.strategy_artifact_id == strategy.artifact_id
    assert prepared.plan_artifact.artifact_id in repository.artifacts


@pytest.mark.asyncio
async def test_prepare_and_confirm_launch_plan_use_current_account_direction_bridge() -> None:
    direction_proposal, direction = _direction_lineage()
    world = _map_artifact(direction_artifact=direction)
    repository = _MemoryRepository((world, direction_proposal, direction))
    seen_input: dict[str, object] = {}

    async def structured_model(schema, messages):
        nonlocal seen_input
        seen_input = json.loads(messages[1].content)
        return _draft_payload(planning_request="按确认方向编排首轮起号计划")

    prepared = await prepare_account_launch_plan(
        project=PROJECT,
        logical_account=LOGICAL_ACCOUNT,
        repository=repository,
        planning_request="按确认方向编排首轮起号计划",
        content_map_artifact_id=world.artifact_id,
        structured_model=structured_model,
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-launch",
    )

    assert prepared.plan.direction_artifact_id == direction.artifact_id
    assert prepared.plan.strategy_artifact_id is None
    assert seen_input["confirmed_account_direction"]["artifact_id"] == direction.artifact_id
    assert direction.to_parent_ref() in prepared.plan_artifact.parents

    confirmed = await confirm_account_launch_plan(
        project=PROJECT,
        logical_account=LOGICAL_ACCOUNT,
        repository=repository,
        plan_artifact_id=prepared.plan_artifact.artifact_id,
        confirmation_user_text=account_launch_plan_confirmation_text(prepared.plan_artifact.artifact_id),
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-confirm",
    )

    assert confirmed.plan.decision_status == "confirmed"
    assert confirmed.plan.direction_artifact_id == direction.artifact_id
    assert direction.to_parent_ref() in confirmed.plan_artifact.parents


@pytest.mark.asyncio
async def test_direction_launch_bridge_requires_the_exact_direction_proposal_parent() -> None:
    _, direction = _direction_lineage()
    world = _map_artifact(direction_artifact=direction)
    repository = _MemoryRepository((world, direction))

    async def should_not_run(schema, messages):
        raise AssertionError("model must not run for an orphaned confirmed direction")

    with pytest.raises(ValueError, match="exact account direction proposal"):
        await prepare_account_launch_plan(
            project=PROJECT,
            logical_account=LOGICAL_ACCOUNT,
            repository=repository,
            planning_request="编排起号计划",
            content_map_artifact_id=world.artifact_id,
            structured_model=should_not_run,
            created_at=NOW,
            source_thread_id="thread-1",
            source_run_id="run-launch",
        )


@pytest.mark.asyncio
async def test_direction_launch_bridge_uses_the_shared_derived_content_root() -> None:
    direction_proposal, direction = _direction_lineage(content_root=None)
    world = _map_artifact(direction_artifact=direction)
    repository = _MemoryRepository((world, direction_proposal, direction))

    async def structured_model(schema, messages):
        return _draft_payload(planning_request="沿推导后的内容根编排起号计划")

    prepared = await prepare_account_launch_plan(
        project=PROJECT,
        logical_account=LOGICAL_ACCOUNT,
        repository=repository,
        planning_request="沿推导后的内容根编排起号计划",
        content_map_artifact_id=world.artifact_id,
        structured_model=structured_model,
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-launch",
    )

    assert prepared.plan.direction_artifact_id == direction.artifact_id


@pytest.mark.asyncio
async def test_direction_launch_bridge_rejects_a_map_from_another_content_root() -> None:
    direction_proposal, direction = _direction_lineage(content_root="黄金产品知识")
    world = _map_artifact(direction_artifact=direction)
    repository = _MemoryRepository((world, direction_proposal, direction))

    async def should_not_run(schema, messages):
        raise AssertionError("model must not run for a mismatched direction and map")

    with pytest.raises(ValueError, match="content root"):
        await prepare_account_launch_plan(
            project=PROJECT,
            logical_account=LOGICAL_ACCOUNT,
            repository=repository,
            planning_request="编排起号计划",
            content_map_artifact_id=world.artifact_id,
            structured_model=should_not_run,
            created_at=NOW,
            source_thread_id="thread-1",
            source_run_id="run-launch",
        )


@pytest.mark.asyncio
async def test_direction_launch_bridge_requires_an_exact_map_when_multiple_are_linked() -> None:
    direction_proposal, direction = _direction_lineage()
    first_world = _map_artifact(direction_artifact=direction)
    second_world = ArtifactEnvelope.seal(
        project=PROJECT,
        artifact_type="content_map_candidate",
        version=2,
        payload={
            **first_world.payload,
            "content_map_version_id": "content-map-relations-v2",
        },
        logical_account=LOGICAL_ACCOUNT,
        parents=(direction.to_parent_ref(),),
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-map-v2",
    )
    repository = _MemoryRepository((direction_proposal, direction, first_world, second_world))

    async def should_not_run(schema, messages):
        raise AssertionError("model must wait for an exact map receipt")

    with pytest.raises(ValueError, match="exact content map artifact id"):
        await prepare_account_launch_plan(
            project=PROJECT,
            logical_account=LOGICAL_ACCOUNT,
            repository=repository,
            planning_request="编排起号计划",
            structured_model=should_not_run,
            created_at=NOW,
            source_thread_id="thread-1",
            source_run_id="run-launch",
        )


@pytest.mark.asyncio
async def test_confirm_launch_plan_versions_the_exact_proposal_and_is_idempotent() -> None:
    world = _map_artifact()
    strategy = _strategy_artifact()
    proposal = seal_account_launch_plan(
        project=PROJECT,
        logical_account=LOGICAL_ACCOUNT,
        plan=_plan(strategy_artifact_id=strategy.artifact_id),
        strategy_artifact=strategy,
        content_world_artifact=world,
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-2",
    )
    repository = _MemoryRepository((world, strategy, proposal))

    with pytest.raises(ValueError, match="exact confirmation command"):
        await confirm_account_launch_plan(
            project=PROJECT,
            logical_account=LOGICAL_ACCOUNT,
            repository=repository,
            plan_artifact_id=proposal.artifact_id,
            confirmation_user_text="确认采用这版起号计划。",
            created_at=NOW,
            source_thread_id="thread-1",
            source_run_id="run-rejected",
        )

    confirmation_text = account_launch_plan_confirmation_text(proposal.artifact_id)
    confirmed = await confirm_account_launch_plan(
        project=PROJECT,
        logical_account=LOGICAL_ACCOUNT,
        repository=repository,
        plan_artifact_id=proposal.artifact_id,
        confirmation_user_text=confirmation_text,
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-3",
    )
    repeated = await confirm_account_launch_plan(
        project=PROJECT,
        logical_account=LOGICAL_ACCOUNT,
        repository=repository,
        plan_artifact_id=proposal.artifact_id,
        confirmation_user_text=confirmation_text,
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-4",
    )

    assert confirmed.plan.decision_status == "confirmed"
    assert confirmed.plan.revision_number == 2
    assert confirmed.plan.supersedes_plan_artifact_id == proposal.artifact_id
    assert proposal.to_parent_ref() in confirmed.plan_artifact.parents
    assert repeated.reused is True
    assert repeated.plan_artifact.artifact_id == confirmed.plan_artifact.artifact_id
    selected = select_current_account_launch_plan(
        tuple(repository.artifacts.values()),
        logical_account=LOGICAL_ACCOUNT,
        require_confirmed=True,
    )
    assert selected is not None and selected.plan_artifact == confirmed.plan_artifact


@pytest.mark.asyncio
async def test_confirm_launch_plan_rejects_a_tampered_existing_confirmation_child() -> None:
    world = _map_artifact()
    strategy = _strategy_artifact()
    proposal = seal_account_launch_plan(
        project=PROJECT,
        logical_account=LOGICAL_ACCOUNT,
        plan=_plan(strategy_artifact_id=strategy.artifact_id),
        strategy_artifact=strategy,
        content_world_artifact=world,
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-2",
    )
    proposed_plan = AccountLaunchPlan.model_validate(proposal.payload)
    tampered_plan = proposed_plan.model_copy(
        update={
            "revision_number": 2,
            "supersedes_plan_artifact_id": proposal.artifact_id,
            "revision_reason": "伪造的确认子工件。",
            "decision_status": "confirmed",
            "confirmation_user_text": account_launch_plan_confirmation_text(proposal.artifact_id),
            "planning_request": "被改写的起号计划",
        }
    )
    tampered_confirmation = ArtifactEnvelope.seal(
        project=PROJECT,
        artifact_type="account_launch_plan",
        version=2,
        payload=tampered_plan.model_dump(mode="json"),
        logical_account=LOGICAL_ACCOUNT,
        parents=(
            strategy.to_parent_ref(),
            world.to_parent_ref(),
            proposal.to_parent_ref(),
        ),
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-tampered",
    )
    repository = _MemoryRepository((world, strategy, proposal, tampered_confirmation))

    with pytest.raises(ValueError, match="changed content"):
        await confirm_account_launch_plan(
            project=PROJECT,
            logical_account=LOGICAL_ACCOUNT,
            repository=repository,
            plan_artifact_id=proposal.artifact_id,
            confirmation_user_text=account_launch_plan_confirmation_text(proposal.artifact_id),
            created_at=NOW,
            source_thread_id="thread-1",
            source_run_id="run-replay",
        )


@pytest.mark.asyncio
async def test_launch_plan_selection_and_confirmation_are_isolated_by_logical_account() -> None:
    first_world = _map_artifact()
    first_strategy = _strategy_artifact()
    first_proposal = seal_account_launch_plan(
        project=PROJECT,
        logical_account=LOGICAL_ACCOUNT,
        plan=_plan(strategy_artifact_id=first_strategy.artifact_id),
        strategy_artifact=first_strategy,
        content_world_artifact=first_world,
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-first",
    )
    second_world = _map_artifact(logical_account=SECOND_LOGICAL_ACCOUNT)
    second_strategy = _strategy_artifact(logical_account=SECOND_LOGICAL_ACCOUNT)
    second_proposal = seal_account_launch_plan(
        project=PROJECT,
        logical_account=SECOND_LOGICAL_ACCOUNT,
        plan=_plan(strategy_artifact_id=second_strategy.artifact_id),
        strategy_artifact=second_strategy,
        content_world_artifact=second_world,
        created_at=NOW,
        source_thread_id="thread-2",
        source_run_id="run-second",
    )
    repository = _MemoryRepository(
        (
            first_world,
            first_strategy,
            first_proposal,
            second_world,
            second_strategy,
            second_proposal,
        )
    )

    confirmed = await confirm_account_launch_plan(
        project=PROJECT,
        logical_account=LOGICAL_ACCOUNT,
        repository=repository,
        plan_artifact_id=first_proposal.artifact_id,
        confirmation_user_text=account_launch_plan_confirmation_text(first_proposal.artifact_id),
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-confirm-first",
    )

    assert confirmed.plan_artifact.logical_account == LOGICAL_ACCOUNT
    first_current = select_current_account_launch_plan(
        tuple(repository.artifacts.values()),
        logical_account=LOGICAL_ACCOUNT,
        require_confirmed=True,
    )
    second_current = select_current_account_launch_plan(
        tuple(repository.artifacts.values()),
        logical_account=SECOND_LOGICAL_ACCOUNT,
    )
    assert first_current is not None and first_current.plan.decision_status == "confirmed"
    assert second_current is not None and second_current.plan.decision_status == "proposed"
    assert second_current.plan_artifact.artifact_id == second_proposal.artifact_id
