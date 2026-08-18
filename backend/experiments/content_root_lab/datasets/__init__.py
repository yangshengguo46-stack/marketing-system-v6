from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from pydantic import Field, model_validator

from deerflow.content_intelligence.contracts import ContractModel, NonEmptyStr


class PreferenceCandidate(ContractModel):
    candidate_id: NonEmptyStr
    label: NonEmptyStr
    candidate_kind: NonEmptyStr


class DevelopmentPreference(ContractModel):
    case_id: NonEmptyStr
    subject_expression: NonEmptyStr
    candidates: tuple[PreferenceCandidate, ...] = Field(min_length=2)
    preferred_candidate_id: NonEmptyStr
    preference_reason: NonEmptyStr

    @model_validator(mode="after")
    def validate_preference(self) -> DevelopmentPreference:
        candidate_ids = tuple(item.candidate_id for item in self.candidates)
        if len(set(candidate_ids)) != len(candidate_ids):
            raise ValueError("development candidate ids must be unique")
        if self.preferred_candidate_id not in set(candidate_ids):
            raise ValueError("preferred candidate must exist in the development candidates")
        return self


class DevelopmentDataset(ContractModel):
    dataset_id: NonEmptyStr
    status: NonEmptyStr
    examples: tuple[DevelopmentPreference, ...]


class HeldOutCase(ContractModel):
    case_id: NonEmptyStr
    subject_expression: NonEmptyStr
    accepted_aliases: tuple[NonEmptyStr, ...] = Field(min_length=1)
    rejected_exact_labels: tuple[NonEmptyStr, ...] = ()
    review_rationale: NonEmptyStr


class HeldOutDataset(ContractModel):
    dataset_id: NonEmptyStr
    status: NonEmptyStr
    cases: tuple[HeldOutCase, ...]


@lru_cache(maxsize=1)
def load_development_preferences() -> DevelopmentDataset:
    return DevelopmentDataset.model_validate(_load_json("development_v1.json"))


@lru_cache(maxsize=1)
def load_held_out_cases() -> HeldOutDataset:
    return HeldOutDataset.model_validate(_load_json("held_out_v1.json"))


def _load_json(filename: str) -> dict:
    path = Path(__file__).with_name(filename)
    return json.loads(path.read_text(encoding="utf-8"))


__all__ = [
    "DevelopmentDataset",
    "DevelopmentPreference",
    "HeldOutCase",
    "HeldOutDataset",
    "PreferenceCandidate",
    "load_development_preferences",
    "load_held_out_cases",
]
