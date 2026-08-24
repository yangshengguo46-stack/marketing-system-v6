"""Enforce run-shared tool-call budgets declared by an active Skill."""

from __future__ import annotations

import asyncio
import json
import logging
import posixpath
import secrets
import threading
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, override

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ModelCallResult, ModelRequest, ModelResponse
from langchain_core.messages import HumanMessage, ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.types import Command

from deerflow.runtime.secret_context import (
    SKILL_TOOL_CALL_BUDGET_CONTEXT_KEY,
    SKILL_TOOL_CALL_BUDGET_SCOPE_CONTEXT_KEY,
    read_agent_skill_source_path,
    read_slash_skill_source_path,
)
from deerflow.skills.storage import get_or_new_skill_storage, get_or_new_user_skill_storage
from deerflow.skills.types import Skill, ToolCallBudget

if TYPE_CHECKING:
    from deerflow.config.app_config import AppConfig
    from deerflow.skills.storage.skill_storage import SkillStorage

logger = logging.getLogger(__name__)

_DECISION_VERSION = 2
_SCOPE_VERSION = 1
_SCOPE_TTL_SECONDS = 6 * 60 * 60
_MAX_SCOPES = 2048
_BUDGET_HINT_NAME = "skill_tool_budget"
_BUDGET_EXHAUSTED_MESSAGE = "The run budget for this tool is exhausted. Do not retry it. Continue with other available tools only when they can materially improve the answer; otherwise use collected evidence and state unknowns plainly."


def _budget_key(budget: ToolCallBudget) -> str:
    return json.dumps(list(budget.tools), ensure_ascii=True, separators=(",", ":"))


def _identity_component(value: object) -> str:
    return value if isinstance(value, str) else "" if value is None else str(value)


def _run_identity(context: dict[str, Any]) -> tuple[str, str, str] | None:
    run_id = context.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        return None
    user_id = _identity_component(context.get("user_id")) or "default"
    return (run_id, user_id, _identity_component(context.get("thread_id")))


@dataclass(frozen=True)
class _BudgetSpec:
    key: str
    tools: tuple[str, ...]
    max_calls: int


@dataclass
class _SkillLedger:
    budgets: dict[str, _BudgetSpec] = field(default_factory=dict)
    counts: dict[str, int] = field(default_factory=dict)
    notified: set[str] = field(default_factory=set)


@dataclass
class _RunScope:
    identity: tuple[str, str, str]
    skills: dict[str, _SkillLedger] = field(default_factory=dict)
    touched_at: float = field(default_factory=time.monotonic)


_REGISTRY_LOCK = threading.RLock()
_RUN_SCOPES: dict[str, _RunScope] = {}


def _cleanup_scopes_locked(now: float) -> None:
    expired = [token for token, scope in _RUN_SCOPES.items() if now - scope.touched_at > _SCOPE_TTL_SECONDS]
    for token in expired:
        _RUN_SCOPES.pop(token, None)
    while len(_RUN_SCOPES) >= _MAX_SCOPES:
        oldest = min(_RUN_SCOPES, key=lambda token: _RUN_SCOPES[token].touched_at)
        _RUN_SCOPES.pop(oldest, None)


def _carrier_for_scope(token: str, scope: _RunScope, paths: tuple[str, ...]) -> dict[str, Any]:
    run_id, user_id, thread_id = scope.identity
    return {
        "version": _SCOPE_VERSION,
        "token": token,
        "run_id": run_id,
        "user_id": user_id,
        "thread_id": thread_id,
        "active_paths": list(paths),
    }


def _scope_from_context_locked(context: dict[str, Any]) -> tuple[str, _RunScope, tuple[str, ...]] | None:
    identity = _run_identity(context)
    if identity is None:
        return None
    carrier = context.get(SKILL_TOOL_CALL_BUDGET_SCOPE_CONTEXT_KEY)
    if not isinstance(carrier, dict) or carrier.get("version") != _SCOPE_VERSION:
        return None
    token = carrier.get("token")
    if not isinstance(token, str) or not token:
        return None
    carrier_identity = (
        carrier.get("run_id"),
        carrier.get("user_id"),
        carrier.get("thread_id"),
    )
    if carrier_identity != identity:
        return None
    paths = carrier.get("active_paths")
    if not isinstance(paths, list) or not all(isinstance(path, str) and path for path in paths):
        return None
    scope = _RUN_SCOPES.get(token)
    if scope is None or scope.identity != identity:
        return None
    scope.touched_at = time.monotonic()
    return token, scope, tuple(paths)


def export_skill_tool_budget_scope(context: object) -> dict[str, Any] | None:
    """Return a validated opaque carrier for a native child agent."""

    if not isinstance(context, dict):
        return None
    with _REGISTRY_LOCK:
        resolved = _scope_from_context_locked(context)
        if resolved is None:
            return None
        token, scope, paths = resolved
        authorized_paths = tuple(path for path in paths if path in scope.skills)
        if not authorized_paths:
            return None
        return _carrier_for_scope(token, scope, authorized_paths)


class SkillToolBudgetMiddleware(AgentMiddleware[AgentState]):
    """Bound retries and concurrency without deciding what the Agent should do.

    The active Skill is frozen at each model step. Tool calls emitted by that
    step use the frozen decision even if an activation call runs in parallel.
    Ledgers are retained per Skill for the whole Run, and an opaque carrier lets
    native subagents reserve from the same process-local scope.
    """

    def __init__(
        self,
        *,
        available_skills: set[str] | None = None,
        app_config: AppConfig | None = None,
        user_id: str | None = None,
        slash_source_owner_token: str,
    ) -> None:
        super().__init__()
        if not isinstance(slash_source_owner_token, str) or not slash_source_owner_token:
            raise ValueError("slash_source_owner_token must be a non-empty string")
        self._available_skills = set(available_skills) if available_skills is not None else None
        self._app_config = app_config
        self._user_id = user_id
        self._slash_source_owner_token = slash_source_owner_token
        self._decision_owner_token = secrets.token_urlsafe(24)

    def _storage(self) -> SkillStorage:
        if self._user_id is not None:
            return get_or_new_user_skill_storage(self._user_id, app_config=self._app_config)
        if self._app_config is not None:
            return get_or_new_skill_storage(app_config=self._app_config)
        return get_or_new_skill_storage()

    @staticmethod
    def _context(request: ModelRequest | ToolCallRequest) -> dict[str, Any] | None:
        context = getattr(getattr(request, "runtime", None), "context", None)
        return context if isinstance(context, dict) else None

    def _active_path(self, request: ModelRequest | ToolCallRequest) -> str | None:
        context = self._context(request)
        slash_path = read_slash_skill_source_path(context, owner_token=self._slash_source_owner_token)
        if slash_path is not None:
            return slash_path
        return read_agent_skill_source_path(context, owner_token=self._slash_source_owner_token)

    def _active_skill(self, request: ModelRequest | ToolCallRequest) -> tuple[str, Skill] | None:
        path = self._active_path(request)
        if path is None:
            return None
        try:
            storage = self._storage()
            skills = storage.load_skills(enabled_only=False)
            container_root = storage.get_container_root()
        except Exception:
            logger.exception("Failed to load active Skill for tool-call budget")
            return None

        normalized_path = posixpath.normpath(path)
        for skill in skills:
            if posixpath.normpath(skill.get_container_file_path(container_root)) != normalized_path:
                continue
            if not skill.enabled:
                return None
            if self._available_skills is not None and skill.name not in self._available_skills:
                return None
            return normalized_path, skill
        return None

    @staticmethod
    def _register_skill_locked(scope: _RunScope, path: str, skill: Skill) -> None:
        ledger = scope.skills.setdefault(path, _SkillLedger())
        ledger.budgets = {
            _budget_key(budget): _BudgetSpec(
                key=_budget_key(budget),
                tools=tuple(budget.tools),
                max_calls=budget.max_calls,
            )
            for budget in skill.tool_call_budgets
        }

    def _prepare_decision(self, request: ModelRequest | ToolCallRequest) -> tuple[str, tuple[str, ...]] | None:
        context = self._context(request)
        identity = _run_identity(context) if context is not None else None
        if context is None or identity is None:
            return None

        active = self._active_skill(request)
        current_path = active[0] if active is not None and active[1].tool_call_budgets else None

        with _REGISTRY_LOCK:
            inherited: tuple[str, ...] = ()
            resolved = _scope_from_context_locked(context)
            if context.get("is_subagent") is True and resolved is not None:
                _, _, inherited = resolved

            if resolved is None:
                if current_path is None:
                    return None
                now = time.monotonic()
                _cleanup_scopes_locked(now)
                token = secrets.token_urlsafe(24)
                scope = _RunScope(identity=identity, touched_at=now)
                _RUN_SCOPES[token] = scope
            else:
                token, scope, _ = resolved

            if active is not None and active[1].tool_call_budgets:
                self._register_skill_locked(scope, active[0], active[1])

            own_paths = (current_path,) if current_path else ()
            paths = tuple(dict.fromkeys((*inherited, *own_paths)))
            paths = tuple(path for path in paths if path in scope.skills)
            if not paths:
                return None

            scope.touched_at = time.monotonic()
            context[SKILL_TOOL_CALL_BUDGET_CONTEXT_KEY] = {
                "version": _DECISION_VERSION,
                "owner_token": self._decision_owner_token,
                "scope_token": token,
                "paths": list(paths),
            }
            if context.get("is_subagent") is not True:
                context[SKILL_TOOL_CALL_BUDGET_SCOPE_CONTEXT_KEY] = _carrier_for_scope(token, scope, paths)
            return token, paths

    def _read_decision(self, request: ModelRequest | ToolCallRequest) -> tuple[str, tuple[str, ...]] | None:
        context = self._context(request)
        if context is None:
            return None
        decision = context.get(SKILL_TOOL_CALL_BUDGET_CONTEXT_KEY)
        if not isinstance(decision, dict):
            return None
        if decision.get("version") != _DECISION_VERSION or decision.get("owner_token") != self._decision_owner_token:
            return None
        token = decision.get("scope_token")
        paths = decision.get("paths")
        if not isinstance(token, str) or not isinstance(paths, list):
            return None
        if not all(isinstance(path, str) and path for path in paths):
            return None
        with _REGISTRY_LOCK:
            resolved = _scope_from_context_locked(context)
            if resolved is None or resolved[0] != token:
                return None
            scope = resolved[1]
            normalized_paths = tuple(path for path in paths if path in scope.skills)
            return (token, normalized_paths) if normalized_paths else None

    @staticmethod
    def _reserve(token: str, paths: tuple[str, ...], tool_name: str) -> bool:
        with _REGISTRY_LOCK:
            scope = _RUN_SCOPES.get(token)
            if scope is None:
                return True
            matches: list[tuple[_SkillLedger, _BudgetSpec]] = []
            for path in paths:
                ledger = scope.skills.get(path)
                if ledger is None:
                    continue
                matches.extend((ledger, budget) for budget in ledger.budgets.values() if tool_name in budget.tools)
            if not matches:
                return True
            if any(ledger.counts.get(budget.key, 0) >= budget.max_calls for ledger, budget in matches):
                return False
            for ledger, budget in matches:
                ledger.counts[budget.key] = ledger.counts.get(budget.key, 0) + 1
            scope.touched_at = time.monotonic()
            return True

    @staticmethod
    def _exhausted(token: str, paths: tuple[str, ...]) -> tuple[set[str], set[str]]:
        exhausted_tools: set[str] = set()
        newly_exhausted_tools: set[str] = set()
        with _REGISTRY_LOCK:
            scope = _RUN_SCOPES.get(token)
            if scope is None:
                return exhausted_tools, newly_exhausted_tools
            for path in paths:
                ledger = scope.skills.get(path)
                if ledger is None:
                    continue
                for budget in ledger.budgets.values():
                    if ledger.counts.get(budget.key, 0) < budget.max_calls:
                        continue
                    exhausted_tools.update(budget.tools)
                    if budget.key not in ledger.notified:
                        ledger.notified.add(budget.key)
                        newly_exhausted_tools.update(budget.tools)
            scope.touched_at = time.monotonic()
        return exhausted_tools, newly_exhausted_tools

    @staticmethod
    def _blocked_tool_message(request: ToolCallRequest) -> ToolMessage:
        return ToolMessage(
            content=_BUDGET_EXHAUSTED_MESSAGE,
            tool_call_id=str(request.tool_call.get("id") or "missing_tool_call_id"),
            name=str(request.tool_call.get("name") or "unknown_tool"),
            status="error",
        )

    def _filter_model_request(self, request: ModelRequest) -> ModelRequest:
        decision = self._prepare_decision(request)
        if decision is None:
            return request
        token, paths = decision
        exhausted_tools, newly_exhausted = self._exhausted(token, paths)
        if not exhausted_tools:
            return request

        tools = [tool for tool in request.tools if getattr(tool, "name", None) not in exhausted_tools]
        messages = list(request.messages)
        if newly_exhausted:
            messages.append(
                HumanMessage(
                    content=(
                        "[SKILL TOOL BUDGET] The run budget is exhausted for: "
                        f"{', '.join(sorted(newly_exhausted))}. Those tools are now unavailable. "
                        "Do not retry them. Continue with other available tools only when they can "
                        "materially improve the answer; otherwise use collected evidence and state unknowns."
                    ),
                    name=_BUDGET_HINT_NAME,
                    additional_kwargs={"hide_from_ui": True},
                )
            )
        return request.override(tools=tools, messages=messages)

    def _reserve_request(self, request: ToolCallRequest) -> bool:
        decision = self._read_decision(request)
        if decision is None:
            decision = self._prepare_decision(request)
        if decision is None:
            return True
        token, paths = decision
        return self._reserve(token, paths, str(request.tool_call.get("name") or ""))

    @override
    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelCallResult:
        return handler(self._filter_model_request(request))

    @override
    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelCallResult:
        filtered = await asyncio.to_thread(self._filter_model_request, request)
        return await handler(filtered)

    @override
    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Command],
    ) -> ToolMessage | Command:
        if not self._reserve_request(request):
            return self._blocked_tool_message(request)
        return handler(request)

    @override
    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command]],
    ) -> ToolMessage | Command:
        allowed = await asyncio.to_thread(self._reserve_request, request)
        if not allowed:
            return self._blocked_tool_message(request)
        return await handler(request)
