from __future__ import annotations

import hashlib
import re
import unicodedata
from typing import Annotated, Literal

from pydantic import Field, model_validator

from deerflow.content_intelligence.contracts import ContractModel, NonEmptyStr

CandidateLabel = Annotated[str, Field(min_length=1, max_length=40)]
BoundedReason = Annotated[str, Field(min_length=1, max_length=180)]


class RootCandidateDraft(ContractModel):
    label: CandidateLabel
    relation_to_business: BoundedReason
    long_term_capacity: BoundedReason
    boundary: BoundedReason


class ThinRootDraft(ContractModel):
    candidates: tuple[RootCandidateDraft, ...] = Field(default=(), max_length=5)
    unknowns: tuple[NonEmptyStr, ...] = Field(default=(), max_length=5)

    @model_validator(mode="after")
    def validate_unique_candidates(self) -> ThinRootDraft:
        labels = tuple(_normalize_label(candidate.label) for candidate in self.candidates)
        if len(labels) != len(set(labels)):
            raise ValueError("candidate labels must be unique after normalization")
        return self


class RootCandidate(ContractModel):
    candidate_id: NonEmptyStr
    label: CandidateLabel
    relation_to_business: BoundedReason
    long_term_capacity: BoundedReason
    boundary: BoundedReason
    source: Literal["single_thin_reader"] = "single_thin_reader"


class ThinRootRecord(ContractModel):
    schema_version: Literal["thin-content-root-v1"] = "thin-content-root-v1"
    subject_expression: NonEmptyStr
    commercial_object: NonEmptyStr
    candidates: tuple[RootCandidate, ...] = Field(default=(), max_length=5)
    unknowns: tuple[NonEmptyStr, ...] = Field(default=(), max_length=5)
    discarded_commercial_object_duplicate: bool = False


def bind_thin_root_record(
    *,
    subject_expression: str,
    commercial_object: str,
    draft: ThinRootDraft,
) -> ThinRootRecord:
    object_key = _normalize_label(commercial_object)
    kept: list[RootCandidateDraft] = []
    discarded_object = False
    for candidate in draft.candidates:
        if _normalize_label(candidate.label) == object_key:
            discarded_object = True
            continue
        kept.append(candidate)

    candidates = tuple(
        RootCandidate(
            candidate_id=_candidate_id(commercial_object, candidate.label),
            label=candidate.label,
            relation_to_business=candidate.relation_to_business,
            long_term_capacity=candidate.long_term_capacity,
            boundary=candidate.boundary,
        )
        for candidate in kept
    )
    return ThinRootRecord(
        subject_expression=subject_expression,
        commercial_object=commercial_object,
        candidates=candidates,
        unknowns=draft.unknowns,
        discarded_commercial_object_duplicate=discarded_object,
    )


def _candidate_id(commercial_object: str, label: str) -> str:
    payload = f"{commercial_object}\0{label}".encode()
    return "thin-root-" + hashlib.sha256(payload).hexdigest()[:16]


def normalize_label(value: str) -> str:
    return _normalize_label(value)


def _normalize_label(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return re.sub(r"[\W_]+", "", normalized, flags=re.UNICODE)


__all__ = [
    "RootCandidate",
    "RootCandidateDraft",
    "ThinRootDraft",
    "ThinRootRecord",
    "bind_thin_root_record",
    "normalize_label",
]
