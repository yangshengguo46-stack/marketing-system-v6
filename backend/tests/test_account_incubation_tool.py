from __future__ import annotations

import importlib
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from langchain.tools import ToolRuntime
from langchain_core.messages import ToolMessage
from langgraph.types import Command

from deerflow.incubation import implicit_thread_project_ref
from deerflow.tools.builtins.account_incubation_tool import (
    confirm_account_strategy_tool,
    develop_account_strategy_tool,
)
from deerflow.tools.tools import BUILTIN_TOOLS

tool_module = importlib.import_module("deerflow.tools.builtins.account_incubation_tool")


def _runtime(*, project_id: str | None) -> ToolRuntime:
    context = {
        "thread_id": "thread-1",
        "run_id": "run-1",
        "user_id": "user-1",
    }
    if project_id is not None:
        context["incubation_project_id"] = project_id
    return ToolRuntime(
        state={},
        context=context,
        config={"configurable": {"thread_id": "thread-1"}},
        stream_writer=lambda _: None,
        tools=[],
        tool_call_id="account-strategy-call",
        store=None,
    )


def test_account_strategy_tool_is_a_separate_lead_capability() -> None:
    assert develop_account_strategy_tool in BUILTIN_TOOLS
    assert develop_account_strategy_tool.name == "develop_account_strategy"
    assert develop_account_strategy_tool.return_direct is True
    schema = develop_account_strategy_tool.tool_call_schema.model_json_schema()
    assert set(schema["properties"]) == {"user_request"}
    assert confirm_account_strategy_tool in BUILTIN_TOOLS
    assert confirm_account_strategy_tool.name == "confirm_account_strategy"
    assert confirm_account_strategy_tool.return_direct is True
    confirm_schema = confirm_account_strategy_tool.tool_call_schema.model_json_schema()
    assert set(confirm_schema["properties"]) == {"option_id"}


@pytest.mark.asyncio
async def test_account_strategy_tool_bootstraps_a_thread_project_before_model_work(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = SimpleNamespace(
        get_project=AsyncMock(return_value=None),
        create_project=AsyncMock(return_value=object()),
    )
    bundle = object()
    artifact = SimpleNamespace(
        artifact_type="incubation_judgment",
        artifact_id="artifact-strategy-bootstrap",
        content_sha256="c" * 64,
    )
    prepared = SimpleNamespace(
        judgment=object(),
        judgment_artifact=artifact,
        reused=False,
    )
    create_model = Mock(return_value=object())
    monkeypatch.setattr(tool_module, "get_incubation_repository", Mock(return_value=repository))
    monkeypatch.setattr(tool_module, "create_content_intelligence_model", create_model)
    monkeypatch.setattr(tool_module, "create_lexical_evidence_provider", Mock(return_value=None))
    analysis = AsyncMock(return_value=bundle)
    monkeypatch.setattr(tool_module, "analyze_content_intelligence", analysis)
    prepare = AsyncMock(return_value=prepared)
    monkeypatch.setattr(tool_module, "prepare_account_strategy", prepare)
    monkeypatch.setattr(tool_module, "render_account_strategy", Mock(return_value="# 账号路线候选"))

    result = await develop_account_strategy_tool.ainvoke(
        {
            "name": "develop_account_strategy",
            "args": {
                "user_request": "我是开水果店的，我要怎么起号",
                "runtime": _runtime(project_id=None),
            },
            "id": "account-strategy-call",
            "type": "tool_call",
        }
    )

    assert isinstance(result, Command)
    expected_project = implicit_thread_project_ref(owner_user_id="user-1", thread_id="thread-1")
    assert repository.create_project.await_args.args == (expected_project,)
    assert repository.create_project.await_args.kwargs["display_name"] == "我是开水果店的，我要怎么起号"
    assert prepare.await_args.kwargs["project"] == expected_project
    assert prepare.await_args.kwargs["bundle"] is bundle
    message = result.update["messages"][0]
    assert isinstance(message, ToolMessage)
    assert message.content == "# 账号路线候选"
    assert message.additional_kwargs["incubation_persistence"]["project_id"] == expected_project.project_id
    create_model.assert_called_once()
    analysis.assert_awaited_once()


@pytest.mark.asyncio
async def test_account_strategy_tool_redacts_implicit_project_bootstrap_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = SimpleNamespace(get_project=AsyncMock(side_effect=RuntimeError("database-secret")))
    create_model = Mock()
    monkeypatch.setattr(tool_module, "get_incubation_repository", Mock(return_value=repository))
    monkeypatch.setattr(tool_module, "create_content_intelligence_model", create_model)

    result = await develop_account_strategy_tool.ainvoke(
        {
            "name": "develop_account_strategy",
            "args": {
                "user_request": "我是开水果店的，我要怎么起号",
                "runtime": _runtime(project_id=None),
            },
            "id": "account-strategy-call",
            "type": "tool_call",
        }
    )

    assert isinstance(result, Command)
    message = result.update["messages"][0]
    assert isinstance(message, ToolMessage)
    assert message.content == "账号孵化台账暂时不可用，因此没有生成无法延续的临时定位。"
    assert "database-secret" not in message.content
    create_model.assert_not_called()


@pytest.mark.asyncio
async def test_account_strategy_tool_routes_candidate_map_and_project_evidence_to_strategy_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = SimpleNamespace(get_project=AsyncMock(return_value=object()))
    bundle = object()
    judgment = object()
    artifact = SimpleNamespace(
        artifact_type="incubation_judgment",
        artifact_id="artifact-strategy-1",
        content_sha256="a" * 64,
    )
    prepared = SimpleNamespace(
        judgment=judgment,
        judgment_artifact=artifact,
        reused=False,
    )
    monkeypatch.setattr(tool_module, "get_incubation_repository", Mock(return_value=repository))
    monkeypatch.setattr(tool_module, "create_content_intelligence_model", Mock(return_value=object()))
    monkeypatch.setattr(tool_module, "create_lexical_evidence_provider", Mock(return_value=None))
    analysis = AsyncMock(return_value=bundle)
    monkeypatch.setattr(tool_module, "analyze_content_intelligence", analysis)
    prepare = AsyncMock(return_value=prepared)
    monkeypatch.setattr(tool_module, "prepare_account_strategy", prepare)
    monkeypatch.setattr(tool_module, "render_account_strategy", Mock(return_value="# 账号路线候选\n\n**提案版本：** v1"))

    result = await develop_account_strategy_tool.ainvoke(
        {
            "name": "develop_account_strategy",
            "args": {
                "user_request": "我是做黄金礼品的，我要怎么起号？",
                "runtime": _runtime(project_id="golden-gift"),
            },
            "id": "account-strategy-call",
            "type": "tool_call",
        }
    )

    assert analysis.await_args.args[0].focus == "content_world"
    assert prepare.await_args.kwargs["bundle"] is bundle
    assert prepare.await_args.kwargs["verbatim_user_request"] == "我是做黄金礼品的，我要怎么起号？"
    message = result.update["messages"][0]
    assert message.content.startswith("# 账号路线候选")
    assert message.additional_kwargs["incubation_persistence"]["artifact_id"] == "artifact-strategy-1"


@pytest.mark.asyncio
async def test_account_strategy_confirmation_does_not_require_a_platform_account(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = SimpleNamespace(get_project=AsyncMock(return_value=object()))
    judgment = object()
    artifact = SimpleNamespace(
        artifact_type="incubation_judgment",
        artifact_id="artifact-strategy-2",
        content_sha256="b" * 64,
    )
    confirmed = SimpleNamespace(
        judgment=judgment,
        judgment_artifact=artifact,
        reused=False,
    )
    monkeypatch.setattr(tool_module, "get_incubation_repository", Mock(return_value=repository))
    confirm = AsyncMock(return_value=confirmed)
    monkeypatch.setattr(tool_module, "confirm_account_strategy", confirm)
    monkeypatch.setattr(tool_module, "render_account_strategy", Mock(return_value="# 已确认的账号路线"))

    result = await confirm_account_strategy_tool.ainvoke(
        {
            "name": "confirm_account_strategy",
            "args": {
                "option_id": "route_b",
                "runtime": _runtime(project_id="golden-gift"),
            },
            "id": "account-strategy-call",
            "type": "tool_call",
        }
    )

    assert confirm.await_args.kwargs["option_id"] == "route_b"
    assert "account" not in confirm.await_args.kwargs
    message = result.update["messages"][0]
    assert message.name == "confirm_account_strategy"
    assert "已经由你确认" in message.content


@pytest.mark.asyncio
async def test_account_strategy_confirmation_reuses_the_implicit_thread_project(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = SimpleNamespace(get_project=AsyncMock(return_value=object()))
    artifact = SimpleNamespace(
        artifact_type="incubation_judgment",
        artifact_id="artifact-strategy-implicit-confirmed",
        content_sha256="d" * 64,
    )
    confirmed = SimpleNamespace(
        judgment=object(),
        judgment_artifact=artifact,
        reused=False,
    )
    monkeypatch.setattr(tool_module, "get_incubation_repository", Mock(return_value=repository))
    confirm = AsyncMock(return_value=confirmed)
    monkeypatch.setattr(tool_module, "confirm_account_strategy", confirm)
    monkeypatch.setattr(tool_module, "render_account_strategy", Mock(return_value="# 已确认的账号路线"))

    result = await confirm_account_strategy_tool.ainvoke(
        {
            "name": "confirm_account_strategy",
            "args": {
                "option_id": "route_a",
                "runtime": _runtime(project_id=None),
            },
            "id": "account-strategy-call",
            "type": "tool_call",
        }
    )

    expected_project = implicit_thread_project_ref(owner_user_id="user-1", thread_id="thread-1")
    repository.get_project.assert_awaited_once_with(expected_project)
    assert confirm.await_args.kwargs["project"] == expected_project
    message = result.update["messages"][0]
    assert message.additional_kwargs["incubation_persistence"]["project_id"] == expected_project.project_id
