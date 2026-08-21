from __future__ import annotations

import pytest
from pydantic import ValidationError

from deerflow.content_intelligence import (
    AnalysisFocus,
    BasisRef,
    BusinessSemanticView,
    ComprehensionRecord,
    ContentIntelligenceBundle,
    ContentPath,
    ContentPathStep,
    ContentRootCandidate,
    ContentWorldView,
    GroundedStatement,
    Interpretation,
    ModifierReading,
    NamedCandidate,
    NarrativeFrame,
    Observation,
    SourceItem,
    TopicBrief,
    Unknown,
)
from deerflow.tools.builtins.content_intelligence_tool import _lead_projection


def _source(content: str = "我是做重庆火锅底料的") -> SourceItem:
    return SourceItem(
        source_id="source-user-1",
        kind="user_statement",
        content=content,
    )


@pytest.mark.parametrize(
    "evidence_role",
    (
        "benchmark_account_candidate",
        "benchmark_evidence",
        "benchmark_audience_observation",
    ),
)
def test_content_intelligence_source_rejects_benchmark_evidence_roles(
    evidence_role: str,
) -> None:
    with pytest.raises(ValidationError, match="evidence_role"):
        SourceItem(
            source_id="source-wrong-role",
            kind="external_evidence",
            content="这是对标账号观察，不得冒充内容地图资料。",
            evidence_role=evidence_role,
        )


@pytest.mark.parametrize("evidence_role", ("user_material", "term_evidence", "topic_evidence"))
def test_content_intelligence_source_accepts_only_its_owned_evidence_roles(
    evidence_role: str,
) -> None:
    source = SourceItem(
        source_id=f"source-{evidence_role}",
        kind="external_evidence",
        content="内容理解自己拥有的资料。",
        evidence_role=evidence_role,
    )

    assert source.evidence_role == evidence_role


def _record() -> ComprehensionRecord:
    return ComprehensionRecord(
        record_id="record-1",
        subject_expression="我是做重庆火锅底料的",
        sources=(_source(),),
        observations=(
            Observation(
                observation_id="observation-1",
                claim="用户说自己经营重庆火锅底料",
                source_refs=("source-user-1",),
            ),
        ),
        interpretations=(
            Interpretation(
                interpretation_id="interpretation-1",
                claim="火锅底料是商业对象，火锅可作为待验证的更大内容世界",
                kind="derived",
                basis_refs=(BasisRef(kind="observation", ref_id="observation-1"),),
                limitations=("仅凭这句话不能确定用户的资源、受众或表现能力",),
            ),
        ),
        unknowns=(
            Unknown(
                unknown_id="unknown-1",
                question="用户现有的产品、供应链和内容资源是什么？",
                affects=("account_positioning",),
            ),
        ),
    )


def test_record_keeps_observations_interpretations_and_unknowns_separate() -> None:
    record = _record()

    assert record.observations[0].claim.startswith("用户说")
    assert record.interpretations[0].kind == "derived"
    assert record.interpretations[0].basis_refs == (BasisRef(kind="observation", ref_id="observation-1"),)
    assert record.unknowns[0].question.endswith("？")


def test_record_allows_incomplete_information_without_a_semantic_gate() -> None:
    record = ComprehensionRecord(
        record_id="record-minimal",
        subject_expression="我是做服务的",
        sources=(_source("我是做服务的"),),
    )

    assert record.observations == ()
    assert record.interpretations == ()
    assert record.unknowns == ()


def test_record_rejects_an_observation_with_an_unknown_source() -> None:
    with pytest.raises(ValidationError, match="unknown source"):
        ComprehensionRecord(
            record_id="record-bad-source",
            subject_expression="我是做服务的",
            sources=(_source("我是做服务的"),),
            observations=(
                Observation(
                    observation_id="observation-bad",
                    claim="一条无法追溯的观察",
                    source_refs=("source-missing",),
                ),
            ),
        )


def test_observed_items_cannot_hide_an_empty_source_boundary() -> None:
    with pytest.raises(ValidationError, match="at least 1 item"):
        Observation(
            observation_id="observation-unsourced",
            claim="一条伪装成观察的猜测",
            source_refs=(),
        )


def test_grounded_projection_statement_requires_a_basis_reference() -> None:
    with pytest.raises(ValidationError, match="at least 1 item"):
        GroundedStatement(
            text="一个没有依据的商业对象",
            basis_refs=(),
        )


def test_derived_interpretation_requires_support() -> None:
    with pytest.raises(ValidationError, match="derived interpretation"):
        Interpretation(
            interpretation_id="interpretation-unsupported",
            claim="这是一条没有依据的派生解释",
            kind="derived",
            limitations=("需要更多证据",),
        )


def test_unsourced_hypothesis_is_allowed_only_when_its_limit_is_visible() -> None:
    hypothesis = Interpretation(
        interpretation_id="interpretation-hypothesis",
        claim="某个更大的内容世界可能成立",
        kind="hypothesis",
        limitations=("尚未取得外部证据",),
    )

    assert hypothesis.basis_refs == ()

    with pytest.raises(ValidationError, match="unsourced hypothesis"):
        Interpretation(
            interpretation_id="interpretation-hidden-risk",
            claim="某个更大的内容世界肯定成立",
            kind="hypothesis",
        )


def test_record_rejects_a_reference_that_lies_about_its_kind() -> None:
    with pytest.raises(ValidationError, match="reference kind"):
        ComprehensionRecord(
            record_id="record-bad-kind",
            subject_expression="我是做重庆火锅底料的",
            sources=(_source(),),
            observations=(
                Observation(
                    observation_id="observation-1",
                    claim="用户说自己经营重庆火锅底料",
                    source_refs=("source-user-1",),
                ),
            ),
            interpretations=(
                Interpretation(
                    interpretation_id="interpretation-bad-kind",
                    claim="把观察伪装成关系边来引用",
                    kind="derived",
                    basis_refs=(BasisRef(kind="relation", ref_id="observation-1"),),
                    limitations=("引用类型不真实",),
                ),
            ),
        )


def _bundle(record_id: str = "record-1") -> ContentIntelligenceBundle:
    business_semantics = BusinessSemanticView(
        record_id=record_id,
        commercial_object=GroundedStatement(
            text="重庆火锅底料",
            basis_refs=(BasisRef(kind="observation", ref_id="observation-1"),),
        ),
        lexical_head=GroundedStatement(
            text="底料",
            basis_refs=(BasisRef(kind="observation", ref_id="observation-1"),),
        ),
        modifiers=(
            ModifierReading(
                modifier="重庆火锅",
                modifies="底料",
                semantic_role="限定底料服务的饮食世界",
                removal_counterfactual="去掉修饰后只剩不完整的底料类别",
                basis_refs=(BasisRef(kind="interpretation", ref_id="interpretation-1"),),
            ),
        ),
        summary="这里只解释商业表达，不代替内容地图。",
    )
    content_path = ContentPath(
        path_id="path-1",
        steps=(
            ContentPathStep(
                from_label="火锅",
                relation="可以沿地域习惯研究",
                to_label="不同地方的人为什么形成不同火锅习惯",
                basis_refs=(BasisRef(kind="interpretation", ref_id="interpretation-1"),),
            ),
        ),
        rationale="这是从冻结内容根进入具体选题的地图路径。",
    )
    content_world = ContentWorldView(
        record_id=record_id,
        source_object="重庆火锅底料",
        content_root="火锅",
        root_rationale="火锅是待展开的内容世界，不是销售方案。",
        editorial_promise="借火锅理解各地共同饮食及其背后的人与生活。",
        recurring_lens="从具体地方、人物、事件和习惯进入，再解释它们与火锅的关系。",
        drift_boundaries=("与火锅没有可解释路径的热点不进入地图。",),
    )
    topic_brief = TopicBrief(
        record_id=record_id,
        content_map_version_id=content_world.content_map_version_id(),
        question="一条内容路径真正值得回答什么？",
        central_claim="选题必须从已理解的关系中长出来。",
        mechanism="使用记录中的观察和解释来限定命题。",
        counterpoint="当前没有外部证据，不能把命名案例写成事实。",
        path=content_path,
        evidence_refs=(BasisRef(kind="observation", ref_id="observation-1"),),
        unknown_refs=("unknown-1",),
    )
    return ContentIntelligenceBundle(
        record=_record(),
        business_semantics=business_semantics,
        content_world=content_world,
        topic_brief=topic_brief,
    )


def test_three_projections_share_one_record_without_becoming_one_stage() -> None:
    bundle = _bundle()

    assert bundle.business_semantics is not None
    assert bundle.business_semantics.commercial_object.text == "重庆火锅底料"
    assert bundle.content_world is not None
    assert bundle.content_world.content_root == "火锅"
    assert bundle.topic_brief is not None
    assert bundle.topic_brief.path.path_id == "path-1"
    assert bundle.topic_brief.content_map_version_id == bundle.content_world.content_map_version_id()


def test_topic_cannot_bind_to_a_different_content_map_version() -> None:
    bundle = _bundle()
    assert bundle.topic_brief is not None
    payload = bundle.model_dump(mode="json")
    payload["topic_brief"]["content_map_version_id"] = "content-map-wrong"

    with pytest.raises(ValueError, match="content map version"):
        ContentIntelligenceBundle.model_validate(payload)


def test_content_map_version_ignores_research_candidates_but_changes_with_positioning() -> None:
    bundle = _bundle()
    world = bundle.content_world
    assert world is not None

    research_enriched = world.model_copy(
        update={
            "named_candidates": (
                NamedCandidate(
                    name="一个后来核验的人物",
                    connection="它只是地图上的一个已取证入口。",
                    kind="grounded",
                    basis_refs=(BasisRef(kind="observation", ref_id="observation-1"),),
                ),
            )
        }
    )
    changed_lens = world.model_copy(update={"recurring_lens": "只介绍火锅产品和制作步骤。"})

    assert research_enriched.content_map_version_id() == world.content_map_version_id()
    assert changed_lens.content_map_version_id() != world.content_map_version_id()


def test_narrative_frame_must_resolve_every_claim_to_the_shared_record() -> None:
    bundle = _bundle()
    assert bundle.topic_brief is not None
    invalid_frame = NarrativeFrame(
        protagonist="一个人物",
        goal="完成一件具体的事",
        obstacle="一个真实阻碍",
        action_or_choice="采取一个行动",
        stakes_or_consequence="失败会产生代价",
        outcome_or_change="行动后发生变化",
        basis_refs=(BasisRef(kind="observation", ref_id="observation-missing"),),
    )

    with pytest.raises(ValidationError, match="unknown record item"):
        ContentIntelligenceBundle(
            record=bundle.record,
            business_semantics=bundle.business_semantics,
            content_world=bundle.content_world,
            topic_brief=bundle.topic_brief.model_copy(update={"narrative_frame": invalid_frame}),
        )


def test_lead_projection_exposes_an_optional_complete_narrative_frame() -> None:
    bundle = _bundle()
    assert bundle.topic_brief is not None
    frame = NarrativeFrame(
        protagonist="一个人物",
        goal="完成一件具体的事",
        obstacle="一个真实阻碍",
        action_or_choice="采取一个行动",
        stakes_or_consequence="失败会产生代价",
        outcome_or_change="行动后发生变化",
        basis_refs=(BasisRef(kind="observation", ref_id="observation-1"),),
        limitations=("当前只由一条记录支持。",),
    )
    bound = ContentIntelligenceBundle(
        record=bundle.record,
        business_semantics=bundle.business_semantics,
        content_world=bundle.content_world,
        topic_brief=bundle.topic_brief.model_copy(update={"narrative_frame": frame}),
    )

    payload = _lead_projection(bound)

    assert payload["topic_brief"]["narrative_frame"] == {
        "protagonist": "一个人物",
        "goal": "完成一件具体的事",
        "obstacle": "一个真实阻碍",
        "action_or_choice": "采取一个行动",
        "stakes_or_consequence": "失败会产生代价",
        "outcome_or_change": "行动后发生变化",
        "limitations": ["当前只由一条记录支持。"],
    }


def test_semantic_and_world_views_keep_the_attention_handoff_visible() -> None:
    record = _record()
    semantic_basis = (BasisRef(kind="interpretation", ref_id="interpretation-1"),)
    semantics = BusinessSemanticView(
        record_id=record.record_id,
        commercial_object=GroundedStatement(text="重庆火锅底料", basis_refs=semantic_basis),
        lexical_head=GroundedStatement(text="底料", basis_refs=semantic_basis),
        offering_role="intermediate_enabler",
        role_rationale="底料用于完成火锅，而不是终端餐饮对象。",
        served_objects=(GroundedStatement(text="火锅", basis_refs=semantic_basis),),
        served_activities=(GroundedStatement(text="制作火锅", basis_refs=semantic_basis),),
        defining_functions_or_uses=(GroundedStatement(text="形成火锅锅底风味", basis_refs=semantic_basis),),
        social_or_cultural_frames=(GroundedStatement(text="火锅饮食文化", basis_refs=semantic_basis),),
    )
    world = ContentWorldView(
        record_id=record.record_id,
        source_object="重庆火锅底料",
        audience_territory=GroundedStatement(text="火锅", basis_refs=semantic_basis),
        content_root="火锅",
        root_rationale="底料是火锅的中间实现物，火锅是更完整的对象世界。",
        root_candidates=(
            ContentRootCandidate(
                candidate_id="candidate-firepot",
                label="火锅",
                relation_to_business="底料服务的完整对象",
                strength="完整且可长期展开",
                overreach_risk="不能把任何饮食习惯都混成火锅",
                basis_refs=semantic_basis,
            ),
        ),
    )

    assert semantics.offering_role == "intermediate_enabler"
    assert semantics.served_objects[0].text == "火锅"
    assert semantics.served_activities[0].text == "制作火锅"
    assert world.audience_territory.text == "火锅"
    assert world.root_candidates[0].candidate_id == "candidate-firepot"


def test_projection_cannot_attach_to_a_different_record() -> None:
    with pytest.raises(ValidationError, match="projection record_id"):
        _bundle(record_id="record-from-another-project")


def test_projection_contracts_do_not_own_format_sales_platform_or_experiments() -> None:
    schemas = (
        BusinessSemanticView.model_json_schema(),
        ContentWorldView.model_json_schema(),
        TopicBrief.model_json_schema(),
    )
    forbidden = {
        "presentation_format",
        "platform",
        "sales_plan",
        "experiment",
        "object_anchor",
        "return_path",
        "bridge_path",
    }

    for schema in schemas:
        assert forbidden.isdisjoint(schema["properties"])


def test_lead_projection_is_compact_and_keeps_map_claims_provisional() -> None:
    payload = _lead_projection(_bundle(), focus=AnalysisFocus.CONTENT_WORLD)

    assert "record" not in payload
    assert "observations" not in payload
    assert "interpretations" not in payload
    assert payload["record_fingerprint"]
    assert payload["content_world"]["content_root"] == "火锅"
    assert payload["scope"]["map_axis"] == "火锅"
    assert "commercial_object_role" not in payload["scope"]
    assert "unrequested downstream operating plan" in payload["scope"]["does_not_support"]
    assert payload["scope"]["supports"] == [
        "semantic transition",
        "content root",
        "audience territory",
        "research directions",
    ]
    assert "object_anchor" not in payload["content_world"]
    assert "bridge_path" not in payload["content_world"]
    assert "root_candidates" not in payload["content_world"]
    assert "source_object" not in payload["content_world"]
    assert "business_semantics" not in payload
    assert "unknowns" not in payload
    assert payload["semantic_transition"]["lexical_head"] == "底料"
    assert "platform choice" in payload["scope"]["does_not_support"]
    assert "posting cadence" in payload["scope"]["does_not_support"]
    assert "numeric quota" in payload["scope"]["does_not_support"]


def test_record_fingerprint_is_stable_and_changes_with_source_content() -> None:
    original = _record()
    same = _record()
    changed = ComprehensionRecord(
        record_id="record-1",
        subject_expression="我是做其他业务的",
        sources=(_source("我是做其他业务的"),),
    )

    assert original.fingerprint() == same.fingerprint()
    assert original.fingerprint() != changed.fingerprint()


def test_content_path_rejects_a_disconnected_chain() -> None:
    with pytest.raises(ValidationError, match="continuous"):
        ContentPath(
            path_id="path-disconnected",
            steps=(
                ContentPathStep(
                    from_label="海鲜",
                    relation="向下细分",
                    to_label="牡蛎",
                    status="candidate",
                    verification_needed=True,
                ),
                ContentPathStep(
                    from_label="另一条无关分支",
                    relation="进入作品",
                    to_label="《我的叔叔于勒》",
                    status="candidate",
                    verification_needed=True,
                ),
            ),
            rationale="这条路径中间断开，不能伪装成完整联想链。",
        )
