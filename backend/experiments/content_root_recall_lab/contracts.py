from __future__ import annotations

import hashlib
import re
import unicodedata
from enum import StrEnum
from typing import Literal

from pydantic import Field

from deerflow.content_intelligence.contracts import ContractModel, NonEmptyStr


class ReaderKind(StrEnum):
    DETERMINISTIC_INPUT = "deterministic_input"
    OPEN_RECALL = "open_recall"
    OBJECT_ACTIVITY = "object_activity"
    HUMAN_PRACTICE = "human_practice"


class SemanticPathStepDraft(ContractModel):
    source: NonEmptyStr
    relation: NonEmptyStr
    target: NonEmptyStr


class CandidateDraft(ContractModel):
    label: NonEmptyStr
    semantic_path: tuple[SemanticPathStepDraft, ...] = Field(min_length=1, max_length=4)
    complete_world_reason: NonEmptyStr
    limitations: tuple[NonEmptyStr, ...] = ()


class CandidateWorkerDraft(ContractModel):
    candidates: tuple[CandidateDraft, ...] = Field(default=(), max_length=6)
    unknowns: tuple[NonEmptyStr, ...] = ()


class RecallCandidate(ContractModel):
    candidate_id: NonEmptyStr
    label: NonEmptyStr
    semantic_path: tuple[SemanticPathStepDraft, ...]
    complete_world_reason: NonEmptyStr
    limitations: tuple[NonEmptyStr, ...] = ()
    source_readers: tuple[ReaderKind, ...] = Field(min_length=1)


class ContentRootRecallRecord(ContractModel):
    schema_version: Literal["content-root-recall-v1"] = "content-root-recall-v1"
    subject_expression: NonEmptyStr
    commercial_object: NonEmptyStr
    candidates: tuple[RecallCandidate, ...] = Field(min_length=1, max_length=10)
    unknowns: tuple[NonEmptyStr, ...] = ()
    truncated: bool = False


def bind_recall_record(
    *,
    subject_expression: str,
    commercial_object: str,
    worker_drafts: tuple[tuple[ReaderKind, CandidateWorkerDraft], ...],
    max_candidates: int = 10,
) -> ContentRootRecallRecord:
    if not 1 <= max_candidates <= 10:
        raise ValueError("max_candidates must be between one and ten")

    object_key = _normalize_label(commercial_object)
    ordered: list[tuple[ReaderKind, CandidateDraft]] = []
    max_worker_length = max((len(draft.candidates) for _, draft in worker_drafts), default=0)
    for index in range(max_worker_length):
        for reader_kind, draft in worker_drafts:
            if index >= len(draft.candidates):
                continue
            candidate = draft.candidates[index]
            _validate_path(candidate, commercial_object=commercial_object)
            if _normalize_label(candidate.label) == object_key:
                continue
            ordered.append((reader_kind, candidate))

    deduplicated: dict[str, tuple[CandidateDraft, list[ReaderKind]]] = {}
    for reader_kind, candidate in ordered:
        key = _normalize_label(candidate.label)
        existing = deduplicated.get(key)
        if existing is None:
            deduplicated[key] = (candidate, [reader_kind])
        elif reader_kind not in existing[1]:
            existing[1].append(reader_kind)

    bound = [
        RecallCandidate(
            candidate_id=_candidate_id(commercial_object, commercial_object),
            label=commercial_object,
            semantic_path=(),
            complete_world_reason="用户输入中已冻结的商业对象。",
            source_readers=(ReaderKind.DETERMINISTIC_INPUT,),
        )
    ]
    for candidate, readers in deduplicated.values():
        bound.append(
            RecallCandidate(
                candidate_id=_candidate_id(commercial_object, candidate.label),
                label=candidate.label,
                semantic_path=candidate.semantic_path,
                complete_world_reason=candidate.complete_world_reason,
                limitations=candidate.limitations,
                source_readers=tuple(readers),
            )
        )

    unknowns = _deduplicate(unknown for _, draft in worker_drafts for unknown in draft.unknowns)
    return ContentRootRecallRecord(
        subject_expression=subject_expression,
        commercial_object=commercial_object,
        candidates=tuple(bound[:max_candidates]),
        unknowns=unknowns,
        truncated=len(bound) > max_candidates,
    )


def _validate_path(candidate: CandidateDraft, *, commercial_object: str) -> None:
    path = candidate.semantic_path
    if path[0].source != commercial_object:
        raise ValueError("semantic path must start at the frozen commercial object")
    for previous, current in zip(path, path[1:], strict=False):
        if previous.target != current.source:
            raise ValueError("semantic path steps must be connected")
    if path[-1].target != candidate.label:
        raise ValueError("semantic path must end at the candidate label")


def _candidate_id(commercial_object: str, label: str) -> str:
    payload = f"{commercial_object}\0{label}".encode()
    return "root-candidate-" + hashlib.sha256(payload).hexdigest()[:16]


def _normalize_label(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return re.sub(r"[\W_]+", "", normalized, flags=re.UNICODE)


def _deduplicate(values: object) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip()
        key = _normalize_label(text)
        if key and key not in seen:
            seen.add(key)
            result.append(text)
    return tuple(result)


__all__ = [
    "CandidateDraft",
    "CandidateWorkerDraft",
    "ContentRootRecallRecord",
    "ReaderKind",
    "RecallCandidate",
    "SemanticPathStepDraft",
    "bind_recall_record",
]
