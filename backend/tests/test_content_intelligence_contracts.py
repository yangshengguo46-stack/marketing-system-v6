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
                from_label="重庆火锅底料",
                relation="用于",
                to_label="火锅",
                basis_refs=(BasisRef(kind="interpretation", ref_id="interpretation-1"),),
            ),
        ),
        rationale="这是具体选题的理解路径，不属于内容地图。",
    )
    content_world = ContentWorldView(
        record_id=record_id,
        source_object="重庆火锅底料",
        content_root="火锅",
        root_rationale="火锅是待展开的内容世界，不是销售方案。",
    )
    topic_brief = TopicBrief(
        record_id=record_id,
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
