import pytest

from deerflow.mcp.tasks import (
    CLAIMABLE_TASK_STATUSES,
    McpTaskDriverRegistry,
    TaskSnapshot,
    TaskStatus,
    TaskSubmission,
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


def test_input_required_snapshot_requires_payload():
    with pytest.raises(ValueError, match="requires an input_required payload"):
        TaskSnapshot(status=TaskStatus.INPUT_REQUIRED)


def test_submission_rejects_empty_remote_id():
    with pytest.raises(ValueError, match="remote_task_id must not be empty"):
        TaskSubmission(remote_task_id="  ", snapshot=TaskSnapshot(status=TaskStatus.SUBMITTED))


def test_driver_registry_rejects_duplicate_names():
    registry = McpTaskDriverRegistry()
    driver = object()
    registry.register("ordinary", driver)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="already registered"):
        registry.register("ordinary", driver)  # type: ignore[arg-type]
