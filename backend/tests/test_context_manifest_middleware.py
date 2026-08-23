from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from langchain.agents.middleware.types import ModelRequest, ModelResponse
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.tools import tool

from deerflow.agents.lead_agent.identity import PRODUCT_IDENTITY_ASSET
from deerflow.agents.middlewares.context_manifest_middleware import (
    CONTEXT_MANIFEST_VERSION,
    ContextManifestMiddleware,
    build_context_manifest,
)
from deerflow.runtime.secret_context import write_user_profile_projection


@tool
def _lookup(query: str) -> str:
    """Look up a public fact."""
    return query


def _request(*, context: dict | None = None, messages: list | None = None) -> ModelRequest:
    agent_name = "the user's new-media operations teammate"
    identity = PRODUCT_IDENTITY_ASSET.content.format(agent_name=agent_name)
    return ModelRequest(
        model=FakeMessagesListChatModel(responses=[AIMessage(content="ok")]),
        system_message=SystemMessage(content=f"{identity}\nSYSTEM-SECRET-SHOULD-NOT-BE-COPIED"),
        messages=messages
        or [
            HumanMessage(content="USER-SECRET-SHOULD-NOT-BE-COPIED"),
            HumanMessage(
                content="<memory>MEMORY-SECRET-SHOULD-NOT-BE-COPIED</memory>",
                additional_kwargs={"hide_from_ui": True, "dynamic_context_reminder": True},
            ),
            HumanMessage(
                content='<active_skill_context name="gift" path="/private/gift/SKILL.md" sha256="' + "a" * 64 + '" mode="agent">BODY</active_skill_context>',
                additional_kwargs={"hide_from_ui": True, "active_skill_context": True},
            ),
            HumanMessage(
                content="<durable_context_data>PRIVATE</durable_context_data>",
                additional_kwargs={"hide_from_ui": True, "durable_context_data": True},
            ),
        ],
        tools=[_lookup],
        state={
            "summary_text": "PRIVATE SUMMARY",
            "delegations": [{"id": "d1"}],
            "skill_context": [{"path": "/private/inspected/SKILL.md"}],
        },
        runtime=SimpleNamespace(context=context if context is not None else {}),
        model_settings={"temperature": 0.2},
    )


def test_manifest_accounts_for_identity_messages_tools_and_context_without_copying_content():
    request = _request(context={"secrets": {"API_KEY": "REQUEST-SECRET-SHOULD-NOT-BE-COPIED"}})

    manifest = build_context_manifest(
        request,
        call_index=1,
        agent_name=None,
        activation_owner_token="owner-token",
        outcome="success",
        response_usage={"input_tokens": 123, "output_tokens": 7, "total_tokens": 130},
    )

    assert manifest["version"] == CONTEXT_MANIFEST_VERSION == 1
    assert manifest["call_index"] == 1
    assert manifest["identity"] == {
        "present": True,
        "source": PRODUCT_IDENTITY_ASSET.source,
        "version": PRODUCT_IDENTITY_ASSET.version,
        "sha256": PRODUCT_IDENTITY_ASSET.sha256,
    }
    assert manifest["request"]["message_count"] == 5  # separate system message + four request messages
    assert manifest["request"]["by_role"]["system"]["count"] == 1
    assert manifest["request"]["by_role"]["human"]["count"] == 4
    assert manifest["request"]["tool_count"] == 1
    assert manifest["request"]["tools"][0]["name"] == "_lookup"
    assert manifest["request"]["tool_schema_utf8_bytes"] > 0
    assert manifest["request"]["estimated_payload_utf8_bytes"] > manifest["request"]["tool_schema_utf8_bytes"]
    assert manifest["context_layers"]["memory"]["message_count"] == 1
    assert manifest["context_layers"]["active_skill"]["message_count"] == 1
    assert manifest["context_layers"]["durable_context"]["message_count"] == 1
    assert manifest["state_projection"] == {
        "summary_present": True,
        "summary_utf8_bytes": len(b"PRIVATE SUMMARY"),
        "delegation_count": 1,
        "inspected_skill_count": 1,
    }
    assert manifest["response_usage"]["input_tokens"] == 123
    assert manifest["user_profile"] == {
        "present": False,
        "version": None,
        "content_sha256": None,
        "item_count": 0,
        "projected_item_count": 0,
        "omitted_item_count": 0,
    }

    serialized = json.dumps(manifest, ensure_ascii=False, sort_keys=True)
    for forbidden in (
        "SYSTEM-SECRET",
        "USER-SECRET",
        "MEMORY-SECRET",
        "REQUEST-SECRET",
        "PRIVATE SUMMARY",
        "/private/",
        "Look up a public fact",
    ):
        assert forbidden not in serialized


def test_manifest_reports_authenticated_run_scoped_activation_without_local_path():
    from deerflow.runtime.secret_context import write_agent_skill_source_path

    context: dict = {}
    write_agent_skill_source_path(context, "/mnt/skills/public/gift/SKILL.md", owner_token="owner-token")

    manifest = build_context_manifest(
        _request(context=context),
        call_index=2,
        agent_name=None,
        activation_owner_token="owner-token",
        outcome="success",
    )

    assert manifest["skill_activation"] == {
        "mode": "agent",
        "skill_name": "gift",
        "content_sha256": "a" * 64,
    }
    assert "/mnt/skills" not in json.dumps(manifest)


def test_manifest_reports_authenticated_profile_counts_without_content_or_owner_token():
    context: dict = {}
    write_user_profile_projection(
        context,
        owner_token="profile-owner",
        version=3,
        content_sha256="c" * 64,
        item_count=5,
        projected_item_count=4,
        omitted_item_count=1,
    )
    request = _request(
        context=context,
        messages=[
            HumanMessage(
                content="PROFILE-CONTENT-SHOULD-NOT-BE-COPIED",
                additional_kwargs={"hide_from_ui": True, "user_profile_context": True},
            ),
            HumanMessage(content="current request"),
        ],
    )

    manifest = build_context_manifest(
        request,
        call_index=1,
        agent_name=None,
        activation_owner_token="owner-token",
        user_profile_owner_token="profile-owner",
        outcome="success",
    )

    assert manifest["context_layers"]["user_profile"]["message_count"] == 1
    assert manifest["user_profile"] == {
        "present": True,
        "version": 3,
        "content_sha256": "c" * 64,
        "item_count": 5,
        "projected_item_count": 4,
        "omitted_item_count": 1,
    }
    serialized = json.dumps(manifest, ensure_ascii=False)
    assert "PROFILE-CONTENT" not in serialized
    assert "profile-owner" not in serialized

    forged = build_context_manifest(
        request,
        call_index=2,
        agent_name=None,
        activation_owner_token="owner-token",
        user_profile_owner_token="wrong-owner",
        outcome="success",
    )
    assert forged["user_profile"]["present"] is False


def test_middleware_records_each_successful_model_call_with_provider_usage():
    journal = Mock()
    context = {"__run_journal": journal}
    middleware = ContextManifestMiddleware(agent_name=None, activation_owner_token="owner-token")

    def handler(_request):
        return ModelResponse(
            result=[
                AIMessage(
                    content="answer",
                    usage_metadata={
                        "input_tokens": 222,
                        "output_tokens": 11,
                        "total_tokens": 233,
                        "input_token_details": {"cache_read": 20},
                    },
                )
            ]
        )

    middleware.wrap_model_call(_request(context=context), handler)
    middleware.wrap_model_call(_request(context=context), handler)

    assert journal.record_context_manifest.call_count == 2
    first = journal.record_context_manifest.call_args_list[0].args[0]
    second = journal.record_context_manifest.call_args_list[1].args[0]
    assert first["call_index"] == 1
    assert second["call_index"] == 2
    assert first["response_usage"] == {
        "input_tokens": 222,
        "output_tokens": 11,
        "total_tokens": 233,
        "cache_read_tokens": 20,
    }
    assert first["outcome"] == "success"


def test_middleware_records_error_type_without_swallowing_or_copying_error_text():
    journal = Mock()
    context = {"__run_journal": journal}
    middleware = ContextManifestMiddleware(agent_name=None, activation_owner_token="owner-token")

    def handler(_request):
        raise RuntimeError("TOP-SECRET-PROVIDER-ERROR")

    with pytest.raises(RuntimeError, match="TOP-SECRET-PROVIDER-ERROR"):
        middleware.wrap_model_call(_request(context=context), handler)

    manifest = journal.record_context_manifest.call_args.args[0]
    assert manifest["outcome"] == "error"
    assert manifest["error_type"] == "RuntimeError"
    assert "TOP-SECRET" not in json.dumps(manifest)


@pytest.mark.anyio
async def test_async_middleware_records_manifest_without_changing_response():
    journal = Mock()
    context = {"__run_journal": journal}
    middleware = ContextManifestMiddleware(agent_name=None, activation_owner_token="owner-token")
    expected = ModelResponse(result=[AIMessage(content="answer", usage_metadata={"input_tokens": 3, "output_tokens": 2, "total_tokens": 5})])

    async def handler(_request):
        return expected

    actual = await middleware.awrap_model_call(_request(context=context), handler)

    assert actual is expected
    assert journal.record_context_manifest.call_args.args[0]["response_usage"]["total_tokens"] == 5
