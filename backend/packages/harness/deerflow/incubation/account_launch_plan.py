from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from deerflow.incubation.account_strategy import select_current_account_strategy
from deerflow.incubation.contracts import ArtifactEnvelope, LogicalAccountRef, ProjectRef
from deerflow.incubation.launch_plan import AccountLaunchPlan, seal_account_launch_plan
from deerflow.incubation.launch_plan_runtime import StructuredLaunchPlanModel, generate_account_launch_plan


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


async def prepare_account_launch_plan(
    *,
    project: ProjectRef,
    logical_account: LogicalAccountRef,
    repository: AccountLaunchPlanRepository,
    planning_request: str,
    structured_model: StructuredLaunchPlanModel,
    created_at: datetime,
    source_thread_id: str,
    source_run_id: str,
) -> PreparedAccountLaunchPlan:
    artifacts = await repository.list_artifacts(
        project,
        logical_account=logical_account,
    )
    strategy = select_current_account_strategy(
        artifacts,
        logical_account=logical_account,
        require_confirmed=True,
    )
    if strategy is None:
        raise ValueError("account launch planning requires a confirmed account strategy")
    by_id = {artifact.artifact_id: artifact for artifact in artifacts}
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
        and current.plan.strategy_artifact_id == strategy.judgment_artifact.artifact_id
        and current.plan.content_map_version_id == strategy.judgment.content_map_version_id
    ):
        return current

    artifact = await generate_account_launch_plan(
        project=project,
        planning_request=planning_request,
        strategy_artifact=strategy.judgment_artifact,
        content_world_artifact=content_world_artifact,
        previous_plan_artifact=(current.plan_artifact if current is not None else None),
        structured_model=structured_model,
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


async def confirm_account_launch_plan(
    *,
    project: ProjectRef,
    logical_account: LogicalAccountRef,
    repository: AccountLaunchPlanRepository,
    created_at: datetime,
    source_thread_id: str,
    source_run_id: str,
) -> PreparedAccountLaunchPlan:
    artifacts = await repository.list_artifacts(
        project,
        logical_account=logical_account,
    )
    current = select_current_account_launch_plan(
        artifacts,
        logical_account=logical_account,
    )
    if current is None:
        raise ValueError("account launch plan proposal is unavailable")
    if current.plan.decision_status == "confirmed":
        return current

    by_id = {artifact.artifact_id: artifact for artifact in artifacts}
    strategy_artifact = _artifact_by_parent(
        parent_owner=current.plan_artifact,
        artifacts_by_id=by_id,
        artifact_type="incubation_judgment",
    )
    content_world_artifact = _artifact_by_parent(
        parent_owner=current.plan_artifact,
        artifacts_by_id=by_id,
        artifact_type="content_map_candidate",
    )
    confirmed_plan = current.plan.model_copy(
        update={
            "revision_number": current.plan.revision_number + 1,
            "supersedes_plan_artifact_id": current.plan_artifact.artifact_id,
            "revision_reason": "用户确认采用当前 7 天与 30 天账号运营计划。",
            "decision_status": "confirmed",
        }
    )
    artifact = seal_account_launch_plan(
        project=project,
        plan=confirmed_plan,
        strategy_artifact=strategy_artifact,
        content_world_artifact=content_world_artifact,
        previous_plan_artifact=current.plan_artifact,
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
    "confirm_account_launch_plan",
    "prepare_account_launch_plan",
    "select_current_account_launch_plan",
]
