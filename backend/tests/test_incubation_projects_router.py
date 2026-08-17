from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import UUID

from _router_auth_helpers import make_authed_test_app
from fastapi.testclient import TestClient
from langgraph.store.memory import InMemoryStore

from app.gateway.auth.models import User
from app.gateway.routers import incubation_projects
from deerflow.community.mediakit import MediaKitCloudApprovalRequest
from deerflow.incubation import (
    ApprovalGrant,
    ArtifactEnvelope,
    ArtifactParentRef,
    MediaKitExecutionReceipt,
    MediaObservationSnapshot,
    MediaSourceReceipt,
    ProjectRecord,
    ProjectRef,
    VideoMetadataObservation,
    seal_media_observation_snapshot,
    seal_media_source_receipt,
)
from deerflow.incubation.media import VideoFormatMetadata, VideoStreamMetadata
from deerflow.persistence.thread_meta.memory import MemoryThreadMetaStore

NOW = datetime(2026, 8, 17, 12, 0, tzinfo=UTC)
USER_ID = "11111111-1111-4111-8111-111111111111"
OTHER_USER_ID = "22222222-2222-4222-8222-222222222222"


def _user() -> User:
    return User(
        email="incubation@example.com",
        password_hash="x",
        system_role="user",
        id=UUID(USER_ID),
    )


class _FakeLedger:
    def __init__(self) -> None:
        self.projects: dict[tuple[str, str], ProjectRecord] = {}
        self.artifacts: dict[str, ArtifactEnvelope] = {}
        self.grants: dict[str, ApprovalGrant] = {}

    async def create_project(self, project: ProjectRef, *, display_name: str) -> ProjectRecord:
        record = ProjectRecord(
            project=project,
            display_name=display_name,
            created_at=NOW,
            updated_at=NOW,
        )
        self.projects[(project.owner_user_id, project.project_id)] = record
        return record

    async def get_project(self, project: ProjectRef) -> ProjectRecord | None:
        return self.projects.get((project.owner_user_id, project.project_id))

    async def list_projects(self, owner_user_id: str, *, limit: int = 100, offset: int = 0) -> list[ProjectRecord]:
        rows = [record for (owner, _project_id), record in self.projects.items() if owner == owner_user_id]
        return rows[offset : offset + limit]

    async def get_artifact(self, artifact_id: str, *, owner_user_id: str) -> ArtifactEnvelope | None:
        artifact = self.artifacts.get(artifact_id)
        if artifact is None or artifact.project.owner_user_id != owner_user_id:
            return None
        return artifact

    async def get_approval_grant(self, grant_id: str, *, owner_user_id: str) -> ApprovalGrant | None:
        grant = self.grants.get(grant_id)
        if grant is None or grant.project.owner_user_id != owner_user_id:
            return None
        return grant

    async def put_artifact(self, artifact: ArtifactEnvelope) -> ArtifactEnvelope:
        existing = self.artifacts.get(artifact.artifact_id)
        if existing is not None:
            return existing
        self.artifacts[artifact.artifact_id] = artifact
        return artifact

    async def issue_approval_pair(
        self,
        cloud: ApprovalGrant,
        fee: ApprovalGrant,
    ) -> tuple[ApprovalGrant, ApprovalGrant]:
        self.grants[cloud.grant_id] = cloud
        self.grants[fee.grant_id] = fee
        return cloud, fee


def _build_app() -> tuple[object, _FakeLedger, MemoryThreadMetaStore]:
    app = make_authed_test_app(user_factory=_user)
    ledger = _FakeLedger()
    thread_store = MemoryThreadMetaStore(InMemoryStore())
    app.state.incubation_ledger_repo = ledger
    app.state.thread_store = thread_store
    app.include_router(incubation_projects.router)
    return app, ledger, thread_store


def test_create_list_and_get_projects_do_not_expose_owner_identity() -> None:
    app, _ledger, _thread_store = _build_app()

    with TestClient(app) as client:
        created = client.post(
            "/api/incubation/projects",
            json={"project_id": "golden-gift", "display_name": "黄金礼品账号"},
        )
        listed = client.get("/api/incubation/projects")
        fetched = client.get("/api/incubation/projects/golden-gift")

    assert created.status_code == 201, created.text
    assert created.json()["project_id"] == "golden-gift"
    assert "owner_user_id" not in created.text
    assert listed.status_code == 200
    assert [row["project_id"] for row in listed.json()] == ["golden-gift"]
    assert fetched.status_code == 200
    assert fetched.json()["display_name"] == "黄金礼品账号"


def test_thread_binding_requires_owned_project_and_rehydrates_binding() -> None:
    app, ledger, thread_store = _build_app()

    async def seed() -> None:
        await thread_store.create("thread-1", user_id=USER_ID)
        await ledger.create_project(
            ProjectRef(owner_user_id=USER_ID, project_id="golden-gift"),
            display_name="黄金礼品账号",
        )
        await ledger.create_project(
            ProjectRef(owner_user_id=OTHER_USER_ID, project_id="other-user-project"),
            display_name="其他用户项目",
        )

    asyncio.run(seed())

    with TestClient(app) as client:
        bound = client.put(
            "/api/incubation/threads/thread-1/project",
            json={"project_id": "golden-gift"},
        )
        current = client.get("/api/incubation/threads/thread-1/project")
        missing = client.put(
            "/api/incubation/threads/thread-1/project",
            json={"project_id": "other-user-project"},
        )

    assert bound.status_code == 200, bound.text
    assert bound.json()["project"]["project_id"] == "golden-gift"
    assert current.status_code == 200
    assert current.json()["project"]["project_id"] == "golden-gift"
    assert missing.status_code == 404


def test_thread_binding_rejects_unknown_thread() -> None:
    app, ledger, _thread_store = _build_app()
    asyncio.run(
        ledger.create_project(
            ProjectRef(owner_user_id=USER_ID, project_id="golden-gift"),
            display_name="黄金礼品账号",
        )
    )

    with TestClient(app) as client:
        response = client.put(
            "/api/incubation/threads/missing-thread/project",
            json={"project_id": "golden-gift"},
        )

    assert response.status_code == 404


def _approval_request_artifact(
    *,
    owner: str = USER_ID,
    project_id: str = "media-project",
    quoted_at: datetime = NOW,
    valid_until: datetime = datetime(2099, 1, 1, tzinfo=UTC),
    operation_sha256: str = "a" * 64,
    parent: ArtifactParentRef | None = None,
) -> ArtifactEnvelope:
    request = MediaKitCloudApprovalRequest(
        operation_sha256=operation_sha256,
        capability_domain="video",
        capability_tool="enhance-video",
        capability_schema_sha256="b" * 64,
        capability_arguments_sha256="c" * 64,
        pricing_evidence_sha256="d" * 64,
        fee_quote_sha256="e" * 64,
        source_content_sha256="f" * 64,
        source_duration_milliseconds=1_000,
        output_resolution_tier="720p",
        output_fps=25,
        tool_version="standard",
        currency="CNY",
        amount_micros_per_minute=750_000,
        estimated_amount_micros=12_500,
        maximum_amount_micros=20_000,
        provider_hard_cap_supported=False,
        quoted_at=quoted_at,
        valid_until=valid_until,
    )
    return ArtifactEnvelope.seal(
        project=ProjectRef(owner_user_id=owner, project_id=project_id),
        artifact_type="mediakit_cloud_approval_request",
        version=1,
        payload=request.model_dump(mode="json"),
        parents=(
            parent
            or ArtifactParentRef(
                owner_user_id=owner,
                project_id=project_id,
                artifact_id="media-observation-1",
                artifact_type="media_observation",
                content_sha256="1" * 64,
            ),
        ),
        created_at=quoted_at,
        source_thread_id="thread-1",
        source_run_id="run-1",
    )


def _media_artifacts() -> tuple[ArtifactEnvelope, ArtifactEnvelope]:
    project = ProjectRef(owner_user_id=USER_ID, project_id="media-project")
    source = seal_media_source_receipt(
        project=project,
        receipt=MediaSourceReceipt(
            source_ref="media-source-1",
            media_kind="video",
            transport="local_file",
            resolver="gateway-upload",
            rights_ref="rights-1",
            locator_sha256="1" * 64,
            resolved_at=NOW,
        ),
        evidence_role="user_material",
        source_thread_id="thread-1",
        source_run_id="run-1",
    )
    snapshot = MediaObservationSnapshot(
        source_ref="media-source-1",
        observation_kind="video_metadata",
        observed_at=NOW,
        observation=VideoMetadataObservation(
            format_meta=VideoFormatMetadata(container="mp4", duration=1.0, size=2_320),
            video_stream_meta=VideoStreamMetadata(
                codec="h264",
                duration=1.0,
                width=320,
                height=240,
                fps=25,
            ),
        ),
        execution=MediaKitExecutionReceipt(
            capability_domain="video",
            capability_tool="probe-video-metadata",
            cli_version="0.2.0",
            schema_sha256="2" * 64,
            execution_mode="local",
            request_sha256="3" * 64,
            source_content_sha256="f" * 64,
            output_sha256="4" * 64,
            completed_at=NOW,
            cloud_processing_approved=False,
        ),
    )
    observation = seal_media_observation_snapshot(
        project=project,
        snapshot=snapshot,
        source_receipt_artifact=source,
        source_thread_id="thread-1",
        source_run_id="run-2",
    )
    return source, observation


class _FakeQuoteService:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def prepare_approval_request(self, **kwargs) -> ArtifactEnvelope:
        self.calls.append(kwargs)
        observation = kwargs["media_observation_artifact"]
        assert isinstance(observation, ArtifactEnvelope)
        return _approval_request_artifact(
            quoted_at=kwargs["quoted_at"],
            valid_until=datetime(2099, 1, 1, tzinfo=UTC),
            parent=observation.to_parent_ref(),
        )


def test_mediakit_quote_api_uses_owned_observation_and_persists_reviewable_request() -> None:
    app, ledger, _thread_store = _build_app()
    project = ProjectRef(owner_user_id=USER_ID, project_id="media-project")
    asyncio.run(ledger.create_project(project, display_name="Media project"))
    source, observation = _media_artifacts()
    ledger.artifacts[source.artifact_id] = source
    ledger.artifacts[observation.artifact_id] = observation
    quote_service = _FakeQuoteService()
    app.state.mediakit_quote_service = quote_service

    with TestClient(app) as client:
        created = client.post(
            "/api/incubation/projects/media-project/media/mediakit/enhance-video/quotes",
            json={
                "media_observation_artifact_id": observation.artifact_id,
                "tool_version": "standard",
                "scene": "common",
                "resolution": "720p",
                "fps": 25,
                "bitrate_level": "medium",
                "maximum_amount_micros": 20_000,
            },
        )
        invented_price = client.post(
            "/api/incubation/projects/media-project/media/mediakit/enhance-video/quotes",
            json={
                "media_observation_artifact_id": observation.artifact_id,
                "tool_version": "standard",
                "scene": "common",
                "resolution": "720p",
                "fps": 25,
                "bitrate_level": "medium",
                "maximum_amount_micros": 20_000,
                "amount_micros_per_minute": 1,
            },
        )

    assert created.status_code == 201, created.text
    assert created.json()["capability_tool"] == "enhance-video"
    assert created.json()["estimated_amount_micros"] == 12_500
    quote_artifact_id = created.json()["quote_artifact_id"]
    assert ledger.artifacts[quote_artifact_id].artifact_type == "mediakit_cloud_approval_request"
    assert quote_service.calls[0]["source_receipt_artifact"] == source
    assert quote_service.calls[0]["media_observation_artifact"] == observation
    assert invented_price.status_code == 422
    assert not hasattr(app.state, "mediakit_cloud_driver")


def test_mediakit_quote_api_fails_closed_without_service_or_valid_lineage() -> None:
    app, ledger, _thread_store = _build_app()
    project = ProjectRef(owner_user_id=USER_ID, project_id="media-project")
    asyncio.run(ledger.create_project(project, display_name="Media project"))
    source, observation = _media_artifacts()
    ledger.artifacts[source.artifact_id] = source
    ledger.artifacts[observation.artifact_id] = observation
    body = {
        "media_observation_artifact_id": observation.artifact_id,
        "tool_version": "standard",
        "scene": "common",
        "resolution": "720p",
        "fps": 25,
        "bitrate_level": "medium",
        "maximum_amount_micros": 20_000,
    }

    with TestClient(app) as client:
        unavailable = client.post(
            "/api/incubation/projects/media-project/media/mediakit/enhance-video/quotes",
            json=body,
        )
        missing = client.post(
            "/api/incubation/projects/media-project/media/mediakit/enhance-video/quotes",
            json={**body, "media_observation_artifact_id": "artifact_" + "0" * 64},
        )

    assert unavailable.status_code == 503
    assert missing.status_code == 404


def test_exact_mediakit_approval_api_issues_two_grants_without_starting_a_task() -> None:
    app, ledger, _thread_store = _build_app()
    project = ProjectRef(owner_user_id=USER_ID, project_id="media-project")
    asyncio.run(ledger.create_project(project, display_name="Media project"))
    quote_artifact = _approval_request_artifact()
    ledger.artifacts[quote_artifact.artifact_id] = quote_artifact
    body = {
        "quote_artifact_id": quote_artifact.artifact_id,
        "fee_quote_sha256": "e" * 64,
        "currency": "CNY",
        "maximum_amount_micros": 20_000,
        "confirm_cloud_processing": True,
        "confirm_fee_authorization": True,
        "acknowledge_no_provider_hard_cap": True,
    }

    with TestClient(app) as client:
        review = client.get(f"/api/incubation/projects/media-project/approvals/mediakit-cloud/{quote_artifact.artifact_id}")
        created = client.post(
            "/api/incubation/projects/media-project/approvals/mediakit-cloud",
            json=body,
        )
        replayed = client.post(
            "/api/incubation/projects/media-project/approvals/mediakit-cloud",
            json=body,
        )

    assert review.status_code == 200, review.text
    assert review.json()["capability_tool"] == "enhance-video"
    assert review.json()["pricing_evidence_sha256"] == "d" * 64
    assert review.json()["output_resolution_tier"] == "720p"
    assert review.json()["estimated_amount_micros"] == 12_500
    assert review.json()["requires_no_provider_hard_cap_acknowledgement"] is True
    assert "source_ref" not in review.text
    assert "rights_ref" not in review.text
    assert "/Users/" not in review.text
    assert created.status_code == 201, created.text
    assert created.json()["operation_sha256"] == "a" * 64
    assert created.json()["estimated_amount_micros"] == 12_500
    assert created.json()["provider_hard_cap_supported"] is False
    assert replayed.status_code == 200, replayed.text
    assert replayed.json()["replayed"] is True
    assert {grant.kind for grant in ledger.grants.values()} == {
        "cloud_processing",
        "fee_authorization",
    }
    assert not hasattr(app.state, "mediakit_cloud_driver")


def test_two_quote_artifacts_for_one_operation_replay_the_same_approval_pair() -> None:
    app, ledger, _thread_store = _build_app()
    project = ProjectRef(owner_user_id=USER_ID, project_id="media-project")
    asyncio.run(ledger.create_project(project, display_name="Media project"))
    first = _approval_request_artifact(quoted_at=NOW)
    second = _approval_request_artifact(quoted_at=NOW.replace(second=1))
    assert first.artifact_id != second.artifact_id
    ledger.artifacts[first.artifact_id] = first
    ledger.artifacts[second.artifact_id] = second

    def body(artifact: ArtifactEnvelope) -> dict[str, object]:
        return {
            "quote_artifact_id": artifact.artifact_id,
            "fee_quote_sha256": "e" * 64,
            "currency": "CNY",
            "maximum_amount_micros": 20_000,
            "confirm_cloud_processing": True,
            "confirm_fee_authorization": True,
            "acknowledge_no_provider_hard_cap": True,
        }

    with TestClient(app) as client:
        created = client.post(
            "/api/incubation/projects/media-project/approvals/mediakit-cloud",
            json=body(first),
        )
        replayed = client.post(
            "/api/incubation/projects/media-project/approvals/mediakit-cloud",
            json=body(second),
        )

    assert created.status_code == 201, created.text
    assert replayed.status_code == 200, replayed.text
    assert replayed.json()["replayed"] is True
    assert replayed.json()["cloud_processing_grant_id"] == created.json()["cloud_processing_grant_id"]
    assert replayed.json()["fee_authorization_grant_id"] == created.json()["fee_authorization_grant_id"]
    assert len(ledger.grants) == 2


def test_mediakit_approval_api_rejects_stale_or_cross_project_confirmation() -> None:
    app, ledger, _thread_store = _build_app()
    project = ProjectRef(owner_user_id=USER_ID, project_id="media-project")
    asyncio.run(ledger.create_project(project, display_name="Media project"))
    quote_artifact = _approval_request_artifact()
    ledger.artifacts[quote_artifact.artifact_id] = quote_artifact
    stale_artifact = _approval_request_artifact(
        quoted_at=datetime(2025, 1, 1, tzinfo=UTC),
        valid_until=datetime(2025, 1, 2, tzinfo=UTC),
    )
    ledger.artifacts[stale_artifact.artifact_id] = stale_artifact
    base = {
        "quote_artifact_id": quote_artifact.artifact_id,
        "fee_quote_sha256": "e" * 64,
        "currency": "CNY",
        "maximum_amount_micros": 20_000,
        "confirm_cloud_processing": True,
        "confirm_fee_authorization": True,
        "acknowledge_no_provider_hard_cap": True,
    }

    with TestClient(app) as client:
        wrong_amount = client.post(
            "/api/incubation/projects/media-project/approvals/mediakit-cloud",
            json={**base, "maximum_amount_micros": 20_001},
        )
        wrong_project = client.post(
            "/api/incubation/projects/another-project/approvals/mediakit-cloud",
            json=base,
        )
        missing_ack = client.post(
            "/api/incubation/projects/media-project/approvals/mediakit-cloud",
            json={**base, "acknowledge_no_provider_hard_cap": False},
        )
        stale = client.post(
            "/api/incubation/projects/media-project/approvals/mediakit-cloud",
            json={**base, "quote_artifact_id": stale_artifact.artifact_id},
        )

    assert wrong_amount.status_code == 409
    assert wrong_project.status_code == 404
    assert missing_ack.status_code == 422
    assert stale.status_code == 409
    assert ledger.grants == {}
