"""Middleware for user slash and Agent-selected task-scoped Skill activation."""

from __future__ import annotations

import asyncio
import hashlib
import html
import logging
import posixpath
import uuid
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, override

from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ModelRequest, ModelResponse
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.types import Command

from deerflow.runtime.events.catalog import (
    MIDDLEWARE_SKILL_ACTIVATION_TAG,
    MIDDLEWARE_SKILL_SECRETS_TAG,
)
from deerflow.runtime.secret_context import (
    _SECRETS_BINDING_AUDIT_KEY,
    _SLASH_SKILL_ACTIVATION_RUN_KEY,
    ACTIVE_SECRETS_CONTEXT_KEY,
    extract_request_secrets,
    read_agent_skill_source_path,
    read_slash_skill_source_path,
    write_agent_skill_source_path,
    write_slash_skill_source_path,
)
from deerflow.skills.describe import SKILL_ACTIVATION_ENTRY_KEY
from deerflow.skills.slash import parse_slash_skill_reference, resolve_slash_skill
from deerflow.skills.storage import get_or_new_skill_storage, get_or_new_user_skill_storage
from deerflow.skills.storage.skill_storage import SkillStorage
from deerflow.skills.types import SKILL_MD_FILE, SecretRequirement, Skill, SkillCategory
from deerflow.utils.messages import get_original_user_content_text, is_real_user_message

if TYPE_CHECKING:
    from deerflow.config.app_config import AppConfig

logger = logging.getLogger(__name__)

_SLASH_SKILL_ACTIVATION_KEY = "slash_skill_activation"
_SLASH_SKILL_ACTIVATION_TARGET_ID_KEY = "slash_skill_activation_target_id"
_AGENT_ACTIVATION_TOOL_NAME = "activate_skill"
_ACTIVE_SKILL_CONTEXT_KEY = "active_skill_context"

# _SECRETS_BINDING_AUDIT_KEY: last audited binding (skill and secret names only,
# never values) so unchanged bindings are not re-recorded each call.
# The shared slash-source context contract holds the latest slash activation,
# ONLY the activated skill's canonical container path (never its declared
# secrets — those are read from the live registry on each call, #3938). The
# injection set is recomputed every model call, but a slash-activated skill must
# stay bound for the rest of the run — the model's tool loop issues many model
# calls after the single activation call (#3861 semantics).
# _SLASH_SKILL_ACTIVATION_RUN_KEY: identity of the slash message already activated
# in this run, so the reminder injection + skill disk read + "activate" audit event
# fire once per user slash command instead of on every model call. The reminder is
# added via request.override(messages=...) for a single model call and never
# persisted to graph state, so the 2nd..Nth model call of a turn rebuilds
# request.messages from state without it — the run context is the only signal that
# survives the tool loop. All three live in secret_context so they are covered by
# REDACTED_CONTEXT_KEYS in one place.


@dataclass(frozen=True, slots=True)
class _Activation:
    skill_name: str
    category: str
    container_file_path: str
    skill_content: str
    content_hash: str
    remaining_text: str
    editable: bool
    required_secrets: tuple[SecretRequirement, ...] = ()


@dataclass(frozen=True, slots=True)
class _ActivationResolution:
    activation: _Activation | None = None
    failure_message: str | None = None


def is_slash_skill_activation_reminder(message: object) -> bool:
    """Return whether a message is hidden slash-skill activation context."""
    return isinstance(message, HumanMessage) and bool(message.additional_kwargs.get(_SLASH_SKILL_ACTIVATION_KEY))


def _is_user_activation_target(message: object) -> bool:
    return is_real_user_message(message)


class SkillActivationMiddleware(AgentMiddleware):
    """Inject full SKILL.md content when the user explicitly types /skill-name."""

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

    def _storage(self) -> SkillStorage:
        if self._user_id is not None:
            return get_or_new_user_skill_storage(self._user_id, app_config=self._app_config)
        if self._app_config is not None:
            return get_or_new_skill_storage(app_config=self._app_config)
        return get_or_new_skill_storage()

    @staticmethod
    def _read_skill_content(skill_file: Path, skills_root: Path, *, storage: SkillStorage | None = None) -> str:
        if skill_file.name != SKILL_MD_FILE:
            raise ValueError(f"Expected {SKILL_MD_FILE}, got {skill_file.name}")
        # Use the storage's path validation if available — UserScopedSkillStorage
        # stores custom skills in a per-user directory that is not a sub-path of
        # the global skills root, so the simple relative_to check would reject them.
        # Fall back to the relative_to check when the storage is a mock (e.g. tests)
        # that doesn't implement validate_skill_file_path.
        if storage is not None and hasattr(storage, "validate_skill_file_path"):
            resolved_file = storage.validate_skill_file_path(skill_file)
        else:
            resolved_file = skill_file.resolve()
            resolved_root = skills_root.resolve()
            try:
                resolved_file.relative_to(resolved_root)
            except ValueError as exc:
                raise ValueError("Resolved skill file must stay within the configured skills root.") from exc
        if not resolved_file.is_file():
            raise FileNotFoundError(resolved_file)
        return resolved_file.read_text(encoding="utf-8")

    def _resolve_activation(self, text: str) -> _ActivationResolution | None:
        reference = parse_slash_skill_reference(text)
        if reference is None:
            return None

        storage = self._storage()
        skills = storage.load_skills(enabled_only=False)
        skill = next((candidate for candidate in skills if candidate.name == reference.name), None)
        if skill is None:
            return _ActivationResolution(failure_message=f"Skill `/{reference.name}` is not installed.")
        if not skill.enabled:
            return _ActivationResolution(failure_message=f"Skill `/{reference.name}` is installed but disabled. Enable it before using slash activation.")
        if self._available_skills is not None and reference.name not in self._available_skills:
            return _ActivationResolution(failure_message=f"Skill `/{reference.name}` is not available for this agent.")

        resolved = resolve_slash_skill(
            text,
            skills,
            available_skills=self._available_skills,
            container_base_path=storage.get_container_root(),
        )
        if resolved is None:
            return _ActivationResolution(failure_message=f"Skill `/{reference.name}` could not be resolved.")

        try:
            skill_content = self._read_skill_content(resolved.skill.skill_file, storage.get_skills_root_path(), storage=storage)
        except (OSError, ValueError):
            logger.exception("Failed to read slash-activated skill %s", resolved.skill.name)
            return _ActivationResolution(failure_message=f"Skill `/{reference.name}` could not be loaded safely. Please check the skill installation.")

        content_hash = hashlib.sha256(skill_content.encode("utf-8")).hexdigest()
        # CUSTOM skills are editable; PUBLIC and LEGACY are read-only
        editable = resolved.skill.category == SkillCategory.CUSTOM
        return _ActivationResolution(
            activation=_Activation(
                skill_name=resolved.skill.name,
                category=str(resolved.skill.category),
                container_file_path=resolved.container_file_path,
                skill_content=skill_content,
                content_hash=content_hash,
                remaining_text=resolved.remaining_text,
                editable=editable,
                required_secrets=tuple(resolved.skill.required_secrets or ()),
            )
        )

    @staticmethod
    def _build_activation_reminder(activation: _Activation) -> str:
        user_request = activation.remaining_text or ("No additional task text was provided after the slash skill command. Ask the user what they want to do with this skill if the next step is unclear.")
        escaped_user_request = html.escape(user_request, quote=False)
        escaped_skill_content = html.escape(activation.skill_content, quote=False)
        escaped_skill_name = html.escape(activation.skill_name, quote=True)
        escaped_category = html.escape(activation.category, quote=True)
        escaped_path = html.escape(activation.container_file_path, quote=True)
        escaped_content_hash = html.escape(activation.content_hash, quote=True)
        editable_str = "true" if activation.editable else "false"
        return f"""<slash_skill_activation>
The user explicitly activated the `{escaped_skill_name}` skill for this turn.
Treat the task text as:
<user_request>
{escaped_user_request}
</user_request>

Follow this skill before choosing a general workflow. Load supporting resources from the same skill directory only when needed.

<skill name="{escaped_skill_name}" category="{escaped_category}" path="{escaped_path}" sha256="{escaped_content_hash}" editable="{editable_str}">
<skill_content encoding="xml-escaped">
{escaped_skill_content}
</skill_content>
</skill>
</slash_skill_activation>"""

    @staticmethod
    def _has_existing_activation_for_target(messages: list, target_index: int, target: HumanMessage) -> bool:
        if target_index <= 0:
            return False

        if target.id:
            for previous in messages[:target_index]:
                if not is_slash_skill_activation_reminder(previous):
                    continue
                target_id = previous.additional_kwargs.get(_SLASH_SKILL_ACTIVATION_TARGET_ID_KEY)
                if target_id == target.id or previous.id == f"{target.id}__slash_activation":
                    return True

        previous = messages[target_index - 1]
        return is_slash_skill_activation_reminder(previous)

    @staticmethod
    def _activation_run_key(target: HumanMessage) -> str:
        """Stable identity for a user slash message, used to activate once per run.

        Prefers the message id (LangGraph assigns and preserves a stable id once a
        message is in graph state); falls back to a digest of the genuine user text
        so an id-less message still dedupes within a run. A new user slash message
        (new id / new text) yields a new key, so it is not suppressed.
        """
        if target.id:
            return target.id
        content = get_original_user_content_text(target.content, target.additional_kwargs)
        return "sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest()

    @staticmethod
    def _run_context(request: ModelRequest) -> dict | None:
        runtime = getattr(request, "runtime", None)
        context = getattr(runtime, "context", None)
        return context if isinstance(context, dict) else None

    @staticmethod
    def _already_activated(run_context: dict | None, run_key: str) -> bool:
        """Whether ``run_key`` was already recorded as activated earlier in this run.

        Sibling to ``_has_existing_activation_for_target``: that helper catches an
        activation reminder still present in the scanned ``messages`` window; this
        one catches a prior activation recorded on ``run_context`` whose reminder
        already fell out of that window (the tool-loop case — see
        ``_SLASH_SKILL_ACTIVATION_RUN_KEY``). ``run_key`` is computed once by the
        caller (``_find_activation_target``) and reused as-is at the write site in
        ``_prepare_model_request``, so the same key is always used to check and to
        record — this helper only ever checks membership, never computes the key.
        """
        return isinstance(run_context, dict) and run_context.get(_SLASH_SKILL_ACTIVATION_RUN_KEY) == run_key

    def _find_activation_target(self, messages: list, *, run_context: dict | None = None) -> tuple[int, HumanMessage, _ActivationResolution, str] | None:
        if not messages:
            return None

        target_index = next((idx for idx in range(len(messages) - 1, -1, -1) if _is_user_activation_target(messages[idx])), None)
        if target_index is None:
            return None

        target = messages[target_index]
        if target is None:
            return None
        if self._has_existing_activation_for_target(messages, target_index, target):
            return None
        # This exact slash message may have already activated earlier in the run.
        # The message scan above cannot catch it because the reminder lives only in
        # a per-call request override, never in state — the run context is the
        # durable signal (see _already_activated / _SLASH_SKILL_ACTIVATION_RUN_KEY).
        # Skipping here avoids the redundant skill disk read, reminder re-injection,
        # and duplicate "activate" audit. run_key is computed once here and threaded
        # through to the write site in _prepare_model_request.
        run_key = self._activation_run_key(target)
        if self._already_activated(run_context, run_key):
            return None

        content = get_original_user_content_text(target.content, target.additional_kwargs)
        resolution = self._resolve_activation(content)
        if resolution is None:
            return None
        return target_index, target, resolution, run_key

    @staticmethod
    def _record_activation(request: ModelRequest | ToolCallRequest, activation: _Activation, *, hook: str, mode: str = "slash") -> None:
        runtime = getattr(request, "runtime", None)
        context = getattr(runtime, "context", None)
        journal = context.get("__run_journal") if isinstance(context, dict) else None
        if journal is None:
            return
        try:
            journal.record_middleware(
                MIDDLEWARE_SKILL_ACTIVATION_TAG,
                name="SkillActivationMiddleware",
                hook=hook,
                action="activate",
                changes={
                    "mode": mode,
                    "skill_name": activation.skill_name,
                    "category": activation.category,
                    "path": activation.container_file_path,
                    "content_hash": activation.content_hash,
                },
            )
        except Exception:
            logger.warning("Failed to record skill activation audit event", exc_info=True)

    @staticmethod
    def _activation_tool_error(request: ToolCallRequest, content: str) -> ToolMessage:
        return ToolMessage(
            content=f"Error: {content}",
            tool_call_id=str(request.tool_call.get("id") or "missing_tool_call_id"),
            name=_AGENT_ACTIVATION_TOOL_NAME,
            status="error",
        )

    @staticmethod
    def _activation_tool_message(result: ToolMessage | Command) -> ToolMessage | None:
        if isinstance(result, ToolMessage):
            return result if result.name == _AGENT_ACTIVATION_TOOL_NAME else None
        if not isinstance(result, Command) or not isinstance(result.update, dict):
            return None
        messages = result.update.get("messages")
        if not isinstance(messages, list) or len(messages) != 1:
            return None
        message = messages[0]
        return message if isinstance(message, ToolMessage) and message.name == _AGENT_ACTIVATION_TOOL_NAME else None

    def _consume_agent_activation_result(
        self,
        request: ToolCallRequest,
        result: ToolMessage | Command,
        *,
        hook: str,
    ) -> ToolMessage | Command:
        if str(request.tool_call.get("name") or "") != _AGENT_ACTIVATION_TOOL_NAME:
            return result

        context = getattr(getattr(request, "runtime", None), "context", None)
        if not isinstance(context, dict):
            return self._activation_tool_error(request, "runtime context is unavailable; Skill was not activated.")
        if read_slash_skill_source_path(context, owner_token=self._slash_source_owner_token) is not None:
            return self._activation_tool_error(request, "the user already selected a /skill for this run; autonomous activation cannot replace it.")

        message = self._activation_tool_message(result)
        if message is None:
            return self._activation_tool_error(request, "activate_skill returned an invalid result; Skill was not activated.")
        if getattr(message, "status", "success") == "error":
            return result
        marker = message.additional_kwargs.get(SKILL_ACTIVATION_ENTRY_KEY)
        if not isinstance(marker, Mapping):
            return self._activation_tool_error(request, "activate_skill result omitted its activation marker.")

        called_args = request.tool_call.get("args")
        called_name = called_args.get("name") if isinstance(called_args, dict) else None
        name = marker.get("name")
        path = marker.get("path")
        content_hash = marker.get("sha256")
        if not all(isinstance(value, str) and value for value in (called_name, name, path, content_hash)) or name != called_name:
            return self._activation_tool_error(request, "activate_skill result did not match the requested exact Skill name.")

        registry = self._load_skill_registry_by_path()
        if registry is None:
            return self._activation_tool_error(request, "the live Skill registry is unavailable; Skill was not activated.")
        skill = self._resolve_registry_skill_reference(registry, path)
        if skill is None or skill.name != name:
            return self._activation_tool_error(request, "the selected Skill is disabled, unavailable, or outside this Agent's allowlist.")
        try:
            live_content = skill.skill_file.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            logger.exception("Failed to revalidate Agent-activated Skill %s", name)
            return self._activation_tool_error(request, "the selected Skill could not be revalidated from disk.")
        live_hash = hashlib.sha256(live_content.encode("utf-8")).hexdigest()
        if live_hash != content_hash:
            return self._activation_tool_error(request, "the selected Skill changed while it was being activated; inspect it again.")

        write_agent_skill_source_path(context, path, owner_token=self._slash_source_owner_token)
        activation = _Activation(
            skill_name=skill.name,
            category=str(skill.category),
            container_file_path=path,
            skill_content=live_content,
            content_hash=live_hash,
            remaining_text="",
            editable=skill.category == SkillCategory.CUSTOM,
            required_secrets=tuple(skill.required_secrets or ()),
        )
        self._record_activation(request, activation, hook=hook, mode="agent")
        return result

    def _prepare_model_request(self, request: ModelRequest, *, hook: str) -> tuple[ModelRequest | AIMessage | None, _Activation | None]:
        run_context = self._run_context(request)
        target_and_resolution = self._find_activation_target(list(request.messages), run_context=run_context)
        if target_and_resolution is None:
            return None, None

        target_index, target, resolution, run_key = target_and_resolution
        if resolution.failure_message:
            return AIMessage(content=resolution.failure_message), None

        activation = resolution.activation
        if activation is None:
            return None, None

        logger.info(
            "SkillActivationMiddleware: activating slash skill %s category=%s path=%s hash=%s",
            activation.skill_name,
            activation.category,
            activation.container_file_path,
            activation.content_hash,
        )
        self._record_activation(request, activation, hook=hook)
        # Mark this slash message as activated for the run so the tool loop's later
        # model calls skip the redundant re-activation (#3861: one activation call,
        # many follow-up model calls). A new user slash message keys differently and
        # still activates. Overwrite (`=`), not append/accumulate, is intentional:
        # _find_activation_target only ever considers the latest real user message as
        # an activation target, so there is nothing earlier in the run worth
        # remembering once a new activation replaces it — do not "fix" this into a
        # set. run_key is the same value already checked in _find_activation_target
        # (computed once there, threaded through here) rather than recomputed.
        if run_context is not None:
            run_context[_SLASH_SKILL_ACTIVATION_RUN_KEY] = run_key
        activation_msg = self._make_activation_message(target, self._build_activation_reminder(activation))
        messages = list(request.messages)
        messages.insert(target_index, activation_msg)
        return request.override(messages=messages), activation

    def _handle_model_request(self, request: ModelRequest, *, hook: str) -> ModelRequest | AIMessage:
        prepared, activation = self._prepare_model_request(request, hook=hook)
        if isinstance(prepared, AIMessage):
            return prepared
        effective = prepared if prepared is not None else request
        if activation is None:
            effective = self._inject_active_skill_context(effective)
        self._resolve_secret_bindings(effective, activation, hook=hook)
        return effective

    @staticmethod
    def _contains_activation_body(messages: list, activation: _Activation) -> bool:
        for message in messages:
            if not isinstance(message, ToolMessage) or message.name != _AGENT_ACTIVATION_TOOL_NAME:
                continue
            marker = message.additional_kwargs.get(SKILL_ACTIVATION_ENTRY_KEY)
            if not isinstance(marker, Mapping):
                continue
            if marker.get("path") == activation.container_file_path and marker.get("sha256") == activation.content_hash:
                return True
        return False

    def _active_activation_from_context(self, request: ModelRequest) -> tuple[_Activation, str] | None:
        context = getattr(getattr(request, "runtime", None), "context", None)
        if not isinstance(context, dict):
            return None
        slash_path = read_slash_skill_source_path(context, owner_token=self._slash_source_owner_token)
        agent_path = read_agent_skill_source_path(context, owner_token=self._slash_source_owner_token)
        path = slash_path or agent_path
        mode = "slash" if slash_path else "agent"
        if path is None:
            return None

        registry = self._load_skill_registry_by_path()
        if registry is None:
            return None
        skill = self._resolve_registry_skill_reference(registry, path)
        if skill is None:
            return None
        try:
            content = skill.skill_file.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            logger.exception("Failed to reload active Skill context %s", skill.name)
            return None
        return (
            _Activation(
                skill_name=skill.name,
                category=str(skill.category),
                container_file_path=path,
                skill_content=content,
                content_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
                remaining_text="",
                editable=skill.category == SkillCategory.CUSTOM,
                required_secrets=tuple(skill.required_secrets or ()),
            ),
            mode,
        )

    @staticmethod
    def _build_active_skill_context(activation: _Activation, *, mode: str) -> str:
        escaped_name = html.escape(activation.skill_name, quote=True)
        escaped_path = html.escape(activation.container_file_path, quote=True)
        escaped_hash = html.escape(activation.content_hash, quote=True)
        escaped_mode = html.escape(mode, quote=True)
        escaped_content = html.escape(activation.skill_content, quote=False)
        return f"""<active_skill_context name="{escaped_name}" path="{escaped_path}" sha256="{escaped_hash}" mode="{escaped_mode}">
This Skill is active only for the current run. Apply it with judgment; user facts and higher-level boundaries still govern.
<skill_content encoding="xml-escaped">
{escaped_content}
</skill_content>
</active_skill_context>"""

    def _inject_active_skill_context(self, request: ModelRequest) -> ModelRequest:
        resolved = self._active_activation_from_context(request)
        if resolved is None:
            return request
        activation, mode = resolved
        messages = list(request.messages)
        if mode == "agent" and self._contains_activation_body(messages, activation):
            return request

        insertion_index = 0
        while insertion_index < len(messages) and isinstance(messages[insertion_index], SystemMessage):
            insertion_index += 1
        messages.insert(
            insertion_index,
            HumanMessage(
                content=self._build_active_skill_context(activation, mode=mode),
                additional_kwargs={
                    "hide_from_ui": True,
                    _ACTIVE_SKILL_CONTEXT_KEY: True,
                },
            ),
        )
        return request.override(messages=messages)

    def _resolve_secret_bindings(self, request: ModelRequest, activation: _Activation | None, *, hook: str) -> None:
        """Recompute the per-run secret injection set (binding point A+, #3861/#3914).

        Sources, unioned on every model call:

        - the most recent slash activation of this run (persisted as a source on
          the run context so the whole tool loop after the activation call keeps
          the binding — a new slash activation replaces it). The slash source is
          validated once, at activation (enabled + allowlist checks in
          ``_resolve_activation``), and deliberately NOT re-validated per call:
          slash is a run-scoped commitment made by the user, and it dies with
          the run anyway;
        - the latest Skill selected by ``activate_skill`` in this run,
          re-validated against the live registry on each call: enabled,
          runtime-allowed for this agent, and not opted out via
          ``secrets-autonomous: false``. Slash activation dominates and is
          exempt from the opt-out because it is the explicit user ceremony.

        The set is recomputed and REPLACED each call, so ending the run or a
        caller that stops supplying a value loses its injection automatically.
        Injected values always come
        from the caller's request (``context.secrets``) — never the host
        environment, which ``env_policy.build_sandbox_env`` scrubs before
        injection — so a skill can never harvest a host platform credential.
        Secret *values* are never logged; the audit journal records names only.
        """
        runtime = getattr(request, "runtime", None)
        context = getattr(runtime, "context", None)
        if not isinstance(context, dict):
            return

        # The slash source records the canonical container path plus a
        # middleware-chain-local owner token — never declared secrets. Both
        # consumers authenticate the source and resolve the live registry skill
        # by path, so caller-mergeable context cannot forge an activation.
        if activation is not None:
            write_slash_skill_source_path(
                context,
                activation.container_file_path,
                owner_token=self._slash_source_owner_token,
            )

        request_secrets = extract_request_secrets(context)
        sources: list[tuple[str, tuple[SecretRequirement, ...]]] = []
        if request_secrets:
            registry = self._load_skill_registry_by_path()
            if registry is not None:
                # Slash source: exempt from the ``secrets-autonomous`` opt-out
                # (explicit ceremony), but still enabled + allowlist checked.
                slash_path = read_slash_skill_source_path(context, owner_token=self._slash_source_owner_token)
                slash_skill = self._resolve_registry_skill(registry, slash_path, require_autonomous=False)
                if slash_skill is not None:
                    sources.append((slash_skill.name, tuple(slash_skill.required_secrets)))
                else:
                    agent_path = read_agent_skill_source_path(context, owner_token=self._slash_source_owner_token)
                    agent_skill = self._resolve_registry_skill(registry, agent_path, require_autonomous=True)
                    if agent_skill is not None:
                        sources.append((agent_skill.name, tuple(agent_skill.required_secrets)))

        injected: dict[str, str] = {}
        bound_skills: set[str] = set()
        missing: dict[str, list[str]] = {}
        for skill_name, requirements in sources:
            for req in requirements:
                if req.name in request_secrets:
                    injected[req.name] = request_secrets[req.name]
                    bound_skills.add(skill_name)
                elif not req.optional:
                    missing.setdefault(skill_name, []).append(req.name)

        if injected:
            context[ACTIVE_SECRETS_CONTEXT_KEY] = injected
        else:
            context.pop(ACTIVE_SECRETS_CONTEXT_KEY, None)

        audit_state = {
            "skills": sorted(bound_skills),
            "secrets": sorted(injected),
            "missing": {name: sorted(values) for name, values in sorted(missing.items())},
        }
        previous = context.get(_SECRETS_BINDING_AUDIT_KEY)
        if previous == audit_state:
            return
        if previous is None and not injected and not missing:
            return
        context[_SECRETS_BINDING_AUDIT_KEY] = audit_state
        for skill_name, names in sorted(missing.items()):
            logger.warning(
                "Skill %s is active but required secrets are missing from the request context: %s",
                skill_name,
                ", ".join(names),
            )
        self._record_secret_binding(context, audit_state, hook=hook)

    def _load_skill_registry_by_path(self) -> dict[str, Skill] | None:
        """Load the live skill registry keyed by normalized container file path.

        Reloaded every call on purpose (not cached): load_skills re-reads the
        enabled state from extensions_config so an operator disabling a skill
        revokes its secret binding on the very next model call. A cache keyed on
        file mtimes would miss enable/disable toggles (which do not touch
        SKILL.md) and keep injecting after a disable — trading the
        immediate-revocation security property for speed. The cost is gated: the
        only caller runs this only when the caller supplied secrets.

        Paths are normalized so a non-canonical ``container_path`` config (e.g. a
        trailing slash) still matches the canonical path captured in
        the activation source. Returns ``None`` if the registry can't load —
        both the slash and Agent-selected sources then bind nothing for that call
        (fail closed). This is a deliberate availability-for-security trade-off:
        a transient registry read failure mid-run drops the injection for that
        call rather than trusting stale caller-supplied data.
        """
        try:
            storage = self._storage()
            skills = storage.load_skills(enabled_only=False)
            container_root = storage.get_container_root()
        except Exception:
            logger.exception("Failed to load skills while resolving secret bindings")
            return None
        return {posixpath.normpath(skill.get_container_file_path(container_root)): skill for skill in skills}

    def _resolve_registry_skill_reference(self, registry: dict[str, Skill], path: object) -> Skill | None:
        """Resolve an enabled, agent-allowed Skill by canonical container path."""
        if not isinstance(path, str) or not path:
            return None
        skill = registry.get(posixpath.normpath(path))
        if skill is None or not skill.enabled:
            return None
        if self._available_skills is not None and skill.name not in self._available_skills:
            return None
        return skill

    def _resolve_registry_skill(self, registry: dict[str, Skill], path: object, *, require_autonomous: bool) -> Skill | None:
        """Resolve a container path to a live registry skill eligible for secret
        binding, or ``None``.

        Match strictly by normalized container file path — never by name. A
        by-name fallback would be a confused deputy: DeerFlow lets a custom skill
        shadow a same-named public/legacy one (load_skills de-dupes by name,
        custom wins), so a reference to public/foo could bind the custom foo's
        secrets. A path that does not resolve simply binds nothing (the safe
        direction), which also fails closed on a caller-forged path (#3938).

        Gates: the skill must be enabled, declare secrets, and be allowlisted for
        this agent. ``require_autonomous`` additionally enforces the
        ``secrets-autonomous`` opt-out for the Agent-selected path; the slash path
        passes ``False`` because explicit activation is the ceremony that opt-out
        is meant to preserve.
        """
        skill = self._resolve_registry_skill_reference(registry, path)
        if skill is None or not skill.required_secrets:
            return None
        if require_autonomous and not skill.secrets_autonomous:
            return None
        return skill

    @staticmethod
    def _record_secret_binding(context: dict, audit_state: dict, *, hook: str) -> None:
        journal = context.get("__run_journal")
        if journal is None:
            return
        try:
            journal.record_middleware(
                MIDDLEWARE_SKILL_SECRETS_TAG,
                name="SkillActivationMiddleware",
                hook=hook,
                action="bind_secrets",
                changes=audit_state,
            )
        except Exception:
            logger.warning("Failed to record skill secret binding audit event", exc_info=True)

    @staticmethod
    def _make_activation_message(target: HumanMessage, activation_content: str) -> HumanMessage:
        stable_id = target.id or str(uuid.uuid4())
        additional_kwargs = {
            "hide_from_ui": True,
            _SLASH_SKILL_ACTIVATION_KEY: True,
        }
        if target.id:
            additional_kwargs[_SLASH_SKILL_ACTIVATION_TARGET_ID_KEY] = target.id
        return HumanMessage(
            content=activation_content,
            id=f"{stable_id}__slash_activation",
            additional_kwargs=additional_kwargs,
        )

    @override
    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse | AIMessage:
        prepared = self._handle_model_request(request, hook="wrap_model_call")
        if isinstance(prepared, AIMessage):
            return prepared
        return handler(prepared)

    @override
    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse | AIMessage:
        prepared = await asyncio.to_thread(self._handle_model_request, request, hook="awrap_model_call")
        if isinstance(prepared, AIMessage):
            return prepared
        return await handler(prepared)

    @override
    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Command],
    ) -> ToolMessage | Command:
        if (
            str(request.tool_call.get("name") or "") == _AGENT_ACTIVATION_TOOL_NAME
            and read_slash_skill_source_path(
                getattr(getattr(request, "runtime", None), "context", None),
                owner_token=self._slash_source_owner_token,
            )
            is not None
        ):
            return self._activation_tool_error(request, "the user already selected a /skill for this run; autonomous activation cannot replace it.")
        return self._consume_agent_activation_result(request, handler(request), hook="wrap_tool_call")

    @override
    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command]],
    ) -> ToolMessage | Command:
        if (
            str(request.tool_call.get("name") or "") == _AGENT_ACTIVATION_TOOL_NAME
            and read_slash_skill_source_path(
                getattr(getattr(request, "runtime", None), "context", None),
                owner_token=self._slash_source_owner_token,
            )
            is not None
        ):
            return self._activation_tool_error(request, "the user already selected a /skill for this run; autonomous activation cannot replace it.")
        result = await handler(request)
        return self._consume_agent_activation_result(request, result, hook="awrap_tool_call")
