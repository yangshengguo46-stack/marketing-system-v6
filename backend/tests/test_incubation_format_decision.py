from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from deerflow.incubation import (
    ArtifactEnvelope,
    BaseDraftBinding,
    FormatAlternative,
    FormatChoice,
    FormatDecision,
    FormatDecisionDraft,
    MessagePlanBinding,
    ProjectRef,
    ResourceMatch,
    seal_format_decision,
)

NOW = datetime(2026, 8, 17, 18, 0, tzinfo=UTC)
PROJECT = ProjectRef(owner_user_id="user-1", project_id="golden-gift")


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
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-1",
        parents=parents,
        evidence_role=evidence_role,
    )


def _message_plan(
    *,
    evidence_refs: list[dict[str, str]] | None = None,
    point_of_view: str = "礼的深层作用是把人与人的关系变成共同理解的秩序",
) -> ArtifactEnvelope:
    return _artifact(
        artifact_type="message_plan",
        payload={
            "message_plan_id": "message-plan-1",
            "record_id": "record-golden-gift",
            "topic_title": "古代的礼，为什么不只是礼貌？",
            "focal_subject": "生活在礼制中的普通人",
            "context": "古代社会的日常交往中",
            "concrete_event_or_question": "人们为什么需要用一套礼来安排彼此的关系",
            "account_position": "从一名礼品经营者的真实观察出发",
            "account_position_basis": "我是做黄金礼品的",
            "point_of_view": point_of_view,
            "entry_point": "从今天把礼理解成礼貌这个误会讲起",
            "telling_lens": "跟着礼的含义变化理解关系如何被安排",
            "audience_question": "为什么古人把礼看得如此重要",
            "information_order": "先辨认今天的直觉，再回到制度作用，最后说明边界",
            "payoff": "观众理解礼貌只是礼的一小部分",
            "opening": "今天说一个人有礼，通常只是说他有礼貌。",
            "message_beats": ["但在古代，礼还在安排身份、关系和行为。"],
            "closing": "礼崩坏，说的从来不只是大家突然没礼貌了。",
            "evidence_refs": evidence_refs if evidence_refs is not None else [{"kind": "observation", "ref_id": "observation-gift-1"}],
            "limitations": ["当前只有一份有界公开资料。"],
            "unknown_refs": ["unknown-source-date"],
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


def _draft(**updates: object) -> FormatDecisionDraft:
    values: dict[str, object] = {
        "status": "provisional",
        "selected_format": FormatChoice(kind="image_text"),
        "selection_rationale": "现有资料可直接支撑图文表达，且尚未确认用户是否愿意出镜。",
        "resource_matches": (),
        "resource_gaps": ("缺少用户是否愿意出镜的确认。",),
        "sustainability_risks": ("长期依赖同类史料可能造成视觉重复。",),
        "alternatives": (
            FormatAlternative(
                format=FormatChoice(kind="interview"),
                rationale="若能找到合适受访者，可以让关系经验更具体。",
            ),
        ),
        "unknowns": ("用户可持续取得哪些视觉资料仍未知。",),
    }
    values.update(updates)
    return FormatDecisionDraft.model_validate(values)


def test_format_decision_binds_exact_message_plan_and_optional_supporting_artifacts() -> None:
    message_plan = _message_plan()
    base_draft = _base_draft(message_plan)
    judgment = _artifact(
        artifact_type="incubation_judgment",
        payload={"content_map_version_id": "map-gift-relations-v1"},
    )
    media = _artifact(
        artifact_type="media_observation",
        payload={"available_material": "一组已授权的礼制博物馆图片"},
        evidence_role="user_material",
    )
    draft = _draft(
        resource_matches=(
            ResourceMatch(
                resource="已授权的礼制博物馆图片",
                fit="可以直接承载制度与器物的视觉说明。",
                basis_artifact_ids=(media.artifact_id,),
            ),
        )
    )

    sealed = seal_format_decision(
        project=PROJECT,
        draft=draft,
        message_plan_artifact=message_plan,
        base_draft_artifact=base_draft,
        incubation_judgment_artifact=judgment,
        resource_evidence_artifacts=(media,),
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-1",
    )

    assert sealed.artifact_type == "format_decision"
    assert set(sealed.parents) == {
        message_plan.to_parent_ref(),
        base_draft.to_parent_ref(),
        judgment.to_parent_ref(),
        media.to_parent_ref(),
    }
    binding = sealed.payload["message_plan_binding"]
    assert binding["artifact_id"] == message_plan.artifact_id
    assert binding["artifact_content_sha256"] == message_plan.content_sha256
    assert binding["message_plan_id"] == "message-plan-1"
    assert set(binding) == {
        "artifact_id",
        "artifact_content_sha256",
        "message_plan_id",
        "record_id",
        "protected_content_sha256",
        "evidence_boundary_sha256",
    }
    assert len(binding["protected_content_sha256"]) == 64
    assert len(binding["evidence_boundary_sha256"]) == 64
    draft_binding = sealed.payload["base_draft_binding"]
    assert draft_binding["artifact_id"] == base_draft.artifact_id
    assert draft_binding["artifact_content_sha256"] == base_draft.content_sha256
    assert draft_binding["draft_id"] == "base-draft-1"
    assert draft_binding["message_plan_id"] == "message-plan-1"
    assert draft_binding["stage"] == "base"
    assert len(draft_binding["body_sha256"]) == 64
    assert sealed.payload["incubation_judgment_ref"]["artifact_id"] == judgment.artifact_id
    assert sealed.payload["resource_evidence_refs"][0]["artifact_id"] == media.artifact_id


def test_format_decision_draft_cannot_rewrite_upstream_topic_or_evidence_fields() -> None:
    for forbidden_field in (
        "topic_title",
        "focal_subject",
        "concrete_event_or_question",
        "point_of_view",
        "evidence_refs",
        "limitations",
    ):
        with pytest.raises(ValidationError):
            _draft(**{forbidden_field: "格式层擅自改写的内容"})


def test_format_decision_hashes_protected_content_and_evidence_separately() -> None:
    first_plan = _message_plan()
    first_draft = _base_draft(first_plan)
    changed_content_plan = _message_plan(
        point_of_view="礼的深层作用是让不同角色知道彼此如何相处",
    )
    changed_content_draft = _base_draft(changed_content_plan)
    changed_evidence_plan = _message_plan(
        evidence_refs=[
            {"kind": "observation", "ref_id": "observation-gift-1"},
            {"kind": "observation", "ref_id": "observation-gift-2"},
        ]
    )
    changed_evidence_draft = _base_draft(changed_evidence_plan)

    first = seal_format_decision(
        project=PROJECT,
        draft=_draft(),
        message_plan_artifact=first_plan,
        base_draft_artifact=first_draft,
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-1",
    )
    changed_content = seal_format_decision(
        project=PROJECT,
        draft=_draft(),
        message_plan_artifact=changed_content_plan,
        base_draft_artifact=changed_content_draft,
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-1",
    )
    changed_evidence = seal_format_decision(
        project=PROJECT,
        draft=_draft(),
        message_plan_artifact=changed_evidence_plan,
        base_draft_artifact=changed_evidence_draft,
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-1",
    )

    first_binding = first.payload["message_plan_binding"]
    changed_content_binding = changed_content.payload["message_plan_binding"]
    changed_evidence_binding = changed_evidence.payload["message_plan_binding"]

    assert first_binding["protected_content_sha256"] != changed_content_binding["protected_content_sha256"]
    assert first_binding["evidence_boundary_sha256"] == changed_content_binding["evidence_boundary_sha256"]
    assert first_binding["protected_content_sha256"] == changed_evidence_binding["protected_content_sha256"]
    assert first_binding["evidence_boundary_sha256"] != changed_evidence_binding["evidence_boundary_sha256"]
    assert first.parents != changed_content.parents
    assert first.parents != changed_evidence.parents


def test_format_decision_public_api_is_exported() -> None:
    assert FormatDecisionDraft.__module__ == "deerflow.incubation.format_decision"
    assert FormatDecision.__module__ == "deerflow.incubation.format_decision"
    assert MessagePlanBinding.__module__ == "deerflow.incubation.format_decision"
    assert BaseDraftBinding.__module__ == "deerflow.incubation.format_decision"


@pytest.mark.parametrize(
    ("field", "invalid_value", "error"),
    (
        ("topic_title", None, "non-empty topic_title"),
        ("evidence_refs", "not-a-list", "explicit evidence_refs boundary"),
    ),
)
def test_seal_validates_protected_content_and_evidence_boundaries(
    field: str,
    invalid_value: object,
    error: str,
) -> None:
    payload = dict(_message_plan().payload)
    payload[field] = invalid_value
    message_plan = _artifact(
        artifact_type="message_plan",
        payload=payload,
    )

    with pytest.raises(ValueError, match=error):
        seal_format_decision(
            project=PROJECT,
            draft=_draft(),
            message_plan_artifact=message_plan,
            base_draft_artifact=_base_draft(message_plan),
            created_at=NOW,
            source_thread_id="thread-1",
            source_run_id="run-1",
        )


def test_message_plan_binding_rejects_non_sha256_hashes() -> None:
    with pytest.raises(ValidationError, match="lowercase SHA-256"):
        MessagePlanBinding(
            artifact_id="artifact-1",
            artifact_content_sha256="not-a-digest",
            message_plan_id="message-plan-1",
            record_id="record-1",
            protected_content_sha256="0" * 64,
            evidence_boundary_sha256="1" * 64,
        )


def test_base_draft_binding_rejects_non_sha256_hashes() -> None:
    with pytest.raises(ValidationError, match="lowercase SHA-256"):
        BaseDraftBinding(
            artifact_id="artifact-1",
            artifact_content_sha256="not-a-digest",
            draft_id="base-draft-1",
            message_plan_id="message-plan-1",
            stage="base",
            body_sha256="0" * 64,
        )


@pytest.mark.parametrize(
    "kind",
    (
        "spoken_delivery",
        "micro_drama",
        "situational_drama",
        "image_text",
        "material_only",
        "interview",
        "documentary_observation",
    ),
)
def test_format_choice_supports_real_presentation_forms(kind: str) -> None:
    assert FormatChoice(kind=kind).kind == kind


def test_format_choice_supports_an_extensible_custom_form() -> None:
    choice = FormatChoice(kind="custom", custom_name="screen_recording_explainer")

    assert choice.custom_name == "screen_recording_explainer"


@pytest.mark.parametrize("content_label", ("historical_story", "real_case"))
def test_format_choice_does_not_mistake_content_sources_for_forms(content_label: str) -> None:
    with pytest.raises(ValidationError):
        FormatChoice(kind=content_label)


@pytest.mark.parametrize("content_label", ("历史故事", "真实案例"))
def test_custom_format_cannot_relabel_a_content_source_as_a_form(content_label: str) -> None:
    with pytest.raises(ValidationError, match="content source"):
        FormatChoice(kind="custom", custom_name=content_label)


def test_custom_name_is_required_only_for_custom_forms() -> None:
    with pytest.raises(ValidationError, match="custom form requires"):
        FormatChoice(kind="custom")

    with pytest.raises(ValidationError, match="custom_name is only valid"):
        FormatChoice(kind="image_text", custom_name="extra label")


def test_narrative_method_is_an_optional_hint_only_for_narrative_forms() -> None:
    narrative_without_hint = _draft(
        selected_format=FormatChoice(kind="micro_drama"),
        narrative_method_hint=None,
    )
    narrative_with_hint = _draft(
        selected_format=FormatChoice(kind="situational_drama"),
        narrative_method_hint="可按目标、阻碍与行动检查是否值得进入叙事方法。",
    )

    assert narrative_without_hint.narrative_method_hint is None
    assert narrative_with_hint.narrative_method_hint is not None

    with pytest.raises(ValidationError, match="narrative method hint"):
        _draft(
            selected_format=FormatChoice(kind="spoken_delivery"),
            narrative_method_hint="强制套用故事结构",
        )


def test_format_decision_normalizes_only_the_explicit_json_null_literal() -> None:
    decision = _draft(
        selected_format=FormatChoice(kind="spoken_delivery"),
        narrative_method_hint="null",
    )

    assert decision.narrative_method_hint is None

    with pytest.raises(ValidationError, match="narrative method hint"):
        _draft(
            selected_format=FormatChoice(kind="spoken_delivery"),
            narrative_method_hint="none",
        )


def test_provisional_decision_allows_missing_resource_information() -> None:
    message_plan = _message_plan()
    sealed = seal_format_decision(
        project=PROJECT,
        draft=_draft(
            status="provisional",
            resource_matches=(),
            resource_gaps=(),
            sustainability_risks=(),
            alternatives=(),
            unknowns=("尚未了解用户的出镜意愿、素材和协作资源。",),
        ),
        message_plan_artifact=message_plan,
        base_draft_artifact=_base_draft(message_plan),
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-1",
    )

    assert sealed.payload["status"] == "provisional"
    assert sealed.payload["resource_matches"] == []
    assert sealed.payload["unknowns"] == ["尚未了解用户的出镜意愿、素材和协作资源。"]


def test_a_claimed_resource_match_requires_at_least_one_evidence_artifact() -> None:
    with pytest.raises(ValidationError):
        ResourceMatch(
            resource="店内可直接拍摄的旧书",
            fit="可以作为本条内容的实物依据。",
            basis_artifact_ids=(),
        )


def test_resource_basis_must_be_bound_as_a_parent() -> None:
    draft = _draft(
        resource_matches=(
            ResourceMatch(
                resource="一组图片",
                fit="可用于图文说明。",
                basis_artifact_ids=("artifact-not-a-parent",),
            ),
        )
    )

    message_plan = _message_plan()
    with pytest.raises(ValueError, match="resource basis artifact"):
        seal_format_decision(
            project=PROJECT,
            draft=draft,
            message_plan_artifact=message_plan,
            base_draft_artifact=_base_draft(message_plan),
            created_at=NOW,
            source_thread_id="thread-1",
            source_run_id="run-1",
        )


def test_format_decision_rejects_wrong_parent_type_or_project() -> None:
    message_plan = _message_plan()
    with pytest.raises(ValueError, match="expected message_plan parent"):
        seal_format_decision(
            project=PROJECT,
            draft=_draft(),
            message_plan_artifact=_artifact(artifact_type="topic_brief", payload={"question": "一个选题"}),
            base_draft_artifact=_base_draft(message_plan),
            created_at=NOW,
            source_thread_id="thread-1",
            source_run_id="run-1",
        )

    other_project_plan = _artifact(
        artifact_type="message_plan",
        payload=_message_plan().payload,
        project=ProjectRef(owner_user_id="user-2", project_id="other-project"),
    )
    with pytest.raises(ValueError, match="project must match"):
        seal_format_decision(
            project=PROJECT,
            draft=_draft(),
            message_plan_artifact=other_project_plan,
            base_draft_artifact=_base_draft(message_plan),
            created_at=NOW,
            source_thread_id="thread-1",
            source_run_id="run-1",
        )


def test_format_decision_requires_exact_base_draft_lineage() -> None:
    message_plan = _message_plan()
    unrelated_plan = _message_plan(point_of_view="另一份消息计划")

    with pytest.raises(ValueError, match="base draft must descend from the exact message plan"):
        seal_format_decision(
            project=PROJECT,
            draft=_draft(),
            message_plan_artifact=message_plan,
            base_draft_artifact=_base_draft(unrelated_plan),
            created_at=NOW,
            source_thread_id="thread-1",
            source_run_id="run-1",
        )


def test_format_decision_requires_base_stage_and_matching_plan_id() -> None:
    message_plan = _message_plan()
    wrong_stage = _artifact(
        artifact_type="draft_version",
        payload={
            "draft_id": "adapted-draft-1",
            "message_plan_id": "message-plan-1",
            "text": "已经适配后的稿件",
            "stage": "adapted",
        },
        parents=(message_plan.to_parent_ref(),),
    )
    with pytest.raises(ValueError, match="base stage"):
        seal_format_decision(
            project=PROJECT,
            draft=_draft(),
            message_plan_artifact=message_plan,
            base_draft_artifact=wrong_stage,
            created_at=NOW,
            source_thread_id="thread-1",
            source_run_id="run-1",
        )


@pytest.mark.parametrize(
    "forbidden_field",
    (
        "platform",
        "sales_call_to_action",
        "publish_at",
        "duration_seconds",
        "shot_count",
        "posting_frequency",
    ),
)
def test_format_decision_has_no_platform_sales_publishing_or_fixed_number_controls(
    forbidden_field: str,
) -> None:
    with pytest.raises(ValidationError):
        _draft(**{forbidden_field: "not part of a format decision"})
