from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence

from deerflow.content_intelligence.contracts import ContractModel, NonEmptyStr
from experiments.content_root_recall_lab.datasets import HeldOutRecallCase, RecallCohort


class RecallCaseScore(ContractModel):
    case_id: NonEmptyStr
    cohort: RecallCohort
    required_group_count: int
    recalled_group_count: int
    complete_recall: bool
    forbidden_hit: bool
    matched_group_aliases: tuple[NonEmptyStr, ...] = ()
    matched_forbidden_labels: tuple[NonEmptyStr, ...] = ()
    contract_success: bool
    candidate_count: int


def score_case(
    case: HeldOutRecallCase,
    candidate_labels: Sequence[str],
    *,
    contract_success: bool = True,
) -> RecallCaseScore:
    normalized_labels = {_normalize_label(label) for label in candidate_labels}
    matched_groups = tuple(match for aliases in case.required_concept_groups if (match := next((alias for alias in aliases if _normalize_label(alias) in normalized_labels), None)) is not None)
    matched_forbidden = tuple(label for label in case.forbidden_exact_labels if _normalize_label(label) in normalized_labels)
    return RecallCaseScore(
        case_id=case.case_id,
        cohort=case.cohort,
        required_group_count=len(case.required_concept_groups),
        recalled_group_count=len(matched_groups),
        complete_recall=len(matched_groups) == len(case.required_concept_groups),
        forbidden_hit=bool(matched_forbidden),
        matched_group_aliases=matched_groups,
        matched_forbidden_labels=matched_forbidden,
        contract_success=contract_success,
        candidate_count=len(candidate_labels),
    )


def summarize_scores(scores: Sequence[RecallCaseScore]) -> dict[str, int]:
    guards = tuple(score for score in scores if score.cohort is RecallCohort.LEXICALIZED_GUARD)
    return {
        "case_count": len(scores),
        "required_group_count": sum(score.required_group_count for score in scores),
        "recalled_group_count": sum(score.recalled_group_count for score in scores),
        "complete_case_recall": sum(score.complete_recall for score in scores),
        "guard_case_count": len(guards),
        "guard_forbidden_hit": sum(score.forbidden_hit for score in guards),
        "contract_success": sum(score.contract_success for score in scores),
        "candidate_count": sum(score.candidate_count for score in scores),
    }


def _normalize_label(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return re.sub(r"[\W_]+", "", normalized, flags=re.UNICODE)


__all__ = ["RecallCaseScore", "score_case", "summarize_scores"]
