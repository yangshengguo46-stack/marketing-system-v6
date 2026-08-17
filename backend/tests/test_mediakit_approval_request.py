from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta

import pytest

from deerflow.community.mediakit import (
    MediaKitCloudApprovalRequest,
    MediaKitCloudOutputPolicy,
    MediaKitFeeQuote,
    seal_mediakit_cloud_approval_request,
)
from deerflow.incubation import (
    ArtifactEnvelope,
    ArtifactParentRef,
    ProjectRef,
)
from deerflow.incubation.media import (
    MediaKitExecutionReceipt,
    MediaObservationSnapshot,
    VideoFormatMetadata,
    VideoMetadataObservation,
    VideoStreamMetadata,
)

NOW = datetime(2026, 8, 17, 12, tzinfo=UTC)
PROJECT = ProjectRef(owner_user_id="user-1", project_id="project-1")
CAPABILITY_ARGUMENTS = {
    "tool_version": "standard",
    "scene": "common",
    "resolution": "720p",
    "fps": 25,
    "bitrate_level": "medium",
}


def _sha256(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _quote() -> MediaKitFeeQuote:
    return MediaKitFeeQuote(
        capability_schema_sha256="a" * 64,
        pricing_evidence_sha256="b" * 64,
        capability_arguments_sha256=_sha256(CAPABILITY_ARGUMENTS),
        source_duration_milliseconds=1_000,
        output_resolution_tier="720p",
        output_fps=25,
        tool_version="standard",
        currency="CNY",
        amount_micros_per_minute=750_000,
        estimated_amount_micros=12_500,
        maximum_amount_micros=20_000,
        provider_hard_cap_supported=False,
        valid_until=NOW + timedelta(minutes=30),
        output_policy=MediaKitCloudOutputPolicy(
            capability_domain="video",
            capability_tool="enhance-video",
            url_field="video_url",
            media_kind="video",
            maximum_bytes=25 * 1024 * 1024,
        ),
    )


def _operation_arguments() -> dict[str, object]:
    quote = _quote()
    return {
        "project_id": PROJECT.project_id,
        "source_ref": "media-source:" + "d" * 64,
        "source_content_sha256": "e" * 64,
        "rights_ref": "rights-1",
        "capability_domain": "video",
        "capability_tool": "enhance-video",
        "capability_arguments": CAPABILITY_ARGUMENTS,
        "expected_schema_sha256": quote.capability_schema_sha256,
        "currency": quote.currency,
        "maximum_amount_micros": quote.maximum_amount_micros,
        **quote.as_operation_fields(),
    }


def _observation_artifact(*, duration: float = 1.0) -> ArtifactEnvelope:
    snapshot = MediaObservationSnapshot(
        source_ref="media-source:" + "d" * 64,
        observation_kind="video_metadata",
        observed_at=NOW - timedelta(minutes=1),
        observation=VideoMetadataObservation(
            format_meta=VideoFormatMetadata(
                container="mp4",
                duration=duration,
                size=2_320,
            ),
            video_stream_meta=VideoStreamMetadata(
                codec="h264",
                duration=duration,
                width=320,
                height=240,
                fps=25,
            ),
        ),
        execution=MediaKitExecutionReceipt(
            capability_domain="video",
            capability_tool="probe-video-metadata",
            cli_version="0.2.0",
            schema_sha256="f" * 64,
            execution_mode="local",
            request_sha256="1" * 64,
            source_content_sha256="e" * 64,
            output_sha256="2" * 64,
            completed_at=NOW - timedelta(minutes=1),
            cloud_processing_approved=False,
        ),
    )
    return ArtifactEnvelope.seal(
        project=PROJECT,
        artifact_type="media_observation",
        version=1,
        payload=snapshot.model_dump(mode="json"),
        parents=(
            ArtifactParentRef(
                owner_user_id=PROJECT.owner_user_id,
                project_id=PROJECT.project_id,
                artifact_id="source-receipt-1",
                artifact_type="media_source_receipt",
                content_sha256="3" * 64,
            ),
        ),
        evidence_role="user_material",
        created_at=snapshot.observed_at,
        source_thread_id="thread-1",
        source_run_id="run-1",
    )


def test_server_quote_seals_an_immutable_approval_request_without_locator() -> None:
    request = MediaKitCloudApprovalRequest.from_quote(
        project=PROJECT,
        quote=_quote(),
        operation_arguments=_operation_arguments(),
        source_content_sha256="e" * 64,
        quoted_at=NOW,
    )
    artifact = seal_mediakit_cloud_approval_request(
        project=PROJECT,
        request=request,
        media_observation_artifact=_observation_artifact(),
        source_thread_id="thread-1",
        source_run_id="run-2",
    )

    assert artifact.artifact_type == "mediakit_cloud_approval_request"
    assert artifact.parents == (_observation_artifact().to_parent_ref(),)
    assert artifact.payload["fee_quote_sha256"] == _quote().fee_quote_sha256
    serialized = artifact.model_dump_json()
    assert "source_ref" not in serialized
    assert "rights_ref" not in serialized
    assert "video_url" not in serialized
    assert "/Users/" not in serialized


def test_approval_request_rejects_operation_or_observation_mismatch() -> None:
    operation = _operation_arguments()
    operation["maximum_amount_micros"] = 20_001
    with pytest.raises(ValueError, match="quote"):
        MediaKitCloudApprovalRequest.from_quote(
            project=PROJECT,
            quote=_quote(),
            operation_arguments=operation,
            source_content_sha256="e" * 64,
            quoted_at=NOW,
        )

    request = MediaKitCloudApprovalRequest.from_quote(
        project=PROJECT,
        quote=_quote(),
        operation_arguments=_operation_arguments(),
        source_content_sha256="e" * 64,
        quoted_at=NOW,
    )
    with pytest.raises(ValueError, match="duration"):
        seal_mediakit_cloud_approval_request(
            project=PROJECT,
            request=request,
            media_observation_artifact=_observation_artifact(duration=2),
            source_thread_id="thread-1",
            source_run_id="run-2",
        )

    benchmark_observation = _observation_artifact().model_copy(update={"evidence_role": "benchmark_evidence"})
    with pytest.raises(ValueError, match="user-authorized material"):
        seal_mediakit_cloud_approval_request(
            project=PROJECT,
            request=request,
            media_observation_artifact=benchmark_observation,
            source_thread_id="thread-1",
            source_run_id="run-2",
        )
