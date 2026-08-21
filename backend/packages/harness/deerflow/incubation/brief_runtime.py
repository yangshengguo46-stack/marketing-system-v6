from __future__ import annotations

from datetime import datetime

from deerflow.incubation.account_audience import MarketingSubjectSnapshot
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


def build_subject_incubation_brief(
    *,
    project: ProjectRef,
    logical_account: LogicalAccountRef,
    subject: MarketingSubjectSnapshot,
    source_object: str,
    created_at: datetime,
    source_thread_id: str,
    source_run_id: str,
    parent_artifacts: tuple[ArtifactEnvelope, ...] = (),
    prohibited_assumptions: tuple[str, ...] = (),
) -> ArtifactEnvelope:
    """Build a brief from either user words or the trusted host-product profile."""

    subject = MarketingSubjectSnapshot.model_validate(subject.model_dump(mode="python"))
    _require_nonblank(source_object, field_name="source_object")
    if source_object not in subject.subject_expression:
        raise ValueError("source_object must be a contiguous span of the resolved subject")
    normalized_assumptions = tuple(
        dict.fromkeys(
            (
                _BUSINESS_ROLE_IS_NOT_CAPABILITY,
                *(item.strip() for item in prohibited_assumptions),
            )
        )
    )
    if subject.subject_kind == "user_business":
        business_facts = (
            BriefFact(
                statement=source_object,
                provenance="user_stated",
                source_quote=source_object,
            ),
        )
        capabilities: tuple[BriefFact, ...] = ()
        resources: tuple[BriefFact, ...] = ()
        constraints: tuple[BriefFact, ...] = ()
        goals: tuple[BriefFact, ...] = ()
    else:
        parent_ids = {artifact.artifact_id for artifact in parent_artifacts}
        basis_ids = tuple(subject.basis_artifact_ids)
        if not basis_ids or not set(basis_ids).issubset(parent_ids):
            raise ValueError("agent self facts require their host-product profile parent")

        def observed_facts(values: tuple[str, ...]) -> tuple[BriefFact, ...]:
            return tuple(
                BriefFact(
                    statement=value,
                    provenance="authorized_observation",
                    basis_artifact_ids=basis_ids,
                )
                for value in values
            )

        business_facts = observed_facts(subject.business_facts)
        capabilities = observed_facts(subject.capabilities)
        resources = observed_facts(subject.resources)
        constraints = observed_facts(subject.constraints)
        goals = observed_facts(subject.goals)

    brief = IncubationBrief(
        subject_expression=subject.subject_expression,
        business_facts=business_facts,
        capabilities=capabilities,
        resources=resources,
        constraints=constraints,
        goals=goals,
        prohibited_assumptions=normalized_assumptions,
        unknowns=("当前目标人群是起号前假设，仍需由用户选择、对标证据和后续真实反馈校正。",),
    )
    return seal_incubation_brief(
        project=project,
        brief=brief,
        logical_account=logical_account,
        parents=tuple(artifact.to_parent_ref() for artifact in parent_artifacts),
        created_at=created_at,
        source_thread_id=source_thread_id,
        source_run_id=source_run_id,
    )


__all__ = ["build_minimal_incubation_brief", "build_subject_incubation_brief"]
