from __future__ import annotations

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
from deerflow.incubation.media import MediaSourceReceipt


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
