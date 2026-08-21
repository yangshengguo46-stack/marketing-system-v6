from __future__ import annotations

import json

from deerflow.incubation.launch_plan_runtime import (
    ACCOUNT_LAUNCH_PLAN_MODEL_INPUT_MAX_BYTES,
    ACCOUNT_LAUNCH_PLAN_SYSTEM_PROMPT,
    AccountLaunchPlanModelError,
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
