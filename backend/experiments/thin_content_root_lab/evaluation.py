from __future__ import annotations

from collections.abc import Sequence

from deerflow.content_intelligence.contracts import ContractModel, NonEmptyStr
from experiments.thin_content_root_lab.contracts import normalize_label
from experiments.thin_content_root_lab.datasets import HeldOutRootCase, RootCohort


class ThinRootCaseScore(ContractModel):
    case_id: NonEmptyStr
    cohort: RootCohort
    required_group_count: int
    recalled_group_count: int
    complete_recall: bool
    forbidden_hit: bool
    matched_group_aliases: tuple[NonEmptyStr, ...] = ()
    matched_candidate_labels: tuple[NonEmptyStr, ...] = ()
    matched_forbidden_fragments: tuple[NonEmptyStr, ...] = ()
    contract_success: bool
    candidate_count: int


def score_case(
    case: HeldOutRootCase,
    candidate_labels: Sequence[str],
    *,
    contract_success: bool = True,
) -> ThinRootCaseScore:
    labels = tuple(candidate_labels)
    normalized_labels = tuple(normalize_label(label) for label in labels)
    matches = _maximum_distinct_matches(case.required_concept_groups, labels, normalized_labels)
    matched_forbidden = tuple(fragment for fragment in case.forbidden_label_fragments if any(normalize_label(fragment) in label for label in normalized_labels))
    return ThinRootCaseScore(
        case_id=case.case_id,
        cohort=case.cohort,
        required_group_count=len(case.required_concept_groups),
        recalled_group_count=len(matches),
        complete_recall=len(matches) == len(case.required_concept_groups),
        forbidden_hit=bool(matched_forbidden),
        matched_group_aliases=tuple(match[1] for match in matches),
        matched_candidate_labels=tuple(match[2] for match in matches),
        matched_forbidden_fragments=matched_forbidden,
        contract_success=contract_success,
        candidate_count=len(labels),
    )


def summarize_scores(scores: Sequence[ThinRootCaseScore]) -> dict[str, int]:
    guards = tuple(score for score in scores if score.cohort is RootCohort.LEXICALIZED_GUARD)
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


def _maximum_distinct_matches(
    groups: tuple[tuple[str, ...], ...],
    labels: tuple[str, ...],
    normalized_labels: tuple[str, ...],
) -> tuple[tuple[int, str, str], ...]:
    options: tuple[tuple[tuple[int, str], ...], ...] = tuple(
        tuple((candidate_index, alias) for candidate_index, normalized_label in enumerate(normalized_labels) for alias in aliases if normalize_label(alias) in normalized_label) for aliases in groups
    )
    best: tuple[tuple[int, str, str], ...] = ()

    def visit(
        group_index: int,
        used_candidates: frozenset[int],
        selected: tuple[tuple[int, str, str], ...],
    ) -> None:
        nonlocal best
        if group_index == len(groups):
            if len(selected) > len(best):
                best = selected
            return
        visit(group_index + 1, used_candidates, selected)
        for candidate_index, alias in options[group_index]:
            if candidate_index in used_candidates:
                continue
            visit(
                group_index + 1,
                used_candidates | {candidate_index},
                selected + ((group_index, alias, labels[candidate_index]),),
            )

    visit(0, frozenset(), ())
    return tuple(sorted(best, key=lambda match: match[0]))


__all__ = ["ThinRootCaseScore", "score_case", "summarize_scores"]
