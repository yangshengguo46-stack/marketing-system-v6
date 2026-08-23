from __future__ import annotations

from hashlib import sha256

import pytest

from deerflow.agents.lead_agent.agent_core_contract import PRODUCTION_AGENT_KERNEL
from deerflow.agents.lead_agent.identity import (
    ProductIdentityError,
    build_product_identity_asset,
    load_product_identity_asset,
)


def test_default_product_identity_is_external_versioned_asset():
    asset = load_product_identity_asset()

    assert asset.source.endswith("/lead_agent/IDENTITY.md")
    assert asset.content == PRODUCTION_AGENT_KERNEL
    assert asset.sha256 == sha256(asset.content.encode("utf-8")).hexdigest()
    assert asset.version == f"sha256:{asset.sha256}"


def test_default_product_identity_preserves_the_reviewed_thin_kernel():
    asset = load_product_identity_asset()
    normalized = " ".join(asset.content.split())

    assert asset.content.count("<agent_kernel>") == 1
    assert asset.content.count("</agent_kernel>") == 1
    assert asset.content.count("{agent_name}") == 1
    assert "new-media incubation and operations employee" in normalized
    assert "inside the user's team" in normalized
    assert "no capability or workflow is mandatory" in normalized
    assert len(asset.content.encode("utf-8")) <= 1_600


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("", "empty"),
        ("<agent_kernel>missing close", "exactly one"),
        ("<agent_kernel>missing name</agent_kernel>", "agent_name"),
        (
            "<agent_kernel>{agent_name}</agent_kernel>\n<agent_kernel>{agent_name}</agent_kernel>",
            "exactly one",
        ),
    ],
)
def test_product_identity_validation_fails_closed(content: str, message: str):
    with pytest.raises(ProductIdentityError, match=message):
        build_product_identity_asset(content, source="test://identity")


def test_product_identity_normalizes_one_trailing_newline():
    asset = build_product_identity_asset(
        "<agent_kernel>\nYou are {agent_name}.\n</agent_kernel>\n\n\n",
        source="test://identity",
    )

    assert asset.content.endswith("</agent_kernel>\n")
    assert not asset.content.endswith("\n\n")
