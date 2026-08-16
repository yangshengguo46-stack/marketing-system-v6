from datetime import UTC, datetime

import pytest
import pytest_asyncio
from pydantic import ValidationError

from deerflow.config.database_config import DatabaseConfig
from deerflow.incubation import (
    ArtifactEnvelope,
    IncubationLedgerRepository,
    MediaKitExecutionReceipt,
    MediaObservationSnapshot,
    MediaSourceReceipt,
    MissingAccountError,
    MissingParentArtifactError,
    PlatformAccountRef,
    ProjectRef,
    VideoMetadataObservation,
    seal_media_observation_snapshot,
    seal_media_source_receipt,
)
from deerflow.incubation.media import EphemeralMediaSource
from deerflow.persistence.engine import close_engine, get_session_factory, init_engine_from_config

NOW = datetime(2026, 8, 16, 12, 0, tzinfo=UTC)


@pytest_asyncio.fixture(autouse=True)
async def _close_persistence_engine():
    yield
    await close_engine()


async def _make_repo(tmp_path) -> IncubationLedgerRepository:
    await init_engine_from_config(DatabaseConfig(backend="sqlite", sqlite_dir=str(tmp_path)))
    session_factory = get_session_factory()
    assert session_factory is not None
    return IncubationLedgerRepository(session_factory)


def _project(*, owner: str = "user-1", project_id: str = "project-1") -> ProjectRef:
    return ProjectRef(owner_user_id=owner, project_id=project_id)


def _account(
    *,
    owner: str = "user-1",
    project_id: str = "project-1",
    account_id: str = "account-1",
) -> PlatformAccountRef:
    return PlatformAccountRef(
        owner_user_id=owner,
        project_id=project_id,
        account_id=account_id,
        platform="douyin",
    )


def _artifact(
    *,
    project: ProjectRef | None = None,
    artifact_type: str = "content_world",
    payload: dict | None = None,
    account: PlatformAccountRef | None = None,
    parents=(),
    evidence_role: str | None = None,
) -> ArtifactEnvelope:
    return ArtifactEnvelope.seal(
        project=project or _project(),
        artifact_type=artifact_type,
        version=1,
        payload=payload or {"content_root": "礼与人与人相处"},
        account=account,
        parents=parents,
        evidence_role=evidence_role,
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-1",
    )


def test_sealed_artifact_is_canonical_and_content_addressed() -> None:
    first = _artifact(payload={"root": "礼", "territories": ["历史", "关系"]})
    reordered = _artifact(payload={"territories": ["历史", "关系"], "root": "礼"})
    changed = _artifact(payload={"root": "礼品", "territories": ["历史", "关系"]})

    assert first.artifact_id == reordered.artifact_id
    assert first.content_sha256 == reordered.content_sha256
    assert first.artifact_id != changed.artifact_id
    assert first.content_sha256 != changed.content_sha256


def test_evidence_role_is_part_of_artifact_identity() -> None:
    topic = _artifact(
        artifact_type="evidence_snapshot",
        payload={"source_ids": ["douyin-video-1"]},
        evidence_role="topic_evidence",
    )
    benchmark = _artifact(
        artifact_type="evidence_snapshot",
        payload={"source_ids": ["douyin-video-1"]},
        evidence_role="benchmark_evidence",
    )

    assert topic.content_sha256 == benchmark.content_sha256
    assert topic.artifact_id != benchmark.artifact_id


def test_artifact_rejects_cross_owner_account_and_parent() -> None:
    other_account = _account(owner="user-2")
    with pytest.raises(ValidationError, match="account owner and project must match"):
        _artifact(account=other_account)

    parent = _artifact(project=_project(owner="user-2"))
    with pytest.raises(ValidationError, match="parent owner and project must match"):
        _artifact(parents=(parent.to_parent_ref(),))


@pytest.mark.parametrize(
    "payload",
    [
        {"access_token": "secret"},
        {"nested": {"cookie": "session=secret"}},
        {"media": [{"local_path": "/private/tmp/video.mp4"}]},
    ],
)
def test_business_artifact_rejects_sensitive_payload_keys(payload: dict) -> None:
    with pytest.raises(ValidationError, match="sensitive field"):
        _artifact(payload=payload)


@pytest.mark.asyncio
async def test_projects_and_accounts_are_owner_scoped(tmp_path) -> None:
    repo = await _make_repo(tmp_path)
    alice = _project(owner="alice", project_id="shared-name")
    bob = _project(owner="bob", project_id="shared-name")

    await repo.create_project(alice, display_name="Alice IP")
    await repo.create_project(bob, display_name="Bob IP")
    await repo.connect_account(
        _account(owner="alice", project_id="shared-name"),
        external_account_id="alice-open-id",
        display_name="Alice Douyin",
    )

    assert await repo.get_project(alice) is not None
    assert await repo.get_project(bob) is not None
    assert await repo.get_project(_project(owner="mallory", project_id="shared-name")) is None
    assert await repo.get_account(_account(owner="alice", project_id="shared-name")) is not None
    assert await repo.get_account(_account(owner="bob", project_id="shared-name")) is None


@pytest.mark.asyncio
async def test_project_listing_is_owner_scoped_and_newest_first(tmp_path) -> None:
    repo = await _make_repo(tmp_path)
    await repo.create_project(_project(owner="alice", project_id="older"), display_name="Older")
    await repo.create_project(_project(owner="bob", project_id="private"), display_name="Private")
    await repo.create_project(_project(owner="alice", project_id="newer"), display_name="Newer")

    projects = await repo.list_projects("alice")

    assert [record.project.project_id for record in projects] == ["newer", "older"]
    assert all(record.project.owner_user_id == "alice" for record in projects)


@pytest.mark.asyncio
async def test_artifact_write_requires_bound_account_and_existing_parent(tmp_path) -> None:
    repo = await _make_repo(tmp_path)
    project = _project()
    await repo.create_project(project, display_name="Golden Gift")

    unbound_account = _account()
    with pytest.raises(MissingAccountError):
        await repo.put_artifact(_artifact(project=project, account=unbound_account))

    missing_parent = _artifact(project=project).to_parent_ref()
    child = _artifact(
        project=project,
        artifact_type="topic_brief",
        payload={"question": "周公之礼的礼是什么？"},
        parents=(missing_parent,),
    )
    with pytest.raises(MissingParentArtifactError):
        await repo.put_artifact(child)


@pytest.mark.asyncio
async def test_artifact_lineage_is_owner_scoped_and_idempotent(tmp_path) -> None:
    repo = await _make_repo(tmp_path)
    project = _project()
    account = _account()
    await repo.create_project(project, display_name="Golden Gift")
    await repo.connect_account(
        account,
        external_account_id="douyin-open-id-1",
        display_name="Golden Gift Douyin",
    )

    parent = _artifact(project=project, account=account)
    first = await repo.put_artifact(parent)
    replay = await repo.put_artifact(parent)
    child = _artifact(
        project=project,
        artifact_type="topic_brief",
        account=account,
        payload={"question": "美国收到自由女神意味着什么？"},
        parents=(parent.to_parent_ref(),),
    )
    stored_child = await repo.put_artifact(child)

    assert first == replay
    assert stored_child.parents == (parent.to_parent_ref(),)
    assert await repo.get_artifact(parent.artifact_id, owner_user_id="user-1") == parent
    assert await repo.get_artifact(parent.artifact_id, owner_user_id="user-2") is None


@pytest.mark.asyncio
async def test_artifact_queries_do_not_mix_evidence_roles(tmp_path) -> None:
    repo = await _make_repo(tmp_path)
    project = _project()
    await repo.create_project(project, display_name="Golden Gift")
    topic = _artifact(
        project=project,
        artifact_type="evidence_snapshot",
        payload={"source_ids": ["video-1"]},
        evidence_role="topic_evidence",
    )
    benchmark = _artifact(
        project=project,
        artifact_type="evidence_snapshot",
        payload={"source_ids": ["account-post-1", "account-post-2"]},
        evidence_role="benchmark_evidence",
    )
    await repo.put_artifact(topic)
    await repo.put_artifact(benchmark)

    topic_rows = await repo.list_artifacts(project, evidence_role="topic_evidence")
    benchmark_rows = await repo.list_artifacts(project, evidence_role="benchmark_evidence")

    assert topic_rows == [topic]
    assert benchmark_rows == [benchmark]


@pytest.mark.asyncio
async def test_mutated_payload_cannot_enter_ledger_with_a_stale_hash(tmp_path) -> None:
    repo = await _make_repo(tmp_path)
    project = _project()
    await repo.create_project(project, display_name="Golden Gift")
    artifact = _artifact(project=project)
    artifact.payload["content_root"] = "tampered after sealing"

    with pytest.raises(ValidationError, match="content_sha256"):
        await repo.put_artifact(artifact)

    assert await repo.get_artifact(artifact.artifact_id, owner_user_id="user-1") is None


@pytest.mark.asyncio
async def test_media_observation_persists_with_source_lineage_and_role(tmp_path) -> None:
    repo = await _make_repo(tmp_path)
    project = _project()
    await repo.create_project(project, display_name="Benchmark media")
    local_video = tmp_path / "sample.mp4"
    local_video.write_bytes(b"sample-video")
    source = EphemeralMediaSource.local_file(
        source_ref="douyin:video:sample",
        locator=local_video,
        rights_ref="rights:public-benchmark",
        resolver="douyin-media:v1",
    )
    source_artifact = seal_media_source_receipt(
        project=project,
        receipt=MediaSourceReceipt.from_ephemeral(source, resolved_at=NOW),
        evidence_role="benchmark_evidence",
        source_thread_id="thread-1",
        source_run_id="run-1",
    )
    observation = MediaObservationSnapshot(
        source_ref=source.source_ref,
        observation_kind="video_metadata",
        observed_at=NOW,
        observation=VideoMetadataObservation.from_mediakit_output(
            {
                "format_meta": {
                    "container": "mp4",
                    "duration": 1,
                    "size": len(b"sample-video"),
                },
                "video_stream_meta": {
                    "codec": "h264",
                    "duration": 1,
                    "width": 320,
                    "height": 240,
                    "fps": 25,
                },
            }
        ),
        execution=MediaKitExecutionReceipt(
            capability_domain="video",
            capability_tool="probe-video-metadata",
            cli_version="0.2.0",
            schema_sha256="a" * 64,
            execution_mode="local",
            request_sha256="b" * 64,
            source_content_sha256="c" * 64,
            output_sha256="d" * 64,
            completed_at=NOW,
            cloud_processing_approved=False,
        ),
    )
    observation_artifact = seal_media_observation_snapshot(
        project=project,
        snapshot=observation,
        source_receipt_artifact=source_artifact,
        source_thread_id="thread-1",
        source_run_id="run-1",
    )

    await repo.put_artifact(source_artifact)
    stored = await repo.put_artifact(observation_artifact)

    assert stored.parents == (source_artifact.to_parent_ref(),)
    assert stored.evidence_role == "benchmark_evidence"
    assert await repo.get_artifact(stored.artifact_id, owner_user_id="user-1") == stored
