from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from deerflow.incubation import ArtifactEnvelope, ProjectRef
from deerflow.incubation.judgment import (
    AccountPresentationPlan,
    AudienceHypothesis,
    BriefFact,
    IncubationBrief,
    IncubationJudgment,
    MonetizationHypothesis,
    PersonaDecision,
    PositioningDecision,
    seal_incubation_brief,
    seal_incubation_judgment,
)

NOW = datetime(2026, 8, 17, 16, 0, tzinfo=UTC)
PROJECT = ProjectRef(owner_user_id="user-1", project_id="golden-gift")


def _world() -> ArtifactEnvelope:
    return ArtifactEnvelope.seal(
        project=PROJECT,
        artifact_type="content_world",
        version=1,
        payload={
            "content_map_version_id": "map-gift-relations-v1",
            "content_root": "礼与人与人相处",
            "audience_territory": "关心人情、礼节和关系判断的人",
            "editorial_promise": "借具体的人、事、时间和地方理解人与人怎样相处。",
            "recurring_lens": "从一件具体的礼或关系事件进入。",
            "drift_boundaries": ["不退回黄金产品目录。"],
            "dimensions": [],
        },
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-1",
    )


def _brief() -> IncubationBrief:
    return IncubationBrief(
        subject_expression="我是做黄金礼品的，我要怎么起号？",
        business_facts=(
            BriefFact(
                statement="用户经营黄金礼品。",
                provenance="user_stated",
                source_quote="我是做黄金礼品的",
            ),
        ),
        goals=(
            BriefFact(
                statement="用户希望从零开始运营账号。",
                provenance="user_stated",
                source_quote="我要怎么起号",
            ),
        ),
        unknowns=("尚不知道用户是否愿意露脸。",),
    )


def _brief_artifact() -> ArtifactEnvelope:
    return seal_incubation_brief(
        project=PROJECT,
        brief=_brief(),
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-1",
    )


def _judgment(*, basis_ids: tuple[str, ...]) -> IncubationJudgment:
    return IncubationJudgment(
        content_map_version_id="map-gift-relations-v1",
        positioning=PositioningDecision(
            decision="研究礼、人情和关系秩序的礼品从业者账号",
            audience_promise="每次借一件具体的人情事件，讲清人与人怎样相处。",
            rationale="这与冻结内容根一致，也保留用户真实从业位置。",
            basis_artifact_ids=basis_ids,
        ),
        audience=AudienceHypothesis(
            people="经常面对送礼、回礼、礼节和关系判断的人",
            recurring_interest="想理解一件礼背后的关系含义，而不只想看商品。",
            why_return="账号持续提供可迁移的人情判断视角。",
            rationale="内容地图长期围绕礼和关系展开，受众假设仍需真实数据校正。",
            basis_artifact_ids=basis_ids,
        ),
        persona=PersonaDecision(
            account_role="从礼品生意观察人情世界的一线从业者",
            trust_basis=("用户真实经营黄金礼品。",),
            boundaries=("不冒充历史学者或礼仪专家。",),
            rationale="保留真实从业身份，不补造证书或表现力。",
            basis_artifact_ids=basis_ids,
        ),
        presentation=AccountPresentationPlan(
            primary_forms=("口述故事", "图文资料叙事"),
            supporting_forms=("情景短剧",),
            rationale="账号级形式组合服务同一内容世界；单条内容仍需另做 FormatDecision。",
            constraints=("是否露脸仍未知。",),
            basis_artifact_ids=basis_ids,
        ),
        monetization=(
            MonetizationHypothesis(
                path="由礼与关系判断建立信任，再由主页或咨询承接礼品需求。",
                trust_required="观众先确认账号确实懂不同关系和场合。",
                preconditions=("用户确认实际可承接的产品与服务。",),
                rationale="变现独立于内容地图，只描述待验证的信任承接路径。",
                basis_artifact_ids=basis_ids,
            ),
        ),
        unknowns=("尚未取得真实受众反馈。",),
        alternatives=("若本人不适合出镜，可先采用图文资料叙事。",),
    )


def test_incubation_brief_allows_missing_information_without_inventing_it() -> None:
    brief = _brief()

    assert brief.resources == ()
    assert brief.capabilities == ()
    assert brief.constraints == ()
    assert brief.unknowns == ("尚不知道用户是否愿意露脸。",)


def test_incubation_brief_rejects_agent_inference_as_a_project_fact() -> None:
    with pytest.raises(ValidationError):
        BriefFact(
            statement="用户擅长镜头表达。",
            provenance="agent_inferred",
            source_quote="用户没有说过这句话",
        )


def test_incubation_judgment_keeps_account_forms_separate_from_content_topics() -> None:
    brief = _brief_artifact()
    world = _world()
    judgment = _judgment(basis_ids=(brief.artifact_id, world.artifact_id))

    assert judgment.presentation.primary_forms == ("口述故事", "图文资料叙事")
    assert not hasattr(judgment.presentation, "topic")
    assert judgment.positioning.decision.startswith("研究礼")


def test_incubation_judgment_requires_brief_and_matching_frozen_world_parents() -> None:
    brief = _brief_artifact()
    world = _world()
    judgment = _judgment(basis_ids=(brief.artifact_id, world.artifact_id))

    sealed = seal_incubation_judgment(
        project=PROJECT,
        judgment=judgment,
        brief_artifact=brief,
        content_world_artifact=world,
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-1",
    )

    assert sealed.artifact_type == "incubation_judgment"
    assert sealed.parents == tuple(
        sorted(
            (brief.to_parent_ref(), world.to_parent_ref()),
            key=lambda parent: parent.artifact_id,
        )
    )
    assert sealed.payload["content_map_version_id"] == "map-gift-relations-v1"


def test_incubation_judgment_rejects_a_different_content_map_version() -> None:
    brief = _brief_artifact()
    world = _world()
    judgment = _judgment(basis_ids=(brief.artifact_id, world.artifact_id)).model_copy(update={"content_map_version_id": "map-something-else"})

    with pytest.raises(ValueError, match="content map version"):
        seal_incubation_judgment(
            project=PROJECT,
            judgment=judgment,
            brief_artifact=brief,
            content_world_artifact=world,
            created_at=NOW,
            source_thread_id="thread-1",
            source_run_id="run-1",
        )


def test_incubation_judgment_rejects_unbound_basis_artifacts() -> None:
    brief = _brief_artifact()
    world = _world()
    judgment = _judgment(basis_ids=(brief.artifact_id, "artifact_not_a_parent"))

    with pytest.raises(ValueError, match="basis artifact"):
        seal_incubation_judgment(
            project=PROJECT,
            judgment=judgment,
            brief_artifact=brief,
            content_world_artifact=world,
            created_at=NOW,
            source_thread_id="thread-1",
            source_run_id="run-1",
        )
