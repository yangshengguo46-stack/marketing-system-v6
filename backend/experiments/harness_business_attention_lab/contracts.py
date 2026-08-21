from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class BusinessAttentionCase(BaseModel):
    model_config = ConfigDict(frozen=True)

    case_id: str
    split: Literal["diagnostic", "held_out"]
    prompt: str


class BusinessAttentionDataset(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: Literal["harness-business-attention-dataset-v1"]
    dataset_id: str
    status: Literal["frozen_before_live_run"]
    cases: tuple[BusinessAttentionCase, ...]


class PromptManifest(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: Literal["prompt-manifest-v1"] = "prompt-manifest-v1"
    arm: str
    section_bytes: dict[str, int]
    section_hashes: dict[str, str]
    total_bytes: int
    estimated_tokens: int


class BlindPair(BaseModel):
    model_config = ConfigDict(frozen=True)

    case_id: str
    answer_a: str
    answer_b: str
    arm_by_label: dict[Literal["A", "B"], str]
    judge_payload: str


class BusinessAnswerScore(BaseModel):
    model_config = ConfigDict(frozen=True)

    business_comprehension: int = Field(ge=0, le=2)
    audience_logic: int = Field(ge=0, le=2)
    durable_content_world: int = Field(ge=0, le=2)
    distinctive_viewpoint: int = Field(ge=0, le=2)
    business_return_path: int = Field(ge=0, le=2)
    fact_boundary: int = Field(ge=0, le=2)
    major_issues: tuple[str, ...] = ()

    @property
    def total(self) -> int:
        return self.business_comprehension + self.audience_logic + self.durable_content_world + self.distinctive_viewpoint + self.business_return_path + self.fact_boundary

    @property
    def fact_boundary_pass(self) -> bool:
        return self.fact_boundary >= 1


class PairwiseBusinessJudgeRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    answer_a: BusinessAnswerScore
    answer_b: BusinessAnswerScore
    preferred: Literal["A", "B", "tie"]
    reason: str
