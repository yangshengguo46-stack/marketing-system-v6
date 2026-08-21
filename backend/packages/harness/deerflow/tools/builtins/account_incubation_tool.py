from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any, Literal

from langchain_core.messages import ToolMessage
from langchain_core.tools import tool
from langgraph.types import Command
from pydantic import ValidationError

from deerflow.content_intelligence import (
    AnalysisFocus,
    ContentAudienceContext,
    ContentIntelligenceRequest,
    IncubationSkillProfileError,
    analyze_content_intelligence,
    load_incubation_skill_profile,
)
from deerflow.incubation import (
    IncubationJudgmentModelError,
    LogicalAccountRef,
    ProjectRef,
    confirm_account_strategy,
    implicit_project_display_name,
    implicit_thread_logical_account_ref,
    implicit_thread_project_ref,
    prepare_account_strategy,
    seal_benchmark_snapshot,
)
from deerflow.incubation.account_audience import (
    MarketingSubjectSnapshot,
    prepare_account_audience,
    render_account_audience_decision,
)
from deerflow.incubation.account_strategy_presentation import render_account_strategy
from deerflow.incubation.host_product_profile import (
    build_agent_self_subject,
    current_host_product_profile,
    seal_host_product_profile,
)
from deerflow.tools.builtins.douyin_public_benchmark_evidence import (
    collect_public_douyin_benchmark,
)
from deerflow.tools.builtins.incubation_tool_support import (
    create_content_intelligence_model,
    create_lexical_evidence_provider,
    get_incubation_repository,
    runtime_context_text,
    structured_model_runner,
)
from deerflow.tools.types import Runtime

logger = logging.getLogger(__name__)


def _safe_validation_diagnostics(error: ValidationError) -> tuple[str, ...]:
    """Expose bounded schema locations without logging model or user values."""

    diagnostics: list[str] = []
    for item in error.errors(include_url=False, include_context=False, include_input=False)[:8]:
        location = ".".join(str(part) for part in item.get("loc", ())) or "root"
        diagnostics.append(f"{location}:{item.get('type', 'validation_error')}")
    return tuple(diagnostics) or ("root:validation_error",)


def _terminal_account_strategy_command(
    content: str,
    *,
    tool_call_id: str,
    tool_name: str = "develop_account_strategy",
    persistence: dict[str, Any] | None = None,
) -> Command:
    additional_kwargs: dict[str, Any] = {
        "hide_from_ui": True,
        "deerflow_direct_response": True,
    }
    if persistence is not None:
        additional_kwargs["incubation_persistence"] = persistence
    return Command(
        update={
            "messages": [
                ToolMessage(
                    id=f"{tool_call_id}:result",
                    content=content,
                    tool_call_id=tool_call_id,
                    name=tool_name,
                    additional_kwargs=additional_kwargs,
                )
            ]
        }
    )


@tool("develop_account_strategy", parse_docstring=True, return_direct=True)
async def develop_account_strategy_tool(
    runtime: Runtime,
    user_request: str,
    subject_ref: Literal["user_business", "agent_self"],
    audience_option_id: str | None = None,
    incubation_skill: str | None = None,
) -> Command:
    """Create or revise the current thread project's long-lived account incubation strategy.

    This high-level tool first resolves the cold-start business/content
    audience, then proposes positioning, persona, account-level presentation,
    and monetization hypotheses. It uses a candidate content map plus separately
    stored benchmark and observed-audience evidence. It does not create a daily
    topic, script, production plan, or publication.

    Args:
        user_request: The user's current account-starting or positioning request, copied verbatim.
        subject_ref: Whether the account belongs to the user's business or to the current Agent product itself.
        audience_option_id: Exact pending audience route selected by the user, when the prior response requested a choice.
        incubation_skill: Exact name of one already discovered and loaded vertical incubation Skill, when applicable.
    """

    owner_user_id = runtime_context_text(runtime, "user_id")
    thread_id = runtime_context_text(runtime, "thread_id")
    run_id = runtime_context_text(runtime, "run_id")
    if owner_user_id is None or thread_id is None or run_id is None:
        return _terminal_account_strategy_command(
            "当前对话缺少可验证的用户或运行身份，因此没有生成账号定位。",
            tool_call_id=runtime.tool_call_id,
        )

    project_id = runtime_context_text(runtime, "incubation_project_id")
    if project_id is not None:
        project = ProjectRef(owner_user_id=owner_user_id, project_id=project_id)
    else:
        project = implicit_thread_project_ref(owner_user_id=owner_user_id, thread_id=thread_id)
    logical_account_id = runtime_context_text(
        runtime,
        "incubation_logical_account_id",
    )
    if logical_account_id is not None:
        logical_account = LogicalAccountRef(
            owner_user_id=owner_user_id,
            project_id=project.project_id,
            logical_account_id=logical_account_id,
        )
    else:
        logical_account = implicit_thread_logical_account_ref(
            project=project,
            thread_id=thread_id,
        )
    repository = get_incubation_repository()
    if repository is None:
        return _terminal_account_strategy_command(
            "账号孵化台账暂时不可用，因此没有生成无法延续的临时定位。",
            tool_call_id=runtime.tool_call_id,
        )
    try:
        project_record = await repository.get_project(project)
        if project_record is None and project_id is not None:
            return _terminal_account_strategy_command(
                "当前选择的孵化项目不可用，因此没有生成临时定位。",
                tool_call_id=runtime.tool_call_id,
            )
        if project_record is None:
            try:
                await repository.create_project(
                    project,
                    display_name=implicit_project_display_name(user_request),
                )
            except Exception:
                # A concurrent first request may have created the deterministic project.
                if await repository.get_project(project) is None:
                    raise
        logical_account_record = await repository.get_logical_account(logical_account)
        if logical_account_record is None:
            try:
                await repository.create_logical_account(
                    logical_account,
                    display_name=implicit_project_display_name(user_request),
                )
            except Exception:
                if await repository.get_logical_account(logical_account) is None:
                    raise
    except Exception as exc:
        logger.warning("Account strategy project bootstrap was unavailable: %s", type(exc).__name__)
        return _terminal_account_strategy_command(
            "账号孵化台账暂时不可用，因此没有生成无法延续的临时定位。",
            tool_call_id=runtime.tool_call_id,
        )

    try:
        model = create_content_intelligence_model(runtime.config)
        created_at = datetime.now(UTC)
        subject: MarketingSubjectSnapshot | None = None
        subject_parent_artifacts = ()
        if audience_option_id is None:
            if subject_ref == "agent_self":
                profile_artifact = seal_host_product_profile(
                    project=project,
                    logical_account=logical_account,
                    profile=current_host_product_profile(),
                    created_at=created_at,
                    source_thread_id=thread_id,
                    source_run_id=run_id,
                )
                profile_artifact = await repository.put_artifact(profile_artifact)
                subject_parent_artifacts = (profile_artifact,)
                subject = build_agent_self_subject(
                    user_request=user_request,
                    profile_artifact=profile_artifact,
                )
            else:
                subject = MarketingSubjectSnapshot(
                    subject_kind="user_business",
                    subject_expression=user_request,
                    source_user_request=user_request,
                    business_facts=(user_request,),
                )

        audience = await prepare_account_audience(
            project=project,
            logical_account=logical_account,
            repository=repository,
            subject=subject,
            structured_model=structured_model_runner(model, runtime.config),
            option_id=audience_option_id,
            expected_subject_kind=subject_ref,
            subject_parent_artifacts=subject_parent_artifacts,
            created_at=created_at,
            source_thread_id=thread_id,
            source_run_id=run_id,
        )
        if audience.decision.subject.subject_kind != subject_ref:
            raise ValueError("the selected audience route belongs to a different marketing subject")
        if audience.decision.decision_status == "proposed":
            artifact = audience.decision_artifact
            return _terminal_account_strategy_command(
                render_account_audience_decision(audience.decision),
                tool_call_id=runtime.tool_call_id,
                persistence={
                    "status": "reused" if audience.reused else "stored",
                    "project_id": project.project_id,
                    "logical_account_id": logical_account.logical_account_id,
                    "artifact_type": artifact.artifact_type,
                    "artifact_id": artifact.artifact_id,
                    "content_sha256": artifact.content_sha256,
                },
            )

        subject = audience.decision.subject
        selected_audience = audience.decision.selected_route()
        if selected_audience is None:
            raise ValueError("resolved account audience has no selected route")
        if subject.subject_kind == "agent_self" and not subject_parent_artifacts:
            artifacts = await repository.list_artifacts(
                project,
                logical_account=logical_account,
            )
            by_id = {artifact.artifact_id: artifact for artifact in artifacts}
            try:
                subject_parent_artifacts = tuple(by_id[artifact_id] for artifact_id in subject.basis_artifact_ids)
            except KeyError as exc:
                raise ValueError("host product profile is unavailable") from exc

        incubation_profile = None
        if incubation_skill is not None:
            try:
                incubation_profile = load_incubation_skill_profile(
                    incubation_skill,
                    user_id=owner_user_id,
                )
            except IncubationSkillProfileError as exc:
                logger.warning(
                    "Selected incubation skill profile was unavailable: %s",
                    type(exc).__name__,
                )
                return _terminal_account_strategy_command(
                    "当前选中的行业孵化 Skill 不可用，因此没有用一份未校验的行业经验生成定位。",
                    tool_call_id=runtime.tool_call_id,
                )

        audience_context = ContentAudienceContext(
            business_role=selected_audience.business_role,
            payer_or_contracting_party=selected_audience.payer_or_contracting_party,
            decision_makers=selected_audience.decision_makers,
            users_or_beneficiaries=selected_audience.users_or_beneficiaries,
            target_people=selected_audience.target_people,
            target_need=selected_audience.target_need,
            desired_action=selected_audience.desired_action,
            market_scope=selected_audience.market_scope,
            content_audience=selected_audience.content_audience,
            recurring_interest=selected_audience.recurring_interest,
        )
        bundle = await analyze_content_intelligence(
            ContentIntelligenceRequest(
                user_request=subject.subject_expression,
                subject_expression=subject.subject_expression,
                focus=AnalysisFocus.CONTENT_WORLD,
                source_materials=(),
                audience_context=audience_context,
            ),
            model=model,
            runnable_config=runtime.config,
            lexical_evidence_provider=create_lexical_evidence_provider(),
            incubation_profile=incubation_profile,
        )
        content_world = getattr(bundle, "content_world", None)
        content_root = getattr(content_world, "content_root", None)
        if isinstance(content_root, str) and content_root.strip():
            try:
                benchmark = await collect_public_douyin_benchmark(
                    runtime,
                    query=f"{content_root.strip()} {selected_audience.content_audience}"[:240],
                    max_posts=6,
                )
                if benchmark is not None:
                    await repository.put_artifact(
                        seal_benchmark_snapshot(
                            project=project,
                            snapshot=benchmark,
                            source_thread_id=thread_id,
                            source_run_id=run_id,
                            logical_account=logical_account,
                        )
                    )
            except Exception as exc:
                logger.warning(
                    "Account strategy benchmark evidence was unavailable: %s",
                    type(exc).__name__,
                )
        strategy = await prepare_account_strategy(
            project=project,
            logical_account=logical_account,
            repository=repository,
            bundle=bundle,
            verbatim_user_request=subject.source_user_request,
            marketing_subject=subject,
            subject_parent_artifacts=subject_parent_artifacts,
            audience_decision_artifact=audience.decision_artifact,
            structured_model=structured_model_runner(model, runtime.config),
            created_at=created_at,
            source_thread_id=thread_id,
            source_run_id=run_id,
        )
    except IncubationJudgmentModelError as exc:
        logger.warning(
            "Account strategy generation failed at %s: %s",
            exc.stage,
            ",".join(exc.diagnostics),
        )
        return _terminal_account_strategy_command(
            "账号孵化判断暂时不可用，已有项目事实、候选地图和对标证据都没有被改写。",
            tool_call_id=runtime.tool_call_id,
        )
    except (ValidationError, ValueError) as exc:
        diagnostics = _safe_validation_diagnostics(exc) if isinstance(exc, ValidationError) else (type(exc).__name__,)
        logger.warning(
            "Account strategy generation failed contract validation: %s",
            ",".join(diagnostics),
        )
        return _terminal_account_strategy_command(
            "这次账号孵化判断没有通过结构校验，因此没有用候选地图或对标观察替你补出定位。",
            tool_call_id=runtime.tool_call_id,
        )
    except Exception as exc:
        logger.warning("Account strategy generation was unavailable: %s", type(exc).__name__)
        return _terminal_account_strategy_command(
            "账号孵化判断暂时不可用，已有项目事实、候选地图和对标证据都没有被改写。",
            tool_call_id=runtime.tool_call_id,
        )

    artifact = strategy.judgment_artifact
    return _terminal_account_strategy_command(
        render_account_strategy(strategy.judgment),
        tool_call_id=runtime.tool_call_id,
        persistence={
            "status": "reused" if strategy.reused else "stored",
            "project_id": project.project_id,
            "logical_account_id": logical_account.logical_account_id,
            "artifact_type": artifact.artifact_type,
            "artifact_id": artifact.artifact_id,
            "content_sha256": artifact.content_sha256,
        },
    )


@tool("confirm_account_strategy", parse_docstring=True, return_direct=True)
async def confirm_account_strategy_tool(
    runtime: Runtime,
    option_id: str,
) -> Command:
    """Confirm one route from the current thread project's latest account proposal.

    This records the user's choice and projects that exact route into the
    versioned account strategy. It does not require a platform account login,
    and it does not create a topic, script, production plan, or publication.

    Args:
        option_id: The exact route identifier the user selected from the latest proposal.
    """

    owner_user_id = runtime_context_text(runtime, "user_id")
    thread_id = runtime_context_text(runtime, "thread_id")
    run_id = runtime_context_text(runtime, "run_id")
    if owner_user_id is None or thread_id is None or run_id is None:
        return _terminal_account_strategy_command(
            "当前对话缺少可验证的用户或运行身份，因此没有记录这次路线选择。",
            tool_call_id=runtime.tool_call_id,
            tool_name="confirm_account_strategy",
        )

    project_id = runtime_context_text(runtime, "incubation_project_id")
    if project_id is not None:
        project = ProjectRef(owner_user_id=owner_user_id, project_id=project_id)
    else:
        project = implicit_thread_project_ref(owner_user_id=owner_user_id, thread_id=thread_id)
    logical_account_id = runtime_context_text(
        runtime,
        "incubation_logical_account_id",
    )
    if logical_account_id is not None:
        logical_account = LogicalAccountRef(
            owner_user_id=owner_user_id,
            project_id=project.project_id,
            logical_account_id=logical_account_id,
        )
    else:
        logical_account = implicit_thread_logical_account_ref(
            project=project,
            thread_id=thread_id,
        )
    repository = get_incubation_repository()
    if repository is None or await repository.get_project(project) is None or await repository.get_logical_account(logical_account) is None:
        return _terminal_account_strategy_command(
            "当前选择的孵化项目不可用，因此没有记录这次路线选择。",
            tool_call_id=runtime.tool_call_id,
            tool_name="confirm_account_strategy",
        )

    try:
        confirmed = await confirm_account_strategy(
            project=project,
            logical_account=logical_account,
            repository=repository,
            option_id=option_id,
            created_at=datetime.now(UTC),
            source_thread_id=thread_id,
            source_run_id=run_id,
        )
    except ValueError as exc:
        logger.warning("Account strategy confirmation was rejected: %s", str(exc))
        return _terminal_account_strategy_command(
            "这个路线编号不属于当前待确认提案，因此没有替你选择。请从最新候选中重新选一条。",
            tool_call_id=runtime.tool_call_id,
            tool_name="confirm_account_strategy",
        )
    except Exception as exc:
        logger.warning("Account strategy confirmation was unavailable: %s", type(exc).__name__)
        return _terminal_account_strategy_command(
            "这次账号路线确认暂时未能封存，原提案保持不变。",
            tool_call_id=runtime.tool_call_id,
            tool_name="confirm_account_strategy",
        )

    artifact = confirmed.judgment_artifact
    return _terminal_account_strategy_command(
        render_account_strategy(confirmed.judgment) + "\n\n这条路线已经由你确认。接下来可以沿它生成第一条具体可拍选题。",
        tool_call_id=runtime.tool_call_id,
        tool_name="confirm_account_strategy",
        persistence={
            "status": "reused" if confirmed.reused else "stored",
            "project_id": project.project_id,
            "logical_account_id": logical_account.logical_account_id,
            "artifact_type": artifact.artifact_type,
            "artifact_id": artifact.artifact_id,
            "content_sha256": artifact.content_sha256,
        },
    )


__all__ = ["confirm_account_strategy_tool", "develop_account_strategy_tool"]
