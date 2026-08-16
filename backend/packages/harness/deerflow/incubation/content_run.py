from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import model_validator

from deerflow.incubation.content_world import seal_content_world_version
from deerflow.incubation.contracts import (
    ArtifactEnvelope,
    ArtifactParentRef,
    IncubationContract,
    ProjectRef,
)
from deerflow.incubation.evidence import EvidenceSnapshot

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
    reading_parents: tuple[ArtifactParentRef, ...] = (),
) -> ContentRunArtifactSet:
    """Seal one content-intelligence run without changing its judgments."""

    world = bundle.content_world
    if world is None or world.content_root is None:
        raise ValueError("content run persistence requires a frozen content world")

    record_payload = bundle.record.model_dump(mode="json")
    for source in record_payload["sources"]:
        if source.get("evidence_role") is None:
            source["evidence_role"] = "user_material"

    reading = ArtifactEnvelope.seal(
        project=project,
        artifact_type="content_reading",
        version=1,
        payload={
            "record": record_payload,
            "business_semantics": (bundle.business_semantics.model_dump(mode="json") if bundle.business_semantics is not None else None),
            "root_selection": {
                "content_map_version_id": world.content_map_version_id(),
                "source_object": world.source_object,
                "content_root": world.content_root,
                "root_rationale": world.root_rationale,
                "root_candidates": [candidate.model_dump(mode="json") for candidate in world.root_candidates],
                "named_candidates": [candidate.model_dump(mode="json") for candidate in world.named_candidates],
                "unknown_refs": list(world.unknown_refs),
            },
        },
        created_at=created_at,
        source_thread_id=source_thread_id,
        source_run_id=source_run_id,
        parents=reading_parents,
    )
    content_world = seal_content_world_version(
        project=project,
        content_world=world,
        created_at=created_at,
        source_thread_id=source_thread_id,
        source_run_id=source_run_id,
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
            parents=(
                reading.to_parent_ref(),
                content_world.to_parent_ref(),
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
            parents=(topic_artifact.to_parent_ref(),),
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
