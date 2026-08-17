from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_CEILING, Decimal
from typing import Any
from urllib.parse import urlparse

from jsonschema import Draft202012Validator

from deerflow.incubation.media import VideoMetadataObservation

from .contracts import MediaKitCapability, MediaKitCloudOutputPolicy
from .router import MediaKitCommandError

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_RESOLUTION_TIERS = ("720p", "1080p", "2k", "4k")
_RESOLUTION_NAMES = {
    "240p": "720p",
    "360p": "720p",
    "480p": "720p",
    "540p": "720p",
    "720p": "720p",
    "1080p": "1080p",
    "2k": "2k",
    "4k": "4k",
}
_SAFE_ARGUMENTS = frozenset(
    {
        "bitrate_level",
        "fps",
        "resolution",
        "resolution_limit",
        "scene",
        "tool_version",
    }
)


def _bounded_text(value: str, *, name: str, maximum: int) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string")
    normalized = value.strip()
    if not normalized or len(normalized) > maximum:
        raise ValueError(f"{name} must contain between 1 and {maximum} characters")
    return normalized


def _sha256(value: str, *, name: str) -> str:
    normalized = _bounded_text(value, name=name, maximum=64)
    if not _SHA256.fullmatch(normalized):
        raise ValueError(f"{name} must be a SHA-256 digest")
    return normalized


def _utc(value: datetime, *, name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value.astimezone(UTC)


def _canonical_sha256(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class MediaKitPricingRate:
    tool_version: str
    resolution_tier: str
    maximum_fps: float
    amount_micros_per_minute: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "tool_version",
            _bounded_text(self.tool_version, name="tool_version", maximum=64),
        )
        resolution_tier = _bounded_text(
            self.resolution_tier,
            name="resolution_tier",
            maximum=16,
        ).casefold()
        if resolution_tier not in _RESOLUTION_TIERS:
            raise ValueError("resolution_tier is unsupported")
        object.__setattr__(self, "resolution_tier", resolution_tier)
        if isinstance(self.maximum_fps, bool) or not isinstance(self.maximum_fps, (int, float)):
            raise ValueError("maximum_fps must be numeric")
        maximum_fps = float(self.maximum_fps)
        if not math.isfinite(maximum_fps) or maximum_fps <= 0:
            raise ValueError("maximum_fps must be positive and finite")
        object.__setattr__(self, "maximum_fps", maximum_fps)
        if not isinstance(self.amount_micros_per_minute, int) or isinstance(self.amount_micros_per_minute, bool) or self.amount_micros_per_minute <= 0:
            raise ValueError("amount_micros_per_minute must be a positive integer")

    def as_evidence(self) -> dict[str, object]:
        return {
            "tool_version": self.tool_version,
            "resolution_tier": self.resolution_tier,
            "maximum_fps": self.maximum_fps,
            "amount_micros_per_minute": self.amount_micros_per_minute,
        }


@dataclass(frozen=True, slots=True)
class MediaKitPricingEvidence:
    provider: str
    capability_domain: str
    capability_tool: str
    currency: str
    source_url: str
    document_id: str
    document_sha256: str
    document_updated_at: datetime
    checked_at: datetime
    valid_until: datetime
    provider_hard_cap_supported: bool
    rates: tuple[MediaKitPricingRate, ...]

    def __post_init__(self) -> None:
        for name, maximum in (
            ("provider", 128),
            ("capability_domain", 64),
            ("capability_tool", 64),
            ("document_id", 128),
        ):
            object.__setattr__(
                self,
                name,
                _bounded_text(getattr(self, name), name=name, maximum=maximum),
            )
        currency = _bounded_text(self.currency, name="currency", maximum=3).upper()
        if len(currency) != 3 or not currency.isalpha():
            raise ValueError("currency must be a three-letter code")
        object.__setattr__(self, "currency", currency)
        source_url = _bounded_text(self.source_url, name="source_url", maximum=2048)
        parsed = urlparse(source_url)
        if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password or parsed.fragment:
            raise ValueError("source_url must be a public HTTPS document URL")
        object.__setattr__(self, "source_url", source_url)
        object.__setattr__(
            self,
            "document_sha256",
            _sha256(self.document_sha256, name="document_sha256"),
        )
        for name in ("document_updated_at", "checked_at", "valid_until"):
            object.__setattr__(self, name, _utc(getattr(self, name), name=name))
        if self.document_updated_at > self.checked_at:
            raise ValueError("pricing document cannot be newer than its check")
        if self.valid_until <= self.checked_at:
            raise ValueError("pricing evidence validity must end after its check")
        if not isinstance(self.provider_hard_cap_supported, bool):
            raise ValueError("provider_hard_cap_supported must be boolean")
        rates = tuple(self.rates)
        if not rates or any(not isinstance(rate, MediaKitPricingRate) for rate in rates):
            raise ValueError("pricing evidence requires typed rates")
        keys = [(rate.tool_version, rate.resolution_tier, rate.maximum_fps) for rate in rates]
        if len(keys) != len(set(keys)):
            raise ValueError("pricing rates must be unique")
        object.__setattr__(self, "rates", rates)

    @property
    def evidence_sha256(self) -> str:
        rates = sorted(
            (rate.as_evidence() for rate in self.rates),
            key=lambda rate: (
                str(rate["tool_version"]),
                _RESOLUTION_TIERS.index(str(rate["resolution_tier"])),
                float(rate["maximum_fps"]),
            ),
        )
        return _canonical_sha256(
            {
                "contract_version": "mediakit-pricing-evidence-v1",
                "provider": self.provider,
                "capability_domain": self.capability_domain,
                "capability_tool": self.capability_tool,
                "currency": self.currency,
                "source_url": self.source_url,
                "document_id": self.document_id,
                "document_sha256": self.document_sha256,
                "document_updated_at": self.document_updated_at.isoformat(),
                "checked_at": self.checked_at.isoformat(),
                "valid_until": self.valid_until.isoformat(),
                "provider_hard_cap_supported": self.provider_hard_cap_supported,
                "rates": rates,
            }
        )

    def rate_for(
        self,
        *,
        tool_version: str,
        resolution_tier: str,
        output_fps: float,
    ) -> MediaKitPricingRate:
        matches = sorted(
            (rate for rate in self.rates if rate.tool_version == tool_version and rate.resolution_tier == resolution_tier and output_fps <= rate.maximum_fps),
            key=lambda rate: rate.maximum_fps,
        )
        if not matches:
            raise ValueError("pricing evidence does not cover the requested output")
        return matches[0]


@dataclass(frozen=True, slots=True)
class MediaKitFeeQuote:
    capability_schema_sha256: str
    pricing_evidence_sha256: str
    capability_arguments_sha256: str
    source_duration_milliseconds: int
    output_resolution_tier: str
    output_fps: float
    tool_version: str
    currency: str
    amount_micros_per_minute: int
    estimated_amount_micros: int
    maximum_amount_micros: int
    provider_hard_cap_supported: bool
    valid_until: datetime
    output_policy: MediaKitCloudOutputPolicy

    @property
    def fee_quote_sha256(self) -> str:
        return _canonical_sha256(
            {
                "contract_version": "mediakit-fee-quote-v1",
                "capability_schema_sha256": self.capability_schema_sha256,
                "pricing_evidence_sha256": self.pricing_evidence_sha256,
                "capability_arguments_sha256": self.capability_arguments_sha256,
                "source_duration_milliseconds": self.source_duration_milliseconds,
                "output_resolution_tier": self.output_resolution_tier,
                "output_fps": self.output_fps,
                "tool_version": self.tool_version,
                "currency": self.currency,
                "amount_micros_per_minute": self.amount_micros_per_minute,
                "estimated_amount_micros": self.estimated_amount_micros,
                "maximum_amount_micros": self.maximum_amount_micros,
                "provider_hard_cap_supported": self.provider_hard_cap_supported,
                "valid_until": self.valid_until.isoformat(),
                "output_policy": {
                    "capability_domain": self.output_policy.capability_domain,
                    "capability_tool": self.output_policy.capability_tool,
                    "url_field": self.output_policy.url_field,
                    "media_kind": self.output_policy.media_kind,
                    "maximum_bytes": self.output_policy.maximum_bytes,
                },
            }
        )

    def as_operation_fields(self) -> dict[str, object]:
        """Project the quote fields that must survive durable task recovery."""

        return {
            "pricing_evidence_sha256": self.pricing_evidence_sha256,
            "fee_quote_sha256": self.fee_quote_sha256,
            "estimated_amount_micros": self.estimated_amount_micros,
            "fee_quote_valid_until": self.valid_until.isoformat(),
        }


class MediaKitEnhanceVideoPreflight:
    """Quote one reviewed enhance-video request without calling the provider."""

    def __init__(
        self,
        *,
        expected_schema_sha256: str,
        pricing: MediaKitPricingEvidence,
        allowed_tool_versions: Collection[str],
        allowed_resolution_tiers: Collection[str],
        minimum_fps: float,
        maximum_fps: float,
        maximum_output_bytes: int,
    ) -> None:
        self._expected_schema_sha256 = _sha256(
            expected_schema_sha256,
            name="expected_schema_sha256",
        )
        if not isinstance(pricing, MediaKitPricingEvidence):
            raise ValueError("pricing must be typed evidence")
        if (pricing.capability_domain, pricing.capability_tool) != (
            "video",
            "enhance-video",
        ):
            raise ValueError("pricing evidence belongs to another capability")
        self._pricing = pricing
        self._allowed_tool_versions = frozenset(_bounded_text(value, name="allowed tool version", maximum=64) for value in allowed_tool_versions)
        self._allowed_resolution_tiers = frozenset(_bounded_text(value, name="allowed resolution tier", maximum=16).casefold() for value in allowed_resolution_tiers)
        if not self._allowed_tool_versions:
            raise ValueError("at least one tool version must be enabled")
        if not self._allowed_resolution_tiers or not self._allowed_resolution_tiers <= set(_RESOLUTION_TIERS):
            raise ValueError("allowed resolution tiers are invalid")
        if isinstance(minimum_fps, bool) or isinstance(maximum_fps, bool) or not isinstance(minimum_fps, (int, float)) or not isinstance(maximum_fps, (int, float)):
            raise ValueError("fps bounds must be numeric")
        self._minimum_fps = float(minimum_fps)
        self._maximum_fps = float(maximum_fps)
        if not math.isfinite(self._minimum_fps) or not math.isfinite(self._maximum_fps) or self._minimum_fps <= 0 or self._maximum_fps < self._minimum_fps:
            raise ValueError("fps bounds are invalid")
        self._output_policy = MediaKitCloudOutputPolicy(
            capability_domain="video",
            capability_tool="enhance-video",
            url_field="video_url",
            media_kind="video",
            maximum_bytes=maximum_output_bytes,
        )

    @staticmethod
    def _validate_capability(capability: MediaKitCapability) -> None:
        if (capability.domain, capability.tool) != ("video", "enhance-video"):
            raise MediaKitCommandError("MediaKit enhance-video capability is unavailable")
        input_properties = capability.input_schema.get("properties")
        if not isinstance(input_properties, Mapping) or not {
            "video_url",
            "tool_version",
            "resolution",
            "resolution_limit",
            "fps",
        } <= set(input_properties):
            raise MediaKitCommandError("MediaKit enhance-video input contract is incomplete")
        final_result = capability.output_schema.get("final_result")
        final_properties = final_result.get("properties") if isinstance(final_result, Mapping) else None
        if not isinstance(final_properties, Mapping) or not {
            "video_url",
            "duration",
            "resolution",
        } <= set(final_properties):
            raise MediaKitCommandError("MediaKit enhance-video terminal output contract is incomplete")

    @staticmethod
    def _resolution_tier(arguments: Mapping[str, Any]) -> str:
        resolution = arguments.get("resolution")
        resolution_limit = arguments.get("resolution_limit")
        if resolution is None and resolution_limit is None:
            raise ValueError("MediaKit enhance-video requires explicit output resolution")
        if resolution is not None and resolution_limit is not None:
            raise ValueError("MediaKit enhance-video output resolution controls are mutually exclusive")
        if resolution is not None:
            if not isinstance(resolution, str) or resolution.casefold() not in _RESOLUTION_NAMES:
                raise ValueError("MediaKit enhance-video output resolution is unsupported")
            return _RESOLUTION_NAMES[resolution.casefold()]
        if not isinstance(resolution_limit, int) or isinstance(resolution_limit, bool) or not 64 <= resolution_limit <= 2160:
            raise ValueError("MediaKit enhance-video resolution_limit is invalid")
        if resolution_limit <= 720:
            return "720p"
        if resolution_limit <= 1080:
            return "1080p"
        if resolution_limit <= 1440:
            return "2k"
        return "4k"

    def quote(
        self,
        *,
        capability: MediaKitCapability,
        source_metadata: VideoMetadataObservation,
        capability_arguments: Mapping[str, Any],
        maximum_amount_micros: int,
        now: datetime,
    ) -> MediaKitFeeQuote:
        if not isinstance(capability, MediaKitCapability):
            raise ValueError("capability must be a discovered MediaKit capability")
        self._validate_capability(capability)
        if capability.schema_sha256 != self._expected_schema_sha256:
            raise MediaKitCommandError("MediaKit capability schema changed")
        checked_now = _utc(now, name="now")
        if checked_now < self._pricing.checked_at:
            raise PermissionError("MediaKit pricing evidence is not yet valid")
        if checked_now >= self._pricing.valid_until:
            raise PermissionError("MediaKit pricing evidence expired")
        if not isinstance(source_metadata, VideoMetadataObservation) or source_metadata.video_stream_meta is None:
            raise ValueError("MediaKit enhance-video requires video stream metadata")
        source_duration = Decimal(str(source_metadata.format_meta.duration))
        if not source_duration.is_finite() or source_duration <= 0:
            raise ValueError("MediaKit enhance-video requires positive source duration")

        arguments = dict(capability_arguments)
        if "callback_args" in arguments:
            raise ValueError("MediaKit enhance-video callback arguments are not allowed")
        unsupported = set(arguments) - _SAFE_ARGUMENTS
        if unsupported:
            raise ValueError("MediaKit enhance-video arguments are not enabled")
        tool_version = arguments.get("tool_version")
        if not isinstance(tool_version, str) or not tool_version.strip():
            raise ValueError("MediaKit enhance-video requires explicit tool version")
        tool_version = tool_version.strip()
        if tool_version not in self._allowed_tool_versions:
            raise ValueError("MediaKit enhance-video tool version is not enabled")
        resolution_tier = self._resolution_tier(arguments)
        if resolution_tier not in self._allowed_resolution_tiers:
            raise ValueError("MediaKit enhance-video resolution tier is not enabled")
        if "fps" not in arguments:
            raise ValueError("MediaKit enhance-video requires explicit output fps")
        output_fps = arguments["fps"]
        if isinstance(output_fps, bool) or not isinstance(output_fps, (int, float)):
            raise ValueError("MediaKit enhance-video output fps must be numeric")
        output_fps = float(output_fps)
        if not math.isfinite(output_fps) or not self._minimum_fps <= output_fps <= self._maximum_fps:
            raise ValueError("MediaKit enhance-video output fps is outside the enabled range")

        input_payload = {"video_url": "https://media.invalid/source.mp4", **arguments}
        errors = sorted(
            Draft202012Validator(capability.input_schema).iter_errors(input_payload),
            key=lambda error: list(error.absolute_path),
        )
        if errors:
            raise ValueError("MediaKit enhance-video arguments do not match the discovered schema")
        rate = self._pricing.rate_for(
            tool_version=tool_version,
            resolution_tier=resolution_tier,
            output_fps=output_fps,
        )
        source_duration_milliseconds = int((source_duration * Decimal(1000)).to_integral_value(rounding=ROUND_CEILING))
        estimated_amount_micros = (source_duration_milliseconds * rate.amount_micros_per_minute + 60_000 - 1) // 60_000
        if not isinstance(maximum_amount_micros, int) or isinstance(maximum_amount_micros, bool) or maximum_amount_micros <= 0:
            raise ValueError("maximum_amount_micros must be a positive integer")
        if maximum_amount_micros < estimated_amount_micros:
            raise PermissionError("MediaKit fee authorization is below the deterministic estimate")

        return MediaKitFeeQuote(
            capability_schema_sha256=capability.schema_sha256,
            pricing_evidence_sha256=self._pricing.evidence_sha256,
            capability_arguments_sha256=_canonical_sha256(arguments),
            source_duration_milliseconds=source_duration_milliseconds,
            output_resolution_tier=resolution_tier,
            output_fps=output_fps,
            tool_version=tool_version,
            currency=self._pricing.currency,
            amount_micros_per_minute=rate.amount_micros_per_minute,
            estimated_amount_micros=estimated_amount_micros,
            maximum_amount_micros=maximum_amount_micros,
            provider_hard_cap_supported=self._pricing.provider_hard_cap_supported,
            valid_until=self._pricing.valid_until,
            output_policy=self._output_policy,
        )


__all__ = [
    "MediaKitEnhanceVideoPreflight",
    "MediaKitFeeQuote",
    "MediaKitPricingEvidence",
    "MediaKitPricingRate",
]
