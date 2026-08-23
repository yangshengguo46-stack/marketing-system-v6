from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from langchain.agents.middleware.types import ModelRequest, ModelResponse
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from deerflow.agents.middlewares.context_manifest_middleware import ContextManifestMiddleware
from deerflow.agents.middlewares.user_profile_middleware import (
    USER_PROFILE_PROJECTION_MAX_BYTES,
    UserProfileMiddleware,
)
from deerflow.agents.user_profile import FileUserProfileStore, UserProfileMutationSource
from deerflow.config.paths import Paths
from deerflow.runtime.secret_context import (
    read_user_profile_projection,
    redact_secret_context_keys,
    write_user_profile_projection,
)


def _source(index: int) -> UserProfileMutationSource:
    return UserProfileMutationSource(
        thread_id="thread-1",
        run_id="run-1",
        message_id=f"message-{index}",
        message_sha256="a" * 64,
        excerpt_sha256=(f"{index:064x}"[-64:]),
        recorded_at=datetime(2026, 8, 23, 8, index % 60, tzinfo=UTC),
    )


def _request() -> ModelRequest:
    return ModelRequest(
        model=FakeMessagesListChatModel(responses=[AIMessage(content="ok")]),
        system_message=SystemMessage(content="system"),
        messages=[HumanMessage(content="当前请求")],
        tools=[],
        state={},
        runtime=SimpleNamespace(context={}),
    )


def test_profile_projection_is_hidden_bounded_escaped_and_before_current_request(tmp_path) -> None:
    store = FileUserProfileStore(Paths(tmp_path))
    first = store.remember(
        "user-a",
        kind="background",
        statement="我不懂 <code> & 英文",
        source=_source(1),
    )
    for index in range(2, 15):
        store.remember(
            "user-a",
            kind="collaboration_preference",
            statement=(f"这是第 {index} 条稳定协作偏好：" + "直接行动" * 25),
            source=_source(index),
        )

    middleware = UserProfileMiddleware(
        user_id="user-a",
        store=store,
        owner_token="profile-owner",
    )
    captured: list[ModelRequest] = []

    def handler(request: ModelRequest) -> ModelResponse:
        captured.append(request)
        return ModelResponse(result=[AIMessage(content="ok")])

    original = _request()
    middleware.wrap_model_call(original, handler)

    assert original.messages == [HumanMessage(content="当前请求")]
    injected = captured[0]
    assert injected.messages[-1].content == "当前请求"
    profile_message = injected.messages[0]
    assert isinstance(profile_message, HumanMessage)
    assert profile_message.additional_kwargs["hide_from_ui"] is True
    assert profile_message.additional_kwargs["user_profile_context"] is True
    assert "user_profile_owner_token" not in profile_message.additional_kwargs
    assert profile_message.additional_kwargs["user_profile_version"] == 14
    assert profile_message.additional_kwargs["user_profile_sha256"] == store.load("user-a").content_sha256
    assert first.item_id in profile_message.content
    assert "&lt;code&gt; &amp;" in profile_message.content
    assert len(profile_message.content.encode("utf-8")) <= USER_PROFILE_PROJECTION_MAX_BYTES
    assert profile_message.additional_kwargs["user_profile_omitted_count"] > 0
    assert read_user_profile_projection(injected.runtime.context, owner_token="profile-owner") == {
        "version": 14,
        "content_sha256": store.load("user-a").content_sha256,
        "item_count": 14,
        "projected_item_count": profile_message.additional_kwargs["user_profile_projected_count"],
        "omitted_item_count": profile_message.additional_kwargs["user_profile_omitted_count"],
    }


def test_missing_or_invalid_profile_fails_open_without_injecting_context(tmp_path) -> None:
    store = FileUserProfileStore(Paths(tmp_path))
    middleware = UserProfileMiddleware(user_id="user-a", store=store, owner_token="profile-owner")
    seen: list[ModelRequest] = []
    request = _request()
    write_user_profile_projection(
        request.runtime.context,
        owner_token="profile-owner",
        version=1,
        content_sha256="a" * 64,
        item_count=1,
        projected_item_count=1,
        omitted_item_count=0,
    )

    middleware.wrap_model_call(request, lambda injected: seen.append(injected) or ModelResponse(result=[AIMessage(content="ok")]))

    assert seen[0].messages == [HumanMessage(content="当前请求")]
    assert read_user_profile_projection(request.runtime.context, owner_token="profile-owner") is None


def test_profile_projection_internal_metadata_is_redacted_from_observable_context() -> None:
    context: dict = {"thread_id": "thread-1"}
    write_user_profile_projection(
        context,
        owner_token="profile-owner",
        version=2,
        content_sha256="b" * 64,
        item_count=3,
        projected_item_count=2,
        omitted_item_count=1,
    )

    assert read_user_profile_projection(context, owner_token="wrong-owner") is None
    assert redact_secret_context_keys(context) == {"thread_id": "thread-1"}


def test_profile_projection_and_manifest_observe_the_same_authenticated_revision(tmp_path) -> None:
    store = FileUserProfileStore(Paths(tmp_path))
    revision = store.remember(
        "user-a",
        kind="collaboration_preference",
        statement="先给结论，再讲代码",
        source=_source(1),
    ).revision
    journal = Mock()
    request = _request()
    request.runtime.context["__run_journal"] = journal
    profile = UserProfileMiddleware(user_id="user-a", store=store, owner_token="profile-owner")
    manifest = ContextManifestMiddleware(
        agent_name=None,
        activation_owner_token="skill-owner",
        user_profile_owner_token="profile-owner",
    )

    profile.wrap_model_call(
        request,
        lambda injected: manifest.wrap_model_call(
            injected,
            lambda _final: ModelResponse(result=[AIMessage(content="ok")]),
        ),
    )

    recorded = journal.record_context_manifest.call_args.args[0]
    assert recorded["user_profile"] == {
        "present": True,
        "version": revision.version,
        "content_sha256": revision.content_sha256,
        "item_count": 1,
        "projected_item_count": 1,
        "omitted_item_count": 0,
    }
    assert recorded["context_layers"]["user_profile"]["message_count"] == 1


@pytest.mark.asyncio
async def test_async_profile_projection_preserves_the_handler_response(tmp_path) -> None:
    store = FileUserProfileStore(Paths(tmp_path))
    store.remember(
        "user-a",
        kind="communication_preference",
        statement="请用中文",
        source=_source(1),
    )
    middleware = UserProfileMiddleware(user_id="user-a", store=store, owner_token="profile-owner")
    expected = ModelResponse(result=[AIMessage(content="ok")])

    async def handler(request: ModelRequest) -> ModelResponse:
        assert request.messages[0].additional_kwargs["user_profile_context"] is True
        return expected

    assert await middleware.awrap_model_call(_request(), handler) is expected
