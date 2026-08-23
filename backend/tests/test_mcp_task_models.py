import pytest

from deerflow.mcp.tasks import (
    ATTENTION_TASK_STATUSES,
    CLAIMABLE_TASK_STATUSES,
    TERMINAL_TASK_STATUSES,
    McpTaskDriverRegistry,
    TaskSnapshot,
    TaskStatus,
    TaskSubmission,
    TaskSubmissionPolicy,
)


def test_task_snapshot_normalizes_string_statuses():
    snapshot = TaskSnapshot(status="working")  # type: ignore[arg-type]
    assert snapshot.status is TaskStatus.WORKING
    assert snapshot.is_pollable is True


def test_submission_pending_is_claimable_but_not_a_remote_poll_state():
    assert TaskStatus.SUBMISSION_PENDING in CLAIMABLE_TASK_STATUSES
    snapshot = TaskSnapshot(status=TaskStatus.SUBMISSION_PENDING)
    assert snapshot.is_pollable is False
    assert snapshot.needs_attention is False


def test_submission_unknown_is_terminal_attention_and_never_claimable():
    assert TaskStatus.SUBMISSION_UNKNOWN in TERMINAL_TASK_STATUSES
    assert TaskStatus.SUBMISSION_UNKNOWN in ATTENTION_TASK_STATUSES
    assert TaskStatus.SUBMISSION_UNKNOWN not in CLAIMABLE_TASK_STATUSES
    snapshot = TaskSnapshot(status=TaskStatus.SUBMISSION_UNKNOWN)
    assert snapshot.is_pollable is False
    assert snapshot.needs_attention is True


def test_submission_policy_values_are_stable():
    assert TaskSubmissionPolicy.IDEMPOTENT_RETRY.value == "idempotent_retry"
    assert TaskSubmissionPolicy.AT_MOST_ONCE.value == "at_most_once"


def test_input_required_snapshot_requires_payload():
    with pytest.raises(ValueError, match="requires an input_required payload"):
        TaskSnapshot(status=TaskStatus.INPUT_REQUIRED)


def test_submission_rejects_empty_remote_id():
    with pytest.raises(ValueError, match="remote_task_id must not be empty"):
        TaskSubmission(remote_task_id="  ", snapshot=TaskSnapshot(status=TaskStatus.SUBMITTED))


@pytest.mark.parametrize(
    "status",
    [TaskStatus.SUBMISSION_PENDING, TaskStatus.SUBMISSION_UNKNOWN],
)
def test_remote_task_submission_rejects_local_only_statuses(status: TaskStatus) -> None:
    with pytest.raises(ValueError, match="local-only"):
        TaskSubmission(
            remote_task_id="remote-1",
            snapshot=TaskSnapshot(status=status),
        )


def test_driver_registry_rejects_duplicate_names():
    registry = McpTaskDriverRegistry()
    driver = object()
    registry.register("ordinary", driver)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="already registered"):
        registry.register("ordinary", driver)  # type: ignore[arg-type]
