from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from deerflow.community.mediakit import (
    MediaKitCapability,
    MediaKitCommandError,
    MediaKitEnhanceVideoPreflight,
    MediaKitPricingEvidence,
    MediaKitPricingRate,
)
from deerflow.incubation.media import (
    AudioStreamMetadata,
    VideoFormatMetadata,
    VideoMetadataObservation,
    VideoStreamMetadata,
)

_ENHANCE_SCHEMA_SHA256 = "5573324d5727b5398b13ca89182a1e45c7953c9a8389bb12eec0b331eca46f00"
_PRICING_DOCUMENT_SHA256 = "41e6833f4ca2ae1946e241d2e273b3fea833815dc4ccd129abf4b25115789ad6"
_CHECKED_AT = datetime(2026, 8, 17, 10, tzinfo=UTC)


def _capability(*, schema_sha256: str = _ENHANCE_SCHEMA_SHA256) -> MediaKitCapability:
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
                "tool_version": {
                    "type": "string",
                    "enum": ["standard", "professional"],
                },
                "scene": {
                    "type": "string",
                    "enum": ["common", "ugc", "short_series", "aigc", "old_film"],
                },
                "resolution": {
                    "type": "string",
                    "enum": ["240p", "360p", "480p", "540p", "720p", "1080p", "2k", "4k"],
                },
                "resolution_limit": {"type": "integer"},
                "fps": {"type": "number"},
                "bitrate_level": {
                    "type": "string",
                    "enum": ["low", "medium", "high"],
                },
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


def _metadata(*, duration: float = 1.0) -> VideoMetadataObservation:
    return VideoMetadataObservation(
        format_meta=VideoFormatMetadata(
            container="mp4",
            duration=duration,
            size=2_320,
            bitrate=18_560,
        ),
        video_stream_meta=VideoStreamMetadata(
            codec="h264",
            duration=duration,
            width=320,
            height=240,
            fps=25.0,
            bitrate=9_000,
        ),
        audio_stream_meta=AudioStreamMetadata(
            codec="aac",
            duration=duration,
            channels=1,
            sample_rate=44_100,
            bitrate=8_000,
        ),
    )


def _pricing(*, valid_until: datetime | None = None) -> MediaKitPricingEvidence:
    return MediaKitPricingEvidence(
        provider="volcengine-mediakit",
        capability_domain="video",
        capability_tool="enhance-video",
        currency="CNY",
        source_url="https://docs.volcengine.com/docs/6448/2486473",
        document_id="2486473",
        document_sha256=_PRICING_DOCUMENT_SHA256,
        document_updated_at=datetime(2026, 8, 6, 13, 38, 50, tzinfo=UTC),
        checked_at=_CHECKED_AT,
        valid_until=valid_until or (_CHECKED_AT + timedelta(days=1)),
        provider_hard_cap_supported=False,
        rates=(
            MediaKitPricingRate(
                tool_version="standard",
                resolution_tier="720p",
                maximum_fps=30,
                amount_micros_per_minute=750_000,
            ),
        ),
    )


def _preflight(*, pricing: MediaKitPricingEvidence | None = None) -> MediaKitEnhanceVideoPreflight:
    return MediaKitEnhanceVideoPreflight(
        expected_schema_sha256=_ENHANCE_SCHEMA_SHA256,
        pricing=pricing or _pricing(),
        allowed_tool_versions={"standard"},
        allowed_resolution_tiers={"720p"},
        minimum_fps=15,
        maximum_fps=30,
        maximum_output_bytes=25 * 1024 * 1024,
    )


def _arguments(**changes: object) -> dict[str, object]:
    arguments: dict[str, object] = {
        "tool_version": "standard",
        "scene": "common",
        "resolution": "720p",
        "fps": 25,
        "bitrate_level": "medium",
    }
    arguments.update(changes)
    return arguments


def test_preflight_quotes_first_synthetic_run_from_explicit_specs() -> None:
    quote = _preflight().quote(
        capability=_capability(),
        source_metadata=_metadata(duration=1.0),
        capability_arguments=_arguments(),
        maximum_amount_micros=20_000,
        now=_CHECKED_AT + timedelta(minutes=5),
    )

    assert quote.currency == "CNY"
    assert quote.source_duration_milliseconds == 1_000
    assert quote.output_resolution_tier == "720p"
    assert quote.output_fps == 25.0
    assert quote.tool_version == "standard"
    assert quote.amount_micros_per_minute == 750_000
    assert quote.estimated_amount_micros == 12_500
    assert quote.maximum_amount_micros == 20_000
    assert quote.provider_hard_cap_supported is False
    assert quote.capability_schema_sha256 == _ENHANCE_SCHEMA_SHA256
    assert quote.pricing_evidence_sha256 == _pricing().evidence_sha256
    assert len(quote.capability_arguments_sha256) == 64
    assert len(quote.fee_quote_sha256) == 64
    assert quote.output_policy.capability_tool == "enhance-video"
    assert quote.output_policy.url_field == "video_url"
    assert quote.output_policy.maximum_bytes == 25 * 1024 * 1024
    assert quote.as_operation_fields() == {
        "pricing_evidence_sha256": quote.pricing_evidence_sha256,
        "fee_quote_sha256": quote.fee_quote_sha256,
        "estimated_amount_micros": 12_500,
        "fee_quote_valid_until": (_CHECKED_AT + timedelta(days=1)).isoformat(),
    }


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        ({"tool_version": "standard", "fps": 25}, "explicit output resolution"),
        ({"tool_version": "standard", "resolution": "720p"}, "explicit output fps"),
        (_arguments(tool_version="professional"), "tool version is not enabled"),
        (_arguments(resolution="1080p"), "resolution tier is not enabled"),
        (_arguments(fps=31), "output fps is outside"),
        (_arguments(callback_args="opaque"), "callback arguments are not allowed"),
    ],
)
def test_preflight_rejects_ambiguous_or_out_of_scope_first_run(
    arguments: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        _preflight().quote(
            capability=_capability(),
            source_metadata=_metadata(),
            capability_arguments=arguments,
            maximum_amount_micros=20_000,
            now=_CHECKED_AT + timedelta(minutes=5),
        )


def test_preflight_rejects_stale_pricing_and_insufficient_authorization() -> None:
    expired = _pricing(valid_until=_CHECKED_AT + timedelta(minutes=1))
    with pytest.raises(PermissionError, match="pricing evidence expired"):
        _preflight(pricing=expired).quote(
            capability=_capability(),
            source_metadata=_metadata(),
            capability_arguments=_arguments(),
            maximum_amount_micros=20_000,
            now=_CHECKED_AT + timedelta(minutes=2),
        )

    with pytest.raises(PermissionError, match="fee authorization is below"):
        _preflight().quote(
            capability=_capability(),
            source_metadata=_metadata(),
            capability_arguments=_arguments(),
            maximum_amount_micros=12_499,
            now=_CHECKED_AT + timedelta(minutes=5),
        )

    with pytest.raises(PermissionError, match="pricing evidence expired"):
        _preflight().quote(
            capability=_capability(),
            source_metadata=_metadata(),
            capability_arguments=_arguments(),
            maximum_amount_micros=20_000,
            now=_pricing().valid_until,
        )


def test_preflight_rejects_schema_drift_and_an_untyped_terminal_video() -> None:
    with pytest.raises(MediaKitCommandError, match="capability schema changed"):
        _preflight().quote(
            capability=_capability(schema_sha256="a" * 64),
            source_metadata=_metadata(),
            capability_arguments=_arguments(),
            maximum_amount_micros=20_000,
            now=_CHECKED_AT + timedelta(minutes=5),
        )

    capability = _capability()
    capability.output_schema["final_result"]["properties"].pop("video_url")
    with pytest.raises(MediaKitCommandError, match="terminal output contract"):
        _preflight().quote(
            capability=capability,
            source_metadata=_metadata(),
            capability_arguments=_arguments(),
            maximum_amount_micros=20_000,
            now=_CHECKED_AT + timedelta(minutes=5),
        )


def test_quote_digest_binds_arguments_price_evidence_and_user_cap() -> None:
    preflight = _preflight()
    common = {
        "capability": _capability(),
        "source_metadata": _metadata(),
        "now": _CHECKED_AT + timedelta(minutes=5),
    }
    original = preflight.quote(
        capability_arguments=_arguments(scene="common"),
        maximum_amount_micros=20_000,
        **common,
    )
    changed_scene = preflight.quote(
        capability_arguments=_arguments(scene="ugc"),
        maximum_amount_micros=20_000,
        **common,
    )
    changed_cap = preflight.quote(
        capability_arguments=_arguments(scene="common"),
        maximum_amount_micros=30_000,
        **common,
    )

    assert original.fee_quote_sha256 != changed_scene.fee_quote_sha256
    assert original.fee_quote_sha256 != changed_cap.fee_quote_sha256


def test_preflight_requires_positive_video_metadata() -> None:
    audio_only = VideoMetadataObservation(
        format_meta=VideoFormatMetadata(
            container="m4a",
            duration=1,
            size=128,
        ),
        audio_stream_meta=AudioStreamMetadata(
            codec="aac",
            duration=1,
            channels=1,
            sample_rate=44_100,
        ),
    )
    with pytest.raises(ValueError, match="video stream metadata"):
        _preflight().quote(
            capability=_capability(),
            source_metadata=audio_only,
            capability_arguments=_arguments(),
            maximum_amount_micros=20_000,
            now=_CHECKED_AT + timedelta(minutes=5),
        )

    with pytest.raises(ValueError, match="positive source duration"):
        _preflight().quote(
            capability=_capability(),
            source_metadata=_metadata(duration=0),
            capability_arguments=_arguments(),
            maximum_amount_micros=20_000,
            now=_CHECKED_AT + timedelta(minutes=5),
        )
