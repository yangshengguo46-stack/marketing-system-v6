from __future__ import annotations

import importlib
from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.types import Command

from deerflow.agents.lead_agent.prompt import SYSTEM_PROMPT_TEMPLATE
from deerflow.tools.builtins.content_intelligence_tool import content_intelligence_tool, explore_content_world_tool
from deerflow.tools.tools import BUILTIN_TOOLS

content_intelligence_tool_module = importlib.import_module("deerflow.tools.builtins.content_intelligence_tool")


def test_content_intelligence_tool_is_available_to_the_lead_by_default() -> None:
    assert content_intelligence_tool in BUILTIN_TOOLS
    assert explore_content_world_tool in BUILTIN_TOOLS
    assert content_intelligence_tool.name == "analyze_content_intelligence"
    assert explore_content_world_tool.name == "explore_content_world"
    assert explore_content_world_tool.return_direct is True


@pytest.mark.asyncio
async def test_content_world_tool_delivers_one_visible_terminal_ai_message(monkeypatch: pytest.MonkeyPatch) -> None:
    bundle = object()
    narration = object()
    monkeypatch.setattr(content_intelligence_tool_module, "_create_content_intelligence_model", lambda config: object())
    monkeypatch.setattr(
        content_intelligence_tool_module,
        "analyze_content_intelligence",
        AsyncMock(return_value=bundle),
    )
    monkeypatch.setattr(
        content_intelligence_tool_module,
        "synthesize_content_world_narration",
        AsyncMock(return_value=narration),
    )
    monkeypatch.setattr(
        content_intelligence_tool_module,
        "render_content_world_narration",
        lambda actual_bundle, actual_narration: "# 火锅\n\n围绕火锅本身展开内容世界。",
    )

    result = await explore_content_world_tool.ainvoke(
        {
            "name": "explore_content_world",
            "args": {
                "user_request": "我是卖重庆火锅底料的，该怎么起号？",
                "subject_expression": "重庆火锅底料",
            },
            "id": "content-world-call-1",
            "type": "tool_call",
        }
    )

    assert isinstance(result, Command)
    assert result.goto == ()
    assert isinstance(result.update, dict)
    messages = result.update["messages"]
    assert len(messages) == 1

    tool_message = messages[0]
    assert isinstance(tool_message, ToolMessage)
    assert tool_message.tool_call_id == "content-world-call-1"
    assert tool_message.additional_kwargs["hide_from_ui"] is True
    assert tool_message.additional_kwargs["deerflow_direct_response"] is True
    assert tool_message.content == "# 火锅\n\n围绕火锅本身展开内容世界。"
    assert not any(isinstance(message, AIMessage) for message in messages)


def test_content_world_tool_hides_injected_delivery_arguments_from_the_model() -> None:
    schema = explore_content_world_tool.tool_call_schema.model_json_schema()

    assert set(schema["properties"]) == {
        "user_request",
        "subject_expression",
        "source_materials",
    }


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
    focus_schema = schema["$defs"]["ToolAnalysisFocus"]
    assert focus_schema["enum"] == ["business_semantics", "topic_brief"]
    assert schema["properties"]["focus"]["default"] == "business_semantics"


def test_lead_prompt_uses_a_thin_content_incubation_contract() -> None:
    assert "content incubation and new-media operations agent" in SYSTEM_PROMPT_TEMPLATE
    assert "<content_intelligence>" in SYSTEM_PROMPT_TEMPLATE
    assert "analyze_content_intelligence" in SYSTEM_PROMPT_TEMPLATE
    assert "explore_content_world" in SYSTEM_PROMPT_TEMPLATE
    assert "optional" in SYSTEM_PROMPT_TEMPLATE.lower()

    content_section = SYSTEM_PROMPT_TEMPLATE.split("<content_intelligence>", 1)[1].split("</content_intelligence>", 1)[0]
    assert "黄金礼品" not in content_section
    assert "海鲜" not in content_section
    assert "火锅底料" not in content_section
    assert "10 days" not in content_section
    assert "3 candidates" not in content_section
    normalized_section = " ".join(content_section.split())
    assert "what the account should talk about before how to operate it" in normalized_section
    assert "posting cadence" in normalized_section
    assert "provisional rooted map is already a useful answer" in normalized_section
    assert "do not call `ask_clarification` in that turn" in normalized_section
    assert "content root is the entry into the map" in normalized_section
    assert "Treat the rooted content map as complete for the current question" in normalized_section
    assert "do not extend it into an unrequested downstream operating plan" in normalized_section
    assert "do not add an arbitrary number of posts, days, or branches" in normalized_section
    for attention_leak in (
        "return path",
        "product-return",
        "commercial return",
        "object anchor",
        "bridge path",
    ):
        assert attention_leak not in content_section.lower()


def test_clarification_is_not_a_mandatory_business_workflow_gate() -> None:
    assert "MANDATORY Clarification Scenarios" not in SYSTEM_PROMPT_TEMPLATE
    assert "Approach Choices" not in SYSTEM_PROMPT_TEMPLATE
    assert "If missing details do not prevent a useful response" in SYSTEM_PROMPT_TEMPLATE
    assert "ALWAYS clarify unclear/missing/ambiguous requirements" not in SYSTEM_PROMPT_TEMPLATE
    assert "Scope-Aligned" in SYSTEM_PROMPT_TEMPLATE
