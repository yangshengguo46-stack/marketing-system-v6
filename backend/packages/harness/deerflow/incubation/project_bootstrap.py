from __future__ import annotations

import hashlib

from deerflow.incubation.contracts import LogicalAccountRef, ProjectRef


def implicit_thread_project_ref(*, owner_user_id: str, thread_id: str) -> ProjectRef:
    """Return the stable owner-scoped project used to bootstrap an unbound thread."""

    digest = hashlib.sha256(f"{owner_user_id}\0{thread_id}".encode()).hexdigest()[:32]
    return ProjectRef(
        owner_user_id=owner_user_id,
        project_id=f"thread_{digest}",
    )


def implicit_project_display_name(user_request: str) -> str:
    """Use the first real incubation request as the provisional project label."""

    normalized = " ".join(user_request.split())
    return normalized[:255] or "新孵化项目"


def implicit_thread_logical_account_ref(
    *,
    project: ProjectRef,
    thread_id: str,
) -> LogicalAccountRef:
    """Return the stable logical account for a thread before platform login."""

    digest = hashlib.sha256(f"{project.owner_user_id}\0{project.project_id}\0{thread_id}".encode()).hexdigest()[:32]
    return LogicalAccountRef(
        owner_user_id=project.owner_user_id,
        project_id=project.project_id,
        logical_account_id=f"account_{digest}",
    )


__all__ = [
    "implicit_project_display_name",
    "implicit_thread_logical_account_ref",
    "implicit_thread_project_ref",
]
