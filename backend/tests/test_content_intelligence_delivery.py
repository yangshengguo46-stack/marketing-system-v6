from __future__ import annotations

from typing import Any

import pytest

from deerflow.content_intelligence import (
    BasisRef,
    ComprehensionRecord,
    ContentDimension,
    ContentIntelligenceBundle,
    ContentPath,
    ContentPathStep,
    ContentWorldView,
    MessagePlanDraft,
    Observation,
    SourceItem,
    TopicBrief,
    render_shooting_delivery,
    synthesize_shooting_delivery,
)
from deerflow.content_intelligence.delivery import SHOOTING_DELIVERY_SYSTEM_PROMPT


class StructuredDeliveryFakeModel:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.schema = None
        self.message_batches: list[tuple[object, ...]] = []

    def with_structured_output(self, schema, *, include_raw: bool = False):
        self.schema = schema
        return self

    async def ainvoke(self, messages, config=None):
        self.message_batches.append(tuple(messages))
        return self.schema.model_validate(self.payload)


def _evidence_bound_bundle() -> ContentIntelligenceBundle:
    evidence_ref = BasisRef(kind="observation", ref_id="observation-topic-1")
    record = ComprehensionRecord(
        record_id="record-baijiu",
        subject_expression="我是卖白酒的，该怎么起号？",
        sources=(
            SourceItem(
                source_id="source-topic-1",
                kind="web_page",
                evidence_role="topic_evidence",
                title="A public record about regional drinking customs",
                uri="https://example.com/regional-customs",
                content="A bounded public record about people, occasions, and drinking customs.",
            ),
        ),
        observations=(
            Observation(
                observation_id="observation-topic-1",
                claim="The supplied record describes drinking as part of recurring social occasions.",
                source_refs=("source-topic-1",),
            ),
        ),
    )
    path = ContentPath(
        path_id="path-regional-customs",
        steps=(
            ContentPathStep(
                from_label="饮酒与人际礼俗",
                relation="在地域与场合中具体化",
                to_label="山东、河南宴席上的饮酒习俗",
                basis_refs=(evidence_ref,),
            ),
        ),
        rationale="从反复发生的人际场合解释地域饮酒习俗。",
    )
    world = ContentWorldView(
        record_id=record.record_id,
        content_root="饮酒与人际礼俗",
        root_rationale="它能展开具体的人、场合和事情。",
        editorial_promise="持续借具体酒桌理解地方礼俗与人际表达，而不是只介绍酒。",
        recurring_lens="从一个具体人物、场合或行为进入，解释酒桌上的关系如何被表达。",
        drift_boundaries=("与饮酒和人际礼俗没有可解释路径的热点不进入账号地图。",),
        dimensions=(
            ContentDimension(
                name="地域与场合",
                rationale="不同地域的人如何在具体场合饮酒。",
                paths=(path,),
            ),
        ),
    )
    topic = TopicBrief(
        record_id=record.record_id,
        content_map_version_id=world.content_map_version_id(),
        question="为什么山东、河南的宴席饮酒文化给人格外重的印象？",
        central_claim="这种印象需要从宴席礼俗和人际表达解释，不能简化为当地人更能喝。",
        mechanism="具体场合中的行为和角色让宏观的地域印象变得可解释。",
        counterpoint="不能把两个省的人简化为同一种性格，也不能用一份来源证明普遍因果。",
        path=path,
        evidence_refs=(evidence_ref,),
        limitations=("当前只有一份有界证据回执。",),
        research_needed=("成稿前补充两地的礼俗及历史来源。",),
    )
    return ContentIntelligenceBundle(record=record, content_world=world, topic_brief=topic)


def _message_plan_payload() -> dict[str, Any]:
    return {
        "topic_title": "为什么山东、河南的酒文化给人特别重的印象？",
        "focal_subject": "参加当地宴席的饮酒者与主家",
        "context": "宴请、节庆和人情往来的饭桌上",
        "concrete_event_or_question": "同样是喝酒，为什么这些场合会让外地人感到礼数和饮酒压力都很重",
        "account_position": "从一名白酒经营者日常观察饮酒场景的立场出发",
        "point_of_view": "重的不只是酒量，而是人们用宴席中的饮酒行为表达礼数与关系",
        "entry_point": "从一场外地客人第一次参加当地宴席时感受到的饮酒压力讲起",
        "telling_lens": "跟着外地客人的疑问观察主家、客人和酒在一张饭桌上的关系",
        "audience_question": "明明都在喝酒，为什么这一桌会让人感觉礼数格外重",
        "information_order": "先呈现外地人的直观压力，再辨认饭桌上的角色与回应，最后解释酒如何承载人情表达",
        "payoff": "观众最后理解，所谓酒文化重，未必只是在说酒量，更是在说一套具体的人情表达方式",
        "opening": "一张酒桌上，大家真的只是在比谁更能喝吗？",
        "message_beats": [
            "表面看是能喝，但在很多宴席上，酒还在表达主家的礼数、客人的回应和关系的远近。",
            "所以我们要理解的不只是喝了多少，而是一张酒桌怎么成了人情表达的场所。",
            "当然，这不代表两地每个人都一样，具体历史与礼俗还需要更完整的证据。",
        ],
        "closing": "看懂一个地方的酒桌，先要看懂它怎么表达人情。",
        "limitations": ["具体历史原因尚待补充权威来源。"],
        "unknowns": [],
    }


@pytest.mark.asyncio
async def test_topic_brief_becomes_a_concrete_shooting_delivery_from_the_users_position() -> None:
    bundle = _evidence_bound_bundle()
    model = StructuredDeliveryFakeModel(_message_plan_payload())

    delivery = await synthesize_shooting_delivery(
        bundle,
        user_request="我是卖白酒的，该怎么起号？",
        model=model,
    )

    assert delivery is not None
    assert delivery.message_plan.record_id == bundle.record.record_id
    assert delivery.message_plan.account_position_basis == "我是卖白酒的，该怎么起号？"
    assert delivery.message_plan.focal_subject == "参加当地宴席的饮酒者与主家"
    assert delivery.message_plan.context is not None
    assert delivery.message_plan.concrete_event_or_question
    assert delivery.message_plan.point_of_view
    assert delivery.message_plan.entry_point.startswith("从一场外地客人")
    assert delivery.message_plan.telling_lens.startswith("跟着外地客人")
    assert delivery.message_plan.audience_question
    assert delivery.message_plan.information_order
    assert delivery.message_plan.payoff
    assert delivery.base_draft.message_plan_id == delivery.message_plan.message_plan_id
    assert delivery.base_draft.text.startswith("一张酒桌上")
    assert delivery.message_plan.evidence_refs == bundle.topic_brief.evidence_refs

    prompt_input = model.message_batches[0][1].content
    assert '"用户原话": "我是卖白酒的，该怎么起号？"' in prompt_input
    assert '"具体问题"' in prompt_input
    assert '"中心判断"' in prompt_input
    assert '"账号长期承诺"' in prompt_input
    assert '"持续观察方法"' in prompt_input
    assert "business_semantics" not in prompt_input
    assert "map_dimensions" not in prompt_input
    assert "A bounded public record" not in prompt_input


@pytest.mark.asyncio
async def test_delivery_is_optional_when_research_has_not_produced_a_topic() -> None:
    bundle = _evidence_bound_bundle().model_copy(update={"topic_brief": None})
    model = StructuredDeliveryFakeModel(_message_plan_payload())

    delivery = await synthesize_shooting_delivery(
        bundle,
        user_request="我是卖白酒的，该怎么起号？",
        model=model,
    )

    assert delivery is None
    assert model.message_batches == []


def test_message_plan_contract_requires_a_telling_treatment_but_not_forced_time() -> None:
    schema = MessagePlanDraft.model_json_schema()

    assert {
        "focal_subject",
        "concrete_event_or_question",
        "account_position",
        "point_of_view",
        "entry_point",
        "telling_lens",
        "audience_question",
        "information_order",
        "payoff",
    }.issubset(schema["required"])
    assert "context" not in schema["required"]

    payload = _message_plan_payload()
    payload["context"] = None
    validated = MessagePlanDraft.model_validate(payload)
    assert validated.context is None


def test_delivery_prompt_separates_internal_exploration_from_the_shootable_answer() -> None:
    assert "语义理解和账号内容地图已经完成" in SHOOTING_DELIVERY_SYSTEM_PROMPT
    assert "谁在什么情境下遇到了什么具体事情" in SHOOTING_DELIVERY_SYSTEM_PROMPT
    assert "不得冒充医生、律师、历史学者" in SHOOTING_DELIVERY_SYSTEM_PROMPT
    assert "不设固定段数" in SHOOTING_DELIVERY_SYSTEM_PROMPT
    assert "只能改写输入的具体问题" in SHOOTING_DELIVERY_SYSTEM_PROMPT
    assert "消费者为什么买单" in SHOOTING_DELIVERY_SYSTEM_PROMPT
    assert "从哪个具体事实、人物、物件、场面或问题切入" in SHOOTING_DELIVERY_SYSTEM_PROMPT
    assert "信息按什么顺序揭示" in SHOOTING_DELIVERY_SYSTEM_PROMPT
    assert "不能制造虚假悬念" in SHOOTING_DELIVERY_SYSTEM_PROMPT
    assert "标题包装不能替代" in SHOOTING_DELIVERY_SYSTEM_PROMPT
    assert "context 描述内容世界里的时间、地点、场合或处境" in SHOOTING_DELIVERY_SYSTEM_PROMPT
    assert "选择一个主入口" in SHOOTING_DELIVERY_SYSTEM_PROMPT
    assert "不要求把用户的店铺、职业或商品写进正文" in SHOOTING_DELIVERY_SYSTEM_PROMPT
    assert "来源名称本身不是内容" in SHOOTING_DELIVERY_SYSTEM_PROMPT
    assert "红薯" not in SHOOTING_DELIVERY_SYSTEM_PROMPT
    assert "白酒" not in SHOOTING_DELIVERY_SYSTEM_PROMPT


def test_rendered_delivery_shows_account_positioning_before_one_daily_topic() -> None:
    bundle = _evidence_bound_bundle()
    draft = MessagePlanDraft.model_validate(_message_plan_payload())
    delivery = draft.bind(
        bundle=bundle,
        account_position_basis="我是卖白酒的，该怎么起号？",
    )

    rendered = render_shooting_delivery(bundle, delivery)

    assert rendered.startswith("# 账号内容定位")
    assert "**长期讲什么：** 饮酒与人际礼俗" in rendered
    assert "**关注理由：** 持续借具体酒桌理解地方礼俗与人际表达，而不是只介绍酒。" in rendered
    assert "**稳定观察方法：** 从一个具体人物、场合或行为进入，解释酒桌上的关系如何被表达。" in rendered
    assert "# 今日建议拍摄" in rendered
    assert "**谁：** 参加当地宴席的饮酒者与主家" in rendered
    assert "**时间 / 场景：** 宴请、节庆和人情往来的饭桌上" in rendered
    assert "**发生什么：**" in rendered
    assert "**你的立场：**" in rendered
    assert "**核心观点：**" in rendered
    assert "**从哪里讲起：**" in rendered
    assert "**讲述视角：**" in rendered
    assert "**观众一路想知道：**" in rendered
    assert "**信息怎么揭开：**" in rendered
    assert "**最后得到什么：**" in rendered
    assert "## 基础文案" in rendered
    assert "## 内容路径" in rendered
    assert "饮酒与人际礼俗" in rendered
    assert "A public record about regional drinking customs" in rendered
    assert "# 饮酒与人际礼俗" not in rendered


def test_same_topic_with_a_different_telling_treatment_gets_a_distinct_plan_id() -> None:
    bundle = _evidence_bound_bundle()
    first = MessagePlanDraft.model_validate(_message_plan_payload()).bind(
        bundle=bundle,
        account_position_basis="我是卖白酒的，该怎么起号？",
    )
    alternate_payload = _message_plan_payload()
    alternate_payload["entry_point"] = "从主家第一杯酒先敬给谁讲起"
    alternate_payload["telling_lens"] = "跟着主家的敬酒顺序观察一桌人的关系"
    alternate = MessagePlanDraft.model_validate(alternate_payload).bind(
        bundle=bundle,
        account_position_basis="我是卖白酒的，该怎么起号？",
    )

    assert first.message_plan.topic_title == alternate.message_plan.topic_title
    assert first.message_plan.message_plan_id != alternate.message_plan.message_plan_id
