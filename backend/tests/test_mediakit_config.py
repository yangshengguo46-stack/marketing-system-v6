from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from app.gateway.mediakit import build_mediakit_quote_service
from deerflow.community.mediakit import MediaKitEnhanceVideoQuoteService
from deerflow.config.app_config import AppConfig
from deerflow.config.mediakit_config import MediaKitAppConfig
from deerflow.config.sandbox_config import SandboxConfig

SCHEMA_SHA256 = "5573324d5727b5398b13ca89182a1e45c7953c9a8389bb12eec0b331eca46f00"


def test_mediakit_quote_preparation_is_disabled_by_default() -> None:
    config = AppConfig(sandbox=SandboxConfig(use="test"))

    assert config.mediakit.quote_preparation_enabled is False
    assert build_mediakit_quote_service(None, project_root=Path("/tmp/project")) is None
    assert build_mediakit_quote_service(config.mediakit, project_root=Path("/tmp/project")) is None


def test_config_example_documents_fail_closed_mediakit_quote_service() -> None:
    example_path = Path(__file__).resolve().parents[2] / "config.example.yaml"
    example = yaml.safe_load(example_path.read_text(encoding="utf-8"))

    assert example["mediakit"]["quote_preparation_enabled"] is False
    assert example["mediakit"]["expected_schema_sha256"] == SCHEMA_SHA256
    assert example["mediakit"]["allowed_tool_versions"] == ["standard"]
    assert example["mediakit"]["allowed_resolution_tiers"] == ["720p"]


def test_enabled_mediakit_quote_service_resolves_operator_pricing_file(tmp_path) -> None:
    config = MediaKitAppConfig(
        quote_preparation_enabled=True,
        cli_path="/usr/local/bin/mediakit-cli",
        pricing_evidence_path="private/mediakit-pricing.json",
        expected_schema_sha256=SCHEMA_SHA256,
        allowed_tool_versions={"standard"},
        allowed_resolution_tiers={"720p"},
        minimum_fps=15,
        maximum_fps=30,
        maximum_output_bytes=25 * 1024 * 1024,
    )

    service = build_mediakit_quote_service(config, project_root=tmp_path)

    assert isinstance(service, MediaKitEnhanceVideoQuoteService)
    assert service.pricing_evidence_path == (tmp_path / "private/mediakit-pricing.json").resolve()


@pytest.mark.parametrize(
    "changes",
    [
        {"expected_schema_sha256": "not-a-digest"},
        {"allowed_tool_versions": set()},
        {"allowed_resolution_tiers": {"4k"}},
        {"minimum_fps": 31, "maximum_fps": 30},
        {"pricing_evidence_path": ""},
    ],
)
def test_mediakit_quote_config_rejects_unsafe_or_unreviewed_policy(changes) -> None:
    values = {
        "quote_preparation_enabled": True,
        "expected_schema_sha256": SCHEMA_SHA256,
        **changes,
    }
    with pytest.raises(ValidationError):
        MediaKitAppConfig(**values)
