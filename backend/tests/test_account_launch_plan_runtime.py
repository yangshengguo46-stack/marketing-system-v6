from __future__ import annotations

import json
from datetime import UTC, datetime

from deerflow.incubation import ArtifactEnvelope, LogicalAccountRef, ProjectRef
from deerflow.incubation.account_direction import AccountDirectionOption, AccountDirectionVersion
from deerflow.incubation.launch_plan_runtime import (
    ACCOUNT_LAUNCH_PLAN_MODEL_INPUT_MAX_BYTES,
    ACCOUNT_LAUNCH_PLAN_SYSTEM_PROMPT,
    AccountLaunchPlanModelError,
    _render_model_input,
)


def test_launch_plan_prompt_keeps_7_30_day_windows_out_of_platform_mythology() -> None:
    normalized = " ".join(ACCOUNT_LAUNCH_PLAN_SYSTEM_PROMPT.split())

    assert "7 天不是算法门槛" in normalized
    assert "30 天不是成功期限" in normalized
    assert "非发布日" in normalized
    assert "不能冒充 TopicBrief" in normalized
    assert "不得修改已确认的定位、受众、人设、表现形式或变现判断" in normalized


def test_launch_plan_input_budget_is_smaller_than_a_full_cold_start_context() -> None:
    assert ACCOUNT_LAUNCH_PLAN_MODEL_INPUT_MAX_BYTES <= 24_000


def test_launch_plan_model_error_keeps_stage_without_provider_payload() -> None:
    error = AccountLaunchPlanModelError(
        "invalid plan",
        stage="binding",
        diagnostics=("unknown_map_path",),
    )

    assert error.stage == "binding"
    assert error.diagnostics == ("unknown_map_path",)
    assert "provider" not in json.dumps(error.diagnostics)


def test_direction_projection_stays_bounded_when_free_text_lists_are_large() -> None:
    project = ProjectRef(owner_user_id="user-1", project_id="project-1")
    account = LogicalAccountRef(owner_user_id="user-1", project_id="project-1", logical_account_id="account-1")
    now = datetime(2026, 8, 22, tzinfo=UTC)
    long_item = "很长的补充说明" * 2_000
    direction = AccountDirectionVersion(
        revision_number=1,
        proposal_artifact_id="proposal-1",
        source_user_text="确认方向",
        confirmation_user_text="确认采用",
        marketing_subject="测试业务",
        selected_option=AccountDirectionOption(
            option_id="direction_1",
            name="关系观察",
            content_root="人与人的关系",
            long_term_content_subject="从具体事件观察人与人的关系",
            rationale="测试",
            presentation_directions=tuple(long_item for _ in range(8)),
            unknowns=tuple(long_item for _ in range(12)),
            tradeoffs=tuple(long_item for _ in range(8)),
        ),
        unknowns=tuple(long_item for _ in range(12)),
    )
    direction_artifact = ArtifactEnvelope.seal(
        project=project,
        logical_account=account,
        artifact_type="account_direction_version",
        version=1,
        payload=direction.model_dump(mode="json"),
        created_at=now,
        source_thread_id="thread-1",
        source_run_id="run-1",
    )
    world_artifact = ArtifactEnvelope.seal(
        project=project,
        logical_account=account,
        artifact_type="content_map_candidate",
        version=1,
        payload={
            "content_map_version_id": "map-v1",
            "content_root": "人与人的关系",
            "dimensions": [],
        },
        parents=(direction_artifact.to_parent_ref(),),
        created_at=now,
        source_thread_id="thread-1",
        source_run_id="run-1",
    )

    rendered = _render_model_input(
        planning_request="编排起号计划",
        account_decision_artifact=direction_artifact,
        content_world_artifact=world_artifact,
        previous_plan_artifact=None,
    )

    assert len(rendered.encode("utf-8")) < ACCOUNT_LAUNCH_PLAN_MODEL_INPUT_MAX_BYTES
    payload = json.loads(rendered)
    projected = payload["confirmed_account_direction"]["payload"]["selected_option"]
    assert len(projected["presentation_directions"]) == 6
    assert all(len(item) <= 240 for item in projected["presentation_directions"])
