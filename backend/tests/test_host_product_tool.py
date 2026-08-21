from __future__ import annotations

import json

from deerflow.tools.builtins.host_product_tool import inspect_agent_product_profile_tool
from deerflow.tools.tools import BUILTIN_TOOLS


def test_agent_product_profile_is_an_optional_read_only_lead_capability() -> None:
    assert inspect_agent_product_profile_tool in BUILTIN_TOOLS
    assert inspect_agent_product_profile_tool.name == "inspect_agent_product_profile"
    assert inspect_agent_product_profile_tool.return_direct is False
    assert inspect_agent_product_profile_tool.tool_call_schema.model_json_schema()["properties"] == {}


def test_agent_product_profile_returns_versioned_facts_and_boundaries() -> None:
    payload = json.loads(inspect_agent_product_profile_tool.invoke({}))

    assert payload["subject_expression"] == "DeerFlow 内容孵化与新媒体运营 Agent"
    assert payload["profile_version"] >= 1
    assert payload["business_facts"]
    assert payload["capabilities"]
    assert payload["constraints"]
    assert any("不能保证" in item for item in payload["constraints"])
