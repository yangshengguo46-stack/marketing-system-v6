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
    SourceMaterial,
    analyze_content_intelligence,
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
            "root_rationale": "这个世界能回到维修服务，但仍需要客户信息验证。",
            "return_path": {
                "path_id": "path-1",
                "steps": [
                    {
                        "from_label": "咖啡设备维修服务",
                        "relation": "解决",
                        "to_label": "设备故障与出品问题",
                        "basis_refs": [{"kind": "interpretation", "ref_id": "interpretation-1"}],
                        "status": "grounded",
                        "verification_needed": False,
                    }
                ],
                "rationale": "保留与商业对象的回程。",
            },
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
    model = StructuredFakeModel(_payload())
    request = ContentIntelligenceRequest(
        user_request="我是做咖啡设备维修的，这个账号可以讲什么？",
        subject_expression="我是做咖啡设备维修的",
        focus=AnalysisFocus.CONTENT_WORLD,
    )

    await analyze_content_intelligence(request, model=model)
    system_text = model.messages[0].content

    assert "黄金礼品" not in system_text
    assert "海鲜" not in system_text
    assert "火锅底料" not in system_text
    assert "10 天" not in system_text
    assert "3 个候选" not in system_text
    assert "列表可以为空" in system_text


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
    second_model = StructuredFakeModel(_payload())
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
    payload["topic_brief"] = {
        "question": "咖啡为什么会因设备故障变难喝？",
        "central_claim": "部分口感问题可能来自设备状态，而不只是咖啡豆。",
        "mechanism": "从设备故障与出品问题的关系中形成待取证命题。",
        "counterpoint": "当前材料尚未证明任何具体故障与口感的因果关系。",
        "path": payload["content_world"]["return_path"],
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
