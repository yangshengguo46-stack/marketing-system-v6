from __future__ import annotations

import re
import unicodedata

from deerflow.content_intelligence.contracts import ContractModel, NonEmptyStr
from experiments.content_root_lab.datasets import HeldOutCase


class AutomaticCaseScore(ContractModel):
    case_id: NonEmptyStr
    candidate_recall: bool
    final_acceptance: bool
    selected_rejected_label: bool
    matched_candidate_alias: NonEmptyStr | None = None
    matched_selected_alias: NonEmptyStr | None = None


def score_case(
    *,
    case: HeldOutCase,
    candidate_labels: tuple[str, ...],
    selected_label: str | None,
) -> AutomaticCaseScore:
    matched_candidate = _first_matching_alias(candidate_labels, case.accepted_aliases)
    matched_selected = _first_matching_alias(
        (selected_label,) if selected_label is not None else (),
        case.accepted_aliases,
    )
    selected_rejected = _first_matching_alias(
        (selected_label,) if selected_label is not None else (),
        case.rejected_exact_labels,
    )
    return AutomaticCaseScore(
        case_id=case.case_id,
        candidate_recall=matched_candidate is not None,
        final_acceptance=matched_selected is not None,
        selected_rejected_label=selected_rejected is not None,
        matched_candidate_alias=matched_candidate,
        matched_selected_alias=matched_selected,
    )


def normalize_label(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return re.sub(r"[\W_]+", "", normalized, flags=re.UNICODE)


def _first_matching_alias(
    labels: tuple[str | None, ...],
    aliases: tuple[str, ...],
) -> str | None:
    normalized_aliases = {normalize_label(alias): alias for alias in aliases}
    for label in labels:
        if label is None:
            continue
        alias = normalized_aliases.get(normalize_label(label))
        if alias is not None:
            return alias
    return None


__all__ = ["AutomaticCaseScore", "normalize_label", "score_case"]
