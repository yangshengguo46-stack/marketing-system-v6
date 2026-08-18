from __future__ import annotations

import json
import unicodedata
from collections.abc import Mapping
from typing import Any

from experiments.benchmark_first_incubation_lab.contracts import (
    BlindCandidateScore,
    CommonRouteDraft,
)
from experiments.benchmark_first_incubation_lab.datasets import BenchmarkReviewLabel


def detect_fatal_drift(
    review_label: BenchmarkReviewLabel,
    route: CommonRouteDraft,
) -> tuple[str, ...]:
    rendered = json.dumps(route.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
    normalized = unicodedata.normalize("NFKC", rendered).casefold()
    return tuple(fragment for fragment in review_label.fatal_drift_fragments if unicodedata.normalize("NFKC", fragment).casefold() in normalized)


def core_score(score: BlindCandidateScore) -> int:
    return score.business_relevance + score.long_term_coherence + score.differentiation_and_transfer + score.shootability


def is_usable_route(score: BlindCandidateScore, *, fatal_drift: tuple[str, ...]) -> bool:
    return score.total >= 9 and not score.fatal_issues and not fatal_drift


def decide_pilot(
    *,
    arm_scores: Mapping[str, Mapping[str, BlindCandidateScore]],
    fatal_drifts: Mapping[str, Mapping[str, tuple[str, ...]]],
) -> dict[str, Any]:
    b_usable = 0
    c_usable = 0
    b_non_inferior = 0
    c_wins = 0
    cases: list[dict[str, Any]] = []
    for case_id, scores in arm_scores.items():
        score_b = scores["B"]
        score_c = scores["C"]
        usable_b = is_usable_route(score_b, fatal_drift=fatal_drifts.get(case_id, {}).get("B", ()))
        usable_c = is_usable_route(score_c, fatal_drift=fatal_drifts.get(case_id, {}).get("C", ()))
        b_usable += int(usable_b)
        c_usable += int(usable_c)
        c_case_win = core_score(score_c) > core_score(score_b) and score_c.shootability >= score_b.shootability
        b_case_non_inferior = core_score(score_b) >= core_score(score_c)
        c_wins += int(c_case_win)
        b_non_inferior += int(b_case_non_inferior)
        cases.append(
            {
                "case_id": case_id,
                "b_usable": usable_b,
                "c_usable": usable_c,
                "b_core_score": core_score(score_b),
                "c_core_score": core_score(score_c),
                "b_non_inferior": b_case_non_inferior,
                "c_win": c_case_win,
            }
        )

    if c_usable >= 5 and c_wins >= 4:
        decision = "thin_world_advances_to_real_account_validation"
    elif b_usable >= 5 and b_non_inferior >= 5:
        decision = "explicit_thin_world_gain_not_demonstrated"
    else:
        decision = "inconclusive"
    return {
        "decision": decision,
        "b_usable": b_usable,
        "c_usable": c_usable,
        "b_non_inferior": b_non_inferior,
        "c_wins": c_wins,
        "cases": cases,
    }


__all__ = ["core_score", "decide_pilot", "detect_fatal_drift", "is_usable_route"]
