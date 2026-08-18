from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from deerflow.content_intelligence.contracts import ContractModel, NonEmptyStr
from deerflow.content_intelligence.lexical_evidence import LexicalEvidenceSource


class CandidateBasis(StrEnum):
    LITERAL_EXPRESSION = "literal_expression"
    LEXICAL_EVIDENCE = "lexical_evidence"
    COMMONSENSE_HYPOTHESIS = "commonsense_hypothesis"


class CandidateRecallItem(ContractModel):
    label: NonEmptyStr
    candidate_kind: NonEmptyStr
    relation_from_object: NonEmptyStr | None = None
    basis: CandidateBasis
    support_terms: tuple[NonEmptyStr, ...] = ()

    @model_validator(mode="after")
    def validate_basis(self) -> CandidateRecallItem:
        if self.basis is CandidateBasis.LEXICAL_EVIDENCE and not self.support_terms:
            raise ValueError("lexical evidence candidates require support terms")
        if self.basis is not CandidateBasis.LEXICAL_EVIDENCE and self.support_terms:
            raise ValueError("only lexical evidence candidates may cite support terms")
        return self


class CandidateRecallDraft(ContractModel):
    commercial_object: NonEmptyStr
    candidates: tuple[CandidateRecallItem, ...] = Field(min_length=1, max_length=8)
    unknowns: tuple[NonEmptyStr, ...] = ()

    @model_validator(mode="after")
    def validate_candidates(self) -> CandidateRecallDraft:
        labels = tuple(_normalize_label(candidate.label) for candidate in self.candidates)
        if len(set(labels)) != len(labels):
            raise ValueError("candidate labels must be unique")
        return self


class CandidateRecallRecord(ContractModel):
    schema_version: Literal["lexical-candidate-recall-v1"] = "lexical-candidate-recall-v1"
    subject_expression: NonEmptyStr
    commercial_object: NonEmptyStr
    candidates: tuple[CandidateRecallItem, ...]
    unknowns: tuple[NonEmptyStr, ...] = ()
    lexical_evidence_used: bool
    lexical_evidence_source: LexicalEvidenceSource | None = None
    lexical_payload_sha256: NonEmptyStr | None = None
    selected_candidate_id: None = None


def bind_candidate_record(
    *,
    subject_expression: str,
    commercial_object: str,
    draft: CandidateRecallDraft,
    allowed_lexical_terms: set[str],
    lexical_evidence_used: bool,
    lexical_evidence_source: LexicalEvidenceSource | None = None,
    lexical_payload: dict | None = None,
) -> CandidateRecallRecord:
    if draft.commercial_object != commercial_object:
        raise ValueError("draft commercial object must match the frozen input")

    object_key = _normalize_label(commercial_object)
    object_candidates = [candidate for candidate in draft.candidates if _normalize_label(candidate.label) == object_key]
    if len(object_candidates) != 1:
        raise ValueError("exactly one commercial object candidate is required")
    object_candidate = object_candidates[0]
    if object_candidate.basis is not CandidateBasis.LITERAL_EXPRESSION or object_candidate.relation_from_object is not None:
        raise ValueError("commercial object candidate must preserve the literal expression")

    normalized_allowed_terms = {_normalize_label(term) for term in allowed_lexical_terms}
    for candidate in draft.candidates:
        if candidate is not object_candidate and candidate.relation_from_object is None:
            raise ValueError("non-object candidates require a relation from the commercial object")
        if candidate.basis is CandidateBasis.LEXICAL_EVIDENCE:
            if not lexical_evidence_used:
                raise ValueError("lexical evidence cannot be cited when the arm has no evidence")
            unsupported = [term for term in candidate.support_terms if _normalize_label(term) not in normalized_allowed_terms]
            if unsupported:
                raise ValueError("unbound lexical evidence term")

    payload_sha256 = None
    if lexical_payload is not None:
        serialized = json.dumps(lexical_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        payload_sha256 = hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    return CandidateRecallRecord(
        subject_expression=subject_expression.strip(),
        commercial_object=commercial_object,
        candidates=draft.candidates,
        unknowns=draft.unknowns,
        lexical_evidence_used=lexical_evidence_used,
        lexical_evidence_source=lexical_evidence_source if lexical_evidence_used else None,
        lexical_payload_sha256=payload_sha256 if lexical_evidence_used else None,
    )


def _normalize_label(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return re.sub(r"[\W_]+", "", normalized, flags=re.UNICODE)


__all__ = [
    "CandidateBasis",
    "CandidateRecallDraft",
    "CandidateRecallItem",
    "CandidateRecallRecord",
    "bind_candidate_record",
]
