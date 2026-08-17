from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio

from app.mcp_tasks.service import McpTaskService
from deerflow.community.mediakit import (
    CommandResult,
    EphemeralMediaSource,
    MediaKitCapabilityRouter,
    MediaKitCloudApprovalAuthorizer,
    MediaKitCloudAuthorizationContext,
    MediaKitCloudDriver,
    MediaKitCloudMaterializationContext,
    MediaKitCloudMaterializedOutput,
    MediaKitCommandError,
    mediakit_cloud_operation_sha256,
)
from deerflow.config.database_config import DatabaseConfig
from deerflow.incubation import ApprovalGrant, IncubationLedgerRepository, ProjectRef
from deerflow.mcp.tasks import McpTaskDriverRegistry, TaskReference, TaskStatus, TaskSubmitRequest
from deerflow.persistence.engine import close_engine, get_session_factory, init_engine_from_config
from deerflow.persistence.mcp_tasks import McpTaskRepository


@pytest_asyncio.fixture(autouse=True)
async def _close_persistence_engine():
    yield
    await close_engine()


def _capability_schema() -> dict:
    return {
        "name": "asr_subtitles",
        "description": "ASR",
        "input_schema": {
            "type": "object",
            "properties": {
                "video_url": {"type": "string"},
                "enable_confidence": {"type": "boolean"},
                "client_token": {"type": "string"},
            },
            "additionalProperties": False,
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string"},
                "request_id": {"type": "string"},
            },
        },
    }


def _query_schema() -> dict:
    return {
        "name": "query_task",
        "description": "query",
        "input_schema": {
            "type": "object",
            "properties": {"task_id": {"type": "string"}},
            "required": ["task_id"],
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string"},
                "request_id": {"type": "string"},
                "status": {"type": "string"},
                "video_url": {"type": "string"},
            },
        },
    }


class FakeMediaKitRunner:
    def __init__(self) -> None:
        self.commands: list[tuple[str, ...]] = []
        self.query_schema_payload = _query_schema()
        self.submission_payload: dict = {
            "task_id": "remote-task-1",
            "request_id": "provider-request-secret",
        }
        self.query_results: list[tuple[int, dict]] = []

    async def __call__(self, command: tuple[str, ...], timeout_seconds: float) -> CommandResult:
        del timeout_seconds
        self.commands.append(command)
        if command == ("mediakit-cli", "version"):
            return CommandResult(returncode=0, stdout="mediakit-cli 0.2.0\n", stderr="")
        if command == ("mediakit-cli", "video", "asr-subtitles", "--schema"):
            return CommandResult(returncode=0, stdout=json.dumps(_capability_schema()), stderr="")
        if command == ("mediakit-cli", "shared", "query-task", "--schema"):
            return CommandResult(
                returncode=0,
                stdout=json.dumps(self.query_schema_payload),
                stderr="",
            )
        if command[:4] == ("mediakit-cli", "--cloud", "video", "asr-subtitles"):
            return CommandResult(returncode=0, stdout=json.dumps(self.submission_payload), stderr="")
        if command[:3] == ("mediakit-cli", "shared", "query-task"):
            returncode, payload = self.query_results.pop(0)
            return CommandResult(
                returncode=returncode,
                stdout=json.dumps(payload),
                stderr="Authorization: Bearer provider-secret",
            )
        raise AssertionError(f"unexpected MediaKit command: {command}")


def _source() -> EphemeralMediaSource:
    return EphemeralMediaSource.direct_http(
        source_ref="media-source-1",
        locator="https://cdn.example.com/input.mp4?signature=temporary-secret",
        rights_ref="rights-1",
        resolver="authorized-upload:v1",
        content_type="video/mp4",
        expires_at=datetime.now(UTC) + timedelta(minutes=10),
    )


async def _resolve_source(
    user_id: str,
    source_ref: str,
    rights_ref: str,
) -> EphemeralMediaSource:
    assert (user_id, source_ref, rights_ref) == ("user-1", "media-source-1", "rights-1")
    return _source()


async def _materialize(
    context: MediaKitCloudMaterializationContext,
) -> MediaKitCloudMaterializedOutput:
    assert context.provider_output["video_url"].startswith("https://provider.example/")
    return MediaKitCloudMaterializedOutput(
        artifact_ref=f"artifact://media/{context.local_task_id}",
        content_sha256="a" * 64,
        content_type="video/mp4",
        size_bytes=42,
    )


def _request(schema_sha256: str, *, local_task_id: str = "task-local-1") -> TaskSubmitRequest:
    return TaskSubmitRequest(
        user_id="user-1",
        thread_id="thread-1",
        run_id="run-1",
        tool_call_id="call-1",
        server_name="mediakit",
        task_name="ASR",
        arguments={
            "project_id": "project-1",
            "source_ref": "media-source-1",
            "rights_ref": "rights-1",
            "source_content_sha256": "b" * 64,
            "capability_domain": "video",
            "capability_tool": "asr-subtitles",
            "capability_arguments": {"enable_confidence": True},
            "expected_schema_sha256": schema_sha256,
            "cloud_processing_approval_ref": "approval-cloud-1",
            "fee_authorization_ref": "approval-fee-1",
            "currency": "CNY",
            "maximum_amount_micros": 1_000_000,
        },
        local_task_id=local_task_id,
    )


async def _driver(
    runner: FakeMediaKitRunner,
    *,
    events: list[str] | None = None,
) -> tuple[MediaKitCloudDriver, str]:
    router = MediaKitCapabilityRouter(runner=runner)
    capability = await router.discover_capability("video", "asr-subtitles")

    async def authorize(context: MediaKitCloudAuthorizationContext) -> None:
        assert context.project_id == "project-1"
        assert context.local_task_id.startswith("task-")
        assert context.source_content_sha256 == "b" * 64
        assert len(context.operation_sha256) == 64
        assert context.cloud_processing_approval_ref == "approval-cloud-1"
        assert context.fee_authorization_ref == "approval-fee-1"
        assert context.currency == "CNY"
        assert context.maximum_amount_micros == 1_000_000
        if events is not None:
            events.append("authorize")

    async def resolve_source(user_id: str, source_ref: str, rights_ref: str) -> EphemeralMediaSource:
        assert (user_id, source_ref, rights_ref) == ("user-1", "media-source-1", "rights-1")
        if events is not None:
            events.append("resolve")
        return _source()

    return (
        MediaKitCloudDriver(
            router=router,
            authorize=authorize,
            resolve_source=resolve_source,
            materialize_result=_materialize,
            poll_after_seconds=1,
        ),
        capability.schema_sha256,
    )


@pytest.mark.asyncio
async def test_cloud_submit_authorizes_then_resolves_source_and_uses_local_id_as_client_token() -> None:
    runner = FakeMediaKitRunner()
    events: list[str] = []
    driver, schema_sha256 = await _driver(runner, events=events)
    runner.commands.clear()

    submission = await driver.submit(_request(schema_sha256))

    assert events == ["authorize", "resolve"]
    assert submission.remote_task_id == "remote-task-1"
    assert submission.snapshot.status is TaskStatus.SUBMITTED
    cloud_command = next(command for command in runner.commands if "--cloud" in command)
    assert cloud_command[-2:] == ("--client-token", "task-local-1")
    assert "signature=temporary-secret" in " ".join(cloud_command)
    serialized = json.dumps(submission.driver_data, sort_keys=True)
    assert "signature=temporary-secret" not in serialized
    assert "provider-request-secret" not in serialized
    assert submission.driver_data["request_id_sha256"]
    assert submission.driver_data["client_token_sha256"]


@pytest.mark.asyncio
async def test_schema_drift_stops_before_source_resolution_or_cloud_submission() -> None:
    runner = FakeMediaKitRunner()
    resolved = False

    async def authorize(context: MediaKitCloudAuthorizationContext) -> None:
        del context

    async def resolve_source(user_id: str, source_ref: str, rights_ref: str) -> EphemeralMediaSource:
        nonlocal resolved
        del user_id, source_ref, rights_ref
        resolved = True
        return _source()

    driver = MediaKitCloudDriver(
        router=MediaKitCapabilityRouter(runner=runner),
        authorize=authorize,
        resolve_source=resolve_source,
        materialize_result=_materialize,
    )

    with pytest.raises(MediaKitCommandError, match="schema changed"):
        await driver.submit(_request("f" * 64))

    assert resolved is False
    assert not any("--cloud" in command for command in runner.commands)


@pytest.mark.asyncio
async def test_authorization_failure_allows_only_local_schema_discovery() -> None:
    runner = FakeMediaKitRunner()
    router = MediaKitCapabilityRouter(runner=runner)
    capability = await router.discover_capability("video", "asr-subtitles")
    runner.commands.clear()
    resolved = False

    async def reject(context: MediaKitCloudAuthorizationContext) -> None:
        del context
        raise PermissionError("approval expired")

    async def resolve_source(user_id: str, source_ref: str, rights_ref: str) -> EphemeralMediaSource:
        nonlocal resolved
        del user_id, source_ref, rights_ref
        resolved = True
        return _source()

    driver = MediaKitCloudDriver(
        router=router,
        authorize=reject,
        resolve_source=resolve_source,
        materialize_result=_materialize,
    )

    with pytest.raises(PermissionError, match="MediaKit cloud authorization failed") as caught:
        await driver.submit(_request(capability.schema_sha256))

    assert "approval expired" not in str(caught.value)
    assert runner.commands
    assert not any("--cloud" in command for command in runner.commands)
    assert resolved is False


def test_operation_digest_binds_source_schema_arguments_and_fee_limit() -> None:
    baseline = _request("f" * 64).arguments
    baseline_digest = mediakit_cloud_operation_sha256(baseline)

    for field, value in (
        ("source_content_sha256", "c" * 64),
        ("expected_schema_sha256", "e" * 64),
        ("maximum_amount_micros", 1_000_001),
    ):
        changed = dict(baseline)
        changed[field] = value
        assert mediakit_cloud_operation_sha256(changed) != baseline_digest

    changed_arguments = dict(baseline)
    changed_arguments["capability_arguments"] = {"enable_confidence": False}
    assert mediakit_cloud_operation_sha256(changed_arguments) != baseline_digest

    changed_approval_refs = dict(baseline)
    changed_approval_refs["cloud_processing_approval_ref"] = "approval-cloud-2"
    changed_approval_refs["fee_authorization_ref"] = "approval-fee-2"
    assert mediakit_cloud_operation_sha256(changed_approval_refs) == baseline_digest


@pytest.mark.asyncio
async def test_ledger_authorizer_binds_exact_operation_to_the_durable_task(tmp_path) -> None:
    await init_engine_from_config(DatabaseConfig(backend="sqlite", sqlite_dir=str(tmp_path)))
    session_factory = get_session_factory()
    assert session_factory is not None
    ledger = IncubationLedgerRepository(session_factory)
    project = ProjectRef(owner_user_id="user-1", project_id="project-1")
    await ledger.create_project(project, display_name="Media project")

    runner = FakeMediaKitRunner()
    router = MediaKitCapabilityRouter(runner=runner)
    capability = await router.discover_capability("video", "asr-subtitles")
    request = _request(capability.schema_sha256)
    operation_sha256 = mediakit_cloud_operation_sha256(request.arguments)
    for grant in (
        ApprovalGrant.issue(
            grant_id="approval-cloud-1",
            project=project,
            kind="cloud_processing",
            operation_sha256=operation_sha256,
            issued_at=datetime(2026, 8, 17, 12, 0, tzinfo=UTC),
            expires_at=datetime(2026, 8, 17, 13, 0, tzinfo=UTC),
        ),
        ApprovalGrant.issue(
            grant_id="approval-fee-1",
            project=project,
            kind="fee_authorization",
            operation_sha256=operation_sha256,
            issued_at=datetime(2026, 8, 17, 12, 0, tzinfo=UTC),
            expires_at=datetime(2026, 8, 17, 13, 0, tzinfo=UTC),
            currency="CNY",
            maximum_amount_micros=1_000_000,
        ),
    ):
        await ledger.issue_approval_grant(grant)
    driver = MediaKitCloudDriver(
        router=router,
        authorize=MediaKitCloudApprovalAuthorizer(
            ledger,
            clock=lambda: datetime(2026, 8, 17, 12, 1, tzinfo=UTC),
        ),
        resolve_source=_resolve_source,
        materialize_result=_materialize,
    )

    await driver.submit(request)

    cloud = await ledger.get_approval_grant("approval-cloud-1", owner_user_id="user-1")
    fee = await ledger.get_approval_grant("approval-fee-1", owner_user_id="user-1")
    assert cloud is not None and cloud.bound_local_task_id == "task-local-1"
    assert fee is not None and fee.bound_local_task_id == "task-local-1"

    changed = _request(capability.schema_sha256, local_task_id="task-local-2")
    changed.arguments["capability_arguments"] = {"enable_confidence": False}
    with pytest.raises(PermissionError, match="MediaKit cloud authorization failed"):
        await driver.submit(changed)


@pytest.mark.asyncio
async def test_durable_arguments_reject_urls_paths_and_credentials_before_authorization() -> None:
    runner = FakeMediaKitRunner()
    authorized = False

    async def authorize(context: MediaKitCloudAuthorizationContext) -> None:
        nonlocal authorized
        del context
        authorized = True

    driver = MediaKitCloudDriver(
        router=MediaKitCapabilityRouter(runner=runner),
        authorize=authorize,
        resolve_source=lambda *_args: _source(),
        materialize_result=_materialize,
    )
    request = _request("f" * 64)
    request.arguments["capability_arguments"] = {
        "video_url": "https://provider.example/signed?token=secret",
        "api_key": "secret",
        "output_path": "/tmp/result.json",
    }

    with pytest.raises(ValueError, match="execution-only"):
        await driver.submit(request)

    assert authorized is False
    assert runner.commands == []


@pytest.mark.asyncio
async def test_durable_reference_cannot_smuggle_a_signed_url() -> None:
    runner = FakeMediaKitRunner()
    authorized = False

    async def authorize(context: MediaKitCloudAuthorizationContext) -> None:
        nonlocal authorized
        del context
        authorized = True

    driver = MediaKitCloudDriver(
        router=MediaKitCapabilityRouter(runner=runner),
        authorize=authorize,
        resolve_source=lambda *_args: _source(),
        materialize_result=_materialize,
    )
    request = _request("f" * 64)
    request.arguments["source_ref"] = "https://provider.example/input.mp4?token=secret"

    with pytest.raises(ValueError, match="stable reference"):
        await driver.submit(request)

    assert authorized is False
    assert runner.commands == []


@pytest.mark.asyncio
async def test_source_resolution_failure_does_not_expose_ephemeral_locator() -> None:
    runner = FakeMediaKitRunner()
    router = MediaKitCapabilityRouter(runner=runner)
    capability = await router.discover_capability("video", "asr-subtitles")

    async def authorize(context: MediaKitCloudAuthorizationContext) -> None:
        del context

    async def fail_source_resolution(
        user_id: str,
        source_ref: str,
        rights_ref: str,
    ) -> EphemeralMediaSource:
        del user_id, source_ref, rights_ref
        raise RuntimeError("source failed: https://cdn.example.com/input.mp4?signature=temporary-secret")

    driver = MediaKitCloudDriver(
        router=router,
        authorize=authorize,
        resolve_source=fail_source_resolution,
        materialize_result=_materialize,
    )
    runner.commands.clear()

    with pytest.raises(MediaKitCommandError, match="source resolution failed") as caught:
        await driver.submit(_request(capability.schema_sha256))

    assert "cdn.example.com" not in str(caught.value)
    assert "temporary-secret" not in str(caught.value)
    assert not any("--cloud" in command for command in runner.commands)


@pytest.mark.asyncio
async def test_cloud_query_normalizes_statuses_and_materializes_completed_output() -> None:
    runner = FakeMediaKitRunner()
    driver, schema_sha256 = await _driver(runner)
    submission = await driver.submit(_request(schema_sha256))
    task = TaskReference(
        local_task_id="task-local-1",
        user_id="user-1",
        thread_id="thread-1",
        server_name="mediakit",
        remote_task_id=submission.remote_task_id,
        driver_data=submission.driver_data,
    )
    runner.query_results.extend(
        [
            (0, {"task_id": "remote-task-1", "status": "queued"}),
            (0, {"task_id": "remote-task-1", "status": "processing"}),
            (
                0,
                {
                    "task_id": "remote-task-1",
                    "status": "completed",
                    "request_id": "provider-request-secret",
                    "video_url": "https://provider.example/output.mp4?token=temporary-secret",
                },
            ),
        ]
    )

    queued = await driver.get_status(task)
    processing = await driver.get_status(task)
    completed = await driver.get_status(task)

    assert queued.status is TaskStatus.SUBMITTED
    assert processing.status is TaskStatus.WORKING
    assert completed.status is TaskStatus.COMPLETED
    assert completed.result == {
        "artifact_ref": "artifact://media/task-local-1",
        "content_sha256": "a" * 64,
        "content_type": "video/mp4",
        "size_bytes": 42,
        "provider_output_sha256": completed.result["provider_output_sha256"],
    }
    assert len(completed.result["provider_output_sha256"]) == 64
    assert "provider.example" not in json.dumps(completed.result)
    query_commands = [command for command in runner.commands if command[:3] == ("mediakit-cli", "shared", "query-task") and command[-1] != "--schema"]
    assert query_commands
    assert all("--poll-complete" not in command for command in query_commands)


@pytest.mark.asyncio
async def test_failed_query_is_terminal_and_redacts_provider_error() -> None:
    runner = FakeMediaKitRunner()
    driver, schema_sha256 = await _driver(runner)
    submission = await driver.submit(_request(schema_sha256))
    task = TaskReference(
        local_task_id="task-local-1",
        user_id="user-1",
        thread_id="thread-1",
        server_name="mediakit",
        remote_task_id=submission.remote_task_id,
        driver_data=submission.driver_data,
    )
    runner.query_results.append(
        (
            20,
            {
                "success": False,
                "task_id": "remote-task-1",
                "status": "failed",
                "error": "Authorization Bearer provider-secret",
            },
        )
    )

    snapshot = await driver.get_status(task)

    assert snapshot.status is TaskStatus.FAILED
    assert snapshot.error == "MediaKit cloud task failed"
    assert "provider-secret" not in repr(snapshot)


@pytest.mark.asyncio
async def test_materializer_failure_does_not_expose_provider_output() -> None:
    runner = FakeMediaKitRunner()
    router = MediaKitCapabilityRouter(runner=runner)
    capability = await router.discover_capability("video", "asr-subtitles")

    async def authorize(context: MediaKitCloudAuthorizationContext) -> None:
        del context

    async def resolve_source(user_id: str, source_ref: str, rights_ref: str) -> EphemeralMediaSource:
        del user_id, source_ref, rights_ref
        return _source()

    async def fail_materialization(
        context: MediaKitCloudMaterializationContext,
    ) -> MediaKitCloudMaterializedOutput:
        raise RuntimeError(f"download failed: {context.provider_output['video_url']}")

    driver = MediaKitCloudDriver(
        router=router,
        authorize=authorize,
        resolve_source=resolve_source,
        materialize_result=fail_materialization,
    )
    submission = await driver.submit(_request(capability.schema_sha256))
    task = TaskReference(
        local_task_id="task-local-1",
        user_id="user-1",
        thread_id="thread-1",
        server_name="mediakit",
        remote_task_id=submission.remote_task_id,
        driver_data=submission.driver_data,
    )
    runner.query_results.append(
        (
            0,
            {
                "task_id": "remote-task-1",
                "status": "completed",
                "video_url": "https://provider.example/output.mp4?token=temporary-secret",
            },
        )
    )

    with pytest.raises(MediaKitCommandError, match="result materialization failed") as caught:
        await driver.get_status(task)

    assert "provider.example" not in str(caught.value)
    assert "temporary-secret" not in str(caught.value)


def test_materialized_output_requires_a_stable_artifact_reference() -> None:
    with pytest.raises(ValueError, match="artifact reference"):
        MediaKitCloudMaterializedOutput(
            artifact_ref="https://provider.example/output.mp4?token=secret",
            content_sha256="a" * 64,
            content_type="video/mp4",
            size_bytes=42,
        )


@pytest.mark.asyncio
async def test_recovery_rejects_tampered_hash_before_provider_query() -> None:
    runner = FakeMediaKitRunner()
    driver, schema_sha256 = await _driver(runner)
    submission = await driver.submit(_request(schema_sha256))
    driver_data = dict(submission.driver_data)
    driver_data["request_sha256"] = "not-a-digest"
    task = TaskReference(
        local_task_id="task-local-1",
        user_id="user-1",
        thread_id="thread-1",
        server_name="mediakit",
        remote_task_id=submission.remote_task_id,
        driver_data=driver_data,
    )
    runner.commands.clear()

    with pytest.raises(MediaKitCommandError, match="task recovery data is invalid"):
        await driver.get_status(task)

    assert runner.commands == []


@pytest.mark.asyncio
async def test_recovery_rejects_query_schema_drift_after_restart() -> None:
    submission_runner = FakeMediaKitRunner()
    submitting_driver, schema_sha256 = await _driver(submission_runner)
    submission = await submitting_driver.submit(_request(schema_sha256))
    task = TaskReference(
        local_task_id="task-local-1",
        user_id="user-1",
        thread_id="thread-1",
        server_name="mediakit",
        remote_task_id=submission.remote_task_id,
        driver_data=submission.driver_data,
    )

    recovery_runner = FakeMediaKitRunner()
    recovery_runner.query_schema_payload["output_schema"]["properties"]["progress"] = {"type": "number"}
    recovering_driver = MediaKitCloudDriver(
        router=MediaKitCapabilityRouter(runner=recovery_runner),
        authorize=lambda _context: None,
        resolve_source=lambda *_args: _source(),
        materialize_result=_materialize,
    )

    with pytest.raises(MediaKitCommandError, match="query-task schema changed"):
        await recovering_driver.get_status(task)

    assert not any(command[:3] == ("mediakit-cli", "shared", "query-task") and command[-1] != "--schema" for command in recovery_runner.commands)


@pytest.mark.asyncio
async def test_query_rejects_identity_mismatch_and_unknown_status() -> None:
    runner = FakeMediaKitRunner()
    driver, schema_sha256 = await _driver(runner)
    submission = await driver.submit(_request(schema_sha256))
    task = TaskReference(
        local_task_id="task-local-1",
        user_id="user-1",
        thread_id="thread-1",
        server_name="mediakit",
        remote_task_id=submission.remote_task_id,
        driver_data=submission.driver_data,
    )
    runner.query_results.extend(
        [
            (0, {"task_id": "another-task", "status": "completed"}),
            (0, {"task_id": "remote-task-1", "status": "mystery"}),
        ]
    )

    with pytest.raises(MediaKitCommandError, match="identity mismatch"):
        await driver.get_status(task)
    with pytest.raises(MediaKitCommandError, match="unsupported task status"):
        await driver.get_status(task)


@pytest_asyncio.fixture
async def task_repo(tmp_path):
    await init_engine_from_config(DatabaseConfig(backend="sqlite", sqlite_dir=str(tmp_path)))
    session_factory = get_session_factory()
    assert session_factory is not None
    try:
        yield McpTaskRepository(session_factory)
    finally:
        await close_engine()


@pytest.mark.asyncio
async def test_service_persists_safe_cloud_lifecycle_without_provider_urls(task_repo: McpTaskRepository) -> None:
    runner = FakeMediaKitRunner()
    runner.query_results.append(
        (
            0,
            {
                "task_id": "remote-task-1",
                "status": "completed",
                "video_url": "https://provider.example/output.mp4?token=temporary-secret",
            },
        )
    )
    driver, schema_sha256 = await _driver(runner)
    registry = McpTaskDriverRegistry()
    registry.register("mediakit", driver)
    service = McpTaskService(
        repository=task_repo,
        drivers=registry,
        poll_interval_seconds=1,
        lease_seconds=120,
        max_concurrent_polls=2,
    )
    queued_at = datetime.now(UTC)

    queued = await service.enqueue(
        driver_name="mediakit",
        request=_request(schema_sha256, local_task_id="task-e2e-1"),
        now=queued_at,
    )
    assert queued["status"] == "submission_pending"
    assert not any("--cloud" in command for command in runner.commands)

    await service.run_once(now=queued_at)
    submitted = await task_repo.get("task-e2e-1", user_id="user-1")
    assert submitted is not None
    assert submitted["status"] == "submitted"
    assert submitted["submit_arguments"] is None

    await service.run_once(now=datetime.fromisoformat(submitted["next_poll_at"]) + timedelta(seconds=1))
    completed = await task_repo.get("task-e2e-1", user_id="user-1")
    assert completed is not None
    assert completed["status"] == "completed"
    assert completed["result"]["artifact_ref"] == "artifact://media/task-e2e-1"
    serialized = json.dumps(completed, sort_keys=True)
    assert "provider.example" not in serialized
    assert "temporary-secret" not in serialized
    assert "provider-request-secret" not in serialized
