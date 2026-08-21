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
    NarrativeFrame,
    Observation,
    SourceItem,
    TopicBrief,
    Unknown,
    render_shooting_delivery,
    synthesize_shooting_delivery,
)
from deerflow.content_intelligence.delivery import SHOOTING_DELIVERY_SYSTEM_PROMPT
from deerflow.incubation import (
    AccountPresentationPlan,
    AudienceHypothesis,
    IncubationJudgment,
    MonetizationHypothesis,
    PersonaDecision,
    PositioningDecision,
)


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


class SequencedStructuredDeliveryFakeModel:
    def __init__(self, payloads: list[dict[str, Any]]) -> None:
        self.payloads = payloads
        self.schema = None
        self.message_batches: list[tuple[object, ...]] = []

    def with_structured_output(self, schema, *, include_raw: bool = False):
        self.schema = schema
        return self

    async def ainvoke(self, messages, config=None):
        self.message_batches.append(tuple(messages))
        payload = self.payloads[min(len(self.message_batches) - 1, len(self.payloads) - 1)]
        return self.schema.model_validate(payload)


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


def _narrative_bundle() -> ContentIntelligenceBundle:
    bundle = _evidence_bound_bundle()
    assert bundle.topic_brief is not None
    story_source = SourceItem(
        source_id="source-story-1",
        kind="web_page",
        evidence_role="topic_evidence",
        title="A bounded account of one banquet guest",
        uri="https://example.com/banquet-guest",
        content="A bounded account records a first-time guest observing the toast order and adjusting his response.",
    )
    story_observation = Observation(
        observation_id="observation-story-1",
        claim="A first-time guest wanted to respond respectfully, did not understand the local toast order, observed the table, adjusted his response, and then understood that the occasion expressed both courtesy and relationships.",
        source_refs=(story_source.source_id,),
    )
    evidence_ref = BasisRef(kind="observation", ref_id=story_observation.observation_id)
    return bundle.model_copy(
        update={
            "record": bundle.record.model_copy(
                update={
                    "sources": (*bundle.record.sources, story_source),
                    "observations": (*bundle.record.observations, story_observation),
                }
            ),
            "topic_brief": bundle.topic_brief.model_copy(
                update={
                    "evidence_refs": (*bundle.topic_brief.evidence_refs, evidence_ref),
                    "narrative_frame": NarrativeFrame(
                        protagonist="一位第一次参加当地宴席的外地客人",
                        goal="得体地回应主家的款待",
                        obstacle="他不理解酒桌上敬酒与回应的当地礼数",
                        action_or_choice="他观察席间人物的先后顺序并调整自己的回应",
                        stakes_or_consequence="回应失当可能被误解为不尊重对方",
                        outcome_or_change="他开始理解这张酒桌表达的不只是酒量，还有关系与礼数",
                        basis_refs=(evidence_ref,),
                        limitations=("当前回执只能支持这条行动链作为有界故事线索。",),
                    ),
                }
            ),
        }
    )


def _incubation_judgment(bundle: ContentIntelligenceBundle) -> IncubationJudgment:
    assert bundle.content_world is not None
    return IncubationJudgment(
        content_map_version_id=bundle.content_world.content_map_version_id(),
        positioning=PositioningDecision(
            decision="从酒桌中的具体人物和事情理解地方礼俗",
            audience_promise="让观众借一张具体饭桌看懂关系如何被表达",
            rationale="它与冻结内容根一致。",
        ),
        audience=AudienceHypothesis(
            people="对地方生活、人际往来和酒桌现象好奇的观众",
            recurring_interest="具体场合中的关系表达",
            why_return="每次都从一件具体事情得到新的关系解释",
            rationale="这是待真实反馈校正的受众假设。",
        ),
        persona=PersonaDecision(
            account_role="观察日常酒桌与地方人情的经营者",
            trust_basis=("用户只声明自己卖白酒。",),
            boundaries=("不冒充民俗学者。",),
            rationale="只使用用户原话允许的经营者立场。",
        ),
        presentation=AccountPresentationPlan(
            primary_forms=("围绕具体人物和事件展开",),
            rationale="账号级表达应服务长期观察方法。",
        ),
        monetization=(
            MonetizationHypothesis(
                path="通过长期信任承接白酒购买需求",
                trust_required="观众认可账号懂酒桌与人情",
                rationale="只是一条待验证商业假设。",
            ),
        ),
        unknowns=("尚未确认用户是否愿意出镜。",),
    )


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
    assert '"项目主体原话": "我是卖白酒的，该怎么起号？"' in prompt_input
    assert '"具体问题"' in prompt_input
    assert '"中心判断"' in prompt_input
    assert '"账号长期承诺"' in prompt_input
    assert '"持续观察方法"' in prompt_input
    assert "business_semantics" not in prompt_input
    assert "map_dimensions" not in prompt_input
    assert "A bounded public record" not in prompt_input


@pytest.mark.asyncio
async def test_evidence_bound_narrative_frame_reaches_delivery_as_the_story_spine() -> None:
    bundle = _narrative_bundle()
    payload = _message_plan_payload()
    payload.update(
        {
            "topic_title": "一个外地人，为什么在这张酒桌上突然不会喝酒了？",
            "focal_subject": "一位第一次参加当地宴席的外地客人",
            "concrete_event_or_question": "外地客人想得体回应款待，却因不懂敬酒顺序而迟疑",
            "entry_point": "从主家突然端起第一杯酒的那一刻讲起",
            "telling_lens": "跟着这位客人的观察、迟疑和调整往前推进",
            "opening": "主家端起第一杯酒时，这位外地客人突然不知道自己该不该起身。",
            "message_beats": [
                "他本来只想得体地回应款待，却看不懂这张桌上谁先敬、谁后回的顺序。",
                "他开始观察席间人物的动作，再调整自己的回应，因为一个失当的动作可能被误解为不尊重。",
            ],
            "closing": "那一刻他才明白，这张酒桌表达的不只是酒量，还有关系与礼数。",
        }
    )
    model = StructuredDeliveryFakeModel(payload)

    delivery = await synthesize_shooting_delivery(
        bundle,
        user_request="我是卖白酒的，该怎么起号？",
        model=model,
    )

    assert delivery is not None
    assert delivery.base_draft.text.startswith("主家端起第一杯酒时")
    prompt_input = model.message_batches[0][1].content
    assert '"叙事骨架"' in prompt_input
    assert '"具体目标": "得体地回应主家的款待"' in prompt_input
    assert '"阻碍": "他不理解酒桌上敬酒与回应的当地礼数"' in prompt_input
    assert '"行动或选择"' in prompt_input
    assert '"结果或变化"' in prompt_input


@pytest.mark.asyncio
async def test_confirmed_route_continuation_keeps_the_project_subject_as_its_position_basis() -> None:
    bundle = _evidence_bound_bundle()
    model = StructuredDeliveryFakeModel(_message_plan_payload())

    delivery = await synthesize_shooting_delivery(
        bundle,
        user_request="按照已确认路线，再给我一个今天能拍的选题和基础稿。",
        model=model,
    )

    assert delivery is not None
    assert delivery.message_plan.account_position_basis == bundle.record.subject_expression
    assert delivery.message_plan.account_position == bundle.record.subject_expression
    assert "按照已确认路线" not in delivery.message_plan.account_position_basis


@pytest.mark.asyncio
async def test_incubation_judgment_guides_position_and_audience_without_leaking_monetization() -> None:
    bundle = _evidence_bound_bundle()
    model = StructuredDeliveryFakeModel(_message_plan_payload())

    delivery = await synthesize_shooting_delivery(
        bundle,
        user_request="我是卖白酒的，该怎么起号？",
        model=model,
        incubation_judgment=_incubation_judgment(bundle),
    )

    assert delivery is not None
    assert delivery.message_plan.account_position_basis == "观察日常酒桌与地方人情的经营者"
    assert delivery.message_plan.account_position == "观察日常酒桌与地方人情的经营者"
    assert "怎么起号" not in delivery.message_plan.account_position_basis
    prompt_input = model.message_batches[0][1].content
    assert "从酒桌中的具体人物和事情理解地方礼俗" in prompt_input
    assert "对地方生活、人际往来和酒桌现象好奇的观众" in prompt_input
    assert "观察日常酒桌与地方人情的经营者" in prompt_input
    assert "尚未确认用户是否愿意出镜" in prompt_input
    assert "账号级表达方向" not in prompt_input
    assert '"备选"' not in prompt_input
    assert "通过长期信任承接白酒购买需求" not in prompt_input
    assert "monetization" not in prompt_input.casefold()


@pytest.mark.asyncio
async def test_thin_editorial_context_guides_delivery_without_an_old_incubation_judgment() -> None:
    from deerflow.content_intelligence import ResearchEditorialContext

    bundle = _evidence_bound_bundle()
    model = StructuredDeliveryFakeModel(_message_plan_payload())
    editorial_context = ResearchEditorialContext(
        route_id="direction_1",
        content_subject="地方酒桌背后的人际关系与生活秩序",
        audience_promise="从具体人物和事情看懂地方人情",
        audience_people="对地方生活与人际往来好奇的人",
        recurring_interest=None,
        account_role="从白酒生意观察地方人情的经营者",
    )

    delivery = await synthesize_shooting_delivery(
        bundle,
        user_request="给我一个今天能拍的具体选题。",
        model=model,
        editorial_context=editorial_context,
    )

    assert delivery is not None
    assert delivery.message_plan.account_position_basis == editorial_context.account_role
    prompt_input = model.message_batches[0][1].content
    assert editorial_context.content_subject in prompt_input
    assert editorial_context.audience_promise in prompt_input
    assert editorial_context.audience_people in prompt_input
    assert "monetization" not in prompt_input.casefold()


@pytest.mark.asyncio
async def test_delivery_repairs_named_numeric_and_absolute_claims_absent_from_evidence() -> None:
    bundle = _evidence_bound_bundle()
    unsupported = _message_plan_payload()
    unsupported["topic_title"] = "全球最贵的地方酒桌"
    unsupported["opening"] = "1977 年，Eduardo Rivera 第一次来到这张酒桌。"
    unsupported["message_beats"] = [
        "这个只有模型记忆、没有证据的人名和年份，不能被补进稿子。",
    ]
    model = SequencedStructuredDeliveryFakeModel([unsupported, _message_plan_payload()])

    delivery = await synthesize_shooting_delivery(
        bundle,
        user_request="我是卖白酒的，该怎么起号？",
        model=model,
    )

    assert delivery is not None
    assert "Eduardo Rivera" not in delivery.base_draft.text
    assert "1977" not in delivery.base_draft.text
    assert "全球最贵" not in delivery.message_plan.topic_title
    assert len(model.message_batches) == 2
    repair_message = model.message_batches[1][-1].content
    assert "Eduardo" in repair_message
    assert "Rivera" in repair_message
    assert "1977" in repair_message
    assert "全球最贵" in repair_message
    assert "do not replace it with another name" in repair_message


@pytest.mark.asyncio
async def test_delivery_repairs_unsupported_user_experience_and_foreign_text() -> None:
    bundle = _evidence_bound_bundle()
    unsupported = _message_plan_payload()
    unsupported["message_beats"] = [
        "旧书店里待久了你就会知道，我们的客户 заранее 都会先看这枚印。",
    ]
    model = SequencedStructuredDeliveryFakeModel([unsupported, _message_plan_payload()])

    delivery = await synthesize_shooting_delivery(
        bundle,
        user_request="我是卖白酒的，该怎么起号？",
        model=model,
    )

    assert delivery is not None
    assert "待久了你就会知道" not in delivery.base_draft.text
    assert "我们的客户" not in delivery.base_draft.text
    assert "заранее" not in delivery.base_draft.text
    assert len(model.message_batches) == 2
    repair_message = model.message_batches[1][-1].content
    assert "待久了你就会知道" in repair_message
    assert "我们的客户" in repair_message
    assert "заранее" in repair_message


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

    payload["context"] = "null"
    normalized = MessagePlanDraft.model_validate(payload)
    assert normalized.context is None


def test_delivery_prompt_separates_internal_exploration_from_the_shootable_answer() -> None:
    assert "语义理解和候选内容地图已经完成" in SHOOTING_DELIVERY_SYSTEM_PROMPT
    assert "它才负责长期定位、受众与人设" in SHOOTING_DELIVERY_SYSTEM_PROMPT
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
    assert "业务身份不等于拥有拍摄素材" in SHOOTING_DELIVERY_SYSTEM_PROMPT
    assert "不得改写成用户做久了、见过、经手过" in SHOOTING_DELIVERY_SYSTEM_PROMPT
    assert "只推进一条连贯的论证主线" in SHOOTING_DELIVERY_SYSTEM_PROMPT
    assert "来源名称本身不是内容" in SHOOTING_DELIVERY_SYSTEM_PROMPT
    assert "已封存的叙事骨架" in SHOOTING_DELIVERY_SYSTEM_PROMPT
    assert "先让观众看到人如何行动" in SHOOTING_DELIVERY_SYSTEM_PROMPT
    assert "按发生顺序推进具体事件" in SHOOTING_DELIVERY_SYSTEM_PROMPT
    assert "把故事改写成案例分析" in SHOOTING_DELIVERY_SYSTEM_PROMPT
    assert "接收者第一反应" in SHOOTING_DELIVERY_SYSTEM_PROMPT
    assert "没有叙事骨架时不得硬编" in SHOOTING_DELIVERY_SYSTEM_PROMPT
    assert "红薯" not in SHOOTING_DELIVERY_SYSTEM_PROMPT
    assert "白酒" not in SHOOTING_DELIVERY_SYSTEM_PROMPT


def test_rendered_delivery_is_a_compact_daily_topic_and_base_draft() -> None:
    bundle = _evidence_bound_bundle()
    assert bundle.topic_brief is not None
    bundle = bundle.model_copy(
        update={
            "record": bundle.record.model_copy(
                update={
                    "unknowns": (
                        Unknown(
                            unknown_id="unknown-regional-scope",
                            question="这份资料能否代表两地全部宴席？",
                        ),
                    )
                }
            ),
            "topic_brief": bundle.topic_brief.model_copy(update={"unknown_refs": ("unknown-regional-scope",)}),
        }
    )
    draft = MessagePlanDraft.model_validate(_message_plan_payload())
    delivery = draft.bind(
        bundle=bundle,
        account_position_basis="我是卖白酒的，该怎么起号？",
    )

    rendered = render_shooting_delivery(bundle, delivery)

    assert rendered.startswith("# 今日建议拍摄")
    assert "**内容路线：** 饮酒与人际礼俗 → 山东、河南宴席上的饮酒习俗" in rendered
    assert "**账号方向：**" not in rendered
    assert "**谁：** 参加当地宴席的饮酒者与主家" in rendered
    assert "**时间 / 场景：** 宴请、节庆和人情往来的饭桌上" in rendered
    assert "**发生什么：**" in rendered
    assert "**账号观察立场：** 我是卖白酒的，该怎么起号？" in rendered
    assert "**你的立场：**" not in rendered
    assert "从一名白酒经营者日常观察饮酒场景的立场出发" not in rendered
    assert "**核心观点：**" in rendered
    assert "**切入点：**" in rendered
    assert "## 基础文案" in rendered
    assert "饮酒与人际礼俗" in rendered
    assert "A public record about regional drinking customs" in rendered
    assert "**证据状态：** 3 项待补证边界；未核实内容未写成事实。" in rendered
    assert "**待确认：** 1 项未知；未确认内容未写成事实。" in rendered
    assert "当前只有一份有界证据回执。" not in rendered
    assert "成稿前补充两地的礼俗及历史来源。" not in rendered
    assert "这份资料能否代表两地全部宴席？" not in rendered
    assert "## 证据边界" not in rendered
    assert "## 待确认" not in rendered
    assert "# 内容机会依据" not in rendered
    assert "## 候选内容方向" not in rendered
    assert "**讲述视角：**" not in rendered
    assert "**信息怎么揭开：**" not in rendered
    assert rendered.count(delivery.base_draft.text) == 1


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
