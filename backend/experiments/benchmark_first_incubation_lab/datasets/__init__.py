from __future__ import annotations

import json
from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from pydantic import Field, model_validator

from deerflow.content_intelligence.contracts import ContractModel, NonEmptyStr


class BenchmarkCaseCohort(StrEnum):
    EMOTION_AND_RITUAL = "emotion_and_ritual"
    MEMORY_AND_CRAFT = "memory_and_craft"
    FAMILY_SERVICE = "family_service"
    ORGANIZATIONAL_SERVICE = "organizational_service"
    B2B_CONDITIONAL_IP = "b2b_conditional_ip"
    PRODUCT_AND_ACTIVITY = "product_and_activity"
    LEXICALIZED_GUARD = "lexicalized_guard"


class BenchmarkIncubationCase(ContractModel):
    case_id: NonEmptyStr
    cohort: BenchmarkCaseCohort
    subject_expression: NonEmptyStr
    commercial_object: NonEmptyStr


class BenchmarkIncubationDataset(ContractModel):
    dataset_id: NonEmptyStr
    status: NonEmptyStr
    annotation_status: NonEmptyStr
    cases: tuple[BenchmarkIncubationCase, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_cases(self) -> BenchmarkIncubationDataset:
        case_ids = tuple(case.case_id for case in self.cases)
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("benchmark incubation case ids must be unique")
        return self


@lru_cache(maxsize=1)
def load_held_out_cases() -> BenchmarkIncubationDataset:
    path = Path(__file__).with_name("held_out_v1.json")
    return BenchmarkIncubationDataset.model_validate(json.loads(path.read_text(encoding="utf-8")))


class BenchmarkReviewLabel(ContractModel):
    case_id: NonEmptyStr
    review_focus: NonEmptyStr
    fatal_drift_fragments: tuple[NonEmptyStr, ...] = ()


class BenchmarkReviewLabels(ContractModel):
    dataset_id: NonEmptyStr
    case_labels: tuple[BenchmarkReviewLabel, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_labels(self) -> BenchmarkReviewLabels:
        case_ids = tuple(label.case_id for label in self.case_labels)
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("benchmark review case ids must be unique")
        return self

    def for_case(self, case_id: str) -> BenchmarkReviewLabel:
        try:
            return next(label for label in self.case_labels if label.case_id == case_id)
        except StopIteration as exc:
            raise KeyError(f"missing review label for case {case_id}") from exc


@lru_cache(maxsize=1)
def load_review_labels() -> BenchmarkReviewLabels:
    path = Path(__file__).with_name("review_labels_v1.json")
    labels = BenchmarkReviewLabels.model_validate(json.loads(path.read_text(encoding="utf-8")))
    case_ids = {case.case_id for case in load_held_out_cases().cases}
    label_ids = {label.case_id for label in labels.case_labels}
    if case_ids != label_ids:
        raise ValueError("held-out cases and sealed review labels must have identical case ids")
    return labels


__all__ = [
    "BenchmarkCaseCohort",
    "BenchmarkIncubationCase",
    "BenchmarkIncubationDataset",
    "BenchmarkReviewLabel",
    "BenchmarkReviewLabels",
    "load_held_out_cases",
    "load_review_labels",
]
