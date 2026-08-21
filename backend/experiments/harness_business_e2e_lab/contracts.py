from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class FullAgentBusinessCase(BaseModel):
    model_config = ConfigDict(frozen=True)

    case_id: str
    split: Literal["diagnostic", "held_out"]
    prompt: str


class FullAgentBusinessDataset(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: Literal["harness-business-e2e-dataset-v1"]
    dataset_id: str
    status: Literal["frozen_before_live_run"]
    cases: tuple[FullAgentBusinessCase, ...]


class ModelRequestObservation(BaseModel):
    model_config = ConfigDict(frozen=True)

    arm: str
    call_index: int
    base_system_hash: str
    final_system_hash: str
    base_system_bytes: int
    final_system_bytes: int
    attention_hash: str | None
    tool_names: tuple[str, ...]
    tool_schema_hash: str
    model_class: str
    model_contract_hash: str
    message_count: int


class TokenUsage(BaseModel):
    model_config = ConfigDict(frozen=True)

    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0


class CollectedAgentStream(BaseModel):
    model_config = ConfigDict(frozen=True)

    answer: str
    answer_source: Literal["assistant", "clarification", "none"]
    tool_calls: tuple[str, ...]
    tool_result_count: int
    tool_failure_count: int
    usage: TokenUsage
    repetitive: bool
    valid: bool
    termination_reason: Literal["completed", "clarification", "repetitive", "empty"]


class FullAgentBusinessScore(BaseModel):
    model_config = ConfigDict(frozen=True)

    business_comprehension: int = Field(ge=0, le=2)
    audience_behavior_chain: int = Field(ge=0, le=2)
    durable_content_world: int = Field(ge=0, le=2)
    distinctive_viewpoint: int = Field(ge=0, le=2)
    concrete_direction: int = Field(ge=0, le=2)
    business_return_path: int = Field(ge=0, le=2)
    fact_boundary: int = Field(ge=0, le=2)
    major_issues: tuple[str, ...] = ()

    @property
    def total(self) -> int:
        return self.business_comprehension + self.audience_behavior_chain + self.durable_content_world + self.distinctive_viewpoint + self.concrete_direction + self.business_return_path + self.fact_boundary

    @property
    def fact_boundary_pass(self) -> bool:
        return self.fact_boundary >= 1


class PairwiseFullAgentJudgeRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    answer_a: FullAgentBusinessScore
    answer_b: FullAgentBusinessScore
    preferred: Literal["A", "B", "tie"]
    reason: str
