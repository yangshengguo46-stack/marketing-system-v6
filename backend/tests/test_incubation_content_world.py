from datetime import UTC, datetime

from deerflow.content_intelligence import ContentWorldView, NamedCandidate
from deerflow.incubation import ProjectRef, seal_content_world_version

NOW = datetime(2026, 8, 16, 13, 0, tzinfo=UTC)


def _world(
    *,
    record_id: str,
    named_candidate: str,
    content_root: str = "礼与人与人相处",
    content_entry: str = "送礼",
) -> ContentWorldView:
    return ContentWorldView(
        record_id=record_id,
        source_object="黄金礼品",
        content_entry=content_entry,
        content_root=content_root,
        root_rationale="从商品用途进入长期的人际关系世界。",
        editorial_promise="借礼看人与人怎样相处。",
        recurring_lens="从人物、事件、时间与空间理解礼。",
        drift_boundaries=("不退回黄金产品目录",),
        named_candidates=(
            NamedCandidate(
                name=named_candidate,
                connection="可作为一次公开资料取证入口。",
                kind="hypothesis",
                verification_query=f"{named_candidate} 礼 历史",
            ),
        ),
    )


def test_content_world_artifact_tracks_only_the_durable_editorial_map() -> None:
    project = ProjectRef(owner_user_id="user-1", project_id="project-1")
    first = seal_content_world_version(
        project=project,
        content_world=_world(record_id="record-1", named_candidate="自由女神像"),
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-1",
    )
    later_research = seal_content_world_version(
        project=project,
        content_world=_world(record_id="record-2", named_candidate="埃文凯尔", content_entry="礼节"),
        created_at=NOW,
        source_thread_id="thread-2",
        source_run_id="run-2",
    )

    assert first.artifact_id == later_research.artifact_id
    assert first.payload == later_research.payload
    assert "record_id" not in first.payload
    assert "named_candidates" not in first.payload
    assert "source_object" not in first.payload
    assert "content_entry" not in first.payload


def test_content_world_artifact_changes_when_the_frozen_map_changes() -> None:
    project = ProjectRef(owner_user_id="user-1", project_id="project-1")
    people = seal_content_world_version(
        project=project,
        content_world=_world(record_id="record-1", named_candidate="周礼"),
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-1",
    )
    product_catalog = seal_content_world_version(
        project=project,
        content_world=_world(
            record_id="record-1",
            named_candidate="水贝黄金",
            content_root="黄金产品知识",
        ),
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-1",
    )

    assert people.artifact_id != product_catalog.artifact_id
    assert people.content_sha256 != product_catalog.content_sha256
