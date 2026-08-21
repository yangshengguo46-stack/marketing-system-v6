from __future__ import annotations

from datetime import datetime

from deerflow.incubation.contracts import ArtifactEnvelope, LogicalAccountRef, ProjectRef
from deerflow.incubation.judgment import (
    BriefFact,
    IncubationBrief,
    seal_incubation_brief,
)

_MINIMAL_BRIEF_UNKNOWN = "除用户逐字陈述的业务主体外，能力、资源、约束、目标、偏好、受众、变现方式和平台均未确认。"
_BUSINESS_ROLE_IS_NOT_CAPABILITY = "用户的业务身份本身不能证明其拥有相关专业能力、经验、客户案例、素材、供应链、销售渠道、出镜或制作能力。"


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
    logical_account: LogicalAccountRef | None = None,
    prohibited_assumptions: tuple[str, ...] = (),
) -> ArtifactEnvelope:
    """Seal only the business subject proven by the user's exact words."""

    _require_nonblank(verbatim_user_request, field_name="verbatim_user_request")
    _require_nonblank(source_object, field_name="source_object")
    if source_object not in verbatim_user_request:
        raise ValueError("source_object must be one contiguous verbatim span of verbatim_user_request")
    normalized_assumptions = tuple(
        dict.fromkeys(
            (
                _BUSINESS_ROLE_IS_NOT_CAPABILITY,
                *(item.strip() for item in prohibited_assumptions),
            )
        )
    )
    if any(not item for item in normalized_assumptions):
        raise ValueError("prohibited assumptions must not contain blank entries")
    if any(len(item) > 500 for item in normalized_assumptions):
        raise ValueError("a prohibited assumption exceeds the length limit")
    brief = IncubationBrief(
        subject_expression=verbatim_user_request,
        business_facts=(
            BriefFact(
                statement=source_object,
                provenance="user_stated",
                source_quote=source_object,
            ),
        ),
        prohibited_assumptions=normalized_assumptions,
        unknowns=(_MINIMAL_BRIEF_UNKNOWN,),
    )
    return seal_incubation_brief(
        project=project,
        brief=brief,
        created_at=created_at,
        source_thread_id=source_thread_id,
        source_run_id=source_run_id,
        logical_account=logical_account,
    )


__all__ = ["build_minimal_incubation_brief"]
