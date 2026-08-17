from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

_ENHANCE_VIDEO_SCHEMA_SHA256 = "5573324d5727b5398b13ca89182a1e45c7953c9a8389bb12eec0b331eca46f00"


class MediaKitAppConfig(BaseModel):
    """Fail-closed configuration for server-generated MediaKit quotes."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    quote_preparation_enabled: bool = False
    cli_path: str = Field(default="mediakit-cli", min_length=1, max_length=4096)
    pricing_evidence_path: str = Field(
        default=".deer-flow/mediakit/enhance-video-pricing.json",
        min_length=1,
        max_length=4096,
    )
    expected_schema_sha256: str = Field(
        default=_ENHANCE_VIDEO_SCHEMA_SHA256,
        pattern=r"^[0-9a-f]{64}$",
    )
    allowed_tool_versions: set[Literal["standard"]] = Field(
        default_factory=lambda: {"standard"},
        min_length=1,
    )
    allowed_resolution_tiers: set[Literal["720p"]] = Field(
        default_factory=lambda: {"720p"},
        min_length=1,
    )
    minimum_fps: float = Field(default=15, gt=0, le=30)
    maximum_fps: float = Field(default=30, gt=0, le=30)
    maximum_output_bytes: int = Field(default=25 * 1024 * 1024, gt=0, le=100 * 1024 * 1024 * 1024)

    @model_validator(mode="after")
    def validate_fps_window(self) -> MediaKitAppConfig:
        if self.maximum_fps < self.minimum_fps:
            raise ValueError("MediaKit maximum_fps must be at least minimum_fps")
        return self


__all__ = ["MediaKitAppConfig"]
