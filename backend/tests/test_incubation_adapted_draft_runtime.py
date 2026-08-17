from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import pytest

from deerflow.incubation.adapted_draft import AdaptedDraftDraft
from deerflow.incubation.adapted_draft_runtime import (
    ADAPTED_DRAFT_MODEL_INPUT_MAX_BYTES,
    ADAPTED_DRAFT_SYSTEM_PROMPT,
    AdaptedDraftModelError,
    generate_adapted_draft,
)
from deerflow.incubation.contracts import ArtifactEnvelope, ProjectRef
from deerflow.incubation.format_decision import (
    FormatChoice,
    FormatDecisionDraft,
    seal_format_decision,
)

NOW = datetime(2026, 8, 17, 22, 30, tzinfo=UTC)
PROJECT = ProjectRef(owner_user_id="user-1", project_id="golden-gift")
BASE_TEXT = "今天说一个人有礼，通常只是说他有礼貌。\n\n但在古代，礼还在安排身份、关系和行为。"


def _artifact(
    *,
    artifact_type: str,
    payload: dict[str, object],
    project: ProjectRef = PROJECT,
    parents: tuple = (),
) -> ArtifactEnvelope:
    return ArtifactEnvelope.seal(
        project=project,
        artifact_type=artifact_type,
        version=1,
        payload=payload,
        parents=parents,
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-1",
    )


def _parents(
    *,
    kind: str = "image_text",
    base_text: str = BASE_TEXT,
    format_extra: dict[str, object] | None = None,
) -> tuple[ArtifactEnvelope, ArtifactEnvelope]:
    message_plan = _artifact(
        artifact_type="message_plan",
        payload={
            "message_plan_id": "message-plan-1",
            "record_id": "record-1",
            "topic_title": "古代的礼，为什么不只是礼貌？",
            "focal_subject": "古代社会中的普通人",
            "concrete_event_or_question": "礼如何安排关系",
            "point_of_view": "礼先规定关系，再规定行为。",
            "evidence_refs": [],
            "limitations": [],
            "unknown_refs": [],
            "research_needed": [],
        },
    )
    base_draft = _artifact(
        artifact_type="draft_version",
        payload={
            "draft_id": "base-draft-1",
            "message_plan_id": "message-plan-1",
            "text": base_text,
            "stage": "base",
        },
        parents=(message_plan.to_parent_ref(),),
    )
    format_draft_values: dict[str, object] = {
        "status": "confirmed",
        "selected_format": FormatChoice(kind=kind),
        "selection_rationale": "把基础稿翻译成适合阅读的表现形式。",
    }
    if format_extra:
        format_draft_values.update(format_extra)
    format_decision = seal_format_decision(
        project=PROJECT,
        draft=FormatDecisionDraft.model_validate(format_draft_values),
        message_plan_artifact=message_plan,
        base_draft_artifact=base_draft,
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-1",
    )
    return format_decision, base_draft


def _model_payload(*, source_excerpt: str | None = None) -> dict[str, Any]:
    return {
        "units": [
            {
                "unit_id": "unit-1",
                "mode": "on_screen_text",
                "adapted_expression": "有礼，在今天常常只被理解成有礼貌。",
                "source_excerpts": [source_excerpt or "今天说一个人有礼，通常只是说他有礼貌。"],
                "visual_treatment": "让这句话先单独出现。",
                "narrative_treatment": None,
            }
        ]
    }


@pytest.mark.asyncio
async def test_runtime_validates_parents_then_hands_bounded_source_to_model() -> None:
    format_decision, base_draft = _parents()
    seen: dict[str, object] = {}

    async def structured_model(schema, messages):
        seen["schema"] = schema
        seen["messages"] = messages
        return _model_payload()

    sealed = await generate_adapted_draft(
        project=PROJECT,
        base_draft_artifact=base_draft,
        format_decision_artifact=format_decision,
        structured_model=structured_model,
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-2",
    )

    assert seen["schema"] is AdaptedDraftDraft
    messages = seen["messages"]
    rendered = json.loads(messages[1].content)
    assert len(messages[1].content.encode("utf-8")) <= ADAPTED_DRAFT_MODEL_INPUT_MAX_BYTES
    assert rendered["base_draft"]["artifact_id"] == base_draft.artifact_id
    assert rendered["base_draft"]["text"] == BASE_TEXT
    assert rendered["format_decision"]["artifact_id"] == format_decision.artifact_id
    assert rendered["format_decision"]["selected_format"]["kind"] == "image_text"
    assert "topic_title" not in messages[1].content
    assert "evidence_refs" not in messages[1].content
    assert set(sealed.parents) == {
        base_draft.to_parent_ref(),
        format_decision.to_parent_ref(),
    }


@pytest.mark.asyncio
async def test_parent_lineage_failure_happens_before_the_model_call() -> None:
    format_decision, _ = _parents()
    _, unrelated_base = _parents(base_text="另一份基础稿。")
    called = False

    async def structured_model(schema, messages):
        nonlocal called
        called = True
        return _model_payload()

    with pytest.raises(ValueError, match="exact base draft"):
        await generate_adapted_draft(
            project=PROJECT,
            base_draft_artifact=unrelated_base,
            format_decision_artifact=format_decision,
            structured_model=structured_model,
            created_at=NOW,
            source_thread_id="thread-1",
            source_run_id="run-2",
        )

    assert called is False


@pytest.mark.asyncio
async def test_model_or_source_contract_failure_does_not_call_the_sealer(
    monkeypatch,
) -> None:
    import deerflow.incubation.adapted_draft_runtime as runtime_module

    format_decision, base_draft = _parents()
    sealed = False

    def forbidden_seal(**kwargs):
        nonlocal sealed
        sealed = True
        raise AssertionError("an invalid adaptation must not be sealed")

    monkeypatch.setattr(runtime_module, "seal_adapted_draft", forbidden_seal)

    async def invalid_model(schema, messages):
        return _model_payload(source_excerpt="基础稿里没有这句话")

    with pytest.raises(AdaptedDraftModelError, match="invalid adapted draft"):
        await generate_adapted_draft(
            project=PROJECT,
            base_draft_artifact=base_draft,
            format_decision_artifact=format_decision,
            structured_model=invalid_model,
            created_at=NOW,
            source_thread_id="thread-1",
            source_run_id="run-2",
        )

    assert sealed is False


@pytest.mark.asyncio
async def test_provider_failure_does_not_call_the_sealer(monkeypatch) -> None:
    import deerflow.incubation.adapted_draft_runtime as runtime_module

    format_decision, base_draft = _parents()
    provider_error = RuntimeError("provider unavailable")
    sealed = False

    async def failing_model(schema, messages):
        raise provider_error

    def forbidden_seal(**kwargs):
        nonlocal sealed
        sealed = True
        raise AssertionError("a failed model result must not be sealed")

    monkeypatch.setattr(runtime_module, "seal_adapted_draft", forbidden_seal)

    with pytest.raises(AdaptedDraftModelError, match="structured model") as exc_info:
        await generate_adapted_draft(
            project=PROJECT,
            base_draft_artifact=base_draft,
            format_decision_artifact=format_decision,
            structured_model=failing_model,
            created_at=NOW,
            source_thread_id="thread-1",
            source_run_id="run-2",
        )

    assert sealed is False
    assert exc_info.value.__cause__ is provider_error


@pytest.mark.asyncio
async def test_runtime_input_is_bounded_and_omits_unrelated_format_payload() -> None:
    huge = "很长但与适配无关的说明" * 10_000
    base_text = "今天说一个人有礼，通常只是说他有礼貌。" + ("正文" * 20_000)
    format_decision, base_draft = _parents(
        base_text=base_text,
        format_extra={"resource_gaps": (huge,), "unknowns": (huge,)},
    )

    async def structured_model(schema, messages):
        rendered = messages[1].content
        assert len(rendered.encode("utf-8")) <= ADAPTED_DRAFT_MODEL_INPUT_MAX_BYTES
        assert huge not in rendered
        return _model_payload()

    sealed = await generate_adapted_draft(
        project=PROJECT,
        base_draft_artifact=base_draft,
        format_decision_artifact=format_decision,
        structured_model=structured_model,
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-2",
    )
    assert sealed.artifact_type == "adapted_draft"


def test_runtime_prompt_keeps_adaptation_below_content_and_operations() -> None:
    required_boundaries = (
        "不得换题",
        "不得添加事实",
        "连续逐字",
        "销售",
        "平台",
        "固定时长",
        "真实人物经历",
    )
    for boundary in required_boundaries:
        assert boundary in ADAPTED_DRAFT_SYSTEM_PROMPT
