from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from typing import Literal

from pydantic import Field, model_validator

from deerflow.content_intelligence.contracts import ContractModel, NonEmptyStr


class CandidateItemDraft(ContractModel):
    label: NonEmptyStr
    candidate_kind: NonEmptyStr
    relation_from_object: NonEmptyStr | None = None


class CandidateDraft(ContractModel):
    commercial_object: NonEmptyStr
    candidates: tuple[CandidateItemDraft, ...] = Field(min_length=1, max_length=8)
    unknowns: tuple[NonEmptyStr, ...] = ()

    @model_validator(mode="after")
    def validate_candidates(self) -> CandidateDraft:
        labels = tuple(_normalize_label(candidate.label) for candidate in self.candidates)
        if len(set(labels)) != len(labels):
            raise ValueError("candidate labels must be unique")
        return self


class CandidateRecord(ContractModel):
    schema_version: Literal["compact-lexical-candidate-v1"] = "compact-lexical-candidate-v1"
    subject_expression: NonEmptyStr
    commercial_object: NonEmptyStr
    candidates: tuple[CandidateItemDraft, ...]
    unknowns: tuple[NonEmptyStr, ...] = ()
    lexical_evidence_used: bool
    lexical_source: dict[str, str] | None = None
    lexical_payload_sha256: NonEmptyStr | None = None
    selected_candidate_id: None = None


def bind_candidate_record(
    *,
    subject_expression: str,
    commercial_object: str,
    draft: CandidateDraft,
    lexical_projection: dict | None,
) -> CandidateRecord:
    if draft.commercial_object != commercial_object:
        raise ValueError("draft commercial object must match the frozen input")

    object_key = _normalize_label(commercial_object)
    object_candidates = [candidate for candidate in draft.candidates if _normalize_label(candidate.label) == object_key]
    if len(object_candidates) != 1:
        raise ValueError("exactly one commercial object candidate is required")
    object_candidate = object_candidates[0]
    if object_candidate.relation_from_object is not None:
        raise ValueError("commercial object candidate must have no relation from itself")
    for candidate in draft.candidates:
        if candidate is not object_candidate and candidate.relation_from_object is None:
            raise ValueError("non-object candidates require a relation from the commercial object")

    payload_sha256 = None
    lexical_source = None
    if lexical_projection is not None:
        serialized = json.dumps(
            lexical_projection,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        payload_sha256 = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
        raw_source = lexical_projection.get("source")
        if isinstance(raw_source, dict):
            lexical_source = {str(key): str(value) for key, value in raw_source.items()}

    return CandidateRecord(
        subject_expression=subject_expression.strip(),
        commercial_object=commercial_object,
        candidates=draft.candidates,
        unknowns=draft.unknowns,
        lexical_evidence_used=lexical_projection is not None,
        lexical_source=lexical_source,
        lexical_payload_sha256=payload_sha256,
    )


def _normalize_label(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return re.sub(r"[\W_]+", "", normalized, flags=re.UNICODE)


__all__ = [
    "CandidateDraft",
    "CandidateItemDraft",
    "CandidateRecord",
    "bind_candidate_record",
]
