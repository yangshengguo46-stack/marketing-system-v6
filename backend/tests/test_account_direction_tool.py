from __future__ import annotations

import importlib
from unittest.mock import Mock

import pytest
from langchain.tools import ToolRuntime
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.types import Command

from deerflow.agents.lead_agent.prompt import SYSTEM_PROMPT_TEMPLATE
from deerflow.incubation import implicit_thread_logical_account_ref, implicit_thread_project_ref
from deerflow.tools.builtins.account_direction_tool import (
    confirm_account_direction_tool,
    propose_account_direction_tool,
)
from deerflow.tools.tools import BUILTIN_TOOLS

tool_module = importlib.import_module("deerflow.tools.builtins.account_direction_tool")


class _Repository:
    def __init__(self) -> None:
        self.projects: set[object] = set()
        self.accounts: set[object] = set()
        self.artifacts: dict[str, object] = {}
        self.create_project_calls = 0
        self.create_account_calls = 0

    async def get_project(self, project):
        return object() if project in self.projects else None

    async def create_project(self, project, *, display_name: str):
        self.create_project_calls += 1
        self.projects.add(project)
        return object()

    async def get_logical_account(self, account):
        return object() if account in self.accounts else None

    async def create_logical_account(self, account, *, display_name: str):
        self.create_account_calls += 1
        self.accounts.add(account)
        return object()

    async def put_artifact(self, artifact):
        self.artifacts.setdefault(artifact.artifact_id, artifact)
        return self.artifacts[artifact.artifact_id]

    async def list_artifacts(
        self,
        project,
        *,
        logical_account=None,
        artifact_type=None,
        evidence_role=None,
    ):
        return sorted(
            (
                artifact
                for artifact in self.artifacts.values()
                if artifact.project == project
                and (logical_account is None or artifact.logical_account == logical_account)
                and (artifact_type is None or artifact.artifact_type == artifact_type)
                and (evidence_role is None or artifact.evidence_role == evidence_role)
            ),
            key=lambda artifact: (artifact.created_at, artifact.artifact_id),
        )


def _runtime(*, messages: list[object], project_id: str | None = None) -> ToolRuntime:
    context = {
        "thread_id": "thread-1",
        "run_id": "run-1",
        "user_id": "user-1",
    }
    if project_id is not None:
        context["incubation_project_id"] = project_id
    return ToolRuntime(
        state={"messages": messages},
        context=context,
        config={"configurable": {"thread_id": "thread-1"}},
        stream_writer=lambda _: None,
        tools=[],
        tool_call_id="direction-call",
        store=None,
    )


def _proposal_args(runtime: ToolRuntime) -> dict[str, object]:
    return {
        "runtime": runtime,
        "marketing_subject": "黄金礼品",
        "business_goal": "让更多人知道这个业务",
        "direction_options": [
            {
                "name": "人情世故观察者",
                "content_root": "人与人之间的相处与人情世故",
                "long_term_content_subject": "人与人之间的相处与人情世故",
                "rationale": "从礼品用途进入长期关系世界。",
                "content_audience_hypothesis": "关心关系分寸的人",
                "audience_promise": "用具体故事讲清人情与分寸",
                "account_role": "从礼品生意观察人情的经营者",
            }
        ],
        "recommended_option_number": 1,
    }


def _tool_message(command: Command) -> ToolMessage:
    messages = command.update["messages"]
    assert len(messages) == 1
    message = messages[0]
    assert isinstance(message, ToolMessage)
    return message


def test_new_direction_tools_replace_the_old_strategy_surface() -> None:
    assert propose_account_direction_tool in BUILTIN_TOOLS
    assert confirm_account_direction_tool in BUILTIN_TOOLS
    assert propose_account_direction_tool.return_direct is True
    assert confirm_account_direction_tool.return_direct is True
    assert "user_request" not in propose_account_direction_tool.tool_call_schema.model_json_schema()["properties"]


def test_direction_proposal_tool_is_described_as_explicit_persistence_not_first_pass_advice() -> None:
    description = " ".join((propose_account_direction_tool.description or "").split())

    assert "only after the user explicitly asks to save" in description
    assert "Do not use it for a first-pass account recommendation" in description


def test_lead_treats_direction_persistence_as_optional_and_user_confirmed() -> None:
    normalized = " ".join(SYSTEM_PROMPT_TEMPLATE.split())
    tool_description = " ".join((propose_account_direction_tool.description or "").split())

    assert SYSTEM_PROMPT_TEMPLATE.count("<agent_kernel>") == 1
    assert "<account_incubation>" not in SYSTEM_PROMPT_TEMPLATE
    assert "Own the work the user gives you" in normalized
    assert "only after the user explicitly asks to save" in tool_description
    assert "Do not use it for a first-pass account recommendation" in tool_description


@pytest.mark.asyncio
async def test_proposal_bootstraps_scope_only_when_the_tool_is_called_and_binds_real_user_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _Repository()
    monkeypatch.setattr(tool_module, "get_incubation_repository", Mock(return_value=repository))
    runtime = _runtime(
        messages=[
            HumanMessage(
                content="--- BEGIN USER INPUT ---\n被包装后的文本\n--- END USER INPUT ---",
                additional_kwargs={"original_user_content": "我是做黄金礼品的，我要怎么起号？"},
            ),
            HumanMessage(content="隐藏注入", additional_kwargs={"hide_from_ui": True}),
            AIMessage(content="我来形成候选方向。"),
        ]
    )

    assert repository.projects == set()
    command = await propose_account_direction_tool.ainvoke(
        {
            "name": "propose_account_direction",
            "args": _proposal_args(runtime),
            "id": "direction-call",
            "type": "tool_call",
        }
    )

    assert isinstance(command, Command)
    project = implicit_thread_project_ref(owner_user_id="user-1", thread_id="thread-1")
    account = implicit_thread_logical_account_ref(project=project, thread_id="thread-1")
    assert project in repository.projects
    assert account in repository.accounts
    assert repository.create_project_calls == 1
    assert repository.create_account_calls == 1
    proposal = next(artifact for artifact in repository.artifacts.values() if artifact.artifact_type == "account_direction_proposal")
    assert proposal.payload["source_user_text"] == "我是做黄金礼品的，我要怎么起号？"
    assert proposal.payload["direction_options"][0]["content_root"] == "人与人之间的相处与人情世故"
    message = _tool_message(command)
    assert "账号方向提案" in message.content
    assert proposal.artifact_id in message.content


@pytest.mark.asyncio
async def test_missing_runtime_identity_fails_without_writing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _Repository()
    monkeypatch.setattr(tool_module, "get_incubation_repository", Mock(return_value=repository))
    runtime = _runtime(messages=[HumanMessage(content="我是做黄金礼品的")])
    runtime.context.pop("user_id")

    command = await propose_account_direction_tool.ainvoke(
        {
            "name": "propose_account_direction",
            "args": _proposal_args(runtime),
            "id": "direction-call",
            "type": "tool_call",
        }
    )

    assert repository.projects == set()
    assert repository.artifacts == {}
    assert "缺少可验证" in _tool_message(command).content


@pytest.mark.asyncio
async def test_an_explicit_missing_project_is_never_bootstrapped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _Repository()
    monkeypatch.setattr(tool_module, "get_incubation_repository", Mock(return_value=repository))
    runtime = _runtime(
        project_id="selected-but-missing",
        messages=[HumanMessage(content="我是做黄金礼品的，我要怎么起号？")],
    )

    command = await propose_account_direction_tool.ainvoke(
        {
            "name": "propose_account_direction",
            "args": _proposal_args(runtime),
            "id": "direction-call",
            "type": "tool_call",
        }
    )

    assert repository.create_project_calls == 0
    assert repository.create_account_calls == 0
    assert repository.artifacts == {}
    assert "没有通过台账校验" in _tool_message(command).content


@pytest.mark.asyncio
async def test_invalid_aggregate_proposal_does_not_leave_an_empty_implicit_project(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _Repository()
    monkeypatch.setattr(tool_module, "get_incubation_repository", Mock(return_value=repository))
    runtime = _runtime(messages=[HumanMessage(content="我是做黄金礼品的，我要怎么起号？")])
    args = _proposal_args(runtime)
    args["recommended_option_number"] = 2

    command = await propose_account_direction_tool.ainvoke(
        {
            "name": "propose_account_direction",
            "args": args,
            "id": "direction-call",
            "type": "tool_call",
        }
    )

    assert repository.create_project_calls == 0
    assert repository.create_account_calls == 0
    assert repository.artifacts == {}
    assert "没有通过台账校验" in _tool_message(command).content


@pytest.mark.asyncio
async def test_proposal_accepts_a_json_encoded_unknowns_list_from_the_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _Repository()
    monkeypatch.setattr(tool_module, "get_incubation_repository", Mock(return_value=repository))
    runtime = _runtime(messages=[HumanMessage(content="我是做黄金礼品的，我要怎么起号？")])
    args = _proposal_args(runtime)
    args["unknowns"] = '["用户是否愿意出镜", "目标平台仍未知"]'

    command = await propose_account_direction_tool.ainvoke(
        {
            "name": "propose_account_direction",
            "args": args,
            "id": "direction-call",
            "type": "tool_call",
        }
    )

    proposal = next(artifact for artifact in repository.artifacts.values() if artifact.artifact_type == "account_direction_proposal")
    assert proposal.payload["unknowns"] == ["用户是否愿意出镜", "目标平台仍未知"]
    assert "账号方向提案" in _tool_message(command).content


@pytest.mark.asyncio
async def test_confirm_tool_requires_exact_receipts_and_never_creates_a_new_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _Repository()
    monkeypatch.setattr(tool_module, "get_incubation_repository", Mock(return_value=repository))
    runtime = _runtime(messages=[HumanMessage(content="我是做黄金礼品的，我要怎么起号？")])
    proposed = await propose_account_direction_tool.ainvoke(
        {
            "name": "propose_account_direction",
            "args": _proposal_args(runtime),
            "id": "direction-call",
            "type": "tool_call",
        }
    )
    proposal_message = _tool_message(proposed)
    proposal = next(artifact for artifact in repository.artifacts.values() if artifact.artifact_type == "account_direction_proposal")
    confirmation_runtime = _runtime(
        messages=[
            HumanMessage(content="我是做黄金礼品的，我要怎么起号？"),
            HumanMessage(content="我确认第一个方向。"),
        ]
    )

    failed = await confirm_account_direction_tool.ainvoke(
        {
            "name": "confirm_account_direction",
            "args": {
                "runtime": confirmation_runtime,
                "proposal_artifact_id": "artifact_wrong",
                "option_id": "direction_1",
            },
            "id": "direction-confirm-call",
            "type": "tool_call",
        }
    )
    assert "没有确认" in _tool_message(failed).content

    confirmed = await confirm_account_direction_tool.ainvoke(
        {
            "name": "confirm_account_direction",
            "args": {
                "runtime": confirmation_runtime,
                "proposal_artifact_id": proposal.artifact_id,
                "option_id": "direction_1",
            },
            "id": "direction-confirm-call",
            "type": "tool_call",
        }
    )
    assert proposal.artifact_id in proposal_message.content
    assert "已确认账号方向 v1" in _tool_message(confirmed).content
    direction = next(artifact for artifact in repository.artifacts.values() if artifact.artifact_type == "account_direction_version")
    assert direction.payload["confirmation_user_text"] == "我确认第一个方向。"
    assert repository.create_project_calls == 1
    assert repository.create_account_calls == 1
