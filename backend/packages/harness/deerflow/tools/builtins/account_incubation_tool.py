from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from langchain_core.messages import ToolMessage
from langchain_core.tools import tool
from langgraph.types import Command
from pydantic import ValidationError

from deerflow.content_intelligence import (
    AnalysisFocus,
    ContentIntelligenceRequest,
    analyze_content_intelligence,
)
from deerflow.incubation import ProjectRef, confirm_account_strategy, prepare_account_strategy
from deerflow.incubation.account_strategy_presentation import render_account_strategy
from deerflow.tools.builtins.incubation_tool_support import (
    create_content_intelligence_model,
    create_lexical_evidence_provider,
    get_incubation_repository,
    runtime_context_text,
    structured_model_runner,
)
from deerflow.tools.types import Runtime

logger = logging.getLogger(__name__)


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
) -> Command:
    """Create or revise the selected project's long-lived account incubation strategy.

    This is the only high-level tool that decides positioning, audience,
    persona, account-level presentation, and monetization hypotheses. It uses a
    candidate content map plus separately stored benchmark and audience
    evidence. It does not create a daily topic, script, production plan, or
    publication.

    Args:
        user_request: The user's current account-starting or positioning request, copied verbatim.
    """

    project_id = runtime_context_text(runtime, "incubation_project_id")
    owner_user_id = runtime_context_text(runtime, "user_id")
    thread_id = runtime_context_text(runtime, "thread_id")
    run_id = runtime_context_text(runtime, "run_id")
    if project_id is None or owner_user_id is None or thread_id is None or run_id is None:
        return _terminal_account_strategy_command(
            "要生成可持续复盘和修订的账号定位，需要先创建或选择一个项目。当前没有把一次内容地图冒充成账号定位。",
            tool_call_id=runtime.tool_call_id,
        )

    project = ProjectRef(owner_user_id=owner_user_id, project_id=project_id)
    repository = get_incubation_repository()
    if repository is None or await repository.get_project(project) is None:
        return _terminal_account_strategy_command(
            "当前选择的孵化项目不可用，因此没有生成临时定位。",
            tool_call_id=runtime.tool_call_id,
        )

    try:
        model = create_content_intelligence_model(runtime.config)
        bundle = await analyze_content_intelligence(
            ContentIntelligenceRequest(
                user_request=user_request,
                subject_expression=user_request,
                focus=AnalysisFocus.CONTENT_WORLD,
                source_materials=(),
            ),
            model=model,
            runnable_config=runtime.config,
            lexical_evidence_provider=create_lexical_evidence_provider(),
        )
        strategy = await prepare_account_strategy(
            project=project,
            repository=repository,
            bundle=bundle,
            verbatim_user_request=user_request,
            structured_model=structured_model_runner(model, runtime.config),
            created_at=datetime.now(UTC),
            source_thread_id=thread_id,
            source_run_id=run_id,
        )
    except (ValidationError, ValueError) as exc:
        logger.warning("Account strategy generation failed contract validation: %s", type(exc).__name__)
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
            "project_id": project_id,
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
    """Confirm one route from the selected project's latest account proposal.

    This records the user's choice and projects that exact route into the
    versioned account strategy. It does not require a platform account login,
    and it does not create a topic, script, production plan, or publication.

    Args:
        option_id: The exact route identifier the user selected from the latest proposal.
    """

    project_id = runtime_context_text(runtime, "incubation_project_id")
    owner_user_id = runtime_context_text(runtime, "user_id")
    thread_id = runtime_context_text(runtime, "thread_id")
    run_id = runtime_context_text(runtime, "run_id")
    if project_id is None or owner_user_id is None or thread_id is None or run_id is None:
        return _terminal_account_strategy_command(
            "当前没有可用的孵化项目，因此没有记录这次路线选择。",
            tool_call_id=runtime.tool_call_id,
            tool_name="confirm_account_strategy",
        )

    project = ProjectRef(owner_user_id=owner_user_id, project_id=project_id)
    repository = get_incubation_repository()
    if repository is None or await repository.get_project(project) is None:
        return _terminal_account_strategy_command(
            "当前选择的孵化项目不可用，因此没有记录这次路线选择。",
            tool_call_id=runtime.tool_call_id,
            tool_name="confirm_account_strategy",
        )

    try:
        confirmed = await confirm_account_strategy(
            project=project,
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
            "project_id": project_id,
            "artifact_type": artifact.artifact_type,
            "artifact_id": artifact.artifact_id,
            "content_sha256": artifact.content_sha256,
        },
    )


__all__ = ["confirm_account_strategy_tool", "develop_account_strategy_tool"]
