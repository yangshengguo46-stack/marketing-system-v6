from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from deerflow.incubation.contracts import ArtifactEnvelope, ProjectRef

NonEmptyStr = Annotated[str, Field(min_length=1)]
RootCandidateOrigin = Literal["model", "user_added"]
RootCandidateDecision = Literal["best", "acceptable", "rejected"]
RootFeasibility = Literal["strong", "conditional", "weak", "unknown"]
RootFeedbackErrorKind = Literal[
    "candidate_recall",
    "candidate_selection",
    "ip_feasibility",
    "label_disagreement",
]
RootFeedbackStatus = Literal[
    "proposed",
    "confirmed",
    "contested",
    "superseded",
    "retired",
]


class RootFeedbackContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class RootCandidateFeedback(RootFeedbackContract):
    label: NonEmptyStr
    origin: RootCandidateOrigin
    decision: RootCandidateDecision
    reason: NonEmptyStr


class RootFeedbackRecord(RootFeedbackContract):
    """One user-reviewable content-root experience, never an automatic rule."""

    user_utterance: NonEmptyStr
    commercial_object: NonEmptyStr
    evaluated_content_root: NonEmptyStr
    candidate_feedback: Annotated[tuple[RootCandidateFeedback, ...], Field(min_length=1)]
    no_strong_root: bool = False
    ip_feasibility: RootFeasibility
    conditions: tuple[NonEmptyStr, ...] = ()
    unknowns: tuple[NonEmptyStr, ...] = ()
    error_kinds: tuple[RootFeedbackErrorKind, ...] = ()
    status: RootFeedbackStatus
    revision_reason: NonEmptyStr | None = None

    @model_validator(mode="after")
    def validate_feedback(self) -> RootFeedbackRecord:
        normalized_labels = [item.label.casefold() for item in self.candidate_feedback]
        if len(normalized_labels) != len(set(normalized_labels)):
            raise ValueError("candidate labels must be unique")
        if len(self.error_kinds) != len(set(self.error_kinds)):
            raise ValueError("error kinds must be unique")

        evaluated = [item for item in self.candidate_feedback if item.label == self.evaluated_content_root]
        if len(evaluated) != 1 or evaluated[0].origin != "model":
            raise ValueError("evaluated content root must identify exactly one model candidate")
        evaluated_candidate = evaluated[0]

        best = [item for item in self.candidate_feedback if item.decision == "best"]
        if self.no_strong_root and best:
            raise ValueError("no_strong_root feedback cannot select a best candidate")
        if self.status == "confirmed" and not self.no_strong_root and len(best) != 1:
            raise ValueError("confirmed feedback requires exactly one best candidate")
        if len(best) > 1:
            raise ValueError("feedback cannot select more than one best candidate")

        if any(item.origin == "user_added" for item in self.candidate_feedback) and "candidate_recall" not in self.error_kinds:
            raise ValueError("a user-added candidate requires candidate_recall")

        another_best = any(item.decision == "best" and item.label != self.evaluated_content_root for item in self.candidate_feedback)
        rejected_without_root = self.no_strong_root and evaluated_candidate.decision == "rejected"
        if (another_best or rejected_without_root) and "candidate_selection" not in self.error_kinds:
            raise ValueError("replacing or rejecting the evaluated root requires candidate_selection")

        if self.ip_feasibility == "conditional" and not self.conditions:
            raise ValueError("conditional IP feasibility requires at least one condition")

        if self.status in {"contested", "superseded", "retired"} and self.revision_reason is None:
            raise ValueError("non-initial feedback status requires a revision reason")
        return self


def seal_root_feedback_record(
    *,
    project: ProjectRef,
    content_map: ArtifactEnvelope,
    feedback: RootFeedbackRecord,
    created_at: datetime,
    source_thread_id: str,
    source_run_id: str,
    previous_feedback: ArtifactEnvelope | None = None,
) -> ArtifactEnvelope:
    """Seal feedback without retrieving it or changing any runtime prompt."""

    feedback = RootFeedbackRecord.model_validate(feedback.model_dump(mode="python"))
    if content_map.project != project:
        raise ValueError("content map project must match feedback project")
    if content_map.artifact_type != "content_map_candidate":
        raise ValueError("root feedback requires a content_map_candidate parent")
    if content_map.payload.get("content_root") != feedback.evaluated_content_root:
        raise ValueError("evaluated content root must match the parent content map")

    parent_refs = [content_map.to_parent_ref()]
    if previous_feedback is not None:
        if previous_feedback.project != project:
            raise ValueError("previous feedback project must match")
        if previous_feedback.artifact_type != "content_root_feedback":
            raise ValueError("previous feedback parent must be content_root_feedback")
        if content_map.to_parent_ref() not in previous_feedback.parents:
            raise ValueError("previous feedback must evaluate the same content map")
        for field in ("user_utterance", "commercial_object", "evaluated_content_root"):
            if previous_feedback.payload.get(field) != getattr(feedback, field):
                raise ValueError(f"previous feedback {field} must match")
        parent_refs.append(previous_feedback.to_parent_ref())
    elif feedback.status in {"contested", "superseded", "retired"}:
        raise ValueError("non-initial feedback status requires a previous feedback parent")

    return ArtifactEnvelope.seal(
        project=project,
        artifact_type="content_root_feedback",
        version=1,
        payload=feedback.model_dump(mode="json", exclude_none=True),
        account=content_map.account,
        parents=tuple(parent_refs),
        created_at=created_at,
        source_thread_id=source_thread_id,
        source_run_id=source_run_id,
    )
