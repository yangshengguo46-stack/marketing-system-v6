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
    monkeypatch.setattr(content_intelligence_tool_module, "create_chat_model", create_model)

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
    monkeypatch.setattr(content_intelligence_tool_module, "runtime_home", lambda: tmp_path)

    assert content_intelligence_tool_module._create_lexical_evidence_provider() is None


def test_lexical_evidence_provider_is_created_from_the_untracked_local_index(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    index_path = "/tmp/local-cc-cedict.sqlite3"
    provider = object()
    provider_factory = Mock(return_value=provider)
    monkeypatch.setenv("CONTENT_INTELLIGENCE_CEDICT_INDEX", index_path)
    monkeypatch.setattr(
        content_intelligence_tool_module,
        "CedictLexicalEvidenceProvider",
        provider_factory,
    )

    actual = content_intelligence_tool_module._create_lexical_evidence_provider()

    assert actual is provider
    provider_factory.assert_called_once_with(index_path)


@pytest.mark.asyncio
async def test_content_world_tool_stops_after_the_frozen_map_for_long_term_positioning(
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
    positioning = Mock(return_value="# 账号内容定位\n\n**长期讲什么：** 火锅")
    monkeypatch.setattr(content_intelligence_tool_module, "_render_positioning_basis", positioning, raising=False)
    persist = AsyncMock(return_value={"status": "not_selected"})
    monkeypatch.setattr(content_intelligence_tool_module, "_persist_content_run", persist)

    result = await explore_content_world_tool.ainvoke(
        {
            "name": "explore_content_world",
            "args": {
                "user_request": "我是卖重庆火锅底料的，该怎么起号？",
                "answer_goal": "long_term_positioning",
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
    assert tool_message.content == "# 账号内容定位\n\n**长期讲什么：** 火锅"
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
    positioning.assert_called_once_with(bundle)


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
    render = Mock(return_value="# 账号内容定位\n\n**长期讲什么：** 饮酒与人际礼俗\n\n# 今日建议拍摄\n\n## 为什么当地的酒桌礼数这么重？")
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
    assert "# 长期定位依据" in rendered
    assert rendered.index("# 今日建议拍摄") < rendered.index("# 长期定位依据")
    delivery.assert_awaited_once()
    assert delivery.await_args.args[0] is enriched_bundle
    assert delivery.await_args.kwargs["user_request"] == user_request
    render.assert_called_once_with(enriched_bundle, shooting_delivery)
    research = content_intelligence_tool_module.enrich_content_world_with_research
    assert research.await_args.kwargs["topic_seed"] is None


@pytest.mark.asyncio
async def test_selected_project_prepares_incubation_judgment_before_delivery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle = object()
    enriched_bundle = SimpleNamespace(topic_brief=object())
    judgment = object()
    judgment_artifact = object()
    prepared = SimpleNamespace(
        judgment=judgment,
        judgment_artifact=judgment_artifact,
    )
    shooting_delivery = object()
    order: list[str] = []

    monkeypatch.setattr(content_intelligence_tool_module, "_create_content_intelligence_model", lambda config: object())
    monkeypatch.setattr(content_intelligence_tool_module, "_create_lexical_evidence_provider", lambda: None)
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

    async def prepare(**kwargs):
        order.append("prepare")
        return prepared

    async def deliver(*args, **kwargs):
        order.append("deliver")
        return shooting_delivery

    async def persist(**kwargs):
        order.append("persist")
        return {
            "status": "stored",
            "project_id": "project-1",
            "artifacts": [],
            "_answer_appendix": "# 本条表现形式\n\n图文",
        }

    monkeypatch.setattr(content_intelligence_tool_module, "_prepare_incubation_judgment", prepare)
    delivery = AsyncMock(side_effect=deliver)
    monkeypatch.setattr(content_intelligence_tool_module, "synthesize_shooting_delivery", delivery)
    persistence = AsyncMock(side_effect=persist)
    monkeypatch.setattr(content_intelligence_tool_module, "_persist_content_run", persistence)
    monkeypatch.setattr(
        content_intelligence_tool_module,
        "render_shooting_delivery",
        Mock(return_value="# 今日建议拍摄\n\n## 一条具体选题"),
    )
    render_judgment = Mock(return_value="# 孵化判断\n\n已形成项目级判断")
    monkeypatch.setattr(content_intelligence_tool_module, "_render_incubation_judgment", render_judgment)

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

    assert order == ["prepare", "deliver", "persist"]
    assert delivery.await_args.kwargs["incubation_judgment"] is judgment
    assert persistence.await_args.kwargs["incubation_judgment_artifact"] is judgment_artifact
    assert "# 孵化判断" in result.update["messages"][0].content
    assert "# 本条表现形式" in result.update["messages"][0].content
    assert "_answer_appendix" not in result.update["messages"][0].additional_kwargs["incubation_persistence"]
    render_judgment.assert_called_once_with(judgment)


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
    positioning = Mock(return_value="# 账号内容定位\n\n**长期讲什么：** 火锅")
    monkeypatch.setattr(content_intelligence_tool_module, "_render_positioning_basis", positioning, raising=False)

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
    assert "定位完成但未形成可拍选题" in content
    assert "# 账号内容定位" in content
    delivery.assert_not_awaited()
    positioning.assert_called_once_with(bundle)


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
        "_render_positioning_basis",
        Mock(return_value="# 账号内容定位\n\n**长期讲什么：** 火锅"),
        raising=False,
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

    assert "定位完成但未形成可拍选题" in result.update["messages"][0].content
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
        "_render_positioning_basis",
        Mock(return_value="# 账号内容定位\n\n**长期讲什么：** 火锅"),
        raising=False,
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

    assert "定位完成但未形成可拍选题" in result.update["messages"][0].content
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
        "_render_positioning_basis",
        Mock(return_value="# 账号内容定位\n\n**长期讲什么：** 火锅"),
        raising=False,
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

    assert "定位完成但未形成可拍选题" in result.update["messages"][0].content


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
        Mock(return_value="# 账号内容定位\n\n普通人观察\n\n# 今日建议拍摄\n\n## 为什么这部影片能火？"),
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
async def test_topic_seed_outside_user_request_is_rejected_before_analysis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    analysis = AsyncMock()
    research = AsyncMock()
    monkeypatch.setattr(content_intelligence_tool_module, "_create_content_intelligence_model", lambda config: object())
    monkeypatch.setattr(content_intelligence_tool_module, "analyze_content_intelligence", analysis)
    monkeypatch.setattr(content_intelligence_tool_module, "enrich_content_world_with_research", research)

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

    assert "选题线索必须直接来自你的原话" in result.update["messages"][0].content
    analysis.assert_not_awaited()
    research.assert_not_awaited()


def test_tool_layer_renders_positioning_as_basis_and_prioritizes_the_shootable_topic() -> None:
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

    positioning = content_intelligence_tool_module._render_positioning_basis(SimpleNamespace(content_world=world))
    prioritized = content_intelligence_tool_module._prioritize_shooting_delivery(positioning + "\n\n# 今日建议拍摄\n\n## 外国人到底吃不吃火锅？")

    assert "**长期讲什么：** 火锅" in positioning
    assert "外国人怎么吃火锅" in positioning
    assert prioritized.startswith("# 今日建议拍摄")
    assert "# 长期定位依据" in prioritized
    assert prioritized.index("# 今日建议拍摄") < prioritized.index("# 长期定位依据")


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

    rendered = content_intelligence_tool_module._render_incubation_judgment(judgment)

    assert rendered.startswith("# 孵化判断")
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
        "topic_seed",
        "user_request",
    }
    goal_schema = schema["$defs"]["ContentWorldAnswerGoal"]
    assert goal_schema["enum"] == ["long_term_positioning", "one_shootable_topic"]
    assert schema["properties"]["answer_goal"]["default"] == "one_shootable_topic"


@pytest.mark.asyncio
async def test_incubation_preparation_persists_brief_world_and_judgment_in_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from datetime import UTC, datetime

    from deerflow.incubation import ArtifactEnvelope, IncubationBrief, IncubationJudgment, ProjectRef

    project = ProjectRef(owner_user_id="user-1", project_id="golden-gift")
    now = datetime(2026, 8, 18, 1, 0, tzinfo=UTC)

    def artifact(artifact_type: str, payload: dict[str, object]) -> ArtifactEnvelope:
        return ArtifactEnvelope.seal(
            project=project,
            artifact_type=artifact_type,
            version=1,
            payload=payload,
            created_at=now,
            source_thread_id="thread-1",
            source_run_id="run-1",
        )

    reading = artifact("content_reading", {"record": "bounded"})
    world_artifact = artifact(
        "content_world",
        {
            "content_map_version_id": "map-1",
            "content_root": "礼与人与人相处",
        },
    )
    brief = artifact(
        "incubation_brief",
        IncubationBrief(subject_expression="我是做黄金礼品的，我要怎么起号？").model_dump(mode="json"),
    )
    judgment = artifact(
        "incubation_judgment",
        IncubationJudgment(content_map_version_id="map-1").model_dump(mode="json"),
    )
    repository = SimpleNamespace(
        get_project=AsyncMock(return_value=object()),
        put_artifact=AsyncMock(side_effect=lambda item: item),
        list_artifacts=AsyncMock(return_value=[reading, world_artifact, brief]),
    )
    monkeypatch.setattr(content_intelligence_tool_module, "_get_incubation_repository", Mock(return_value=repository))
    monkeypatch.setattr(
        content_intelligence_tool_module,
        "seal_content_run_artifacts",
        Mock(return_value=SimpleNamespace(storage_order=lambda: (reading, world_artifact))),
    )
    build_brief = Mock(return_value=brief)
    monkeypatch.setattr(content_intelligence_tool_module, "build_minimal_incubation_brief", build_brief)
    generate_judgment = AsyncMock(return_value=judgment)
    monkeypatch.setattr(content_intelligence_tool_module, "generate_incubation_judgment", generate_judgment)

    prepared = await content_intelligence_tool_module._prepare_incubation_judgment(
        bundle=SimpleNamespace(
            content_world=SimpleNamespace(
                content_root="礼与人与人相处",
                source_object="黄金礼品",
            )
        ),
        user_request="我是做黄金礼品的，我要怎么起号？",
        model=object(),
        runtime=_tool_runtime(
            "content-world-call-prepare",
            context={"incubation_project_id": "golden-gift"},
        ),
        topic_evidence_snapshots=(),
    )

    assert prepared is not None
    assert prepared.judgment_artifact is judgment
    assert prepared.judgment.content_map_version_id == "map-1"
    assert [call.args[0].artifact_type for call in repository.put_artifact.await_args_list] == [
        "content_reading",
        "content_world",
        "incubation_brief",
        "incubation_judgment",
    ]
    assert build_brief.call_args.kwargs["source_object"] == "黄金礼品"
    assert generate_judgment.await_args.kwargs["brief_artifact"] is brief
    assert generate_judgment.await_args.kwargs["content_world_artifact"] is world_artifact
    assert generate_judgment.await_args.kwargs["benchmark_evidence_artifacts"] == ()
    assert generate_judgment.await_args.kwargs["audience_evidence_artifacts"] == ()


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
            "content_world",
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
            "content_world",
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
        "content_world",
        "topic_brief",
        "message_plan",
        "draft_version",
    ]


@pytest.mark.asyncio
async def test_persistence_continues_from_base_draft_through_production_plan(
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
            "content_world",
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
    assert "optional" in SYSTEM_PROMPT_TEMPLATE.lower()

    content_section = SYSTEM_PROMPT_TEMPLATE.split("<content_intelligence>", 1)[1].split("</content_intelligence>", 1)[0]
    assert "黄金礼品" not in content_section
    assert "海鲜" not in content_section
    assert "火锅底料" not in content_section
    assert "10 days" not in content_section
    assert "3 candidates" not in content_section
    normalized_section = " ".join(content_section.split())
    assert "Use `analyze_content_intelligence` for business semantics only" in normalized_section
    assert "answer_goal=`long_term_positioning`" in normalized_section
    assert "answer_goal=`one_shootable_topic`" in normalized_section
    assert "only when the user explicitly asks just for positioning" in normalized_section
    assert 'A normal account-starting request such as "how should I start this account?"' in normalized_section
    assert "defaults to answer_goal=`one_shootable_topic`" in normalized_section
    assert "Do not route a concrete shootable-topic request through `analyze_content_intelligence`" in normalized_section
    assert "topic_seed" in normalized_section
    assert "contiguous verbatim span of the current user request" in normalized_section
    assert "what the account should talk about before how to operate it" in normalized_section
    assert "posting cadence" in normalized_section
    assert "provisional rooted map is already a useful answer" in normalized_section
    assert "do not call `ask_clarification` in that turn" in normalized_section
    assert "content root is the entry into the map" in normalized_section
    assert "Treat the rooted content map as complete for the current question" in normalized_section
    assert "do not extend it into an unrequested downstream operating plan" in normalized_section
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


def test_clarification_is_not_a_mandatory_business_workflow_gate() -> None:
    assert "MANDATORY Clarification Scenarios" not in SYSTEM_PROMPT_TEMPLATE
    assert "Approach Choices" not in SYSTEM_PROMPT_TEMPLATE
    assert "If missing details do not prevent a useful response" in SYSTEM_PROMPT_TEMPLATE
    assert "ALWAYS clarify unclear/missing/ambiguous requirements" not in SYSTEM_PROMPT_TEMPLATE
    assert "Scope-Aligned" in SYSTEM_PROMPT_TEMPLATE
