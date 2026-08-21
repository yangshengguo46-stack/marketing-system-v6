from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from deerflow.incubation import ArtifactEnvelope, LogicalAccountRef, ProjectRef
from deerflow.incubation.account_launch_plan import (
    confirm_account_launch_plan,
    prepare_account_launch_plan,
    select_current_account_launch_plan,
)
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


def _map_artifact(*, logical_account: LogicalAccountRef = LOGICAL_ACCOUNT) -> ArtifactEnvelope:
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
        "strategy_artifact_id",
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

    confirmed = await confirm_account_launch_plan(
        project=PROJECT,
        logical_account=LOGICAL_ACCOUNT,
        repository=repository,
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-3",
    )
    repeated = await confirm_account_launch_plan(
        project=PROJECT,
        logical_account=LOGICAL_ACCOUNT,
        repository=repository,
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
