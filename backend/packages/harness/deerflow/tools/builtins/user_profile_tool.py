"""Explicit, source-bound user profile mutation for the Lead agent."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Literal

from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.types import Command

from deerflow.agents.user_profile import UserProfileKind, UserProfileMutationSource, get_user_profile_store
from deerflow.runtime.user_context import resolve_runtime_user_id
from deerflow.tools.types import Runtime


def _text_content(message: HumanMessage) -> str:
    if isinstance(message.content, str):
        return message.content
    parts: list[str] = []
    if isinstance(message.content, list):
        for block in message.content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and isinstance(block.get("text"), str):
                parts.append(block["text"])
    return "\n".join(parts)


def _latest_visible_user_message(runtime: Runtime) -> tuple[HumanMessage, str]:
    messages = runtime.state.get("messages", []) if runtime.state else []
    for message in reversed(messages):
        if not isinstance(message, HumanMessage):
            continue
        if message.additional_kwargs.get("hide_from_ui") is True:
            continue
        content = _text_content(message)
        if content:
            return message, content
    raise ValueError("no current visible user message is available as profile evidence")


def _context_text(runtime: Runtime, key: str) -> str | None:
    context = runtime.context if isinstance(runtime.context, dict) else {}
    value = context.get(key)
    return str(value) if value else None


def _result_message(runtime: Runtime, payload: dict[str, object] | str) -> Command:
    content = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return Command(update={"messages": [ToolMessage(content=content, tool_call_id=runtime.tool_call_id)]})


@tool("manage_user_profile", parse_docstring=True)
def manage_user_profile_tool(
    action: Literal["remember", "replace", "forget"],
    user_statement: str,
    runtime: Runtime,
    kind: UserProfileKind | None = None,
    item_id: str | None = None,
) -> Command:
    """Remember, correct, or forget one stable cross-project user profile item.

    Use only when the latest visible user message contains an exact excerpt
    stating a stable background fact or collaboration preference, or explicitly
    asks to correct/forget one. Pass that exact excerpt as ``user_statement``.
    Never store project, account, brand, product, audience, temporary-task,
    inferred, or permission-granting information.

    Args:
        action: ``remember`` creates an item, ``replace`` corrects ``item_id``, and ``forget`` removes ``item_id``.
        user_statement: Exact excerpt from the latest visible user message. For forget, use the user's deletion request.
        kind: Item kind for remember/replace; omit for forget.
        item_id: Existing profile item ID for replace/forget; omit for remember.
    """
    try:
        message, full_message = _latest_visible_user_message(runtime)
        exact_statement = user_statement.strip()
        if not exact_statement or exact_statement not in full_message:
            raise ValueError("user_statement must be an exact excerpt from the latest visible user message")
        if action in {"remember", "replace"} and kind is None:
            raise ValueError("kind is required for remember and replace")
        if action in {"replace", "forget"} and not item_id:
            raise ValueError("item_id is required for replace and forget")
        if action == "remember" and item_id is not None:
            raise ValueError("item_id must be omitted for remember")

        source = UserProfileMutationSource(
            thread_id=_context_text(runtime, "thread_id"),
            run_id=_context_text(runtime, "run_id"),
            message_id=str(message.id) if message.id else None,
            message_sha256=hashlib.sha256(full_message.encode("utf-8")).hexdigest(),
            excerpt_sha256=hashlib.sha256(exact_statement.encode("utf-8")).hexdigest(),
            recorded_at=datetime.now(UTC),
        )
        store = get_user_profile_store()
        user_id = resolve_runtime_user_id(runtime)
        current = store.load(user_id)
        expected_version = current.version if current is not None else 0
        if action == "remember":
            result = store.remember(
                user_id,
                kind=kind,
                statement=exact_statement,
                source=source,
                expected_version=expected_version,
            )
        elif action == "replace":
            result = store.replace(
                user_id,
                item_id=item_id or "",
                kind=kind,
                statement=exact_statement,
                source=source,
                expected_version=expected_version,
            )
        else:
            result = store.forget(
                user_id,
                item_id=item_id or "",
                source=source,
                expected_version=expected_version,
            )
        return _result_message(
            runtime,
            {
                "status": "updated" if result.changed else "unchanged",
                "action": action,
                "item_id": result.item_id,
                "profile_version": result.revision.version,
                "profile_sha256": result.revision.content_sha256,
            },
        )
    except Exception as exc:
        return _result_message(runtime, f"Error: {exc}")


__all__ = ["manage_user_profile_tool"]
