from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from deerflow.incubation.adapted_draft import (
    AdaptedDraft,
    AdaptedDraftDraft,
    NarrativeTreatment,
    PresentationUnitDraft,
    seal_adapted_draft,
)
from deerflow.incubation.contracts import ArtifactEnvelope, ProjectRef
from deerflow.incubation.format_decision import (
    FormatChoice,
    FormatDecisionDraft,
    seal_format_decision,
)

NOW = datetime(2026, 8, 17, 22, 0, tzinfo=UTC)
PROJECT = ProjectRef(owner_user_id="user-1", project_id="golden-gift")
BASE_TEXT = "今天说一个人有礼，通常只是说他有礼貌。\n\n但在古代，礼还在安排身份、关系和行为。\n\n礼崩坏，说的从来不只是大家突然没礼貌了。"


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


def _message_plan(*, project: ProjectRef = PROJECT) -> ArtifactEnvelope:
    return _artifact(
        artifact_type="message_plan",
        project=project,
        payload={
            "message_plan_id": "message-plan-1",
            "record_id": "record-golden-gift",
            "topic_title": "古代的礼，为什么不只是礼貌？",
            "focal_subject": "生活在礼制中的普通人",
            "concrete_event_or_question": "礼如何安排人与人之间的关系",
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
    text: str = BASE_TEXT,
) -> ArtifactEnvelope:
    return _artifact(
        artifact_type="draft_version",
        project=message_plan.project,
        payload={
            "draft_id": "base-draft-1",
            "message_plan_id": message_plan.payload["message_plan_id"],
            "text": text,
            "stage": "base",
        },
        parents=(message_plan.to_parent_ref(),),
    )


def _format_decision(
    *,
    kind: str = "image_text",
    project: ProjectRef = PROJECT,
    base_text: str = BASE_TEXT,
) -> tuple[ArtifactEnvelope, ArtifactEnvelope]:
    message_plan = _message_plan(project=project)
    base_draft = _base_draft(message_plan, text=base_text)
    decision = seal_format_decision(
        project=project,
        draft=FormatDecisionDraft(
            status="confirmed",
            selected_format=FormatChoice(kind=kind),
            selection_rationale="把同一份基础稿翻译成当前表现形式。",
        ),
        message_plan_artifact=message_plan,
        base_draft_artifact=base_draft,
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-1",
    )
    return decision, base_draft


def _draft(*, narrative: bool = False) -> AdaptedDraftDraft:
    return AdaptedDraftDraft(
        units=(
            PresentationUnitDraft(
                unit_id="unit-opening",
                mode="on_screen_text",
                adapted_expression="我们今天说的有礼，往往只剩下有礼貌。",
                source_excerpts=("今天说一个人有礼，通常只是说他有礼貌。",),
                visual_treatment="先出现今天对‘有礼’的日常理解。",
                narrative_treatment=(
                    NarrativeTreatment(
                        scene_purpose="把日常误解变成可见的开场处境。",
                        performance_intent="只表演基础稿已有的误解，不补人物经历。",
                    )
                    if narrative
                    else None
                ),
            ),
            PresentationUnitDraft(
                unit_id="unit-payoff",
                mode="voiceover",
                adapted_expression="古代的礼还在安排身份、关系与行为。",
                source_excerpts=("但在古代，礼还在安排身份、关系和行为。",),
            ),
        )
    )


def test_adapted_draft_binds_exact_base_and_format_with_source_anchors() -> None:
    format_decision, base_draft = _format_decision()

    sealed = seal_adapted_draft(
        project=PROJECT,
        draft=_draft(),
        base_draft_artifact=base_draft,
        format_decision_artifact=format_decision,
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-2",
    )

    assert sealed.artifact_type == "adapted_draft"
    assert set(sealed.parents) == {
        base_draft.to_parent_ref(),
        format_decision.to_parent_ref(),
    }
    adapted = AdaptedDraft.model_validate(sealed.payload)
    assert adapted.base_draft_binding.artifact_id == base_draft.artifact_id
    assert adapted.base_draft_binding.body_sha256 == format_decision.payload["base_draft_binding"]["body_sha256"]
    assert adapted.format_decision_ref == format_decision.to_parent_ref()
    assert adapted.selected_format.kind == "image_text"
    assert adapted.adapted_body == "\n\n".join(unit.adapted_expression for unit in adapted.units)
    assert len(adapted.adapted_body_sha256) == 64
    anchor = adapted.units[0].source_anchors[0]
    assert BASE_TEXT[anchor.start_char : anchor.end_char] == anchor.excerpt
    assert "topic_title" not in sealed.payload
    assert "message_plan" not in sealed.payload
    assert "evidence_refs" not in sealed.payload


def test_adapted_draft_rejects_a_base_other_than_the_exact_format_parent() -> None:
    format_decision, expected_base = _format_decision()
    unrelated_plan = _message_plan()
    unrelated_base = _base_draft(unrelated_plan, text="这是一份无关基础稿。")

    with pytest.raises(ValueError, match="exact base draft"):
        seal_adapted_draft(
            project=PROJECT,
            draft=_draft(),
            base_draft_artifact=unrelated_base,
            format_decision_artifact=format_decision,
            created_at=NOW,
            source_thread_id="thread-1",
            source_run_id="run-2",
        )

    assert expected_base.artifact_id != unrelated_base.artifact_id


def test_every_unit_requires_a_contiguous_verbatim_base_excerpt() -> None:
    with pytest.raises(ValidationError):
        PresentationUnitDraft(
            unit_id="source-free",
            mode="voiceover",
            adapted_expression="没有来源的发挥。",
            source_excerpts=(),
        )

    format_decision, base_draft = _format_decision()
    invalid = AdaptedDraftDraft(
        units=(
            PresentationUnitDraft(
                unit_id="invented",
                mode="voiceover",
                adapted_expression="擅自加入一个历史人物。",
                source_excerpts=("基础稿里不存在的连续原句",),
            ),
        )
    )
    with pytest.raises(ValueError, match="contiguous verbatim"):
        seal_adapted_draft(
            project=PROJECT,
            draft=invalid,
            base_draft_artifact=base_draft,
            format_decision_artifact=format_decision,
            created_at=NOW,
            source_thread_id="thread-1",
            source_run_id="run-2",
        )


def test_draft_schema_cannot_rewrite_content_evidence_or_operations() -> None:
    forbidden = {
        "topic_brief",
        "message_plan",
        "topic_title",
        "focal_subject",
        "point_of_view",
        "evidence_refs",
        "sales",
        "platform",
        "publish_at",
        "duration_seconds",
        "shot_count",
        "post_count",
        "quota",
    }
    assert forbidden.isdisjoint(AdaptedDraftDraft.model_fields)
    assert forbidden.isdisjoint(PresentationUnitDraft.model_fields)

    with pytest.raises(ValidationError):
        AdaptedDraftDraft.model_validate(
            {
                **_draft().model_dump(mode="json"),
                "topic_title": "格式层擅自换题",
                "evidence_refs": ["new-evidence"],
            }
        )


@pytest.mark.parametrize(
    "kind",
    (
        "spoken_delivery",
        "image_text",
        "material_only",
        "interview",
        "documentary_observation",
    ),
)
def test_non_narrative_formats_use_generic_units_without_forced_performance(
    kind: str,
) -> None:
    format_decision, base_draft = _format_decision(kind=kind)
    sealed = seal_adapted_draft(
        project=PROJECT,
        draft=_draft(),
        base_draft_artifact=base_draft,
        format_decision_artifact=format_decision,
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-2",
    )
    assert all(unit["narrative_treatment"] is None for unit in sealed.payload["units"])


@pytest.mark.parametrize("kind", ("image_text", "material_only"))
def test_image_and_material_forms_reject_dialogue_or_narrative_treatment(
    kind: str,
) -> None:
    format_decision, base_draft = _format_decision(kind=kind)
    narrative_unit = PresentationUnitDraft(
        unit_id="forced-performance",
        mode="dialogue",
        adapted_expression="甲说礼只是礼貌。",
        source_excerpts=("今天说一个人有礼，通常只是说他有礼貌。",),
        narrative_treatment=NarrativeTreatment(
            scene_purpose="增加一场戏。",
            performance_intent="要求两个人对话。",
        ),
    )
    with pytest.raises(ValueError, match="narrative|dialogue"):
        seal_adapted_draft(
            project=PROJECT,
            draft=AdaptedDraftDraft(units=(narrative_unit,)),
            base_draft_artifact=base_draft,
            format_decision_artifact=format_decision,
            created_at=NOW,
            source_thread_id="thread-1",
            source_run_id="run-2",
        )


@pytest.mark.parametrize("kind", ("micro_drama", "situational_drama"))
def test_narrative_forms_allow_high_level_scene_treatment(kind: str) -> None:
    format_decision, base_draft = _format_decision(kind=kind)
    sealed = seal_adapted_draft(
        project=PROJECT,
        draft=_draft(narrative=True),
        base_draft_artifact=base_draft,
        format_decision_artifact=format_decision,
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-2",
    )
    assert sealed.payload["units"][0]["narrative_treatment"] is not None


def test_presentation_unit_ids_are_unique_and_order_is_preserved() -> None:
    duplicate = _draft().units[0]
    with pytest.raises(ValidationError, match="unique"):
        AdaptedDraftDraft(units=(duplicate, duplicate))

    format_decision, base_draft = _format_decision()
    sealed = seal_adapted_draft(
        project=PROJECT,
        draft=_draft(),
        base_draft_artifact=base_draft,
        format_decision_artifact=format_decision,
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-2",
    )
    assert [unit["unit_id"] for unit in sealed.payload["units"]] == [
        "unit-opening",
        "unit-payoff",
    ]
