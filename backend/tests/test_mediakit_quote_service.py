from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from deerflow.community.mediakit import (
    MediaKitCapability,
    MediaKitEnhanceVideoQuoteService,
    MediaKitPricingConfigurationError,
)
from deerflow.incubation import (
    MediaKitExecutionReceipt,
    MediaObservationSnapshot,
    MediaSourceReceipt,
    ProjectRef,
    VideoMetadataObservation,
    seal_media_observation_snapshot,
    seal_media_source_receipt,
)
from deerflow.incubation.media import VideoFormatMetadata, VideoStreamMetadata

NOW = datetime(2026, 8, 17, 12, tzinfo=UTC)
PROJECT = ProjectRef(owner_user_id="user-1", project_id="project-1")
SCHEMA_SHA256 = "5573324d5727b5398b13ca89182a1e45c7953c9a8389bb12eec0b331eca46f00"
SOURCE_SHA256 = "e" * 64
CAPABILITY_ARGUMENTS = {
    "tool_version": "standard",
    "scene": "common",
    "resolution": "720p",
    "fps": 25,
    "bitrate_level": "medium",
}


class _CapabilityRouter:
    def __init__(self, *, schema_sha256: str = SCHEMA_SHA256) -> None:
        self.calls: list[tuple[str, str]] = []
        self.capability = _capability(schema_sha256=schema_sha256)

    async def discover_capability(self, domain: str, tool: str) -> MediaKitCapability:
        self.calls.append((domain, tool))
        return self.capability


def _capability(*, schema_sha256: str = SCHEMA_SHA256) -> MediaKitCapability:
    return MediaKitCapability(
        domain="video",
        tool="enhance-video",
        name="enhance_video",
        description="enhance",
        cli_version="0.2.0",
        schema_sha256=schema_sha256,
        input_schema={
            "type": "object",
            "properties": {
                "video_url": {"type": "string"},
                "tool_version": {"type": "string", "enum": ["standard", "professional"]},
                "scene": {"type": "string", "enum": ["common", "ugc", "short_series", "aigc", "old_film"]},
                "resolution": {
                    "type": "string",
                    "enum": ["240p", "360p", "480p", "540p", "720p", "1080p", "2k", "4k"],
                },
                "resolution_limit": {"type": "integer"},
                "fps": {"type": "number"},
                "bitrate_level": {"type": "string", "enum": ["low", "medium", "high"]},
                "client_token": {"type": "string"},
                "callback_args": {"type": "string"},
            },
            "required": ["video_url"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "task_id": {"type": "string"},
                "request_id": {"type": "string"},
            },
            "final_result": {
                "type": "object",
                "properties": {
                    "video_url": {"type": "string"},
                    "duration": {"type": "number"},
                    "resolution": {"type": "string"},
                },
            },
        },
    )


def _pricing_payload(*, valid_until: datetime | None = None) -> dict[str, object]:
    return {
        "provider": "volcengine-mediakit",
        "capability_domain": "video",
        "capability_tool": "enhance-video",
        "currency": "CNY",
        "source_url": "https://docs.volcengine.com/docs/6448/2486473",
        "document_id": "2486473",
        "document_sha256": "41e6833f4ca2ae1946e241d2e273b3fea833815dc4ccd129abf4b25115789ad6",
        "document_updated_at": "2026-08-06T13:38:50Z",
        "checked_at": "2026-08-17T10:00:00Z",
        "valid_until": (valid_until or (NOW + timedelta(hours=1))).isoformat(),
        "provider_hard_cap_supported": False,
        "rates": [
            {
                "tool_version": "standard",
                "resolution_tier": "720p",
                "maximum_fps": 30,
                "amount_micros_per_minute": 750_000,
            }
        ],
    }


def _write_pricing(tmp_path, *, payload: dict[str, object] | None = None):
    path = tmp_path / "enhance-video-pricing.json"
    path.write_text(json.dumps(payload or _pricing_payload()), encoding="utf-8")
    return path


def _media_artifacts(*, role: str = "user_material", source_ref: str = "media-source-1"):
    receipt = MediaSourceReceipt(
        source_ref=source_ref,
        media_kind="video",
        transport="local_file",
        resolver="gateway-upload",
        rights_ref="rights-1",
        locator_sha256="a" * 64,
        resolved_at=NOW - timedelta(minutes=2),
    )
    source_artifact = seal_media_source_receipt(
        project=PROJECT,
        receipt=receipt,
        evidence_role=role,
        source_thread_id="thread-1",
        source_run_id="run-1",
    )
    snapshot = MediaObservationSnapshot(
        source_ref=source_ref,
        observation_kind="video_metadata",
        observed_at=NOW - timedelta(minutes=1),
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
            schema_sha256="b" * 64,
            execution_mode="local",
            request_sha256="c" * 64,
            source_content_sha256=SOURCE_SHA256,
            output_sha256="d" * 64,
            completed_at=NOW - timedelta(minutes=1),
            cloud_processing_approved=False,
        ),
    )
    observation_artifact = seal_media_observation_snapshot(
        project=PROJECT,
        snapshot=snapshot,
        source_receipt_artifact=source_artifact,
        source_thread_id="thread-1",
        source_run_id="run-2",
    )
    return source_artifact, observation_artifact


def _service(tmp_path, *, router: _CapabilityRouter | None = None, pricing_payload: dict[str, object] | None = None):
    return MediaKitEnhanceVideoQuoteService(
        capability_router=router or _CapabilityRouter(),
        pricing_evidence_path=_write_pricing(tmp_path, payload=pricing_payload),
        expected_schema_sha256=SCHEMA_SHA256,
        allowed_tool_versions={"standard"},
        allowed_resolution_tiers={"720p"},
        minimum_fps=15,
        maximum_fps=30,
        maximum_output_bytes=25 * 1024 * 1024,
    )


@pytest.mark.asyncio
async def test_server_quote_service_seals_owned_user_material_without_execution_locator(tmp_path) -> None:
    router = _CapabilityRouter()
    service = _service(tmp_path, router=router)
    source_artifact, observation_artifact = _media_artifacts()

    artifact = await service.prepare_approval_request(
        project=PROJECT,
        media_observation_artifact=observation_artifact,
        source_receipt_artifact=source_artifact,
        capability_arguments=CAPABILITY_ARGUMENTS,
        maximum_amount_micros=20_000,
        quoted_at=NOW,
        source_run_id="gateway-quote-1",
    )

    assert router.calls == [("video", "enhance-video")]
    assert artifact.artifact_type == "mediakit_cloud_approval_request"
    assert artifact.parents == (observation_artifact.to_parent_ref(),)
    assert artifact.payload["estimated_amount_micros"] == 12_500
    assert artifact.payload["maximum_amount_micros"] == 20_000
    assert artifact.payload["capability_schema_sha256"] == SCHEMA_SHA256
    serialized = artifact.model_dump_json()
    assert "media-source-1" not in serialized
    assert "rights-1" not in serialized
    assert "video_url" not in serialized
    assert "local_path" not in serialized


@pytest.mark.asyncio
async def test_quote_service_rejects_non_user_material_or_mismatched_parent(tmp_path) -> None:
    service = _service(tmp_path)
    benchmark_source, benchmark_observation = _media_artifacts(role="benchmark_evidence")
    with pytest.raises(ValueError, match="user-authorized material"):
        await service.prepare_approval_request(
            project=PROJECT,
            media_observation_artifact=benchmark_observation,
            source_receipt_artifact=benchmark_source,
            capability_arguments=CAPABILITY_ARGUMENTS,
            maximum_amount_micros=20_000,
            quoted_at=NOW,
            source_run_id="gateway-quote-1",
        )

    source_artifact, observation_artifact = _media_artifacts()
    other_source, _other_observation = _media_artifacts(source_ref="other-source")
    with pytest.raises(ValueError, match="source receipt"):
        await service.prepare_approval_request(
            project=PROJECT,
            media_observation_artifact=observation_artifact,
            source_receipt_artifact=other_source,
            capability_arguments=CAPABILITY_ARGUMENTS,
            maximum_amount_micros=20_000,
            quoted_at=NOW,
            source_run_id="gateway-quote-1",
        )
    assert source_artifact.artifact_id != other_source.artifact_id


@pytest.mark.asyncio
async def test_quote_service_fails_closed_on_stale_pricing_schema_drift_or_low_cap(tmp_path) -> None:
    source_artifact, observation_artifact = _media_artifacts()
    stale = _service(
        tmp_path,
        pricing_payload=_pricing_payload(valid_until=NOW),
    )
    with pytest.raises(PermissionError, match="expired"):
        await stale.prepare_approval_request(
            project=PROJECT,
            media_observation_artifact=observation_artifact,
            source_receipt_artifact=source_artifact,
            capability_arguments=CAPABILITY_ARGUMENTS,
            maximum_amount_micros=20_000,
            quoted_at=NOW,
            source_run_id="gateway-quote-1",
        )

    drifted = _service(tmp_path, router=_CapabilityRouter(schema_sha256="f" * 64))
    with pytest.raises(MediaKitPricingConfigurationError, match="schema"):
        await drifted.prepare_approval_request(
            project=PROJECT,
            media_observation_artifact=observation_artifact,
            source_receipt_artifact=source_artifact,
            capability_arguments=CAPABILITY_ARGUMENTS,
            maximum_amount_micros=20_000,
            quoted_at=NOW,
            source_run_id="gateway-quote-1",
        )

    service = _service(tmp_path)
    with pytest.raises(PermissionError, match="below"):
        await service.prepare_approval_request(
            project=PROJECT,
            media_observation_artifact=observation_artifact,
            source_receipt_artifact=source_artifact,
            capability_arguments=CAPABILITY_ARGUMENTS,
            maximum_amount_micros=12_499,
            quoted_at=NOW,
            source_run_id="gateway-quote-1",
        )


@pytest.mark.asyncio
async def test_quote_service_rejects_missing_oversized_or_unknown_pricing_documents(tmp_path) -> None:
    source_artifact, observation_artifact = _media_artifacts()
    missing = MediaKitEnhanceVideoQuoteService(
        capability_router=_CapabilityRouter(),
        pricing_evidence_path=tmp_path / "missing.json",
        expected_schema_sha256=SCHEMA_SHA256,
        allowed_tool_versions={"standard"},
        allowed_resolution_tiers={"720p"},
        minimum_fps=15,
        maximum_fps=30,
        maximum_output_bytes=25 * 1024 * 1024,
    )
    with pytest.raises(MediaKitPricingConfigurationError, match="unavailable"):
        await missing.prepare_approval_request(
            project=PROJECT,
            media_observation_artifact=observation_artifact,
            source_receipt_artifact=source_artifact,
            capability_arguments=CAPABILITY_ARGUMENTS,
            maximum_amount_micros=20_000,
            quoted_at=NOW,
            source_run_id="gateway-quote-1",
        )

    oversized_path = tmp_path / "oversized.json"
    oversized_path.write_text(" " * (64 * 1024 + 1), encoding="utf-8")
    oversized = MediaKitEnhanceVideoQuoteService(
        capability_router=_CapabilityRouter(),
        pricing_evidence_path=oversized_path,
        expected_schema_sha256=SCHEMA_SHA256,
        allowed_tool_versions={"standard"},
        allowed_resolution_tiers={"720p"},
        minimum_fps=15,
        maximum_fps=30,
        maximum_output_bytes=25 * 1024 * 1024,
    )
    with pytest.raises(MediaKitPricingConfigurationError, match="unavailable"):
        await oversized.prepare_approval_request(
            project=PROJECT,
            media_observation_artifact=observation_artifact,
            source_receipt_artifact=source_artifact,
            capability_arguments=CAPABILITY_ARGUMENTS,
            maximum_amount_micros=20_000,
            quoted_at=NOW,
            source_run_id="gateway-quote-1",
        )

    invalid_payload = _pricing_payload()
    invalid_payload["unexpected"] = "not accepted"
    invalid = _service(tmp_path, pricing_payload=invalid_payload)
    with pytest.raises(MediaKitPricingConfigurationError, match="invalid"):
        await invalid.prepare_approval_request(
            project=PROJECT,
            media_observation_artifact=observation_artifact,
            source_receipt_artifact=source_artifact,
            capability_arguments=CAPABILITY_ARGUMENTS,
            maximum_amount_micros=20_000,
            quoted_at=NOW,
            source_run_id="gateway-quote-1",
        )
