from __future__ import annotations

from deerflow.agents.lead_agent.prompt import SYSTEM_PROMPT_TEMPLATE
from deerflow.tools.builtins.content_intelligence_tool import content_intelligence_tool
from deerflow.tools.tools import BUILTIN_TOOLS


def test_content_intelligence_tool_is_available_to_the_lead_by_default() -> None:
    assert content_intelligence_tool in BUILTIN_TOOLS
    assert content_intelligence_tool.name == "analyze_content_intelligence"


def test_tool_schema_exposes_one_optional_shared_analysis_request() -> None:
    schema = content_intelligence_tool.args_schema.model_json_schema()

    assert set(schema["properties"]) == {
        "user_request",
        "subject_expression",
        "focus",
        "source_materials",
    }
    assert "optional" in content_intelligence_tool.description.lower()
    assert "final" in content_intelligence_tool.description.lower()


def test_lead_prompt_uses_a_thin_content_incubation_contract() -> None:
    assert "content incubation and new-media operations agent" in SYSTEM_PROMPT_TEMPLATE
    assert "<content_intelligence>" in SYSTEM_PROMPT_TEMPLATE
    assert "analyze_content_intelligence" in SYSTEM_PROMPT_TEMPLATE
    assert "optional" in SYSTEM_PROMPT_TEMPLATE.lower()

    content_section = SYSTEM_PROMPT_TEMPLATE.split("<content_intelligence>", 1)[1].split("</content_intelligence>", 1)[0]
    assert "黄金礼品" not in content_section
    assert "海鲜" not in content_section
    assert "火锅底料" not in content_section
    assert "10 days" not in content_section
    assert "3 candidates" not in content_section


def test_clarification_is_not_a_mandatory_business_workflow_gate() -> None:
    assert "MANDATORY Clarification Scenarios" not in SYSTEM_PROMPT_TEMPLATE
    assert "Approach Choices" not in SYSTEM_PROMPT_TEMPLATE
    assert "If missing details do not prevent a useful response" in SYSTEM_PROMPT_TEMPLATE
