from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from deerflow.incubation.contracts import (
    ArtifactEnvelope,
    ArtifactParentRef,
    PlatformAccountRef,
    ProjectRef,
)

if TYPE_CHECKING:
    from deerflow.content_intelligence.contracts import ContentWorldView


def seal_content_world_version(
    *,
    project: ProjectRef,
    content_world: ContentWorldView,
    created_at: datetime,
    source_thread_id: str,
    source_run_id: str,
    account: PlatformAccountRef | None = None,
    parents: tuple[ArtifactParentRef, ...] = (),
) -> ArtifactEnvelope:
    """Seal only the durable account-level editorial map.

    Per-run record IDs, commercial source objects, root candidates, named
    research candidates, and unknown references remain evidence or run
    projections. They must not create a new account-map version by accident.
    """

    payload = {
        "content_map_version_id": content_world.content_map_version_id(),
        "content_root": content_world.content_root,
        "audience_territory": content_world.audience_territory.text if content_world.audience_territory else None,
        "editorial_promise": content_world.editorial_promise,
        "recurring_lens": content_world.recurring_lens,
        "drift_boundaries": list(content_world.drift_boundaries),
        "dimensions": [dimension.model_dump(mode="json") for dimension in content_world.dimensions],
    }
    return ArtifactEnvelope.seal(
        project=project,
        artifact_type="content_world",
        version=1,
        payload=payload,
        account=account,
        parents=parents,
        created_at=created_at,
        source_thread_id=source_thread_id,
        source_run_id=source_run_id,
    )
