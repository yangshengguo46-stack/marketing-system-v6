from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any, Literal

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from pydantic import Field, ValidationError, model_validator

from deerflow.incubation.contracts import (
    ArtifactEnvelope,
    IncubationContract,
    LogicalAccountRef,
    NonEmptyStr,
    ProjectRef,
)
from deerflow.incubation.judgment import IncubationJudgment
from deerflow.incubation.launch_plan import (
    AccountLaunchPlan,
    FirstWeekDay,
    LaunchCapacity,
    LaunchCheckpoint,
    LaunchPhase,
    LaunchSeries,
    PlannedTopicSeed,
    seal_account_launch_plan,
)


class AccountLaunchPlanDraft(IncubationContract):
    """Model-owned plan body; identity, lineage and confirmation are server-owned."""

    planning_request: NonEmptyStr = Field(max_length=4000)
    capacity: LaunchCapacity
    series: tuple[LaunchSeries, ...] = Field(min_length=1, max_length=8)
    topic_seeds: tuple[PlannedTopicSeed, ...] = Field(min_length=1, max_length=24)
    first_week: tuple[FirstWeekDay, ...] = Field(min_length=7, max_length=7)
    later_phases: tuple[LaunchPhase, ...] = Field(min_length=1, max_length=8)
    checkpoints: tuple[LaunchCheckpoint, ...] = Field(min_length=2, max_length=8)
    unknowns: tuple[NonEmptyStr, ...] = Field(default=(), max_length=12)

    @model_validator(mode="after")
    def validate_body(self) -> AccountLaunchPlanDraft:
        AccountLaunchPlan(
            strategy_artifact_id="server-owned-placeholder",
            content_map_version_id="server-owned-placeholder",
            **self.model_dump(),
        )
        return self


StructuredLaunchPlanModel = Callable[
    [type[AccountLaunchPlanDraft], tuple[BaseMessage, ...]],
    Awaitable[Any],
]

ACCOUNT_LAUNCH_PLAN_MODEL_INPUT_MAX_BYTES = 24_000
_MAX_PROJECTED_PATHS = 16

ACCOUNT_LAUNCH_PLAN_SYSTEM_PROMPT = """<account_launch_plan>
你正在为一个已经由用户确认路线的逻辑账号，编制可修改的 7 天首轮和 30 天运营计划。你只负责编排栏目、计划题眼、行动节奏、观察问题和调整条件；不得重新做账号定位。

边界：
- 7 天不是算法门槛，只是第一轮方向与真实产能验证期。30 天不是成功期限，只是形成第一版可重复运营系统的计划视窗。
- 不得修改已确认的定位、受众、人设、表现形式或变现判断。confirmed_account_strategy 是父级，不是供你改写的草稿。
- 栏目和题眼只能引用 allowed_content_map_path_ids 中的路径。地图路径是候选方向，不是已经证实的爆款机制。
- 一个计划题眼必须写清具体主体、具体事件或问题，以及账号准备表达的观点。笼统的行业方向不能充当题眼。
- 计划题眼不能冒充 TopicBrief。人物、历史、作品、数字和当前事件在执行前仍须搜索、读证据并形成 TopicBrief；evidence_need 必须明说如何核验。
- 用户案例只有明确提供时才能使用；否则只能写 user_case 作为未来来源，不能补造客户、素材、经历或结果。
- creative_hypothesis 必须明确是创意情景，不能冒充真实故事。
- 非发布日是一等运营日，可以研究、取证、写稿、试拍、制作、观察或复盘。不要强迫每天发布。
- 发布节奏来自 user_stated_capacity。产能未知时 capacity.status 必须是 provisional，并把发布日写成可修改安排；不得伪装成平台规律。
- 不写粉丝、播放、转化、预算、发布时间或成功率硬阈值，不保证爆款或起号成功。
- 每条内容只指定一个主要 content_role。组合可以覆盖 attention、recognition、understanding、trust、proof、action，但不得为凑齐类别强行各安排一条。
- 第 7 天与第 30 天检查点只提出观察问题和可选调整，不得阻止继续创作。
- planning_request 必须逐字复制输入，不得扩写用户要求。

只返回 AccountLaunchPlanDraft。版本、父级、账号身份和确认状态由代码负责。
</account_launch_plan>"""


class AccountLaunchPlanModelError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        stage: Literal["model_call", "model_output", "binding"],
        diagnostics: tuple[str, ...],
    ) -> None:
        super().__init__(message)
        self.stage = stage
        self.diagnostics = diagnostics


def _safe_diagnostics(error: BaseException) -> tuple[str, ...]:
    if isinstance(error, ValidationError):
        return tuple(f"{item.get('type', 'validation_error')}@{'.'.join(str(part) for part in item.get('loc', ())) or 'root'}" for item in error.errors(include_url=False, include_context=False, include_input=False)[:8])
    return (type(error).__name__,)


def _clip(value: object, *, max_chars: int) -> object:
    if isinstance(value, str) and len(value) > max_chars:
        return value[: max_chars - 3] + "..."
    return value


def _strategy_projection(artifact: ArtifactEnvelope) -> dict[str, object]:
    fields = (
        "selected_option_id",
        "positioning",
        "business_intent",
        "audience",
        "persona",
        "presentation",
        "monetization",
        "unknowns",
    )
    return {field: artifact.payload.get(field) for field in fields}


def _path_projection(content_world_artifact: ArtifactEnvelope) -> list[dict[str, object]]:
    projected: list[dict[str, object]] = []
    dimensions = content_world_artifact.payload.get("dimensions", [])
    if not isinstance(dimensions, list):
        return projected
    for dimension in dimensions:
        if not isinstance(dimension, dict):
            continue
        paths = dimension.get("paths", [])
        if not isinstance(paths, list):
            continue
        for path in paths:
            if not isinstance(path, dict) or not isinstance(path.get("path_id"), str):
                continue
            steps = path.get("steps", [])
            step_projection = []
            if isinstance(steps, list):
                for step in steps:
                    if isinstance(step, dict):
                        step_projection.append(
                            {
                                "from_label": _clip(step.get("from_label"), max_chars=240),
                                "relation": _clip(step.get("relation"), max_chars=240),
                                "to_label": _clip(step.get("to_label"), max_chars=240),
                                "status": step.get("status"),
                                "verification_needed": step.get("verification_needed"),
                            }
                        )
            projected.append(
                {
                    "dimension": _clip(dimension.get("name"), max_chars=160),
                    "path_id": path["path_id"],
                    "rationale": _clip(path.get("rationale"), max_chars=360),
                    "steps": step_projection,
                }
            )
    return sorted(projected, key=lambda item: str(item["path_id"]))[:_MAX_PROJECTED_PATHS]


def _render_model_input(
    *,
    planning_request: str,
    strategy_artifact: ArtifactEnvelope,
    content_world_artifact: ArtifactEnvelope,
    previous_plan_artifact: ArtifactEnvelope | None,
) -> str:
    paths = _path_projection(content_world_artifact)
    payload = {
        "planning_request": planning_request,
        "confirmed_account_strategy": {
            "artifact_id": strategy_artifact.artifact_id,
            "content_sha256": strategy_artifact.content_sha256,
            "payload": _strategy_projection(strategy_artifact),
        },
        "candidate_content_map": {
            "artifact_id": content_world_artifact.artifact_id,
            "content_sha256": content_world_artifact.content_sha256,
            "content_map_version_id": content_world_artifact.payload.get("content_map_version_id"),
            "content_root": content_world_artifact.payload.get("content_root"),
            "editorial_promise": content_world_artifact.payload.get("editorial_promise"),
            "recurring_lens": content_world_artifact.payload.get("recurring_lens"),
            "drift_boundaries": content_world_artifact.payload.get("drift_boundaries", []),
            "paths": paths,
        },
        "allowed_content_map_path_ids": [str(path["path_id"]) for path in paths],
        "previous_launch_plan": (
            {
                "artifact_id": previous_plan_artifact.artifact_id,
                "content_sha256": previous_plan_artifact.content_sha256,
                "payload": previous_plan_artifact.payload,
            }
            if previous_plan_artifact is not None
            else None
        ),
    }
    rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    if len(rendered.encode("utf-8")) > ACCOUNT_LAUNCH_PLAN_MODEL_INPUT_MAX_BYTES:
        raise ValueError("bounded account launch plan input exceeds its byte budget")
    return rendered


def _validate_parents(
    *,
    project: ProjectRef,
    strategy_artifact: ArtifactEnvelope,
    content_world_artifact: ArtifactEnvelope,
    logical_account: LogicalAccountRef,
) -> IncubationJudgment:
    if strategy_artifact.project != project or strategy_artifact.artifact_type != "incubation_judgment":
        raise ValueError("launch planning requires a same-project incubation judgment")
    if content_world_artifact.project != project or content_world_artifact.artifact_type != "content_map_candidate":
        raise ValueError("launch planning requires a same-project candidate content map")
    if strategy_artifact.logical_account != logical_account or content_world_artifact.logical_account != logical_account:
        raise ValueError("launch planning parent logical accounts must match")
    strategy = IncubationJudgment.model_validate(strategy_artifact.payload)
    if strategy.decision_status != "confirmed":
        raise ValueError("launch planning requires a confirmed account strategy")
    if strategy.content_map_version_id != content_world_artifact.payload.get("content_map_version_id"):
        raise ValueError("launch planning strategy and map versions must match")
    return strategy


async def generate_account_launch_plan(
    *,
    project: ProjectRef,
    logical_account: LogicalAccountRef,
    planning_request: str,
    strategy_artifact: ArtifactEnvelope,
    content_world_artifact: ArtifactEnvelope,
    structured_model: StructuredLaunchPlanModel,
    created_at: datetime,
    source_thread_id: str,
    source_run_id: str,
    previous_plan_artifact: ArtifactEnvelope | None = None,
) -> ArtifactEnvelope:
    _validate_parents(
        project=project,
        strategy_artifact=strategy_artifact,
        content_world_artifact=content_world_artifact,
        logical_account=logical_account,
    )
    messages: tuple[BaseMessage, ...] = (
        SystemMessage(content=ACCOUNT_LAUNCH_PLAN_SYSTEM_PROMPT),
        HumanMessage(
            content=_render_model_input(
                planning_request=planning_request,
                strategy_artifact=strategy_artifact,
                content_world_artifact=content_world_artifact,
                previous_plan_artifact=previous_plan_artifact,
            )
        ),
    )
    try:
        result = await structured_model(AccountLaunchPlanDraft, messages)
    except Exception as error:
        raise AccountLaunchPlanModelError(
            "structured model failed while generating an account launch plan",
            stage="model_call",
            diagnostics=_safe_diagnostics(error),
        ) from error
    try:
        draft = AccountLaunchPlanDraft.model_validate(result)
    except (ValidationError, TypeError, ValueError) as error:
        raise AccountLaunchPlanModelError(
            "structured model returned an invalid account launch plan draft",
            stage="model_output",
            diagnostics=_safe_diagnostics(error),
        ) from error

    if draft.planning_request != planning_request:
        raise AccountLaunchPlanModelError(
            "account launch plan changed the user's planning request",
            stage="binding",
            diagnostics=("planning_request_mismatch",),
        )
    revision_number = 1
    supersedes_id = None
    revision_reason = None
    if previous_plan_artifact is not None:
        previous = AccountLaunchPlan.model_validate(previous_plan_artifact.payload)
        revision_number = previous.revision_number + 1
        supersedes_id = previous_plan_artifact.artifact_id
        revision_reason = "用户提出新的计划要求，或账号已确认状态发生变化，重新生成待确认运营计划。"
    plan = AccountLaunchPlan(
        revision_number=revision_number,
        supersedes_plan_artifact_id=supersedes_id,
        revision_reason=revision_reason,
        decision_status="proposed",
        strategy_artifact_id=strategy_artifact.artifact_id,
        content_map_version_id=str(content_world_artifact.payload["content_map_version_id"]),
        **draft.model_dump(),
    )
    try:
        return seal_account_launch_plan(
            project=project,
            logical_account=logical_account,
            plan=plan,
            strategy_artifact=strategy_artifact,
            content_world_artifact=content_world_artifact,
            previous_plan_artifact=previous_plan_artifact,
            created_at=created_at,
            source_thread_id=source_thread_id,
            source_run_id=source_run_id,
        )
    except (ValidationError, TypeError, ValueError) as error:
        raise AccountLaunchPlanModelError(
            "account launch plan could not bind to its immutable parents",
            stage="binding",
            diagnostics=_safe_diagnostics(error),
        ) from error


__all__ = [
    "ACCOUNT_LAUNCH_PLAN_MODEL_INPUT_MAX_BYTES",
    "ACCOUNT_LAUNCH_PLAN_SYSTEM_PROMPT",
    "AccountLaunchPlanDraft",
    "AccountLaunchPlanModelError",
    "StructuredLaunchPlanModel",
    "generate_account_launch_plan",
]
