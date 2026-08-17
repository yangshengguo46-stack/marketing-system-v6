from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import pytest

from deerflow.incubation.adapted_draft import (
    AdaptedDraftDraft,
    PresentationUnitDraft,
    seal_adapted_draft,
)
from deerflow.incubation.contracts import ArtifactEnvelope, ProjectRef
from deerflow.incubation.format_decision import (
    FormatChoice,
    FormatDecisionDraft,
    ResourceMatch,
    seal_format_decision,
)
from deerflow.incubation.production_plan import ProductionPlanDraft
from deerflow.incubation.production_runtime import (
    PRODUCTION_PLAN_MODEL_INPUT_MAX_BYTES,
    PRODUCTION_PLAN_SYSTEM_PROMPT,
    ProductionPlanModelError,
    generate_production_plan,
)

NOW = datetime(2026, 8, 18, 2, 0, tzinfo=UTC)
PROJECT = ProjectRef(owner_user_id="user-1", project_id="golden-gift")
BASE_TEXT = "今天说一个人有礼，通常只是说他有礼貌。\n\n但在古代，礼还在安排身份、关系和行为。"


def _artifact(
    *,
    artifact_type: str,
    payload: dict[str, object],
    project: ProjectRef = PROJECT,
    parents: tuple = (),
    evidence_role: str | None = None,
) -> ArtifactEnvelope:
    return ArtifactEnvelope.seal(
        project=project,
        artifact_type=artifact_type,
        version=1,
        payload=payload,
        parents=parents,
        evidence_role=evidence_role,
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-1",
    )


def _user_material(
    label: str,
    *,
    project: ProjectRef = PROJECT,
    role: str = "user_material",
    extra_payload: dict[str, object] | None = None,
) -> ArtifactEnvelope:
    payload: dict[str, object] = {
        "source_ref": f"artifact://user-material/{label}",
        "observation_kind": "video_metadata",
        "observation": {"summary": label},
        "limitations": ["只证明用户已授权提供该素材，不证明传播效果。"],
    }
    if extra_payload:
        payload.update(extra_payload)
    return _artifact(
        artifact_type="media_observation",
        payload=payload,
        project=project,
        evidence_role=role,
    )


def _parents(
    *,
    kind: str = "image_text",
    materials: tuple[ArtifactEnvelope, ...] = (),
    adapted_expression: str = BASE_TEXT,
) -> tuple[ArtifactEnvelope, ArtifactEnvelope]:
    message_plan = _artifact(
        artifact_type="message_plan",
        payload={
            "message_plan_id": "message-plan-1",
            "record_id": "record-1",
            "topic_title": "古代的礼，为什么不只是礼貌？",
            "focal_subject": "古代社会中的普通人",
            "concrete_event_or_question": "礼如何安排人与人之间的关系",
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
            "text": BASE_TEXT,
            "stage": "base",
        },
        parents=(message_plan.to_parent_ref(),),
    )
    material_ids = tuple(material.artifact_id for material in materials)
    decision = seal_format_decision(
        project=PROJECT,
        draft=FormatDecisionDraft(
            status="confirmed" if materials else "provisional",
            selected_format=FormatChoice(kind=kind),
            selection_rationale="按既定内容和已知资源选择承载形式。",
            resource_matches=(
                ResourceMatch(
                    resource="用户已授权素材",
                    fit="可承载适配稿中已经确定的表达。",
                    basis_artifact_ids=material_ids,
                ),
            )
            if materials
            else (),
            resource_gaps=() if materials else ("尚无已确认素材。",),
            unknowns=() if materials else ("可用素材仍未知。",),
        ),
        message_plan_artifact=message_plan,
        base_draft_artifact=base_draft,
        resource_evidence_artifacts=materials,
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-1",
    )
    adapted = seal_adapted_draft(
        project=PROJECT,
        draft=AdaptedDraftDraft(
            units=(
                PresentationUnitDraft(
                    unit_id="unit-1",
                    mode="on_screen_text",
                    adapted_expression=adapted_expression,
                    source_excerpts=(BASE_TEXT,),
                    visual_treatment="把既定表达排成可阅读的画面。",
                ),
            )
        ),
        base_draft_artifact=base_draft,
        format_decision_artifact=decision,
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-1",
    )
    return decision, adapted


def _model_payload(
    *,
    material_id: str | None = None,
    action_kind: str = "text_layout",
    narrative_hint: str | None = None,
) -> dict[str, Any]:
    if material_id is None:
        asset = {
            "asset_id": "asset-text-card",
            "kind": "text_graphic",
            "purpose": "承载适配稿中已经确定的文字表达。",
            "source": "derived_from_adapted_draft",
            "basis_artifact_ids": [],
        }
        gaps = ["尚未确认可用的用户素材。"]
        unknowns = ["视觉素材来源仍未知。"]
    else:
        asset = {
            "asset_id": "asset-user-image",
            "kind": "image",
            "purpose": "承载适配稿已经明确的视觉说明。",
            "source": "existing_user_material",
            "basis_artifact_ids": [material_id],
        }
        gaps = []
        unknowns = []
    return {
        "status": "provisional" if gaps or unknowns else "ready",
        "asset_requirements": [asset],
        "production_actions": [
            {
                "action_id": "action-1",
                "kind": action_kind,
                "instruction": "只把适配稿的既定表达落实到对应素材。",
                "asset_ids": [asset["asset_id"]],
            }
        ],
        "assembly_steps": [
            {
                "step_id": "assembly-1",
                "instruction": "按适配单元的原有顺序装配。",
                "input_asset_ids": [asset["asset_id"]],
            }
        ],
        "resource_gaps": gaps,
        "unknowns": unknowns,
        "limitations": ["本计划不改变选题、观点或事实。"],
        "narrative_execution_hint": narrative_hint,
    }


@pytest.mark.asyncio
async def test_runtime_validates_exact_parents_and_projects_a_bounded_execution_input() -> None:
    used = _user_material("已授权礼制图片")
    unused = _user_material("已授权环境空镜")
    decision, adapted = _parents(materials=(used, unused))
    seen: dict[str, object] = {}

    async def structured_model(schema, messages):
        seen["schema"] = schema
        seen["messages"] = messages
        return _model_payload(material_id=used.artifact_id)

    sealed = await generate_production_plan(
        project=PROJECT,
        adapted_draft_artifact=adapted,
        format_decision_artifact=decision,
        user_material_artifacts=(unused, used),
        structured_model=structured_model,
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-2",
    )

    assert seen["schema"] is ProductionPlanDraft
    messages = seen["messages"]
    rendered = json.loads(messages[1].content)
    assert len(messages[1].content.encode("utf-8")) <= PRODUCTION_PLAN_MODEL_INPUT_MAX_BYTES
    assert rendered["adapted_draft"]["artifact_id"] == adapted.artifact_id
    assert rendered["adapted_draft"]["adapted_body_sha256"] == adapted.payload["adapted_body_sha256"]
    assert rendered["format_decision"]["selected_format"]["kind"] == "image_text"
    units = json.loads(rendered["adapted_draft"]["units_excerpt"])
    assert units[0]["adapted_expression"] == BASE_TEXT
    assert rendered["allowed_user_material_artifact_ids"] == sorted([used.artifact_id, unused.artifact_id])
    assert {item["artifact_id"] for item in rendered["reviewed_user_materials"]} == {
        used.artifact_id,
        unused.artifact_id,
    }
    assert set(sealed.parents) == {
        adapted.to_parent_ref(),
        decision.to_parent_ref(),
        used.to_parent_ref(),
    }


@pytest.mark.asyncio
async def test_unreviewed_material_is_rejected_before_the_model_call() -> None:
    reviewed = _user_material("已审阅素材")
    unreviewed = _user_material("未审阅素材")
    decision, adapted = _parents(materials=(reviewed,))
    called = False

    async def structured_model(schema, messages):
        nonlocal called
        called = True
        return _model_payload()

    with pytest.raises(ValueError, match="reviewed by the exact format decision"):
        await generate_production_plan(
            project=PROJECT,
            adapted_draft_artifact=adapted,
            format_decision_artifact=decision,
            user_material_artifacts=(unreviewed,),
            structured_model=structured_model,
            created_at=NOW,
            source_thread_id="thread-1",
            source_run_id="run-2",
        )

    assert called is False


@pytest.mark.asyncio
async def test_more_than_eight_reviewed_materials_are_rejected_before_model_call() -> None:
    materials = tuple(_user_material(f"素材-{index}") for index in range(9))
    decision, adapted = _parents(materials=materials)
    called = False

    async def structured_model(schema, messages):
        nonlocal called
        called = True
        return _model_payload()

    with pytest.raises(ValueError, match="at most 8"):
        await generate_production_plan(
            project=PROJECT,
            adapted_draft_artifact=adapted,
            format_decision_artifact=decision,
            user_material_artifacts=materials,
            structured_model=structured_model,
            created_at=NOW,
            source_thread_id="thread-1",
            source_run_id="run-2",
        )

    assert called is False


@pytest.mark.asyncio
async def test_model_cannot_claim_an_unprovided_user_resource_or_reach_the_sealer(monkeypatch) -> None:
    import deerflow.incubation.production_runtime as runtime_module

    decision, adapted = _parents()
    sealed = False

    def forbidden_seal(**kwargs):
        nonlocal sealed
        sealed = True
        raise AssertionError("invalid production output must not be sealed")

    monkeypatch.setattr(runtime_module, "seal_production_plan", forbidden_seal)

    async def structured_model(schema, messages):
        return _model_payload(material_id="artifact_not-provided")

    with pytest.raises(ProductionPlanModelError, match="invalid production plan"):
        await generate_production_plan(
            project=PROJECT,
            adapted_draft_artifact=adapted,
            format_decision_artifact=decision,
            structured_model=structured_model,
            created_at=NOW,
            source_thread_id="thread-1",
            source_run_id="run-2",
        )

    assert sealed is False


@pytest.mark.asyncio
async def test_non_narrative_model_output_cannot_force_performance_before_sealing(monkeypatch) -> None:
    import deerflow.incubation.production_runtime as runtime_module

    decision, adapted = _parents(kind="image_text")
    sealed = False

    def forbidden_seal(**kwargs):
        nonlocal sealed
        sealed = True
        raise AssertionError("invalid production output must not be sealed")

    monkeypatch.setattr(runtime_module, "seal_production_plan", forbidden_seal)

    async def structured_model(schema, messages):
        return _model_payload(action_kind="performance_blocking")

    with pytest.raises(ProductionPlanModelError, match="invalid production plan"):
        await generate_production_plan(
            project=PROJECT,
            adapted_draft_artifact=adapted,
            format_decision_artifact=decision,
            structured_model=structured_model,
            created_at=NOW,
            source_thread_id="thread-1",
            source_run_id="run-2",
        )

    assert sealed is False


@pytest.mark.asyncio
async def test_no_material_can_remain_provisional_without_blocking() -> None:
    decision, adapted = _parents()

    async def structured_model(schema, messages):
        assert json.loads(messages[1].content)["reviewed_user_materials"] == []
        return _model_payload()

    sealed = await generate_production_plan(
        project=PROJECT,
        adapted_draft_artifact=adapted,
        format_decision_artifact=decision,
        structured_model=structured_model,
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-2",
    )

    assert sealed.payload["status"] == "provisional"
    assert sealed.payload["resource_gaps"]
    assert sealed.payload["unknowns"]
    assert len(sealed.parents) == 2


@pytest.mark.asyncio
async def test_model_and_material_projection_stays_bounded_and_omits_marketing_fields() -> None:
    huge_expression = "适配表达" * 3_000
    material = _user_material(
        "大素材",
        extra_payload={
            "observation": {"summary": "素材说明" * 30_000},
            "monetization": "不应进入制作模型" * 10_000,
            "benchmark_analysis": "不应进入制作模型" * 10_000,
        },
    )
    decision, adapted = _parents(materials=(material,), adapted_expression=huge_expression)

    async def structured_model(schema, messages):
        rendered = messages[1].content
        assert len(rendered.encode("utf-8")) <= PRODUCTION_PLAN_MODEL_INPUT_MAX_BYTES
        assert "不应进入制作模型" not in rendered
        assert "bounded projection truncated" in rendered
        return _model_payload()

    await generate_production_plan(
        project=PROJECT,
        adapted_draft_artifact=adapted,
        format_decision_artifact=decision,
        user_material_artifacts=(material,),
        structured_model=structured_model,
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-2",
    )


@pytest.mark.asyncio
async def test_provider_failure_does_not_call_the_sealer(monkeypatch) -> None:
    import deerflow.incubation.production_runtime as runtime_module

    decision, adapted = _parents()
    provider_error = RuntimeError("provider unavailable")
    sealed = False

    async def failing_model(schema, messages):
        raise provider_error

    def forbidden_seal(**kwargs):
        nonlocal sealed
        sealed = True
        raise AssertionError("provider failure must not be sealed")

    monkeypatch.setattr(runtime_module, "seal_production_plan", forbidden_seal)

    with pytest.raises(ProductionPlanModelError, match="structured model") as exc_info:
        await generate_production_plan(
            project=PROJECT,
            adapted_draft_artifact=adapted,
            format_decision_artifact=decision,
            structured_model=failing_model,
            created_at=NOW,
            source_thread_id="thread-1",
            source_run_id="run-2",
        )

    assert sealed is False
    assert exc_info.value.__cause__ is provider_error


def test_runtime_prompt_keeps_production_below_content_format_and_operations() -> None:
    required_boundaries = (
        "不得换题",
        "不得改变观点",
        "不得补事实",
        "不得补造用户资源",
        "销售",
        "平台",
        "发布",
        "固定时长",
        "微短剧",
        "情景剧",
    )
    for boundary in required_boundaries:
        assert boundary in PRODUCTION_PLAN_SYSTEM_PROMPT
