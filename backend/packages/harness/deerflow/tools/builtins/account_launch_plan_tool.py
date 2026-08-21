from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from langchain_core.messages import ToolMessage
from langchain_core.tools import tool
from langgraph.types import Command

from deerflow.incubation import (
    LogicalAccountRef,
    ProjectRef,
    implicit_thread_logical_account_ref,
    implicit_thread_project_ref,
)
from deerflow.incubation.account_launch_plan import (
    confirm_account_launch_plan,
    prepare_account_launch_plan,
)
from deerflow.incubation.account_launch_plan_presentation import render_account_launch_plan
from deerflow.incubation.launch_plan_runtime import AccountLaunchPlanModelError
from deerflow.tools.builtins.incubation_tool_support import (
    create_content_intelligence_model,
    get_incubation_repository,
    runtime_context_text,
    structured_model_runner,
)
from deerflow.tools.types import Runtime

logger = logging.getLogger(__name__)


def _terminal_launch_plan_command(
    content: str,
    *,
    tool_call_id: str,
    tool_name: str,
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


def _runtime_scope(
    runtime: Runtime,
) -> tuple[ProjectRef, LogicalAccountRef, str, str] | None:
    owner_user_id = runtime_context_text(runtime, "user_id")
    thread_id = runtime_context_text(runtime, "thread_id")
    run_id = runtime_context_text(runtime, "run_id")
    if owner_user_id is None or thread_id is None or run_id is None:
        return None
    project_id = runtime_context_text(runtime, "incubation_project_id")
    if project_id is None:
        project = implicit_thread_project_ref(
            owner_user_id=owner_user_id,
            thread_id=thread_id,
        )
    else:
        project = ProjectRef(
            owner_user_id=owner_user_id,
            project_id=project_id,
        )
    logical_account_id = runtime_context_text(
        runtime,
        "incubation_logical_account_id",
    )
    if logical_account_id is None:
        logical_account = implicit_thread_logical_account_ref(
            project=project,
            thread_id=thread_id,
        )
    else:
        logical_account = LogicalAccountRef(
            owner_user_id=owner_user_id,
            project_id=project.project_id,
            logical_account_id=logical_account_id,
        )
    return project, logical_account, thread_id, run_id


async def _scope_is_available(
    repository: Any,
    *,
    project: ProjectRef,
    logical_account: LogicalAccountRef,
) -> bool:
    return await repository.get_project(project) is not None and await repository.get_logical_account(logical_account) is not None


def _persistence_receipt(
    *,
    project: ProjectRef,
    logical_account: LogicalAccountRef,
    prepared: Any,
) -> dict[str, Any]:
    artifact = prepared.plan_artifact
    return {
        "status": "reused" if prepared.reused else "stored",
        "project_id": project.project_id,
        "logical_account_id": logical_account.logical_account_id,
        "artifact_type": artifact.artifact_type,
        "artifact_id": artifact.artifact_id,
        "content_sha256": artifact.content_sha256,
    }


@tool("plan_account_launch", parse_docstring=True, return_direct=True)
async def plan_account_launch_tool(
    runtime: Runtime,
    planning_request: str,
) -> Command:
    """Create or revise an optional 7-day and 30-day plan for the current logical account.

    The tool requires an already confirmed account strategy. It arranges
    series, research leads, actions and review questions without changing
    positioning or claiming platform guarantees. It does not publish content.

    Args:
        planning_request: The user's current request for an account launch plan, copied verbatim.
    """

    scope = _runtime_scope(runtime)
    if scope is None:
        return _terminal_launch_plan_command(
            "当前对话缺少可验证的账号身份，因此没有生成起号计划。",
            tool_call_id=runtime.tool_call_id,
            tool_name="plan_account_launch",
        )
    project, logical_account, thread_id, run_id = scope
    repository = get_incubation_repository()
    try:
        available = repository is not None and await _scope_is_available(
            repository,
            project=project,
            logical_account=logical_account,
        )
    except Exception as exc:
        logger.warning("Account launch-plan scope lookup failed: %s", type(exc).__name__)
        available = False
    if not available or repository is None:
        return _terminal_launch_plan_command(
            "当前逻辑账号不可用，因此没有生成无法延续的临时计划。",
            tool_call_id=runtime.tool_call_id,
            tool_name="plan_account_launch",
        )

    try:
        model = create_content_intelligence_model(runtime.config)
        prepared = await prepare_account_launch_plan(
            project=project,
            logical_account=logical_account,
            repository=repository,
            planning_request=planning_request,
            structured_model=structured_model_runner(model, runtime.config),
            created_at=datetime.now(UTC),
            source_thread_id=thread_id,
            source_run_id=run_id,
        )
    except AccountLaunchPlanModelError as exc:
        logger.warning(
            "Account launch-plan generation failed at %s: %s",
            exc.stage,
            ",".join(exc.diagnostics),
        )
        return _terminal_launch_plan_command(
            "起号计划暂时没有通过结构校验，已确认的账号定位和内容地图保持不变。",
            tool_call_id=runtime.tool_call_id,
            tool_name="plan_account_launch",
        )
    except ValueError as exc:
        logger.warning("Account launch-plan request was rejected: %s", type(exc).__name__)
        return _terminal_launch_plan_command(
            "当前账号还没有已确认的路线，先选择并确认账号定位，再编排 7 天与 30 天计划。",
            tool_call_id=runtime.tool_call_id,
            tool_name="plan_account_launch",
        )
    except Exception as exc:
        logger.warning("Account launch-plan generation was unavailable: %s", type(exc).__name__)
        return _terminal_launch_plan_command(
            "起号计划暂时不可用，已有账号资产没有被改写。",
            tool_call_id=runtime.tool_call_id,
            tool_name="plan_account_launch",
        )

    return _terminal_launch_plan_command(
        render_account_launch_plan(prepared.plan),
        tool_call_id=runtime.tool_call_id,
        tool_name="plan_account_launch",
        persistence=_persistence_receipt(
            project=project,
            logical_account=logical_account,
            prepared=prepared,
        ),
    )


@tool("confirm_account_launch_plan", parse_docstring=True, return_direct=True)
async def confirm_account_launch_plan_tool(runtime: Runtime) -> Command:
    """Confirm the current logical account's latest proposed launch plan."""

    scope = _runtime_scope(runtime)
    if scope is None:
        return _terminal_launch_plan_command(
            "当前对话缺少可验证的账号身份，因此没有确认起号计划。",
            tool_call_id=runtime.tool_call_id,
            tool_name="confirm_account_launch_plan",
        )
    project, logical_account, thread_id, run_id = scope
    repository = get_incubation_repository()
    try:
        available = repository is not None and await _scope_is_available(
            repository,
            project=project,
            logical_account=logical_account,
        )
    except Exception as exc:
        logger.warning("Account launch-plan confirmation scope failed: %s", type(exc).__name__)
        available = False
    if not available or repository is None:
        return _terminal_launch_plan_command(
            "当前逻辑账号不可用，因此没有确认起号计划。",
            tool_call_id=runtime.tool_call_id,
            tool_name="confirm_account_launch_plan",
        )

    try:
        prepared = await confirm_account_launch_plan(
            project=project,
            logical_account=logical_account,
            repository=repository,
            created_at=datetime.now(UTC),
            source_thread_id=thread_id,
            source_run_id=run_id,
        )
    except ValueError:
        return _terminal_launch_plan_command(
            "当前账号没有可确认的起号计划，请先生成或修订计划。",
            tool_call_id=runtime.tool_call_id,
            tool_name="confirm_account_launch_plan",
        )
    except Exception as exc:
        logger.warning("Account launch-plan confirmation failed: %s", type(exc).__name__)
        return _terminal_launch_plan_command(
            "这次计划确认暂时未能封存，原计划保持不变。",
            tool_call_id=runtime.tool_call_id,
            tool_name="confirm_account_launch_plan",
        )

    return _terminal_launch_plan_command(
        render_account_launch_plan(prepared.plan),
        tool_call_id=runtime.tool_call_id,
        tool_name="confirm_account_launch_plan",
        persistence=_persistence_receipt(
            project=project,
            logical_account=logical_account,
            prepared=prepared,
        ),
    )


__all__ = ["confirm_account_launch_plan_tool", "plan_account_launch_tool"]
