from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from deerflow.content_intelligence.analyzer import (
    ContentAudienceContext,
    ContentIntelligenceRequest,
    ContentRootCandidateSetDraft,
    ContentRootSelectionDraft,
    RootCandidateDraft,
    _render_frozen_map_input,
    _render_root_decision_input,
)
from deerflow.incubation.account_audience import (
    AccountAudienceProposalDraft,
    AccountAudienceRouteDraft,
    MarketingSubjectSnapshot,
    SubjectTermEvidence,
    compile_account_audience_decision,
    confirm_account_audience_decision,
    prepare_account_audience,
    render_account_audience_decision,
    seal_account_audience_decision,
)
from deerflow.incubation.account_audience_runtime import generate_account_audience_decision
from deerflow.incubation.brief_runtime import build_subject_incubation_brief
from deerflow.incubation.contracts import LogicalAccountRef, ProjectRef
from deerflow.incubation.host_product_profile import (
    build_agent_self_subject,
    current_host_product_profile,
    seal_host_product_profile,
)
from deerflow.incubation.judgment import IncubationBrief

NOW = datetime(2026, 8, 21, 12, 0, tzinfo=UTC)
PROJECT = ProjectRef(owner_user_id="user-1", project_id="project-1")
ACCOUNT = LogicalAccountRef(
    owner_user_id="user-1",
    project_id="project-1",
    logical_account_id="account-1",
)


def _subject(expression: str = "我是做水果生意的") -> MarketingSubjectSnapshot:
    return MarketingSubjectSnapshot(
        subject_kind="user_business",
        subject_expression=expression,
        source_user_request=expression,
        business_facts=(expression,),
    )


def _route(
    option_id: str,
    *,
    name: str,
    target_people: str,
    content_audience: str,
) -> AccountAudienceRouteDraft:
    return AccountAudienceRouteDraft(
        option_id=option_id,
        name=name,
        business_role="水果经营者",
        market_relationship="向明确客户群提供水果商品",
        account_objective=f"让{target_people}理解这项业务的选择价值并产生合适的业务行动",
        payer_or_contracting_party=target_people,
        decision_makers=target_people,
        users_or_beneficiaries=target_people,
        target_people=target_people,
        target_need="稳定获得符合其采购或消费要求的水果",
        desired_action="产生咨询、到店或采购行为",
        market_scope="用户尚未说明地区",
        content_audience=content_audience,
        recurring_interest="持续了解与自身采购或消费有关的水果知识和判断",
        rationale="由交易对象差异形成不同的账号路线",
        confidence="low",
        unknowns=("具体地区和品类尚未确认",),
    )


def test_material_b2b_b2c_difference_must_remain_an_audience_choice() -> None:
    draft = AccountAudienceProposalDraft(
        route_options=(
            _route(
                "b2b_wholesale",
                name="产地批发",
                target_people="批发商、零售商、餐饮采购者",
                content_audience="需要判断货源、行情和品质的经营者",
            ),
            _route(
                "b2c_retail",
                name="终端零售",
                target_people="家庭消费者和到店顾客",
                content_audience="关心水果口感、吃法、文化和选择的消费者",
            ),
        ),
        recommended_option_id="b2b_wholesale",
        material_choice_required=True,
        choice_reason="批发与零售会改变客户、内容和成交方式，不能替用户合并。",
    )

    decision = compile_account_audience_decision(
        subject=_subject(),
        draft=draft,
    )

    assert decision.decision_status == "proposed"
    assert decision.selected_option_id is None
    assert decision.route_options[0].target_people != decision.route_options[1].target_people
    rendered = render_account_audience_decision(decision)
    assert "谁付钱或签约" in rendered
    assert "谁做决定" in rendered
    assert "谁使用或受益" in rendered
    assert "谁会长期看内容" in rendered


def test_clear_business_audience_can_resolve_without_a_confirmation_gate() -> None:
    route = _route(
        "b2b_wholesale",
        name="产地批发",
        target_people="水果批发商、零售商和餐饮采购者",
        content_audience="需要判断货源、行情和品质的经营者",
    )
    draft = AccountAudienceProposalDraft(
        route_options=(route,),
        recommended_option_id=route.option_id,
        material_choice_required=False,
        choice_reason="用户已经明确自己做产地批发。",
    )

    decision = compile_account_audience_decision(
        subject=_subject("我是做水果产地批发的"),
        draft=draft,
    )

    assert decision.decision_status == "resolved"
    assert decision.selected_option_id == "b2b_wholesale"


def test_material_choice_cannot_be_hidden_inside_one_route() -> None:
    route = _route(
        "generic_fruit",
        name="泛水果人群",
        target_people="所有需要水果的人",
        content_audience="所有对水果感兴趣的人",
    )

    with pytest.raises(ValueError, match="material audience choice requires at least two routes"):
        AccountAudienceProposalDraft(
            route_options=(route,),
            recommended_option_id=route.option_id,
            material_choice_required=True,
            choice_reason="批发和零售尚未确认。",
        )


def test_confirmed_audience_route_is_append_only_and_exact() -> None:
    draft = AccountAudienceProposalDraft(
        route_options=(
            _route(
                "adult_children",
                name="子女决策",
                target_people="为父母做健康消费决策的成年子女",
                content_audience="关心父母老年生活和健康管理的成年子女",
            ),
            _route(
                "older_adults",
                name="老人自决策",
                target_people="有自主购买能力的老年消费者",
                content_audience="主动了解老年生活与健康信息的老人",
            ),
        ),
        recommended_option_id="adult_children",
        material_choice_required=True,
        choice_reason="使用者、付款者与内容受众可能不是同一批人。",
    )
    proposed = compile_account_audience_decision(
        subject=_subject("我是做老年保健品的"),
        draft=draft,
    )
    proposed_artifact = seal_account_audience_decision(
        project=PROJECT,
        logical_account=ACCOUNT,
        decision=proposed,
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-1",
    )

    confirmed = confirm_account_audience_decision(
        proposed_artifact=proposed_artifact,
        option_id="adult_children",
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-2",
    )

    assert confirmed.payload["decision_status"] == "confirmed"
    assert confirmed.payload["selected_option_id"] == "adult_children"
    assert confirmed.version == 2
    assert proposed_artifact.artifact_id in {parent.artifact_id for parent in confirmed.parents}


def test_agent_self_subject_is_not_rewritten_as_an_unknown_ordinary_person() -> None:
    subject = MarketingSubjectSnapshot(
        subject_kind="agent_self",
        subject_expression="DeerFlow 内容孵化与新媒体运营 Agent",
        source_user_request="你以自己的第一人称去卖，自己起号做账号",
        business_facts=("这是一个内容孵化与新媒体运营 Agent 产品。",),
        capabilities=("能把业务表达转成账号策略、内容世界和具体可拍选题。",),
        constraints=("不能保证涨粉、播放或成交结果。",),
    )

    assert subject.subject_expression == "DeerFlow 内容孵化与新媒体运营 Agent"
    assert "普通人" not in subject.model_dump_json()


def test_agent_self_subject_comes_from_a_versioned_product_fact_artifact() -> None:
    profile = current_host_product_profile()
    profile_artifact = seal_host_product_profile(
        project=PROJECT,
        logical_account=ACCOUNT,
        profile=profile,
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-1",
    )

    subject = build_agent_self_subject(
        user_request="你以自己的第一人称去卖，自己起号做账号",
        profile_artifact=profile_artifact,
    )

    assert profile_artifact.artifact_type == "host_product_profile"
    assert subject.subject_kind == "agent_self"
    assert subject.subject_expression == profile.subject_expression
    assert subject.basis_artifact_ids == (profile_artifact.artifact_id,)
    assert any("账号策略" in capability for capability in subject.capabilities)
    assert any("保证" in boundary for boundary in subject.constraints)
    assert "翻几百个对标账号" not in subject.model_dump_json()


def test_agent_self_brief_uses_only_versioned_product_facts() -> None:
    profile_artifact = seal_host_product_profile(
        project=PROJECT,
        logical_account=ACCOUNT,
        profile=current_host_product_profile(),
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-1",
    )
    subject = build_agent_self_subject(
        user_request="你以自己的第一人称去卖，自己起号做账号",
        profile_artifact=profile_artifact,
    )

    brief_artifact = build_subject_incubation_brief(
        project=PROJECT,
        logical_account=ACCOUNT,
        subject=subject,
        source_object=subject.subject_expression,
        parent_artifacts=(profile_artifact,),
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-1",
    )
    brief = IncubationBrief.model_validate(brief_artifact.payload)

    assert brief_artifact.parents == (profile_artifact.to_parent_ref(),)
    assert all(fact.provenance == "authorized_observation" for fact in brief.all_facts())
    assert all(fact.basis_artifact_ids == (profile_artifact.artifact_id,) for fact in brief.all_facts())
    assert "你以自己的第一人称" not in {fact.statement for fact in brief.all_facts()}


def test_user_business_brief_does_not_gain_host_product_capabilities() -> None:
    subject = _subject("我是做水果产地批发的")

    brief_artifact = build_subject_incubation_brief(
        project=PROJECT,
        logical_account=ACCOUNT,
        subject=subject,
        source_object="水果产地批发",
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-1",
    )
    brief = IncubationBrief.model_validate(brief_artifact.payload)

    assert [fact.statement for fact in brief.business_facts] == ["水果产地批发"]
    assert brief.capabilities == ()
    assert brief.resources == ()


@pytest.mark.asyncio
async def test_audience_decision_runs_before_content_map_and_sees_product_truth() -> None:
    captured: dict[str, object] = {}

    async def structured_model(schema, messages):
        captured["schema"] = schema
        captured["messages"] = messages
        return {
            "route_options": [
                _route(
                    "business_operators",
                    name="经营者操盘",
                    target_people="需要把业务转成内容账号的经营者",
                    content_audience="关心账号定位、选题和真实操盘过程的经营者",
                ).model_dump(mode="json")
            ],
            "recommended_option_id": "business_operators",
            "material_choice_required": False,
            "choice_reason": "产品事实已明确首要服务对象。",
            "unknowns": [],
        }

    decision = await generate_account_audience_decision(
        subject=MarketingSubjectSnapshot(
            subject_kind="agent_self",
            subject_expression="DeerFlow 内容孵化与新媒体运营 Agent",
            source_user_request="你给自己起号",
            business_facts=("这是一个内容孵化 Agent。",),
            capabilities=("能生成账号策略和具体可拍选题。",),
            constraints=("不能保证结果。",),
        ),
        structured_model=structured_model,
    )

    assert decision.decision_status == "resolved"
    messages = captured["messages"]
    assert "先于内容根、内容地图" in messages[0].content
    assert "candidate_content_map" not in messages[1].content
    assert "能生成账号策略和具体可拍选题" in messages[1].content
    assert captured["schema"] is AccountAudienceProposalDraft


@pytest.mark.asyncio
async def test_audience_reads_term_evidence_as_external_context_not_user_fact() -> None:
    captured: dict[str, object] = {}

    async def structured_model(schema, messages):
        captured["messages"] = messages
        return AccountAudienceProposalDraft(
            route_options=(
                _route(
                    "guild_clients",
                    name="直播公会客户",
                    target_people="目标地区的主播与直播团队",
                    content_audience="关心直播公会合作与运营的人",
                ),
            ),
            recommended_option_id="guild_clients",
            material_choice_required=False,
            choice_reason="词项证据只解释业务表达，目标人群仍是可修正假设。",
        )

    subject = MarketingSubjectSnapshot(
        subject_kind="user_business",
        subject_expression="MENA TikTok直播公会",
        source_user_request="我是做MENA TikTok直播公会的",
        business_facts=("我是做MENA TikTok直播公会的",),
        term_evidence=(
            SubjectTermEvidence(
                title="MENA 词项说明",
                uri="https://example.com/mena",
                content="MENA 是中东和北非地区的常用缩写。",
            ),
        ),
    )

    await generate_account_audience_decision(
        subject=subject,
        structured_model=structured_model,
    )

    system_prompt = captured["messages"][0].content
    user_input = captured["messages"][1].content
    assert "term_evidence" in system_prompt
    assert "不是用户事实、对标账号、市场表现或选题证据" in system_prompt
    assert '"evidence_role":"term_evidence"' in user_input
    assert "MENA 是中东和北非地区" in user_input


@pytest.mark.asyncio
async def test_prepare_account_audience_stores_a_proposal_before_any_downstream_work() -> None:
    repository = SimpleNamespace(
        list_artifacts=AsyncMock(return_value=[]),
        put_artifact=AsyncMock(side_effect=lambda artifact: artifact),
    )

    async def structured_model(schema, messages):
        del schema, messages
        return AccountAudienceProposalDraft(
            route_options=(
                _route(
                    "b2b_wholesale",
                    name="产地批发",
                    target_people="批发商、零售商、餐饮采购者",
                    content_audience="需要判断货源、行情和品质的经营者",
                ),
                _route(
                    "b2c_retail",
                    name="终端零售",
                    target_people="家庭消费者和到店顾客",
                    content_audience="关心水果口感、吃法和选择的消费者",
                ),
            ),
            recommended_option_id="b2b_wholesale",
            material_choice_required=True,
            choice_reason="批发和零售会改变整套账号策略。",
        )

    prepared = await prepare_account_audience(
        project=PROJECT,
        logical_account=ACCOUNT,
        repository=repository,
        subject=_subject(),
        structured_model=structured_model,
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-1",
    )

    assert prepared.decision.decision_status == "proposed"
    assert prepared.reused is False
    repository.put_artifact.assert_awaited_once()
    assert repository.put_artifact.await_args.args[0].artifact_type == "account_audience_decision"


@pytest.mark.asyncio
async def test_prepare_account_audience_confirms_the_exact_pending_route() -> None:
    draft = AccountAudienceProposalDraft(
        route_options=(
            _route(
                "b2b_wholesale",
                name="产地批发",
                target_people="批发商、零售商、餐饮采购者",
                content_audience="需要判断货源、行情和品质的经营者",
            ),
            _route(
                "b2c_retail",
                name="终端零售",
                target_people="家庭消费者和到店顾客",
                content_audience="关心水果口感、吃法和选择的消费者",
            ),
        ),
        recommended_option_id="b2b_wholesale",
        material_choice_required=True,
        choice_reason="批发和零售会改变整套账号策略。",
    )
    proposal = compile_account_audience_decision(subject=_subject(), draft=draft)
    proposal_artifact = seal_account_audience_decision(
        project=PROJECT,
        logical_account=ACCOUNT,
        decision=proposal,
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-1",
    )
    repository = SimpleNamespace(
        list_artifacts=AsyncMock(return_value=[proposal_artifact]),
        put_artifact=AsyncMock(side_effect=lambda artifact: artifact),
    )

    prepared = await prepare_account_audience(
        project=PROJECT,
        logical_account=ACCOUNT,
        repository=repository,
        subject=None,
        structured_model=None,
        option_id="b2c_retail",
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-2",
    )

    assert prepared.decision.decision_status == "confirmed"
    assert prepared.decision.selected_option_id == "b2c_retail"
    repository.put_artifact.assert_awaited_once()


@pytest.mark.asyncio
async def test_repeated_account_audience_confirmation_reuses_the_same_decision() -> None:
    draft = AccountAudienceProposalDraft(
        route_options=(
            _route(
                "b2b_wholesale",
                name="产地批发",
                target_people="批发商、零售商、餐饮采购者",
                content_audience="需要判断货源、行情和品质的经营者",
            ),
            _route(
                "b2c_retail",
                name="终端零售",
                target_people="家庭消费者和到店顾客",
                content_audience="关心水果口感、吃法和选择的消费者",
            ),
        ),
        recommended_option_id="b2b_wholesale",
        material_choice_required=True,
        choice_reason="批发和零售会改变整套账号策略。",
    )
    proposal_artifact = seal_account_audience_decision(
        project=PROJECT,
        logical_account=ACCOUNT,
        decision=compile_account_audience_decision(subject=_subject(), draft=draft),
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-1",
    )
    confirmed_artifact = confirm_account_audience_decision(
        proposed_artifact=proposal_artifact,
        option_id="b2c_retail",
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-2",
    )
    repository = SimpleNamespace(
        list_artifacts=AsyncMock(return_value=[proposal_artifact, confirmed_artifact]),
        put_artifact=AsyncMock(side_effect=lambda artifact: artifact),
    )

    prepared = await prepare_account_audience(
        project=PROJECT,
        logical_account=ACCOUNT,
        repository=repository,
        subject=None,
        structured_model=None,
        option_id="b2c_retail",
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-3",
    )

    assert prepared.decision.decision_status == "confirmed"
    assert prepared.decision.selected_option_id == "b2c_retail"
    assert prepared.reused is True
    repository.put_artifact.assert_not_awaited()


@pytest.mark.asyncio
async def test_audience_confirmation_rejects_subject_mismatch_before_writing() -> None:
    draft = AccountAudienceProposalDraft(
        route_options=(
            _route(
                "b2b_wholesale",
                name="产地批发",
                target_people="批发商、零售商、餐饮采购者",
                content_audience="需要判断货源、行情和品质的经营者",
            ),
            _route(
                "b2c_retail",
                name="终端零售",
                target_people="家庭消费者和到店顾客",
                content_audience="关心水果口感、吃法和选择的消费者",
            ),
        ),
        recommended_option_id="b2b_wholesale",
        material_choice_required=True,
        choice_reason="批发和零售会改变整套账号策略。",
    )
    proposal = compile_account_audience_decision(subject=_subject(), draft=draft)
    proposal_artifact = seal_account_audience_decision(
        project=PROJECT,
        logical_account=ACCOUNT,
        decision=proposal,
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-1",
    )
    repository = SimpleNamespace(
        list_artifacts=AsyncMock(return_value=[proposal_artifact]),
        put_artifact=AsyncMock(side_effect=lambda artifact: artifact),
    )

    with pytest.raises(ValueError, match="different marketing subject"):
        await prepare_account_audience(
            project=PROJECT,
            logical_account=ACCOUNT,
            repository=repository,
            subject=None,
            structured_model=None,
            option_id="b2c_retail",
            expected_subject_kind="agent_self",
            created_at=NOW,
            source_thread_id="thread-1",
            source_run_id="run-2",
        )

    repository.put_artifact.assert_not_awaited()


def test_selected_audience_guides_root_selection_and_map_but_not_literal_subject() -> None:
    context = ContentAudienceContext(
        business_role="水果产地批发商",
        payer_or_contracting_party="水果批发商和零售商",
        decision_makers="采购负责人或店主",
        users_or_beneficiaries="下游经营者及其顾客",
        target_people="需要稳定货源的水果经营者",
        target_need="判断产地、品质、行情和供货稳定性",
        desired_action="询价并建立采购关系",
        market_scope="中国区域市场，具体地区未知",
        content_audience="关心水果经营、货源和行情的人",
        recurring_interest="产区变化、品种、品质判断、行情和经营决策",
    )
    request = ContentIntelligenceRequest(
        user_request="我是做水果产地批发的，我要怎么起号",
        subject_expression="水果产地批发",
        audience_context=context,
    )
    candidate = RootCandidateDraft(
        level="commercial_object",
        label="水果",
        scope_role="root_candidate",
        relation_to_business="用户经营的完整商品世界",
        strength="能够长期展开",
        overreach_risk="仍需结合受众判断边界",
    )
    candidates = ContentRootCandidateSetDraft(
        source_object="水果产地批发",
        candidates=(candidate,),
    )
    selected = ContentRootSelectionDraft(
        source_object="水果产地批发",
        candidates=(candidate,),
        selected_candidate_index=0,
        root_rationale="水果是可长期展开的内容世界。",
    )

    root_input = _render_root_decision_input(
        candidates,
        offering_role="complete_object_or_service",
        audience_context=request.audience_context,
    )
    map_input = _render_frozen_map_input(
        selected,
        audience_context=request.audience_context,
    )

    assert "需要稳定货源的水果经营者" in root_input
    assert "产区变化、品种、品质判断、行情和经营决策" in map_input
    assert request.subject_expression == "水果产地批发"
