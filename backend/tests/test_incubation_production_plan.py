from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

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
from deerflow.incubation.production_plan import (
    AssemblyStep,
    ProductionAction,
    ProductionAssetRequirement,
    ProductionPlan,
    ProductionPlanDraft,
    seal_production_plan,
)

NOW = datetime(2026, 8, 17, 8, 0, tzinfo=UTC)
PROJECT = ProjectRef(owner_user_id="user-1", project_id="project-1")


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


def _message_plan() -> ArtifactEnvelope:
    return _artifact(
        artifact_type="message_plan",
        payload={
            "message_plan_id": "message-plan-1",
            "record_id": "record-1",
            "topic_title": "为什么礼不只是礼貌",
            "focal_subject": "古代社会中的礼",
            "concrete_event_or_question": "礼如何安排人与人之间的相处",
            "point_of_view": "礼先规定关系，再规定行为。",
            "evidence_refs": [],
            "limitations": [],
            "unknown_refs": [],
            "research_needed": [],
        },
    )


def _base_draft(
    message_plan: ArtifactEnvelope,
    *,
    text: str = "今天说一个人有礼，通常只是说他有礼貌。\n\n但在古代，礼还在安排身份、关系和行为。",
) -> ArtifactEnvelope:
    return _artifact(
        artifact_type="draft_version",
        payload={
            "draft_id": "base-draft-1",
            "message_plan_id": message_plan.payload["message_plan_id"],
            "text": text,
            "stage": "base",
        },
        parents=(message_plan.to_parent_ref(),),
    )


def _user_material(*, project: ProjectRef = PROJECT, role: str = "user_material") -> ArtifactEnvelope:
    return _artifact(
        artifact_type="media_observation",
        payload={"observation": "用户授权的一组礼制博物馆图片"},
        project=project,
        evidence_role=role,
    )


def _format_decision(
    *,
    kind: str = "image_text",
    user_material: ArtifactEnvelope | None = None,
    base_text: str = "今天说一个人有礼，通常只是说他有礼貌。\n\n但在古代，礼还在安排身份、关系和行为。",
) -> tuple[ArtifactEnvelope, ArtifactEnvelope, ArtifactEnvelope]:
    message_plan = _message_plan()
    base_draft = _base_draft(message_plan, text=base_text)
    resource_artifacts = (user_material,) if user_material is not None else ()
    resource_matches = (
        (
            ResourceMatch(
                resource="用户授权图片",
                fit="可作为已定文案的视觉材料",
                basis_artifact_ids=(user_material.artifact_id,),
            ),
        )
        if user_material is not None
        else ()
    )
    decision = seal_format_decision(
        project=PROJECT,
        draft=FormatDecisionDraft(
            status="confirmed" if user_material is not None else "provisional",
            selected_format=FormatChoice(kind=kind),
            selection_rationale="用已定正文选择最适合当前资源的呈现方式。",
            resource_matches=resource_matches,
            resource_gaps=() if user_material is not None else ("尚未确认可用素材。",),
            unknowns=() if user_material is not None else ("用户素材情况未知。",),
        ),
        message_plan_artifact=message_plan,
        base_draft_artifact=base_draft,
        resource_evidence_artifacts=resource_artifacts,
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-1",
    )
    adapted_draft = seal_adapted_draft(
        project=PROJECT,
        draft=AdaptedDraftDraft(
            units=(
                PresentationUnitDraft(
                    unit_id="unit-1",
                    mode="on_screen_text",
                    adapted_expression=base_text,
                    source_excerpts=(base_text,),
                ),
            )
        ),
        base_draft_artifact=base_draft,
        format_decision_artifact=decision,
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-1",
    )
    return decision, base_draft, adapted_draft


def _plan_draft(
    *,
    existing_material_id: str | None = None,
    narrative_hint: str | None = None,
    action_kind: str = "text_layout",
) -> ProductionPlanDraft:
    if existing_material_id is None:
        assets = (
            ProductionAssetRequirement(
                asset_id="asset-title-card",
                kind="text_graphic",
                purpose="承载基础文案的标题与正文",
                source="derived_from_adapted_draft",
            ),
        )
    else:
        assets = (
            ProductionAssetRequirement(
                asset_id="asset-user-images",
                kind="image",
                purpose="配合基础文案提供视觉说明",
                source="existing_user_material",
                basis_artifact_ids=(existing_material_id,),
            ),
        )
    asset_id = assets[0].asset_id
    return ProductionPlanDraft(
        status="provisional",
        asset_requirements=assets,
        production_actions=(
            ProductionAction(
                action_id="action-1",
                kind=action_kind,
                instruction="仅把已定基础文案翻译为对应画面。",
                asset_ids=(asset_id,),
            ),
        ),
        assembly_steps=(
            AssemblyStep(
                step_id="assembly-1",
                instruction="按基础文案原有顺序装配素材。",
                input_asset_ids=(asset_id,),
            ),
        ),
        resource_gaps=("最终视觉资源仍待确认。",),
        unknowns=("尚未确认成片规格。",),
        narrative_execution_hint=narrative_hint,
    )


def test_production_plan_binds_exact_adapted_draft_format_and_user_material() -> None:
    material = _user_material()
    format_decision, _base_draft_artifact, adapted_draft = _format_decision(user_material=material)

    sealed = seal_production_plan(
        project=PROJECT,
        draft=_plan_draft(existing_material_id=material.artifact_id),
        adapted_draft_artifact=adapted_draft,
        format_decision_artifact=format_decision,
        user_material_artifacts=(material,),
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-1",
    )

    assert sealed.artifact_type == "production_plan"
    assert set(sealed.parents) == {
        adapted_draft.to_parent_ref(),
        format_decision.to_parent_ref(),
        material.to_parent_ref(),
    }
    plan = ProductionPlan.model_validate(sealed.payload)
    assert plan.adapted_draft_ref == adapted_draft.to_parent_ref()
    assert plan.adapted_body_sha256 == adapted_draft.payload["adapted_body_sha256"]
    assert plan.format_decision_ref == format_decision.to_parent_ref()
    assert plan.selected_format.kind == "image_text"
    assert plan.user_material_refs == (material.to_parent_ref(),)
    assert "text" not in sealed.payload
    assert "topic_title" not in sealed.payload
    assert "point_of_view" not in sealed.payload


def test_production_plan_rejects_an_adapted_draft_from_another_format_decision() -> None:
    format_decision, _base_draft, adapted_draft = _format_decision()
    _other_format, _other_base, unrelated_adapted = _format_decision(base_text="另一份正文")

    with pytest.raises(ValueError, match="exact format decision"):
        seal_production_plan(
            project=PROJECT,
            draft=_plan_draft(),
            adapted_draft_artifact=unrelated_adapted,
            format_decision_artifact=format_decision,
            created_at=NOW,
            source_thread_id="thread-1",
            source_run_id="run-1",
        )

    assert adapted_draft.artifact_id != unrelated_adapted.artifact_id


@pytest.mark.parametrize(
    ("material", "error"),
    (
        (_user_material(role="topic_evidence"), "user_material"),
        (
            _user_material(project=ProjectRef(owner_user_id="user-1", project_id="project-2")),
            "project",
        ),
    ),
)
def test_existing_material_claim_requires_same_project_user_material_parent(
    material: ArtifactEnvelope,
    error: str,
) -> None:
    valid_material = _user_material()
    format_decision, _base_draft, adapted_draft = _format_decision(user_material=valid_material)
    draft = _plan_draft(existing_material_id=material.artifact_id)

    with pytest.raises(ValueError, match=error):
        seal_production_plan(
            project=PROJECT,
            draft=draft,
            adapted_draft_artifact=adapted_draft,
            format_decision_artifact=format_decision,
            user_material_artifacts=(material,),
            created_at=NOW,
            source_thread_id="thread-1",
            source_run_id="run-1",
        )


def test_existing_material_must_have_been_reviewed_by_the_exact_format_decision() -> None:
    material = _user_material()
    format_decision, _base_draft, adapted_draft = _format_decision()

    with pytest.raises(ValueError, match="exact format decision"):
        seal_production_plan(
            project=PROJECT,
            draft=_plan_draft(existing_material_id=material.artifact_id),
            adapted_draft_artifact=adapted_draft,
            format_decision_artifact=format_decision,
            user_material_artifacts=(material,),
            created_at=NOW,
            source_thread_id="thread-1",
            source_run_id="run-1",
        )


@pytest.mark.parametrize("kind", ("image_text", "material_only"))
def test_non_performance_formats_can_remain_provisional_without_performance(
    kind: str,
) -> None:
    format_decision, _base_draft, adapted_draft = _format_decision(kind=kind)

    sealed = seal_production_plan(
        project=PROJECT,
        draft=_plan_draft(),
        adapted_draft_artifact=adapted_draft,
        format_decision_artifact=format_decision,
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-1",
    )

    assert sealed.payload["status"] == "provisional"
    assert sealed.payload["narrative_execution_hint"] is None
    assert sealed.payload["production_actions"][0]["kind"] == "text_layout"


@pytest.mark.parametrize("kind", ("image_text", "material_only"))
def test_non_performance_formats_reject_forced_performance_or_story_structure(
    kind: str,
) -> None:
    format_decision, _base_draft, adapted_draft = _format_decision(kind=kind)

    with pytest.raises(ValueError, match="performance"):
        seal_production_plan(
            project=PROJECT,
            draft=_plan_draft(action_kind="performance_blocking"),
            adapted_draft_artifact=adapted_draft,
            format_decision_artifact=format_decision,
            created_at=NOW,
            source_thread_id="thread-1",
            source_run_id="run-1",
        )

    with pytest.raises(ValueError, match="narrative"):
        seal_production_plan(
            project=PROJECT,
            draft=_plan_draft(narrative_hint="为人物补一条冲突线。"),
            adapted_draft_artifact=adapted_draft,
            format_decision_artifact=format_decision,
            created_at=NOW,
            source_thread_id="thread-1",
            source_run_id="run-1",
        )


def test_narrative_format_allows_execution_hint_but_not_upstream_rewrite_fields() -> None:
    format_decision, _base_draft, adapted_draft = _format_decision(kind="micro_drama")
    sealed = seal_production_plan(
        project=PROJECT,
        draft=_plan_draft(
            narrative_hint="仅将基础文案里已经存在的行动关系转成场面调度。",
            action_kind="performance_blocking",
        ),
        adapted_draft_artifact=adapted_draft,
        format_decision_artifact=format_decision,
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-1",
    )
    assert sealed.payload["narrative_execution_hint"] is not None

    with pytest.raises(ValidationError):
        ProductionPlanDraft.model_validate(
            {
                **_plan_draft().model_dump(mode="json"),
                "topic_title": "擅自换题",
                "point_of_view": "擅自改观点",
                "text": "擅自改正文",
                "evidence_refs": [],
            }
        )


def test_production_plan_rejects_dangling_asset_references_and_duplicate_ids() -> None:
    with pytest.raises(ValidationError, match="unknown asset"):
        ProductionPlanDraft(
            asset_requirements=(),
            production_actions=(
                ProductionAction(
                    action_id="action-1",
                    kind="capture_video",
                    instruction="拍摄既定内容",
                    asset_ids=("missing-asset",),
                ),
            ),
        )

    with pytest.raises(ValidationError, match="unique"):
        ProductionPlanDraft(
            asset_requirements=(
                ProductionAssetRequirement(
                    asset_id="same",
                    kind="image",
                    purpose="用途一",
                    source="to_capture",
                ),
                ProductionAssetRequirement(
                    asset_id="same",
                    kind="image",
                    purpose="用途二",
                    source="to_capture",
                ),
            ),
        )


def test_production_contract_has_no_platform_sales_publish_or_quota_controls() -> None:
    forbidden = {
        "platform",
        "sales",
        "monetization",
        "publish_at",
        "approval",
        "duration_seconds",
        "shot_count",
        "post_count",
        "cadence",
        "quota",
        "topic_title",
        "point_of_view",
        "text",
        "evidence_refs",
    }
    fields = set(ProductionPlanDraft.model_fields) | set(ProductionAssetRequirement.model_fields) | set(ProductionAction.model_fields) | set(AssemblyStep.model_fields)
    assert forbidden.isdisjoint(fields)
