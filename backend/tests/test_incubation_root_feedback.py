from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from deerflow.incubation import (
    ArtifactEnvelope,
    ProjectRef,
    RootCandidateFeedback,
    RootFeedbackRecord,
    seal_root_feedback_record,
)

NOW = datetime(2026, 8, 19, 18, 0, tzinfo=UTC)


def _project() -> ProjectRef:
    return ProjectRef(owner_user_id="user-1", project_id="project-1")


def _content_map(*, content_root: str = "黄金产品知识") -> ArtifactEnvelope:
    return ArtifactEnvelope.seal(
        project=_project(),
        artifact_type="content_map_candidate",
        version=1,
        payload={
            "content_map_version_id": "content-map-old",
            "content_root": content_root,
            "editorial_promise": "讲黄金产品知识。",
            "recurring_lens": "材质、工艺与价格。",
            "drift_boundaries": [],
            "dimensions": [],
        },
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-1",
    )


def _correction() -> RootFeedbackRecord:
    return RootFeedbackRecord(
        user_utterance="我是做黄金礼品的，我要怎么起号？",
        commercial_object="黄金礼品",
        evaluated_content_root="黄金产品知识",
        candidate_feedback=(
            RootCandidateFeedback(
                label="黄金产品知识",
                origin="model",
                decision="rejected",
                reason="仍围着材质和商品打转。",
            ),
            RootCandidateFeedback(
                label="人们如何用礼组织人与人的相处",
                origin="user_added",
                decision="best",
                reason="礼品背后更大的长期世界是礼与人情世故。",
            ),
        ),
        ip_feasibility="strong",
        error_kinds=("candidate_recall", "candidate_selection"),
        status="confirmed",
    )


def test_root_feedback_seals_as_append_only_child_of_exact_content_map() -> None:
    content_map = _content_map()

    artifact = seal_root_feedback_record(
        project=_project(),
        content_map=content_map,
        feedback=_correction(),
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-2",
    )

    assert artifact.artifact_type == "content_root_feedback"
    assert artifact.parents == (content_map.to_parent_ref(),)
    assert artifact.payload["evaluated_content_root"] == "黄金产品知识"
    assert artifact.payload["candidate_feedback"][1]["label"] == "人们如何用礼组织人与人的相处"
    assert artifact.payload["error_kinds"] == ["candidate_recall", "candidate_selection"]
    assert "retrieval_score" not in artifact.payload
    assert "prompt_update" not in artifact.payload


def test_root_feedback_requires_exact_evaluated_parent_root() -> None:
    feedback = _correction().model_copy(
        update={
            "evaluated_content_root": "黄金礼品",
            "candidate_feedback": (
                RootCandidateFeedback(
                    label="黄金礼品",
                    origin="model",
                    decision="rejected",
                    reason="仍然只是商业对象。",
                ),
                _correction().candidate_feedback[1],
            ),
        }
    )

    with pytest.raises(ValueError, match="evaluated content root must match"):
        seal_root_feedback_record(
            project=_project(),
            content_map=_content_map(),
            feedback=feedback,
            created_at=NOW,
            source_thread_id="thread-1",
            source_run_id="run-2",
        )


def test_root_feedback_rejects_non_content_map_parent() -> None:
    wrong_parent = ArtifactEnvelope.seal(
        project=_project(),
        artifact_type="topic_brief",
        version=1,
        payload={"topic": "周公之礼"},
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-1",
    )

    with pytest.raises(ValueError, match="content_map_candidate"):
        seal_root_feedback_record(
            project=_project(),
            content_map=wrong_parent,
            feedback=_correction(),
            created_at=NOW,
            source_thread_id="thread-1",
            source_run_id="run-2",
        )


def test_confirmed_feedback_requires_one_best_root_or_explicit_no_strong_root() -> None:
    with pytest.raises(ValidationError, match="exactly one best candidate"):
        RootFeedbackRecord(
            user_utterance="我是做黄金礼品的。",
            commercial_object="黄金礼品",
            evaluated_content_root="黄金产品知识",
            candidate_feedback=(
                RootCandidateFeedback(
                    label="黄金产品知识",
                    origin="model",
                    decision="rejected",
                    reason="太窄。",
                ),
            ),
            ip_feasibility="strong",
            error_kinds=("candidate_selection",),
            status="confirmed",
        )

    no_root = RootFeedbackRecord(
        user_utterance="我是卖老年助听器的。",
        commercial_object="老年助听器",
        evaluated_content_root="听力健康",
        candidate_feedback=(
            RootCandidateFeedback(
                label="听力健康",
                origin="model",
                decision="acceptable",
                reason="语义成立，但经营者身份不足以支撑独立 IP。",
            ),
        ),
        no_strong_root=True,
        ip_feasibility="conditional",
        conditions=("需要具备听力健康专业能力或稳定专家合作。",),
        error_kinds=("ip_feasibility",),
        status="confirmed",
    )

    assert no_root.no_strong_root is True


def test_root_feedback_rejects_duplicate_candidates_and_inconsistent_error_labels() -> None:
    duplicate = _correction().model_copy(
        update={
            "candidate_feedback": (
                RootCandidateFeedback(
                    label="礼与人情",
                    origin="model",
                    decision="rejected",
                    reason="第一次。",
                ),
                RootCandidateFeedback(
                    label="礼与人情",
                    origin="user_added",
                    decision="best",
                    reason="第二次。",
                ),
            )
        }
    )
    with pytest.raises(ValidationError, match="candidate labels must be unique"):
        RootFeedbackRecord.model_validate(duplicate.model_dump(mode="python"))

    with pytest.raises(ValidationError, match="candidate_recall"):
        RootFeedbackRecord.model_validate(_correction().model_copy(update={"error_kinds": ("candidate_selection",)}).model_dump(mode="python"))

    with pytest.raises(ValidationError, match="candidate_selection"):
        RootFeedbackRecord.model_validate(_correction().model_copy(update={"error_kinds": ("candidate_recall",)}).model_dump(mode="python"))


def test_root_feedback_revision_is_a_new_artifact_with_prior_feedback_parent() -> None:
    content_map = _content_map()
    original = seal_root_feedback_record(
        project=_project(),
        content_map=content_map,
        feedback=_correction(),
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-2",
    )
    revised_feedback = _correction().model_copy(
        update={
            "status": "superseded",
            "revision_reason": "用户补充说明：礼还应包括礼貌、礼节与礼乐秩序。",
        }
    )

    revised = seal_root_feedback_record(
        project=_project(),
        content_map=content_map,
        feedback=revised_feedback,
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-3",
        previous_feedback=original,
    )

    assert revised.artifact_id != original.artifact_id
    assert revised.parents == tuple(sorted((content_map.to_parent_ref(), original.to_parent_ref()), key=lambda item: item.artifact_id))


def test_non_initial_feedback_status_requires_prior_feedback_parent() -> None:
    feedback = _correction().model_copy(update={"status": "contested", "revision_reason": "存在另一条同样有效的内容世界。"})

    with pytest.raises(ValueError, match="previous feedback"):
        seal_root_feedback_record(
            project=_project(),
            content_map=_content_map(),
            feedback=feedback,
            created_at=NOW,
            source_thread_id="thread-1",
            source_run_id="run-2",
        )


def test_feedback_revision_cannot_cross_to_another_content_map() -> None:
    original_map = _content_map()
    original = seal_root_feedback_record(
        project=_project(),
        content_map=original_map,
        feedback=_correction(),
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-2",
    )
    different_map = ArtifactEnvelope.seal(
        project=_project(),
        artifact_type="content_map_candidate",
        version=1,
        payload={**original_map.payload, "content_map_version_id": "content-map-other"},
        created_at=NOW,
        source_thread_id="thread-2",
        source_run_id="run-3",
    )
    revised_feedback = _correction().model_copy(update={"status": "contested", "revision_reason": "另一条路线也可能成立。"})

    with pytest.raises(ValueError, match="same content map"):
        seal_root_feedback_record(
            project=_project(),
            content_map=different_map,
            feedback=revised_feedback,
            previous_feedback=original,
            created_at=NOW,
            source_thread_id="thread-2",
            source_run_id="run-4",
        )
