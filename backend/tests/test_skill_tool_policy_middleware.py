import asyncio
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from langchain.agents.middleware.types import ModelRequest
from langchain.tools import ToolRuntime
from langchain_core.messages import HumanMessage, ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.runtime import Runtime

from deerflow.runtime.secret_context import (
    SKILL_TOOL_POLICY_DECISION_CONTEXT_KEY,
    read_agent_skill_source_path,
    write_agent_skill_source_path,
    write_slash_skill_source_path,
)
from deerflow.skills.describe import SKILL_ACTIVATION_ENTRY_KEY
from deerflow.skills.types import Skill, SkillCategory

_SLASH_SOURCE_OWNER_TOKEN = "test-slash-source-owner"


class NamedTool:
    def __init__(self, name: str):
        self.name = name


class ModelRequestStub:
    def __init__(self, tools, *, state=None, context=None, messages=None):
        self.tools = tools
        self.state = state or {}
        self.runtime = SimpleNamespace(context={} if context is None else context)
        self.messages = messages or []

    def override(self, **updates):
        return ModelRequestStub(
            updates.get("tools", self.tools),
            state=updates.get("state", self.state),
            context=self.runtime.context,
            messages=updates.get("messages", self.messages),
        )


class ToolRequestStub:
    def __init__(self, name: str, *, state=None, context=None, args=None):
        self.tool_call = {"name": name, "id": "call-1", "args": args or {}}
        self.state = state or {}
        self.runtime = SimpleNamespace(context={} if context is None else context)


class StorageStub:
    def __init__(self, skills):
        self._skills = skills
        self.load_calls = 0

    def load_skills(self, *, enabled_only=False):
        self.load_calls += 1
        return [skill for skill in self._skills if skill.enabled or not enabled_only]

    def get_container_root(self):
        return "/mnt/skills"


def _skill(name: str, allowed_tools, *, enabled=True):
    skill_dir = Path(f"/tmp/skills/public/{name}")
    return Skill(
        name=name,
        description=f"Description for {name}",
        license="MIT",
        skill_dir=skill_dir,
        skill_file=skill_dir / "SKILL.md",
        relative_path=Path(name),
        category=SkillCategory.PUBLIC,
        allowed_tools=None if allowed_tools is None else tuple(allowed_tools),
        enabled=enabled,
    )


def _middleware(skills, *, available_skills=None):
    from deerflow.agents.middlewares.skill_tool_policy_middleware import SkillToolPolicyMiddleware

    middleware = SkillToolPolicyMiddleware(
        available_skills=available_skills,
        slash_source_owner_token=_SLASH_SOURCE_OWNER_TOKEN,
    )
    middleware._storage = lambda: StorageStub(skills)
    return middleware


def _tool_names(request):
    return [tool.name for tool in request.tools]


def _agent_context(path: str) -> dict:
    context: dict = {}
    write_agent_skill_source_path(
        context,
        path,
        owner_token=_SLASH_SOURCE_OWNER_TOKEN,
    )
    return context


@pytest.mark.parametrize(
    "middleware_class_path",
    [
        "deerflow.agents.middlewares.skill_activation_middleware.SkillActivationMiddleware",
        "deerflow.agents.middlewares.skill_tool_policy_middleware.SkillToolPolicyMiddleware",
    ],
)
def test_skill_policy_middlewares_require_shared_slash_source_token(middleware_class_path):
    module_name, class_name = middleware_class_path.rsplit(".", 1)
    module = __import__(module_name, fromlist=[class_name])
    middleware_class = getattr(module, class_name)

    with pytest.raises(TypeError, match="slash_source_owner_token"):
        middleware_class()


@pytest.mark.parametrize("invalid_token", [None, "", 7])
def test_skill_policy_middlewares_reject_invalid_slash_source_tokens(invalid_token):
    from deerflow.agents.middlewares.skill_activation_middleware import SkillActivationMiddleware
    from deerflow.agents.middlewares.skill_tool_policy_middleware import SkillToolPolicyMiddleware

    for middleware_class in (SkillActivationMiddleware, SkillToolPolicyMiddleware):
        with pytest.raises(ValueError, match="non-empty string"):
            middleware_class(slash_source_owner_token=invalid_token)


def test_passive_enabled_skill_does_not_filter_lead_tools():
    middleware = _middleware([_skill("reviewer", ["review_skill_package"])])
    request = ModelRequestStub([NamedTool("task"), NamedTool("web_search"), NamedTool("review_skill_package")])

    filtered = middleware._filter_model_request(request)

    assert _tool_names(filtered) == ["task", "web_search", "review_skill_package"]


def test_sync_passive_model_call_skips_storage():
    middleware = _middleware([])

    def fail_storage():
        raise AssertionError("passive model calls must not load skill storage")

    middleware._storage = fail_storage
    request = ModelRequestStub([NamedTool("task")])

    assert middleware.wrap_model_call(request, lambda model_request: model_request) is request


def test_async_passive_model_call_skips_storage_and_thread_offload():
    middleware = _middleware([])

    def fail_storage():
        raise AssertionError("passive model calls must not load skill storage")

    middleware._storage = fail_storage
    request = ModelRequestStub([NamedTool("task")])

    async def handler(model_request):
        return model_request

    assert asyncio.run(middleware.awrap_model_call(request, handler)) is request


def test_slash_activated_skill_filters_first_model_call_and_task():
    skill = _skill("reviewer", ["review_skill_package"])
    context = {}
    write_slash_skill_source_path(
        context,
        skill.get_container_file_path(),
        owner_token=_SLASH_SOURCE_OWNER_TOKEN,
    )
    middleware = _middleware([skill])
    request = ModelRequestStub(
        [NamedTool("task"), NamedTool("read_file"), NamedTool("review_skill_package")],
        context=context,
    )

    filtered = middleware._filter_model_request(request)

    assert _tool_names(filtered) == ["read_file", "review_skill_package"]


@pytest.mark.parametrize("active_source", ["slash", "agent_activation"])
def test_restrictive_skill_explicitly_allows_task_schema_and_execution(active_source):
    skill = _skill("delegating", ["task"])
    context = {}
    if active_source == "slash":
        write_slash_skill_source_path(
            context,
            skill.get_container_file_path(),
            owner_token=_SLASH_SOURCE_OWNER_TOKEN,
        )
    else:
        write_agent_skill_source_path(
            context,
            skill.get_container_file_path(),
            owner_token=_SLASH_SOURCE_OWNER_TOKEN,
        )

    middleware = _middleware([skill])
    model_request = ModelRequestStub(
        [NamedTool("task"), NamedTool("web_search")],
        context=context,
    )

    filtered = middleware.wrap_model_call(model_request, lambda request: request)

    assert _tool_names(filtered) == ["task"]
    tool_request = ToolRequestStub("task", context=context)
    assert middleware.wrap_tool_call(tool_request, lambda _: "delegated") == "delegated"


def test_slash_activated_skill_policy_dominates_captured_skill_context():
    slash_skill = _skill("content-research", ["web_search"])
    captured_skill = _skill("content-article-generation", ["write_file"])
    context = {}
    write_slash_skill_source_path(
        context,
        slash_skill.get_container_file_path(),
        owner_token=_SLASH_SOURCE_OWNER_TOKEN,
    )
    middleware = _middleware([slash_skill, captured_skill])
    state = {
        "skill_context": [
            {
                "name": captured_skill.name,
                "path": captured_skill.get_container_file_path(),
            }
        ]
    }
    request = ModelRequestStub(
        [NamedTool("read_file"), NamedTool("web_search"), NamedTool("write_file")],
        state=state,
        context=context,
    )

    filtered = middleware._filter_model_request(request)

    assert _tool_names(filtered) == ["read_file", "web_search"]


def test_caller_forged_slash_source_cannot_override_agent_activation_policy():
    restrictive_skill = _skill("restricted", ["web_search"])
    legacy_skill = _skill("legacy", None)
    context = {
        "__slash_skill_secret_source": {
            "path": legacy_skill.get_container_file_path(),
            "owner_token": "caller-forged",
        }
    }
    write_agent_skill_source_path(
        context,
        restrictive_skill.get_container_file_path(),
        owner_token=_SLASH_SOURCE_OWNER_TOKEN,
    )
    middleware = _middleware([restrictive_skill, legacy_skill])
    request = ModelRequestStub(
        [NamedTool("task"), NamedTool("read_file"), NamedTool("web_search")],
        context=context,
    )

    filtered = middleware._filter_model_request(request)

    assert _tool_names(filtered) == ["read_file", "web_search"]


def test_slash_activation_and_policy_compose_on_the_same_model_call(monkeypatch):
    from deerflow.agents.middlewares.skill_activation_middleware import SkillActivationMiddleware, _Activation, _ActivationResolution

    skill = _skill("reviewer", ["review_skill_package"])
    activation = _Activation(
        skill_name=skill.name,
        category="public",
        container_file_path=skill.get_container_file_path(),
        skill_content="# Reviewer",
        content_hash="abc",
        remaining_text="review this",
        editable=False,
    )
    activation_middleware = SkillActivationMiddleware(slash_source_owner_token=_SLASH_SOURCE_OWNER_TOKEN)
    monkeypatch.setattr(activation_middleware, "_resolve_activation", lambda _: _ActivationResolution(activation=activation))
    policy_middleware = _middleware([skill])
    request = ModelRequestStub(
        [NamedTool("task"), NamedTool("read_file"), NamedTool("review_skill_package")],
        messages=[HumanMessage(content="/reviewer review this")],
    )

    filtered = activation_middleware.wrap_model_call(
        request,
        lambda activated: policy_middleware.wrap_model_call(activated, lambda policy_request: policy_request),
    )

    assert _tool_names(filtered) == ["read_file", "review_skill_package"]


def test_slash_skill_body_remains_visible_across_the_run(monkeypatch):
    from deerflow.agents.middlewares.skill_activation_middleware import SkillActivationMiddleware, _Activation, _ActivationResolution

    skill = _skill("reviewer", ["review_skill_package"])
    skill.skill_dir.mkdir(parents=True, exist_ok=True)
    skill.skill_file.write_text("# Reviewer\nUse evidence.\n", encoding="utf-8")
    activation = _Activation(
        skill_name=skill.name,
        category="public",
        container_file_path=skill.get_container_file_path(),
        skill_content="# Reviewer\nUse evidence.\n",
        content_hash=hashlib.sha256(b"# Reviewer\nUse evidence.\n").hexdigest(),
        remaining_text="review this",
        editable=False,
    )
    middleware = SkillActivationMiddleware(slash_source_owner_token=_SLASH_SOURCE_OWNER_TOKEN)
    middleware._storage = lambda: StorageStub([skill])
    monkeypatch.setattr(middleware, "_resolve_activation", lambda _: _ActivationResolution(activation=activation))
    context = {}

    middleware.wrap_model_call(
        ModelRequestStub([], messages=[HumanMessage(content="/reviewer review this", id="m1")], context=context),
        lambda request: request,
    )
    second = middleware.wrap_model_call(
        ModelRequestStub([], messages=[HumanMessage(content="continue", id="m1")], context=context),
        lambda request: request,
    )

    active_messages = [message for message in second.messages if isinstance(message, HumanMessage) and message.additional_kwargs.get("active_skill_context")]
    assert len(active_messages) == 1
    assert "# Reviewer" in active_messages[0].content
    assert 'mode="slash"' in active_messages[0].content


def test_inspected_skill_context_does_not_filter_follow_up_model_calls():
    skill = _skill("restricted", ["web_search"])
    middleware = _middleware([skill])
    request = ModelRequestStub(
        [NamedTool("task"), NamedTool("read_file"), NamedTool("web_search")],
        state={"skill_context": [{"name": skill.name, "path": skill.get_container_file_path()}]},
    )

    filtered = middleware._filter_model_request(request)

    assert _tool_names(filtered) == ["task", "read_file", "web_search"]


def test_activate_skill_result_sets_task_scoped_policy_source(tmp_path):
    from deerflow.agents.middlewares.skill_activation_middleware import SkillActivationMiddleware

    skill = _skill("restricted", ["web_search"])
    skill.skill_dir.mkdir(parents=True, exist_ok=True)
    content = "---\nname: restricted\ndescription: Restrict tools\n---\n\n# Method\n"
    skill.skill_file.write_text(content, encoding="utf-8")
    storage = StorageStub([skill])
    activation = SkillActivationMiddleware(slash_source_owner_token=_SLASH_SOURCE_OWNER_TOKEN)
    activation._storage = lambda: storage
    context = {}
    request = ToolRequestStub(
        "activate_skill",
        context=context,
        args={"name": skill.name},
    )
    result_message = ToolMessage(
        content="activated",
        tool_call_id="call-1",
        name="activate_skill",
        additional_kwargs={
            SKILL_ACTIVATION_ENTRY_KEY: {
                "name": skill.name,
                "path": skill.get_container_file_path(),
                "description": skill.description,
                "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
            }
        },
    )

    assert activation.wrap_tool_call(request, lambda _: result_message) is result_message
    assert read_agent_skill_source_path(context, owner_token=_SLASH_SOURCE_OWNER_TOKEN) == skill.get_container_file_path()

    next_model_call = activation.wrap_model_call(
        ModelRequestStub([], messages=[HumanMessage(content="continue")], context=context),
        lambda model_request: model_request,
    )
    active_messages = [message for message in next_model_call.messages if isinstance(message, HumanMessage) and message.additional_kwargs.get("active_skill_context")]
    assert len(active_messages) == 1
    assert "# Method" in active_messages[0].content
    assert 'mode="agent"' in active_messages[0].content

    policy = _middleware([skill])
    filtered = policy._filter_model_request(
        ModelRequestStub(
            [NamedTool("task"), NamedTool("activate_skill"), NamedTool("web_search")],
            context=context,
        )
    )
    assert _tool_names(filtered) == ["activate_skill", "web_search"]


def test_activate_skill_cannot_replace_user_slash_selection():
    from deerflow.agents.middlewares.skill_activation_middleware import SkillActivationMiddleware

    context = {}
    write_slash_skill_source_path(
        context,
        "/mnt/skills/public/user-selected/SKILL.md",
        owner_token=_SLASH_SOURCE_OWNER_TOKEN,
    )
    middleware = SkillActivationMiddleware(slash_source_owner_token=_SLASH_SOURCE_OWNER_TOKEN)
    request = ToolRequestStub("activate_skill", context=context, args={"name": "other"})

    result = middleware.wrap_tool_call(request, lambda _: pytest.fail("handler must not run"))

    assert result.status == "error"
    assert "user already selected" in result.content


def test_latest_agent_activation_replaces_previous_policy_source():
    restricted = _skill("restricted", ["web_search"])
    second = _skill("second", ["bash"])
    middleware = _middleware([restricted, second])
    context = _agent_context(restricted.get_container_file_path())
    write_agent_skill_source_path(
        context,
        second.get_container_file_path(),
        owner_token=_SLASH_SOURCE_OWNER_TOKEN,
    )
    request = ModelRequestStub(
        [NamedTool("task"), NamedTool("bash"), NamedTool("web_search")],
        context=context,
    )

    filtered = middleware._filter_model_request(request)

    assert _tool_names(filtered) == ["bash"]


def test_only_legacy_active_skill_preserves_all_tools():
    legacy = _skill("legacy", None)
    middleware = _middleware([legacy])
    request = ModelRequestStub(
        [NamedTool("task"), NamedTool("bash")],
        context=_agent_context(legacy.get_container_file_path()),
    )

    assert _tool_names(middleware._filter_model_request(request)) == ["task", "bash"]


def test_explicit_empty_allowed_tools_keeps_only_framework_tools():
    restricted = _skill("restricted", [])
    middleware = _middleware([restricted])
    request = ModelRequestStub(
        [
            NamedTool("task"),
            NamedTool("read_file"),
            NamedTool("review_skill_package"),
            NamedTool("tool_search"),
            NamedTool("describe_skill"),
            NamedTool("activate_skill"),
        ],
        context=_agent_context(restricted.get_container_file_path()),
    )

    assert _tool_names(middleware._filter_model_request(request)) == [
        "read_file",
        "review_skill_package",
        "tool_search",
        "describe_skill",
        "activate_skill",
    ]


def test_active_skill_keeps_framework_discovery_tools():
    restricted = _skill("restricted", ["calc"])
    middleware = _middleware([restricted])
    request = ModelRequestStub(
        [NamedTool("calc"), NamedTool("tool_search"), NamedTool("describe_skill"), NamedTool("activate_skill")],
        context=_agent_context(restricted.get_container_file_path()),
    )

    assert _tool_names(middleware._filter_model_request(request)) == ["calc", "tool_search", "describe_skill", "activate_skill"]


def test_custom_agent_allowlist_rejects_all_out_of_scope_active_skills():
    restricted = _skill("restricted", ["web_search"])
    middleware = _middleware([restricted], available_skills={"other"})
    request = ModelRequestStub(
        [NamedTool("task"), NamedTool("web_search")],
        context=_agent_context(restricted.get_container_file_path()),
    )

    assert _tool_names(middleware._filter_model_request(request)) == []


def test_unauthorized_tool_execution_is_blocked():
    restricted = _skill("restricted", ["web_search"])
    middleware = _middleware([restricted])
    request = ToolRequestStub(
        "task",
        context=_agent_context(restricted.get_container_file_path()),
    )

    result = middleware.wrap_tool_call(request, lambda _: "executed")

    assert result.status == "error"
    assert result.name == "task"
    assert "not allowed" in result.content


def test_allowed_tool_execution_reaches_handler():
    restricted = _skill("restricted", ["web_search"])
    middleware = _middleware([restricted])
    request = ToolRequestStub(
        "web_search",
        context=_agent_context(restricted.get_container_file_path()),
    )

    assert middleware.wrap_tool_call(request, lambda _: "executed") == "executed"


def test_async_unauthorized_tool_execution_is_blocked():
    restricted = _skill("restricted", ["web_search"])
    middleware = _middleware([restricted])
    request = ToolRequestStub(
        "task",
        context=_agent_context(restricted.get_container_file_path()),
    )

    async def handler(_):
        return "executed"

    result = asyncio.run(middleware.awrap_tool_call(request, handler))

    assert result.status == "error"
    assert result.name == "task"


def test_unknown_agent_activation_path_fails_closed_to_framework_tools():
    middleware = _middleware([])
    request = ModelRequestStub(
        [NamedTool("task"), NamedTool("read_file"), NamedTool("activate_skill")],
        context=_agent_context("/mnt/skills/public/missing/SKILL.md"),
    )

    assert _tool_names(middleware._filter_model_request(request)) == ["read_file", "activate_skill"]


def test_all_unknown_active_paths_fail_closed_to_framework_tools():
    middleware = _middleware([])
    request = ModelRequestStub(
        [
            NamedTool("task"),
            NamedTool("read_file"),
            NamedTool("review_skill_package"),
            NamedTool("tool_search"),
            NamedTool("describe_skill"),
            NamedTool("activate_skill"),
        ],
        context=_agent_context("/mnt/skills/public/missing/SKILL.md"),
    )

    assert _tool_names(middleware._filter_model_request(request)) == [
        "read_file",
        "review_skill_package",
        "tool_search",
        "describe_skill",
        "activate_skill",
    ]


def test_all_disabled_active_paths_fail_closed_to_framework_tools():
    disabled = _skill("disabled", ["task"], enabled=False)
    middleware = _middleware([disabled])
    request = ModelRequestStub(
        [
            NamedTool("task"),
            NamedTool("read_file"),
            NamedTool("review_skill_package"),
            NamedTool("tool_search"),
            NamedTool("describe_skill"),
            NamedTool("activate_skill"),
        ],
        context=_agent_context(disabled.get_container_file_path()),
    )

    assert _tool_names(middleware._filter_model_request(request)) == [
        "read_file",
        "review_skill_package",
        "tool_search",
        "describe_skill",
        "activate_skill",
    ]


def test_async_passive_tool_call_skips_storage_and_thread_offload():
    middleware = _middleware([])

    def fail_storage():
        raise AssertionError("passive tool calls must not load skill storage")

    middleware._storage = fail_storage
    request = ToolRequestStub("task")

    async def handler(_):
        return "executed"

    assert asyncio.run(middleware.awrap_tool_call(request, handler)) == "executed"


def test_sync_passive_tool_call_skips_policy_resolution():
    middleware = _middleware([])
    request = ToolRequestStub("task")
    middleware._blocked_tool_message = MagicMock(side_effect=AssertionError("passive tool calls must bypass policy resolution"))

    assert middleware.wrap_tool_call(request, lambda _: "executed") == "executed"
    middleware._blocked_tool_message.assert_not_called()


def test_tool_calls_reuse_the_current_model_step_policy_decision():
    restricted = _skill("restricted", ["web_search"])
    storage = StorageStub([restricted])
    middleware = _middleware([])
    middleware._storage = lambda: storage
    context = _agent_context(restricted.get_container_file_path())
    model_request = ModelRequestStub(
        [NamedTool("task"), NamedTool("web_search")],
        context=context,
    )

    filtered = middleware.wrap_model_call(model_request, lambda request: request)
    assert _tool_names(filtered) == ["web_search"]

    for _ in range(3):
        tool_request = ToolRequestStub("web_search", context=context)
        assert middleware.wrap_tool_call(tool_request, lambda _: "executed") == "executed"

    assert storage.load_calls == 1


def test_async_tool_calls_reuse_the_current_model_step_policy_decision():
    restricted = _skill("restricted", ["web_search"])
    storage = StorageStub([restricted])
    middleware = _middleware([])
    middleware._storage = lambda: storage
    context = _agent_context(restricted.get_container_file_path())
    model_request = ModelRequestStub(
        [NamedTool("task"), NamedTool("web_search")],
        context=context,
    )

    async def go():
        filtered = await middleware.awrap_model_call(model_request, lambda request: asyncio.sleep(0, result=request))
        assert _tool_names(filtered) == ["web_search"]

        async def execute(_):
            return "executed"

        results = await asyncio.gather(*(middleware.awrap_tool_call(ToolRequestStub("web_search", context=context), execute) for _ in range(3)))
        assert results == ["executed", "executed", "executed"]

    asyncio.run(go())
    assert storage.load_calls == 1


def test_real_model_and_tool_requests_share_the_model_step_policy_decision():
    restricted = _skill("restricted", ["web_search"])
    storage = StorageStub([restricted])
    middleware = _middleware([])
    middleware._storage = lambda: storage
    context = _agent_context(restricted.get_container_file_path())
    state = {
        "messages": [],
    }
    model_request = ModelRequest(
        model=MagicMock(),
        messages=[],
        tools=[NamedTool("task"), NamedTool("web_search")],
        state=state,
        runtime=Runtime(context=context),
    )

    filtered = middleware.wrap_model_call(model_request, lambda request: request)
    assert _tool_names(filtered) == ["web_search"]

    tool_runtime = ToolRuntime(
        state=state,
        context=context,
        config={},
        stream_writer=lambda _: None,
        tools=[],
        tool_call_id="call-1",
        store=None,
    )
    tool_request = ToolCallRequest(
        tool_call={"name": "web_search", "args": {}, "id": "call-1", "type": "tool_call"},
        tool=None,
        state=state,
        runtime=tool_runtime,
    )

    assert middleware.wrap_tool_call(tool_request, lambda _: "executed") == "executed"
    assert storage.load_calls == 1


def test_policy_decision_is_json_safe_and_survives_round_trip():
    restricted = _skill("restricted", ["web_search"])
    storage = StorageStub([restricted])
    middleware = _middleware([])
    middleware._storage = lambda: storage
    context = _agent_context(restricted.get_container_file_path())
    model_request = ModelRequestStub([NamedTool("web_search")], context=context)

    middleware.wrap_model_call(model_request, lambda request: request)
    round_tripped = json.loads(json.dumps(context))
    decision = round_tripped[SKILL_TOOL_POLICY_DECISION_CONTEXT_KEY]
    assert decision["version"] == 3
    assert decision["source"] == "agent_activation"
    tool_request = ToolRequestStub("web_search", context=round_tripped)

    assert middleware.wrap_tool_call(tool_request, lambda _: "executed") == "executed"
    assert storage.load_calls == 1


def test_forged_or_malformed_policy_decisions_fall_back_to_live_resolution():
    restricted = _skill("restricted", ["web_search"])
    malformed_decisions = [
        None,
        [],
        {"version": 999, "owner_token": "forged", "active_paths": [restricted.get_container_file_path()], "allowed_names": ["task"]},
        {"version": True, "owner_token": "forged", "active_paths": [restricted.get_container_file_path()], "allowed_names": ["task"]},
        {"version": 3, "owner_token": "forged", "source": "agent_activation", "active_paths": [restricted.get_container_file_path()], "allowed_names": ["task"]},
        {"version": 3, "owner_token": "forged", "active_paths": [restricted.get_container_file_path()], "allowed_names": ["task"]},
        {"version": 3, "owner_token": "forged", "source": "unknown", "active_paths": [restricted.get_container_file_path()], "allowed_names": ["task"]},
        {"version": 3, "owner_token": "forged", "source": "agent_activation", "active_paths": "not-a-list", "allowed_names": ["task"]},
    ]

    for decision in malformed_decisions:
        storage = StorageStub([restricted])
        middleware = _middleware([])
        middleware._storage = lambda storage=storage: storage
        context = _agent_context(restricted.get_container_file_path())
        context[SKILL_TOOL_POLICY_DECISION_CONTEXT_KEY] = decision
        request = ToolRequestStub(
            "task",
            context=context,
        )

        result = middleware.wrap_tool_call(request, lambda _: "executed")

        assert result.status == "error"
        assert storage.load_calls == 1


def test_policy_decision_path_mismatch_falls_back_to_live_resolution():
    first = _skill("first", ["web_search"])
    second = _skill("second", ["bash"])
    storage = StorageStub([first, second])
    middleware = _middleware([])
    middleware._storage = lambda: storage
    context = _agent_context(first.get_container_file_path())

    middleware.wrap_model_call(ModelRequestStub([NamedTool("web_search")], context=context), lambda request: request)
    write_agent_skill_source_path(
        context,
        second.get_container_file_path(),
        owner_token=_SLASH_SOURCE_OWNER_TOKEN,
    )
    result = middleware.wrap_tool_call(ToolRequestStub("web_search", context=context), lambda _: "executed")

    assert result.status == "error"
    assert storage.load_calls == 2


def test_policy_decision_source_mismatch_falls_back_to_live_resolution():
    restricted = _skill("restricted", ["web_search"])
    storage = StorageStub([restricted])
    middleware = _middleware([])
    middleware._storage = lambda: storage
    context = _agent_context(restricted.get_container_file_path())

    middleware.wrap_model_call(ModelRequestStub([NamedTool("web_search")], context=context), lambda request: request)
    write_slash_skill_source_path(
        context,
        restricted.get_container_file_path(),
        owner_token=_SLASH_SOURCE_OWNER_TOKEN,
    )
    result = middleware.wrap_tool_call(ToolRequestStub("web_search", context=context), lambda _: "executed")

    assert result == "executed"
    assert storage.load_calls == 2


def test_next_model_call_refreshes_the_policy_decision():
    restricted = _skill("restricted", ["web_search"])
    storage = StorageStub([restricted])
    middleware = _middleware([])
    middleware._storage = lambda: storage
    context = _agent_context(restricted.get_container_file_path())

    first = ModelRequestStub([NamedTool("bash"), NamedTool("web_search")], context=context)
    assert _tool_names(middleware.wrap_model_call(first, lambda request: request)) == ["web_search"]

    storage._skills = [_skill("restricted", ["bash"])]
    second = ModelRequestStub([NamedTool("bash"), NamedTool("web_search")], context=context)
    assert _tool_names(middleware.wrap_model_call(second, lambda request: request)) == ["bash"]
    assert storage.load_calls == 2


def test_tool_call_without_matching_model_decision_revalidates_registry():
    restricted = _skill("restricted", ["web_search"])
    storage = StorageStub([restricted])
    middleware = _middleware([])
    middleware._storage = lambda: storage
    request = ToolRequestStub(
        "task",
        context=_agent_context(restricted.get_container_file_path()),
    )

    result = middleware.wrap_tool_call(request, lambda _: "executed")

    assert result.status == "error"
    assert storage.load_calls == 1


def test_active_policy_load_failure_fails_closed_to_framework_tools():
    middleware = _middleware([])

    def fail_storage():
        raise RuntimeError("storage unavailable")

    middleware._storage = fail_storage
    request = ModelRequestStub(
        [
            NamedTool("task"),
            NamedTool("read_file"),
            NamedTool("review_skill_package"),
            NamedTool("tool_search"),
            NamedTool("describe_skill"),
            NamedTool("activate_skill"),
        ],
        context=_agent_context("/mnt/skills/public/restricted/SKILL.md"),
    )

    assert _tool_names(middleware._filter_model_request(request)) == [
        "read_file",
        "review_skill_package",
        "tool_search",
        "describe_skill",
        "activate_skill",
    ]
