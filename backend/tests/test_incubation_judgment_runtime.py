from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import pytest

from deerflow.incubation import generate_incubation_judgment as exported_generate_incubation_judgment
from deerflow.incubation.account_audience import (
    AccountAudienceProposalDraft,
    AccountAudienceRouteDraft,
    compile_account_audience_decision,
    seal_account_audience_decision,
)
from deerflow.incubation.benchmark import (
    BenchmarkCoverageReceipt,
    BenchmarkPostObservation,
    BenchmarkProfileObservation,
    BenchmarkRouteReceipt,
    BenchmarkSnapshot,
    seal_benchmark_snapshot,
)
from deerflow.incubation.brief_runtime import build_subject_incubation_brief
from deerflow.incubation.contracts import ArtifactEnvelope, LogicalAccountRef, ProjectRef
from deerflow.incubation.evidence import (
    EvidenceCoverageReceipt,
    EvidenceItem,
    EvidenceSnapshot,
    seal_evidence_snapshot,
)
from deerflow.incubation.host_product_profile import (
    build_agent_self_subject,
    current_host_product_profile,
    seal_host_product_profile,
)
from deerflow.incubation.judgment import (
    IncubationBrief,
    seal_incubation_brief,
)
from deerflow.incubation.judgment_runtime import (
    INCUBATION_JUDGMENT_SYSTEM_PROMPT,
    MAX_JUDGMENT_MODEL_INPUT_BYTES,
    AccountStrategyProposalDraft,
    IncubationJudgmentModelError,
    generate_incubation_judgment,
)

NOW = datetime(2026, 8, 17, 20, 0, tzinfo=UTC)
PROJECT = ProjectRef(owner_user_id="user-1", project_id="golden-gift")


def test_judgment_runtime_is_exported_from_the_incubation_package() -> None:
    assert exported_generate_incubation_judgment is generate_incubation_judgment


def _brief_artifact(
    *,
    project: ProjectRef = PROJECT,
    prohibited_assumptions: tuple[str, ...] = (),
) -> ArtifactEnvelope:
    return seal_incubation_brief(
        project=project,
        brief=IncubationBrief(
            subject_expression="我是做黄金礼品的，我要怎么起号？",
            prohibited_assumptions=prohibited_assumptions,
            unknowns=("尚不知道用户是否愿意出镜。",),
        ),
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-1",
    )


def _content_world_artifact(*, project: ProjectRef = PROJECT) -> ArtifactEnvelope:
    return ArtifactEnvelope.seal(
        project=project,
        artifact_type="content_map_candidate",
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


def _evidence_artifact(
    *,
    artifact_type: str,
    evidence_role: str,
    project: ProjectRef = PROJECT,
    item_count: int = 1,
    excerpt: str = "一份有界证据摘要。",
) -> ArtifactEnvelope:
    if artifact_type == "benchmark_snapshot":
        account_id = "benchmark-account-1"
        snapshot = BenchmarkSnapshot(
            provider="douyin-openapi",
            collection_method="authorized-public-search",
            captured_at=NOW,
            rights_basis="public-account-research",
            requested_url="https://www.douyin.com/user/benchmark-account-1",
            profile=BenchmarkProfileObservation(
                platform="douyin",
                external_account_id=account_id,
                canonical_url="https://www.douyin.com/user/benchmark-account-1",
                display_name="对标账号",
                captured_at=NOW,
            ),
            posts=tuple(
                BenchmarkPostObservation(
                    platform="douyin",
                    external_post_id=f"post-{index}",
                    author_external_account_id=account_id,
                    canonical_url=f"https://www.douyin.com/video/{index}",
                    caption=excerpt,
                    captured_at=NOW,
                )
                for index in range(item_count)
            ),
            coverage=BenchmarkCoverageReceipt(
                population_scope="public account posts",
                requested_count=item_count,
                returned_count=item_count,
                sample_basis="bounded recent public sample",
                limitations=("不能代表账号全部历史。",),
            ),
            route_receipt=BenchmarkRouteReceipt(
                adapter="douyin-openapi",
                capability_version="v2",
            ),
            limitations=("不能直接证明账号定位、受众或成功原因。",),
        )
        return seal_benchmark_snapshot(
            project=project,
            snapshot=snapshot,
            source_thread_id="thread-1",
            source_run_id="run-1",
        )

    snapshot = EvidenceSnapshot(
        provider="authorized-audience-source",
        collection_method="bounded-observation",
        evidence_role=evidence_role,
        captured_at=NOW,
        rights_basis="account-owner-authorization",
        items=tuple(
            EvidenceItem(
                source_ref=f"audience-{index}",
                source_type="audience_observation",
                title=f"受众观察 {index}",
                excerpt=excerpt,
                provenance="observed",
            )
            for index in range(item_count)
        ),
        coverage=EvidenceCoverageReceipt(
            population_scope="authorized audience sample",
            requested_count=item_count,
            returned_count=item_count,
            limitations=("不能代表全部受众。",),
        ),
        limitations=("不能代表全部受众。",),
    )
    return seal_evidence_snapshot(
        project=project,
        snapshot=snapshot,
        source_thread_id="thread-1",
        source_run_id="run-1",
    )


def _judgment_payload(*, basis_ids: tuple[str, ...]) -> dict[str, Any]:
    def route(option_id: str, name: str, form: str) -> dict[str, Any]:
        return {
            "option_id": option_id,
            "name": name,
            "content_subject": f"{name}视角下的人情、礼节和关系判断",
            "business_connection": "礼品从业位置提供观察角度，不把产品当成内容主体。",
            "long_term_promise": "每次借一件具体人情事件讲清人怎样相处。",
            "audience_people": "关心人情、礼节和关系判断的人",
            "recurring_interest": "具体关系如何被安排",
            "account_role": "从礼品生意观察人情的从业者",
            "primary_forms": [form],
            "supporting_forms": [],
            "monetization_path": "先建立长期内容信任，再承接用户已有的礼品服务。",
            "monetization_trust_required": "观众先确认账号懂礼与关系。",
            "rationale": "与已冻结的内容根一致。",
            "confidence": "low",
            "unknowns": ["仍需真实反馈校正。"],
            "resource_requirements": [f"持续生产{form}所需素材"],
            "tradeoffs": [f"{form}的成本待确认"],
        }

    return {
        "content_map_version_id": "map-gift-relations-v1",
        "business_intent": {
            "business_role": "提供黄金礼品解决方案的从业者",
            "account_objective": "建立懂送礼与人情分寸的信任，并承接真实礼品需求",
            "target_people": "正在为具体关系和场合选择礼物的人",
            "target_need": "判断送什么、怎么送才合适且不失分寸",
            "desired_action": "在出现礼品需求时主动咨询用户已有的黄金礼品业务",
            "market_scope": "用户未说明经营地区，首版保留为未知",
            "rationale": "来自用户业务原话，经营地区仍未知。",
            "confidence": "low",
            "unknowns": ["经营地区未知。"],
        },
        "route_options": [
            route("route_a", "真人故事", "真人出镜口述"),
            route("route_b", "无人素材", "无人素材旁白"),
        ],
        "recommended_option_id": "route_a",
        "basis_artifact_ids": list(basis_ids),
        "unknowns": ["尚无真实受众反馈。"],
    }


@pytest.mark.asyncio
async def test_runtime_binds_exact_brief_world_and_optional_evidence_parents() -> None:
    prohibited_assumption = "用户的业务身份不能证明其拥有行业经验或客户案例"
    brief = _brief_artifact(prohibited_assumptions=(prohibited_assumption,))
    world = _content_world_artifact()
    benchmark = _evidence_artifact(
        artifact_type="benchmark_snapshot",
        evidence_role="benchmark_evidence",
    )
    audience = _evidence_artifact(
        artifact_type="evidence_snapshot",
        evidence_role="owned_audience_observation",
    )
    seen: dict[str, object] = {}

    async def structured_model(schema, messages):
        seen["schema"] = schema
        seen["messages"] = messages
        return _judgment_payload(basis_ids=(brief.artifact_id, world.artifact_id, benchmark.artifact_id, audience.artifact_id))

    sealed = await generate_incubation_judgment(
        project=PROJECT,
        brief_artifact=brief,
        content_world_artifact=world,
        structured_model=structured_model,
        benchmark_evidence_artifacts=(benchmark,),
        audience_evidence_artifacts=(audience,),
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-2",
    )

    assert seen["schema"] is AccountStrategyProposalDraft
    assert sealed.artifact_type == "incubation_judgment"
    assert set(sealed.parents) == {
        brief.to_parent_ref(),
        world.to_parent_ref(),
        benchmark.to_parent_ref(),
        audience.to_parent_ref(),
    }
    assert sealed.payload["content_map_version_id"] == "map-gift-relations-v1"

    messages = seen["messages"]
    assert isinstance(messages, tuple)
    prompt_input = messages[1].content
    assert brief.artifact_id in prompt_input
    assert world.artifact_id in prompt_input
    assert benchmark.artifact_id in prompt_input
    assert audience.artifact_id in prompt_input
    model_input = json.loads(prompt_input)
    assert model_input["user_fact_boundary"] == {
        "allowed_user_fact_statements": [],
        "confirmed_capabilities": [],
        "confirmed_resources": [],
        "prohibited_assumptions": [prohibited_assumption],
    }
    assert "content_branch_boundary" not in model_input


@pytest.mark.asyncio
async def test_runtime_allows_a_local_branch_as_supporting_context() -> None:
    brief = _brief_artifact()
    world = _content_world_artifact()
    payload = _judgment_payload(basis_ids=(brief.artifact_id, world.artifact_id))
    payload["route_options"][0]["content_subject"] = "从婚礼伴手礼等局部馈赠场景观察人情、礼节和关系判断"

    async def structured_model(schema, messages):
        model_input = json.loads(messages[1].content)
        assert "content_branch_boundary" not in model_input
        return payload

    sealed = await generate_incubation_judgment(
        project=PROJECT,
        brief_artifact=brief,
        content_world_artifact=world,
        structured_model=structured_model,
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-2",
    )

    assert sealed.payload["business_intent"]["target_people"] == "正在为具体关系和场合选择礼物的人"
    assert sealed.payload["route_options"][0]["positioning"]["decision"] == "从婚礼伴手礼等局部馈赠场景观察人情、礼节和关系判断"


@pytest.mark.asyncio
async def test_runtime_uses_bounded_evidence_projection_instead_of_full_snapshot() -> None:
    brief = _brief_artifact()
    world = _content_world_artifact()
    audience = _evidence_artifact(
        artifact_type="evidence_snapshot",
        evidence_role="owned_audience_observation",
        item_count=20,
        excerpt="受众原始观察" * 300,
    )
    seen_input = ""

    async def structured_model(schema, messages):
        nonlocal seen_input
        seen_input = messages[1].content
        return _judgment_payload(basis_ids=(brief.artifact_id, world.artifact_id, audience.artifact_id))

    await generate_incubation_judgment(
        project=PROJECT,
        brief_artifact=brief,
        content_world_artifact=world,
        structured_model=structured_model,
        audience_evidence_artifacts=(audience,),
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-2",
    )

    model_input = json.loads(seen_input)
    projection = model_input["audience_evidence"][0]["projection"]
    assert len(seen_input.encode("utf-8")) <= MAX_JUDGMENT_MODEL_INPUT_BYTES
    assert projection["projection"]["total_items"] == 20
    assert projection["projection"]["omitted_items"] > 0
    assert "payload" not in model_input["audience_evidence"][0]


@pytest.mark.asyncio
async def test_agent_self_product_truth_and_benchmark_fit_the_strategy_input_budget() -> None:
    """The real host profile must leave room for bounded benchmark evidence."""

    logical_account = LogicalAccountRef(
        owner_user_id=PROJECT.owner_user_id,
        project_id=PROJECT.project_id,
        logical_account_id="agent-self-account",
    )
    profile = seal_host_product_profile(
        project=PROJECT,
        logical_account=logical_account,
        profile=current_host_product_profile(),
        created_at=NOW,
        source_thread_id="thread-agent-self",
        source_run_id="run-agent-self",
    )
    subject = build_agent_self_subject(
        user_request="现在，我要你自己卖你自己，你要怎么起号？",
        profile_artifact=profile,
    )
    brief = build_subject_incubation_brief(
        project=PROJECT,
        logical_account=logical_account,
        subject=subject,
        source_object=subject.subject_expression,
        parent_artifacts=(profile,),
        created_at=NOW,
        source_thread_id="thread-agent-self",
        source_run_id="run-agent-self",
    )
    audience_decision = compile_account_audience_decision(
        subject=subject,
        draft=AccountAudienceProposalDraft(
            route_options=(
                AccountAudienceRouteDraft(
                    option_id="agent_operators",
                    name="公开操盘",
                    business_role="内容孵化与新媒体运营 Agent 产品",
                    market_relationship="为需要经营内容账号的个人与团队提供判断支持",
                    account_objective="让目标用户通过真实操盘理解产品能力和边界",
                    payer_or_contracting_party="尚未确认",
                    decision_makers="需要账号孵化支持的经营者或运营负责人",
                    users_or_beneficiaries="实际使用该 Agent 的个人与团队",
                    target_people="需要把业务转成可持续内容账号的人",
                    target_need="看清账号应该影响谁、长期讲什么和第一条拍什么",
                    desired_action="持续观察真实操盘，并在有需要时采用产品",
                    market_scope="尚未限定地区和平台",
                    content_audience="关心账号孵化方法和真实操盘过程的人",
                    recurring_interest="Agent 能做什么、做到什么程度以及边界在哪里",
                    rationale="来自版本化产品事实档案",
                    confidence="medium",
                ),
            ),
            recommended_option_id="agent_operators",
            material_choice_required=False,
            choice_reason="当前请求明确要求 Agent 营销自身。",
        ),
    )
    audience = seal_account_audience_decision(
        project=PROJECT,
        logical_account=logical_account,
        decision=audience_decision,
        parent_artifacts=(profile,),
        created_at=NOW,
        source_thread_id="thread-agent-self",
        source_run_id="run-agent-self",
    )
    world = ArtifactEnvelope.seal(
        project=PROJECT,
        artifact_type="content_map_candidate",
        version=1,
        payload={
            "content_map_version_id": "map-agent-work-v1",
            "content_root": "软件代理替人完成营销工作",
            "editorial_promise": "用真实任务展示 Agent 能做什么以及不能做什么。",
            "recurring_lens": "从一次真实业务请求进入。",
            "drift_boundaries": ["不把未验收能力说成已经可用。"],
        },
        logical_account=logical_account,
        created_at=NOW,
        source_thread_id="thread-agent-self",
        source_run_id="run-agent-self",
    )
    benchmark = _evidence_artifact(
        artifact_type="benchmark_snapshot",
        evidence_role="benchmark_evidence",
        item_count=6,
        excerpt="用真实案例解释 AI 产品如何解决具体工作问题。" * 12,
    )
    seen_input = ""

    async def structured_model(schema, messages):
        nonlocal seen_input
        seen_input = messages[1].content
        payload = _judgment_payload(
            basis_ids=(
                brief.artifact_id,
                world.artifact_id,
                audience.artifact_id,
                benchmark.artifact_id,
            )
        )
        payload["content_map_version_id"] = "map-agent-work-v1"
        return payload

    await generate_incubation_judgment(
        project=PROJECT,
        logical_account=logical_account,
        brief_artifact=brief,
        content_world_artifact=world,
        audience_decision_artifact=audience,
        benchmark_evidence_artifacts=(benchmark,),
        structured_model=structured_model,
        created_at=NOW,
        source_thread_id="thread-agent-self",
        source_run_id="run-agent-self",
    )

    model_input = json.loads(seen_input)
    assert len(seen_input.encode("utf-8")) <= MAX_JUDGMENT_MODEL_INPUT_BYTES
    assert model_input["incubation_brief"]["payload"]["subject_expression"] == subject.subject_expression
    assert model_input["incubation_brief"]["payload"]["capabilities"] == list(subject.capabilities)
    assert model_input["benchmark_evidence"][0]["projection"]["projection"]["included_posts"] >= 1


@pytest.mark.asyncio
async def test_runtime_rejects_an_evidence_role_wrapped_in_the_wrong_artifact_type() -> None:
    wrong_type = ArtifactEnvelope.seal(
        project=PROJECT,
        artifact_type="generic_report",
        version=1,
        payload={"summary": "not a BenchmarkSnapshot"},
        evidence_role="benchmark_evidence",
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-1",
    )

    async def structured_model(schema, messages):
        raise AssertionError("model must not run")

    with pytest.raises(ValueError, match="benchmark_snapshot"):
        await generate_incubation_judgment(
            project=PROJECT,
            brief_artifact=_brief_artifact(),
            content_world_artifact=_content_world_artifact(),
            structured_model=structured_model,
            benchmark_evidence_artifacts=(wrong_type,),
            created_at=NOW,
            source_thread_id="thread-1",
            source_run_id="run-2",
        )


@pytest.mark.asyncio
async def test_runtime_rejects_cross_project_parent_before_calling_model() -> None:
    other_project = ProjectRef(owner_user_id="user-2", project_id="golden-gift")
    called = False

    async def structured_model(schema, messages):
        nonlocal called
        called = True
        return _judgment_payload(basis_ids=())

    with pytest.raises(ValueError, match="brief parent project"):
        await generate_incubation_judgment(
            project=PROJECT,
            brief_artifact=_brief_artifact(project=other_project),
            content_world_artifact=_content_world_artifact(),
            structured_model=structured_model,
            created_at=NOW,
            source_thread_id="thread-1",
            source_run_id="run-2",
        )

    assert called is False


@pytest.mark.asyncio
async def test_runtime_surfaces_structured_model_failure_without_sealing() -> None:
    provider_error = RuntimeError("provider unavailable")

    async def failing_model(schema, messages):
        raise provider_error

    with pytest.raises(IncubationJudgmentModelError, match="structured model") as exc_info:
        await generate_incubation_judgment(
            project=PROJECT,
            brief_artifact=_brief_artifact(),
            content_world_artifact=_content_world_artifact(),
            structured_model=failing_model,
            created_at=NOW,
            source_thread_id="thread-1",
            source_run_id="run-2",
        )

    assert exc_info.value.__cause__ is provider_error


@pytest.mark.asyncio
async def test_runtime_exposes_only_safe_contract_locations_for_nested_model_errors() -> None:
    async def invalid_model(schema, messages):
        try:
            schema.model_validate({"private_payload": "must-never-enter-logs"})
        except Exception as validation_error:
            raise ValueError("structured model output could not be parsed") from validation_error

    with pytest.raises(IncubationJudgmentModelError) as exc_info:
        await generate_incubation_judgment(
            project=PROJECT,
            brief_artifact=_brief_artifact(),
            content_world_artifact=_content_world_artifact(),
            structured_model=invalid_model,
            created_at=NOW,
            source_thread_id="thread-1",
            source_run_id="run-2",
        )

    error = exc_info.value
    assert error.stage == "model_output"
    assert any("business_intent" in item for item in error.diagnostics)
    assert "must-never-enter-logs" not in " ".join(error.diagnostics)


@pytest.mark.asyncio
async def test_runtime_rejects_an_unknown_only_result_instead_of_hiding_missing_routes() -> None:
    async def unknown_only_model(schema, messages):
        return {
            "content_map_version_id": "map-gift-relations-v1",
            "unknowns": ["用户可持续投入的出镜与制作资源仍未知。"],
            "alternatives": ["待资源确认后再在口述与图文之间判断。"],
        }

    with pytest.raises(IncubationJudgmentModelError, match="invalid incubation judgment"):
        await generate_incubation_judgment(
            project=PROJECT,
            brief_artifact=_brief_artifact(),
            content_world_artifact=_content_world_artifact(),
            structured_model=unknown_only_model,
            created_at=NOW,
            source_thread_id="thread-1",
            source_run_id="run-2",
        )


@pytest.mark.asyncio
async def test_monetization_stays_in_judgment_and_cannot_rewrite_content_map() -> None:
    brief = _brief_artifact()
    world = _content_world_artifact()
    frozen_world = world.model_dump(mode="json")

    async def monetization_model(schema, messages):
        assert "变现路径不属于内容地图" in messages[0].content
        return _judgment_payload(basis_ids=(brief.artifact_id, world.artifact_id))

    sealed = await generate_incubation_judgment(
        project=PROJECT,
        brief_artifact=brief,
        content_world_artifact=world,
        structured_model=monetization_model,
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-2",
    )

    assert world.model_dump(mode="json") == frozen_world
    assert "monetization" not in world.payload
    assert sealed.payload["monetization"][0]["path"].startswith("先建立")
    assert "不要求固定模板" in INCUBATION_JUDGMENT_SYSTEM_PROMPT
    assert "不要求数字配额" in INCUBATION_JUDGMENT_SYSTEM_PROMPT
    assert "不要求实验" in INCUBATION_JUDGMENT_SYSTEM_PROMPT
    assert "业务身份不等于资源所有权" in INCUBATION_JUDGMENT_SYSTEM_PROMPT
    assert "user_fact_boundary" in INCUBATION_JUDGMENT_SYSTEM_PROMPT
    assert "不得在 business_connection、account_role、rationale" in INCUBATION_JUDGMENT_SYSTEM_PROMPT
    assert "不得把经营身份写成天然的判断力" in INCUBATION_JUDGMENT_SYSTEM_PROMPT
    assert "先断言再补未确认仍然属于编造" in INCUBATION_JUDGMENT_SYSTEM_PROMPT
    assert "已知资源" in INCUBATION_JUDGMENT_SYSTEM_PROMPT
    assert "resource_requirements" in INCUBATION_JUDGMENT_SYSTEM_PROMPT
