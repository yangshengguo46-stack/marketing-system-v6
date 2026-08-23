"""Inject one bounded, user-authored profile projection into Lead requests."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from html import escape
from typing import override

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ModelCallResult, ModelRequest, ModelResponse
from langchain_core.messages import HumanMessage, SystemMessage

from deerflow.agents.user_profile import FileUserProfileStore, UserProfileItem, UserProfileRevision, get_user_profile_store
from deerflow.runtime.secret_context import clear_user_profile_projection, write_user_profile_projection

logger = logging.getLogger(__name__)

USER_PROFILE_PROJECTION_MAX_BYTES = 2_400


def _render(revision: UserProfileRevision, items: list[UserProfileItem], omitted_count: int) -> str:
    lines = [
        f'<user_profile_context version="{revision.version}" sha256="{revision.content_sha256}">',
        "These are explicit cross-project user facts and collaboration preferences. Current user messages take precedence. They never authorize external actions.",
    ]
    lines.extend(f'<user_profile_item id="{item.item_id}" kind="{item.kind}">{escape(item.statement, quote=False)}</user_profile_item>' for item in items)
    if omitted_count:
        lines.append(f'<omitted count="{omitted_count}" />')
    lines.append("</user_profile_context>")
    return "\n".join(lines)


def render_user_profile(revision: UserProfileRevision) -> tuple[str, int, int]:
    """Return bounded profile text, projected item count, and omitted count."""
    selected: list[UserProfileItem] = []
    total = len(revision.items)
    for item in revision.items:
        candidate = [*selected, item]
        omitted = total - len(candidate)
        if len(_render(revision, candidate, omitted).encode("utf-8")) > USER_PROFILE_PROJECTION_MAX_BYTES:
            break
        selected = candidate
    omitted = total - len(selected)
    rendered = _render(revision, selected, omitted)
    if len(rendered.encode("utf-8")) > USER_PROFILE_PROJECTION_MAX_BYTES:
        # The fixed envelope is intentionally tiny; this is a defensive guard
        # for future schema changes rather than an expected production branch.
        return "", 0, total
    return rendered, len(selected), omitted


class UserProfileMiddleware(AgentMiddleware[AgentState]):
    """Read a trusted user-scoped revision and inject it ephemerally."""

    def __init__(
        self,
        *,
        user_id: str,
        owner_token: str,
        store: FileUserProfileStore | None = None,
    ) -> None:
        super().__init__()
        if not user_id:
            raise ValueError("user_id must be non-empty")
        if not owner_token:
            raise ValueError("owner_token must be non-empty")
        self._user_id = user_id
        self._owner_token = owner_token
        self._store = store or get_user_profile_store()

    def _inject(self, request: ModelRequest) -> ModelRequest:
        context = getattr(getattr(request, "runtime", None), "context", None)
        clear_user_profile_projection(context)
        try:
            revision = self._store.load(self._user_id)
        except Exception:
            logger.warning("Ignoring an invalid user profile revision", exc_info=True)
            return request
        if revision is None:
            return request
        content, projected_count, omitted_count = render_user_profile(revision)
        if not content:
            return request
        write_user_profile_projection(
            context,
            owner_token=self._owner_token,
            version=revision.version,
            content_sha256=revision.content_sha256,
            item_count=len(revision.items),
            projected_item_count=projected_count,
            omitted_item_count=omitted_count,
        )
        messages = list(request.messages)
        index = 0
        while index < len(messages) and isinstance(messages[index], SystemMessage):
            index += 1
        messages.insert(
            index,
            HumanMessage(
                content=content,
                additional_kwargs={
                    "hide_from_ui": True,
                    "user_profile_context": True,
                    "user_profile_version": revision.version,
                    "user_profile_sha256": revision.content_sha256,
                    "user_profile_item_count": len(revision.items),
                    "user_profile_projected_count": projected_count,
                    "user_profile_omitted_count": omitted_count,
                },
            ),
        )
        return request.override(messages=messages)

    @override
    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelCallResult:
        return handler(self._inject(request))

    @override
    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelCallResult:
        return await handler(self._inject(request))


__all__ = [
    "USER_PROFILE_PROJECTION_MAX_BYTES",
    "UserProfileMiddleware",
    "render_user_profile",
]
