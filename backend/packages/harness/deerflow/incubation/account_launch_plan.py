from __future__ import annotations

import asyncio
import threading
import weakref
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from deerflow.incubation.account_direction import (
    AccountDirectionProposal,
    AccountDirectionVersion,
    account_direction_content_root,
    select_current_account_direction,
)
from deerflow.incubation.account_strategy import select_current_account_strategy
from deerflow.incubation.contracts import ArtifactEnvelope, LogicalAccountRef, ProjectRef
from deerflow.incubation.launch_plan import (
    AccountLaunchPlan,
    account_launch_plan_confirmation_text,
    seal_account_launch_plan,
)
from deerflow.incubation.launch_plan_runtime import StructuredLaunchPlanModel, generate_account_launch_plan

_CONFIRMATION_LOCKS: weakref.WeakValueDictionary[tuple[int, str], asyncio.Lock] = weakref.WeakValueDictionary()
_CONFIRMATION_LOCKS_GUARD = threading.Lock()


def _confirmation_lock(
    *,
    logical_account: LogicalAccountRef,
    plan_artifact_id: str,
) -> asyncio.Lock:
    loop = asyncio.get_running_loop()
    identity = "\0".join(
        (
            logical_account.owner_user_id,
            logical_account.project_id,
            logical_account.logical_account_id,
            plan_artifact_id,
        )
    )
    key = (id(loop), identity)
    with _CONFIRMATION_LOCKS_GUARD:
        lock = _CONFIRMATION_LOCKS.get(key)
        if lock is None:
            lock = asyncio.Lock()
            _CONFIRMATION_LOCKS[key] = lock
        return lock


class AccountLaunchPlanRepository(Protocol):
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
class PreparedAccountLaunchPlan:
    plan: AccountLaunchPlan
    plan_artifact: ArtifactEnvelope
    reused: bool


def select_current_account_launch_plan(
    artifacts: list[ArtifactEnvelope] | tuple[ArtifactEnvelope, ...],
    *,
    logical_account: LogicalAccountRef,
    require_confirmed: bool = False,
) -> PreparedAccountLaunchPlan | None:
    candidates: list[tuple[AccountLaunchPlan, ArtifactEnvelope]] = []
    for artifact in artifacts:
        if artifact.artifact_type != "account_launch_plan" or artifact.logical_account != logical_account:
            continue
        plan = AccountLaunchPlan.model_validate(artifact.payload)
        if plan.revision_number != artifact.version:
            raise ValueError("account launch plan version must match its artifact envelope")
        if require_confirmed and plan.decision_status != "confirmed":
            continue
        candidates.append((plan, artifact))
    if not candidates:
        return None
    plan, artifact = max(
        candidates,
        key=lambda item: (item[0].revision_number, item[1].created_at, item[1].artifact_id),
    )
    return PreparedAccountLaunchPlan(plan=plan, plan_artifact=artifact, reused=True)


def _artifact_by_parent(
    *,
    parent_owner: ArtifactEnvelope,
    artifacts_by_id: dict[str, ArtifactEnvelope],
    artifact_type: str,
) -> ArtifactEnvelope:
    refs = tuple(parent for parent in parent_owner.parents if parent.artifact_type == artifact_type)
    if len(refs) != 1:
        raise ValueError(f"artifact requires exactly one {artifact_type} parent")
    ref = refs[0]
    artifact = artifacts_by_id.get(ref.artifact_id)
    if artifact is None or artifact.content_sha256 != ref.content_sha256 or artifact.artifact_type != artifact_type:
        raise ValueError(f"stored {artifact_type} parent does not match its receipt")
    return artifact


def _matching_content_world_for_direction(
    artifacts: list[ArtifactEnvelope],
    *,
    direction_artifact: ArtifactEnvelope,
    direction_proposal_artifact: ArtifactEnvelope,
    content_map_artifact_id: str | None,
) -> ArtifactEnvelope:
    direction = AccountDirectionVersion.model_validate(direction_artifact.payload)
    content_root = account_direction_content_root(direction.selected_option)
    basis_ids = set(direction.basis_artifact_ids)
    basis_refs = {parent for parent in direction_proposal_artifact.parents if parent.artifact_id in basis_ids and parent.artifact_type == "content_map_candidate"}
    candidates = []
    for artifact in artifacts:
        if artifact.artifact_type != "content_map_candidate" or artifact.payload.get("content_root") != content_root:
            continue
        is_direction_child = direction_artifact.to_parent_ref() in artifact.parents
        is_proposal_basis = artifact.to_parent_ref() in basis_refs
        if is_direction_child or is_proposal_basis:
            candidates.append(artifact)
    if not candidates:
        raise ValueError("account direction content root has no explicitly linked candidate content map")
    if content_map_artifact_id is not None:
        selected = next((artifact for artifact in candidates if artifact.artifact_id == content_map_artifact_id), None)
        if selected is None:
            raise ValueError("requested content map is not linked to the confirmed account direction")
        return selected
    if len(candidates) != 1:
        raise ValueError("multiple direction-linked content maps require an exact content map artifact id")
    return candidates[0]


def _exact_direction_proposal_artifact(
    *,
    direction_artifact: ArtifactEnvelope,
    artifacts_by_id: dict[str, ArtifactEnvelope],
) -> ArtifactEnvelope:
    direction = AccountDirectionVersion.model_validate(direction_artifact.payload)
    proposal_artifact = artifacts_by_id.get(direction.proposal_artifact_id)
    if proposal_artifact is None or proposal_artifact.artifact_type != "account_direction_proposal":
        raise ValueError("confirmed account direction requires its exact account direction proposal")
    if proposal_artifact.project != direction_artifact.project or proposal_artifact.logical_account != direction_artifact.logical_account:
        raise ValueError("account direction proposal scope must match the confirmed direction")
    if proposal_artifact.to_parent_ref() not in direction_artifact.parents:
        raise ValueError("confirmed account direction must retain its exact proposal parent")
    proposal = AccountDirectionProposal.model_validate(proposal_artifact.payload)
    if proposal_artifact.version != proposal.target_revision_number:
        raise ValueError("account direction proposal version must match its payload")
    if proposal.target_revision_number != direction.revision_number:
        raise ValueError("account direction proposal revision must match the confirmed direction")
    selected = next(
        (option for option in proposal.direction_options if option.option_id == direction.selected_option.option_id),
        None,
    )
    if selected != direction.selected_option:
        raise ValueError("confirmed account direction must match an exact proposal option")
    if proposal.basis_artifact_ids != direction.basis_artifact_ids:
        raise ValueError("confirmed account direction basis must match its proposal")
    return proposal_artifact


def _validated_confirmation_child(
    *,
    proposal: AccountLaunchPlan,
    proposal_artifact: ArtifactEnvelope,
    confirmed_artifact: ArtifactEnvelope,
    decision_artifact: ArtifactEnvelope,
    content_world_artifact: ArtifactEnvelope,
) -> AccountLaunchPlan:
    """Validate an existing confirmation before treating replay as idempotent."""

    confirmed = AccountLaunchPlan.model_validate(confirmed_artifact.payload)
    if confirmed_artifact.version != confirmed.revision_number:
        raise ValueError("confirmed launch plan version must match its artifact envelope")
    if proposal.decision_status != "proposed" or confirmed.decision_status != "confirmed":
        raise ValueError("account launch plan replay requires an exact proposal and confirmation")
    if confirmed.revision_number != proposal.revision_number + 1:
        raise ValueError("confirmed launch plan revision must immediately follow its proposal")
    if confirmed.supersedes_plan_artifact_id != proposal_artifact.artifact_id:
        raise ValueError("confirmed launch plan must supersede its exact proposal")

    confirmation_fields = {
        "revision_number",
        "supersedes_plan_artifact_id",
        "revision_reason",
        "decision_status",
        "confirmation_user_text",
    }
    if confirmed.model_dump(exclude=confirmation_fields) != proposal.model_dump(exclude=confirmation_fields):
        raise ValueError("confirmed launch plan changed content after its proposal")

    expected_parents = {
        decision_artifact.to_parent_ref(),
        content_world_artifact.to_parent_ref(),
        proposal_artifact.to_parent_ref(),
    }
    if set(confirmed_artifact.parents) != expected_parents:
        raise ValueError("confirmed launch plan does not retain its exact proposal lineage")
    return confirmed


async def prepare_account_launch_plan(
    *,
    project: ProjectRef,
    logical_account: LogicalAccountRef,
    repository: AccountLaunchPlanRepository,
    planning_request: str,
    content_map_artifact_id: str | None = None,
    structured_model: StructuredLaunchPlanModel,
    created_at: datetime,
    source_thread_id: str,
    source_run_id: str,
) -> PreparedAccountLaunchPlan:
    artifacts = await repository.list_artifacts(
        project,
        logical_account=logical_account,
    )
    direction = select_current_account_direction(
        artifacts,
        logical_account=logical_account,
    )
    by_id = {artifact.artifact_id: artifact for artifact in artifacts}
    strategy = None
    direction_proposal_artifact = None
    if direction is not None:
        account_decision_artifact = direction.direction_artifact
        direction_proposal_artifact = _exact_direction_proposal_artifact(
            direction_artifact=account_decision_artifact,
            artifacts_by_id=by_id,
        )
        content_world_artifact = _matching_content_world_for_direction(
            artifacts,
            direction_artifact=account_decision_artifact,
            direction_proposal_artifact=direction_proposal_artifact,
            content_map_artifact_id=content_map_artifact_id,
        )
    else:
        strategy = select_current_account_strategy(
            artifacts,
            logical_account=logical_account,
            require_confirmed=True,
        )
        if strategy is None:
            raise ValueError("account launch planning requires a confirmed account strategy")
        account_decision_artifact = strategy.judgment_artifact
        content_world_artifact = _artifact_by_parent(
            parent_owner=strategy.judgment_artifact,
            artifacts_by_id=by_id,
            artifact_type="content_map_candidate",
        )
    current = select_current_account_launch_plan(
        artifacts,
        logical_account=logical_account,
    )
    if (
        current is not None
        and current.plan.planning_request == planning_request
        and (current.plan.direction_artifact_id or current.plan.strategy_artifact_id) == account_decision_artifact.artifact_id
        and current.plan.content_map_version_id == content_world_artifact.payload.get("content_map_version_id")
        and content_world_artifact.to_parent_ref() in current.plan_artifact.parents
    ):
        return current

    artifact = await generate_account_launch_plan(
        project=project,
        planning_request=planning_request,
        account_decision_artifact=account_decision_artifact,
        content_world_artifact=content_world_artifact,
        previous_plan_artifact=(current.plan_artifact if current is not None else None),
        structured_model=structured_model,
        logical_account=logical_account,
        created_at=created_at,
        source_thread_id=source_thread_id,
        source_run_id=source_run_id,
        direction_proposal_artifact=direction_proposal_artifact,
    )
    artifact = await repository.put_artifact(artifact)
    return PreparedAccountLaunchPlan(
        plan=AccountLaunchPlan.model_validate(artifact.payload),
        plan_artifact=artifact,
        reused=False,
    )


async def confirm_account_launch_plan(
    *,
    project: ProjectRef,
    logical_account: LogicalAccountRef,
    repository: AccountLaunchPlanRepository,
    plan_artifact_id: str,
    confirmation_user_text: str,
    created_at: datetime,
    source_thread_id: str,
    source_run_id: str,
) -> PreparedAccountLaunchPlan:
    expected_confirmation = account_launch_plan_confirmation_text(plan_artifact_id)
    if confirmation_user_text.strip() != expected_confirmation:
        raise ValueError("account launch plan requires the exact confirmation command")
    lock = _confirmation_lock(
        logical_account=logical_account,
        plan_artifact_id=plan_artifact_id,
    )
    async with lock:
        return await _confirm_account_launch_plan_unlocked(
            project=project,
            logical_account=logical_account,
            repository=repository,
            plan_artifact_id=plan_artifact_id,
            confirmation_user_text=expected_confirmation,
            created_at=created_at,
            source_thread_id=source_thread_id,
            source_run_id=source_run_id,
        )


async def _confirm_account_launch_plan_unlocked(
    *,
    project: ProjectRef,
    logical_account: LogicalAccountRef,
    repository: AccountLaunchPlanRepository,
    plan_artifact_id: str,
    confirmation_user_text: str,
    created_at: datetime,
    source_thread_id: str,
    source_run_id: str,
) -> PreparedAccountLaunchPlan:
    artifacts = await repository.list_artifacts(
        project,
        logical_account=logical_account,
    )
    by_id = {artifact.artifact_id: artifact for artifact in artifacts}
    target_artifact = by_id.get(plan_artifact_id)
    if target_artifact is None or target_artifact.artifact_type != "account_launch_plan":
        raise ValueError("exact account launch plan proposal receipt is unavailable")
    target = AccountLaunchPlan.model_validate(target_artifact.payload)
    if target_artifact.version != target.revision_number:
        raise ValueError("account launch plan version must match its artifact envelope")
    if target.decision_status != "proposed":
        raise ValueError("account launch plan confirmation requires a proposed plan")

    decision_artifact_type = "account_direction_version" if target.direction_artifact_id is not None else "incubation_judgment"
    account_decision_artifact = _artifact_by_parent(
        parent_owner=target_artifact,
        artifacts_by_id=by_id,
        artifact_type=decision_artifact_type,
    )
    content_world_artifact = _artifact_by_parent(
        parent_owner=target_artifact,
        artifacts_by_id=by_id,
        artifact_type="content_map_candidate",
    )
    direction_proposal_artifact = None
    if decision_artifact_type == "account_direction_version":
        direction_proposal_artifact = _exact_direction_proposal_artifact(
            direction_artifact=account_decision_artifact,
            artifacts_by_id=by_id,
        )

    confirmed_children = [artifact for artifact in artifacts if artifact.artifact_type == "account_launch_plan" and target_artifact.to_parent_ref() in artifact.parents and artifact.payload.get("decision_status") == "confirmed"]
    if confirmed_children:
        if len(confirmed_children) != 1:
            raise ValueError("account launch plan proposal has conflicting confirmations")
        confirmed_artifact = confirmed_children[0]
        confirmed = _validated_confirmation_child(
            proposal=target,
            proposal_artifact=target_artifact,
            confirmed_artifact=confirmed_artifact,
            decision_artifact=account_decision_artifact,
            content_world_artifact=content_world_artifact,
        )
        return PreparedAccountLaunchPlan(
            plan=confirmed,
            plan_artifact=confirmed_artifact,
            reused=True,
        )
    current = select_current_account_launch_plan(
        artifacts,
        logical_account=logical_account,
    )
    if current is None or current.plan_artifact.artifact_id != plan_artifact_id:
        raise ValueError("the latest account launch plan proposal receipt is required")
    confirmed_plan = target.model_copy(
        update={
            "revision_number": target.revision_number + 1,
            "supersedes_plan_artifact_id": target_artifact.artifact_id,
            "revision_reason": "用户确认采用当前 7 天与 30 天账号运营计划。",
            "decision_status": "confirmed",
            "confirmation_user_text": confirmation_user_text,
        }
    )
    artifact = seal_account_launch_plan(
        project=project,
        plan=confirmed_plan,
        content_world_artifact=content_world_artifact,
        strategy_artifact=(account_decision_artifact if decision_artifact_type == "incubation_judgment" else None),
        direction_artifact=(account_decision_artifact if decision_artifact_type == "account_direction_version" else None),
        direction_proposal_artifact=direction_proposal_artifact,
        previous_plan_artifact=target_artifact,
        logical_account=logical_account,
        created_at=created_at,
        source_thread_id=source_thread_id,
        source_run_id=source_run_id,
    )
    artifact = await repository.put_artifact(artifact)
    return PreparedAccountLaunchPlan(
        plan=AccountLaunchPlan.model_validate(artifact.payload),
        plan_artifact=artifact,
        reused=False,
    )


__all__ = [
    "AccountLaunchPlanRepository",
    "PreparedAccountLaunchPlan",
    "account_launch_plan_confirmation_text",
    "confirm_account_launch_plan",
    "prepare_account_launch_plan",
    "select_current_account_launch_plan",
]
