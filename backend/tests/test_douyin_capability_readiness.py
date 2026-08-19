from __future__ import annotations

import json

import pytest

from deerflow.community.douyin_openapi.catalog import load_official_catalog
from deerflow.community.douyin_openapi.readiness import (
    build_capability_readiness,
    render_capability_readiness_markdown,
)


def _live_observation() -> dict[str, object]:
    return {
        "schema_version": 1,
        "observed_at": "2026-08-19T12:00:00+08:00",
        "application_type": "mobile_or_web",
        "configured_auth_modes": ["client_token"],
        "declared_scopes": ["aweme.dy.video_search_v2"],
        "official_mcp": {
            "initialized": True,
            "tested_tool_group_aids": [None, "28"],
            "tool_names": [],
        },
        "direct_receipts": [
            {
                "capability_id": "douyin.search.capability.aweme.dy.video.search",
                "state": "provider_denied",
                "provider_code": 28001018,
                "message": "应用未获得该能力",
            }
        ],
    }


def test_readiness_separates_catalog_adapter_configuration_and_live_access() -> None:
    report = build_capability_readiness(
        load_official_catalog(),
        _live_observation(),
    )

    assert report["summary"]["catalog_capabilities"] == 119
    assert report["summary"]["live_verified_capabilities"] == 0
    assert report["official_mcp"]["state"] == "connected_no_tools"

    rows = {row["capability_id"]: row for row in report["capabilities"]}
    video = rows["douyin.search.capability.aweme.dy.video.search"]
    assert video["integration_state"] == "provider_denied"
    assert video["adapter_state"] == "adapter_ready"
    assert video["authorization_mode"] == "client_token"
    assert video["provider_code"] == 28001018
    assert "平台" in video["next_action"]

    image_text = rows["douyin.search.capability.aweme.experience.search"]
    assert image_text["integration_state"] == "adapter_ready_permission_not_declared"
    assert image_text["adapter_state"] == "adapter_ready"

    own_fans = rows["account.management.fans.portrait.data.get.user.fans.data"]
    assert own_fans["authorization_mode"] == "user_oauth"
    assert own_fans["integration_state"] == "documented_not_integrated"


def test_readiness_does_not_treat_mcp_handshake_as_an_available_tool() -> None:
    report = build_capability_readiness(
        load_official_catalog(),
        _live_observation(),
    )

    assert report["official_mcp"] == {
        "initialized": True,
        "state": "connected_no_tools",
        "tested_tool_group_aids": [None, "28"],
        "tool_count": 0,
        "tool_names": [],
    }


def test_readiness_does_not_count_a_live_token_exchange_as_a_business_api() -> None:
    observation = _live_observation()
    observation["direct_receipts"] = [
        *observation["direct_receipts"],
        {
            "capability_id": "account.permission.client.token",
            "state": "live_verified",
            "provider_code": 0,
        },
    ]

    report = build_capability_readiness(load_official_catalog(), observation)
    rows = {row["capability_id"]: row for row in report["capabilities"]}

    assert report["summary"]["live_verified_capabilities"] == 1
    assert report["summary"]["live_verified_business_capabilities"] == 0
    assert rows["account.permission.client.token"]["adapter_state"] == "adapter_ready"
    assert rows["account.permission.client.token"]["integration_state"] == "live_verified"


def test_readiness_renderer_is_reproducible_complete_and_credential_free() -> None:
    report = build_capability_readiness(
        load_official_catalog(),
        _live_observation(),
    )
    rendered = render_capability_readiness_markdown(report)

    assert rendered.count("| [docs](https://") == 119
    assert "连接成功但无工具" in rendered
    assert "28001018" in rendered
    assert "DOUYIN_CLIENT_SECRET" not in rendered
    assert "private-client-token-value" not in rendered
    json.dumps(report, ensure_ascii=False)


def test_readiness_rejects_receipts_for_unknown_catalog_capabilities() -> None:
    observation = _live_observation()
    observation["direct_receipts"] = [
        {
            "capability_id": "not.in.the.official.catalog",
            "state": "live_verified",
        }
    ]

    with pytest.raises(ValueError, match="unknown capability"):
        build_capability_readiness(load_official_catalog(), observation)
