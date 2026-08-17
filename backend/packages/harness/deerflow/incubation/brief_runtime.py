from __future__ import annotations

from datetime import datetime

from deerflow.incubation.contracts import ArtifactEnvelope, ProjectRef
from deerflow.incubation.judgment import (
    BriefFact,
    IncubationBrief,
    seal_incubation_brief,
)

_MINIMAL_BRIEF_UNKNOWN = "除用户逐字陈述的业务主体外，能力、资源、约束、目标、偏好、受众、变现方式和平台均未确认。"


def _require_nonblank(value: str, *, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be blank")


def build_minimal_incubation_brief(
    *,
    project: ProjectRef,
    verbatim_user_request: str,
    source_object: str,
    created_at: datetime,
    source_thread_id: str,
    source_run_id: str,
) -> ArtifactEnvelope:
    """Seal only the business subject proven by the user's exact words."""

    _require_nonblank(verbatim_user_request, field_name="verbatim_user_request")
    _require_nonblank(source_object, field_name="source_object")
    if source_object not in verbatim_user_request:
        raise ValueError("source_object must be one contiguous verbatim span of verbatim_user_request")

    brief = IncubationBrief(
        subject_expression=verbatim_user_request,
        business_facts=(
            BriefFact(
                statement=source_object,
                provenance="user_stated",
                source_quote=source_object,
            ),
        ),
        unknowns=(_MINIMAL_BRIEF_UNKNOWN,),
    )
    return seal_incubation_brief(
        project=project,
        brief=brief,
        created_at=created_at,
        source_thread_id=source_thread_id,
        source_run_id=source_run_id,
    )


__all__ = ["build_minimal_incubation_brief"]
