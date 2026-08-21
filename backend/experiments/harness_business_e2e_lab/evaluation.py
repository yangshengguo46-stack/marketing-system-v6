from __future__ import annotations

import math

from pydantic import BaseModel, ConfigDict


class FullAgentCaseComparison(BaseModel):
    model_config = ConfigDict(frozen=True)

    case_id: str
    split: str
    baseline_score: int
    candidate_score: int
    preferred_arm: str
    baseline_fact_boundary_pass: bool
    candidate_fact_boundary_pass: bool
    initial_tools_match: bool
    initial_tool_schema_match: bool
    base_system_match: bool
    model_contract_match: bool
    baseline_valid: bool
    candidate_valid: bool
    judge_valid: bool


class FullAgentPromotionDecision(BaseModel):
    model_config = ConfigDict(frozen=True)

    promote: bool
    held_out_case_count: int
    candidate_wins: int
    mean_score_gain: float
    reasons: tuple[str, ...]


def decide_full_agent_promotion(
    comparisons: list[FullAgentCaseComparison],
) -> FullAgentPromotionDecision:
    held_out = [item for item in comparisons if item.split == "held_out"]
    reasons: list[str] = []
    if len(held_out) < 6:
        reasons.append("insufficient_held_out_cases")
    if any(not item.initial_tools_match for item in held_out):
        reasons.append("tool_contract_mismatch")
    if any(not item.initial_tool_schema_match for item in held_out):
        reasons.append("tool_schema_contract_mismatch")
    if any(not item.base_system_match for item in held_out):
        reasons.append("base_prompt_mismatch")
    if any(not item.model_contract_match for item in held_out):
        reasons.append("model_contract_mismatch")
    if any(not item.baseline_valid or not item.candidate_valid for item in held_out):
        reasons.append("invalid_agent_run")
    if any(not item.judge_valid for item in held_out):
        reasons.append("judge_failed")

    candidate_wins = sum(item.preferred_arm == "focused_business" for item in held_out)
    mean_gain = sum(item.candidate_score - item.baseline_score for item in held_out) / len(held_out) if held_out else 0.0
    if held_out and candidate_wins < math.ceil(len(held_out) * 0.625):
        reasons.append("insufficient_candidate_wins")
    if held_out and mean_gain < 1.5:
        reasons.append("insufficient_mean_gain")
    if any(item.baseline_fact_boundary_pass and not item.candidate_fact_boundary_pass for item in held_out):
        reasons.append("fact_boundary_regression")
    if any(item.candidate_score < item.baseline_score - 2 for item in held_out):
        reasons.append("material_case_regression")

    return FullAgentPromotionDecision(
        promote=bool(held_out) and not reasons,
        held_out_case_count=len(held_out),
        candidate_wins=candidate_wins,
        mean_score_gain=round(mean_gain, 3),
        reasons=tuple(dict.fromkeys(reasons)),
    )
