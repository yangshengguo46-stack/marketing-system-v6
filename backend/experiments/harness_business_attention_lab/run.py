from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import time
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from deerflow.agents.lead_agent.prompt import apply_prompt_template, get_enabled_skills_for_config
from deerflow.config.app_config import get_app_config
from deerflow.models import create_chat_model
from experiments.harness_business_attention_lab.contracts import (
    BusinessAttentionCase,
    PairwiseBusinessJudgeRecord,
)
from experiments.harness_business_attention_lab.datasets import load_business_attention_cases
from experiments.harness_business_attention_lab.evaluation import (
    JUDGE_SYSTEM_PROMPT,
    CaseComparison,
    decide_business_attention_promotion,
)
from experiments.harness_business_attention_lab.lab import (
    build_blind_pair,
    build_business_attention_section,
    build_minimal_host_prompt,
    build_prompt_manifest,
)

_ARM_CURRENT = "current_full"
_ARM_MINIMAL = "minimal_host"
_ARM_FOCUSED = "focused_business"
_ARMS = (_ARM_CURRENT, _ARM_MINIMAL, _ARM_FOCUSED)


def _create_model(model_name: str, *, thinking_enabled: bool) -> Any:
    return create_chat_model(
        name=model_name,
        thinking_enabled=thinking_enabled,
        app_config=get_app_config(),
        attach_tracing=False,
        model_overrides={"temperature": 0},
    )


def _current_full_prompt() -> str:
    app_config = get_app_config()
    enabled_skills = get_enabled_skills_for_config(app_config)
    skill_names = frozenset(skill.name for skill in enabled_skills)
    return apply_prompt_template(
        subagent_enabled=False,
        app_config=app_config,
        skill_names=skill_names or None,
    )


def _prompt_sections() -> dict[str, tuple[tuple[str, str], ...]]:
    return {
        _ARM_CURRENT: (("current_full", _current_full_prompt()),),
        _ARM_MINIMAL: (("minimal_host", build_minimal_host_prompt()),),
        _ARM_FOCUSED: (
            ("minimal_host", build_minimal_host_prompt()),
            ("business_attention", build_business_attention_section()),
        ),
    }


def _render_system_prompt(sections: tuple[tuple[str, str], ...]) -> str:
    return "\n\n".join(text for _, text in sections)


def _message_text(message: AIMessage) -> str:
    content = message.content
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, Mapping):
                text = item.get("text") or item.get("content")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(part.strip() for part in parts if part.strip()).strip()
    return str(content).strip()


def _usage(message: AIMessage) -> dict[str, int]:
    usage = message.usage_metadata
    if not isinstance(usage, Mapping):
        metadata = message.response_metadata
        if isinstance(metadata, Mapping):
            usage = metadata.get("token_usage") or metadata.get("usage")
    if not isinstance(usage, Mapping):
        return {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    input_tokens = int(usage.get("input_tokens", usage.get("prompt_tokens", 0)) or 0)
    output_tokens = int(usage.get("output_tokens", usage.get("completion_tokens", 0)) or 0)
    total_tokens = int(usage.get("total_tokens", input_tokens + output_tokens) or 0)
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
    }


async def _run_primary(
    *,
    model: Any,
    case: BusinessAttentionCase,
    arm: str,
    sections: tuple[tuple[str, str], ...],
) -> dict[str, Any]:
    started = time.perf_counter()
    manifest = build_prompt_manifest(arm=arm, sections=sections, user_prompt=case.prompt)
    try:
        response = await model.ainvoke(
            [
                SystemMessage(content=_render_system_prompt(sections)),
                HumanMessage(content=case.prompt),
            ]
        )
        if not isinstance(response, AIMessage):
            raise TypeError(f"expected AIMessage, got {type(response).__name__}")
        answer = _message_text(response)
        if not answer:
            raise ValueError("model returned an empty answer")
        return {
            "status": "succeeded",
            "answer": answer,
            "usage": _usage(response),
            "duration_seconds": round(time.perf_counter() - started, 3),
            "prompt_manifest": manifest.model_dump(mode="json"),
        }
    except Exception as exc:
        return {
            "status": "failed",
            "error_type": type(exc).__name__,
            "error": str(exc)[:800],
            "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
            "duration_seconds": round(time.perf_counter() - started, 3),
            "prompt_manifest": manifest.model_dump(mode="json"),
        }


async def _run_judge(
    *,
    judge_model: Any,
    case: BusinessAttentionCase,
    baseline: dict[str, Any],
    candidate: dict[str, Any],
) -> tuple[dict[str, Any], CaseComparison | None]:
    if baseline.get("status") != "succeeded" or candidate.get("status") != "succeeded":
        return (
            {
                "status": "skipped",
                "reason": "primary_arm_failed",
            },
            None,
        )

    pair = build_blind_pair(
        case_id=case.case_id,
        left_arm=_ARM_CURRENT,
        left_text=str(baseline["answer"]),
        right_arm=_ARM_FOCUSED,
        right_text=str(candidate["answer"]),
    )
    prompt = f"<user_request>\n{case.prompt}\n</user_request>\n\n{pair.judge_payload}"
    started = time.perf_counter()
    try:
        runnable = judge_model.with_structured_output(PairwiseBusinessJudgeRecord, include_raw=True)
        result = await runnable.ainvoke(
            [
                SystemMessage(content=JUDGE_SYSTEM_PROMPT),
                HumanMessage(content=prompt),
            ]
        )
        parsed = result.get("parsed") if isinstance(result, Mapping) else result
        if not isinstance(parsed, PairwiseBusinessJudgeRecord):
            raise ValueError("judge returned no parsed record")
        score_by_label = {"A": parsed.answer_a, "B": parsed.answer_b}
        baseline_label = next(label for label, arm in pair.arm_by_label.items() if arm == _ARM_CURRENT)
        candidate_label = next(label for label, arm in pair.arm_by_label.items() if arm == _ARM_FOCUSED)
        preferred_arm = "tie" if parsed.preferred == "tie" else pair.arm_by_label[parsed.preferred]
        baseline_score = score_by_label[baseline_label]
        candidate_score = score_by_label[candidate_label]
        raw = result.get("raw") if isinstance(result, Mapping) else None
        comparison = CaseComparison(
            case_id=case.case_id,
            split=case.split,
            baseline_score=baseline_score.total,
            candidate_score=candidate_score.total,
            preferred_arm=preferred_arm,
            baseline_fact_boundary_pass=baseline_score.fact_boundary_pass,
            candidate_fact_boundary_pass=candidate_score.fact_boundary_pass,
        )
        return (
            {
                "status": "succeeded",
                "arm_by_label": pair.arm_by_label,
                "record": parsed.model_dump(mode="json"),
                "usage": _usage(raw) if isinstance(raw, AIMessage) else {},
                "duration_seconds": round(time.perf_counter() - started, 3),
            },
            comparison,
        )
    except Exception as exc:
        return (
            {
                "status": "failed",
                "error_type": type(exc).__name__,
                "error": str(exc)[:800],
                "duration_seconds": round(time.perf_counter() - started, 3),
            },
            None,
        )


def preflight() -> dict[str, Any]:
    dataset = load_business_attention_cases()
    sections_by_arm = _prompt_sections()
    checks = []
    for case in dataset.cases:
        checks.append(
            {
                "case_id": case.case_id,
                "split": case.split,
                "manifests": {arm: build_prompt_manifest(arm=arm, sections=sections_by_arm[arm], user_prompt=case.prompt).model_dump(mode="json") for arm in _ARMS},
            }
        )
    focused_bytes = len(_render_system_prompt(sections_by_arm[_ARM_FOCUSED]).encode())
    return {
        "dataset_id": dataset.dataset_id,
        "case_count": len(dataset.cases),
        "held_out_count": sum(case.split == "held_out" for case in dataset.cases),
        "diagnostic_count": sum(case.split == "diagnostic" for case in dataset.cases),
        "focused_prompt_within_budget": focused_bytes <= 4_096,
        "focused_prompt_bytes": focused_bytes,
        "checks": checks,
    }


async def run_experiment(*, model_name: str) -> dict[str, Any]:
    dataset = load_business_attention_cases()
    preflight_receipt = preflight()
    if preflight_receipt["held_out_count"] < 6 or not preflight_receipt["focused_prompt_within_budget"]:
        raise RuntimeError("business attention preflight failed before model invocation")

    sections_by_arm = _prompt_sections()
    primary_model = _create_model(model_name, thinking_enabled=True)
    judge_model = _create_model(model_name, thinking_enabled=False)
    started_at = datetime.now(UTC)
    case_receipts: list[dict[str, Any]] = []
    comparisons: list[CaseComparison] = []

    for case in dataset.cases:
        arms: dict[str, dict[str, Any]] = {}
        for arm in _ARMS:
            arms[arm] = await _run_primary(
                model=primary_model,
                case=case,
                arm=arm,
                sections=sections_by_arm[arm],
            )
        judge, comparison = await _run_judge(
            judge_model=judge_model,
            case=case,
            baseline=arms[_ARM_CURRENT],
            candidate=arms[_ARM_FOCUSED],
        )
        if comparison is not None:
            comparisons.append(comparison)
        case_receipts.append(
            {
                "case_id": case.case_id,
                "split": case.split,
                "prompt": case.prompt,
                "arms": arms,
                "judge": judge,
                "comparison": comparison.model_dump(mode="json") if comparison is not None else None,
            }
        )

    promotion = decide_business_attention_promotion(comparisons)
    return {
        "schema_version": "harness-business-attention-receipt-v1",
        "experiment_id": "A130-harness-business-attention-v1",
        "dataset_id": dataset.dataset_id,
        "dataset_status": dataset.status,
        "git_commit": _git_commit(),
        "model_name": model_name,
        "primary_thinking_enabled": True,
        "judge_thinking_enabled": False,
        "temperature": 0,
        "tools_enabled": False,
        "network_enabled": False,
        "preflight": preflight_receipt,
        "started_at": started_at.isoformat(),
        "completed_at": datetime.now(UTC).isoformat(),
        "cases": case_receipts,
        "comparisons": [item.model_dump(mode="json") for item in comparisons],
        "promotion": promotion.model_dump(mode="json"),
        "manual_review_status": "pending",
        "runtime_promotion_status": "full_deerflow_e2e_required" if promotion.promote else "not_eligible",
    }


def _git_commit() -> str:
    root = Path(__file__).parents[3]
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the isolated Harness business-attention comparison.")
    parser.add_argument("--model", default="glm-5-2-260617")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--preflight", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    receipt = preflight() if args.preflight else asyncio.run(run_experiment(model_name=args.model))
    rendered = json.dumps(receipt, ensure_ascii=False, indent=2)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(f"{rendered}\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
