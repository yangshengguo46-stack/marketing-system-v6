from __future__ import annotations

import importlib
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from langchain.tools import ToolRuntime
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.types import Command

from deerflow.agents.lead_agent.prompt import SYSTEM_PROMPT_TEMPLATE
from deerflow.tools.builtins.content_intelligence_tool import content_intelligence_tool, explore_content_world_tool
from deerflow.tools.tools import BUILTIN_TOOLS

content_intelligence_tool_module = importlib.import_module("deerflow.tools.builtins.content_intelligence_tool")
incubation_tool_support_module = importlib.import_module("deerflow.tools.builtins.incubation_tool_support")


def _tool_runtime(tool_call_id: str, *, context: dict[str, str] | None = None) -> ToolRuntime:
    runtime_context = {
        "thread_id": "thread-1",
        "run_id": "run-1",
        "user_id": "user-1",
        **(context or {}),
    }
    return ToolRuntime(
        state={},
        context=runtime_context,
        config={"configurable": {"thread_id": runtime_context["thread_id"]}},
        stream_writer=lambda _: None,
        tools=[],
        tool_call_id=tool_call_id,
        store=None,
    )


def test_content_intelligence_workers_do_not_inherit_lead_thinking_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    app_config_module = importlib.import_module("deerflow.config.app_config")
    app_config = SimpleNamespace(
        models=[SimpleNamespace(name="deepseek-v4-pro")],
        get_model_config=lambda name: object() if name == "deepseek-v4-pro" else None,
    )
    monkeypatch.setattr(app_config_module, "get_app_config", lambda: app_config)
    create_model = Mock(return_value=object())
    monkeypatch.setattr(incubation_tool_support_module, "create_chat_model", create_model)

    content_intelligence_tool_module._create_content_intelligence_model(
        {
            "configurable": {
                "model_name": "deepseek-v4-pro",
                "thinking_enabled": True,
            }
        }
    )

    create_model.assert_called_once_with(
        name="deepseek-v4-pro",
        thinking_enabled=False,
        app_config=app_config,
        attach_tracing=False,
    )


def test_content_intelligence_tool_is_available_to_the_lead_by_default() -> None:
    assert content_intelligence_tool in BUILTIN_TOOLS
    assert explore_content_world_tool in BUILTIN_TOOLS
    assert content_intelligence_tool.name == "analyze_content_intelligence"
    assert explore_content_world_tool.name == "explore_content_world"
    assert explore_content_world_tool.return_direct is True


def test_lexical_evidence_provider_is_disabled_without_a_local_index_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.delenv("CONTENT_INTELLIGENCE_CEDICT_INDEX", raising=False)
    monkeypatch.setattr(incubation_tool_support_module, "runtime_home", lambda: tmp_path)

    assert content_intelligence_tool_module._create_lexical_evidence_provider() is None


def test_lexical_evidence_provider_is_created_from_the_untracked_local_index(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    index_path = "/tmp/local-cc-cedict.sqlite3"
    provider = object()
    provider_factory = Mock(return_value=provider)
    monkeypatch.setenv("CONTENT_INTELLIGENCE_CEDICT_INDEX", index_path)
    monkeypatch.setattr(
        incubation_tool_support_module,
        "CedictLexicalEvidenceProvider",
        provider_factory,
    )

    actual = content_intelligence_tool_module._create_lexical_evidence_provider()

    assert actual is provider
    provider_factory.assert_called_once_with(index_path)


@pytest.mark.asyncio
async def test_content_world_tool_stops_after_the_candidate_map_for_content_opportunities(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle = object()
    lexical_provider = object()
    topic_search_factory = Mock()
    monkeypatch.setattr(content_intelligence_tool_module, "DouyinMcpTopicEvidenceSearch", topic_search_factory)
    monkeypatch.setattr(content_intelligence_tool_module, "_create_content_intelligence_model", lambda config: object())
    monkeypatch.setattr(content_intelligence_tool_module, "_create_lexical_evidence_provider", lambda: lexical_provider)
    analysis = AsyncMock(return_value=bundle)
    monkeypatch.setattr(content_intelligence_tool_module, "analyze_content_intelligence", analysis)
    research = AsyncMock()
    monkeypatch.setattr(content_intelligence_tool_module, "enrich_content_world_with_research", research)
    delivery = AsyncMock()
    monkeypatch.setattr(content_intelligence_tool_module, "synthesize_shooting_delivery", delivery)
    opportunities = Mock(return_value="# 候选内容机会地图\n\n**地图从哪里展开：** 火锅")
    monkeypatch.setattr(content_intelligence_tool_module, "_render_content_opportunity_map", opportunities)
    persist = AsyncMock(return_value={"status": "not_selected"})
    monkeypatch.setattr(content_intelligence_tool_module, "_persist_content_run", persist)

    result = await explore_content_world_tool.ainvoke(
        {
            "name": "explore_content_world",
            "args": {
                "user_request": "我是卖重庆火锅底料的，该怎么起号？",
                "answer_goal": "content_opportunities",
                "runtime": _tool_runtime("content-world-call-1"),
            },
            "id": "content-world-call-1",
            "type": "tool_call",
        }
    )

    assert isinstance(result, Command)
    assert result.goto == ()
    assert isinstance(result.update, dict)
    messages = result.update["messages"]
    assert len(messages) == 1
    tool_message = messages[0]
    assert isinstance(tool_message, ToolMessage)
    assert tool_message.tool_call_id == "content-world-call-1"
    assert tool_message.additional_kwargs["hide_from_ui"] is True
    assert tool_message.additional_kwargs["deerflow_direct_response"] is True
    assert tool_message.content == "# 候选内容机会地图\n\n**地图从哪里展开：** 火锅"
    assert not any(isinstance(message, AIMessage) for message in messages)
    research.assert_not_awaited()
    delivery.assert_not_awaited()
    topic_search_factory.assert_not_called()
    assert analysis.await_args.args[0].subject_expression == "我是卖重庆火锅底料的，该怎么起号？"
    assert analysis.await_args.args[0].source_materials == ()
    assert analysis.await_args.kwargs["lexical_evidence_provider"] is lexical_provider
    persist.assert_awaited_once()
    assert persist.await_args.kwargs["bundle"] is bundle
    assert persist.await_args.kwargs["delivery"] is None
    assert persist.await_args.kwargs["topic_evidence_snapshots"] == ()
    opportunities.assert_called_once_with(bundle)


@pytest.mark.asyncio
async def test_content_world_tool_returns_the_concrete_shooting_delivery_before_map_narration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle = object()
    enriched_bundle = SimpleNamespace(topic_brief=object())
    shooting_delivery = object()
    user_request = "我是卖白酒的，该怎么起号？"
    monkeypatch.setattr(content_intelligence_tool_module, "_create_content_intelligence_model", lambda config: object())
    monkeypatch.setattr(content_intelligence_tool_module, "_create_lexical_evidence_provider", lambda: None)
    monkeypatch.setattr(
        content_intelligence_tool_module,
        "analyze_content_intelligence",
        AsyncMock(return_value=bundle),
    )
    monkeypatch.setattr(
        content_intelligence_tool_module,
        "enrich_content_world_with_research",
        AsyncMock(return_value=enriched_bundle),
    )
    delivery = AsyncMock(return_value=shooting_delivery)
    monkeypatch.setattr(content_intelligence_tool_module, "synthesize_shooting_delivery", delivery)
    render = Mock(return_value="# 内容机会依据\n\n**本题来自哪张地图：** 饮酒与人际礼俗\n\n# 今日建议拍摄\n\n## 为什么当地的酒桌礼数这么重？")
    monkeypatch.setattr(content_intelligence_tool_module, "render_shooting_delivery", render)

    result = await explore_content_world_tool.ainvoke(
        {
            "name": "explore_content_world",
            "args": {
                "user_request": user_request,
                "runtime": _tool_runtime("content-world-call-shooting-delivery"),
            },
            "id": "content-world-call-shooting-delivery",
            "type": "tool_call",
        }
    )

    rendered = result.update["messages"][0].content
    assert rendered.startswith("# 今日建议拍摄")
    assert "# 内容机会依据" in rendered
    assert rendered.index("# 今日建议拍摄") < rendered.index("# 内容机会依据")
    delivery.assert_awaited_once()
    assert delivery.await_args.args[0] is enriched_bundle
    assert delivery.await_args.kwargs["user_request"] == user_request
    render.assert_called_once_with(enriched_bundle, shooting_delivery)
    research = content_intelligence_tool_module.enrich_content_world_with_research
    assert research.await_args.kwargs["topic_seed"] is None


@pytest.mark.asyncio
async def test_selected_project_loads_existing_incubation_judgment_before_topic_research(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle = object()
    enriched_bundle = SimpleNamespace(topic_brief=object())
    judgment = SimpleNamespace(
        decision_status="confirmed",
        route_options=(),
        selected_option_id="route_a",
        positioning=SimpleNamespace(
            decision="观察具体人际场景里谁在行动、如何选择、关系怎样变化",
            audience_promise="让观众看懂日常关系中没有说破的规则",
        ),
        audience=SimpleNamespace(
            people="对人际分寸与真实故事好奇的普通成年人",
            recurring_interest="每次从一件具体的人和事得到新的关系判断",
        ),
        persona=SimpleNamespace(account_role="人际规则的场景观察者"),
    )
    judgment_artifact = object()
    prepared = SimpleNamespace(
        judgment=judgment,
        judgment_artifact=judgment_artifact,
    )
    shooting_delivery = object()
    order: list[str] = []

    monkeypatch.setattr(content_intelligence_tool_module, "_create_content_intelligence_model", lambda config: object())
    monkeypatch.setattr(content_intelligence_tool_module, "_create_lexical_evidence_provider", lambda: None)
    monkeypatch.setattr(
        content_intelligence_tool_module,
        "_load_confirmed_topic_context",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(content_intelligence_tool_module, "analyze_content_intelligence", AsyncMock(return_value=bundle))
    monkeypatch.setattr(
        content_intelligence_tool_module,
        "enrich_content_world_with_research",
        AsyncMock(return_value=enriched_bundle),
    )
    monkeypatch.setattr(
        content_intelligence_tool_module,
        "DouyinMcpTopicEvidenceSearch",
        Mock(return_value=SimpleNamespace(snapshots=())),
    )

    async def load_current(**kwargs):
        order.append("load_current")
        return prepared

    async def research(*args, **kwargs):
        order.append("research")
        return enriched_bundle

    async def deliver(*args, **kwargs):
        order.append("deliver")
        return shooting_delivery

    async def persist(**kwargs):
        order.append("persist")
        return {
            "status": "stored",
            "project_id": "project-1",
            "artifacts": [],
        }

    monkeypatch.setattr(content_intelligence_tool_module, "_load_current_account_strategy", load_current)
    monkeypatch.setattr(content_intelligence_tool_module, "enrich_content_world_with_research", AsyncMock(side_effect=research))
    delivery = AsyncMock(side_effect=deliver)
    monkeypatch.setattr(content_intelligence_tool_module, "synthesize_shooting_delivery", delivery)
    persistence = AsyncMock(side_effect=persist)
    monkeypatch.setattr(content_intelligence_tool_module, "_persist_content_run", persistence)
    monkeypatch.setattr(
        content_intelligence_tool_module,
        "render_shooting_delivery",
        Mock(return_value="# 今日建议拍摄\n\n## 一条具体选题"),
    )
    render_route_reference = Mock(return_value="## 已确认路线\n\n**沿用：** 酒桌人情")
    monkeypatch.setattr(
        content_intelligence_tool_module,
        "_render_confirmed_route_reference",
        render_route_reference,
    )

    result = await explore_content_world_tool.ainvoke(
        {
            "name": "explore_content_world",
            "args": {
                "user_request": "我是卖白酒的，该怎么起号？",
                "runtime": _tool_runtime(
                    "content-world-call-incubation",
                    context={"incubation_project_id": "project-1"},
                ),
            },
            "id": "content-world-call-incubation",
            "type": "tool_call",
        }
    )

    assert order == ["load_current", "research", "deliver", "persist"]
    assert delivery.await_args.kwargs["incubation_judgment"] is judgment
    assert persistence.await_args.kwargs["incubation_judgment_artifact"] is judgment_artifact
    assert persistence.await_args.kwargs["include_presentation_adaptation"] is False
    assert persistence.await_args.kwargs["include_production_plan"] is False
    assert "## 已确认路线" in result.update["messages"][0].content
    assert "# 本条表现形式" not in result.update["messages"][0].content
    assert "_answer_appendix" not in result.update["messages"][0].additional_kwargs["incubation_persistence"]
    render_route_reference.assert_called_once_with(judgment)


@pytest.mark.asyncio
async def test_confirmed_route_topic_continuation_reuses_its_frozen_map_before_semantic_analysis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frozen_bundle = SimpleNamespace(
        record=SimpleNamespace(subject_expression="我是开旧书店的"),
        content_world=SimpleNamespace(
            source_object="旧书店",
            content_entry="旧书",
            content_root="旧书",
        ),
    )
    enriched_bundle = SimpleNamespace(topic_brief=object())
    judgment = SimpleNamespace(
        decision_status="confirmed",
        route_options=(),
        selected_option_id="route_a",
        positioning=SimpleNamespace(
            decision="追踪一本旧书在不同主人手中的经历",
            audience_promise="让观众透过一本旧书看见旧主人和时代",
        ),
        audience=SimpleNamespace(
            people="喜欢旧书、人物故事和时代痕迹的人",
            recurring_interest="每本书都能打开一段具体人物经历",
        ),
        persona=SimpleNamespace(account_role="旧书履历的调查者"),
    )
    judgment_artifact = object()
    prepared = SimpleNamespace(
        judgment=judgment,
        judgment_artifact=judgment_artifact,
    )
    shooting_delivery = object()
    load_context = AsyncMock(return_value=(frozen_bundle, prepared))
    semantic_analysis = AsyncMock()

    monkeypatch.setattr(content_intelligence_tool_module, "_create_content_intelligence_model", lambda config: object())
    monkeypatch.setattr(content_intelligence_tool_module, "_load_confirmed_topic_context", load_context)
    monkeypatch.setattr(content_intelligence_tool_module, "analyze_content_intelligence", semantic_analysis)
    research = AsyncMock(return_value=enriched_bundle)
    monkeypatch.setattr(content_intelligence_tool_module, "enrich_content_world_with_research", research)
    monkeypatch.setattr(
        content_intelligence_tool_module,
        "DouyinMcpTopicEvidenceSearch",
        Mock(return_value=SimpleNamespace(snapshots=())),
    )
    delivery = AsyncMock(return_value=shooting_delivery)
    monkeypatch.setattr(content_intelligence_tool_module, "synthesize_shooting_delivery", delivery)
    monkeypatch.setattr(
        content_intelligence_tool_module,
        "render_shooting_delivery",
        Mock(return_value="# 今日建议拍摄\n\n## 一本旧书如何换过三个主人？"),
    )
    monkeypatch.setattr(
        content_intelligence_tool_module,
        "_render_confirmed_route_reference",
        Mock(return_value="## 已确认路线\n\n**沿用：** 旧书的履历表"),
    )
    monkeypatch.setattr(
        content_intelligence_tool_module,
        "_persist_content_run",
        AsyncMock(return_value={"status": "stored", "project_id": "project-1", "artifacts": []}),
    )

    result = await explore_content_world_tool.ainvoke(
        {
            "name": "explore_content_world",
            "args": {
                "user_request": "按照这条路线，给我一个今天能直接拍的具体选题和基础稿。",
                "subject_expression": "旧书店",
                "topic_seed": "一本旧书的版本信息、扉页题字、藏书印、批注、修补痕迹和流通线索",
                "runtime": _tool_runtime(
                    "content-world-call-confirmed-continuation",
                    context={"incubation_project_id": "project-1"},
                ),
            },
            "id": "content-world-call-confirmed-continuation",
            "type": "tool_call",
        }
    )

    load_context.assert_awaited_once()
    semantic_analysis.assert_not_awaited()
    assert research.await_args.args[0] is frozen_bundle
    assert research.await_args.kwargs["topic_seed"] is None
    editorial_context = research.await_args.kwargs["editorial_context"]
    assert editorial_context.route_id == "route_a"
    assert editorial_context.content_subject.startswith("追踪一本旧书")
    assert delivery.await_args.kwargs["incubation_judgment"] is judgment
    assert "一本旧书如何换过三个主人" in result.update["messages"][0].content


@pytest.mark.asyncio
async def test_confirmed_topic_context_rehydrates_the_exact_map_bound_to_the_judgment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from datetime import UTC, datetime

    from deerflow.content_intelligence import ComprehensionRecord, ContentIntelligenceBundle, ContentWorldView, SourceItem
    from deerflow.incubation import (
        ArtifactEnvelope,
        ProjectRef,
        implicit_thread_logical_account_ref,
        seal_content_run_artifacts,
    )

    now = datetime(2026, 8, 20, 8, 0, tzinfo=UTC)
    project = ProjectRef(owner_user_id="user-1", project_id="old-books")
    logical_account = implicit_thread_logical_account_ref(
        project=project,
        thread_id="thread-1",
    )
    record = ComprehensionRecord(
        record_id="record-old-books",
        subject_expression="我是开旧书店的",
        sources=(
            SourceItem(
                source_id="source-user",
                kind="user_statement",
                content="我是开旧书店的",
            ),
        ),
    )
    world = ContentWorldView(
        record_id=record.record_id,
        source_object="旧书店",
        content_entry="旧书",
        content_root="旧书",
        root_rationale="店是经营容器，旧书才是可持续追踪履历的内容主体。",
        editorial_promise="从书的版本、旧主人与流转经历理解一本书的生命。",
        recurring_lens="追踪一本书在不同时间、地方和人手中的变化。",
    )
    bundle = ContentIntelligenceBundle(record=record, content_world=world)
    artifacts = seal_content_run_artifacts(
        project=project,
        bundle=bundle,
        delivery=None,
        created_at=now,
        source_thread_id="thread-original",
        source_run_id="run-original",
        logical_account=logical_account,
    )
    judgment = ArtifactEnvelope.seal(
        project=project,
        artifact_type="incubation_judgment",
        version=1,
        payload={
            "content_map_version_id": world.content_map_version_id(),
            "monetization": [],
            "unknowns": [],
            "alternatives": [],
        },
        parents=(artifacts.content_world.to_parent_ref(),),
        logical_account=logical_account,
        created_at=now,
        source_thread_id="thread-confirmation",
        source_run_id="run-confirmation",
    )
    stored = [artifacts.content_reading, artifacts.content_world, judgment]
    repository = SimpleNamespace(
        get_project=AsyncMock(return_value=object()),
        list_artifacts=AsyncMock(return_value=stored),
    )
    monkeypatch.setattr(content_intelligence_tool_module, "_get_incubation_repository", lambda: repository)

    result = await content_intelligence_tool_module._load_confirmed_topic_context(
        runtime=_tool_runtime(
            "load-confirmed-topic-context",
            context={"incubation_project_id": project.project_id},
        )
    )

    assert result is not None
    restored_bundle, restored_strategy = result
    assert restored_bundle.record.subject_expression == "我是开旧书店的"
    assert restored_bundle.content_world is not None
    assert restored_bundle.content_world.content_root == "旧书"
    assert restored_bundle.content_world.content_map_version_id() == world.content_map_version_id()
    assert restored_strategy.judgment_artifact == judgment


@pytest.mark.asyncio
async def test_shootable_topic_goal_never_silently_downgrades_to_a_map_when_research_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle = object()
    monkeypatch.setattr(content_intelligence_tool_module, "_create_content_intelligence_model", lambda config: object())
    monkeypatch.setattr(
        content_intelligence_tool_module,
        "analyze_content_intelligence",
        AsyncMock(return_value=bundle),
    )
    monkeypatch.setattr(
        content_intelligence_tool_module,
        "enrich_content_world_with_research",
        AsyncMock(side_effect=RuntimeError("provider unavailable")),
    )
    delivery = AsyncMock()
    monkeypatch.setattr(
        content_intelligence_tool_module,
        "synthesize_shooting_delivery",
        delivery,
    )
    opportunities = Mock(return_value="# 候选内容机会地图\n\n**地图从哪里展开：** 火锅")
    monkeypatch.setattr(content_intelligence_tool_module, "_render_content_opportunity_map", opportunities)

    result = await explore_content_world_tool.ainvoke(
        {
            "name": "explore_content_world",
            "args": {
                "user_request": "我是卖重庆火锅底料的，该怎么起号？",
                "runtime": _tool_runtime("content-world-call-research-failure"),
            },
            "id": "content-world-call-research-failure",
            "type": "tool_call",
        }
    )

    assert isinstance(result, Command)
    content = result.update["messages"][0].content
    assert content.startswith("# 本轮选题结果")
    assert "候选内容地图已形成，但没有形成可拍选题" in content
    assert "# 候选内容机会地图" in content
    delivery.assert_not_awaited()
    opportunities.assert_called_once_with(bundle)


@pytest.mark.asyncio
async def test_shootable_topic_goal_reports_when_topic_evidence_adapter_cannot_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle = object()
    monkeypatch.setattr(content_intelligence_tool_module, "_create_content_intelligence_model", lambda config: object())
    monkeypatch.setattr(content_intelligence_tool_module, "_create_lexical_evidence_provider", lambda: None)
    monkeypatch.setattr(content_intelligence_tool_module, "analyze_content_intelligence", AsyncMock(return_value=bundle))
    monkeypatch.setattr(
        content_intelligence_tool_module,
        "DouyinMcpTopicEvidenceSearch",
        Mock(side_effect=RuntimeError("topic evidence adapter unavailable")),
    )
    research = AsyncMock()
    monkeypatch.setattr(content_intelligence_tool_module, "enrich_content_world_with_research", research)
    monkeypatch.setattr(
        content_intelligence_tool_module,
        "_render_content_opportunity_map",
        Mock(return_value="# 候选内容机会地图\n\n**地图从哪里展开：** 火锅"),
    )

    result = await explore_content_world_tool.ainvoke(
        {
            "name": "explore_content_world",
            "args": {
                "user_request": "我是卖重庆火锅底料的，该怎么起号？",
                "answer_goal": "one_shootable_topic",
                "runtime": _tool_runtime("content-world-call-adapter-failure"),
            },
            "id": "content-world-call-adapter-failure",
            "type": "tool_call",
        }
    )

    assert "候选内容地图已形成，但没有形成可拍选题" in result.update["messages"][0].content
    research.assert_not_awaited()


@pytest.mark.asyncio
async def test_shootable_topic_goal_reports_when_research_returns_no_topic_brief(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle = object()
    researched_bundle = SimpleNamespace(topic_brief=None)
    monkeypatch.setattr(content_intelligence_tool_module, "_create_content_intelligence_model", lambda config: object())
    monkeypatch.setattr(content_intelligence_tool_module, "_create_lexical_evidence_provider", lambda: None)
    monkeypatch.setattr(
        content_intelligence_tool_module,
        "analyze_content_intelligence",
        AsyncMock(return_value=bundle),
    )
    monkeypatch.setattr(
        content_intelligence_tool_module,
        "enrich_content_world_with_research",
        AsyncMock(return_value=researched_bundle),
    )
    delivery = AsyncMock()
    monkeypatch.setattr(content_intelligence_tool_module, "synthesize_shooting_delivery", delivery)
    monkeypatch.setattr(
        content_intelligence_tool_module,
        "_render_content_opportunity_map",
        Mock(return_value="# 候选内容机会地图\n\n**地图从哪里展开：** 火锅"),
    )

    result = await explore_content_world_tool.ainvoke(
        {
            "name": "explore_content_world",
            "args": {
                "user_request": "我是卖重庆火锅底料的，该怎么起号？",
                "answer_goal": "one_shootable_topic",
                "runtime": _tool_runtime("content-world-call-no-topic"),
            },
            "id": "content-world-call-no-topic",
            "type": "tool_call",
        }
    )

    assert "候选内容地图已形成，但没有形成可拍选题" in result.update["messages"][0].content
    delivery.assert_not_awaited()


@pytest.mark.asyncio
async def test_shootable_topic_goal_reports_when_message_plan_or_base_draft_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle = object()
    researched_bundle = SimpleNamespace(topic_brief=object())
    monkeypatch.setattr(content_intelligence_tool_module, "_create_content_intelligence_model", lambda config: object())
    monkeypatch.setattr(content_intelligence_tool_module, "_create_lexical_evidence_provider", lambda: None)
    monkeypatch.setattr(content_intelligence_tool_module, "analyze_content_intelligence", AsyncMock(return_value=bundle))
    monkeypatch.setattr(
        content_intelligence_tool_module,
        "enrich_content_world_with_research",
        AsyncMock(return_value=researched_bundle),
    )
    monkeypatch.setattr(
        content_intelligence_tool_module,
        "synthesize_shooting_delivery",
        AsyncMock(side_effect=ValueError("message plan contract failed")),
    )
    monkeypatch.setattr(
        content_intelligence_tool_module,
        "_render_content_opportunity_map",
        Mock(return_value="# 候选内容机会地图\n\n**地图从哪里展开：** 火锅"),
    )

    result = await explore_content_world_tool.ainvoke(
        {
            "name": "explore_content_world",
            "args": {
                "user_request": "我是卖重庆火锅底料的，该怎么起号？",
                "answer_goal": "one_shootable_topic",
                "runtime": _tool_runtime("content-world-call-delivery-failure"),
            },
            "id": "content-world-call-delivery-failure",
            "type": "tool_call",
        }
    )

    assert "候选内容地图已形成，但没有形成可拍选题" in result.update["messages"][0].content


@pytest.mark.asyncio
async def test_topic_seed_reaches_research_only_as_a_verbatim_user_request_span(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle = object()
    enriched_bundle = SimpleNamespace(topic_brief=object())
    shooting_delivery = object()
    user_request = "我是个普通人，今天的牛来这部影片比较火，给我出一个选题"
    research = AsyncMock(return_value=enriched_bundle)
    monkeypatch.setattr(content_intelligence_tool_module, "_create_content_intelligence_model", lambda config: object())
    monkeypatch.setattr(content_intelligence_tool_module, "_create_lexical_evidence_provider", lambda: None)
    monkeypatch.setattr(content_intelligence_tool_module, "analyze_content_intelligence", AsyncMock(return_value=bundle))
    monkeypatch.setattr(content_intelligence_tool_module, "enrich_content_world_with_research", research)
    monkeypatch.setattr(
        content_intelligence_tool_module,
        "synthesize_shooting_delivery",
        AsyncMock(return_value=shooting_delivery),
    )
    monkeypatch.setattr(
        content_intelligence_tool_module,
        "render_shooting_delivery",
        Mock(return_value="# 内容机会依据\n\n普通人观察\n\n# 今日建议拍摄\n\n## 为什么这部影片能火？"),
    )

    await explore_content_world_tool.ainvoke(
        {
            "name": "explore_content_world",
            "args": {
                "user_request": user_request,
                "answer_goal": "one_shootable_topic",
                "topic_seed": "今天的牛来这部影片比较火",
                "runtime": _tool_runtime("content-world-call-topic-seed"),
            },
            "id": "content-world-call-topic-seed",
            "type": "tool_call",
        }
    )

    assert research.await_args.kwargs["topic_seed"] == "今天的牛来这部影片比较火"


@pytest.mark.asyncio
async def test_topic_seed_outside_user_request_is_dropped_without_blocking_the_valid_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle = object()
    enriched_bundle = SimpleNamespace(topic_brief=object())
    shooting_delivery = object()
    analysis = AsyncMock(return_value=bundle)
    research = AsyncMock(return_value=enriched_bundle)
    monkeypatch.setattr(content_intelligence_tool_module, "_create_content_intelligence_model", lambda config: object())
    monkeypatch.setattr(content_intelligence_tool_module, "_create_lexical_evidence_provider", lambda: None)
    monkeypatch.setattr(content_intelligence_tool_module, "analyze_content_intelligence", analysis)
    monkeypatch.setattr(content_intelligence_tool_module, "enrich_content_world_with_research", research)
    monkeypatch.setattr(
        content_intelligence_tool_module,
        "synthesize_shooting_delivery",
        AsyncMock(return_value=shooting_delivery),
    )
    monkeypatch.setattr(
        content_intelligence_tool_module,
        "render_shooting_delivery",
        Mock(return_value="# 今日建议拍摄\n\n## 一条不依赖伪线索的选题"),
    )

    result = await explore_content_world_tool.ainvoke(
        {
            "name": "explore_content_world",
            "args": {
                "user_request": "我是个普通人，给我出一个选题",
                "answer_goal": "one_shootable_topic",
                "topic_seed": "用户没有说过的热点",
                "runtime": _tool_runtime("content-world-call-invalid-seed"),
            },
            "id": "content-world-call-invalid-seed",
            "type": "tool_call",
        }
    )

    assert "一条不依赖伪线索的选题" in result.update["messages"][0].content
    analysis.assert_awaited_once()
    assert research.await_args.kwargs["topic_seed"] is None


def test_tool_layer_renders_candidate_map_as_basis_and_prioritizes_the_shootable_topic() -> None:
    world = SimpleNamespace(
        content_root="火锅",
        audience_territory=SimpleNamespace(text="围绕火锅形成的饮食与社交世界"),
        editorial_promise="从一口锅看不同地方的人怎么吃、怎么聚",
        recurring_lens="持续观察人物、时间、地域和事件",
        dimensions=(
            SimpleNamespace(
                name="地域",
                rationale="观察不同地方的火锅传统",
                paths=(SimpleNamespace(steps=(SimpleNamespace(to_label="外国人怎么吃火锅"),)),),
            ),
        ),
        drift_boundaries=("不能脱离火锅只讲泛餐饮",),
    )

    positioning = content_intelligence_tool_module._render_content_opportunity_map(SimpleNamespace(content_world=world))
    prioritized = content_intelligence_tool_module._prioritize_shooting_delivery(positioning + "\n\n# 今日建议拍摄\n\n## 外国人到底吃不吃火锅？")

    assert "**地图从哪里展开：** 火锅" in positioning
    assert "外国人怎么吃火锅" in positioning
    assert prioritized.startswith("# 今日建议拍摄")
    assert "# 内容机会依据" in prioritized
    assert prioritized.index("# 今日建议拍摄") < prioritized.index("# 内容机会依据")


def test_incubation_renderer_keeps_position_audience_persona_form_and_monetization_separate() -> None:
    from deerflow.incubation import (
        AccountPresentationPlan,
        AudienceHypothesis,
        IncubationJudgment,
        MonetizationHypothesis,
        PersonaDecision,
        PositioningDecision,
    )

    judgment = IncubationJudgment(
        content_map_version_id="map-1",
        positioning=PositioningDecision(
            decision="从一件具体礼俗理解人与人怎样相处",
            audience_promise="每次讲清一段具体关系",
            rationale="与冻结地图一致",
            confidence="medium",
        ),
        audience=AudienceHypothesis(
            people="对人情与礼俗感兴趣的人",
            recurring_interest="具体关系如何被安排",
            why_return="持续得到可以理解现实关系的新视角",
            rationale="仍需真实反馈校正",
            confidence="low",
        ),
        persona=PersonaDecision(
            account_role="从礼品生意观察人情的经营者",
            rationale="只使用用户已声明身份",
        ),
        presentation=AccountPresentationPlan(
            primary_forms=("具体故事讲解", "图文材料解读"),
            rationale="属于账号级长期方向",
        ),
        monetization=(
            MonetizationHypothesis(
                path="以长期内容信任承接礼品咨询",
                trust_required="观众认可账号懂送礼场景",
                rationale="待真实业务验证",
            ),
        ),
        unknowns=("用户持续产能未知",),
        alternatives=("也可先从不出镜图文开始",),
    )

    rendered = content_intelligence_tool_module.render_account_strategy(judgment)

    assert rendered.startswith("# 已确认的账号路线")
    assert "**定位版本：** v1" in rendered
    for heading in (
        "## 定位",
        "## 受众假设",
        "## 人设",
        "## 账号级表现方向",
        "## 变现假设",
        "## 未知与备选",
    ):
        assert heading in rendered
    assert "**置信度：** 中" in rendered
    assert "以长期内容信任承接礼品咨询" in rendered


@pytest.mark.asyncio
async def test_content_world_search_uses_configured_query_only_provider_and_normalizes_list_receipt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    @tool("web_search")
    async def configured_search(query: str) -> str:
        """Search through the configured test provider."""
        calls.append(query)
        return json.dumps(
            [
                {
                    "title": "A public source",
                    "url": "https://example.com/source",
                    "snippet": "A bounded public search receipt.",
                }
            ]
        )

    search_config = SimpleNamespace(use="tests.fake:configured_search")
    app_config = SimpleNamespace(
        get_tool_config=lambda name: search_config if name == "web_search" else None,
    )
    monkeypatch.setattr("deerflow.config.get_app_config", lambda: app_config)
    monkeypatch.setattr("deerflow.reflection.resolve_variable", lambda use, expected: configured_search)
    monkeypatch.setattr(
        "deerflow.community.ddg_search.tools.web_search_tool",
        AsyncMock(return_value=json.dumps({"results": []})),
    )

    results = await content_intelligence_tool_module._search_content_world_evidence(
        "human gift exchange",
        2,
    )

    assert calls == ["human gift exchange"]
    assert len(results) == 1
    assert results[0].title == "A public source"
    assert results[0].content == "A bounded public search receipt."


@pytest.mark.asyncio
async def test_content_world_search_passes_supported_limit_and_normalizes_byted_receipt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, int]] = []

    @tool("web_search")
    async def configured_search(query: str, max_results: int = 5) -> str:
        """Search through a provider with an explicit result limit."""
        calls.append((query, max_results))
        return json.dumps(
            {
                "Result": {
                    "WebResults": [
                        {
                            "Title": "Official-style result",
                            "Url": "https://example.com/official",
                            "Summary": "Provider summary.",
                        },
                        {
                            "Title": "Second result",
                            "Url": "https://example.com/second",
                            "Snippet": "Second provider snippet.",
                        },
                    ]
                }
            }
        )

    search_config = SimpleNamespace(use="tests.fake:configured_search")
    app_config = SimpleNamespace(
        get_tool_config=lambda name: search_config if name == "web_search" else None,
    )
    monkeypatch.setattr("deerflow.config.get_app_config", lambda: app_config)
    monkeypatch.setattr("deerflow.reflection.resolve_variable", lambda use, expected: configured_search)

    results = await content_intelligence_tool_module._search_content_world_evidence(
        "gift customs",
        1,
    )

    assert calls == [("gift customs", 1)]
    assert len(results) == 1
    assert results[0].title == "Official-style result"
    assert results[0].content == "Provider summary."


@pytest.mark.asyncio
async def test_content_world_search_interleaves_web_and_douyin_topic_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, str, int]] = []

    @tool("web_search")
    async def configured_web_search(query: str, max_results: int = 5) -> str:
        """Search public web evidence."""
        calls.append(("web", query, max_results))
        return json.dumps(
            {
                "results": [
                    {
                        "title": "Public article one",
                        "url": "https://example.com/article-one",
                        "content": "Public evidence one.",
                    },
                    {
                        "title": "Public article two",
                        "url": "https://example.com/article-two",
                        "content": "Public evidence two.",
                    },
                ]
            }
        )

    async def mcp_douyin_search(query: str, max_results: int = 5):
        calls.append(("douyin", query, max_results))
        return (
            content_intelligence_tool_module.ResearchSearchResult(
                title="Douyin video",
                url="https://www.douyin.com/video/123",
                content="A bounded official video-search receipt.",
            ),
        )

    configs = {"web_search": SimpleNamespace(use="tests.fake:configured_web_search")}
    monkeypatch.setattr(
        "deerflow.config.get_app_config",
        lambda: SimpleNamespace(get_tool_config=configs.get),
    )
    monkeypatch.setattr(
        "deerflow.reflection.resolve_variable",
        lambda use, expected: configured_web_search,
    )

    results = await content_intelligence_tool_module._search_content_world_evidence(
        "人情往来 送礼",
        3,
        douyin_search=mcp_douyin_search,
    )

    assert sorted(calls) == [
        ("douyin", "人情往来 送礼", 3),
        ("web", "人情往来 送礼", 3),
    ]
    assert [result.title for result in results] == [
        "Public article one",
        "Douyin video",
        "Public article two",
    ]
    assert all(type(result) is content_intelligence_tool_module.ResearchSearchResult for result in results)


@pytest.mark.asyncio
async def test_content_world_search_drops_douyin_benchmark_receipts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    @tool("web_search")
    async def configured_web_search(query: str, max_results: int = 5) -> str:
        """Search public topic evidence."""
        return json.dumps(
            {
                "results": [
                    {
                        "title": "送礼习俗资料",
                        "url": "https://example.com/gift-customs",
                        "content": "一条内容地图可用的公开资料。",
                    }
                ]
            }
        )

    legacy_douyin_search = AsyncMock(side_effect=AssertionError("legacy direct Douyin tool must not run"))

    configs = {
        "web_search": SimpleNamespace(use="tests.fake:configured_web_search"),
        "douyin_video_search": SimpleNamespace(use="tests.fake:legacy_douyin_search"),
    }
    tools_by_use = {
        "tests.fake:configured_web_search": configured_web_search,
        "tests.fake:legacy_douyin_search": legacy_douyin_search,
    }
    monkeypatch.setattr(
        "deerflow.config.get_app_config",
        lambda: SimpleNamespace(get_tool_config=configs.get),
    )
    monkeypatch.setattr(
        "deerflow.reflection.resolve_variable",
        lambda use, expected: tools_by_use[use],
    )

    results = await content_intelligence_tool_module._search_content_world_evidence(
        "人情往来 送礼",
        3,
    )

    assert [result.url for result in results] == ["https://example.com/gift-customs"]
    legacy_douyin_search.assert_not_awaited()


@pytest.mark.asyncio
async def test_content_world_search_drops_explicit_web_benchmark_receipts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    @tool("web_search")
    async def configured_web_search(query: str, max_results: int = 5) -> str:
        """Return a deliberately misrouted benchmark receipt."""
        return json.dumps(
            {
                "evidence_role": "benchmark_evidence",
                "results": [
                    {
                        "title": "对标账号观察",
                        "url": "https://example.com/benchmark-account",
                        "content": "这条证据不属于内容地图。",
                    }
                ],
            }
        )

    monkeypatch.setattr(
        "deerflow.config.get_app_config",
        lambda: SimpleNamespace(get_tool_config=lambda name: SimpleNamespace(use="tests.fake:configured_web_search") if name == "web_search" else None),
    )
    monkeypatch.setattr(
        "deerflow.reflection.resolve_variable",
        lambda use, expected: configured_web_search,
    )

    results = await content_intelligence_tool_module._search_content_world_evidence(
        "人情往来 送礼",
        3,
    )

    assert results == ()


@pytest.mark.asyncio
async def test_content_world_fetch_prefers_local_public_page_reading(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "deerflow.config.get_app_config",
        lambda: SimpleNamespace(tools=[]),
    )
    local_fetch = AsyncMock(return_value="# Local article\n\nEvidence body.")
    configured_fetch = AsyncMock(return_value="# Remote article\n\nFallback body.")
    monkeypatch.setattr(
        content_intelligence_tool_module,
        "_fetch_public_page_direct",
        local_fetch,
        raising=False,
    )
    monkeypatch.setattr(
        content_intelligence_tool_module,
        "_invoke_configured_web_fetch",
        configured_fetch,
        raising=False,
    )

    result = await content_intelligence_tool_module._fetch_content_world_evidence("https://example.com/article")

    assert result == "# Local article\n\nEvidence body."
    local_fetch.assert_awaited_once_with("https://example.com/article")
    configured_fetch.assert_not_awaited()


@pytest.mark.asyncio
async def test_content_world_fetch_uses_configured_reader_when_local_reading_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    local_fetch = AsyncMock(return_value=None)
    configured_fetch = AsyncMock(return_value="# Remote article\n\nFallback body.")
    monkeypatch.setattr(content_intelligence_tool_module, "_fetch_public_page_direct", local_fetch)
    monkeypatch.setattr(content_intelligence_tool_module, "_invoke_configured_web_fetch", configured_fetch)

    result = await content_intelligence_tool_module._fetch_content_world_evidence("https://example.com/article")

    assert result == "# Remote article\n\nFallback body."
    configured_fetch.assert_awaited_once_with("https://example.com/article")


@pytest.mark.asyncio
async def test_content_world_fetch_rejects_non_public_url_before_any_reader(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    local_fetch = AsyncMock(return_value=None)
    configured_fetch = AsyncMock(return_value="# Private content")
    monkeypatch.setattr(content_intelligence_tool_module, "_fetch_public_page_direct", local_fetch)
    monkeypatch.setattr(content_intelligence_tool_module, "_invoke_configured_web_fetch", configured_fetch)
    monkeypatch.setattr(
        content_intelligence_tool_module,
        "validate_public_http_url",
        lambda url, **kwargs: "Error: private address",
    )

    result = await content_intelligence_tool_module._fetch_content_world_evidence("http://127.0.0.1/private")

    assert result is None
    local_fetch.assert_not_awaited()
    configured_fetch.assert_not_awaited()


@pytest.mark.asyncio
async def test_direct_page_reader_rechecks_redirect_target_before_fetching_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checked_urls: list[str] = []
    real_client = httpx.AsyncClient

    def validate(url: str, **kwargs) -> str | None:
        checked_urls.append(url)
        if url.startswith("http://127.0.0.1"):
            return "Error: private address"
        return None

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "http://127.0.0.1/private"})

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(content_intelligence_tool_module, "validate_public_http_url", validate)
    monkeypatch.setattr(
        content_intelligence_tool_module.httpx,
        "AsyncClient",
        lambda **kwargs: real_client(transport=transport, **kwargs),
    )

    result = await content_intelligence_tool_module._fetch_public_page_direct("https://example.com/start")

    assert result is None
    assert checked_urls == ["https://example.com/start", "http://127.0.0.1/private"]


def test_content_world_tool_hides_injected_delivery_arguments_from_the_model() -> None:
    schema = explore_content_world_tool.tool_call_schema.model_json_schema()

    assert set(schema["properties"]) == {
        "answer_goal",
        "subject_expression",
        "topic_seed",
        "user_request",
    }
    goal_schema = schema["$defs"]["ContentWorldAnswerGoal"]
    assert goal_schema["enum"] == ["content_opportunities", "one_shootable_topic"]
    assert schema["properties"]["answer_goal"]["default"] == "one_shootable_topic"


def test_content_tool_does_not_expose_account_positioning_generation_helpers() -> None:
    assert not hasattr(content_intelligence_tool_module, "_prepare_incubation_judgment")
    assert not hasattr(content_intelligence_tool_module, "generate_incubation_judgment")


@pytest.mark.asyncio
async def test_structured_model_runner_unwraps_parsed_output_and_rejects_parse_errors() -> None:
    class StructuredRunnable:
        def __init__(self, result):
            self.result = result

        async def ainvoke(self, messages, config=None):
            return self.result

    class Model:
        def __init__(self, result):
            self.result = result

        def with_structured_output(self, schema, *, include_raw=False):
            assert include_raw is True
            return StructuredRunnable(self.result)

    parsed = object()
    runner = content_intelligence_tool_module._structured_model_runner(
        Model({"parsed": parsed, "parsing_error": None}),
        {},
    )
    assert await runner(object, ()) is parsed

    invalid = content_intelligence_tool_module._structured_model_runner(
        Model({"parsed": None, "parsing_error": ValueError("bad output")}),
        {},
    )
    with pytest.raises(ValueError, match="could not be parsed"):
        await invalid(object, ())


@pytest.mark.asyncio
async def test_content_run_persistence_uses_only_the_runtime_bound_project(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from deerflow.incubation import ProjectRef

    artifacts = tuple(
        SimpleNamespace(
            artifact_type=artifact_type,
            artifact_id=f"artifact-{artifact_type}",
            content_sha256=f"sha-{artifact_type}",
        )
        for artifact_type in (
            "content_reading",
            "content_map_candidate",
            "topic_brief",
            "message_plan",
            "draft_version",
        )
    )
    sealed = SimpleNamespace(storage_order=lambda: artifacts)
    seal = Mock(return_value=sealed)
    repository = SimpleNamespace(
        get_project=AsyncMock(return_value=object()),
        put_artifact=AsyncMock(side_effect=lambda artifact: artifact),
    )
    monkeypatch.setattr(content_intelligence_tool_module, "seal_content_run_artifacts", seal)
    monkeypatch.setattr(
        content_intelligence_tool_module,
        "_get_incubation_repository",
        Mock(return_value=repository),
    )

    judgment_artifact = object()
    receipt = await content_intelligence_tool_module._persist_content_run(
        bundle=object(),
        delivery=object(),
        runtime=SimpleNamespace(
            context={
                "incubation_project_id": "golden-gift",
                "user_id": "user-1",
                "thread_id": "thread-1",
                "run_id": "run-1",
            },
            config={"configurable": {"thread_id": "thread-1"}},
        ),
        topic_evidence_snapshots=(),
        incubation_judgment_artifact=judgment_artifact,
    )

    project = ProjectRef(owner_user_id="user-1", project_id="golden-gift")
    repository.get_project.assert_awaited_once_with(project)
    assert repository.put_artifact.await_count == 5
    assert seal.call_args.kwargs["project"] == project
    assert seal.call_args.kwargs["source_thread_id"] == "thread-1"
    assert seal.call_args.kwargs["source_run_id"] == "run-1"
    assert seal.call_args.kwargs["incubation_judgment_artifact"] is judgment_artifact
    assert receipt["status"] == "stored"
    assert receipt["project_id"] == "golden-gift"
    assert [item["artifact_type"] for item in receipt["artifacts"]] == [artifact.artifact_type for artifact in artifacts]
    assert "user-1" not in json.dumps(receipt)


@pytest.mark.asyncio
async def test_content_run_persistence_stores_used_topic_evidence_before_the_reading(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from deerflow.incubation import ArtifactParentRef

    snapshot = object()
    parent = ArtifactParentRef(
        owner_user_id="user-1",
        project_id="golden-gift",
        artifact_id="artifact-evidence",
        artifact_type="evidence_snapshot",
        content_sha256="a" * 64,
    )
    evidence_artifact = SimpleNamespace(
        artifact_type="evidence_snapshot",
        artifact_id=parent.artifact_id,
        content_sha256=parent.content_sha256,
        to_parent_ref=lambda: parent,
    )
    content_artifacts = tuple(
        SimpleNamespace(
            artifact_type=artifact_type,
            artifact_id=f"artifact-{artifact_type}",
            content_sha256=f"sha-{artifact_type}",
        )
        for artifact_type in (
            "content_reading",
            "content_map_candidate",
            "topic_brief",
            "message_plan",
            "draft_version",
        )
    )
    seal_content = Mock(return_value=SimpleNamespace(storage_order=lambda: content_artifacts))
    repository = SimpleNamespace(
        get_project=AsyncMock(return_value=object()),
        put_artifact=AsyncMock(side_effect=lambda artifact: artifact),
    )
    monkeypatch.setattr(
        content_intelligence_tool_module,
        "select_used_topic_evidence_snapshots",
        Mock(return_value=(snapshot,)),
    )
    seal_evidence = Mock(return_value=evidence_artifact)
    monkeypatch.setattr(content_intelligence_tool_module, "seal_evidence_snapshot", seal_evidence)
    monkeypatch.setattr(content_intelligence_tool_module, "seal_content_run_artifacts", seal_content)
    monkeypatch.setattr(
        content_intelligence_tool_module,
        "_get_incubation_repository",
        Mock(return_value=repository),
    )

    receipt = await content_intelligence_tool_module._persist_content_run(
        bundle=object(),
        delivery=object(),
        runtime=_tool_runtime(
            "content-world-call-with-evidence",
            context={"incubation_project_id": "golden-gift"},
        ),
        topic_evidence_snapshots=(snapshot,),
    )

    assert [call.args[0] for call in repository.put_artifact.await_args_list] == [
        evidence_artifact,
        *content_artifacts,
    ]
    assert seal_content.call_args.kwargs["reading_parents"] == (parent,)
    assert seal_evidence.call_args.kwargs["snapshot"] is snapshot
    assert [item["artifact_type"] for item in receipt["artifacts"]] == [
        "evidence_snapshot",
        "content_reading",
        "content_map_candidate",
        "topic_brief",
        "message_plan",
        "draft_version",
    ]


@pytest.mark.asyncio
async def test_persistence_stops_at_base_draft_without_explicit_presentation_adaptation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    content_artifacts = tuple(
        SimpleNamespace(
            artifact_type=artifact_type,
            artifact_id=f"artifact-{artifact_type}",
            content_sha256=f"sha-{artifact_type}",
        )
        for artifact_type in (
            "content_reading",
            "content_map_candidate",
            "topic_brief",
            "message_plan",
            "draft_version",
        )
    )
    repository = SimpleNamespace(
        get_project=AsyncMock(return_value=object()),
        put_artifact=AsyncMock(side_effect=lambda artifact: artifact),
        list_artifacts=AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        content_intelligence_tool_module,
        "_get_incubation_repository",
        Mock(return_value=repository),
    )
    monkeypatch.setattr(
        content_intelligence_tool_module,
        "seal_content_run_artifacts",
        Mock(return_value=SimpleNamespace(storage_order=lambda: content_artifacts)),
    )
    generate_format = AsyncMock()
    generate_adapted = AsyncMock()
    generate_production = AsyncMock()
    monkeypatch.setattr(content_intelligence_tool_module, "generate_format_decision", generate_format)
    monkeypatch.setattr(content_intelligence_tool_module, "generate_adapted_draft", generate_adapted)
    monkeypatch.setattr(content_intelligence_tool_module, "generate_production_plan", generate_production)

    receipt = await content_intelligence_tool_module._persist_content_run(
        bundle=object(),
        delivery=object(),
        runtime=_tool_runtime(
            "content-world-call-base-draft-only",
            context={"incubation_project_id": "old-books"},
        ),
        topic_evidence_snapshots=(),
        model=object(),
    )

    assert [call.args[0] for call in repository.put_artifact.await_args_list] == list(content_artifacts)
    repository.list_artifacts.assert_not_awaited()
    generate_format.assert_not_awaited()
    generate_adapted.assert_not_awaited()
    generate_production.assert_not_awaited()
    assert "_answer_appendix" not in receipt


@pytest.mark.asyncio
async def test_persistence_continues_through_production_plan_only_when_explicitly_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    content_artifacts = tuple(
        SimpleNamespace(
            artifact_type=artifact_type,
            artifact_id=f"artifact-{artifact_type}",
            content_sha256=f"sha-{artifact_type}",
        )
        for artifact_type in (
            "content_reading",
            "content_map_candidate",
            "topic_brief",
            "message_plan",
            "draft_version",
        )
    )
    artifacts_by_type = {item.artifact_type: item for item in content_artifacts}
    format_artifact = SimpleNamespace(
        artifact_type="format_decision",
        artifact_id="artifact-format",
        content_sha256="sha-format",
    )
    adapted_artifact = SimpleNamespace(
        artifact_type="adapted_draft",
        artifact_id="artifact-adapted",
        content_sha256="sha-adapted",
    )
    production_artifact = SimpleNamespace(
        artifact_type="production_plan",
        artifact_id="artifact-production",
        content_sha256="sha-production",
    )
    repository = SimpleNamespace(
        get_project=AsyncMock(return_value=object()),
        put_artifact=AsyncMock(side_effect=lambda artifact: artifact),
        list_artifacts=AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        content_intelligence_tool_module,
        "_get_incubation_repository",
        Mock(return_value=repository),
    )
    monkeypatch.setattr(
        content_intelligence_tool_module,
        "seal_content_run_artifacts",
        Mock(return_value=SimpleNamespace(storage_order=lambda: content_artifacts)),
    )
    generate_format = AsyncMock(return_value=format_artifact)
    generate_adapted = AsyncMock(return_value=adapted_artifact)
    generate_production = AsyncMock(return_value=production_artifact)
    monkeypatch.setattr(content_intelligence_tool_module, "generate_format_decision", generate_format)
    monkeypatch.setattr(content_intelligence_tool_module, "generate_adapted_draft", generate_adapted)
    monkeypatch.setattr(content_intelligence_tool_module, "generate_production_plan", generate_production)
    monkeypatch.setattr(
        content_intelligence_tool_module,
        "_render_format_decision_artifact",
        Mock(return_value="# 本条表现形式\n\n图文"),
    )
    monkeypatch.setattr(
        content_intelligence_tool_module,
        "_render_adapted_draft_artifact",
        Mock(return_value="# 形式适配稿\n\n适配后的正文"),
    )
    monkeypatch.setattr(
        content_intelligence_tool_module,
        "_render_production_plan_artifact",
        Mock(return_value="# 制作方案\n\n拍摄并装配"),
    )
    judgment_artifact = object()

    receipt = await content_intelligence_tool_module._persist_content_run(
        bundle=object(),
        delivery=object(),
        runtime=_tool_runtime(
            "content-world-call-preproduction",
            context={"incubation_project_id": "golden-gift"},
        ),
        topic_evidence_snapshots=(),
        incubation_judgment_artifact=judgment_artifact,
        model=object(),
        include_production_plan=True,
    )

    assert [call.args[0] for call in repository.put_artifact.await_args_list] == [
        *content_artifacts,
        format_artifact,
        adapted_artifact,
        production_artifact,
    ]
    assert generate_format.await_args.kwargs["message_plan_artifact"] is artifacts_by_type["message_plan"]
    assert generate_format.await_args.kwargs["base_draft_artifact"] is artifacts_by_type["draft_version"]
    assert generate_format.await_args.kwargs["incubation_judgment_artifact"] is judgment_artifact
    assert generate_adapted.await_args.kwargs["base_draft_artifact"] is artifacts_by_type["draft_version"]
    assert generate_adapted.await_args.kwargs["format_decision_artifact"] is format_artifact
    assert generate_production.await_args.kwargs["adapted_draft_artifact"] is adapted_artifact
    assert generate_production.await_args.kwargs["format_decision_artifact"] is format_artifact
    assert generate_production.await_args.kwargs["user_material_artifacts"] == ()
    assert [item["artifact_type"] for item in receipt["artifacts"]][-3:] == [
        "format_decision",
        "adapted_draft",
        "production_plan",
    ]
    assert receipt["_answer_appendix"] == ("# 本条表现形式\n\n图文\n\n# 形式适配稿\n\n适配后的正文\n\n# 制作方案\n\n拍摄并装配")


@pytest.mark.asyncio
async def test_persistence_can_stop_after_adapted_draft_without_starting_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    content_artifacts = tuple(
        SimpleNamespace(
            artifact_type=artifact_type,
            artifact_id=f"artifact-{artifact_type}",
            content_sha256=f"sha-{artifact_type}",
        )
        for artifact_type in (
            "content_reading",
            "content_map_candidate",
            "topic_brief",
            "message_plan",
            "draft_version",
        )
    )
    format_artifact = SimpleNamespace(
        artifact_type="format_decision",
        artifact_id="artifact-format",
        content_sha256="sha-format",
    )
    adapted_artifact = SimpleNamespace(
        artifact_type="adapted_draft",
        artifact_id="artifact-adapted",
        content_sha256="sha-adapted",
    )
    repository = SimpleNamespace(
        get_project=AsyncMock(return_value=object()),
        put_artifact=AsyncMock(side_effect=lambda artifact: artifact),
        list_artifacts=AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        content_intelligence_tool_module,
        "_get_incubation_repository",
        Mock(return_value=repository),
    )
    monkeypatch.setattr(
        content_intelligence_tool_module,
        "seal_content_run_artifacts",
        Mock(return_value=SimpleNamespace(storage_order=lambda: content_artifacts)),
    )
    generate_format = AsyncMock(return_value=format_artifact)
    generate_adapted = AsyncMock(return_value=adapted_artifact)
    generate_production = AsyncMock()
    monkeypatch.setattr(content_intelligence_tool_module, "generate_format_decision", generate_format)
    monkeypatch.setattr(content_intelligence_tool_module, "generate_adapted_draft", generate_adapted)
    monkeypatch.setattr(content_intelligence_tool_module, "generate_production_plan", generate_production)
    monkeypatch.setattr(
        content_intelligence_tool_module,
        "_render_format_decision_artifact",
        Mock(return_value="# 本条表现形式\n\n图文"),
    )
    monkeypatch.setattr(
        content_intelligence_tool_module,
        "_render_adapted_draft_artifact",
        Mock(return_value="# 形式适配稿\n\n适配后的正文"),
    )

    receipt = await content_intelligence_tool_module._persist_content_run(
        bundle=object(),
        delivery=object(),
        runtime=_tool_runtime(
            "content-world-call-adapted-only",
            context={"incubation_project_id": "pet-memorial"},
        ),
        topic_evidence_snapshots=(),
        model=object(),
        include_presentation_adaptation=True,
    )

    assert [call.args[0] for call in repository.put_artifact.await_args_list] == [
        *content_artifacts,
        format_artifact,
        adapted_artifact,
    ]
    generate_production.assert_not_awaited()
    assert [item["artifact_type"] for item in receipt["artifacts"]][-2:] == [
        "format_decision",
        "adapted_draft",
    ]
    assert receipt["_answer_appendix"] == "# 本条表现形式\n\n图文\n\n# 形式适配稿\n\n适配后的正文"


@pytest.mark.asyncio
async def test_content_run_persistence_is_optional_without_a_selected_project(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository_factory = Mock()
    monkeypatch.setattr(
        content_intelligence_tool_module,
        "_get_incubation_repository",
        repository_factory,
    )

    receipt = await content_intelligence_tool_module._persist_content_run(
        bundle=object(),
        delivery=None,
        runtime=_tool_runtime("content-world-call-no-project"),
        topic_evidence_snapshots=(),
    )

    assert receipt == {"status": "not_selected"}
    repository_factory.assert_not_called()


@pytest.mark.asyncio
async def test_content_world_tool_keeps_the_answer_when_project_persistence_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle = SimpleNamespace(topic_brief=object())
    shooting_delivery = object()
    persistence = {
        "status": "failed",
        "project_id": "golden-gift",
        "message": "The generated content could not be stored in the selected project.",
    }
    monkeypatch.setattr(content_intelligence_tool_module, "_create_content_intelligence_model", lambda config: object())
    monkeypatch.setattr(content_intelligence_tool_module, "_create_lexical_evidence_provider", lambda: None)
    monkeypatch.setattr(
        content_intelligence_tool_module,
        "analyze_content_intelligence",
        AsyncMock(return_value=bundle),
    )
    monkeypatch.setattr(
        content_intelligence_tool_module,
        "enrich_content_world_with_research",
        AsyncMock(return_value=bundle),
    )
    monkeypatch.setattr(
        content_intelligence_tool_module,
        "synthesize_shooting_delivery",
        AsyncMock(return_value=shooting_delivery),
    )
    monkeypatch.setattr(
        content_intelligence_tool_module,
        "render_shooting_delivery",
        Mock(return_value="# 今日建议拍摄\n\n## 古代的礼为什么不只是礼貌？"),
    )
    persist = AsyncMock(return_value=persistence)
    monkeypatch.setattr(content_intelligence_tool_module, "_persist_content_run", persist)

    result = await explore_content_world_tool.ainvoke(
        {
            "name": "explore_content_world",
            "args": {
                "user_request": "我是做黄金礼品的，我要怎么起号？",
                "runtime": _tool_runtime("content-world-call-persistence-failed"),
            },
            "id": "content-world-call-persistence-failed",
            "type": "tool_call",
        }
    )

    tool_message = result.update["messages"][0]
    assert tool_message.content.startswith("# 今日建议拍摄")
    assert tool_message.additional_kwargs["incubation_persistence"] == persistence
    persist.assert_awaited_once()
    assert persist.await_args.kwargs["bundle"] is bundle
    assert persist.await_args.kwargs["delivery"] is shooting_delivery
    assert "incubation_project_id" not in persist.await_args.kwargs["runtime"].context


def test_tool_schema_exposes_one_optional_shared_analysis_request() -> None:
    schema = content_intelligence_tool.args_schema.model_json_schema()

    assert set(schema["properties"]) == {
        "user_request",
        "subject_expression",
        "focus",
        "source_materials",
    }
    assert "optional" in content_intelligence_tool.description.lower()
    assert "final" in content_intelligence_tool.description.lower()
    focus_schema = schema["$defs"]["ToolAnalysisFocus"]
    assert focus_schema["enum"] == ["business_semantics", "topic_brief"]
    assert schema["properties"]["focus"]["default"] == "business_semantics"


def test_lead_prompt_uses_a_thin_content_incubation_contract() -> None:
    assert "content incubation and new-media operations agent" in SYSTEM_PROMPT_TEMPLATE
    assert "<content_intelligence>" in SYSTEM_PROMPT_TEMPLATE
    assert "analyze_content_intelligence" in SYSTEM_PROMPT_TEMPLATE
    assert "explore_content_world" in SYSTEM_PROMPT_TEMPLATE
    assert "develop_account_strategy" in SYSTEM_PROMPT_TEMPLATE
    assert "optional" in SYSTEM_PROMPT_TEMPLATE.lower()

    content_section = SYSTEM_PROMPT_TEMPLATE.split("<content_intelligence>", 1)[1].split("</content_intelligence>", 1)[0]
    assert "黄金礼品" not in content_section
    assert "海鲜" not in content_section
    assert "火锅底料" not in content_section
    assert "10 days" not in content_section
    assert "3 candidates" not in content_section
    normalized_section = " ".join(content_section.split())
    assert "Use `analyze_content_intelligence` for business semantics only" in normalized_section
    assert "answer_goal=`content_opportunities`" in normalized_section
    assert "answer_goal=`one_shootable_topic`" in normalized_section
    assert "cold-start business and content audience before content-root or map work" in normalized_section
    assert "Use `develop_account_strategy` for account-starting or positioning requests" in normalized_section
    assert "call `develop_account_strategy` as the first domain action" in normalized_section
    assert "subject_ref=`agent_self`" in normalized_section
    assert "subject_ref=`user_business`" in normalized_section
    assert "server-owned product profile" in normalized_section
    assert "audience_option_id" in normalized_section
    assert "must stop before content-root, map, benchmark, or strategy work" in normalized_section
    assert "Do not run generic web research or competitor discovery before that first proposal" in normalized_section
    assert "A candidate content map is input evidence, not an adopted account position" in normalized_section
    assert "never creates, confirms, or revises account strategy" in normalized_section
    assert "call `confirm_account_strategy` with that exact option id" in normalized_section
    assert "does not block a first proposal" in normalized_section
    assert "BenchmarkSnapshot" in normalized_section
    assert "cannot decide positioning" in normalized_section
    assert "Do not route a concrete shootable-topic request through `analyze_content_intelligence`" in normalized_section
    assert "omit `subject_expression` so the tool rehydrates that confirmed route's exact frozen map" in normalized_section
    assert "Delivery words such as topic, script, draft, or today's post are not the subject" in normalized_section
    assert "topic_seed" in normalized_section
    assert "contiguous verbatim span of the current user request" in normalized_section
    assert "posting cadence" in normalized_section
    assert "`content_entry` only explains the semantic route" in normalized_section
    assert "`content_root` is only the root of that candidate map" in normalized_section
    assert "long_term_positioning" not in normalized_section
    assert "audience territory define the account-level map" not in normalized_section
    assert "content root is the entry into the map" not in normalized_section
    assert "do not add an arbitrary number of posts, days, or branches" in normalized_section
    assert "do not pair it with `web_search`" in normalized_section
    assert "internal post-map research" in normalized_section
    for attention_leak in (
        "return path",
        "product-return",
        "commercial return",
        "object anchor",
        "bridge path",
    ):
        assert attention_leak not in content_section.lower()


def test_lead_routes_account_starting_before_manual_clarification() -> None:
    router = SYSTEM_PROMPT_TEMPLATE.split("<account_start_router>", 1)[1].split("</account_start_router>", 1)[0]
    normalized_router = " ".join(router.split())

    assert SYSTEM_PROMPT_TEMPLATE.index("<account_start_router>") < SYSTEM_PROMPT_TEMPLATE.index("<clarification_system>")
    assert "call `develop_account_strategy` as the first domain action" in normalized_router
    assert "Do not manually interview the user first" in normalized_router
    assert "subject_ref=`agent_self`" in normalized_router
    assert "subject_ref=`user_business`" in normalized_router
    assert "The tool itself returns a bounded audience choice" in normalized_router


def test_confirmed_route_reference_keeps_only_the_selected_name_and_id() -> None:
    judgment = SimpleNamespace(
        selected_option_id="route-old-book-history",
        route_options=(
            SimpleNamespace(
                option_id="route-old-book-history",
                name="旧书的履历表",
                positioning=SimpleNamespace(decision="以逐页翻阅和实物鉴定为基础，追踪每一本旧书跨越时代的完整流转史。"),
            ),
        ),
    )

    rendered = content_intelligence_tool_module._render_confirmed_route_reference(judgment)

    assert rendered == "## 已确认路线\n\n**沿用：** 旧书的履历表（route-old-book-history）"
    assert "逐页翻阅" not in rendered


def test_clarification_is_not_a_mandatory_business_workflow_gate() -> None:
    assert "MANDATORY Clarification Scenarios" not in SYSTEM_PROMPT_TEMPLATE
    assert "Approach Choices" not in SYSTEM_PROMPT_TEMPLATE
    assert "If missing details do not prevent a useful response" in SYSTEM_PROMPT_TEMPLATE
    assert "ALWAYS clarify unclear/missing/ambiguous requirements" not in SYSTEM_PROMPT_TEMPLATE
    assert "Scope-Aligned" in SYSTEM_PROMPT_TEMPLATE
