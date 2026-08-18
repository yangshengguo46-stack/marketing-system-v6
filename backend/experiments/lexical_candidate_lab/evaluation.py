from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence

from deerflow.content_intelligence.contracts import ContractModel, NonEmptyStr
from experiments.lexical_candidate_lab.datasets import CandidateCohort, HeldOutCandidateCase


class CandidateRecallScore(ContractModel):
    case_id: NonEmptyStr
    cohort: CandidateCohort
    contract_success: bool
    candidate_recall: bool
    forbidden_hit: bool
    matched_accepted_alias: NonEmptyStr | None = None
    matched_forbidden_labels: tuple[NonEmptyStr, ...] = ()


def score_case(
    case: HeldOutCandidateCase,
    candidate_labels: tuple[str, ...],
    *,
    contract_success: bool = True,
) -> CandidateRecallScore:
    normalized_labels = {_normalize_label(label) for label in candidate_labels}
    matched_accepted = next(
        (alias for alias in case.accepted_aliases if _normalize_label(alias) in normalized_labels),
        None,
    )
    matched_forbidden = tuple(alias for alias in case.forbidden_exact_labels if _normalize_label(alias) in normalized_labels)
    return CandidateRecallScore(
        case_id=case.case_id,
        cohort=case.cohort,
        contract_success=contract_success,
        candidate_recall=matched_accepted is not None,
        forbidden_hit=bool(matched_forbidden),
        matched_accepted_alias=matched_accepted,
        matched_forbidden_labels=matched_forbidden,
    )


def summarize_scores(scores: Sequence[CandidateRecallScore]) -> dict[str, int]:
    transparent = tuple(score for score in scores if score.cohort is CandidateCohort.TRANSPARENT)
    guards = tuple(score for score in scores if score.cohort is CandidateCohort.GUARD)
    return {
        "case_count": len(scores),
        "transparent_case_count": len(transparent),
        "transparent_candidate_recall": sum(score.candidate_recall for score in transparent),
        "guard_case_count": len(guards),
        "guard_forbidden_hit": sum(score.forbidden_hit for score in guards),
        "contract_success": sum(score.contract_success for score in scores),
    }


def _normalize_label(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return re.sub(r"[\W_]+", "", normalized, flags=re.UNICODE)


__all__ = ["CandidateRecallScore", "score_case", "summarize_scores"]
