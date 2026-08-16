from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from deerflow.community.mediakit import (
    CommandResult,
    EphemeralMediaSource,
    MediaKitCapabilityRouter,
    MediaKitCommandError,
)
from deerflow.incubation import ArtifactEnvelope, ProjectRef
from deerflow.incubation.media import (
    MediaKitExecutionReceipt,
    MediaObservationSnapshot,
    MediaSourceReceipt,
    VideoMetadataObservation,
    seal_media_observation_snapshot,
    seal_media_source_receipt,
)


def _schema_payload() -> dict:
    return {
        "_notice": {"skills": {"message": "sync available"}},
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
            "properties": {"task_id": {"type": "string"}},
        },
    }


def _metadata_schema_payload() -> dict:
    return {
        "_notice": {"skills": {"message": "sync available"}},
        "name": "probe_video_metadata",
        "description": "metadata",
        "input_schema": {
            "type": "object",
            "properties": {"video_url": {"type": "string"}},
            "required": ["video_url"],
        },
        # MediaKit 0.2.0 describes the cloud submission here. Its local result
        # is intentionally checked by VideoMetadataObservation as well.
        "output_schema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string"},
                "request_id": {"type": "string"},
            },
        },
    }


def _metadata_output() -> dict:
    return {
        "_notice": {"skills": {"message": "sync available"}},
        "format_meta": {
            "bitrate": 99_344,
            "container": "mov,mp4,m4a,3gp,3g2,mj2",
            "duration": 1.0,
            "md5": "b040e8a57b6668af7544ac7bf6130bed",
            "size": 12_418,
        },
        "video_stream_meta": {
            "bitrate": 9_208,
            "codec": "h264",
            "duration": 1.0,
            "dynamic_range": None,
            "fps": 25.0,
            "height": 240,
            "width": 320,
        },
        "audio_stream_meta": {
            "bitrate": 70_295,
            "channels": 1,
            "codec": "aac",
            "duration": 1.0,
            "sample_rate": 44_100,
        },
    }


@pytest.mark.asyncio
async def test_mediakit_router_discovers_schema_and_prepares_a_direct_video_url() -> None:
    calls: list[tuple[str, ...]] = []

    async def runner(command: tuple[str, ...], timeout_seconds: float) -> CommandResult:
        calls.append(command)
        if command[-1] == "version":
            return CommandResult(
                returncode=0,
                stdout="mediakit-cli 0.2.0\nbuild date: 2026-07-14T07:05:19Z\n",
                stderr="",
            )
        return CommandResult(
            returncode=0,
            stdout=json.dumps(_schema_payload()),
            stderr="",
        )

    source = EphemeralMediaSource.direct_http(
        source_ref="douyin:video:123",
        locator="https://cdn.example.com/video-123.mp4?signature=temporary",
        rights_ref="rights:benchmark-public-sample",
        resolver="douyin_media_resolver:v1",
        content_type="video/mp4",
        expires_at=datetime.now(UTC) + timedelta(minutes=10),
    )
    router = MediaKitCapabilityRouter(runner=runner)

    prepared = await router.prepare_video_call(
        domain="video",
        tool="asr-subtitles",
        source=source,
        mode="cloud",
        arguments={"enable_confidence": True},
        client_token="job-123",
    )

    assert calls == [
        ("mediakit-cli", "version"),
        ("mediakit-cli", "video", "asr-subtitles", "--schema"),
    ]
    assert prepared.command == (
        "mediakit-cli",
        "--cloud",
        "video",
        "asr-subtitles",
        "--video-url",
        "https://cdn.example.com/video-123.mp4?signature=temporary",
        "--enable-confidence=true",
        "--client-token",
        "job-123",
    )
    assert "signature=temporary" not in repr(prepared)
    assert prepared.capability.cli_version == "0.2.0"
    assert prepared.capability.notices == ("sync available",)


def test_platform_page_is_not_a_mediakit_video_source() -> None:
    with pytest.raises(ValueError, match="resolved direct media"):
        EphemeralMediaSource.platform_page(
            source_ref="douyin:video:123",
            locator="https://v.douyin.com/example/",
            rights_ref="rights:benchmark-public-sample",
        )


def test_html_response_cannot_be_attested_as_a_direct_video_url() -> None:
    with pytest.raises(ValueError, match="video content type"):
        EphemeralMediaSource.direct_http(
            source_ref="douyin:video:123",
            locator="https://v.douyin.com/example/",
            rights_ref="rights:benchmark-public-sample",
            resolver="douyin_media_resolver:v1",
            content_type="text/html; charset=utf-8",
        )


def test_media_source_receipt_never_persists_url_or_local_path(tmp_path: Path) -> None:
    local_video = tmp_path / "video.mp4"
    local_video.write_bytes(b"video-bytes")
    source = EphemeralMediaSource.local_file(
        source_ref="douyin:video:123",
        locator=local_video,
        rights_ref="rights:benchmark-public-sample",
        resolver="douyin_media_resolver:v1",
    )

    receipt = MediaSourceReceipt.from_ephemeral(
        source,
        resolved_at=datetime.now(UTC),
    )
    payload = receipt.model_dump(mode="json")
    serialized = json.dumps(payload)

    assert str(local_video) not in serialized
    assert "local_path" not in serialized
    assert payload["locator_sha256"] == source.locator_sha256
    ArtifactEnvelope.seal(
        project=ProjectRef(owner_user_id="user-1", project_id="project-1"),
        artifact_type="media_source_receipt",
        version=1,
        payload=payload,
        created_at=datetime.now(UTC),
        source_thread_id="thread-1",
        source_run_id="run-1",
    )


@pytest.mark.asyncio
async def test_mediakit_router_rejects_a_schema_without_video_url() -> None:
    payload = _schema_payload()
    payload["input_schema"]["properties"].pop("video_url")

    async def runner(command: tuple[str, ...], timeout_seconds: float) -> CommandResult:
        if command[-1] == "version":
            return CommandResult(returncode=0, stdout="mediakit-cli 0.2.0\n", stderr="")
        return CommandResult(returncode=0, stdout=json.dumps(payload), stderr="")

    source = EphemeralMediaSource.direct_http(
        source_ref="douyin:video:123",
        locator="https://cdn.example.com/video.mp4",
        rights_ref="rights:benchmark-public-sample",
        resolver="douyin_media_resolver:v1",
        content_type="video/mp4",
    )

    with pytest.raises(MediaKitCommandError, match="video_url"):
        await MediaKitCapabilityRouter(runner=runner).prepare_video_call(
            domain="video",
            tool="not-a-video-tool",
            source=source,
        )


@pytest.mark.asyncio
async def test_local_metadata_execution_hashes_the_file_and_returns_a_bounded_result(
    tmp_path: Path,
) -> None:
    calls: list[tuple[str, ...]] = []

    async def runner(command: tuple[str, ...], timeout_seconds: float) -> CommandResult:
        calls.append(command)
        if command[-1] == "version":
            return CommandResult(returncode=0, stdout="mediakit-cli 0.2.0\n", stderr="")
        if command[-1] == "--schema":
            return CommandResult(
                returncode=0,
                stdout=json.dumps(_metadata_schema_payload()),
                stderr="",
            )
        return CommandResult(
            returncode=0,
            stdout=json.dumps(_metadata_output()),
            stderr="",
        )

    local_video = tmp_path / "input.mp4"
    local_video.write_bytes(b"stable-video-bytes")
    source = EphemeralMediaSource.local_file(
        source_ref="douyin:video:123",
        locator=local_video,
        rights_ref="rights:benchmark-public-sample",
        resolver="douyin_media_resolver:v1",
    )
    router = MediaKitCapabilityRouter(runner=runner)
    prepared = await router.prepare_video_call(
        domain="video",
        tool="probe-video-metadata",
        source=source,
        mode="local",
    )

    execution = await router.execute_local(prepared)

    assert calls[-1] == (
        "mediakit-cli",
        "--local",
        "video",
        "probe-video-metadata",
        "--video-url",
        str(local_video),
    )
    assert execution.source_content_sha256 == hashlib.sha256(b"stable-video-bytes").hexdigest()
    assert execution.output == {key: value for key, value in _metadata_output().items() if key != "_notice"}
    assert execution.notices == ("sync available",)
    assert str(local_video) not in repr(execution)


@pytest.mark.asyncio
async def test_local_execution_rejects_cloud_calls_and_truncated_output(tmp_path: Path) -> None:
    local_video = tmp_path / "input.mp4"
    local_video.write_bytes(b"video")
    source = EphemeralMediaSource.local_file(
        source_ref="source-1",
        locator=local_video,
        rights_ref="rights-1",
        resolver="upload:v1",
    )

    async def runner(command: tuple[str, ...], timeout_seconds: float) -> CommandResult:
        if command[-1] == "version":
            return CommandResult(returncode=0, stdout="mediakit-cli 0.2.0\n", stderr="")
        if command[-1] == "--schema":
            return CommandResult(returncode=0, stdout=json.dumps(_metadata_schema_payload()), stderr="")
        return CommandResult(
            returncode=0,
            stdout="{}",
            stderr="",
            stdout_truncated=True,
        )

    router = MediaKitCapabilityRouter(runner=runner)
    cloud_call = await router.prepare_video_call(
        domain="video",
        tool="probe-video-metadata",
        source=source,
        mode="cloud",
        client_token="task-1",
    )
    with pytest.raises(ValueError, match="local execution requires local mode"):
        await router.execute_local(cloud_call)

    local_call = await router.prepare_video_call(
        domain="video",
        tool="probe-video-metadata",
        source=source,
        mode="local",
    )
    with pytest.raises(MediaKitCommandError, match="output budget"):
        await router.execute_local(local_call)


@pytest.mark.asyncio
async def test_local_execution_rejects_a_source_that_changes_during_processing(
    tmp_path: Path,
) -> None:
    local_video = tmp_path / "input.mp4"
    local_video.write_bytes(b"version-one")
    source = EphemeralMediaSource.local_file(
        source_ref="source-1",
        locator=local_video,
        rights_ref="rights-1",
        resolver="upload:v1",
    )

    async def runner(command: tuple[str, ...], timeout_seconds: float) -> CommandResult:
        if command[-1] == "version":
            return CommandResult(returncode=0, stdout="mediakit-cli 0.2.0\n", stderr="")
        if command[-1] == "--schema":
            return CommandResult(returncode=0, stdout=json.dumps(_metadata_schema_payload()), stderr="")
        local_video.write_bytes(b"version-two")
        return CommandResult(returncode=0, stdout=json.dumps(_metadata_output()), stderr="")

    router = MediaKitCapabilityRouter(runner=runner)
    prepared = await router.prepare_video_call(
        domain="video",
        tool="probe-video-metadata",
        source=source,
        mode="local",
    )

    with pytest.raises(MediaKitCommandError, match="changed during execution"):
        await router.execute_local(prepared)


def test_video_metadata_contract_rejects_a_cloud_submission_disguised_as_local_output() -> None:
    with pytest.raises(ValueError, match="format_meta"):
        VideoMetadataObservation.from_mediakit_output({"task_id": "remote-1", "request_id": "request-1"})


@pytest.mark.asyncio
async def test_local_metadata_seals_a_role_inheriting_observation_without_paths(
    tmp_path: Path,
) -> None:
    local_video = tmp_path / "input.mp4"
    local_video.write_bytes(b"video")
    source = EphemeralMediaSource.local_file(
        source_ref="douyin:video:123",
        locator=local_video,
        rights_ref="rights:benchmark-public-sample",
        resolver="douyin_media_resolver:v1",
    )

    async def runner(command: tuple[str, ...], timeout_seconds: float) -> CommandResult:
        if command[-1] == "version":
            return CommandResult(returncode=0, stdout="mediakit-cli 0.2.0\n", stderr="")
        if command[-1] == "--schema":
            return CommandResult(returncode=0, stdout=json.dumps(_metadata_schema_payload()), stderr="")
        return CommandResult(returncode=0, stdout=json.dumps(_metadata_output()), stderr="")

    router = MediaKitCapabilityRouter(runner=runner)
    execution = await router.execute_local(
        await router.prepare_video_call(
            domain="video",
            tool="probe-video-metadata",
            source=source,
            mode="local",
        )
    )
    project = ProjectRef(owner_user_id="user-1", project_id="project-1")
    source_artifact = seal_media_source_receipt(
        project=project,
        receipt=MediaSourceReceipt.from_ephemeral(source, resolved_at=execution.executed_at),
        evidence_role="benchmark_evidence",
        source_thread_id="thread-1",
        source_run_id="run-1",
    )
    receipt = MediaKitExecutionReceipt.from_local_execution(execution)
    snapshot = MediaObservationSnapshot(
        source_ref=source.source_ref,
        observation_kind="video_metadata",
        observed_at=execution.executed_at,
        observation=VideoMetadataObservation.from_mediakit_output(execution.output),
        execution=receipt,
    )

    artifact = seal_media_observation_snapshot(
        project=project,
        snapshot=snapshot,
        source_receipt_artifact=source_artifact,
        source_thread_id="thread-1",
        source_run_id="run-1",
    )

    serialized = json.dumps(artifact.model_dump(mode="json"), ensure_ascii=False)
    assert artifact.evidence_role == "benchmark_evidence"
    assert artifact.parents == (source_artifact.to_parent_ref(),)
    assert str(local_video) not in serialized
    assert "local_path" not in serialized
    assert artifact.payload["execution"]["source_content_sha256"] == execution.source_content_sha256


def test_media_observation_requires_a_role_bearing_source_receipt() -> None:
    project = ProjectRef(owner_user_id="user-1", project_id="project-1")
    observed_at = datetime.now(UTC)
    source_artifact = ArtifactEnvelope.seal(
        project=project,
        artifact_type="media_source_receipt",
        version=1,
        payload={"source_ref": "source-1"},
        created_at=datetime.now(UTC),
        source_thread_id="thread-1",
        source_run_id="run-1",
    )
    snapshot = MediaObservationSnapshot(
        source_ref="source-1",
        observation_kind="video_metadata",
        observed_at=observed_at,
        observation=VideoMetadataObservation.from_mediakit_output(_metadata_output()),
        execution=MediaKitExecutionReceipt(
            capability_domain="video",
            capability_tool="probe-video-metadata",
            cli_version="0.2.0",
            schema_sha256="a" * 64,
            execution_mode="local",
            request_sha256="b" * 64,
            source_content_sha256="c" * 64,
            output_sha256="d" * 64,
            completed_at=observed_at,
            cloud_processing_approved=False,
        ),
    )

    with pytest.raises(ValueError, match="evidence role"):
        seal_media_observation_snapshot(
            project=project,
            snapshot=snapshot,
            source_receipt_artifact=source_artifact,
            source_thread_id="thread-1",
            source_run_id="run-1",
        )
