from __future__ import annotations

import importlib
import json

import pytest
from langchain.tools import ToolRuntime
from langchain_core.messages import HumanMessage, ToolMessage
from langgraph.types import Command

from deerflow.agents.user_profile import FileUserProfileStore
from deerflow.config.paths import Paths
from deerflow.tools.builtins.user_profile_tool import manage_user_profile_tool
from deerflow.tools.tools import BUILTIN_TOOLS, get_available_tools

tool_module = importlib.import_module("deerflow.tools.builtins.user_profile_tool")


def _runtime(messages: list[HumanMessage]) -> ToolRuntime:
    return ToolRuntime(
        state={"messages": messages},
        context={"thread_id": "thread-1", "run_id": "run-1", "user_id": "user-1"},
        config={"configurable": {"thread_id": "thread-1"}},
        stream_writer=lambda _: None,
        tools=[],
        tool_call_id="profile-call",
        store=None,
    )


def _tool_message(command: Command) -> ToolMessage:
    messages = command.update["messages"]
    assert len(messages) == 1
    message = messages[0]
    assert isinstance(message, ToolMessage)
    return message


def test_profile_tool_is_a_lead_capability_with_a_narrow_schema(monkeypatch) -> None:
    assert manage_user_profile_tool in BUILTIN_TOOLS
    schema = manage_user_profile_tool.tool_call_schema.model_json_schema()
    assert set(schema["properties"]) == {"action", "user_statement", "kind", "item_id"}
    description = " ".join((manage_user_profile_tool.description or "").split())
    assert "exact excerpt" in description
    assert "Never store project" in description

    monkeypatch.setattr("deerflow.tools.tools.BUILTIN_TOOLS", [manage_user_profile_tool])
    assert manage_user_profile_tool not in get_available_tools(
        include_mcp=False,
        include_user_profile_tool=False,
    )


@pytest.mark.asyncio
async def test_tool_remembers_only_an_exact_excerpt_from_the_latest_visible_user_message(tmp_path, monkeypatch) -> None:
    store = FileUserProfileStore(Paths(tmp_path))
    monkeypatch.setattr(tool_module, "get_user_profile_store", lambda: store)
    runtime = _runtime(
        [
            HumanMessage(content="请记住，我不懂代码，跟我讲人话。", id="user-message-1"),
            HumanMessage(content="隐藏上下文", additional_kwargs={"hide_from_ui": True}),
        ]
    )

    command = await manage_user_profile_tool.ainvoke(
        {
            "name": "manage_user_profile",
            "args": {
                "action": "remember",
                "user_statement": "我不懂代码",
                "kind": "background",
                "item_id": None,
                "runtime": runtime,
            },
            "id": "profile-call",
            "type": "tool_call",
        }
    )

    assert isinstance(command, Command)
    payload = json.loads(_tool_message(command).content)
    assert payload["status"] == "updated"
    revision = store.load("user-1")
    assert revision is not None
    assert revision.items[0].statement == "我不懂代码"
    assert revision.items[0].source.message_id == "user-message-1"


@pytest.mark.asyncio
async def test_tool_rejects_model_inference_and_does_not_create_a_profile(tmp_path, monkeypatch) -> None:
    store = FileUserProfileStore(Paths(tmp_path))
    monkeypatch.setattr(tool_module, "get_user_profile_store", lambda: store)
    runtime = _runtime([HumanMessage(content="我是做黄金礼品的", id="user-message-1")])

    command = await manage_user_profile_tool.ainvoke(
        {
            "name": "manage_user_profile",
            "args": {
                "action": "remember",
                "user_statement": "用户不懂代码",
                "kind": "background",
                "item_id": None,
                "runtime": runtime,
            },
            "id": "profile-call",
            "type": "tool_call",
        }
    )

    assert isinstance(command, Command)
    assert "exact excerpt" in _tool_message(command).content
    assert store.load("user-1") is None
