from __future__ import annotations

import importlib
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from langchain.tools import ToolRuntime
from langchain_core.messages import ToolMessage
from langgraph.types import Command

from deerflow.incubation import LogicalAccountRef, ProjectRef
from deerflow.tools.tools import BUILTIN_TOOLS

tool_module = importlib.import_module("deerflow.tools.builtins.account_launch_plan_tool")
plan_account_launch_tool = tool_module.plan_account_launch_tool
confirm_account_launch_plan_tool = tool_module.confirm_account_launch_plan_tool

PROJECT = ProjectRef(owner_user_id="user-1", project_id="golden-gift")
LOGICAL_ACCOUNT = LogicalAccountRef(
    owner_user_id="user-1",
    project_id="golden-gift",
    logical_account_id="account-golden-gift",
)


def _runtime() -> ToolRuntime:
    return ToolRuntime(
        state={},
        context={
            "thread_id": "thread-1",
            "run_id": "run-1",
            "user_id": "user-1",
            "incubation_project_id": PROJECT.project_id,
            "incubation_logical_account_id": LOGICAL_ACCOUNT.logical_account_id,
        },
        config={"configurable": {"thread_id": "thread-1"}},
        stream_writer=lambda _: None,
        tools=[],
        tool_call_id="launch-plan-call",
        store=None,
    )


def test_account_launch_plan_tools_are_optional_lead_capabilities() -> None:
    assert plan_account_launch_tool in BUILTIN_TOOLS
    assert plan_account_launch_tool.name == "plan_account_launch"
    assert plan_account_launch_tool.return_direct is True
    assert set(plan_account_launch_tool.tool_call_schema.model_json_schema()["properties"]) == {"planning_request"}

    assert confirm_account_launch_plan_tool in BUILTIN_TOOLS
    assert confirm_account_launch_plan_tool.name == "confirm_account_launch_plan"
    assert confirm_account_launch_plan_tool.return_direct is True
    assert confirm_account_launch_plan_tool.tool_call_schema.model_json_schema()["properties"] == {}


@pytest.mark.asyncio
async def test_plan_account_launch_uses_the_trusted_logical_account_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = SimpleNamespace(
        get_project=AsyncMock(return_value=object()),
        get_logical_account=AsyncMock(return_value=object()),
    )
    artifact = SimpleNamespace(
        artifact_type="account_launch_plan",
        artifact_id="artifact-launch-plan",
        content_sha256="a" * 64,
    )
    prepared = SimpleNamespace(plan=object(), plan_artifact=artifact, reused=False)
    prepare = AsyncMock(return_value=prepared)
    monkeypatch.setattr(tool_module, "get_incubation_repository", Mock(return_value=repository))
    monkeypatch.setattr(tool_module, "create_content_intelligence_model", Mock(return_value=object()))
    monkeypatch.setattr(tool_module, "prepare_account_launch_plan", prepare)
    monkeypatch.setattr(tool_module, "render_account_launch_plan", Mock(return_value="# 账号起号计划"))

    result = await plan_account_launch_tool.ainvoke(
        {
            "name": "plan_account_launch",
            "args": {
                "planning_request": "按当前路线给我一份7天和30天起号计划",
                "runtime": _runtime(),
            },
            "id": "launch-plan-call",
            "type": "tool_call",
        }
    )

    assert isinstance(result, Command)
    assert prepare.await_args.kwargs["project"] == PROJECT
    assert prepare.await_args.kwargs["logical_account"] == LOGICAL_ACCOUNT
    assert prepare.await_args.kwargs["planning_request"] == "按当前路线给我一份7天和30天起号计划"
    message = result.update["messages"][0]
    assert isinstance(message, ToolMessage)
    assert message.content == "# 账号起号计划"
    assert message.additional_kwargs["incubation_persistence"]["logical_account_id"] == LOGICAL_ACCOUNT.logical_account_id


@pytest.mark.asyncio
async def test_confirm_account_launch_plan_seals_only_the_current_logical_account(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = SimpleNamespace(
        get_project=AsyncMock(return_value=object()),
        get_logical_account=AsyncMock(return_value=object()),
    )
    artifact = SimpleNamespace(
        artifact_type="account_launch_plan",
        artifact_id="artifact-launch-plan-confirmed",
        content_sha256="b" * 64,
    )
    prepared = SimpleNamespace(plan=object(), plan_artifact=artifact, reused=False)
    confirm = AsyncMock(return_value=prepared)
    monkeypatch.setattr(tool_module, "get_incubation_repository", Mock(return_value=repository))
    monkeypatch.setattr(tool_module, "confirm_account_launch_plan", confirm)
    monkeypatch.setattr(tool_module, "render_account_launch_plan", Mock(return_value="# 已确认账号计划"))

    result = await confirm_account_launch_plan_tool.ainvoke(
        {
            "name": "confirm_account_launch_plan",
            "args": {"runtime": _runtime()},
            "id": "launch-plan-call",
            "type": "tool_call",
        }
    )

    assert isinstance(result, Command)
    assert confirm.await_args.kwargs["project"] == PROJECT
    assert confirm.await_args.kwargs["logical_account"] == LOGICAL_ACCOUNT
    message = result.update["messages"][0]
    assert isinstance(message, ToolMessage)
    assert message.content == "# 已确认账号计划"
    assert message.additional_kwargs["incubation_persistence"]["artifact_id"] == artifact.artifact_id
