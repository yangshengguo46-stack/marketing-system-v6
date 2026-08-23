from __future__ import annotations

import importlib
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from langchain.tools import ToolRuntime
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.types import Command

from deerflow.agents.lead_agent.agent_core_contract import PRODUCTION_AGENT_KERNEL
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
    assert explore_content_world_tool.return_direct is False
    assert "not an account-strategy tool" in explore_content_world_tool.description
    assert "broad account-starting" not in content_intelligence_tool.description


def test_shootable_topic_failure_is_a_self_contained_terminal_receipt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        content_intelligence_tool_module,
        "_render_content_opportunity_map",
        lambda _bundle: "# 内容机会依据",
    )

    rendered = content_intelligence_tool_module._render_shootable_topic_failure(object())

    assert "这是失败回执，不是继续创作授权" in rendered
    assert "不要另行调用通用搜索或依据地图自行补写稿件" in rendered
    assert rendered.endswith("# 内容机会依据")


def test_global_lead_prompt_does_not_embed_content_surface_policy() -> None:
    assert "<content_intelligence>" not in SYSTEM_PROMPT_TEMPLATE
    assert "surface exclusions" not in SYSTEM_PROMPT_TEMPLATE
    assert "confirmed-direction reference" not in SYSTEM_PROMPT_TEMPLATE


def test_confirmed_direction_reference_projects_the_frozen_root_not_the_business_bearing_subject() -> None:
    selected_option = SimpleNamespace(
        name="关系观察向",
        content_root="人与人的关系本身",
        long_term_content_subject="人与人的关系本身：从商业对象切入但长期不围着商品讲",
    )
    direction = SimpleNamespace(selected_option=selected_option)

    rendered = content_intelligence_tool_module._render_confirmed_direction_reference(direction)

    assert "**沿用：** 关系观察向" in rendered
    assert "**内容根：** 人与人的关系本身" in rendered
    assert "长期内容主体" not in rendered
    assert "商业对象" not in rendered


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
async def test_term_evidence_search_uses_only_configured_web_search_and_preserves_exact_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, int]] = []

    @tool("web_search")
    async def configured_search(query: str, max_results: int = 5) -> str:
        """Search a term through the configured provider."""
        calls.append((query, max_results))
        return json.dumps(
            {
                "results": [
                    {
                        "title": "公开词项说明",
                        "url": "https://example.com/term",
                        "content": "只解释该词项。",
                    }
                ]
            }
        )

    search_config = SimpleNamespace(use="tests.fake:configured_search")
    monkeypatch.setattr(
        "deerflow.config.get_app_config",
        lambda: SimpleNamespace(
            get_tool_config=lambda name: search_config if name == "web_search" else None,
        ),
    )
    monkeypatch.setattr(
        "deerflow.reflection.resolve_variable",
        lambda use, expected: configured_search,
    )

    results = await incubation_tool_support_module.search_term_evidence(
        "MENA和CCA的TikTok直播公会",
        3,
    )

    assert calls == [("MENA和CCA的TikTok直播公会", 3)]
    assert len(results) == 1
    assert results[0].title == "公开词项说明"


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
    assert "deerflow_direct_response" not in tool_message.additional_kwargs
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
async def test_content_world_tool_falls_back_to_the_user_request_when_subject_is_paraphrased(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_request = "我在普通地级市有一家实体水果店，主要卖应季水果，想通过抖音让附近家庭知道我。"
    bundle = object()
    monkeypatch.setattr(content_intelligence_tool_module, "_create_content_intelligence_model", lambda config: object())
    monkeypatch.setattr(content_intelligence_tool_module, "_create_lexical_evidence_provider", lambda: None)
    analysis = AsyncMock(return_value=bundle)
    monkeypatch.setattr(content_intelligence_tool_module, "analyze_content_intelligence", analysis)
    monkeypatch.setattr(
        content_intelligence_tool_module,
        "_render_content_opportunity_map",
        Mock(return_value="# 候选内容机会地图\n\n**地图从哪里展开：** 家庭水果消费"),
    )
    monkeypatch.setattr(
        content_intelligence_tool_module,
        "_persist_content_run",
        AsyncMock(return_value={"status": "not_selected"}),
    )

    result = await explore_content_world_tool.ainvoke(
        {
            "name": "explore_content_world",
            "args": {
                "user_request": user_request,
                "subject_expression": "地级市水果店老板做本地抖音",
                "answer_goal": "content_opportunities",
                "runtime": _tool_runtime("content-world-paraphrase"),
            },
            "id": "content-world-paraphrase",
            "type": "tool_call",
        }
    )

    assert "家庭水果消费" in result.update["messages"][0].content
    assert analysis.await_args.args[0].subject_expression == user_request


@pytest.mark.asyncio
async def test_content_world_tool_does_not_recompute_a_map_twice_in_one_user_turn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _tool_runtime("content-world-repeat")
    runtime.state["messages"] = [
        HumanMessage(content="我是做水果零售的，该怎么起号？"),
        ToolMessage(
            content="# 候选内容机会地图\n\n**地图从哪里展开：** 家庭水果消费",
            tool_call_id="content-world-first",
            name="explore_content_world",
        ),
    ]
    analysis = AsyncMock()
    monkeypatch.setattr(content_intelligence_tool_module, "analyze_content_intelligence", analysis)

    result = await explore_content_world_tool.ainvoke(
        {
            "name": "explore_content_world",
            "args": {
                "user_request": "我是做水果零售的，该怎么起号？",
                "subject_expression": "水果零售",
                "answer_goal": "content_opportunities",
                "runtime": runtime,
            },
            "id": "content-world-repeat",
            "type": "tool_call",
        }
    )

    message = result.update["messages"][0]
    assert "本轮已有内容地图材料" in message.content
    assert "不要再次调用" in message.content
    analysis.assert_not_awaited()


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
    assert research.await_args.kwargs["current_user_request"] == user_request


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
async def test_confirmed_account_direction_guides_topic_without_requiring_a_bound_map(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle = object()
    enriched_bundle = SimpleNamespace(topic_brief=object())
    option = SimpleNamespace(
        option_id="direction_1",
        name="人情世故观察者",
        content_root=None,
        long_term_content_subject="人与人之间的相处与人情世故",
        content_audience_hypothesis="关心关系分寸与人情判断的人",
        audience_promise="用具体人物与事件讲清关系、分寸与人性",
        account_role="从礼品生意观察人情世界的经营者",
    )
    direction = SimpleNamespace(
        revision_number=1,
        selected_option=option,
        unknowns=("持续表现形式仍待确认",),
    )
    direction_artifact = object()
    prepared_direction = SimpleNamespace(
        direction=direction,
        direction_artifact=direction_artifact,
    )
    shooting_delivery = object()

    monkeypatch.setattr(content_intelligence_tool_module, "_create_content_intelligence_model", lambda config: object())
    monkeypatch.setattr(content_intelligence_tool_module, "_create_lexical_evidence_provider", lambda: None)
    monkeypatch.setattr(
        content_intelligence_tool_module,
        "_load_confirmed_topic_context",
        AsyncMock(return_value=None),
    )
    semantic_analysis = AsyncMock(return_value=bundle)
    monkeypatch.setattr(content_intelligence_tool_module, "analyze_content_intelligence", semantic_analysis)
    monkeypatch.setattr(content_intelligence_tool_module, "_load_current_account_strategy", AsyncMock(return_value=None))
    monkeypatch.setattr(
        content_intelligence_tool_module,
        "_load_current_account_direction",
        AsyncMock(return_value=prepared_direction),
    )
    research = AsyncMock(return_value=enriched_bundle)
    monkeypatch.setattr(content_intelligence_tool_module, "enrich_content_world_with_research", research)
    monkeypatch.setattr(
        content_intelligence_tool_module,
        "DouyinMcpTopicEvidenceSearch",
        Mock(return_value=SimpleNamespace(snapshots=())),
    )
    delivery = AsyncMock(return_value=shooting_delivery)
    monkeypatch.setattr(content_intelligence_tool_module, "synthesize_shooting_delivery", delivery)
    persistence = AsyncMock(return_value={"status": "stored", "artifacts": []})
    monkeypatch.setattr(content_intelligence_tool_module, "_persist_content_run", persistence)
    monkeypatch.setattr(
        content_intelligence_tool_module,
        "render_shooting_delivery",
        Mock(return_value="# 今日建议拍摄\n\n## 小王送得贵，为什么升职的却是小张？"),
    )
    render_direction = Mock(return_value="## 已确认账号方向\n\n**沿用：** 人情世故观察者")
    monkeypatch.setattr(
        content_intelligence_tool_module,
        "_render_confirmed_direction_reference",
        render_direction,
    )

    result = await explore_content_world_tool.ainvoke(
        {
            "name": "explore_content_world",
            "args": {
                "user_request": "给我一个今天能拍的人情世故选题。",
                "subject_expression": "模型想改成黄金产品知识",
                "runtime": _tool_runtime(
                    "content-world-call-direction",
                    context={"incubation_project_id": "project-1"},
                ),
            },
            "id": "content-world-call-direction",
            "type": "tool_call",
        }
    )

    editorial_context = research.await_args.kwargs["editorial_context"]
    semantic_request = semantic_analysis.await_args.args[0]
    assert semantic_request.user_request == "人与人之间的相处与人情世故"
    assert semantic_request.subject_expression == "人与人之间的相处与人情世故"
    assert semantic_request.frozen_content_root == "人与人之间的相处与人情世故"
    assert "今天能拍" not in semantic_request.user_request
    assert editorial_context.route_id == "direction_1"
    assert editorial_context.content_subject == "人与人之间的相处与人情世故"
    assert editorial_context.audience_people == "关心关系分寸与人情判断的人"
    assert delivery.await_args.kwargs["editorial_context"] == editorial_context
    assert delivery.await_args.kwargs["incubation_judgment"] is None
    assert persistence.await_args.kwargs["account_direction_artifact"] is direction_artifact
    assert "已确认账号方向" in result.update["messages"][0].content
    render_direction.assert_called_once_with(direction)


@pytest.mark.asyncio
async def test_confirmed_launch_plan_seed_replaces_free_topic_seed_and_reuses_exact_map(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frozen_bundle = object()
    enriched_bundle = SimpleNamespace(
        topic_brief=SimpleNamespace(
            content_map_version_id="content-map-relations-v1",
            path=SimpleNamespace(path_id="path-rites"),
        )
    )
    shooting_delivery = object()
    direction = SimpleNamespace(
        selected_option=SimpleNamespace(
            option_id="direction_1",
            name="关系观察向",
            content_root="人与人的关系",
            long_term_content_subject="人与人的关系",
            audience_promise=None,
            content_audience_hypothesis=None,
            account_role=None,
        )
    )
    direction_artifact = object()
    prepared_direction = SimpleNamespace(
        direction=direction,
        direction_artifact=direction_artifact,
    )
    plan_artifact = SimpleNamespace(
        artifact_id="artifact-plan-confirmed",
        content_sha256="a" * 64,
    )
    planned_seed = SimpleNamespace(
        seed_id="seed-rites",
        map_path_id="path-rites",
        concrete_event_or_question="古代的礼为什么不只是礼貌？",
    )
    launch_context = SimpleNamespace(
        bundle=frozen_bundle,
        plan=SimpleNamespace(content_map_version_id="content-map-relations-v1"),
        plan_artifact=plan_artifact,
        topic_seed=planned_seed,
        direction=prepared_direction,
        strategy=None,
    )
    load_direction = AsyncMock(return_value=prepared_direction)
    load_launch = AsyncMock(return_value=launch_context)
    semantic_analysis = AsyncMock()
    research = AsyncMock(return_value=enriched_bundle)
    persistence = AsyncMock(return_value={"status": "stored", "artifacts": []})

    monkeypatch.setattr(content_intelligence_tool_module, "_create_content_intelligence_model", lambda config: object())
    monkeypatch.setattr(content_intelligence_tool_module, "_create_lexical_evidence_provider", lambda: None)
    monkeypatch.setattr(content_intelligence_tool_module, "_load_current_account_direction", load_direction)
    monkeypatch.setattr(content_intelligence_tool_module, "_load_confirmed_launch_topic_context", load_launch)
    monkeypatch.setattr(content_intelligence_tool_module, "analyze_content_intelligence", semantic_analysis)
    monkeypatch.setattr(content_intelligence_tool_module, "enrich_content_world_with_research", research)
    monkeypatch.setattr(
        content_intelligence_tool_module,
        "DouyinMcpTopicEvidenceSearch",
        Mock(return_value=SimpleNamespace(snapshots=())),
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
    monkeypatch.setattr(content_intelligence_tool_module, "_persist_content_run", persistence)

    result = await explore_content_world_tool.ainvoke(
        {
            "name": "explore_content_world",
            "args": {
                "user_request": "按已确认计划做第一条。",
                "subject_expression": "黄金产品知识",
                "topic_seed": "模型自由补出的热点",
                "launch_plan_artifact_id": "artifact-plan-confirmed",
                "launch_topic_seed_id": "seed-rites",
                "runtime": _tool_runtime(
                    "content-world-launch-seed",
                    context={"incubation_project_id": "golden-gift"},
                ),
            },
            "id": "content-world-launch-seed",
            "type": "tool_call",
        }
    )

    load_direction.assert_awaited_once()
    load_launch.assert_awaited_once_with(
        runtime=load_launch.await_args.kwargs["runtime"],
        plan_artifact_id="artifact-plan-confirmed",
        topic_seed_id="seed-rites",
        current_direction=prepared_direction,
    )
    semantic_analysis.assert_not_awaited()
    assert research.await_args.args[0] is frozen_bundle
    assert research.await_args.kwargs["topic_seed"] == "古代的礼为什么不只是礼貌？"
    assert "模型自由补出的热点" not in research.await_args.kwargs["topic_seed"]
    assert persistence.await_args.kwargs["launch_plan_artifact"] is plan_artifact
    assert persistence.await_args.kwargs["launch_topic_seed_id"] == "seed-rites"
    rendered = result.update["messages"][0].content
    assert "## 已确认起号计划题眼" in rendered
    assert "artifact-plan-confirmed" in rendered
    assert "seed-rites" in rendered


@pytest.mark.asyncio
async def test_launch_plan_and_seed_receipts_are_rejected_when_only_one_is_supplied(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    analysis = AsyncMock()
    monkeypatch.setattr(content_intelligence_tool_module, "analyze_content_intelligence", analysis)

    result = await explore_content_world_tool.ainvoke(
        {
            "name": "explore_content_world",
            "args": {
                "user_request": "按起号计划做第一条。",
                "launch_plan_artifact_id": "artifact-plan-confirmed",
                "runtime": _tool_runtime("content-world-incomplete-launch-seed"),
            },
            "id": "content-world-incomplete-launch-seed",
            "type": "tool_call",
        }
    )

    assert "必须成对提供" in result.update["messages"][0].content
    assert "没有使用模型自由补出" in result.update["messages"][0].content
    analysis.assert_not_awaited()


def test_launch_topic_brief_must_instantiate_the_selected_plan_seed_path() -> None:
    context = SimpleNamespace(
        plan=SimpleNamespace(content_map_version_id="content-map-relations-v1"),
        topic_seed=SimpleNamespace(map_path_id="path-rites"),
    )
    wrong_path_bundle = SimpleNamespace(
        topic_brief=SimpleNamespace(
            content_map_version_id="content-map-relations-v1",
            path=SimpleNamespace(path_id="path-products"),
        )
    )

    with pytest.raises(ValueError, match="selected seed path"):
        content_intelligence_tool_module._validate_launch_topic_brief(
            bundle=wrong_path_bundle,
            context=context,
        )


def test_confirmed_direction_uses_its_concise_subject_as_the_frozen_root() -> None:
    option = SimpleNamespace(
        content_root=None,
        long_term_content_subject=("人与人的关系本身：面子、人情往来、还礼与亏欠、回报与边界。黄金礼品是人情世界中的一个工具和符号。"),
    )

    assert content_intelligence_tool_module._direction_frozen_content_root(option) == "人与人的关系本身"


@pytest.mark.asyncio
async def test_current_direction_loader_reads_the_implicit_thread_scope_without_a_map(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from datetime import UTC, datetime

    from deerflow.incubation import (
        AccountDirectionOption,
        AccountDirectionVersion,
        ArtifactEnvelope,
        implicit_thread_logical_account_ref,
        implicit_thread_project_ref,
    )

    project = implicit_thread_project_ref(owner_user_id="user-1", thread_id="thread-1")
    logical_account = implicit_thread_logical_account_ref(project=project, thread_id="thread-1")
    direction = AccountDirectionVersion(
        revision_number=1,
        proposal_artifact_id="artifact_proposal",
        source_user_text="我是做黄金礼品的，我要怎么起号？",
        confirmation_user_text="我确认这个方向",
        marketing_subject="黄金礼品",
        selected_option=AccountDirectionOption(
            option_id="direction_1",
            name="人情世故观察者",
            long_term_content_subject="人与人之间的相处与人情世故",
            rationale="从礼品用途进入长期关系世界。",
        ),
    )
    artifact = ArtifactEnvelope.seal(
        project=project,
        logical_account=logical_account,
        artifact_type="account_direction_version",
        version=1,
        payload=direction.model_dump(mode="json"),
        created_at=datetime(2026, 8, 22, 12, 0, tzinfo=UTC),
        source_thread_id="thread-1",
        source_run_id="run-1",
    )
    repository = SimpleNamespace(
        get_project=AsyncMock(return_value=object()),
        list_artifacts=AsyncMock(return_value=[artifact]),
    )
    monkeypatch.setattr(content_intelligence_tool_module, "_get_incubation_repository", lambda: repository)

    loaded = await content_intelligence_tool_module._load_current_account_direction(runtime=_tool_runtime("load-direction"))

    assert loaded is not None
    assert loaded.direction_artifact == artifact
    assert loaded.direction.selected_option.long_term_content_subject == "人与人之间的相处与人情世故"
    repository.list_artifacts.assert_awaited_once_with(
        project,
        logical_account=logical_account,
        artifact_type="account_direction_version",
    )


@pytest.mark.asyncio
async def test_launch_topic_loader_requires_exact_current_lineage_and_unchanged_proposal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from datetime import UTC, datetime, timedelta

    from deerflow.content_intelligence import (
        ComprehensionRecord,
        ContentDimension,
        ContentIntelligenceBundle,
        ContentPath,
        ContentPathStep,
        ContentWorldView,
        SourceItem,
    )
    from deerflow.incubation import (
        AccountDirectionOption,
        AccountDirectionProposal,
        AccountDirectionVersion,
        AccountLaunchPlan,
        ArtifactEnvelope,
        FirstWeekDay,
        LaunchCapacity,
        LaunchCheckpoint,
        LaunchPhase,
        LaunchSeries,
        PlannedTopicSeed,
        account_launch_plan_confirmation_text,
        implicit_thread_logical_account_ref,
        seal_content_run_artifacts,
        select_current_account_direction,
    )
    from deerflow.incubation.contracts import ProjectRef

    now = datetime(2026, 8, 22, 13, 0, tzinfo=UTC)
    project = ProjectRef(owner_user_id="user-1", project_id="golden-gift")
    logical_account = implicit_thread_logical_account_ref(
        project=project,
        thread_id="thread-1",
    )
    selected_option = AccountDirectionOption(
        option_id="direction_1",
        name="礼与关系",
        content_root="礼与人与人相处",
        long_term_content_subject="礼与人与人相处",
        rationale="从具体赠与事件观察关系。",
    )
    proposal_payload = AccountDirectionProposal(
        target_revision_number=1,
        source_user_text="我是做黄金礼品的，想从礼与关系切入。",
        marketing_subject="黄金礼品",
        direction_options=(selected_option,),
        recommended_option_id="direction_1",
    )
    proposal_artifact = ArtifactEnvelope.seal(
        project=project,
        logical_account=logical_account,
        artifact_type="account_direction_proposal",
        version=1,
        payload=proposal_payload.model_dump(mode="json"),
        created_at=now,
        source_thread_id="thread-proposal",
        source_run_id="run-proposal",
    )
    direction_payload = AccountDirectionVersion(
        revision_number=1,
        proposal_artifact_id=proposal_artifact.artifact_id,
        source_user_text="我是做黄金礼品的，想从礼与关系切入。",
        confirmation_user_text="确认这个方向。",
        marketing_subject="黄金礼品",
        selected_option=selected_option,
    )
    direction_artifact = ArtifactEnvelope.seal(
        project=project,
        logical_account=logical_account,
        artifact_type="account_direction_version",
        version=1,
        payload=direction_payload.model_dump(mode="json"),
        parents=(proposal_artifact.to_parent_ref(),),
        created_at=now,
        source_thread_id="thread-direction",
        source_run_id="run-direction",
    )
    record = ComprehensionRecord(
        record_id="record-gift",
        subject_expression="我是做黄金礼品的",
        sources=(
            SourceItem(
                source_id="source-user",
                kind="user_statement",
                content="我是做黄金礼品的",
            ),
        ),
    )
    path = ContentPath(
        path_id="path-rites",
        steps=(
            ContentPathStep(
                from_label="礼与人与人相处",
                relation="通过具体制度观察",
                to_label="古代礼制",
                status="candidate",
                verification_needed=True,
            ),
        ),
        rationale="从具体礼制理解关系。",
    )
    world = ContentWorldView(
        record_id=record.record_id,
        source_object="黄金礼品",
        content_entry="送礼",
        content_root="礼与人与人相处",
        root_rationale="从送礼进入礼与关系。",
        editorial_promise="用具体事件理解礼与关系。",
        recurring_lens="观察人物、时间、地方和事件。",
        dimensions=(
            ContentDimension(
                name="制度与习俗",
                rationale="礼如何成为制度。",
                paths=(path,),
            ),
        ),
    )
    map_run = seal_content_run_artifacts(
        project=project,
        logical_account=logical_account,
        bundle=ContentIntelligenceBundle(record=record, content_world=world),
        delivery=None,
        account_direction_artifact=direction_artifact,
        created_at=now,
        source_thread_id="thread-map",
        source_run_id="run-map",
    )
    plan_proposal = AccountLaunchPlan(
        direction_artifact_id=direction_artifact.artifact_id,
        content_map_version_id=world.content_map_version_id(),
        planning_request="编排首轮起号计划",
        capacity=LaunchCapacity(
            status="provisional",
            cadence_summary="先做一条。",
            basis="用户尚未确认发布能力。",
            adjustment_trigger="按实际回执调整。",
        ),
        series=(
            LaunchSeries(
                series_id="rites",
                name="礼制与关系",
                purpose="从礼制观察关系。",
                map_path_ids=("path-rites",),
                repeatable_question="一项礼制怎样安排关系？",
                topic_sources=("public_evidence",),
            ),
        ),
        topic_seeds=(
            PlannedTopicSeed(
                seed_id="seed-rites",
                series_id="rites",
                map_path_id="path-rites",
                content_role="understanding",
                focal_subject="古代礼制",
                concrete_event_or_question="古代的礼为什么不只是礼貌？",
                account_viewpoint="从礼品经营者的视角观察。",
                source_kind="public_evidence",
                evidence_need="可核验的礼制资料。",
            ),
        ),
        first_week=tuple(
            FirstWeekDay(
                day=day,
                focus=f"第 {day} 天",
                actions=("核对证据。",),
                topic_seed_ids=(("seed-rites",) if day == 1 else ()),
            )
            for day in range(1, 8)
        ),
        later_phases=(
            LaunchPhase(
                start_day=8,
                end_day=30,
                objective="按回执调整。",
                series_ids=("rites",),
                actions=("回收结果。",),
                review_questions=("是否继续？",),
            ),
        ),
        checkpoints=(
            LaunchCheckpoint(
                day=7,
                questions=("题眼是否成立？",),
                possible_adjustments=("调整证据需求。",),
            ),
            LaunchCheckpoint(
                day=30,
                questions=("系列是否继续？",),
                possible_adjustments=("保留或停止。",),
            ),
        ),
    )
    plan_proposal_artifact = ArtifactEnvelope.seal(
        project=project,
        logical_account=logical_account,
        artifact_type="account_launch_plan",
        version=plan_proposal.revision_number,
        payload=plan_proposal.model_dump(mode="json"),
        parents=(
            direction_artifact.to_parent_ref(),
            map_run.content_world.to_parent_ref(),
        ),
        created_at=now,
        source_thread_id="thread-plan-proposal",
        source_run_id="run-plan-proposal",
    )
    plan = AccountLaunchPlan.model_validate(
        plan_proposal.model_copy(
            update={
                "revision_number": 2,
                "supersedes_plan_artifact_id": plan_proposal_artifact.artifact_id,
                "revision_reason": "用户确认采用当前起号计划。",
                "decision_status": "confirmed",
                "confirmation_user_text": account_launch_plan_confirmation_text(plan_proposal_artifact.artifact_id),
            }
        ).model_dump(mode="json")
    )
    plan_artifact = ArtifactEnvelope.seal(
        project=project,
        logical_account=logical_account,
        artifact_type="account_launch_plan",
        version=plan.revision_number,
        payload=plan.model_dump(mode="json"),
        parents=(
            direction_artifact.to_parent_ref(),
            map_run.content_world.to_parent_ref(),
            plan_proposal_artifact.to_parent_ref(),
        ),
        created_at=now,
        source_thread_id="thread-plan",
        source_run_id="run-plan",
    )
    stored = [
        proposal_artifact,
        direction_artifact,
        map_run.content_reading,
        map_run.content_world,
        plan_proposal_artifact,
        plan_artifact,
    ]
    repository = SimpleNamespace(
        get_project=AsyncMock(return_value=object()),
        list_artifacts=AsyncMock(return_value=stored),
    )
    monkeypatch.setattr(content_intelligence_tool_module, "_get_incubation_repository", lambda: repository)
    current_direction = select_current_account_direction(
        stored,
        logical_account=logical_account,
    )
    assert current_direction is not None

    context = await content_intelligence_tool_module._load_confirmed_launch_topic_context(
        runtime=_tool_runtime(
            "load-launch-topic",
            context={"incubation_project_id": project.project_id},
        ),
        plan_artifact_id=plan_artifact.artifact_id,
        topic_seed_id="seed-rites",
        current_direction=current_direction,
    )

    assert context.plan_artifact == plan_artifact
    assert context.topic_seed.seed_id == "seed-rites"
    assert context.bundle.content_world is not None
    assert context.bundle.content_world.content_map_version_id() == world.content_map_version_id()
    assert context.direction == current_direction
    assert context.strategy is None

    with pytest.raises(ValueError, match="exact current confirmed"):
        await content_intelligence_tool_module._load_confirmed_launch_topic_context(
            runtime=_tool_runtime(
                "load-stale-launch-topic",
                context={"incubation_project_id": project.project_id},
            ),
            plan_artifact_id="artifact-stale-plan",
            topic_seed_id="seed-rites",
            current_direction=current_direction,
        )

    with pytest.raises(ValueError, match="absent from the confirmed plan"):
        await content_intelligence_tool_module._load_confirmed_launch_topic_context(
            runtime=_tool_runtime(
                "load-unknown-launch-seed",
                context={"incubation_project_id": project.project_id},
            ),
            plan_artifact_id=plan_artifact.artifact_id,
            topic_seed_id="seed-not-in-plan",
            current_direction=current_direction,
        )

    orphan_plan_artifact = ArtifactEnvelope.seal(
        project=project,
        logical_account=logical_account,
        artifact_type="account_launch_plan",
        version=plan.revision_number,
        payload=plan.model_dump(mode="json"),
        parents=(
            direction_artifact.to_parent_ref(),
            map_run.content_world.to_parent_ref(),
        ),
        created_at=now + timedelta(seconds=1),
        source_thread_id="thread-orphan-plan",
        source_run_id="run-orphan-plan",
    )
    repository.list_artifacts.return_value = [
        *stored[:-1],
        orphan_plan_artifact,
    ]
    with pytest.raises(ValueError, match="exactly one account_launch_plan parent"):
        await content_intelligence_tool_module._load_confirmed_launch_topic_context(
            runtime=_tool_runtime(
                "load-orphan-launch-plan",
                context={"incubation_project_id": project.project_id},
            ),
            plan_artifact_id=orphan_plan_artifact.artifact_id,
            topic_seed_id="seed-rites",
            current_direction=current_direction,
        )
    repository.list_artifacts.return_value = stored

    changed_plan = AccountLaunchPlan.model_validate(plan.model_copy(update={"planning_request": "确认时被篡改的起号计划"}).model_dump(mode="json"))
    changed_plan_artifact = ArtifactEnvelope.seal(
        project=project,
        logical_account=logical_account,
        artifact_type="account_launch_plan",
        version=changed_plan.revision_number,
        payload=changed_plan.model_dump(mode="json"),
        parents=(
            direction_artifact.to_parent_ref(),
            map_run.content_world.to_parent_ref(),
            plan_proposal_artifact.to_parent_ref(),
        ),
        created_at=now + timedelta(seconds=1),
        source_thread_id="thread-changed-plan",
        source_run_id="run-changed-plan",
    )
    repository.list_artifacts.return_value = [
        *stored[:-1],
        changed_plan_artifact,
    ]
    with pytest.raises(ValueError, match="changed content after its proposal"):
        await content_intelligence_tool_module._load_confirmed_launch_topic_context(
            runtime=_tool_runtime(
                "load-changed-launch-plan",
                context={"incubation_project_id": project.project_id},
            ),
            plan_artifact_id=changed_plan_artifact.artifact_id,
            topic_seed_id="seed-rites",
            current_direction=current_direction,
        )
    repository.list_artifacts.return_value = stored

    orphan_direction_artifact = ArtifactEnvelope.seal(
        project=project,
        logical_account=logical_account,
        artifact_type="account_direction_version",
        version=1,
        payload=direction_payload.model_dump(mode="json"),
        created_at=now,
        source_thread_id="thread-orphan-direction",
        source_run_id="run-orphan-direction",
    )
    orphan_direction = select_current_account_direction(
        [orphan_direction_artifact],
        logical_account=logical_account,
    )
    assert orphan_direction is not None
    orphan_map = ArtifactEnvelope.seal(
        project=project,
        logical_account=logical_account,
        artifact_type="content_map_candidate",
        version=1,
        payload=map_run.content_world.payload,
        parents=(orphan_direction_artifact.to_parent_ref(),),
        created_at=now,
        source_thread_id="thread-orphan-map",
        source_run_id="run-orphan-map",
    )
    with pytest.raises(ValueError, match="exact proposal parent"):
        content_intelligence_tool_module._validate_direction_map_link(
            direction=orphan_direction,
            map_artifact=orphan_map,
            artifacts_by_id={proposal_artifact.artifact_id: proposal_artifact},
        )

    tampered_direction_payload = direction_payload.model_copy(update={"selected_option": selected_option.model_copy(update={"name": "被篡改的方向名"})})
    tampered_direction_artifact = ArtifactEnvelope.seal(
        project=project,
        logical_account=logical_account,
        artifact_type="account_direction_version",
        version=1,
        payload=tampered_direction_payload.model_dump(mode="json"),
        parents=(proposal_artifact.to_parent_ref(),),
        created_at=now,
        source_thread_id="thread-tampered-direction",
        source_run_id="run-tampered-direction",
    )
    tampered_direction = select_current_account_direction(
        [tampered_direction_artifact],
        logical_account=logical_account,
    )
    assert tampered_direction is not None
    tampered_map = ArtifactEnvelope.seal(
        project=project,
        logical_account=logical_account,
        artifact_type="content_map_candidate",
        version=1,
        payload=map_run.content_world.payload,
        parents=(tampered_direction_artifact.to_parent_ref(),),
        created_at=now,
        source_thread_id="thread-tampered-map",
        source_run_id="run-tampered-map",
    )
    with pytest.raises(ValueError, match="exact proposal option"):
        content_intelligence_tool_module._validate_direction_map_link(
            direction=tampered_direction,
            map_artifact=tampered_map,
            artifacts_by_id={proposal_artifact.artifact_id: proposal_artifact},
        )


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
        "launch_plan_artifact_id",
        "launch_topic_seed_id",
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
async def test_launch_topic_persistence_uses_the_exact_implicit_plan_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from deerflow.incubation import (
        implicit_thread_logical_account_ref,
        implicit_thread_project_ref,
    )

    project = implicit_thread_project_ref(
        owner_user_id="user-1",
        thread_id="thread-1",
    )
    logical_account = implicit_thread_logical_account_ref(
        project=project,
        thread_id="thread-1",
    )
    plan_artifact = SimpleNamespace(project=project)
    repository = SimpleNamespace(
        get_project=AsyncMock(return_value=object()),
        put_artifact=AsyncMock(side_effect=lambda artifact: artifact),
    )
    seal = Mock(return_value=SimpleNamespace(storage_order=lambda: ()))
    monkeypatch.setattr(content_intelligence_tool_module, "_get_incubation_repository", lambda: repository)
    monkeypatch.setattr(content_intelligence_tool_module, "seal_content_run_artifacts", seal)

    receipt = await content_intelligence_tool_module._persist_content_run(
        bundle=object(),
        delivery=None,
        runtime=_tool_runtime("persist-implicit-launch-topic"),
        topic_evidence_snapshots=(),
        launch_plan_artifact=plan_artifact,
        launch_topic_seed_id="seed-rites",
    )

    assert receipt["status"] == "stored"
    assert receipt["project_id"] == project.project_id
    assert receipt["logical_account_id"] == logical_account.logical_account_id
    assert seal.call_args.kwargs["project"] == project
    assert seal.call_args.kwargs["launch_plan_artifact"] is plan_artifact
    assert seal.call_args.kwargs["launch_topic_seed_id"] == "seed-rites"


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
    normalized = " ".join(SYSTEM_PROMPT_TEMPLATE.split())

    assert SYSTEM_PROMPT_TEMPLATE.startswith(PRODUCTION_AGENT_KERNEL)
    assert "new-media incubation and operations employee" in normalized
    assert "no capability or workflow is mandatory" in normalized

    for embedded_domain_route in (
        "<account_incubation>",
        "<content_intelligence>",
        "analyze_content_intelligence",
        "explore_content_world",
        "develop_account_strategy",
        "answer_goal=`content_opportunities`",
        "answer_goal=`one_shootable_topic`",
        "BenchmarkSnapshot",
        "topic_seed",
        "posting cadence",
    ):
        assert embedded_domain_route not in SYSTEM_PROMPT_TEMPLATE

    for industry_answer in ("黄金礼品", "海鲜", "火锅底料", "10 days", "3 candidates"):
        assert industry_answer not in SYSTEM_PROMPT_TEMPLATE


def test_lead_owns_judgment_without_an_embedded_account_router() -> None:
    normalized = " ".join(PRODUCTION_AGENT_KERNEL.split())

    assert "Own the work the user gives you" in normalized
    assert "Think and act independently" in normalized
    assert "no capability or workflow is mandatory" in normalized
    assert "<account_incubation>" not in SYSTEM_PROMPT_TEMPLATE
    assert "fixed pipeline" not in SYSTEM_PROMPT_TEMPLATE
    assert "first domain action" not in SYSTEM_PROMPT_TEMPLATE
    assert "develop_account_strategy" not in SYSTEM_PROMPT_TEMPLATE


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
    normalized = " ".join(SYSTEM_PROMPT_TEMPLATE.split())

    assert "MANDATORY Clarification Scenarios" not in SYSTEM_PROMPT_TEMPLATE
    assert "Approach Choices" not in SYSTEM_PROMPT_TEMPLATE
    assert "If missing details do not prevent a useful response" in SYSTEM_PROMPT_TEMPLATE
    assert "ALWAYS clarify unclear/missing/ambiguous requirements" not in SYSTEM_PROMPT_TEMPLATE
    assert "Ask only when a missing user-owned fact truly blocks useful work" in normalized
