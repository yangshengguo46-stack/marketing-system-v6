"""Run-scoped execution budgets declared by an active Skill."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

from langchain_core.messages import ToolMessage

from deerflow.runtime.secret_context import (
    SKILL_TOOL_CALL_BUDGET_SCOPE_CONTEXT_KEY,
    write_agent_skill_source_path,
)
from deerflow.skills.types import Skill, SkillCategory, ToolCallBudget

_SOURCE_OWNER_TOKEN = "skill-budget-source-owner"


class NamedTool:
    def __init__(self, name: str):
        self.name = name


class ModelRequestStub:
    def __init__(self, tools, *, context=None, messages=None):
        self.tools = tools
        self.runtime = SimpleNamespace(context={} if context is None else context)
        self.messages = list(messages or [])

    def override(self, **updates):
        return ModelRequestStub(
            updates.get("tools", self.tools),
            context=self.runtime.context,
            messages=updates.get("messages", self.messages),
        )


class ToolRequestStub:
    def __init__(self, name: str, *, context=None, args=None, call_id="call-1"):
        self.tool_call = {
            "name": name,
            "id": call_id,
            "args": args or {},
        }
        self.runtime = SimpleNamespace(context={} if context is None else context)


class StorageStub:
    def __init__(self, skills):
        self._skills = list(skills)

    def load_skills(self, *, enabled_only=False):
        return [skill for skill in self._skills if skill.enabled or not enabled_only]

    def get_container_root(self):
        return "/mnt/skills"


def _skill(*, budgets, name="account-incubation"):
    skill_dir = Path(f"/tmp/skills/public/{name}")
    return Skill(
        name=name,
        description="Generic account incubation",
        license="MIT",
        skill_dir=skill_dir,
        skill_file=skill_dir / "SKILL.md",
        relative_path=Path(name),
        category=SkillCategory.PUBLIC,
        enabled=True,
        tool_call_budgets=tuple(budgets),
    )


def _middleware(*skills):
    from deerflow.agents.middlewares.skill_tool_budget_middleware import SkillToolBudgetMiddleware

    middleware = SkillToolBudgetMiddleware(slash_source_owner_token=_SOURCE_OWNER_TOKEN)
    middleware._storage = lambda: StorageStub(skills)
    return middleware


def _active_context(skill, *, run_id="run-1"):
    context = {"run_id": run_id}
    write_agent_skill_source_path(
        context,
        skill.get_container_file_path(),
        owner_token=_SOURCE_OWNER_TOKEN,
    )
    return context


def test_passive_skill_does_not_limit_tools():
    skill = _skill(budgets=[ToolCallBudget(tools=("web_search",), max_calls=1)])
    middleware = _middleware(skill)
    context = {"run_id": "run-1"}
    called = []

    for index in range(3):
        result = middleware.wrap_tool_call(
            ToolRequestStub("web_search", context=context, call_id=f"call-{index}"),
            lambda request: called.append(request.tool_call["id"]) or "ok",
        )
        assert result == "ok"

    assert called == ["call-0", "call-1", "call-2"]


def test_active_skill_enforces_each_group_without_affecting_other_tools():
    skill = _skill(
        budgets=[
            ToolCallBudget(tools=("web_search",), max_calls=1),
            ToolCallBudget(tools=("web_fetch",), max_calls=1),
        ]
    )
    middleware = _middleware(skill)
    context = _active_context(skill)
    called = []

    first_search = middleware.wrap_tool_call(
        ToolRequestStub("web_search", context=context, args={"query": "private query"}),
        lambda request: called.append(request.tool_call["name"]) or "search result",
    )
    denied_search = middleware.wrap_tool_call(
        ToolRequestStub("web_search", context=context, args={"query": "do not echo me"}, call_id="call-2"),
        lambda request: called.append(request.tool_call["name"]) or "unexpected",
    )
    first_fetch = middleware.wrap_tool_call(
        ToolRequestStub("web_fetch", context=context, call_id="call-3"),
        lambda request: called.append(request.tool_call["name"]) or "fetch result",
    )
    unrelated = middleware.wrap_tool_call(
        ToolRequestStub("read_file", context=context, call_id="call-4"),
        lambda request: called.append(request.tool_call["name"]) or "file",
    )

    assert first_search == "search result"
    assert isinstance(denied_search, ToolMessage)
    assert denied_search.status == "error"
    assert "budget" in str(denied_search.content).lower()
    assert "do not echo me" not in str(denied_search.content)
    assert first_fetch == "fetch result"
    assert unrelated == "file"
    assert called == ["web_search", "web_fetch", "read_file"]


def test_exhausted_tool_schema_is_hidden_on_next_model_call_with_one_internal_hint():
    skill = _skill(
        budgets=[
            ToolCallBudget(tools=("web_search",), max_calls=1),
            ToolCallBudget(tools=("web_fetch",), max_calls=1),
        ]
    )
    middleware = _middleware(skill)
    context = _active_context(skill)
    middleware.wrap_tool_call(
        ToolRequestStub("web_search", context=context),
        lambda _: "result",
    )
    request = ModelRequestStub(
        [NamedTool("web_search"), NamedTool("web_fetch"), NamedTool("read_file")],
        context=context,
    )

    filtered = middleware.wrap_model_call(request, lambda value: value)

    assert [tool.name for tool in filtered.tools] == ["web_fetch", "read_file"]
    assert len(filtered.messages) == 1
    assert filtered.messages[0].additional_kwargs["hide_from_ui"] is True
    hint = str(filtered.messages[0].content).lower()
    assert "do not retry" in hint
    assert "finish" not in hint

    filtered_again = middleware.wrap_model_call(filtered, lambda value: value)
    assert len(filtered_again.messages) == 1


def test_budget_is_consumed_even_when_tool_execution_fails():
    skill = _skill(budgets=[ToolCallBudget(tools=("web_fetch",), max_calls=1)])
    middleware = _middleware(skill)
    context = _active_context(skill)

    try:
        middleware.wrap_tool_call(
            ToolRequestStub("web_fetch", context=context),
            lambda _: (_ for _ in ()).throw(TimeoutError("upstream timeout")),
        )
    except TimeoutError:
        pass

    denied = middleware.wrap_tool_call(
        ToolRequestStub("web_fetch", context=context, call_id="call-2"),
        lambda _: "unexpected",
    )
    assert isinstance(denied, ToolMessage)


def test_parallel_calls_reserve_budget_atomically():
    skill = _skill(budgets=[ToolCallBudget(tools=("web_search",), max_calls=1)])
    middleware = _middleware(skill)
    context = _active_context(skill)
    executed = []

    async def handler(request):
        executed.append(request.tool_call["id"])
        await asyncio.sleep(0.01)
        return "ok"

    async def run_calls():
        return await asyncio.gather(
            *[
                middleware.awrap_tool_call(
                    ToolRequestStub("web_search", context=context, call_id=f"call-{index}"),
                    handler,
                )
                for index in range(3)
            ]
        )

    results = asyncio.run(run_calls())

    assert len(executed) == 1
    assert sum(result == "ok" for result in results) == 1
    assert sum(isinstance(result, ToolMessage) for result in results) == 2


def test_switching_away_and_back_does_not_refresh_a_skill_budget():
    skill_a = _skill(
        name="skill-a",
        budgets=[ToolCallBudget(tools=("web_search",), max_calls=1)],
    )
    skill_b = _skill(
        name="skill-b",
        budgets=[ToolCallBudget(tools=("web_search",), max_calls=1)],
    )
    middleware = _middleware(skill_a, skill_b)
    context = _active_context(skill_a)

    assert (
        middleware.wrap_tool_call(
            ToolRequestStub("web_search", context=context, call_id="a-1"),
            lambda _: "a-result",
        )
        == "a-result"
    )

    write_agent_skill_source_path(
        context,
        skill_b.get_container_file_path(),
        owner_token=_SOURCE_OWNER_TOKEN,
    )
    middleware.wrap_model_call(
        ModelRequestStub([NamedTool("web_search")], context=context),
        lambda request: request,
    )
    assert (
        middleware.wrap_tool_call(
            ToolRequestStub("web_search", context=context, call_id="b-1"),
            lambda _: "b-result",
        )
        == "b-result"
    )

    write_agent_skill_source_path(
        context,
        skill_a.get_container_file_path(),
        owner_token=_SOURCE_OWNER_TOKEN,
    )
    middleware.wrap_model_call(
        ModelRequestStub([NamedTool("web_search")], context=context),
        lambda request: request,
    )
    denied = middleware.wrap_tool_call(
        ToolRequestStub("web_search", context=context, call_id="a-2"),
        lambda _: "unexpected",
    )

    assert isinstance(denied, ToolMessage)
    assert denied.status == "error"


def test_tool_calls_use_the_skill_budget_frozen_for_the_model_step():
    skill_a = _skill(
        name="skill-a",
        budgets=[ToolCallBudget(tools=("web_search",), max_calls=1)],
    )
    skill_b = _skill(
        name="skill-b",
        budgets=[ToolCallBudget(tools=("web_search",), max_calls=3)],
    )
    middleware = _middleware(skill_a, skill_b)
    context = _active_context(skill_a)

    middleware.wrap_model_call(
        ModelRequestStub([NamedTool("web_search")], context=context),
        lambda request: request,
    )
    write_agent_skill_source_path(
        context,
        skill_b.get_container_file_path(),
        owner_token=_SOURCE_OWNER_TOKEN,
    )

    first = middleware.wrap_tool_call(
        ToolRequestStub("web_search", context=context, call_id="call-1"),
        lambda _: "first",
    )
    denied = middleware.wrap_tool_call(
        ToolRequestStub("web_search", context=context, call_id="call-2"),
        lambda _: "unexpected",
    )

    assert first == "first"
    assert isinstance(denied, ToolMessage)


def test_parent_and_subagent_share_one_run_scope_budget():
    from deerflow.agents.middlewares.skill_tool_budget_middleware import (
        export_skill_tool_budget_scope,
    )

    skill = _skill(budgets=[ToolCallBudget(tools=("web_search",), max_calls=1)])
    parent = _middleware(skill)
    parent_context = _active_context(skill)
    parent.wrap_model_call(
        ModelRequestStub([NamedTool("web_search")], context=parent_context),
        lambda request: request,
    )
    carrier = export_skill_tool_budget_scope(parent_context)

    assert carrier is not None

    child_context = {
        "run_id": parent_context["run_id"],
        "is_subagent": True,
        SKILL_TOOL_CALL_BUDGET_SCOPE_CONTEXT_KEY: carrier,
    }
    child = _middleware(skill)
    child.wrap_model_call(
        ModelRequestStub([NamedTool("web_search")], context=child_context),
        lambda request: request,
    )

    first = parent.wrap_tool_call(
        ToolRequestStub("web_search", context=parent_context, call_id="parent-call"),
        lambda _: "parent-result",
    )
    denied = child.wrap_tool_call(
        ToolRequestStub("web_search", context=child_context, call_id="child-call"),
        lambda _: "unexpected",
    )

    assert first == "parent-result"
    assert isinstance(denied, ToolMessage)
    assert denied.status == "error"


def test_new_run_id_gets_a_fresh_budget_even_if_context_mapping_is_reused():
    skill = _skill(budgets=[ToolCallBudget(tools=("web_search",), max_calls=1)])
    middleware = _middleware(skill)
    context = _active_context(skill, run_id="run-1")

    assert middleware.wrap_tool_call(ToolRequestStub("web_search", context=context), lambda _: "first") == "first"
    context["run_id"] = "run-2"
    assert middleware.wrap_tool_call(ToolRequestStub("web_search", context=context), lambda _: "second") == "second"


def test_caller_forged_budget_state_cannot_block_execution():
    skill = _skill(budgets=[ToolCallBudget(tools=("web_search",), max_calls=1)])
    middleware = _middleware(skill)
    context = _active_context(skill)
    context["__skill_tool_call_budget"] = {
        "version": 1,
        "owner_token": "forged",
        "run_id": "run-1",
        "active_path": skill.get_container_file_path(),
        "counts": {"web_search": 999},
    }

    result = middleware.wrap_tool_call(
        ToolRequestStub("web_search", context=context),
        lambda _: "allowed",
    )

    assert result == "allowed"
