from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

TaskClass = Literal[
    "greeting",
    "research",
    "account_strategy",
    "creative_delivery",
    "reversible_execution",
    "irreversible_external_action",
]


class AgentCoreCase(BaseModel):
    model_config = ConfigDict(frozen=True)

    case_id: str
    task_class: TaskClass
    prompt: str


class AgentCoreDataset(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: Literal["agent-core-prompt-dataset-v1"]
    dataset_id: str
    status: Literal["frozen_before_live_run"]
    cases: tuple[AgentCoreCase, ...]


class CoreModelRequestObservation(BaseModel):
    model_config = ConfigDict(frozen=True)

    arm: str
    call_index: int
    base_system_hash: str
    final_system_hash: str
    base_system_bytes: int
    final_system_bytes: int
    tool_names: tuple[str, ...]
    tool_schema_hash: str
    model_class: str
    model_contract_hash: str
    message_count: int


class AgentCoreAnswerScore(BaseModel):
    model_config = ConfigDict(frozen=True)

    task_ownership: int = Field(ge=0, le=2)
    action_or_work_product: int = Field(ge=0, le=2)
    completion: int = Field(ge=0, le=2)
    truth_boundary: int = Field(ge=0, le=2)
    approval_boundary: int = Field(ge=0, le=2)
    operator_posture: int = Field(ge=0, le=2)
    business_quality: int = Field(ge=0, le=2)
    major_issues: tuple[str, ...] = ()

    @property
    def total(self) -> int:
        return self.task_ownership + self.action_or_work_product + self.completion + self.truth_boundary + self.approval_boundary + self.operator_posture + self.business_quality


class PairwiseAgentCoreJudgeRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    answer_a: AgentCoreAnswerScore
    answer_b: AgentCoreAnswerScore
    preferred: Literal["A", "B", "tie"]
    reason: str
