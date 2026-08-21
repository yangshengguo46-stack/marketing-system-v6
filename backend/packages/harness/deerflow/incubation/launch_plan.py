from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field, field_validator, model_validator

from deerflow.incubation.contracts import (
    ArtifactEnvelope,
    IncubationContract,
    LogicalAccountRef,
    NonEmptyStr,
    ProjectRef,
)
from deerflow.incubation.judgment import IncubationJudgment

LaunchPlanStatus = Literal["proposed", "confirmed"]
CapacityStatus = Literal["user_stated", "provisional"]
ContentRole = Literal["attention", "recognition", "understanding", "trust", "proof", "action"]
TopicSourceKind = Literal[
    "content_map",
    "user_case",
    "public_evidence",
    "benchmark_pattern",
    "prior_outcome",
    "creative_hypothesis",
]


def _require_unique(values: tuple[str, ...], *, label: str) -> tuple[str, ...]:
    if len(values) != len(set(values)):
        raise ValueError(f"{label} must be unique")
    return values


class LaunchCapacity(IncubationContract):
    status: CapacityStatus
    cadence_summary: NonEmptyStr = Field(max_length=1000)
    planned_publish_days: tuple[int, ...] = Field(default=(), max_length=30)
    basis: NonEmptyStr = Field(max_length=1200)
    production_assumptions: tuple[NonEmptyStr, ...] = Field(default=(), max_length=8)
    adjustment_trigger: NonEmptyStr = Field(max_length=1000)

    @field_validator("planned_publish_days")
    @classmethod
    def validate_publish_days(cls, value: tuple[int, ...]) -> tuple[int, ...]:
        if any(day < 1 or day > 30 for day in value):
            raise ValueError("planned publish days must stay within days 1 through 30")
        _require_unique(tuple(str(day) for day in value), label="planned publish days")
        return tuple(sorted(value))


class LaunchSeries(IncubationContract):
    series_id: NonEmptyStr = Field(max_length=80, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    name: NonEmptyStr = Field(max_length=200)
    purpose: NonEmptyStr = Field(max_length=1000)
    map_path_ids: tuple[NonEmptyStr, ...] = Field(min_length=1, max_length=12)
    repeatable_question: NonEmptyStr = Field(max_length=1000)
    topic_sources: tuple[NonEmptyStr, ...] = Field(min_length=1, max_length=8)

    @field_validator("map_path_ids", "topic_sources")
    @classmethod
    def validate_unique_values(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _require_unique(value, label="series references")


class PlannedTopicSeed(IncubationContract):
    """A concrete research lead, not an evidence-backed TopicBrief."""

    seed_id: NonEmptyStr = Field(max_length=80, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    series_id: NonEmptyStr = Field(max_length=80)
    map_path_id: NonEmptyStr = Field(max_length=160)
    content_role: ContentRole
    focal_subject: NonEmptyStr = Field(max_length=500)
    concrete_event_or_question: NonEmptyStr = Field(max_length=1000)
    account_viewpoint: NonEmptyStr = Field(max_length=1000)
    source_kind: TopicSourceKind
    evidence_need: NonEmptyStr = Field(max_length=1200)
    presentation_hint: NonEmptyStr | None = Field(default=None, max_length=500)


class FirstWeekDay(IncubationContract):
    day: int = Field(ge=1, le=7)
    focus: NonEmptyStr = Field(max_length=500)
    actions: tuple[NonEmptyStr, ...] = Field(min_length=1, max_length=6)
    topic_seed_ids: tuple[NonEmptyStr, ...] = Field(default=(), max_length=8)
    publish: bool = False
    observation_questions: tuple[NonEmptyStr, ...] = Field(default=(), max_length=6)

    @field_validator("topic_seed_ids")
    @classmethod
    def validate_topic_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _require_unique(value, label="first-week topic references")


class LaunchPhase(IncubationContract):
    start_day: int = Field(ge=8, le=30)
    end_day: int = Field(ge=8, le=30)
    objective: NonEmptyStr = Field(max_length=1000)
    series_ids: tuple[NonEmptyStr, ...] = Field(min_length=1, max_length=8)
    topic_seed_ids: tuple[NonEmptyStr, ...] = Field(default=(), max_length=16)
    actions: tuple[NonEmptyStr, ...] = Field(min_length=1, max_length=8)
    review_questions: tuple[NonEmptyStr, ...] = Field(min_length=1, max_length=8)

    @field_validator("series_ids", "topic_seed_ids")
    @classmethod
    def validate_refs(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _require_unique(value, label="phase references")

    @model_validator(mode="after")
    def validate_range(self) -> LaunchPhase:
        if self.end_day < self.start_day:
            raise ValueError("launch phase end_day cannot precede start_day")
        return self


class LaunchCheckpoint(IncubationContract):
    day: int = Field(ge=1, le=30)
    questions: tuple[NonEmptyStr, ...] = Field(min_length=1, max_length=8)
    possible_adjustments: tuple[NonEmptyStr, ...] = Field(min_length=1, max_length=8)


class AccountLaunchPlan(IncubationContract):
    revision_number: int = Field(default=1, ge=1)
    supersedes_plan_artifact_id: NonEmptyStr | None = None
    revision_reason: NonEmptyStr | None = Field(default=None, max_length=1200)
    decision_status: LaunchPlanStatus = "proposed"
    strategy_artifact_id: NonEmptyStr = Field(max_length=80)
    content_map_version_id: NonEmptyStr = Field(max_length=80)
    planning_request: NonEmptyStr = Field(max_length=4000)
    horizon_days: Literal[30] = 30
    first_sprint_days: Literal[7] = 7
    capacity: LaunchCapacity
    series: tuple[LaunchSeries, ...] = Field(min_length=1, max_length=8)
    topic_seeds: tuple[PlannedTopicSeed, ...] = Field(min_length=1, max_length=24)
    first_week: tuple[FirstWeekDay, ...] = Field(min_length=7, max_length=7)
    later_phases: tuple[LaunchPhase, ...] = Field(min_length=1, max_length=8)
    checkpoints: tuple[LaunchCheckpoint, ...] = Field(min_length=2, max_length=8)
    unknowns: tuple[NonEmptyStr, ...] = Field(default=(), max_length=12)

    @model_validator(mode="after")
    def validate_plan(self) -> AccountLaunchPlan:
        if self.revision_number == 1:
            if self.supersedes_plan_artifact_id is not None or self.revision_reason is not None:
                raise ValueError("first launch plan revision cannot supersede another plan")
        elif self.supersedes_plan_artifact_id is None or self.revision_reason is None:
            raise ValueError("a revised launch plan requires its previous artifact and a reason")

        days = tuple(day.day for day in self.first_week)
        if days != tuple(range(1, 8)):
            raise ValueError("first_week must cover days 1 through 7 exactly once and in order")

        expected_start = 8
        for phase in self.later_phases:
            if phase.start_day != expected_start:
                raise ValueError("later launch phases must continuously cover days 8 through 30")
            expected_start = phase.end_day + 1
        if expected_start != 31:
            raise ValueError("later launch phases must continuously cover days 8 through 30")

        checkpoint_days = tuple(checkpoint.day for checkpoint in self.checkpoints)
        _require_unique(tuple(str(day) for day in checkpoint_days), label="checkpoint days")
        if not {7, 30}.issubset(checkpoint_days):
            raise ValueError("launch plan checkpoints must include day 7 and day 30")

        series_by_id = {item.series_id: item for item in self.series}
        if len(series_by_id) != len(self.series):
            raise ValueError("launch series ids must be unique")
        seeds_by_id = {item.seed_id: item for item in self.topic_seeds}
        if len(seeds_by_id) != len(self.topic_seeds):
            raise ValueError("planned topic seed ids must be unique")

        for seed in self.topic_seeds:
            series = series_by_id.get(seed.series_id)
            if series is None:
                raise ValueError("planned topic seed references an unknown series")
            if seed.map_path_id not in series.map_path_ids:
                raise ValueError("planned topic seed path must belong to its series")
        for day in self.first_week:
            if not set(day.topic_seed_ids).issubset(seeds_by_id):
                raise ValueError("first-week day references an unknown planned topic seed")
        for phase in self.later_phases:
            if not set(phase.series_ids).issubset(series_by_id):
                raise ValueError("launch phase references an unknown series")
            if not set(phase.topic_seed_ids).issubset(seeds_by_id):
                raise ValueError("launch phase references an unknown planned topic seed")
        return self


def _map_path_ids(content_world_artifact: ArtifactEnvelope) -> frozenset[str]:
    path_ids: set[str] = set()
    dimensions = content_world_artifact.payload.get("dimensions", [])
    if not isinstance(dimensions, list):
        raise ValueError("candidate map dimensions must be a list")
    for dimension in dimensions:
        if not isinstance(dimension, dict):
            continue
        paths = dimension.get("paths", [])
        if not isinstance(paths, list):
            continue
        for path in paths:
            if isinstance(path, dict) and isinstance(path.get("path_id"), str):
                path_ids.add(path["path_id"])
    return frozenset(path_ids)


def seal_account_launch_plan(
    *,
    project: ProjectRef,
    logical_account: LogicalAccountRef,
    plan: AccountLaunchPlan,
    strategy_artifact: ArtifactEnvelope,
    content_world_artifact: ArtifactEnvelope,
    created_at: datetime,
    source_thread_id: str,
    source_run_id: str,
    previous_plan_artifact: ArtifactEnvelope | None = None,
) -> ArtifactEnvelope:
    plan = AccountLaunchPlan.model_validate(plan.model_dump(mode="json"))
    for artifact, artifact_type in (
        (strategy_artifact, "incubation_judgment"),
        (content_world_artifact, "content_map_candidate"),
    ):
        if artifact.project != project or artifact.artifact_type != artifact_type:
            raise ValueError(f"launch plan requires a same-project {artifact_type} parent")
        if artifact.logical_account != logical_account:
            raise ValueError("launch plan parent logical account must match plan account")

    strategy = IncubationJudgment.model_validate(strategy_artifact.payload)
    if strategy.decision_status != "confirmed":
        raise ValueError("launch plan requires a confirmed account strategy")
    if plan.strategy_artifact_id != strategy_artifact.artifact_id:
        raise ValueError("launch plan strategy id must match its exact parent")
    world_version = content_world_artifact.payload.get("content_map_version_id")
    if not isinstance(world_version, str) or world_version != plan.content_map_version_id:
        raise ValueError("launch plan content map version must match its candidate map")
    if strategy.content_map_version_id != plan.content_map_version_id:
        raise ValueError("launch plan strategy and candidate map versions must match")

    used_path_ids = {path_id for series in plan.series for path_id in series.map_path_ids} | {seed.map_path_id for seed in plan.topic_seeds}
    if not used_path_ids.issubset(_map_path_ids(content_world_artifact)):
        raise ValueError("launch plan may only reference a candidate map path supplied by its parent")

    if plan.revision_number == 1:
        if previous_plan_artifact is not None:
            raise ValueError("first launch plan revision cannot bind a previous plan")
    else:
        if previous_plan_artifact is None:
            raise ValueError("revised launch plan requires its previous plan parent")
        if previous_plan_artifact.project != project or previous_plan_artifact.artifact_type != "account_launch_plan":
            raise ValueError("previous launch plan parent is invalid")
        if previous_plan_artifact.logical_account != logical_account:
            raise ValueError("previous launch plan logical account must match")
        previous = AccountLaunchPlan.model_validate(previous_plan_artifact.payload)
        if plan.revision_number != previous.revision_number + 1:
            raise ValueError("launch plan revision must immediately follow its previous plan")
        if plan.supersedes_plan_artifact_id != previous_plan_artifact.artifact_id:
            raise ValueError("launch plan supersedes id must match its previous parent")

    parents = (
        strategy_artifact,
        content_world_artifact,
        *((previous_plan_artifact,) if previous_plan_artifact is not None else ()),
    )
    return ArtifactEnvelope.seal(
        project=project,
        artifact_type="account_launch_plan",
        version=plan.revision_number,
        payload=plan.model_dump(mode="json"),
        logical_account=logical_account,
        parents=tuple(artifact.to_parent_ref() for artifact in parents),
        created_at=created_at,
        source_thread_id=source_thread_id,
        source_run_id=source_run_id,
    )


__all__ = [
    "AccountLaunchPlan",
    "CapacityStatus",
    "ContentRole",
    "FirstWeekDay",
    "LaunchCapacity",
    "LaunchCheckpoint",
    "LaunchPhase",
    "LaunchPlanStatus",
    "LaunchSeries",
    "PlannedTopicSeed",
    "TopicSourceKind",
    "seal_account_launch_plan",
]
