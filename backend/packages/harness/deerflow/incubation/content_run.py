from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import model_validator

from deerflow.incubation.account_direction import (
    AccountDirectionVersion,
    account_direction_content_root,
)
from deerflow.incubation.content_world import seal_content_world_version
from deerflow.incubation.contracts import (
    ArtifactEnvelope,
    ArtifactParentRef,
    IncubationContract,
    LogicalAccountRef,
    ProjectRef,
)
from deerflow.incubation.evidence import EvidenceSnapshot
from deerflow.incubation.launch_plan import AccountLaunchPlan

if TYPE_CHECKING:
    from datetime import datetime

    from deerflow.content_intelligence import ContentIntelligenceBundle, ShootingDelivery


class ContentRunArtifactSet(IncubationContract):
    content_reading: ArtifactEnvelope
    content_world: ArtifactEnvelope
    topic_brief: ArtifactEnvelope | None = None
    message_plan: ArtifactEnvelope | None = None
    draft_version: ArtifactEnvelope | None = None

    @model_validator(mode="after")
    def validate_chain_shape(self) -> ContentRunArtifactSet:
        if self.topic_brief is None and (self.message_plan is not None or self.draft_version is not None):
            raise ValueError("message plan and draft require a topic brief")
        if self.message_plan is None and self.draft_version is not None:
            raise ValueError("draft version requires a message plan")
        return self

    def storage_order(self) -> tuple[ArtifactEnvelope, ...]:
        return tuple(
            artifact
            for artifact in (
                self.content_reading,
                self.content_world,
                self.topic_brief,
                self.message_plan,
                self.draft_version,
            )
            if artifact is not None
        )


def seal_content_run_artifacts(
    *,
    project: ProjectRef,
    bundle: ContentIntelligenceBundle,
    delivery: ShootingDelivery | None,
    created_at: datetime,
    source_thread_id: str,
    source_run_id: str,
    logical_account: LogicalAccountRef | None = None,
    reading_parents: tuple[ArtifactParentRef, ...] = (),
    incubation_judgment_artifact: ArtifactEnvelope | None = None,
    account_direction_artifact: ArtifactEnvelope | None = None,
    launch_plan_artifact: ArtifactEnvelope | None = None,
    launch_topic_seed_id: str | None = None,
) -> ContentRunArtifactSet:
    """Seal one content-intelligence run without changing its judgments."""

    world = bundle.content_world
    if world is None or world.content_root is None:
        raise ValueError("content run persistence requires a frozen content world")
    if incubation_judgment_artifact is not None:
        if delivery is None and launch_plan_artifact is None:
            raise ValueError("incubation judgment lineage requires a shooting delivery")
        if incubation_judgment_artifact.project != project:
            raise ValueError("incubation judgment project must match content run project")
        if incubation_judgment_artifact.artifact_type != "incubation_judgment":
            raise ValueError("incubation judgment parent has the wrong artifact type")
        if incubation_judgment_artifact.logical_account != logical_account:
            raise ValueError("incubation judgment logical account must match content run")
        if incubation_judgment_artifact.payload.get("content_map_version_id") != world.content_map_version_id():
            raise ValueError("incubation judgment content world version must match the frozen content world")
    if account_direction_artifact is not None:
        if account_direction_artifact.project != project:
            raise ValueError("account direction project must match content run project")
        if account_direction_artifact.artifact_type != "account_direction_version":
            raise ValueError("account direction parent has the wrong artifact type")
        if account_direction_artifact.logical_account != logical_account:
            raise ValueError("account direction logical account must match content run")
        direction = AccountDirectionVersion.model_validate(account_direction_artifact.payload)
        if account_direction_content_root(direction.selected_option) != world.content_root:
            raise ValueError("account direction content root must match the frozen content world")

    launch_plan: AccountLaunchPlan | None = None
    if (launch_plan_artifact is None) != (launch_topic_seed_id is None):
        raise ValueError("launch plan artifact and topic seed id must be supplied together")
    if launch_plan_artifact is not None:
        assert launch_topic_seed_id is not None
        if launch_plan_artifact.project != project:
            raise ValueError("launch plan project must match content run project")
        if launch_plan_artifact.logical_account != logical_account:
            raise ValueError("launch plan logical account must match content run")
        if launch_plan_artifact.artifact_type != "account_launch_plan":
            raise ValueError("launch plan parent has the wrong artifact type")
        launch_plan = AccountLaunchPlan.model_validate(launch_plan_artifact.payload)
        if launch_plan.revision_number != launch_plan_artifact.version:
            raise ValueError("launch plan version must match its artifact envelope")
        if launch_plan.decision_status != "confirmed":
            raise ValueError("launch topic lineage requires a confirmed account launch plan")
        previous_plan_parents = tuple(parent for parent in launch_plan_artifact.parents if parent.artifact_type == "account_launch_plan")
        if len(previous_plan_parents) != 1 or previous_plan_parents[0].artifact_id != launch_plan.supersedes_plan_artifact_id:
            raise ValueError("confirmed launch plan must retain its exact proposal parent")
        if not any(seed.seed_id == launch_topic_seed_id for seed in launch_plan.topic_seeds):
            raise ValueError("launch plan topic seed is unavailable")
        if launch_plan.content_map_version_id != world.content_map_version_id():
            raise ValueError("launch plan content map version must match the frozen content world")

        map_parents = tuple(parent for parent in launch_plan_artifact.parents if parent.artifact_type == "content_map_candidate")
        if len(map_parents) != 1:
            raise ValueError("launch plan requires exactly one candidate-map parent")
        if launch_plan.direction_artifact_id is not None:
            if account_direction_artifact is None or incubation_judgment_artifact is not None:
                raise ValueError("launch plan direction lineage requires its exact account direction")
            if launch_plan.direction_artifact_id != account_direction_artifact.artifact_id or account_direction_artifact.to_parent_ref() not in launch_plan_artifact.parents:
                raise ValueError("launch plan direction parent must match the content run direction")
        else:
            if incubation_judgment_artifact is None or account_direction_artifact is not None:
                raise ValueError("legacy launch plan lineage requires its exact account strategy")
            if launch_plan.strategy_artifact_id != incubation_judgment_artifact.artifact_id or incubation_judgment_artifact.to_parent_ref() not in launch_plan_artifact.parents:
                raise ValueError("launch plan strategy parent must match the content run strategy")

    record_payload = bundle.record.model_dump(mode="json")
    for source in record_payload["sources"]:
        if source.get("evidence_role") is None:
            source["evidence_role"] = "user_material"

    reading_payload = {
        "record": record_payload,
        "business_semantics": (bundle.business_semantics.model_dump(mode="json") if bundle.business_semantics is not None else None),
        "root_selection": {
            "content_map_version_id": world.content_map_version_id(),
            "source_object": world.source_object,
            "content_entry": world.content_entry,
            "content_root": world.content_root,
            "root_rationale": world.root_rationale,
            "root_candidates": [candidate.model_dump(mode="json") for candidate in world.root_candidates],
            "named_candidates": [candidate.model_dump(mode="json") for candidate in world.named_candidates],
            "unknown_refs": list(world.unknown_refs),
        },
    }
    if launch_plan_artifact is not None:
        reading_payload["launch_plan_context"] = {
            "plan_artifact_id": launch_plan_artifact.artifact_id,
            "plan_content_sha256": launch_plan_artifact.content_sha256,
            "topic_seed_id": launch_topic_seed_id,
        }
    reading = ArtifactEnvelope.seal(
        project=project,
        artifact_type="content_reading",
        version=1,
        payload=reading_payload,
        created_at=created_at,
        source_thread_id=source_thread_id,
        source_run_id=source_run_id,
        logical_account=logical_account,
        parents=(
            *reading_parents,
            *((launch_plan_artifact.to_parent_ref(),) if launch_plan_artifact is not None else ()),
        ),
    )
    content_world = seal_content_world_version(
        project=project,
        content_world=world,
        created_at=created_at,
        source_thread_id=source_thread_id,
        source_run_id=source_run_id,
        logical_account=logical_account,
        parents=(
            (account_direction_artifact.to_parent_ref(),)
            if account_direction_artifact is not None
            else ((incubation_judgment_artifact.to_parent_ref(),) if launch_plan_artifact is not None and incubation_judgment_artifact is not None else ())
        ),
    )

    topic_artifact: ArtifactEnvelope | None = None
    message_plan_artifact: ArtifactEnvelope | None = None
    draft_artifact: ArtifactEnvelope | None = None
    if bundle.topic_brief is not None:
        topic_artifact = ArtifactEnvelope.seal(
            project=project,
            artifact_type="topic_brief",
            version=1,
            payload=bundle.topic_brief.model_dump(mode="json"),
            logical_account=logical_account,
            parents=(
                reading.to_parent_ref(),
                content_world.to_parent_ref(),
                *((launch_plan_artifact.to_parent_ref(),) if launch_plan_artifact is not None else ()),
            ),
            created_at=created_at,
            source_thread_id=source_thread_id,
            source_run_id=source_run_id,
        )

    if delivery is not None:
        if topic_artifact is None:
            raise ValueError("shooting delivery requires a sealed topic brief")
        if delivery.message_plan.record_id != bundle.record.record_id:
            raise ValueError("message plan record does not match the content reading")
        message_plan_artifact = ArtifactEnvelope.seal(
            project=project,
            artifact_type="message_plan",
            version=1,
            payload=delivery.message_plan.model_dump(mode="json"),
            logical_account=logical_account,
            parents=(
                topic_artifact.to_parent_ref(),
                *((incubation_judgment_artifact.to_parent_ref(),) if incubation_judgment_artifact is not None else ()),
                *((account_direction_artifact.to_parent_ref(),) if account_direction_artifact is not None else ()),
            ),
            created_at=created_at,
            source_thread_id=source_thread_id,
            source_run_id=source_run_id,
        )
        draft_artifact = ArtifactEnvelope.seal(
            project=project,
            artifact_type="draft_version",
            version=1,
            payload={
                **delivery.base_draft.model_dump(mode="json"),
                "stage": "base",
            },
            logical_account=logical_account,
            parents=(message_plan_artifact.to_parent_ref(),),
            created_at=created_at,
            source_thread_id=source_thread_id,
            source_run_id=source_run_id,
        )

    return ContentRunArtifactSet(
        content_reading=reading,
        content_world=content_world,
        topic_brief=topic_artifact,
        message_plan=message_plan_artifact,
        draft_version=draft_artifact,
    )


def select_used_topic_evidence_snapshots(
    bundle: ContentIntelligenceBundle,
    snapshots: tuple[EvidenceSnapshot, ...],
) -> tuple[EvidenceSnapshot, ...]:
    """Keep only topic receipts whose public items survived final reading."""

    if not snapshots:
        return ()
    used_uris = {source.uri for source in bundle.record.sources if source.evidence_role == "topic_evidence" and source.uri is not None}
    selected: dict[str, EvidenceSnapshot] = {}
    for snapshot in snapshots:
        if snapshot.evidence_role != "topic_evidence":
            continue
        if not any(item.public_uri in used_uris for item in snapshot.items if item.public_uri is not None):
            continue
        selected[snapshot.model_dump_json()] = snapshot
    return tuple(selected[key] for key in sorted(selected))


__all__ = [
    "ContentRunArtifactSet",
    "seal_content_run_artifacts",
    "select_used_topic_evidence_snapshots",
]
