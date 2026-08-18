from __future__ import annotations

import json
from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from pydantic import Field, model_validator

from deerflow.content_intelligence.contracts import ContractModel, NonEmptyStr


class CandidateCohort(StrEnum):
    TRANSPARENT = "transparent"
    GUARD = "guard"


class HeldOutCandidateCase(ContractModel):
    case_id: NonEmptyStr
    cohort: CandidateCohort
    subject_expression: NonEmptyStr
    commercial_object: NonEmptyStr
    accepted_aliases: tuple[NonEmptyStr, ...] = Field(min_length=1)
    forbidden_exact_labels: tuple[NonEmptyStr, ...] = ()
    review_rationale: NonEmptyStr

    @model_validator(mode="after")
    def validate_case(self) -> HeldOutCandidateCase:
        if self.cohort is CandidateCohort.GUARD and not self.forbidden_exact_labels:
            raise ValueError("guard cases require forbidden labels")
        return self


class HeldOutCandidateDataset(ContractModel):
    dataset_id: NonEmptyStr
    status: NonEmptyStr
    cases: tuple[HeldOutCandidateCase, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_dataset(self) -> HeldOutCandidateDataset:
        case_ids = tuple(case.case_id for case in self.cases)
        if len(set(case_ids)) != len(case_ids):
            raise ValueError("held-out case ids must be unique")
        return self


@lru_cache(maxsize=1)
def load_held_out_cases() -> HeldOutCandidateDataset:
    path = Path(__file__).with_name("held_out_v1.json")
    return HeldOutCandidateDataset.model_validate(json.loads(path.read_text(encoding="utf-8")))


__all__ = [
    "CandidateCohort",
    "HeldOutCandidateCase",
    "HeldOutCandidateDataset",
    "load_held_out_cases",
]
