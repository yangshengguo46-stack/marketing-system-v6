from datetime import UTC, datetime

import pytest

from deerflow.content_intelligence import (
    BaseDraft,
    BasisRef,
    ComprehensionRecord,
    ContentDimension,
    ContentIntelligenceBundle,
    ContentPath,
    ContentPathStep,
    ContentWorldView,
    MessagePlan,
    Observation,
    ShootingDelivery,
    SourceItem,
    TopicBrief,
)
from deerflow.incubation import (
    AccountLaunchPlan,
    ArtifactEnvelope,
    ArtifactParentRef,
    EvidenceCoverageReceipt,
    EvidenceItem,
    EvidenceSnapshot,
    FirstWeekDay,
    LaunchCapacity,
    LaunchCheckpoint,
    LaunchPhase,
    LaunchSeries,
    LogicalAccountRef,
    PlannedTopicSeed,
    ProjectRef,
    account_launch_plan_confirmation_text,
    seal_content_run_artifacts,
    select_used_topic_evidence_snapshots,
)
from deerflow.incubation.account_direction import AccountDirectionOption, AccountDirectionVersion

NOW = datetime(2026, 8, 17, 14, 0, tzinfo=UTC)


def _content_run() -> tuple[ContentIntelligenceBundle, ShootingDelivery]:
    evidence_ref = BasisRef(kind="observation", ref_id="observation-gift-1")
    record = ComprehensionRecord(
        record_id="record-golden-gift",
        subject_expression="我是做黄金礼品的，我要怎么起号？",
        sources=(
            SourceItem(
                source_id="source-user",
                kind="user_statement",
                content="我是做黄金礼品的，我要怎么起号？",
            ),
            SourceItem(
                source_id="source-topic-1",
                kind="web_page",
                evidence_role="topic_evidence",
                title="一份公开礼制资料",
                uri="https://example.com/rites",
                content="公开资料描述了礼在人际关系和社会秩序中的作用。",
            ),
        ),
        observations=(
            Observation(
                observation_id="observation-gift-1",
                claim="公开资料将礼与人与人之间的关系联系起来。",
                source_refs=("source-topic-1",),
            ),
        ),
    )
    path = ContentPath(
        path_id="path-rites",
        steps=(
            ContentPathStep(
                from_label="礼与人与人相处",
                relation="通过具体制度观察",
                to_label="古代礼制",
                basis_refs=(evidence_ref,),
            ),
        ),
        rationale="从具体礼制理解人与人怎样相处。",
    )
    world = ContentWorldView(
        record_id=record.record_id,
        source_object="黄金礼品",
        content_entry="送礼",
        content_root="礼与人与人相处",
        root_rationale="黄金是材质，礼品的用途进入礼与人际关系。",
        editorial_promise="借具体的礼与人情故事理解人与人怎样相处。",
        recurring_lens="从人物、时间、地点和事件进入一段关系。",
        drift_boundaries=("不退回黄金产品目录。",),
        dimensions=(
            ContentDimension(
                name="制度与习俗",
                rationale="礼如何成为具体制度和习俗。",
                paths=(path,),
            ),
        ),
    )
    topic = TopicBrief(
        record_id=record.record_id,
        content_map_version_id=world.content_map_version_id(),
        question="古代的礼为什么不只是礼貌？",
        central_claim="礼还承担安排人与人关系和社会秩序的作用。",
        mechanism="制度和习俗把抽象关系变成可观察的行为。",
        counterpoint="不能把不同时期的礼制混成一套固定规则。",
        path=path,
        evidence_refs=(evidence_ref,),
        limitations=("当前只有一份有界公开资料。",),
    )
    bundle = ContentIntelligenceBundle(
        record=record,
        content_world=world,
        topic_brief=topic,
    )
    plan = MessagePlan(
        message_plan_id="message-plan-1",
        record_id=record.record_id,
        topic_title="古代的礼，为什么不只是礼貌？",
        focal_subject="生活在礼制中的普通人",
        context="古代社会的日常交往中",
        concrete_event_or_question="人们为什么需要用一套礼来安排彼此的关系",
        account_position="从一名礼品经营者观察礼与人情关系",
        account_position_basis=record.subject_expression,
        point_of_view="礼的深层作用是把人与人的关系变成共同理解的秩序",
        entry_point="从今天把礼理解成礼貌这个误会讲起",
        telling_lens="跟着礼的含义变化理解关系如何被安排",
        audience_question="为什么古人把礼看得如此重要",
        information_order="先辨认今天的直觉，再回到制度作用，最后说明边界",
        payoff="观众理解礼貌只是礼的一小部分",
        opening="今天说一个人有礼，通常只是说他有礼貌。",
        message_beats=("但在古代，礼还在安排身份、关系和行为。",),
        closing="所以礼崩坏，说的从来不只是大家突然没礼貌了。",
        evidence_refs=(evidence_ref,),
        limitations=topic.limitations,
    )
    delivery = ShootingDelivery(
        message_plan=plan,
        base_draft=BaseDraft(
            draft_id="base-draft-1",
            message_plan_id=plan.message_plan_id,
            text="今天说一个人有礼，通常只是说他有礼貌。\n\n但在古代，礼还在安排身份、关系和行为。",
        ),
    )
    return bundle, delivery


def _topic_snapshot(*, uri: str, role: str = "topic_evidence") -> EvidenceSnapshot:
    return EvidenceSnapshot(
        provider="douyin_open_platform",
        collection_method="official_openapi",
        evidence_role=role,
        captured_at=NOW,
        rights_basis="public search through the configured Douyin Open Platform application",
        query="人情往来 礼",
        items=(
            EvidenceItem(
                source_ref=f"douyin:video:{uri.rsplit('/', 1)[-1]}",
                source_type="douyin_video",
                title="一条公开视频",
                excerpt="公开证据摘要。",
                provenance="observed",
                public_uri=uri,
            ),
        ),
        coverage=EvidenceCoverageReceipt(
            population_scope="public_video_search_results",
            requested_count=3,
            returned_count=1,
        ),
        limitations=("This snapshot is bounded topic evidence.",),
    )


def _confirmed_launch_plan(
    *,
    project: ProjectRef,
    logical_account: LogicalAccountRef,
    direction: ArtifactEnvelope,
    content_world: ArtifactEnvelope,
) -> ArtifactEnvelope:
    plan_proposal = AccountLaunchPlan(
        direction_artifact_id=direction.artifact_id,
        content_map_version_id=content_world.payload["content_map_version_id"],
        planning_request="按已确认方向编排首轮起号计划",
        capacity=LaunchCapacity(
            status="provisional",
            cadence_summary="先用一条可核验题眼进入内容链。",
            basis="发布能力尚未由用户确认。",
            adjustment_trigger="依据实际制作能力调整。",
        ),
        series=(
            LaunchSeries(
                series_id="relations",
                name="礼与关系",
                purpose="用具体事件观察关系。",
                map_path_ids=("path-rites",),
                repeatable_question="一套礼怎样改变人与人的关系？",
                topic_sources=("public_evidence",),
            ),
        ),
        topic_seeds=(
            PlannedTopicSeed(
                seed_id="seed-rites",
                series_id="relations",
                map_path_id="path-rites",
                content_role="understanding",
                focal_subject="古代礼制中的普通人",
                concrete_event_or_question="古代的礼为什么不只是礼貌？",
                account_viewpoint="从礼品经营者的视角观察礼与关系。",
                source_kind="public_evidence",
                evidence_need="找到可核验的礼制资料。",
            ),
        ),
        first_week=tuple(
            FirstWeekDay(
                day=day,
                focus=f"第 {day} 天观察",
                actions=("核对证据后再决定是否制作。",),
                topic_seed_ids=(("seed-rites",) if day == 1 else ()),
            )
            for day in range(1, 8)
        ),
        later_phases=(
            LaunchPhase(
                start_day=8,
                end_day=30,
                objective="根据真实回执保留或调整系列。",
                series_ids=("relations",),
                actions=("回收可观测结果。",),
                review_questions=("题眼是否形成了可持续问题？",),
            ),
        ),
        checkpoints=(
            LaunchCheckpoint(
                day=7,
                questions=("首个题眼是否得到证据？",),
                possible_adjustments=("调整证据需求。",),
            ),
            LaunchCheckpoint(
                day=30,
                questions=("系列是否值得继续？",),
                possible_adjustments=("保留或停止该系列。",),
            ),
        ),
    )
    plan_proposal_artifact = ArtifactEnvelope.seal(
        project=project,
        logical_account=logical_account,
        artifact_type="account_launch_plan",
        version=plan_proposal.revision_number,
        payload=plan_proposal.model_dump(mode="json"),
        parents=(direction.to_parent_ref(), content_world.to_parent_ref()),
        created_at=NOW,
        source_thread_id="thread-plan-proposal",
        source_run_id="run-plan-proposal",
    )
    plan = AccountLaunchPlan.model_validate(
        plan_proposal.model_copy(
            update={
                "revision_number": 2,
                "supersedes_plan_artifact_id": plan_proposal_artifact.artifact_id,
                "revision_reason": "用户确认采用当前起号计划。",
                "decision_status": "confirmed",
                "confirmation_user_text": account_launch_plan_confirmation_text(plan_proposal_artifact.artifact_id),
            }
        ).model_dump(mode="json")
    )
    return ArtifactEnvelope.seal(
        project=project,
        logical_account=logical_account,
        artifact_type="account_launch_plan",
        version=plan.revision_number,
        payload=plan.model_dump(mode="json"),
        parents=(
            direction.to_parent_ref(),
            content_world.to_parent_ref(),
            plan_proposal_artifact.to_parent_ref(),
        ),
        created_at=NOW,
        source_thread_id="thread-plan",
        source_run_id="run-plan",
    )


def test_content_run_artifacts_preserve_roles_and_parent_lineage() -> None:
    bundle, delivery = _content_run()
    project = ProjectRef(owner_user_id="user-1", project_id="golden-gift")
    evidence_parent = ArtifactParentRef(
        owner_user_id="user-1",
        project_id="golden-gift",
        artifact_id="artifact-evidence-1",
        artifact_type="evidence_snapshot",
        content_sha256="a" * 64,
    )

    sealed = seal_content_run_artifacts(
        project=project,
        bundle=bundle,
        delivery=delivery,
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-1",
        reading_parents=(evidence_parent,),
    )

    ordered = sealed.storage_order()
    assert [artifact.artifact_type for artifact in ordered] == [
        "content_reading",
        "content_map_candidate",
        "topic_brief",
        "message_plan",
        "draft_version",
    ]
    assert [source["evidence_role"] for source in sealed.content_reading.payload["record"]["sources"]] == [
        "user_material",
        "topic_evidence",
    ]
    assert sealed.content_reading.parents == (evidence_parent,)
    assert sealed.content_reading.payload["root_selection"]["content_entry"] == "送礼"
    assert "content_entry" not in sealed.content_world.payload
    assert set(sealed.topic_brief.parents) == {
        sealed.content_reading.to_parent_ref(),
        sealed.content_world.to_parent_ref(),
    }
    assert sealed.message_plan.parents == (sealed.topic_brief.to_parent_ref(),)
    assert sealed.draft_version.parents == (sealed.message_plan.to_parent_ref(),)
    assert sealed.draft_version.payload["stage"] == "base"
    assert sealed.draft_version.payload["text"] == delivery.base_draft.text
    assert all(artifact.project == project for artifact in ordered)
    assert all(artifact.source_thread_id == "thread-1" for artifact in ordered)
    assert all(artifact.source_run_id == "run-1" for artifact in ordered)


def test_message_plan_records_the_exact_incubation_judgment_it_used() -> None:
    bundle, delivery = _content_run()
    project = ProjectRef(owner_user_id="user-1", project_id="golden-gift")
    judgment = ArtifactEnvelope.seal(
        project=project,
        artifact_type="incubation_judgment",
        version=1,
        payload={"content_map_version_id": bundle.content_world.content_map_version_id()},
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-1",
    )

    sealed = seal_content_run_artifacts(
        project=project,
        bundle=bundle,
        delivery=delivery,
        incubation_judgment_artifact=judgment,
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-1",
    )

    assert set(sealed.topic_brief.parents) == {
        sealed.content_reading.to_parent_ref(),
        sealed.content_world.to_parent_ref(),
    }
    assert set(sealed.message_plan.parents) == {
        sealed.topic_brief.to_parent_ref(),
        judgment.to_parent_ref(),
    }
    assert sealed.draft_version.parents == (sealed.message_plan.to_parent_ref(),)


def test_message_plan_can_reference_a_confirmed_direction_without_a_map_bound_strategy() -> None:
    bundle, delivery = _content_run()
    project = ProjectRef(owner_user_id="user-1", project_id="golden-gift")
    logical_account = LogicalAccountRef(
        owner_user_id="user-1",
        project_id="golden-gift",
        logical_account_id="account-1",
    )
    direction_payload = AccountDirectionVersion(
        revision_number=1,
        proposal_artifact_id="proposal-1",
        source_user_text="我是做黄金礼品的，我想从礼与关系切入。",
        confirmation_user_text="确认采用这个方向。",
        marketing_subject="黄金礼品业务",
        selected_option=AccountDirectionOption(
            option_id="direction_1",
            name="从礼观察关系",
            content_root="礼与人与人相处",
            long_term_content_subject="从具体赠与事件观察人与人如何相处",
            rationale="业务提供观察入口，内容根保持在礼与关系。",
        ),
    )
    direction = ArtifactEnvelope.seal(
        project=project,
        logical_account=logical_account,
        artifact_type="account_direction_version",
        version=1,
        payload=direction_payload.model_dump(mode="json"),
        created_at=NOW,
        source_thread_id="thread-direction",
        source_run_id="run-direction",
    )

    sealed = seal_content_run_artifacts(
        project=project,
        logical_account=logical_account,
        bundle=bundle,
        delivery=delivery,
        account_direction_artifact=direction,
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-1",
    )

    assert set(sealed.message_plan.parents) == {
        sealed.topic_brief.to_parent_ref(),
        direction.to_parent_ref(),
    }
    assert sealed.content_world.parents == (direction.to_parent_ref(),)


def test_launch_topic_lineage_binds_the_exact_confirmed_plan_seed_and_proposal_parent() -> None:
    bundle, delivery = _content_run()
    project = ProjectRef(owner_user_id="user-1", project_id="golden-gift")
    logical_account = LogicalAccountRef(
        owner_user_id="user-1",
        project_id="golden-gift",
        logical_account_id="account-1",
    )
    direction_payload = AccountDirectionVersion(
        revision_number=1,
        proposal_artifact_id="proposal-1",
        source_user_text="我是做黄金礼品的，我想从礼与关系切入。",
        confirmation_user_text="确认采用这个方向。",
        marketing_subject="黄金礼品业务",
        selected_option=AccountDirectionOption(
            option_id="direction_1",
            name="从礼观察关系",
            content_root="礼与人与人相处",
            long_term_content_subject="从具体赠与事件观察人与人如何相处",
            rationale="业务提供观察入口，内容根保持在礼与关系。",
        ),
    )
    direction = ArtifactEnvelope.seal(
        project=project,
        logical_account=logical_account,
        artifact_type="account_direction_version",
        version=1,
        payload=direction_payload.model_dump(mode="json"),
        created_at=NOW,
        source_thread_id="thread-direction",
        source_run_id="run-direction",
    )
    map_run = seal_content_run_artifacts(
        project=project,
        logical_account=logical_account,
        bundle=bundle,
        delivery=None,
        account_direction_artifact=direction,
        created_at=NOW,
        source_thread_id="thread-map",
        source_run_id="run-map",
    )
    launch_plan = _confirmed_launch_plan(
        project=project,
        logical_account=logical_account,
        direction=direction,
        content_world=map_run.content_world,
    )

    sealed = seal_content_run_artifacts(
        project=project,
        logical_account=logical_account,
        bundle=bundle,
        delivery=delivery,
        account_direction_artifact=direction,
        launch_plan_artifact=launch_plan,
        launch_topic_seed_id="seed-rites",
        created_at=NOW,
        source_thread_id="thread-topic",
        source_run_id="run-topic",
    )

    assert sealed.content_reading.payload["launch_plan_context"] == {
        "plan_artifact_id": launch_plan.artifact_id,
        "plan_content_sha256": launch_plan.content_sha256,
        "topic_seed_id": "seed-rites",
    }
    assert launch_plan.to_parent_ref() in sealed.content_reading.parents
    assert launch_plan.to_parent_ref() in sealed.topic_brief.parents
    assert direction.to_parent_ref() in sealed.content_world.parents

    orphan_plan = ArtifactEnvelope.seal(
        project=project,
        logical_account=logical_account,
        artifact_type="account_launch_plan",
        version=launch_plan.version,
        payload=launch_plan.payload,
        parents=(direction.to_parent_ref(), map_run.content_world.to_parent_ref()),
        created_at=NOW,
        source_thread_id="thread-orphan-plan",
        source_run_id="run-orphan-plan",
    )
    with pytest.raises(ValueError, match="exact proposal parent"):
        seal_content_run_artifacts(
            project=project,
            logical_account=logical_account,
            bundle=bundle,
            delivery=delivery,
            account_direction_artifact=direction,
            launch_plan_artifact=orphan_plan,
            launch_topic_seed_id="seed-rites",
            created_at=NOW,
            source_thread_id="thread-topic",
            source_run_id="run-topic",
        )


@pytest.mark.parametrize(
    ("plan_present", "seed_id", "message"),
    (
        (False, "seed-rites", "supplied together"),
        (True, None, "supplied together"),
        (True, "missing-seed", "topic seed"),
    ),
)
def test_launch_topic_lineage_rejects_an_incomplete_or_unknown_receipt_pair(
    plan_present: bool,
    seed_id: str | None,
    message: str,
) -> None:
    bundle, delivery = _content_run()
    project = ProjectRef(owner_user_id="user-1", project_id="golden-gift")
    logical_account = LogicalAccountRef(
        owner_user_id="user-1",
        project_id="golden-gift",
        logical_account_id="account-1",
    )
    direction_payload = AccountDirectionVersion(
        revision_number=1,
        proposal_artifact_id="proposal-1",
        source_user_text="我是做黄金礼品的。",
        confirmation_user_text="确认这个方向。",
        marketing_subject="黄金礼品业务",
        selected_option=AccountDirectionOption(
            option_id="direction_1",
            name="从礼观察关系",
            content_root="礼与人与人相处",
            long_term_content_subject="礼与人与人相处",
            rationale="保持内容根稳定。",
        ),
    )
    direction = ArtifactEnvelope.seal(
        project=project,
        logical_account=logical_account,
        artifact_type="account_direction_version",
        version=1,
        payload=direction_payload.model_dump(mode="json"),
        created_at=NOW,
        source_thread_id="thread-direction",
        source_run_id="run-direction",
    )
    map_run = seal_content_run_artifacts(
        project=project,
        logical_account=logical_account,
        bundle=bundle,
        delivery=None,
        account_direction_artifact=direction,
        created_at=NOW,
        source_thread_id="thread-map",
        source_run_id="run-map",
    )
    launch_plan = _confirmed_launch_plan(
        project=project,
        logical_account=logical_account,
        direction=direction,
        content_world=map_run.content_world,
    )

    with pytest.raises(ValueError, match=message):
        seal_content_run_artifacts(
            project=project,
            logical_account=logical_account,
            bundle=bundle,
            delivery=delivery,
            account_direction_artifact=direction,
            launch_plan_artifact=(launch_plan if plan_present else None),
            launch_topic_seed_id=seed_id,
            created_at=NOW,
            source_thread_id="thread-topic",
            source_run_id="run-topic",
        )


def test_rejects_judgment_lineage_without_a_delivery() -> None:
    bundle, _delivery = _content_run()
    project = ProjectRef(owner_user_id="user-1", project_id="golden-gift")
    judgment = ArtifactEnvelope.seal(
        project=project,
        artifact_type="incubation_judgment",
        version=1,
        payload={"content_map_version_id": bundle.content_world.content_map_version_id()},
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-1",
    )

    with pytest.raises(ValueError, match="requires a shooting delivery"):
        seal_content_run_artifacts(
            project=project,
            bundle=bundle,
            delivery=None,
            incubation_judgment_artifact=judgment,
            created_at=NOW,
            source_thread_id="thread-1",
            source_run_id="run-1",
        )


@pytest.mark.parametrize(
    ("project", "artifact_type", "message"),
    (
        (ProjectRef(owner_user_id="other-user", project_id="golden-gift"), "incubation_judgment", "project"),
        (ProjectRef(owner_user_id="user-1", project_id="golden-gift"), "evidence_snapshot", "type"),
    ),
)
def test_rejects_invalid_judgment_parent(
    project: ProjectRef,
    artifact_type: str,
    message: str,
) -> None:
    bundle, delivery = _content_run()
    expected_project = ProjectRef(owner_user_id="user-1", project_id="golden-gift")
    judgment = ArtifactEnvelope.seal(
        project=project,
        artifact_type=artifact_type,
        version=1,
        payload={"content_map_version_id": bundle.content_world.content_map_version_id()},
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-1",
    )

    with pytest.raises(ValueError, match=message):
        seal_content_run_artifacts(
            project=expected_project,
            bundle=bundle,
            delivery=delivery,
            incubation_judgment_artifact=judgment,
            created_at=NOW,
            source_thread_id="thread-1",
            source_run_id="run-1",
        )


def test_rejects_judgment_for_a_different_content_world_version() -> None:
    bundle, delivery = _content_run()
    project = ProjectRef(owner_user_id="user-1", project_id="golden-gift")
    judgment = ArtifactEnvelope.seal(
        project=project,
        artifact_type="incubation_judgment",
        version=1,
        payload={"content_map_version_id": "content-map-stale"},
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-1",
    )

    with pytest.raises(ValueError, match="content world version"):
        seal_content_run_artifacts(
            project=project,
            bundle=bundle,
            delivery=delivery,
            incubation_judgment_artifact=judgment,
            created_at=NOW,
            source_thread_id="thread-1",
            source_run_id="run-1",
        )


def test_content_run_selects_only_topic_snapshots_used_by_the_final_reading() -> None:
    bundle, _delivery = _content_run()
    selected = _topic_snapshot(uri="https://example.com/rites")
    unrelated = _topic_snapshot(uri="https://www.douyin.com/video/unrelated")
    wrong_role = _topic_snapshot(
        uri="https://example.com/rites",
        role="benchmark_account_candidate",
    )

    snapshots = select_used_topic_evidence_snapshots(
        bundle,
        (unrelated, wrong_role, selected, selected),
    )

    assert snapshots == (selected,)


def test_content_run_without_a_topic_still_seals_the_reading_and_candidate_map() -> None:
    bundle, _delivery = _content_run()
    map_only = bundle.model_copy(update={"topic_brief": None})

    sealed = seal_content_run_artifacts(
        project=ProjectRef(owner_user_id="user-1", project_id="golden-gift"),
        bundle=map_only,
        delivery=None,
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-1",
    )

    assert [artifact.artifact_type for artifact in sealed.storage_order()] == [
        "content_reading",
        "content_map_candidate",
    ]
    assert sealed.topic_brief is None
    assert sealed.message_plan is None
    assert sealed.draft_version is None
