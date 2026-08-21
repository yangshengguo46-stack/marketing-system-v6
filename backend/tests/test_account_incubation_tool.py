from __future__ import annotations

import importlib
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from langchain.tools import ToolRuntime
from langchain_core.messages import ToolMessage
from langgraph.types import Command
from pydantic import BaseModel, Field, ValidationError

from deerflow.content_intelligence import TermEvidenceSearchResult, TermResolution
from deerflow.incubation import (
    implicit_thread_logical_account_ref,
    implicit_thread_project_ref,
)
from deerflow.incubation.account_audience import (
    AccountAudienceProposalDraft,
    AccountAudienceRouteDraft,
    MarketingSubjectSnapshot,
    compile_account_audience_decision,
)
from deerflow.tools.builtins.account_incubation_tool import (
    confirm_account_strategy_tool,
    develop_account_strategy_tool,
)
from deerflow.tools.tools import BUILTIN_TOOLS

tool_module = importlib.import_module("deerflow.tools.builtins.account_incubation_tool")


def _audience_route(
    option_id: str = "known_audience",
    *,
    target_people: str = "与用户业务直接相关的决策者",
    content_audience: str = "会持续关心该业务所在内容世界的人",
) -> AccountAudienceRouteDraft:
    return AccountAudienceRouteDraft(
        option_id=option_id,
        name="已明确的目标人群",
        business_role="用户明示的业务经营者",
        market_relationship="通过用户明示的业务服务目标人群",
        account_objective=f"让{target_people}理解并产生与该业务相关的下一步行动",
        payer_or_contracting_party=target_people,
        decision_makers=target_people,
        users_or_beneficiaries=target_people,
        target_people=target_people,
        target_need="解决与该业务相关的具体问题",
        desired_action="了解、咨询或进入用户已声明的业务承接",
        market_scope="用户尚未说明具体地区",
        content_audience=content_audience,
        recurring_interest="持续关心该业务背后的判断、人物、事件和经验",
        rationale="这是从已知业务关系得到的冷启动受众假设。",
        confidence="low",
        unknowns=("仍需对标证据和真实反馈校正",),
    )


def _prepared_resolved_audience(
    subject: MarketingSubjectSnapshot,
    *,
    route: AccountAudienceRouteDraft | None = None,
) -> SimpleNamespace:
    selected = route or _audience_route()
    decision = compile_account_audience_decision(
        subject=subject,
        draft=AccountAudienceProposalDraft(
            route_options=(selected,),
            recommended_option_id=selected.option_id,
            material_choice_required=False,
            choice_reason="用户原话已经明确这条业务与受众关系。",
        ),
    )
    return SimpleNamespace(
        decision=decision,
        decision_artifact=SimpleNamespace(
            artifact_type="account_audience_decision",
            artifact_id="artifact-audience-resolved",
            content_sha256="9" * 64,
        ),
        reused=False,
    )


@pytest.fixture(autouse=True)
def _resolve_audience_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    async def resolve(**kwargs):
        subject = kwargs["subject"]
        if subject is None:
            raise AssertionError("default audience fixture requires a subject")
        return _prepared_resolved_audience(subject)

    monkeypatch.setattr(
        tool_module,
        "prepare_account_audience",
        AsyncMock(side_effect=resolve),
        raising=False,
    )
    resolver = SimpleNamespace(
        resolve=AsyncMock(
            side_effect=lambda **kwargs: TermResolution.known(
                checked_terms=(kwargs["lexical_head"],),
            )
        )
    )
    monkeypatch.setattr(
        tool_module,
        "create_term_resolver",
        Mock(return_value=resolver),
        raising=False,
    )


def test_account_strategy_validation_diagnostics_expose_only_schema_locations() -> None:
    class _Fixture(BaseModel):
        bounded_text: str = Field(max_length=3)

    with pytest.raises(ValidationError) as captured:
        _Fixture.model_validate({"bounded_text": "sensitive-model-output"})

    diagnostics = tool_module._safe_validation_diagnostics(captured.value)

    assert diagnostics == ("bounded_text:string_too_long",)
    assert "sensitive-model-output" not in repr(diagnostics)


def _runtime(*, project_id: str | None) -> ToolRuntime:
    context = {
        "thread_id": "thread-1",
        "run_id": "run-1",
        "user_id": "user-1",
    }
    if project_id is not None:
        context["incubation_project_id"] = project_id
    return ToolRuntime(
        state={},
        context=context,
        config={"configurable": {"thread_id": "thread-1"}},
        stream_writer=lambda _: None,
        tools=[],
        tool_call_id="account-strategy-call",
        store=None,
    )


def test_account_strategy_tool_is_a_separate_lead_capability() -> None:
    assert develop_account_strategy_tool in BUILTIN_TOOLS
    assert develop_account_strategy_tool.name == "develop_account_strategy"
    assert develop_account_strategy_tool.return_direct is True
    schema = develop_account_strategy_tool.tool_call_schema.model_json_schema()
    assert set(schema["properties"]) == {
        "user_request",
        "subject_ref",
        "subject_expression",
        "audience_option_id",
        "incubation_skill",
    }
    assert "subject_ref" in schema["required"]
    assert schema["properties"]["audience_option_id"]["default"] is None
    assert schema["properties"]["subject_expression"]["default"] is None
    assert schema["properties"]["incubation_skill"]["default"] is None
    assert confirm_account_strategy_tool in BUILTIN_TOOLS
    assert confirm_account_strategy_tool.name == "confirm_account_strategy"
    assert confirm_account_strategy_tool.return_direct is True
    confirm_schema = confirm_account_strategy_tool.tool_call_schema.model_json_schema()
    assert set(confirm_schema["properties"]) == {"option_id"}


@pytest.mark.asyncio
async def test_user_business_term_is_verified_once_before_audience_and_reused_by_semantics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    order: list[str] = []
    repository = SimpleNamespace(
        get_project=AsyncMock(return_value=object()),
        get_logical_account=AsyncMock(return_value=object()),
    )
    resolution = TermResolution.from_search_results(
        query="MENA和CCA的TikTok直播公会",
        checked_terms=("MENA和CCA的TikTok直播公会",),
        unknown_terms=("MENA和CCA的TikTok直播公会",),
        results=(
            TermEvidenceSearchResult(
                title="区域与行业词项说明",
                url="https://example.com/tiktok-live-guild",
                content="MENA、CCA 与 TikTok 直播公会的公开词项摘要。",
            ),
        ),
    )

    async def resolve_term(**kwargs):
        order.append("term")
        return resolution

    resolver = SimpleNamespace(resolve=AsyncMock(side_effect=resolve_term))
    monkeypatch.setattr(tool_module, "create_term_resolver", Mock(return_value=resolver))
    captured_subjects: list[MarketingSubjectSnapshot] = []

    async def prepare_audience(**kwargs):
        order.append("audience")
        captured_subjects.append(kwargs["subject"])
        return _prepared_resolved_audience(kwargs["subject"])

    monkeypatch.setattr(tool_module, "prepare_account_audience", AsyncMock(side_effect=prepare_audience))
    bundle = SimpleNamespace(content_world=SimpleNamespace(content_root=None))

    async def analyze(*args, **kwargs):
        order.append("semantic")
        return bundle

    analysis = AsyncMock(side_effect=analyze)
    artifact = SimpleNamespace(
        artifact_type="incubation_judgment",
        artifact_id="artifact-new-term-strategy",
        content_sha256="d" * 64,
    )
    monkeypatch.setattr(tool_module, "get_incubation_repository", Mock(return_value=repository))
    monkeypatch.setattr(tool_module, "create_content_intelligence_model", Mock(return_value=object()))
    monkeypatch.setattr(tool_module, "create_lexical_evidence_provider", Mock(return_value=None))
    monkeypatch.setattr(tool_module, "analyze_content_intelligence", analysis)
    monkeypatch.setattr(
        tool_module,
        "prepare_account_strategy",
        AsyncMock(
            return_value=SimpleNamespace(
                judgment=object(),
                judgment_artifact=artifact,
                reused=False,
            )
        ),
    )
    monkeypatch.setattr(tool_module, "render_account_strategy", Mock(return_value="# 账号路线候选"))

    await develop_account_strategy_tool.ainvoke(
        {
            "name": "develop_account_strategy",
            "args": {
                "user_request": "我是做MENA和CCA的TikTok直播公会的，我该怎么起号？",
                "subject_ref": "user_business",
                "subject_expression": "MENA和CCA的TikTok直播公会",
                "runtime": _runtime(project_id="new-term-business"),
            },
            "id": "account-strategy-call",
            "type": "tool_call",
        }
    )

    assert order[:3] == ["term", "audience", "semantic"]
    resolver.resolve.assert_awaited_once_with(
        source_object="MENA和CCA的TikTok直播公会",
        lexical_head="MENA和CCA的TikTok直播公会",
        modifier_terms=(),
    )
    subject = captured_subjects[0]
    assert subject.subject_expression == "MENA和CCA的TikTok直播公会"
    assert subject.business_facts == ("我是做MENA和CCA的TikTok直播公会的，我该怎么起号？",)
    assert len(subject.term_evidence) == 1
    assert subject.term_evidence[0].evidence_role == "term_evidence"
    request = analysis.await_args.args[0]
    assert request.term_resolution_limitations == resolution.limitations
    assert len(request.source_materials) == 1
    assert request.source_materials[0].evidence_role == "term_evidence"
    assert analysis.await_args.kwargs["term_resolver"] is None


@pytest.mark.asyncio
async def test_user_business_subject_expression_must_be_a_verbatim_request_span(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = SimpleNamespace(
        get_project=AsyncMock(return_value=object()),
        get_logical_account=AsyncMock(return_value=object()),
    )
    resolver_factory = Mock()
    audience = AsyncMock()
    monkeypatch.setattr(tool_module, "get_incubation_repository", Mock(return_value=repository))
    monkeypatch.setattr(tool_module, "create_content_intelligence_model", Mock(return_value=object()))
    monkeypatch.setattr(tool_module, "create_term_resolver", resolver_factory)
    monkeypatch.setattr(tool_module, "prepare_account_audience", audience)

    result = await develop_account_strategy_tool.ainvoke(
        {
            "name": "develop_account_strategy",
            "args": {
                "user_request": "我是开水果店的，我该怎么起号？",
                "subject_ref": "user_business",
                "subject_expression": "不存在于原话的业务",
                "runtime": _runtime(project_id="invalid-subject-span"),
            },
            "id": "account-strategy-call",
            "type": "tool_call",
        }
    )

    assert "必须来自当前原话" in result.update["messages"][0].content
    resolver_factory.assert_not_called()
    audience.assert_not_awaited()


@pytest.mark.asyncio
async def test_account_strategy_tool_bootstraps_a_thread_project_before_model_work(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = SimpleNamespace(
        get_project=AsyncMock(return_value=None),
        create_project=AsyncMock(return_value=object()),
        get_logical_account=AsyncMock(return_value=None),
        create_logical_account=AsyncMock(return_value=object()),
    )
    bundle = object()
    artifact = SimpleNamespace(
        artifact_type="incubation_judgment",
        artifact_id="artifact-strategy-bootstrap",
        content_sha256="c" * 64,
    )
    prepared = SimpleNamespace(
        judgment=object(),
        judgment_artifact=artifact,
        reused=False,
    )
    create_model = Mock(return_value=object())
    monkeypatch.setattr(tool_module, "get_incubation_repository", Mock(return_value=repository))
    monkeypatch.setattr(tool_module, "create_content_intelligence_model", create_model)
    monkeypatch.setattr(tool_module, "create_lexical_evidence_provider", Mock(return_value=None))
    analysis = AsyncMock(return_value=bundle)
    monkeypatch.setattr(tool_module, "analyze_content_intelligence", analysis)
    prepare = AsyncMock(return_value=prepared)
    monkeypatch.setattr(tool_module, "prepare_account_strategy", prepare)
    monkeypatch.setattr(tool_module, "render_account_strategy", Mock(return_value="# 账号路线候选"))

    result = await develop_account_strategy_tool.ainvoke(
        {
            "name": "develop_account_strategy",
            "args": {
                "user_request": "我是开水果店的，我要怎么起号",
                "subject_ref": "user_business",
                "runtime": _runtime(project_id=None),
            },
            "id": "account-strategy-call",
            "type": "tool_call",
        }
    )

    assert isinstance(result, Command)
    expected_project = implicit_thread_project_ref(owner_user_id="user-1", thread_id="thread-1")
    expected_account = implicit_thread_logical_account_ref(
        project=expected_project,
        thread_id="thread-1",
    )
    assert repository.create_project.await_args.args == (expected_project,)
    assert repository.create_project.await_args.kwargs["display_name"] == "我是开水果店的，我要怎么起号"
    assert repository.create_logical_account.await_args.args == (expected_account,)
    assert repository.create_logical_account.await_args.kwargs["display_name"] == "我是开水果店的，我要怎么起号"
    assert prepare.await_args.kwargs["project"] == expected_project
    assert prepare.await_args.kwargs["logical_account"] == expected_account
    assert prepare.await_args.kwargs["bundle"] is bundle
    message = result.update["messages"][0]
    assert isinstance(message, ToolMessage)
    assert message.content == "# 账号路线候选"
    assert message.additional_kwargs["incubation_persistence"]["project_id"] == expected_project.project_id
    assert message.additional_kwargs["incubation_persistence"]["logical_account_id"] == expected_account.logical_account_id
    create_model.assert_called_once()
    analysis.assert_awaited_once()


@pytest.mark.asyncio
async def test_account_strategy_tool_redacts_implicit_project_bootstrap_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = SimpleNamespace(get_project=AsyncMock(side_effect=RuntimeError("database-secret")))
    create_model = Mock()
    monkeypatch.setattr(tool_module, "get_incubation_repository", Mock(return_value=repository))
    monkeypatch.setattr(tool_module, "create_content_intelligence_model", create_model)

    result = await develop_account_strategy_tool.ainvoke(
        {
            "name": "develop_account_strategy",
            "args": {
                "user_request": "我是开水果店的，我要怎么起号",
                "subject_ref": "user_business",
                "runtime": _runtime(project_id=None),
            },
            "id": "account-strategy-call",
            "type": "tool_call",
        }
    )

    assert isinstance(result, Command)
    message = result.update["messages"][0]
    assert isinstance(message, ToolMessage)
    assert message.content == "账号孵化台账暂时不可用，因此没有生成无法延续的临时定位。"
    assert "database-secret" not in message.content
    create_model.assert_not_called()


@pytest.mark.asyncio
async def test_account_strategy_tool_routes_candidate_map_and_project_evidence_to_strategy_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = SimpleNamespace(
        get_project=AsyncMock(return_value=object()),
        get_logical_account=AsyncMock(return_value=object()),
    )
    bundle = object()
    judgment = object()
    artifact = SimpleNamespace(
        artifact_type="incubation_judgment",
        artifact_id="artifact-strategy-1",
        content_sha256="a" * 64,
    )
    prepared = SimpleNamespace(
        judgment=judgment,
        judgment_artifact=artifact,
        reused=False,
    )
    monkeypatch.setattr(tool_module, "get_incubation_repository", Mock(return_value=repository))
    monkeypatch.setattr(tool_module, "create_content_intelligence_model", Mock(return_value=object()))
    monkeypatch.setattr(tool_module, "create_lexical_evidence_provider", Mock(return_value=None))
    analysis = AsyncMock(return_value=bundle)
    monkeypatch.setattr(tool_module, "analyze_content_intelligence", analysis)
    prepare = AsyncMock(return_value=prepared)
    monkeypatch.setattr(tool_module, "prepare_account_strategy", prepare)
    monkeypatch.setattr(tool_module, "render_account_strategy", Mock(return_value="# 账号路线候选\n\n**提案版本：** v1"))

    result = await develop_account_strategy_tool.ainvoke(
        {
            "name": "develop_account_strategy",
            "args": {
                "user_request": "我是做黄金礼品的，我要怎么起号？",
                "subject_ref": "user_business",
                "runtime": _runtime(project_id="golden-gift"),
            },
            "id": "account-strategy-call",
            "type": "tool_call",
        }
    )

    assert analysis.await_args.args[0].focus == "content_world"
    assert analysis.await_args.args[0].audience_context is not None
    assert prepare.await_args.kwargs["bundle"] is bundle
    assert prepare.await_args.kwargs["verbatim_user_request"] == "我是做黄金礼品的，我要怎么起号？"
    message = result.update["messages"][0]
    assert message.content.startswith("# 账号路线候选")
    assert message.additional_kwargs["incubation_persistence"]["artifact_id"] == "artifact-strategy-1"


@pytest.mark.asyncio
async def test_account_strategy_loads_the_named_vertical_skill_without_changing_user_words(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = SimpleNamespace(
        get_project=AsyncMock(return_value=object()),
        get_logical_account=AsyncMock(return_value=object()),
    )
    profile = SimpleNamespace(
        skill_name="incubate-gift-human-relations",
    )
    artifact = SimpleNamespace(
        artifact_type="incubation_judgment",
        artifact_id="artifact-strategy-domain-skill",
        content_sha256="d" * 64,
    )
    prepared = SimpleNamespace(
        judgment=object(),
        judgment_artifact=artifact,
        reused=False,
    )
    monkeypatch.setattr(tool_module, "get_incubation_repository", Mock(return_value=repository))
    monkeypatch.setattr(tool_module, "create_content_intelligence_model", Mock(return_value=object()))
    monkeypatch.setattr(tool_module, "create_lexical_evidence_provider", Mock(return_value=None))
    load_profile = Mock(return_value=profile)
    monkeypatch.setattr(tool_module, "load_incubation_skill_profile", load_profile, raising=False)
    analysis = AsyncMock(return_value=object())
    monkeypatch.setattr(tool_module, "analyze_content_intelligence", analysis)
    prepare = AsyncMock(return_value=prepared)
    monkeypatch.setattr(tool_module, "prepare_account_strategy", prepare)
    monkeypatch.setattr(tool_module, "render_account_strategy", Mock(return_value="# 账号路线候选"))

    await develop_account_strategy_tool.ainvoke(
        {
            "name": "develop_account_strategy",
            "args": {
                "user_request": "我是做婚礼伴手礼定制的，我要怎么起号？",
                "subject_ref": "user_business",
                "incubation_skill": "incubate-gift-human-relations",
                "runtime": _runtime(project_id="golden-gift"),
            },
            "id": "account-strategy-call",
            "type": "tool_call",
        }
    )

    load_profile.assert_called_once_with(
        "incubate-gift-human-relations",
        user_id="user-1",
    )
    request = analysis.await_args.args[0]
    assert request.user_request == "我是做婚礼伴手礼定制的，我要怎么起号？"
    assert analysis.await_args.kwargs["incubation_profile"] is profile
    assert "prohibited_assumptions" not in prepare.await_args.kwargs
    assert "excluded_content_branches" not in prepare.await_args.kwargs


@pytest.mark.asyncio
async def test_material_audience_choice_stops_before_content_root_map_and_benchmark(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = SimpleNamespace(
        get_project=AsyncMock(return_value=object()),
        get_logical_account=AsyncMock(return_value=object()),
    )
    subject = MarketingSubjectSnapshot(
        subject_kind="user_business",
        subject_expression="我是做水果生意的",
        source_user_request="我是做水果生意的，我要怎么起号",
        business_facts=("我是做水果生意的，我要怎么起号",),
    )
    proposal = compile_account_audience_decision(
        subject=subject,
        draft=AccountAudienceProposalDraft(
            route_options=(
                _audience_route(
                    "b2b_wholesale",
                    target_people="水果批发商、零售商和餐饮采购者",
                    content_audience="需要判断货源、品质和行情的经营者",
                ),
                _audience_route(
                    "b2c_retail",
                    target_people="家庭消费者和到店顾客",
                    content_audience="关心水果口感、选择、吃法和文化的人",
                ),
            ),
            recommended_option_id="b2b_wholesale",
            material_choice_required=True,
            choice_reason="批发和零售会改变对标、内容和成交对象。",
        ),
    )
    prepared = SimpleNamespace(
        decision=proposal,
        decision_artifact=SimpleNamespace(
            artifact_type="account_audience_decision",
            artifact_id="artifact-audience-choice",
            content_sha256="8" * 64,
        ),
        reused=False,
    )
    prepare_audience = AsyncMock(return_value=prepared)
    analysis = AsyncMock()
    collect = AsyncMock()
    prepare_strategy = AsyncMock()
    monkeypatch.setattr(tool_module, "get_incubation_repository", Mock(return_value=repository))
    monkeypatch.setattr(tool_module, "create_content_intelligence_model", Mock(return_value=object()))
    monkeypatch.setattr(tool_module, "prepare_account_audience", prepare_audience, raising=False)
    monkeypatch.setattr(tool_module, "analyze_content_intelligence", analysis)
    monkeypatch.setattr(tool_module, "collect_public_douyin_benchmark", collect)
    monkeypatch.setattr(tool_module, "prepare_account_strategy", prepare_strategy)

    result = await develop_account_strategy_tool.ainvoke(
        {
            "name": "develop_account_strategy",
            "args": {
                "user_request": "我是做水果生意的，我要怎么起号",
                "subject_ref": "user_business",
                "runtime": _runtime(project_id="fruit-business"),
            },
            "id": "account-strategy-call",
            "type": "tool_call",
        }
    )

    message = result.update["messages"][0]
    assert "先确认账号要影响谁" in message.content
    assert "b2b_wholesale" in message.content
    assert "b2c_retail" in message.content
    assert message.additional_kwargs["incubation_persistence"]["artifact_type"] == "account_audience_decision"
    analysis.assert_not_awaited()
    collect.assert_not_awaited()
    prepare_strategy.assert_not_awaited()


@pytest.mark.asyncio
async def test_agent_self_binding_uses_host_product_truth_instead_of_user_business_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    term_resolver_factory = Mock()
    repository = SimpleNamespace(
        get_project=AsyncMock(return_value=object()),
        get_logical_account=AsyncMock(return_value=object()),
        put_artifact=AsyncMock(side_effect=lambda artifact: artifact),
    )
    captured: dict[str, object] = {}

    async def prepare_audience(**kwargs):
        captured["subject"] = kwargs["subject"]
        captured["subject_parents"] = kwargs["subject_parent_artifacts"]
        return _prepared_resolved_audience(
            kwargs["subject"],
            route=_audience_route(
                "business_operators",
                target_people="不知道账号应该影响谁和长期讲什么的经营者",
                content_audience="关心账号定位、选题和真实操盘过程的经营者",
            ),
        )

    bundle = SimpleNamespace(
        content_world=SimpleNamespace(
            content_root="人们如何把业务转成可持续的内容账号",
            source_object="DeerFlow 内容孵化与新媒体运营 Agent",
        )
    )
    artifact = SimpleNamespace(
        artifact_type="incubation_judgment",
        artifact_id="artifact-agent-self-strategy",
        content_sha256="7" * 64,
    )
    analysis = AsyncMock(return_value=bundle)
    prepare_strategy = AsyncMock(
        return_value=SimpleNamespace(
            judgment=object(),
            judgment_artifact=artifact,
            reused=False,
        )
    )
    monkeypatch.setattr(tool_module, "get_incubation_repository", Mock(return_value=repository))
    monkeypatch.setattr(tool_module, "create_content_intelligence_model", Mock(return_value=object()))
    monkeypatch.setattr(tool_module, "create_lexical_evidence_provider", Mock(return_value=None))
    monkeypatch.setattr(tool_module, "create_term_resolver", term_resolver_factory)
    monkeypatch.setattr(tool_module, "prepare_account_audience", AsyncMock(side_effect=prepare_audience), raising=False)
    monkeypatch.setattr(tool_module, "analyze_content_intelligence", analysis)
    monkeypatch.setattr(tool_module, "collect_public_douyin_benchmark", AsyncMock(return_value=None))
    monkeypatch.setattr(tool_module, "prepare_account_strategy", prepare_strategy)
    monkeypatch.setattr(tool_module, "render_account_strategy", Mock(return_value="# Agent 自营账号路线"))

    await develop_account_strategy_tool.ainvoke(
        {
            "name": "develop_account_strategy",
            "args": {
                "user_request": "你以自己的第一人称去卖，自己起号做账号",
                "subject_ref": "agent_self",
                "runtime": _runtime(project_id="agent-self"),
            },
            "id": "account-strategy-call",
            "type": "tool_call",
        }
    )

    subject = captured["subject"]
    assert subject.subject_kind == "agent_self"
    assert subject.subject_expression == "DeerFlow 内容孵化与新媒体运营 Agent"
    assert "普通人" not in subject.model_dump_json()
    profile_artifact = captured["subject_parents"][0]
    assert profile_artifact.artifact_type == "host_product_profile"
    request = analysis.await_args.args[0]
    assert request.subject_expression == subject.subject_expression
    assert request.user_request == subject.subject_expression
    assert request.audience_context.target_people.startswith("不知道账号应该影响谁")
    assert prepare_strategy.await_args.kwargs["marketing_subject"] == subject
    assert prepare_strategy.await_args.kwargs["subject_parent_artifacts"] == (profile_artifact,)
    term_resolver_factory.assert_not_called()


@pytest.mark.asyncio
async def test_account_strategy_collects_and_stores_public_benchmark_after_root_freezes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stored_evidence = SimpleNamespace(artifact_id="benchmark-evidence-1")
    repository = SimpleNamespace(
        get_project=AsyncMock(return_value=object()),
        get_logical_account=AsyncMock(return_value=object()),
        put_artifact=AsyncMock(return_value=stored_evidence),
    )
    bundle = SimpleNamespace(content_world=SimpleNamespace(content_root="人们如何用礼组织人与人的相处"))
    snapshot = object()
    sealed = object()
    artifact = SimpleNamespace(
        artifact_type="incubation_judgment",
        artifact_id="artifact-strategy-with-evidence",
        content_sha256="e" * 64,
    )
    prepared = SimpleNamespace(
        judgment=object(),
        judgment_artifact=artifact,
        reused=False,
    )
    monkeypatch.setattr(tool_module, "get_incubation_repository", Mock(return_value=repository))
    monkeypatch.setattr(tool_module, "create_content_intelligence_model", Mock(return_value=object()))
    monkeypatch.setattr(tool_module, "create_lexical_evidence_provider", Mock(return_value=None))
    monkeypatch.setattr(tool_module, "analyze_content_intelligence", AsyncMock(return_value=bundle))
    collect = AsyncMock(return_value=snapshot)
    monkeypatch.setattr(tool_module, "collect_public_douyin_benchmark", collect, raising=False)
    seal = Mock(return_value=sealed)
    monkeypatch.setattr(tool_module, "seal_benchmark_snapshot", seal, raising=False)
    prepare = AsyncMock(return_value=prepared)
    monkeypatch.setattr(tool_module, "prepare_account_strategy", prepare)
    monkeypatch.setattr(tool_module, "render_account_strategy", Mock(return_value="# 账号路线候选"))

    await develop_account_strategy_tool.ainvoke(
        {
            "name": "develop_account_strategy",
            "args": {
                "user_request": "我是做黄金礼品的，我要怎么起号？",
                "subject_ref": "user_business",
                "runtime": _runtime(project_id="golden-gift"),
            },
            "id": "account-strategy-call",
            "type": "tool_call",
        }
    )

    collect.assert_awaited_once()
    assert collect.await_args.kwargs["query"] == ("人们如何用礼组织人与人的相处 会持续关心该业务所在内容世界的人")
    seal.assert_called_once_with(
        project=implicit_thread_project_ref(
            owner_user_id="user-1",
            thread_id="thread-1",
        ).model_copy(update={"project_id": "golden-gift"}),
        snapshot=snapshot,
        source_thread_id="thread-1",
        source_run_id="run-1",
        logical_account=implicit_thread_logical_account_ref(
            project=implicit_thread_project_ref(
                owner_user_id="user-1",
                thread_id="thread-1",
            ).model_copy(update={"project_id": "golden-gift"}),
            thread_id="thread-1",
        ),
    )
    repository.put_artifact.assert_awaited_once_with(sealed)
    prepare.assert_awaited_once()


@pytest.mark.asyncio
async def test_account_strategy_confirmation_does_not_require_a_platform_account(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = SimpleNamespace(
        get_project=AsyncMock(return_value=object()),
        get_logical_account=AsyncMock(return_value=object()),
    )
    judgment = object()
    artifact = SimpleNamespace(
        artifact_type="incubation_judgment",
        artifact_id="artifact-strategy-2",
        content_sha256="b" * 64,
    )
    confirmed = SimpleNamespace(
        judgment=judgment,
        judgment_artifact=artifact,
        reused=False,
    )
    monkeypatch.setattr(tool_module, "get_incubation_repository", Mock(return_value=repository))
    confirm = AsyncMock(return_value=confirmed)
    monkeypatch.setattr(tool_module, "confirm_account_strategy", confirm)
    monkeypatch.setattr(tool_module, "render_account_strategy", Mock(return_value="# 已确认的账号路线"))

    result = await confirm_account_strategy_tool.ainvoke(
        {
            "name": "confirm_account_strategy",
            "args": {
                "option_id": "route_b",
                "runtime": _runtime(project_id="golden-gift"),
            },
            "id": "account-strategy-call",
            "type": "tool_call",
        }
    )

    assert confirm.await_args.kwargs["option_id"] == "route_b"
    assert "account" not in confirm.await_args.kwargs
    assert "logical_account" in confirm.await_args.kwargs
    message = result.update["messages"][0]
    assert message.name == "confirm_account_strategy"
    assert "已经由你确认" in message.content


@pytest.mark.asyncio
async def test_account_strategy_confirmation_reuses_the_implicit_thread_project(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = SimpleNamespace(
        get_project=AsyncMock(return_value=object()),
        get_logical_account=AsyncMock(return_value=object()),
    )
    artifact = SimpleNamespace(
        artifact_type="incubation_judgment",
        artifact_id="artifact-strategy-implicit-confirmed",
        content_sha256="d" * 64,
    )
    confirmed = SimpleNamespace(
        judgment=object(),
        judgment_artifact=artifact,
        reused=False,
    )
    monkeypatch.setattr(tool_module, "get_incubation_repository", Mock(return_value=repository))
    confirm = AsyncMock(return_value=confirmed)
    monkeypatch.setattr(tool_module, "confirm_account_strategy", confirm)
    monkeypatch.setattr(tool_module, "render_account_strategy", Mock(return_value="# 已确认的账号路线"))

    result = await confirm_account_strategy_tool.ainvoke(
        {
            "name": "confirm_account_strategy",
            "args": {
                "option_id": "route_a",
                "runtime": _runtime(project_id=None),
            },
            "id": "account-strategy-call",
            "type": "tool_call",
        }
    )

    expected_project = implicit_thread_project_ref(owner_user_id="user-1", thread_id="thread-1")
    repository.get_project.assert_awaited_once_with(expected_project)
    assert confirm.await_args.kwargs["project"] == expected_project
    assert confirm.await_args.kwargs["logical_account"] == implicit_thread_logical_account_ref(
        project=expected_project,
        thread_id="thread-1",
    )
    message = result.update["messages"][0]
    assert message.additional_kwargs["incubation_persistence"]["project_id"] == expected_project.project_id
