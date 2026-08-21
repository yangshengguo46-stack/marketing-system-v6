from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, Protocol

from pydantic import Field, field_validator, model_validator

from deerflow.incubation.contracts import (
    ArtifactEnvelope,
    IncubationContract,
    LogicalAccountRef,
    NonEmptyStr,
    ProjectRef,
)

MarketingSubjectKind = Literal["user_business", "agent_self"]
AudienceDecisionStatus = Literal["proposed", "resolved", "confirmed"]
Confidence = Literal["low", "medium", "high"]


class AccountAudienceRepository(Protocol):
    async def list_artifacts(
        self,
        project: ProjectRef,
        *,
        logical_account: LogicalAccountRef | None = None,
        artifact_type: str | None = None,
        evidence_role: str | None = None,
    ) -> list[ArtifactEnvelope]: ...

    async def put_artifact(self, artifact: ArtifactEnvelope) -> ArtifactEnvelope: ...


@dataclass(frozen=True, slots=True)
class PreparedAccountAudience:
    decision: AccountAudienceDecision
    decision_artifact: ArtifactEnvelope
    reused: bool


class MarketingSubjectSnapshot(IncubationContract):
    """The exact entity whose account is being incubated.

    User businesses come from the user's words. The host Agent uses a bounded,
    server-owned product profile instead of treating second-person references
    such as "你自己" as an unknown customer business.
    """

    subject_kind: MarketingSubjectKind
    subject_expression: NonEmptyStr = Field(max_length=2_000)
    source_user_request: NonEmptyStr = Field(max_length=8_000)
    business_facts: tuple[NonEmptyStr, ...] = Field(min_length=1, max_length=16)
    capabilities: tuple[NonEmptyStr, ...] = Field(default=(), max_length=16)
    resources: tuple[NonEmptyStr, ...] = Field(default=(), max_length=16)
    constraints: tuple[NonEmptyStr, ...] = Field(default=(), max_length=16)
    goals: tuple[NonEmptyStr, ...] = Field(default=(), max_length=8)
    basis_artifact_ids: tuple[NonEmptyStr, ...] = Field(default=(), max_length=4)

    @field_validator("basis_artifact_ids")
    @classmethod
    def canonicalize_basis_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(value)) != len(value):
            raise ValueError("subject basis artifact ids must be unique")
        return tuple(sorted(value))


class AccountAudienceRouteDraft(IncubationContract):
    """One materially distinct business-audience route before content mapping."""

    option_id: NonEmptyStr = Field(max_length=80, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    name: NonEmptyStr = Field(max_length=120)
    business_role: NonEmptyStr = Field(max_length=500)
    market_relationship: NonEmptyStr = Field(max_length=800)
    account_objective: NonEmptyStr = Field(max_length=1_000)
    payer_or_contracting_party: NonEmptyStr = Field(max_length=800)
    decision_makers: NonEmptyStr = Field(max_length=800)
    users_or_beneficiaries: NonEmptyStr = Field(max_length=800)
    target_people: NonEmptyStr = Field(max_length=800)
    target_need: NonEmptyStr = Field(max_length=1_000)
    desired_action: NonEmptyStr = Field(max_length=800)
    market_scope: NonEmptyStr = Field(max_length=800)
    content_audience: NonEmptyStr = Field(max_length=800)
    recurring_interest: NonEmptyStr = Field(max_length=1_000)
    rationale: NonEmptyStr = Field(max_length=1_200)
    confidence: Confidence = "low"
    unknowns: tuple[NonEmptyStr, ...] = Field(default=(), max_length=6)


class AccountAudienceProposalDraft(IncubationContract):
    """Thin model output; code owns selection and persistence state."""

    route_options: tuple[AccountAudienceRouteDraft, ...] = Field(min_length=1, max_length=3)
    recommended_option_id: NonEmptyStr = Field(max_length=80)
    material_choice_required: bool
    choice_reason: NonEmptyStr = Field(max_length=1_000)
    unknowns: tuple[NonEmptyStr, ...] = Field(default=(), max_length=6)

    @model_validator(mode="after")
    def validate_routes(self) -> AccountAudienceProposalDraft:
        option_ids = tuple(option.option_id for option in self.route_options)
        if len(set(option_ids)) != len(option_ids):
            raise ValueError("audience route option ids must be unique")
        if self.recommended_option_id not in option_ids:
            raise ValueError("recommended audience option must identify one route")
        if self.material_choice_required and len(self.route_options) < 2:
            raise ValueError("material audience choice requires at least two routes")
        if not self.material_choice_required and len(self.route_options) != 1:
            raise ValueError("a resolved audience route must contain exactly one route")
        return self


class AccountAudienceDecision(IncubationContract):
    schema_version: Literal["v6-account-audience-v1"] = "v6-account-audience-v1"
    revision_number: int = Field(ge=1)
    decision_status: AudienceDecisionStatus
    subject: MarketingSubjectSnapshot
    route_options: tuple[AccountAudienceRouteDraft, ...] = Field(min_length=1, max_length=3)
    recommended_option_id: NonEmptyStr = Field(max_length=80)
    selected_option_id: NonEmptyStr | None = Field(default=None, max_length=80)
    choice_reason: NonEmptyStr = Field(max_length=1_000)
    unknowns: tuple[NonEmptyStr, ...] = Field(default=(), max_length=6)

    @model_validator(mode="after")
    def validate_state(self) -> AccountAudienceDecision:
        option_ids = tuple(option.option_id for option in self.route_options)
        if len(set(option_ids)) != len(option_ids):
            raise ValueError("audience route option ids must be unique")
        if self.recommended_option_id not in option_ids:
            raise ValueError("recommended audience option must identify one route")
        if self.decision_status == "proposed":
            if len(self.route_options) < 2:
                raise ValueError("a proposed audience decision requires alternatives")
            if self.selected_option_id is not None:
                raise ValueError("a proposed audience decision cannot select for the user")
        elif self.selected_option_id not in option_ids:
            raise ValueError("a resolved audience decision requires one selected route")
        if self.revision_number == 1 and self.decision_status == "confirmed":
            raise ValueError("a user-confirmed audience decision must follow a proposal")
        return self

    def selected_route(self) -> AccountAudienceRouteDraft | None:
        if self.selected_option_id is None:
            return None
        return next(option for option in self.route_options if option.option_id == self.selected_option_id)


def compile_account_audience_decision(
    *,
    subject: MarketingSubjectSnapshot,
    draft: AccountAudienceProposalDraft,
) -> AccountAudienceDecision:
    """Turn a model draft into server-owned proposal or resolved state."""

    subject = MarketingSubjectSnapshot.model_validate(subject.model_dump(mode="python"))
    draft = AccountAudienceProposalDraft.model_validate(draft.model_dump(mode="python"))
    selected_option_id = None
    decision_status: AudienceDecisionStatus = "proposed"
    if not draft.material_choice_required:
        selected_option_id = draft.route_options[0].option_id
        decision_status = "resolved"
    return AccountAudienceDecision(
        revision_number=1,
        decision_status=decision_status,
        subject=subject,
        route_options=draft.route_options,
        recommended_option_id=draft.recommended_option_id,
        selected_option_id=selected_option_id,
        choice_reason=draft.choice_reason,
        unknowns=draft.unknowns,
    )


def seal_account_audience_decision(
    *,
    project: ProjectRef,
    logical_account: LogicalAccountRef,
    decision: AccountAudienceDecision,
    created_at: datetime,
    source_thread_id: str,
    source_run_id: str,
    parent_artifacts: tuple[ArtifactEnvelope, ...] = (),
) -> ArtifactEnvelope:
    decision = AccountAudienceDecision.model_validate(decision.model_dump(mode="python"))
    for artifact in parent_artifacts:
        if artifact.project != project:
            raise ValueError("account audience parent project must match")
        if artifact.logical_account not in {None, logical_account}:
            raise ValueError("account audience parent logical account must match")
    available_parent_ids = {
        artifact_id
        for artifact in parent_artifacts
        for artifact_id in (
            artifact.artifact_id,
            *(parent.artifact_id for parent in artifact.parents),
        )
    }
    if not set(decision.subject.basis_artifact_ids).issubset(available_parent_ids):
        raise ValueError("account audience subject basis must be included as a parent")
    return ArtifactEnvelope.seal(
        project=project,
        artifact_type="account_audience_decision",
        version=decision.revision_number,
        payload=decision.model_dump(mode="json"),
        logical_account=logical_account,
        parents=tuple(artifact.to_parent_ref() for artifact in parent_artifacts),
        created_at=created_at,
        source_thread_id=source_thread_id,
        source_run_id=source_run_id,
    )


def confirm_account_audience_decision(
    *,
    proposed_artifact: ArtifactEnvelope,
    option_id: str,
    created_at: datetime,
    source_thread_id: str,
    source_run_id: str,
) -> ArtifactEnvelope:
    if proposed_artifact.artifact_type != "account_audience_decision":
        raise ValueError("expected an account audience proposal")
    if proposed_artifact.logical_account is None:
        raise ValueError("account audience proposal requires a logical account")
    proposed = AccountAudienceDecision.model_validate(proposed_artifact.payload)
    if proposed.decision_status != "proposed":
        raise ValueError("only a proposed audience decision can be confirmed")
    if option_id not in {option.option_id for option in proposed.route_options}:
        raise ValueError("unknown account audience option")
    confirmed = proposed.model_copy(
        update={
            "revision_number": proposed.revision_number + 1,
            "decision_status": "confirmed",
            "selected_option_id": option_id,
        }
    )
    return seal_account_audience_decision(
        project=proposed_artifact.project,
        logical_account=proposed_artifact.logical_account,
        decision=confirmed,
        parent_artifacts=(proposed_artifact,),
        created_at=created_at,
        source_thread_id=source_thread_id,
        source_run_id=source_run_id,
    )


def select_current_account_audience(
    artifacts: list[ArtifactEnvelope] | tuple[ArtifactEnvelope, ...],
    *,
    logical_account: LogicalAccountRef,
) -> PreparedAccountAudience | None:
    candidates: list[tuple[AccountAudienceDecision, ArtifactEnvelope]] = []
    for artifact in artifacts:
        if artifact.artifact_type != "account_audience_decision":
            continue
        if artifact.logical_account != logical_account:
            continue
        decision = AccountAudienceDecision.model_validate(artifact.payload)
        if artifact.version != decision.revision_number:
            raise ValueError("account audience artifact version must match revision")
        candidates.append((decision, artifact))
    if not candidates:
        return None
    decision, artifact = max(
        candidates,
        key=lambda item: (
            item[1].created_at,
            item[0].revision_number,
            item[1].artifact_id,
        ),
    )
    return PreparedAccountAudience(
        decision=decision,
        decision_artifact=artifact,
        reused=True,
    )


async def prepare_account_audience(
    *,
    project: ProjectRef,
    logical_account: LogicalAccountRef,
    repository: AccountAudienceRepository,
    subject: MarketingSubjectSnapshot | None,
    structured_model: Any,
    created_at: datetime,
    source_thread_id: str,
    source_run_id: str,
    option_id: str | None = None,
    expected_subject_kind: MarketingSubjectKind | None = None,
    subject_parent_artifacts: tuple[ArtifactEnvelope, ...] = (),
) -> PreparedAccountAudience:
    """Resolve or persist the business audience before content-map work."""

    artifacts = await repository.list_artifacts(
        project,
        logical_account=logical_account,
    )
    current = select_current_account_audience(
        artifacts,
        logical_account=logical_account,
    )
    if option_id is not None:
        if current is None:
            raise ValueError("account audience proposal is unavailable")
        if expected_subject_kind is not None and current.decision.subject.subject_kind != expected_subject_kind:
            raise ValueError("the selected audience route belongs to a different marketing subject")
        if current.decision.decision_status in {"resolved", "confirmed"}:
            if current.decision.selected_option_id == option_id:
                return current
            raise ValueError("the current account audience is already resolved")
        confirmed_artifact = confirm_account_audience_decision(
            proposed_artifact=current.decision_artifact,
            option_id=option_id,
            created_at=created_at,
            source_thread_id=source_thread_id,
            source_run_id=source_run_id,
        )
        confirmed_artifact = await repository.put_artifact(confirmed_artifact)
        return PreparedAccountAudience(
            decision=AccountAudienceDecision.model_validate(confirmed_artifact.payload),
            decision_artifact=confirmed_artifact,
            reused=False,
        )

    if subject is None:
        raise ValueError("a marketing subject is required for audience generation")
    subject = MarketingSubjectSnapshot.model_validate(subject.model_dump(mode="python"))
    if expected_subject_kind is not None and subject.subject_kind != expected_subject_kind:
        raise ValueError("the audience subject does not match the expected marketing subject")
    if current is not None and current.decision.subject == subject:
        return current
    if structured_model is None:
        raise ValueError("a structured model is required for audience generation")

    from deerflow.incubation.account_audience_runtime import (
        generate_account_audience_decision,
    )

    decision = await generate_account_audience_decision(
        subject=subject,
        structured_model=structured_model,
    )
    artifact = seal_account_audience_decision(
        project=project,
        logical_account=logical_account,
        decision=decision,
        parent_artifacts=subject_parent_artifacts,
        created_at=created_at,
        source_thread_id=source_thread_id,
        source_run_id=source_run_id,
    )
    artifact = await repository.put_artifact(artifact)
    return PreparedAccountAudience(
        decision=AccountAudienceDecision.model_validate(artifact.payload),
        decision_artifact=artifact,
        reused=False,
    )


def render_account_audience_decision(decision: AccountAudienceDecision) -> str:
    decision = AccountAudienceDecision.model_validate(decision.model_dump(mode="python"))
    if decision.decision_status != "proposed":
        route = decision.selected_route()
        if route is None:
            raise ValueError("resolved audience decision has no selected route")
        return "\n".join(
            (
                "# 已明确账号要影响谁",
                "",
                f"**当前路线：** {route.name}（`{route.option_id}`）",
                "",
                f"**业务要影响的人：** {route.target_people}",
                "",
                f"**谁会长期看内容：** {route.content_audience}",
            )
        )

    lines = [
        "# 先确认账号要影响谁",
        "",
        decision.choice_reason,
    ]
    for index, route in enumerate(decision.route_options, start=1):
        recommended = "（推荐）" if route.option_id == decision.recommended_option_id else ""
        lines.extend(
            (
                "",
                f"## {index}. {route.name}{recommended}",
                "",
                f"**路线编号：** `{route.option_id}`",
                "",
                f"**业务角色：** {route.business_role}",
                "",
                f"**账号要完成什么：** {route.account_objective}",
                "",
                f"**谁付钱或签约：** {route.payer_or_contracting_party}",
                "",
                f"**谁做决定：** {route.decision_makers}",
                "",
                f"**谁使用或受益：** {route.users_or_beneficiaries}",
                "",
                f"**业务真正要影响谁：** {route.target_people}",
                "",
                f"**他们为什么需要：** {route.target_need}",
                "",
                f"**希望他们下一步做什么：** {route.desired_action}",
                "",
                f"**谁会长期看内容：** {route.content_audience}",
                "",
                f"**他们会持续关心什么：** {route.recurring_interest}",
                "",
                f"**当前置信度：** {route.confidence}",
            )
        )
        if route.unknowns:
            lines.extend(("", "**仍未知：** " + "；".join(route.unknowns)))
    if decision.unknowns:
        lines.extend(("", "## 共同未知", "", "；".join(decision.unknowns)))
    lines.extend(
        (
            "",
            "请先选择路线编号。这个选择会决定后续寻找哪类对标、内容根如何收敛，以及账号定位、人设和表现形式。",
        )
    )
    return "\n".join(lines).strip()


__all__ = [
    "AccountAudienceRepository",
    "AccountAudienceDecision",
    "AccountAudienceProposalDraft",
    "AccountAudienceRouteDraft",
    "AudienceDecisionStatus",
    "MarketingSubjectKind",
    "MarketingSubjectSnapshot",
    "PreparedAccountAudience",
    "compile_account_audience_decision",
    "confirm_account_audience_decision",
    "prepare_account_audience",
    "render_account_audience_decision",
    "seal_account_audience_decision",
    "select_current_account_audience",
]
