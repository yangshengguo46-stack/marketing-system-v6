from __future__ import annotations

import json
from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from pydantic import ValidationError

from deerflow.content_intelligence import (
    AnalysisFocus,
    ContentIntelligenceDraft,
    ContentIntelligenceRequest,
    ContentRootCandidateSetDraft,
    ContentRootDecisionDraft,
    ContentRootSelectionDraft,
    FrozenContentMapDraft,
    SemanticReadingDraft,
    SharedWorldSynthesisDraft,
    SourceMaterial,
    analyze_content_intelligence,
    render_content_world_narration,
    synthesize_content_world_narration,
)
from deerflow.content_intelligence.analyzer import (
    CONTENT_WORLD_NARRATION_SYSTEM_PROMPT,
    FROZEN_CONTENT_MAP_SYSTEM_PROMPT,
    _parse_structured_result,
)


class StructuredFakeModel:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.schema = None
        self.messages = None
        self.config = None
        self.calls = 0
        self.include_raw = False

    def with_structured_output(self, schema, *, include_raw: bool = False):
        self.schema = schema
        self.include_raw = include_raw
        return self

    async def ainvoke(self, messages, config=None):
        self.calls += 1
        self.messages = messages
        self.config = config
        try:
            parsed = self.schema.model_validate(self.payload)
            parsing_error = None
        except ValidationError as exc:
            if not self.include_raw:
                raise
            parsed = None
            parsing_error = exc
        if not self.include_raw:
            return parsed
        return {
            "raw": AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": self.schema.__name__,
                        "args": self.payload,
                        "id": "tool-call-1",
                        "type": "tool_call",
                    }
                ],
            ),
            "parsed": parsed,
            "parsing_error": parsing_error,
        }


class SequencedStructuredFakeModel:
    def __init__(self, payloads: dict[type, dict[str, Any]]) -> None:
        self.payloads = payloads
        self.current_schema = None
        self.schemas: list[type] = []
        self.message_batches: list[tuple[object, ...]] = []
        self.include_raw_flags: list[bool] = []
        self.calls = 0

    def with_structured_output(self, schema, *, include_raw: bool = False):
        self.current_schema = schema
        self.schemas.append(schema)
        self.include_raw_flags.append(include_raw)
        return self

    async def ainvoke(self, messages, config=None):
        self.calls += 1
        self.message_batches.append(tuple(messages))
        return self.current_schema.model_validate(self.payloads[self.current_schema])


class RawContentSequencedFakeModel(SequencedStructuredFakeModel):
    async def ainvoke(self, messages, config=None):
        self.calls += 1
        self.message_batches.append(tuple(messages))
        payload = self.payloads[self.current_schema]
        if self.current_schema is SemanticReadingDraft:
            return {
                "raw": AIMessage(content=f"```json\n{json.dumps(payload, ensure_ascii=False)}\n```"),
                "parsed": None,
                "parsing_error": ValueError("provider returned JSON as message content"),
            }
        return self.current_schema.model_validate(payload)


class MalformedToolArgumentsSequencedFakeModel(SequencedStructuredFakeModel):
    async def ainvoke(self, messages, config=None):
        self.calls += 1
        self.message_batches.append(tuple(messages))
        payload = self.payloads[self.current_schema]
        if self.current_schema is FrozenContentMapDraft:
            malformed = json.dumps(payload, ensure_ascii=False).replace('"unknowns": []', "\"unknowns\": ['待核验']")
            return {
                "raw": AIMessage(
                    content="",
                    invalid_tool_calls=[
                        {
                            "name": "FrozenContentMapDraft",
                            "args": malformed,
                            "id": "malformed-map-call",
                            "error": None,
                            "type": "invalid_tool_call",
                        }
                    ],
                ),
                "parsed": None,
                "parsing_error": ValueError("provider emitted one Python-style string inside JSON arguments"),
            }
        return self.current_schema.model_validate(payload)


class RetryableMalformedMapFakeModel(SequencedStructuredFakeModel):
    def __init__(self, payloads: dict[type, dict[str, Any]]) -> None:
        super().__init__(payloads)
        self.map_attempts = 0

    async def ainvoke(self, messages, config=None):
        self.calls += 1
        self.message_batches.append(tuple(messages))
        payload = self.payloads[self.current_schema]
        if self.current_schema is FrozenContentMapDraft:
            self.map_attempts += 1
            if self.map_attempts == 1:
                return {
                    "raw": AIMessage(
                        content="",
                        invalid_tool_calls=[
                            {
                                "name": "FrozenContentMapDraft",
                                "args": json.dumps(payload, ensure_ascii=False) + "}",
                                "id": "structurally-invalid-map-call",
                                "error": None,
                                "type": "invalid_tool_call",
                            }
                        ],
                    ),
                    "parsed": None,
                    "parsing_error": ValueError("provider emitted an extra closing brace"),
                }
        return self.current_schema.model_validate(payload)


class PlainNarrationFakeModel:
    def __init__(self, content: str) -> None:
        self.content = content
        self.message_batches: list[tuple[object, ...]] = []
        self.configs: list[object] = []
        self.calls = 0

    def with_structured_output(self, schema, *, include_raw: bool = False):
        raise AssertionError("the prose editor must not serialize long-form copy as JSON")

    async def ainvoke(self, messages, config=None):
        self.calls += 1
        self.message_batches.append(tuple(messages))
        self.configs.append(config)
        return AIMessage(content=self.content)


def test_structured_parser_rejects_multiple_tool_calls_instead_of_silently_using_first() -> None:
    payload = _semantic_payload()
    parsed = SemanticReadingDraft.model_validate(payload)
    raw = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "SemanticReadingDraft",
                "args": payload,
                "id": f"tool-call-{index}",
                "type": "tool_call",
            }
            for index in range(1, 3)
        ],
    )

    with pytest.raises(ValueError, match="exactly one structured tool call"):
        _parse_structured_result(
            {"raw": raw, "parsed": parsed, "parsing_error": None},
            SemanticReadingDraft,
            container_fields={"modifiers"},
        )


def _semantic_payload() -> dict[str, Any]:
    return {
        "source_object": "重庆火锅底料",
        "lexical_head": "底料",
        "modifiers": [
            {"term": "重庆火锅", "relation": "served_object", "modifies": "底料"},
        ],
        "offering_role": "intermediate_enabler",
        "role_rationale": "底料是完成火锅的调味基底。",
        "served_objects": ["火锅"],
        "served_activities": ["制作火锅"],
        "defining_functions_or_uses": ["形成火锅锅底风味"],
        "social_or_cultural_frames": ["火锅饮食文化"],
        "seller_actions": [],
        "uncertainties": [],
    }


def _root_candidate_set_payload() -> dict[str, Any]:
    return {
        "source_object": "重庆火锅底料",
        "candidates": [
            {
                "level": "served_object_or_activity",
                "label": "火锅",
                "scope_role": "root_candidate",
                "relation_to_business": "底料服务的完整对象",
                "strength": "完整且有长期内容容量",
                "overreach_risk": "不能把任何饮食习惯都混成火锅",
            },
        ],
        "unknowns": [],
    }


def _shared_world_payload() -> dict[str, Any]:
    return {
        "common_action_or_relation": "围绕火锅共同进食",
        "participant_relationship": "共同用餐者",
        "world_label": "围绕火锅的共同用餐生活",
        "covered_frames": ["火锅饮食文化"],
        "limitations": ["不能扩成与火锅无关的泛餐饮生活"],
    }


def _root_decision_payload() -> dict[str, Any]:
    return {
        "selected_candidate_index": 0,
        "audience_territory_candidate_index": 0,
        "root_rationale": "底料是中间实现物，火锅是完整对象世界。",
        "unknowns": [],
    }


def _root_selection_payload() -> dict[str, Any]:
    return {
        **_root_candidate_set_payload(),
        **_root_decision_payload(),
    }


def _frozen_map_payload() -> dict[str, Any]:
    return {
        "map_directions": [
            {"dimension": "地域饮食", "actual_directions": ["不同地区火锅锅底为什么不同"]},
        ],
        "named_candidates": [],
        "unknowns": [],
    }


def _focused_model() -> SequencedStructuredFakeModel:
    return SequencedStructuredFakeModel(
        {
            SemanticReadingDraft: _semantic_payload(),
            SharedWorldSynthesisDraft: _shared_world_payload(),
            ContentRootCandidateSetDraft: _root_candidate_set_payload(),
            ContentRootDecisionDraft: _root_decision_payload(),
            FrozenContentMapDraft: _frozen_map_payload(),
        }
    )


def _payload() -> dict[str, Any]:
    return {
        "observations": [
            {
                "observation_id": "observation-1",
                "claim": "用户说自己从事咖啡设备维修",
                "source_refs": ["source-user"],
            }
        ],
        "entities": [],
        "roles": [],
        "relations": [],
        "state_changes": [],
        "interpretations": [
            {
                "interpretation_id": "interpretation-1",
                "claim": "维修是商业服务，设备故障与咖啡出品是待验证的内容连接",
                "kind": "derived",
                "basis_refs": [{"kind": "observation", "ref_id": "observation-1"}],
                "limitations": ["用户还没有说明服务对象与主要故障类型"],
            }
        ],
        "counterevidence": [],
        "unknowns": [
            {
                "unknown_id": "unknown-1",
                "question": "主要客户是咖啡店还是家用用户？",
                "affects": ["content_world"],
            }
        ],
        "business_semantics": {
            "commercial_object": {
                "text": "咖啡设备维修服务",
                "basis_refs": [{"kind": "observation", "ref_id": "observation-1"}],
            },
            "lexical_head": {
                "text": "维修",
                "basis_refs": [{"kind": "observation", "ref_id": "observation-1"}],
            },
            "modifiers": [],
            "subject_actions": [],
            "summary": "先解释用户在做什么，不代替账号方案。",
            "unknown_refs": ["unknown-1"],
        },
        "content_world": {
            "source_object": "咖啡设备维修服务",
            "content_root": "咖啡设备故障与出品问题",
            "root_rationale": "这个世界围绕设备故障与出品关系展开，但仍需要具体故障证据。",
            "dimensions": [],
            "named_candidates": [
                {
                    "name": "一种常见故障类型",
                    "connection": "可能影响咖啡出品",
                    "kind": "hypothesis",
                    "basis_refs": [],
                    "verification_query": "该客户群最常见的设备故障是什么",
                    "limitations": ["尚无外部证据"],
                }
            ],
            "unknown_refs": ["unknown-1"],
        },
        "topic_brief": None,
    }


@pytest.mark.asyncio
async def test_analyzer_builds_one_shared_record_and_optional_views() -> None:
    model = StructuredFakeModel(_payload())
    request = ContentIntelligenceRequest(
        user_request="我是做咖啡设备维修的，这个账号可以讲什么？",
        subject_expression="我是做咖啡设备维修的",
        focus=AnalysisFocus.COMBINED,
        source_materials=(
            SourceMaterial(
                kind="customer_note",
                title="用户补充",
                content="目前只确认了维修服务，客户类型尚未确认。",
            ),
        ),
    )

    bundle = await analyze_content_intelligence(request, model=model, runnable_config={"callbacks": []})

    assert model.calls == 1
    assert model.schema is ContentIntelligenceDraft
    assert model.include_raw is True
    assert isinstance(model.messages[0], SystemMessage)
    assert isinstance(model.messages[1], HumanMessage)
    assert bundle.record.sources[0].source_id == "source-user"
    assert bundle.record.sources[1].source_id == "source-1"
    assert bundle.business_semantics is not None
    assert bundle.business_semantics.record_id == bundle.record.record_id
    assert bundle.content_world is not None
    assert bundle.content_world.record_id == bundle.record.record_id
    assert bundle.topic_brief is None


@pytest.mark.asyncio
async def test_system_method_is_domain_neutral_and_has_no_fixed_delivery_quota() -> None:
    model = _focused_model()
    request = ContentIntelligenceRequest(
        user_request="我是做咖啡设备维修的，这个账号可以讲什么？",
        subject_expression="我是做咖啡设备维修的",
        focus=AnalysisFocus.CONTENT_WORLD,
    )

    await analyze_content_intelligence(request, model=model)
    system_text = "\n".join(batch[0].content for batch in model.message_batches)

    assert "黄金礼品" not in system_text
    assert "海鲜" not in system_text
    assert "火锅底料" not in system_text
    assert "KTV" not in system_text
    assert "婚嫁" not in system_text
    assert "10 天" not in system_text
    assert "3 个候选" not in system_text
    assert "列表可以为空" in system_text
    assert "商业特异性不必重复在内容根中" in system_text
    assert "不是品类定义测验" in system_text
    assert "完整商品或服务没有先验优先权" in system_text
    assert "对象能够脱离某个场景独立存在，不足以否决" in system_text
    assert "具体人物、事件、关系、选择与跨时间空间的展开能力" in system_text
    assert "某种关系或场景很常见、很有内容，不等于它定义了该品类" not in system_text
    assert "去掉该关系或场景后，对象仍可独立成立、被识别和使用时，保留完整对象为内容根" not in system_text
    assert "优先保留该对象为最小完整中心" not in system_text
    assert "不得把对一个完整对象的制作、使用或消费动作冒充成更完整的对象" in system_text
    assert "地图边界只受已冻结内容根约束" in system_text
    assert "商品回桥" not in system_text
    assert "回到商品" not in system_text
    assert "不能把较窄对象与较宽关系世界拼成折中混合根" in system_text
    assert "不要用抽象的‘XX文化’代替已经识别出的具体活动与关系" in system_text
    assert "逐层拆解复合修饰关系" in system_text
    assert "输入只包含已冻结的内容根" in system_text
    assert "面向参与者的内容主题" in system_text
    assert "不得把活动改写成组织者的运营流程" in system_text
    assert "定价、获客、会员、排班、供应链、合规或交付管理" in system_text
    assert "向下的种类与子世界" in system_text
    assert "跨领域作品与公共对象" in system_text
    assert "叙事组织由后续选题模块负责" in FROZEN_CONTENT_MAP_SYSTEM_PROMPT
    assert "关系差异应按差异、协商、角色互动或融合表达" in FROZEN_CONTENT_MAP_SYSTEM_PROMPT
    assert "冲突" not in FROZEN_CONTENT_MAP_SYSTEM_PROMPT
    assert "博弈" not in FROZEN_CONTENT_MAP_SYSTEM_PROMPT
    assert "隐含场所或经营容器" in system_text
    assert "多种同时成立的构成功能" in system_text
    assert "情绪" in system_text
    assert "具体命名人物、事件、作品或日期" in system_text
    assert "提问动作、交付请求" in system_text
    assert "完整商业实体不自动等于" in system_text
    assert "持续发生的人类活动" in system_text
    assert "社交或情绪功能" in system_text
    assert "物理外壳、设备或卖方流程仍然存在" in system_text
    assert "品类身份和用户进入它的理由是否仍然成立" in system_text
    assert "优先比较它承载的完整对象或参与者活动" in system_text
    assert "不要贬低或删除语义阅读中同时成立的人类活动、社交功能和情绪功能" in CONTENT_WORLD_NARRATION_SYSTEM_PROMPT
    assert "不要把关系差异升级为戏剧阻碍或对抗结构" in CONTENT_WORLD_NARRATION_SYSTEM_PROMPT


@pytest.mark.asyncio
async def test_analyzer_rejects_a_model_observation_that_cannot_be_traced() -> None:
    payload = _payload()
    payload["observations"][0]["source_refs"] = ["source-invented"]
    model = StructuredFakeModel(payload)
    request = ContentIntelligenceRequest(
        user_request="我是做咖啡设备维修的",
        subject_expression="我是做咖啡设备维修的",
        focus=AnalysisFocus.BUSINESS_SEMANTICS,
    )

    with pytest.raises(ValidationError, match="unknown source"):
        await analyze_content_intelligence(request, model=model)


@pytest.mark.asyncio
async def test_same_sources_produce_the_same_record_id_across_requested_views() -> None:
    first_model = StructuredFakeModel(_payload())
    second_model = _focused_model()
    first_request = ContentIntelligenceRequest(
        user_request="解释这句业务表达",
        subject_expression="我是做咖啡设备维修的",
        focus=AnalysisFocus.BUSINESS_SEMANTICS,
    )
    second_request = first_request.model_copy(update={"user_request": "展开内容世界", "focus": AnalysisFocus.CONTENT_WORLD})

    first = await analyze_content_intelligence(first_request, model=first_model)
    second = await analyze_content_intelligence(second_request, model=second_model)

    assert first.record.record_id == second.record.record_id


@pytest.mark.asyncio
async def test_analyzer_decodes_provider_stringified_projection_objects_without_retry() -> None:
    payload = _payload()
    topic_path = {
        "path_id": "path-1",
        "steps": [
            {
                "from_label": "咖啡设备故障",
                "relation": "影响",
                "to_label": "咖啡出品",
                "basis_refs": [{"kind": "interpretation", "ref_id": "interpretation-1"}],
                "status": "grounded",
                "verification_needed": False,
            }
        ],
        "rationale": "这是当前选题的理解路径。",
    }
    payload["topic_brief"] = {
        "question": "咖啡为什么会因设备故障变难喝？",
        "central_claim": "部分口感问题可能来自设备状态，而不只是咖啡豆。",
        "mechanism": "从设备故障与出品问题的关系中形成待取证命题。",
        "counterpoint": "当前材料尚未证明任何具体故障与口感的因果关系。",
        "path": topic_path,
        "evidence_refs": [{"kind": "observation", "ref_id": "observation-1"}],
        "unknown_refs": ["unknown-1"],
        "research_needed": ["取得具体故障与出品变化的可核验材料"],
    }
    for field in ("business_semantics", "content_world", "topic_brief"):
        payload[field] = json.dumps(payload[field], ensure_ascii=False)
    model = StructuredFakeModel(payload)
    request = ContentIntelligenceRequest(
        user_request="我是做咖啡设备维修的，这个账号可以讲什么？",
        subject_expression="我是做咖啡设备维修的",
        focus=AnalysisFocus.COMBINED,
    )

    bundle = await analyze_content_intelligence(request, model=model)

    assert model.calls == 1
    assert bundle.business_semantics is not None
    assert bundle.content_world is not None
    assert bundle.topic_brief is not None


@pytest.mark.asyncio
async def test_content_world_focus_uses_semantic_attention_before_map_expansion() -> None:
    model = _focused_model()
    request = ContentIntelligenceRequest(
        user_request="我是做重庆火锅底料的，我要怎么起号？",
        subject_expression="我是做重庆火锅底料的",
        focus=AnalysisFocus.CONTENT_WORLD,
    )

    bundle = await analyze_content_intelligence(request, model=model)

    assert model.schemas == [
        SemanticReadingDraft,
        SharedWorldSynthesisDraft,
        ContentRootCandidateSetDraft,
        ContentRootDecisionDraft,
        FrozenContentMapDraft,
    ]
    assert model.include_raw_flags == [True, True, True, True, True]
    assert model.calls == 5
    assert "怎么起号" not in model.message_batches[0][1].content
    assert "怎么起号" not in model.message_batches[1][1].content
    assert "怎么起号" not in model.message_batches[2][1].content
    assert "怎么起号" not in model.message_batches[3][1].content
    assert "怎么起号" not in model.message_batches[4][1].content
    assert "intermediate_enabler" in model.message_batches[2][1].content
    assert '"world_label": "围绕火锅的共同用餐生活"' in model.message_batches[2][1].content
    assert '"label": "火锅"' in model.message_batches[3][1].content
    assert '"primary_content_center": "火锅"' in model.message_batches[4][1].content
    assert "重庆火锅底料" not in model.message_batches[4][1].content
    assert "semantic_reading" not in model.message_batches[4][1].content
    assert "source_object" not in model.message_batches[4][1].content
    assert "object_anchor" not in model.message_batches[4][1].content
    assert "bridge_path" not in model.message_batches[4][1].content
    assert "商品" not in model.message_batches[4][0].content
    assert "销售" not in model.message_batches[4][0].content
    assert bundle.business_semantics.offering_role == "intermediate_enabler"
    assert bundle.business_semantics.served_objects[0].text == "火锅"
    assert bundle.business_semantics.served_activities[0].text == "制作火锅"
    assert bundle.content_world.content_root == "火锅"
    assert bundle.content_world.dimensions[0].paths[0].steps[0].to_label == "不同地区火锅锅底为什么不同"


@pytest.mark.asyncio
async def test_analyzer_recovers_provider_json_message_content_without_retry() -> None:
    model = RawContentSequencedFakeModel(
        {
            SemanticReadingDraft: _semantic_payload(),
            SharedWorldSynthesisDraft: _shared_world_payload(),
            ContentRootCandidateSetDraft: _root_candidate_set_payload(),
            ContentRootDecisionDraft: _root_decision_payload(),
            FrozenContentMapDraft: _frozen_map_payload(),
        }
    )
    request = ContentIntelligenceRequest(
        user_request="我是做重庆火锅底料的，我要怎么起号？",
        subject_expression="我是做重庆火锅底料的",
        focus=AnalysisFocus.CONTENT_WORLD,
    )

    bundle = await analyze_content_intelligence(request, model=model)

    assert model.calls == 5
    assert bundle.business_semantics.offering_role == "intermediate_enabler"
    assert bundle.content_world.content_root == "火锅"


@pytest.mark.asyncio
async def test_analyzer_recovers_safe_python_literal_in_invalid_tool_arguments() -> None:
    model = MalformedToolArgumentsSequencedFakeModel(
        {
            SemanticReadingDraft: _semantic_payload(),
            SharedWorldSynthesisDraft: _shared_world_payload(),
            ContentRootCandidateSetDraft: _root_candidate_set_payload(),
            ContentRootDecisionDraft: _root_decision_payload(),
            FrozenContentMapDraft: _frozen_map_payload(),
        }
    )

    bundle = await analyze_content_intelligence(
        ContentIntelligenceRequest(
            user_request="我是做重庆火锅底料的，我要怎么起号？",
            subject_expression="我是做重庆火锅底料的",
            focus=AnalysisFocus.CONTENT_WORLD,
        ),
        model=model,
    )

    assert model.calls == 5
    assert bundle.content_world.content_root == "火锅"
    assert bundle.record.unknowns[-1].question == "待核验"


@pytest.mark.asyncio
async def test_analyzer_retries_one_structurally_invalid_specialist_response() -> None:
    model = RetryableMalformedMapFakeModel(
        {
            SemanticReadingDraft: _semantic_payload(),
            SharedWorldSynthesisDraft: _shared_world_payload(),
            ContentRootCandidateSetDraft: _root_candidate_set_payload(),
            ContentRootDecisionDraft: _root_decision_payload(),
            FrozenContentMapDraft: _frozen_map_payload(),
        }
    )

    bundle = await analyze_content_intelligence(
        ContentIntelligenceRequest(
            user_request="我是做重庆火锅底料的，我要怎么起号？",
            subject_expression="我是做重庆火锅底料的",
            focus=AnalysisFocus.CONTENT_WORLD,
        ),
        model=model,
    )

    assert model.map_attempts == 2
    assert model.calls == 6
    assert len(model.message_batches[-1]) == 3
    assert "只重新返回符合结构合同的内容" in model.message_batches[-1][-1].content
    assert bundle.content_world.content_root == "火锅"


def test_root_selection_requires_the_chosen_root_to_be_an_explicit_candidate() -> None:
    payload = _root_selection_payload()
    payload["selected_candidate_index"] = 99

    with pytest.raises(ValidationError, match="explicit candidate"):
        ContentRootSelectionDraft.model_validate(payload)


def test_root_selection_rejects_a_narrow_example_branch_as_the_content_root() -> None:
    payload = {
        "source_object": "黄金礼品",
        "candidates": [
            {
                "level": "social_or_cultural_world",
                "label": "送礼与人情往来",
                "scope_role": "root_candidate",
                "relation_to_business": "礼品反复进入赠送、收受与回礼关系",
                "strength": "覆盖婚嫁、节庆、商务与人生礼仪等平行场景",
                "overreach_risk": "不能扩成与礼品无关的泛人际关系",
            },
            {
                "level": "social_or_cultural_world",
                "label": "婚嫁礼俗",
                "scope_role": "example_branch",
                "relation_to_business": "黄金礼品可能进入的一种具体赠礼场景",
                "strength": "人物、礼仪与事件丰富",
                "overreach_risk": "它只是多个平行场景之一，不能代表全部黄金礼品业务",
            },
        ],
        "selected_candidate_index": 1,
        "audience_territory_candidate_index": 0,
        "root_rationale": "婚嫁内容很丰富。",
        "unknowns": [],
    }

    with pytest.raises(ValidationError, match="example branch cannot be selected"):
        ContentRootSelectionDraft.model_validate(payload)


@pytest.mark.asyncio
async def test_gold_gift_keeps_human_relations_as_root_and_wedding_as_a_map_branch() -> None:
    semantic = {
        "source_object": "黄金礼品",
        "lexical_head": "礼品",
        "modifiers": [
            {
                "term": "黄金",
                "relation": "材质",
                "modifies": "礼品",
                "removal_counterfactual": "去掉材质后仍是可赠送和收受的礼品",
            }
        ],
        "offering_role": "complete_object_or_service",
        "role_rationale": "黄金是材质，礼品是完整赠送对象。",
        "served_objects": ["黄金材质的礼品"],
        "served_activities": ["送礼", "收礼", "回礼"],
        "defining_functions_or_uses": ["通过礼物表达情感、关系与礼数"],
        "social_or_cultural_frames": ["婚嫁礼俗", "节庆赠礼", "商务馈赠", "人生礼仪"],
        "seller_actions": [],
        "uncertainties": [],
    }
    candidates = {
        "source_object": "黄金礼品",
        "candidates": [
            {
                "level": "commercial_object",
                "label": "黄金礼品",
                "scope_role": "root_candidate",
                "relation_to_business": "直接经营对象",
                "strength": "具体",
                "overreach_risk": "容易停在工艺和选款",
            },
            {
                "level": "social_or_cultural_world",
                "label": "送礼与人情往来",
                "scope_role": "root_candidate",
                "relation_to_business": "礼品的定义性人际功能",
                "strength": "覆盖反复发生的赠受、回礼与关系表达",
                "overreach_risk": "不能扩成与礼品无关的泛关系话题",
            },
            {
                "level": "social_or_cultural_world",
                "label": "婚嫁礼俗",
                "scope_role": "example_branch",
                "relation_to_business": "平行赠礼场景之一",
                "strength": "有具体人物与仪式",
                "overreach_risk": "会排除节庆、商务和其他人生礼仪",
            },
        ],
        "unknowns": [],
    }
    decision = {
        "selected_candidate_index": 1,
        "audience_territory_candidate_index": 1,
        "root_rationale": "礼品的长期内容来自反复发生的赠受与人情关系；婚嫁只是其中一个分支。",
        "unknowns": [],
    }
    content_map = {
        "map_directions": [
            {
                "dimension": "人生礼仪",
                "actual_directions": ["婚嫁中的赠礼与回礼", "满月、祝寿与节庆中的礼数"],
            }
        ],
        "named_candidates": [],
        "unknowns": [],
    }
    model = SequencedStructuredFakeModel(
        {
            SemanticReadingDraft: semantic,
            SharedWorldSynthesisDraft: {
                "common_action_or_relation": "通过赠送、收受与回礼表达情感和维系关系",
                "participant_relationship": "赠礼者、收礼者与相关关系人",
                "world_label": "送礼与人情往来",
                "covered_frames": ["婚嫁礼俗", "节庆赠礼", "商务馈赠", "人生礼仪"],
                "limitations": ["不能扩成与礼品无关的泛人际关系"],
            },
            ContentRootCandidateSetDraft: candidates,
            ContentRootDecisionDraft: decision,
            FrozenContentMapDraft: content_map,
        }
    )

    bundle = await analyze_content_intelligence(
        ContentIntelligenceRequest(
            user_request="我是做黄金礼品的，我要怎么起号？",
            subject_expression="我是做黄金礼品的",
            focus=AnalysisFocus.CONTENT_WORLD,
        ),
        model=model,
    )

    assert bundle.content_world.content_root == "送礼与人情往来"
    assert bundle.content_world.audience_territory.text == "送礼与人情往来"
    shared_world_input = model.message_batches[1][1].content
    assert '"unmodified_subject": "礼品"' in shared_world_input
    assert "黄金" not in shared_world_input
    assert "保值" not in shared_world_input
    assert '"primary_content_center": "送礼与人情往来"' in model.message_batches[4][1].content
    assert "婚嫁" not in model.message_batches[4][1].content
    assert bundle.content_world.dimensions[0].paths[0].steps[0].to_label == "婚嫁中的赠礼与回礼"


def test_root_selection_schema_does_not_own_commercial_return_design() -> None:
    properties = ContentRootSelectionDraft.model_json_schema()["properties"]

    assert "object_anchor" not in properties
    assert "bridge_path" not in properties


def test_frozen_map_schema_cannot_reselect_the_content_root() -> None:
    properties = FrozenContentMapDraft.model_json_schema()["properties"]

    assert "primary_content_center" not in properties
    assert "object_anchor" not in properties
    assert "audience_territory" not in properties


@pytest.mark.asyncio
async def test_content_world_narrator_only_converges_the_frozen_map() -> None:
    bundle = await analyze_content_intelligence(
        ContentIntelligenceRequest(
            user_request="我是做重庆火锅底料的，我要怎么起号？",
            subject_expression="我是做重庆火锅底料的",
            focus=AnalysisFocus.CONTENT_WORLD,
        ),
        model=_focused_model(),
    )
    narration = "# 火锅\n\n底料是完成火锅的中间载体，内容世界应进入火锅本身。\n\n## 地域与饮食习惯\n\n从“为什么这里吃这种火锅”理解地域环境和生活。\n\n- 不同地区火锅锅底为什么不同"
    narrator = PlainNarrationFakeModel(narration)

    draft = await synthesize_content_world_narration(
        bundle,
        model=narrator,
        runnable_config={"callbacks": ["user-visible-stream"]},
    )
    rendered = render_content_world_narration(bundle, draft)

    assert narrator.calls == 1
    assert narrator.configs == [{"callbacks": []}]
    narration_input = narrator.message_batches[0][1].content
    assert '"content_root": "火锅"' in narration_input
    assert '"offering_role": "intermediate_enabler"' in narration_input
    assert '"served_objects"' in narration_input
    assert '"served_activities"' in narration_input
    assert '"root_rationale": "底料是中间实现物，火锅是完整对象世界。"' in narration_input
    assert "root_candidates" not in narration_input
    assert "unknowns" not in narration_input
    assert "bridge" not in narration_input.lower()
    assert "正文到内容判断为止" in narrator.message_batches[0][0].content
    assert "商品回桥" not in narrator.message_batches[0][0].content
    assert "商品" not in narrator.message_batches[0][0].content
    assert "产品" not in narrator.message_batches[0][0].content
    assert rendered == narration
    assert "不同地区火锅锅底为什么不同" in rendered
    assert "平台" not in rendered
    assert "请告诉我" not in rendered
