from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from langchain_core.messages import ToolMessage
from langchain_core.tools import tool
from langgraph.types import Command

from deerflow.incubation.account_direction import (
    AccountDirectionOptionDraft,
    AccountDirectionProposalDraft,
    confirm_account_direction,
    propose_account_direction,
    render_account_direction,
    render_account_direction_proposal,
)
from deerflow.incubation.contracts import LogicalAccountRef, ProjectRef
from deerflow.incubation.project_bootstrap import (
    implicit_project_display_name,
    implicit_thread_logical_account_ref,
    implicit_thread_project_ref,
)
from deerflow.tools.builtins.incubation_tool_support import (
    get_incubation_repository,
    runtime_context_text,
)
from deerflow.tools.types import Runtime
from deerflow.utils.messages import get_original_user_content_text, is_real_user_message

logger = logging.getLogger(__name__)


def _terminal_direction_command(
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


def _latest_real_user_text(runtime: Runtime) -> str | None:
    state = runtime.state if isinstance(runtime.state, dict) else {}
    messages = state.get("messages", ())
    for message in reversed(messages):
        if not is_real_user_message(message):
            continue
        text = get_original_user_content_text(
            message.content,
            message.additional_kwargs,
        ).strip()
        if text:
            return text
    return None


async def _resolve_scope(
    runtime: Runtime,
    *,
    repository: Any,
    source_user_text: str,
    create_implicit: bool,
) -> tuple[ProjectRef, LogicalAccountRef] | None:
    owner_user_id = runtime_context_text(runtime, "user_id")
    thread_id = runtime_context_text(runtime, "thread_id")
    if owner_user_id is None or thread_id is None:
        return None

    selected_project_id = runtime_context_text(runtime, "incubation_project_id")
    project = ProjectRef(owner_user_id=owner_user_id, project_id=selected_project_id) if selected_project_id is not None else implicit_thread_project_ref(owner_user_id=owner_user_id, thread_id=thread_id)
    project_record = await repository.get_project(project)
    if project_record is None:
        if selected_project_id is not None or not create_implicit:
            return None
        try:
            await repository.create_project(
                project,
                display_name=implicit_project_display_name(source_user_text),
            )
        except Exception:
            if await repository.get_project(project) is None:
                raise

    selected_account_id = runtime_context_text(
        runtime,
        "incubation_logical_account_id",
    )
    logical_account = (
        LogicalAccountRef(
            owner_user_id=owner_user_id,
            project_id=project.project_id,
            logical_account_id=selected_account_id,
        )
        if selected_account_id is not None
        else implicit_thread_logical_account_ref(project=project, thread_id=thread_id)
    )
    account_record = await repository.get_logical_account(logical_account)
    if account_record is None:
        if selected_account_id is not None or not create_implicit:
            return None
        try:
            await repository.create_logical_account(
                logical_account,
                display_name=implicit_project_display_name(source_user_text),
            )
        except Exception:
            if await repository.get_logical_account(logical_account) is None:
                raise
    return project, logical_account


def _persistence_receipt(artifact) -> dict[str, str]:
    return {
        "status": "stored",
        "project_id": artifact.project.project_id,
        "logical_account_id": artifact.logical_account.logical_account_id,
        "artifact_type": artifact.artifact_type,
        "artifact_id": artifact.artifact_id,
        "content_sha256": artifact.content_sha256,
    }


@tool("propose_account_direction", return_direct=True)
async def propose_account_direction_tool(
    runtime: Runtime,
    marketing_subject: str,
    direction_options: list[AccountDirectionOptionDraft],
    recommended_option_number: int,
    business_goal: str | None = None,
    basis_artifact_ids: list[str] | None = None,
    unknowns: list[str] | None = None,
    revision_reason: str | None = None,
) -> Command:
    """Persist one to three coherent account-direction candidates without selecting for the user."""

    tool_name = "propose_account_direction"
    owner_user_id = runtime_context_text(runtime, "user_id")
    thread_id = runtime_context_text(runtime, "thread_id")
    run_id = runtime_context_text(runtime, "run_id")
    source_user_text = _latest_real_user_text(runtime)
    if owner_user_id is None or thread_id is None or run_id is None or source_user_text is None:
        return _terminal_direction_command(
            "当前对话缺少可验证的用户原话或运行身份，因此没有写入账号方向。",
            tool_call_id=runtime.tool_call_id,
            tool_name=tool_name,
        )
    repository = get_incubation_repository()
    if repository is None:
        return _terminal_direction_command(
            "账号方向台账暂时不可用，因此没有生成无法延续的临时定位。",
            tool_call_id=runtime.tool_call_id,
            tool_name=tool_name,
        )
    try:
        proposal_draft = AccountDirectionProposalDraft(
            marketing_subject=marketing_subject,
            business_goal=business_goal,
            direction_options=tuple(direction_options),
            recommended_option_number=recommended_option_number,
            basis_artifact_ids=tuple(basis_artifact_ids or ()),
            unknowns=tuple(unknowns or ()),
            revision_reason=revision_reason,
        )
        scope = await _resolve_scope(
            runtime,
            repository=repository,
            source_user_text=source_user_text,
            create_implicit=True,
        )
        if scope is None:
            raise ValueError("selected account direction scope is unavailable")
        project, logical_account = scope
        prepared = await propose_account_direction(
            project=project,
            logical_account=logical_account,
            repository=repository,
            draft=proposal_draft,
            source_user_text=source_user_text,
            created_at=datetime.now(UTC),
            source_thread_id=thread_id,
            source_run_id=run_id,
        )
    except Exception as exc:
        logger.warning(
            "Account direction proposal was unavailable: %s",
            type(exc).__name__,
        )
        return _terminal_direction_command(
            "这次账号方向没有通过台账校验，因此没有用一个无法追溯的提案覆盖用户项目。",
            tool_call_id=runtime.tool_call_id,
            tool_name=tool_name,
        )
    return _terminal_direction_command(
        render_account_direction_proposal(prepared),
        tool_call_id=runtime.tool_call_id,
        tool_name=tool_name,
        persistence=_persistence_receipt(prepared.proposal_artifact),
    )


@tool("confirm_account_direction", return_direct=True)
async def confirm_account_direction_tool(
    runtime: Runtime,
    proposal_artifact_id: str,
    option_id: str,
) -> Command:
    """Confirm one exact option from the latest account-direction proposal."""

    tool_name = "confirm_account_direction"
    thread_id = runtime_context_text(runtime, "thread_id")
    run_id = runtime_context_text(runtime, "run_id")
    source_user_text = _latest_real_user_text(runtime)
    repository = get_incubation_repository()
    if thread_id is None or run_id is None or source_user_text is None or repository is None:
        return _terminal_direction_command(
            "当前账号方向提案不可验证，因此没有确认。",
            tool_call_id=runtime.tool_call_id,
            tool_name=tool_name,
        )
    try:
        scope = await _resolve_scope(
            runtime,
            repository=repository,
            source_user_text=source_user_text,
            create_implicit=False,
        )
        if scope is None:
            raise ValueError("account direction scope is unavailable")
        project, logical_account = scope
        prepared = await confirm_account_direction(
            project=project,
            logical_account=logical_account,
            repository=repository,
            proposal_artifact_id=proposal_artifact_id,
            option_id=option_id,
            confirmation_user_text=source_user_text,
            created_at=datetime.now(UTC),
            source_thread_id=thread_id,
            source_run_id=run_id,
        )
    except Exception as exc:
        logger.warning(
            "Account direction confirmation was rejected: %s",
            type(exc).__name__,
        )
        return _terminal_direction_command(
            "当前回执与最新候选方向不匹配，因此没有确认账号方向。",
            tool_call_id=runtime.tool_call_id,
            tool_name=tool_name,
        )
    return _terminal_direction_command(
        render_account_direction(prepared),
        tool_call_id=runtime.tool_call_id,
        tool_name=tool_name,
        persistence=_persistence_receipt(prepared.direction_artifact),
    )


__all__ = [
    "confirm_account_direction_tool",
    "propose_account_direction_tool",
]
