from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import pytest

from deerflow.incubation.contracts import ArtifactEnvelope, ProjectRef
from deerflow.incubation.format_decision import FormatDecisionDraft
from deerflow.incubation.format_runtime import (
    FORMAT_DECISION_MODEL_INPUT_MAX_BYTES,
    FORMAT_DECISION_SYSTEM_PROMPT,
    FormatDecisionModelError,
    generate_format_decision,
)

NOW = datetime(2026, 8, 17, 21, 0, tzinfo=UTC)
PROJECT = ProjectRef(owner_user_id="user-1", project_id="golden-gift")


def _artifact(
    *,
    artifact_type: str,
    payload: dict[str, object],
    project: ProjectRef = PROJECT,
    evidence_role: str | None = None,
) -> ArtifactEnvelope:
    return ArtifactEnvelope.seal(
        project=project,
        artifact_type=artifact_type,
        version=1,
        payload=payload,
        evidence_role=evidence_role,
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-1",
    )


def _message_plan(*, extra_payload: dict[str, object] | None = None) -> ArtifactEnvelope:
    payload: dict[str, object] = {
        "message_plan_id": "message-plan-1",
        "record_id": "record-golden-gift",
        "topic_title": "古代的礼，为什么不只是礼貌？",
        "focal_subject": "生活在礼制中的普通人",
        "context": "古代社会的日常交往中",
        "concrete_event_or_question": "人们为什么需要用一套礼安排彼此的关系",
        "account_position": "从一名礼品经营者的真实观察出发",
        "account_position_basis": "我是做黄金礼品的",
        "point_of_view": "礼的作用之一，是把人与人的关系变成共同理解的秩序。",
        "entry_point": "从今天把礼理解成礼貌这个误会讲起",
        "telling_lens": "跟着礼的含义变化理解关系如何被安排",
        "audience_question": "为什么古人把礼看得如此重要",
        "information_order": "先辨认今天的直觉，再回到制度作用，最后说明边界",
        "payoff": "观众理解礼貌只是礼的一小部分",
        "opening": "今天说一个人有礼，通常只是说他有礼貌。",
        "message_beats": ["但在古代，礼还在安排身份、关系和行为。"],
        "closing": "礼崩坏，说的从来不只是大家突然没礼貌了。",
        "evidence_refs": [{"kind": "observation", "ref_id": "observation-gift-1"}],
        "limitations": ["当前只有一份有界公开资料。"],
        "unknown_refs": ["unknown-source-date"],
        "research_needed": [],
    }
    if extra_payload:
        payload.update(extra_payload)
    return _artifact(artifact_type="message_plan", payload=payload)


def _base_draft(message_plan: ArtifactEnvelope, *, extra_payload: dict[str, object] | None = None) -> ArtifactEnvelope:
    payload: dict[str, object] = {
        "draft_id": "base-draft-1",
        "message_plan_id": message_plan.payload["message_plan_id"],
        "text": "今天说一个人有礼，通常只是说他有礼貌。\n\n但在古代，礼还在安排身份、关系和行为。",
        "stage": "base",
    }
    if extra_payload:
        payload.update(extra_payload)
    return ArtifactEnvelope.seal(
        project=message_plan.project,
        artifact_type="draft_version",
        version=1,
        payload=payload,
        parents=(message_plan.to_parent_ref(),),
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-1",
    )


def _draft_payload(
    *,
    kind: str = "image_text",
    basis_artifact_ids: tuple[str, ...] = (),
    unknowns: tuple[str, ...] = (),
) -> dict[str, Any]:
    return {
        "status": "provisional" if unknowns else "confirmed",
        "selected_format": {"kind": kind},
        "selection_rationale": "这条内容需要先把抽象关系讲清，现有图文资料足以承载。",
        "resource_matches": [
            {
                "resource": "已授权的礼制器物图片",
                "fit": "可以承载礼从器物进入关系秩序的说明。",
                "basis_artifact_ids": list(basis_artifact_ids),
            }
        ]
        if basis_artifact_ids
        else [],
        "resource_gaps": [],
        "sustainability_risks": [],
        "alternatives": [],
        "unknowns": list(unknowns),
        "narrative_method_hint": None,
    }


@pytest.mark.asyncio
async def test_runtime_hands_exact_parents_to_the_model_and_sealer() -> None:
    message_plan = _message_plan()
    base_draft = _base_draft(message_plan)
    judgment = _artifact(
        artifact_type="incubation_judgment",
        payload={
            "presentation": {"decision": "优先选择低出镜压力的长期形式。"},
            "unknowns": ["尚未确认持续出镜意愿。"],
        },
    )
    resource = _artifact(
        artifact_type="media_observation",
        payload={"available_material": "已授权的礼制器物图片"},
        evidence_role="user_material",
    )
    seen: dict[str, object] = {}

    async def structured_model(schema, messages):
        seen["schema"] = schema
        seen["messages"] = messages
        return _draft_payload(basis_artifact_ids=(resource.artifact_id,))

    sealed = await generate_format_decision(
        project=PROJECT,
        message_plan_artifact=message_plan,
        base_draft_artifact=base_draft,
        structured_model=structured_model,
        incubation_judgment_artifact=judgment,
        resource_evidence_artifacts=(resource,),
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-2",
    )

    assert seen["schema"] is FormatDecisionDraft
    assert set(sealed.parents) == {
        message_plan.to_parent_ref(),
        base_draft.to_parent_ref(),
        judgment.to_parent_ref(),
        resource.to_parent_ref(),
    }
    assert sealed.payload["message_plan_binding"]["artifact_id"] == message_plan.artifact_id
    assert sealed.payload["base_draft_binding"]["artifact_id"] == base_draft.artifact_id
    assert sealed.payload["incubation_judgment_ref"]["artifact_id"] == judgment.artifact_id
    assert sealed.payload["resource_evidence_refs"][0]["artifact_id"] == resource.artifact_id

    messages = seen["messages"]
    assert isinstance(messages, tuple)
    model_input = messages[1].content
    assert len(model_input.encode("utf-8")) <= FORMAT_DECISION_MODEL_INPUT_MAX_BYTES
    rendered = json.loads(model_input)
    assert rendered["message_plan"]["artifact_id"] == message_plan.artifact_id
    assert rendered["base_draft"]["artifact_id"] == base_draft.artifact_id
    assert rendered["incubation_judgment"]["artifact_id"] == judgment.artifact_id
    assert rendered["resource_evidence"][0]["artifact_id"] == resource.artifact_id
    assert rendered["allowed_resource_basis_artifact_ids"] == [resource.artifact_id]


@pytest.mark.asyncio
async def test_model_failure_does_not_call_the_sealer(monkeypatch) -> None:
    import deerflow.incubation.format_runtime as runtime_module

    provider_error = RuntimeError("provider unavailable")
    sealed = False

    async def failing_model(schema, messages):
        raise provider_error

    def forbidden_seal(**kwargs):
        nonlocal sealed
        sealed = True
        raise AssertionError("a failed model result must not be sealed")

    monkeypatch.setattr(runtime_module, "seal_format_decision", forbidden_seal)

    with pytest.raises(FormatDecisionModelError, match="structured model") as exc_info:
        message_plan = _message_plan()
        await generate_format_decision(
            project=PROJECT,
            message_plan_artifact=message_plan,
            base_draft_artifact=_base_draft(message_plan),
            structured_model=failing_model,
            created_at=NOW,
            source_thread_id="thread-1",
            source_run_id="run-2",
        )

    assert sealed is False
    assert exc_info.value.__cause__ is provider_error


def test_runtime_draft_schema_has_no_upstream_body_or_script_fields() -> None:
    forbidden_fields = {
        "topic_brief",
        "topic_title",
        "point_of_view",
        "opening",
        "message_beats",
        "closing",
        "text",
        "script",
    }

    assert forbidden_fields.isdisjoint(FormatDecisionDraft.model_fields)
    assert "不能改写 TopicBrief 或 MessagePlan" in FORMAT_DECISION_SYSTEM_PROMPT


@pytest.mark.asyncio
async def test_non_narrative_choice_does_not_trigger_screenwriting_guidance() -> None:
    calls = 0

    async def structured_model(schema, messages):
        nonlocal calls
        calls += 1
        assert "编剧" not in messages[0].content
        assert "三幕" not in messages[0].content
        assert "目标、阻碍" not in messages[0].content
        return _draft_payload(kind="image_text")

    message_plan = _message_plan()
    sealed = await generate_format_decision(
        project=PROJECT,
        message_plan_artifact=message_plan,
        base_draft_artifact=_base_draft(message_plan),
        structured_model=structured_model,
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-2",
    )

    assert calls == 1
    assert sealed.payload["selected_format"]["kind"] == "image_text"
    assert sealed.payload["narrative_method_hint"] is None


@pytest.mark.asyncio
async def test_unknown_resources_remain_provisional_without_blocking_the_decision() -> None:
    async def unknown_model(schema, messages):
        assert "不要把未知变成硬问卷" in messages[0].content
        return _draft_payload(unknowns=("用户是否愿意出镜、可用素材、隐私边界和持续产能仍未知。",))

    message_plan = _message_plan()
    sealed = await generate_format_decision(
        project=PROJECT,
        message_plan_artifact=message_plan,
        base_draft_artifact=_base_draft(message_plan),
        structured_model=unknown_model,
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-2",
    )

    assert sealed.payload["status"] == "provisional"
    assert sealed.payload["unknowns"] == ["用户是否愿意出镜、可用素材、隐私边界和持续产能仍未知。"]
    assert len(sealed.parents) == 2


@pytest.mark.asyncio
async def test_model_payload_is_bounded_even_when_parent_payloads_are_large() -> None:
    huge_text = "很长的资源说明" * 20_000
    message_plan = _message_plan(extra_payload={"unrelated_internal_notes": huge_text})
    base_draft = _base_draft(message_plan, extra_payload={"unrelated_internal_notes": huge_text})
    resource = _artifact(
        artifact_type="media_observation",
        payload={"summary": huge_text},
        evidence_role="user_material",
    )

    async def structured_model(schema, messages):
        model_input = messages[1].content
        assert len(model_input.encode("utf-8")) <= FORMAT_DECISION_MODEL_INPUT_MAX_BYTES
        assert huge_text not in model_input
        return _draft_payload()

    await generate_format_decision(
        project=PROJECT,
        message_plan_artifact=message_plan,
        base_draft_artifact=base_draft,
        structured_model=structured_model,
        resource_evidence_artifacts=(resource,),
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-2",
    )


@pytest.mark.asyncio
async def test_runtime_rejects_non_user_material_resource_evidence_before_model_call() -> None:
    message_plan = _message_plan()
    benchmark = _artifact(
        artifact_type="benchmark_snapshot",
        payload={"observation": "对标账号常用纯素材"},
        evidence_role="benchmark_evidence",
    )
    called = False

    async def structured_model(schema, messages):
        nonlocal called
        called = True
        return _draft_payload()

    with pytest.raises(ValueError, match="media_observation"):
        await generate_format_decision(
            project=PROJECT,
            message_plan_artifact=message_plan,
            base_draft_artifact=_base_draft(message_plan),
            structured_model=structured_model,
            resource_evidence_artifacts=(benchmark,),
            created_at=NOW,
            source_thread_id="thread-1",
            source_run_id="run-2",
        )

    assert called is False


@pytest.mark.asyncio
async def test_runtime_rejects_mismatched_base_draft_before_model_call() -> None:
    message_plan = _message_plan()
    unrelated_plan = _message_plan(extra_payload={"message_plan_id": "message-plan-2"})
    called = False

    async def structured_model(schema, messages):
        nonlocal called
        called = True
        return _draft_payload()

    with pytest.raises(ValueError, match="exact message plan"):
        await generate_format_decision(
            project=PROJECT,
            message_plan_artifact=message_plan,
            base_draft_artifact=_base_draft(unrelated_plan),
            structured_model=structured_model,
            created_at=NOW,
            source_thread_id="thread-1",
            source_run_id="run-2",
        )

    assert called is False
