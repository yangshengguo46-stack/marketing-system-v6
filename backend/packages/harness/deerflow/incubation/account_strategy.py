from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Protocol

from deerflow.incubation.brief_runtime import build_minimal_incubation_brief
from deerflow.incubation.content_run import seal_content_run_artifacts
from deerflow.incubation.contracts import ArtifactEnvelope, PlatformAccountRef, ProjectRef
from deerflow.incubation.judgment import IncubationJudgment
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
    account: PlatformAccountRef | None = None,
    content_map_version_id: str | None = None,
) -> PreparedAccountStrategy | None:
    candidates: list[tuple[IncubationJudgment, ArtifactEnvelope]] = []
    for artifact in artifacts:
        if artifact.artifact_type != "incubation_judgment" or artifact.account != account:
            continue
        judgment = IncubationJudgment.model_validate(artifact.payload)
        if artifact.version != judgment.revision_number:
            raise ValueError("incubation judgment envelope version must match revision_number")
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


def _same_strategy_inputs(
    previous: ArtifactEnvelope,
    current_inputs: tuple[ArtifactEnvelope, ...],
) -> bool:
    previous_input_ids = {parent.artifact_id for parent in previous.parents if parent.artifact_type != "incubation_judgment"}
    return previous_input_ids == {artifact.artifact_id for artifact in current_inputs}


async def prepare_account_strategy(
    *,
    project: ProjectRef,
    repository: AccountStrategyRepository,
    bundle: ContentIntelligenceBundle,
    verbatim_user_request: str,
    structured_model: StructuredJudgmentModel,
    created_at: datetime,
    source_thread_id: str,
    source_run_id: str,
    account: PlatformAccountRef | None = None,
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
    )
    stored_prerequisites: dict[str, ArtifactEnvelope] = {}
    for artifact in prerequisites.storage_order():
        stored = await repository.put_artifact(artifact)
        stored_prerequisites[stored.artifact_type] = stored

    content_map_artifact = stored_prerequisites["content_map_candidate"]
    world = bundle.content_world
    if world is None or world.content_root is None:
        raise ValueError("account strategy requires a candidate content map")
    brief_artifact = build_minimal_incubation_brief(
        project=project,
        verbatim_user_request=verbatim_user_request,
        source_object=world.source_object,
        created_at=created_at,
        source_thread_id=source_thread_id,
        source_run_id=source_run_id,
    )
    brief_artifact = await repository.put_artifact(brief_artifact)

    artifacts = await repository.list_artifacts(project)
    selected_evidence = select_project_judgment_evidence(
        project=project,
        artifacts=artifacts,
    )
    current = select_current_account_strategy(
        artifacts,
        account=account,
    )
    current_inputs = (
        brief_artifact,
        content_map_artifact,
        *selected_evidence.benchmark_evidence_artifacts,
        *selected_evidence.audience_evidence_artifacts,
    )
    if current is not None and _same_strategy_inputs(current.judgment_artifact, current_inputs):
        return current

    judgment_artifact = await generate_incubation_judgment(
        project=project,
        brief_artifact=brief_artifact,
        content_world_artifact=content_map_artifact,
        structured_model=structured_model,
        benchmark_evidence_artifacts=selected_evidence.benchmark_evidence_artifacts,
        audience_evidence_artifacts=selected_evidence.audience_evidence_artifacts,
        previous_judgment_artifact=(current.judgment_artifact if current is not None else None),
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


__all__ = [
    "AccountStrategyRepository",
    "PreparedAccountStrategy",
    "prepare_account_strategy",
    "select_current_account_strategy",
]
