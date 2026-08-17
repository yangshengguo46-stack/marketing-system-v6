from __future__ import annotations

from pathlib import Path

from deerflow.community.mediakit import (
    MediaKitCapabilityRouter,
    MediaKitEnhanceVideoQuoteService,
)
from deerflow.config.mediakit_config import MediaKitAppConfig
from deerflow.config.runtime_paths import project_root as runtime_project_root


def build_mediakit_quote_service(
    config: MediaKitAppConfig | None,
    *,
    project_root: Path | None = None,
) -> MediaKitEnhanceVideoQuoteService | None:
    """Build the read-only quote service; cloud execution remains unregistered."""
    if config is None or not config.quote_preparation_enabled:
        return None
    root = (project_root or runtime_project_root()).resolve()
    pricing_path = Path(config.pricing_evidence_path).expanduser()
    if not pricing_path.is_absolute():
        pricing_path = root / pricing_path
    return MediaKitEnhanceVideoQuoteService(
        capability_router=MediaKitCapabilityRouter(cli_path=config.cli_path),
        pricing_evidence_path=pricing_path,
        expected_schema_sha256=config.expected_schema_sha256,
        allowed_tool_versions=set(config.allowed_tool_versions),
        allowed_resolution_tiers=set(config.allowed_resolution_tiers),
        minimum_fps=config.minimum_fps,
        maximum_fps=config.maximum_fps,
        maximum_output_bytes=config.maximum_output_bytes,
    )


__all__ = ["build_mediakit_quote_service"]
