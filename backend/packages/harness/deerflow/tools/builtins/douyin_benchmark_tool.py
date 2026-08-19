from __future__ import annotations

import json
import logging
from collections.abc import Mapping

from langchain.tools import tool
from pydantic import ValidationError

from deerflow.community.douyin_browser import (
    DouyinBrowserAccountRequest,
    DouyinBrowserUnavailable,
    collect_browser_benchmark_account,
    collect_browser_benchmark_candidate,
)
from deerflow.community.douyin_openapi import (
    BenchmarkCandidateCollectionError,
    BenchmarkCandidateRequest,
    collect_benchmark_account_candidate,
    seal_benchmark_account_candidate,
)
from deerflow.community.douyin_openapi.server import (
    build_default_router,
    context_from_environment,
)
from deerflow.incubation import (
    IncubationLedgerRepository,
    ProjectRef,
    seal_benchmark_snapshot,
)
from deerflow.persistence.engine import get_session_factory
from deerflow.runtime.user_context import resolve_runtime_user_id
from deerflow.tools.types import Runtime

logger = logging.getLogger(__name__)

_LEAD_PROJECTION_MAX_BYTES = 16_000
_MAX_PAGES = 5


def _runtime_text(runtime: Runtime, name: str) -> str | None:
    context = getattr(runtime, "context", None)
    if not isinstance(context, Mapping):
        return None
    value = context.get(name)
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


def _get_repository() -> IncubationLedgerRepository | None:
    session_factory = get_session_factory()
    if session_factory is None:
        return None
    return IncubationLedgerRepository(session_factory)


def _response(status: str, **values: object) -> str:
    return json.dumps(
        {"status": status, **values},
        ensure_ascii=False,
        separators=(",", ":"),
    )


async def _collect_douyin_benchmark_candidate(
    runtime: Runtime,
    query: str,
    actor_label: str,
    max_posts: int = 12,
) -> str:
    project_id = _runtime_text(runtime, "incubation_project_id")
    repository: IncubationLedgerRepository | None = None
    project: ProjectRef | None = None
    thread_id: str | None = None
    run_id: str | None = None

    if project_id is not None:
        try:
            project = ProjectRef(
                owner_user_id=resolve_runtime_user_id(runtime),
                project_id=project_id,
            )
        except ValidationError:
            return _response(
                "invalid_project",
                message="The selected incubation project is unavailable for the authenticated user.",
            )
        repository = _get_repository()
        if repository is None or await repository.get_project(project) is None:
            return _response(
                "invalid_project",
                message="The selected incubation project is unavailable for the authenticated user.",
            )
        thread_id = _runtime_text(runtime, "thread_id")
        run_id = _runtime_text(runtime, "run_id")
        if thread_id is None or run_id is None:
            return _response(
                "runtime_unavailable",
                message="The current run cannot safely attribute project evidence.",
            )

    try:
        request = BenchmarkCandidateRequest(
            query=query,
            actor_label=actor_label,
            max_posts=max_posts,
            max_pages=_MAX_PAGES,
        )
    except ValidationError:
        return _response(
            "invalid_request",
            message="The Douyin search phrase, actor label, or sample limit is invalid.",
        )

    try:
        snapshot = await collect_benchmark_account_candidate(
            request,
            router=build_default_router(),
            context=context_from_environment(),
        )
    except BenchmarkCandidateCollectionError:
        try:
            snapshot = await collect_browser_benchmark_candidate(request)
        except DouyinBrowserUnavailable:
            return _response(
                "unavailable",
                message="Douyin benchmark evidence is unavailable for this request.",
            )
        except Exception as exc:
            logger.warning(
                "Douyin browser benchmark collection failed: %s",
                type(exc).__name__,
            )
            return _response(
                "unavailable",
                message="Douyin benchmark evidence is unavailable for this request.",
            )
    except Exception as exc:
        logger.warning(
            "Official Douyin benchmark collection failed: %s",
            type(exc).__name__,
        )
        return _response(
            "unavailable",
            message="Official Douyin benchmark evidence is unavailable for this request.",
        )

    projection = snapshot.to_lead_projection(max_bytes=_LEAD_PROJECTION_MAX_BYTES)
    persistence: dict[str, object] = {"status": "not_selected"}
    if project is not None and repository is not None and thread_id is not None and run_id is not None:
        try:
            artifact = seal_benchmark_account_candidate(
                project=project,
                snapshot=snapshot,
                source_thread_id=thread_id,
                source_run_id=run_id,
            )
            stored = await repository.put_artifact(artifact)
            persistence = {
                "status": "stored",
                "project_id": project.project_id,
                "artifact_id": stored.artifact_id,
            }
        except Exception as exc:
            logger.warning(
                "Official Douyin benchmark evidence persistence failed: %s",
                type(exc).__name__,
            )
            persistence = {
                "status": "failed",
                "project_id": project.project_id,
                "message": "The collected evidence could not be stored in the selected project.",
            }

    return _response(
        "ok",
        evidence=projection,
        persistence=persistence,
    )


async def _collect_douyin_benchmark_account(
    runtime: Runtime,
    account_url: str,
    max_posts: int = 12,
) -> str:
    project_id = _runtime_text(runtime, "incubation_project_id")
    repository: IncubationLedgerRepository | None = None
    project: ProjectRef | None = None
    thread_id: str | None = None
    run_id: str | None = None

    if project_id is not None:
        try:
            project = ProjectRef(
                owner_user_id=resolve_runtime_user_id(runtime),
                project_id=project_id,
            )
        except ValidationError:
            return _response(
                "invalid_project",
                message="The selected incubation project is unavailable for the authenticated user.",
            )
        repository = _get_repository()
        if repository is None or await repository.get_project(project) is None:
            return _response(
                "invalid_project",
                message="The selected incubation project is unavailable for the authenticated user.",
            )
        thread_id = _runtime_text(runtime, "thread_id")
        run_id = _runtime_text(runtime, "run_id")
        if thread_id is None or run_id is None:
            return _response(
                "runtime_unavailable",
                message="The current run cannot safely attribute project evidence.",
            )

    try:
        request = DouyinBrowserAccountRequest(
            requested_url=account_url,
            max_posts=max_posts,
        )
    except ValidationError:
        return _response(
            "invalid_request",
            message="The Douyin account URL or sample limit is invalid.",
        )

    try:
        snapshot = await collect_browser_benchmark_account(request)
    except DouyinBrowserUnavailable:
        return _response(
            "unavailable",
            message="The selected Douyin account is unavailable through the local browser session.",
        )
    except Exception as exc:
        logger.warning(
            "Douyin benchmark account collection failed: %s",
            type(exc).__name__,
        )
        return _response(
            "unavailable",
            message="The selected Douyin account is unavailable through the local browser session.",
        )

    projection = snapshot.to_lead_projection(max_bytes=_LEAD_PROJECTION_MAX_BYTES)
    persistence: dict[str, object] = {"status": "not_selected"}
    if project is not None and repository is not None and thread_id is not None and run_id is not None:
        try:
            artifact = seal_benchmark_snapshot(
                project=project,
                snapshot=snapshot,
                source_thread_id=thread_id,
                source_run_id=run_id,
            )
            stored = await repository.put_artifact(artifact)
            persistence = {
                "status": "stored",
                "project_id": project.project_id,
                "artifact_id": stored.artifact_id,
            }
        except Exception as exc:
            logger.warning(
                "Douyin benchmark account persistence failed: %s",
                type(exc).__name__,
            )
            persistence = {
                "status": "failed",
                "project_id": project.project_id,
                "message": "The collected evidence could not be stored in the selected project.",
            }

    return _response(
        "ok",
        evidence=projection,
        persistence=persistence,
    )


@tool("collect_douyin_benchmark_candidate", parse_docstring=True)
async def douyin_benchmark_candidate_tool(
    runtime: Runtime,
    query: str,
    actor_label: str,
    max_posts: int = 12,
) -> str:
    """Collect a bounded public-content sample for one Douyin benchmark candidate.

    Use this when the user asks to inspect or compare a specific public Douyin
    creator or account. It returns observations and coverage, not positioning,
    audience, success-cause, or copyability conclusions. A selected incubation
    project is used only for optional evidence persistence and is injected by
    the runtime rather than supplied by the model.

    Args:
        query: Search phrase likely to retrieve the target creator's public videos.
        actor_label: Target creator display name to match exactly after Unicode normalization.
        max_posts: Maximum author-matching public videos to retain, from 1 to 24.
    """

    return await _collect_douyin_benchmark_candidate(
        runtime=runtime,
        query=query,
        actor_label=actor_label,
        max_posts=max_posts,
    )


@tool("collect_douyin_benchmark_account", parse_docstring=True)
async def douyin_benchmark_account_tool(
    runtime: Runtime,
    account_url: str,
    max_posts: int = 12,
) -> str:
    """Collect a formal bounded snapshot for one specific public Douyin account.

    Use this when the user supplies a Douyin account link or has selected one
    candidate. The connector opens that account directly, keeps only posts with
    the same observed author identity, and returns public observations plus a
    coverage receipt. It does not decide positioning, audience, success cause,
    or whether the account should be copied.

    Args:
        account_url: Public Douyin account or account-share URL to inspect directly.
        max_posts: Maximum author-qualified public posts to retain, from 1 to 24.
    """

    return await _collect_douyin_benchmark_account(
        runtime=runtime,
        account_url=account_url,
        max_posts=max_posts,
    )


__all__ = [
    "douyin_benchmark_account_tool",
    "douyin_benchmark_candidate_tool",
]
