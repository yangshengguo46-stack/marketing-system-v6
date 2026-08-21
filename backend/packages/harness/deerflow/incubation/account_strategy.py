from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Protocol

from deerflow.incubation.account_audience import (
    AccountAudienceDecision,
    MarketingSubjectSnapshot,
)
from deerflow.incubation.brief_runtime import (
    build_minimal_incubation_brief,
    build_subject_incubation_brief,
)
from deerflow.incubation.content_run import seal_content_run_artifacts
from deerflow.incubation.contracts import (
    ArtifactEnvelope,
    LogicalAccountRef,
    PlatformAccountRef,
    ProjectRef,
)
from deerflow.incubation.judgment import IncubationJudgment, seal_incubation_judgment
from deerflow.incubation.judgment_runtime import StructuredJudgmentModel, generate_incubation_judgment
from deerflow.incubation.project_evidence import select_project_judgment_evidence

if TYPE_CHECKING:
    from deerflow.content_intelligence import ContentIntelligenceBundle


class AccountStrategyRepository(Protocol):
    async def put_artifact(self, artifact: ArtifactEnvelope) -> ArtifactEnvelope: ...

    async def list_artifacts(
        self,
        project: ProjectRef,
        *,
        logical_account: LogicalAccountRef | None = None,
        artifact_type: str | None = None,
        evidence_role: str | None = None,
    ) -> list[ArtifactEnvelope]: ...


@dataclass(frozen=True, slots=True)
class PreparedAccountStrategy:
    judgment: IncubationJudgment
    judgment_artifact: ArtifactEnvelope
    reused: bool


def select_current_account_strategy(
    artifacts: list[ArtifactEnvelope] | tuple[ArtifactEnvelope, ...],
    *,
    logical_account: LogicalAccountRef | None = None,
    account: PlatformAccountRef | None = None,
    content_map_version_id: str | None = None,
    require_confirmed: bool = False,
) -> PreparedAccountStrategy | None:
    candidates: list[tuple[IncubationJudgment, ArtifactEnvelope]] = []
    for artifact in artifacts:
        if artifact.artifact_type != "incubation_judgment" or artifact.logical_account != logical_account or artifact.account != account:
            continue
        judgment = IncubationJudgment.model_validate(artifact.payload)
        if artifact.version != judgment.revision_number:
            raise ValueError("incubation judgment envelope version must match revision_number")
        if require_confirmed and judgment.decision_status != "confirmed":
            continue
        if content_map_version_id is not None and judgment.content_map_version_id != content_map_version_id:
            continue
        candidates.append((judgment, artifact))
    if not candidates:
        return None
    judgment, artifact = max(
        candidates,
        key=lambda item: (
            item[0].revision_number,
            item[1].created_at,
            item[1].artifact_id,
        ),
    )
    return PreparedAccountStrategy(
        judgment=judgment,
        judgment_artifact=artifact,
        reused=True,
    )


def _proposal_parent_artifacts(
    *,
    proposal_artifact: ArtifactEnvelope,
    artifacts: list[ArtifactEnvelope],
) -> tuple[
    ArtifactEnvelope,
    ArtifactEnvelope,
    ArtifactEnvelope | None,
    tuple[ArtifactEnvelope, ...],
]:
    by_id = {artifact.artifact_id: artifact for artifact in artifacts}
    parents: list[ArtifactEnvelope] = []
    for parent in proposal_artifact.parents:
        if parent.artifact_type == "incubation_judgment":
            continue
        artifact = by_id.get(parent.artifact_id)
        if artifact is None:
            raise ValueError("account strategy proposal parent is unavailable")
        if artifact.content_sha256 != parent.content_sha256 or artifact.artifact_type != parent.artifact_type:
            raise ValueError("account strategy proposal parent receipt does not match storage")
        parents.append(artifact)
    briefs = tuple(artifact for artifact in parents if artifact.artifact_type == "incubation_brief")
    maps = tuple(artifact for artifact in parents if artifact.artifact_type == "content_map_candidate")
    audience_decisions = tuple(artifact for artifact in parents if artifact.artifact_type == "account_audience_decision")
    if len(briefs) != 1 or len(maps) != 1:
        raise ValueError("account strategy proposal requires exactly one brief and candidate map")
    if len(audience_decisions) > 1:
        raise ValueError("account strategy proposal has multiple audience decisions")
    evidence = tuple(
        artifact
        for artifact in parents
        if artifact.artifact_type
        not in {
            "incubation_brief",
            "content_map_candidate",
            "account_audience_decision",
        }
    )
    return (
        briefs[0],
        maps[0],
        audience_decisions[0] if audience_decisions else None,
        evidence,
    )


async def confirm_account_strategy(
    *,
    project: ProjectRef,
    logical_account: LogicalAccountRef,
    repository: AccountStrategyRepository,
    option_id: str,
    created_at: datetime,
    source_thread_id: str,
    source_run_id: str,
    account: PlatformAccountRef | None = None,
) -> PreparedAccountStrategy:
    """Confirm one offered route without requiring a bound platform account."""

    artifacts = await repository.list_artifacts(
        project,
        logical_account=logical_account,
    )
    current = select_current_account_strategy(
        artifacts,
        logical_account=logical_account,
        account=account,
    )
    if current is None:
        raise ValueError("account strategy proposal is unavailable")
    proposal = current.judgment
    if proposal.decision_status == "confirmed":
        if proposal.selected_option_id == option_id:
            return current
        raise ValueError("the current account strategy is already confirmed")
    selected = next(
        (option for option in proposal.route_options if option.option_id == option_id),
        None,
    )
    if selected is None:
        raise ValueError("unknown account route option")

    (
        brief_artifact,
        content_map_artifact,
        audience_decision_artifact,
        evidence_artifacts,
    ) = _proposal_parent_artifacts(
        proposal_artifact=current.judgment_artifact,
        artifacts=artifacts,
    )
    confirmed = proposal.model_copy(
        update={
            "revision_number": proposal.revision_number + 1,
            "supersedes_judgment_artifact_id": current.judgment_artifact.artifact_id,
            "revision_reason": f"用户确认账号路线：{selected.name}。",
            "decision_status": "confirmed",
            "selected_option_id": selected.option_id,
            "positioning": selected.positioning,
            "business_intent": selected.business_intent,
            "audience": selected.audience,
            "persona": selected.persona,
            "presentation": selected.presentation,
            "monetization": selected.monetization,
        }
    )
    judgment_artifact = seal_incubation_judgment(
        project=project,
        judgment=confirmed,
        brief_artifact=brief_artifact,
        content_world_artifact=content_map_artifact,
        audience_decision_artifact=audience_decision_artifact,
        evidence_artifacts=evidence_artifacts,
        previous_judgment_artifact=current.judgment_artifact,
        logical_account=logical_account,
        account=account,
        created_at=created_at,
        source_thread_id=source_thread_id,
        source_run_id=source_run_id,
    )
    judgment_artifact = await repository.put_artifact(judgment_artifact)
    return PreparedAccountStrategy(
        judgment=IncubationJudgment.model_validate(judgment_artifact.payload),
        judgment_artifact=judgment_artifact,
        reused=False,
    )


def _same_strategy_inputs(
    previous: ArtifactEnvelope,
    current_inputs: tuple[ArtifactEnvelope, ...],
) -> bool:
    previous_input_ids = {parent.artifact_id for parent in previous.parents if parent.artifact_type != "incubation_judgment"}
    return previous_input_ids == {artifact.artifact_id for artifact in current_inputs}


async def prepare_account_strategy(
    *,
    project: ProjectRef,
    logical_account: LogicalAccountRef,
    repository: AccountStrategyRepository,
    bundle: ContentIntelligenceBundle,
    verbatim_user_request: str,
    structured_model: StructuredJudgmentModel,
    created_at: datetime,
    source_thread_id: str,
    source_run_id: str,
    account: PlatformAccountRef | None = None,
    prohibited_assumptions: tuple[str, ...] = (),
    marketing_subject: MarketingSubjectSnapshot | None = None,
    subject_parent_artifacts: tuple[ArtifactEnvelope, ...] = (),
    audience_decision_artifact: ArtifactEnvelope | None = None,
) -> PreparedAccountStrategy:
    """Create or reuse the project's versioned account-incubation judgment.

    Candidate content maps and benchmark/audience observations remain immutable
    inputs. This service alone selects those evidence roles and creates a new
    account-strategy version when the input set changes.
    """

    prerequisites = seal_content_run_artifacts(
        project=project,
        bundle=bundle,
        delivery=None,
        created_at=created_at,
        source_thread_id=source_thread_id,
        source_run_id=source_run_id,
        logical_account=logical_account,
    )
    stored_prerequisites: dict[str, ArtifactEnvelope] = {}
    for artifact in prerequisites.storage_order():
        stored = await repository.put_artifact(artifact)
        stored_prerequisites[stored.artifact_type] = stored

    content_map_artifact = stored_prerequisites["content_map_candidate"]
    world = bundle.content_world
    if world is None or world.content_root is None:
        raise ValueError("account strategy requires a candidate content map")
    if marketing_subject is None:
        if audience_decision_artifact is not None or subject_parent_artifacts:
            raise ValueError("audience and subject parents require a marketing subject")
        brief_artifact = build_minimal_incubation_brief(
            project=project,
            verbatim_user_request=verbatim_user_request,
            source_object=world.source_object,
            created_at=created_at,
            source_thread_id=source_thread_id,
            source_run_id=source_run_id,
            logical_account=logical_account,
            prohibited_assumptions=prohibited_assumptions,
        )
    else:
        marketing_subject = MarketingSubjectSnapshot.model_validate(marketing_subject.model_dump(mode="python"))
        if audience_decision_artifact is None:
            raise ValueError("a marketing subject requires its selected audience decision")
        if audience_decision_artifact.artifact_type != "account_audience_decision":
            raise ValueError("expected an account audience decision")
        if audience_decision_artifact.project != project:
            raise ValueError("account audience project must match strategy project")
        if audience_decision_artifact.logical_account != logical_account:
            raise ValueError("account audience logical account must match strategy account")
        audience_decision = AccountAudienceDecision.model_validate(audience_decision_artifact.payload)
        if audience_decision.decision_status not in {"resolved", "confirmed"}:
            raise ValueError("account strategy requires a resolved audience")
        if audience_decision.subject != marketing_subject:
            raise ValueError("account audience subject must match the strategy subject")
        brief_artifact = build_subject_incubation_brief(
            project=project,
            logical_account=logical_account,
            subject=marketing_subject,
            source_object=world.source_object,
            parent_artifacts=subject_parent_artifacts,
            created_at=created_at,
            source_thread_id=source_thread_id,
            source_run_id=source_run_id,
            prohibited_assumptions=prohibited_assumptions,
        )
    brief_artifact = await repository.put_artifact(brief_artifact)

    artifacts = await repository.list_artifacts(
        project,
        logical_account=logical_account,
    )
    selected_evidence = select_project_judgment_evidence(
        project=project,
        artifacts=artifacts,
    )
    current = select_current_account_strategy(
        artifacts,
        logical_account=logical_account,
        account=account,
    )
    current_inputs = (
        brief_artifact,
        content_map_artifact,
        *((audience_decision_artifact,) if audience_decision_artifact is not None else ()),
        *selected_evidence.benchmark_evidence_artifacts,
        *selected_evidence.audience_evidence_artifacts,
    )
    if current is not None and current.judgment.route_options and _same_strategy_inputs(current.judgment_artifact, current_inputs):
        return current

    judgment_artifact = await generate_incubation_judgment(
        project=project,
        brief_artifact=brief_artifact,
        content_world_artifact=content_map_artifact,
        audience_decision_artifact=audience_decision_artifact,
        structured_model=structured_model,
        benchmark_evidence_artifacts=selected_evidence.benchmark_evidence_artifacts,
        audience_evidence_artifacts=selected_evidence.audience_evidence_artifacts,
        previous_judgment_artifact=(current.judgment_artifact if current is not None else None),
        logical_account=logical_account,
        account=account,
        created_at=created_at,
        source_thread_id=source_thread_id,
        source_run_id=source_run_id,
    )
    judgment = IncubationJudgment.model_validate(judgment_artifact.payload)
    if judgment.decision_status != "proposed" or len(judgment.route_options) < 2:
        raise ValueError("account strategy generation requires a multi-route proposal")
    judgment_artifact = await repository.put_artifact(judgment_artifact)
    return PreparedAccountStrategy(
        judgment=judgment,
        judgment_artifact=judgment_artifact,
        reused=False,
    )


__all__ = [
    "AccountStrategyRepository",
    "PreparedAccountStrategy",
    "confirm_account_strategy",
    "prepare_account_strategy",
    "select_current_account_strategy",
]
