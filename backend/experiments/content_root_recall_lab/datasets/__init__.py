from __future__ import annotations

import json
from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from pydantic import Field, model_validator

from deerflow.content_intelligence.contracts import ContractModel, NonEmptyStr


class RecallCohort(StrEnum):
    WORLD_TRANSFER = "world_transfer"
    LEXICALIZED_GUARD = "lexicalized_guard"


class HeldOutRecallCase(ContractModel):
    case_id: NonEmptyStr
    cohort: RecallCohort
    subject_expression: NonEmptyStr
    commercial_object: NonEmptyStr
    required_concept_groups: tuple[tuple[NonEmptyStr, ...], ...] = Field(min_length=1)
    forbidden_exact_labels: tuple[NonEmptyStr, ...] = ()
    review_rationale: NonEmptyStr

    @model_validator(mode="after")
    def validate_case(self) -> HeldOutRecallCase:
        if self.cohort is RecallCohort.LEXICALIZED_GUARD and not self.forbidden_exact_labels:
            raise ValueError("lexicalized guard cases require forbidden labels")
        return self


class HeldOutRecallDataset(ContractModel):
    dataset_id: NonEmptyStr
    status: NonEmptyStr
    annotation_status: NonEmptyStr
    cases: tuple[HeldOutRecallCase, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_dataset(self) -> HeldOutRecallDataset:
        case_ids = tuple(case.case_id for case in self.cases)
        if len(set(case_ids)) != len(case_ids):
            raise ValueError("held-out case ids must be unique")
        return self


@lru_cache(maxsize=1)
def load_held_out_cases() -> HeldOutRecallDataset:
    path = Path(__file__).with_name("held_out_v1.json")
    return HeldOutRecallDataset.model_validate(json.loads(path.read_text(encoding="utf-8")))


__all__ = [
    "HeldOutRecallCase",
    "HeldOutRecallDataset",
    "RecallCohort",
    "load_held_out_cases",
]
