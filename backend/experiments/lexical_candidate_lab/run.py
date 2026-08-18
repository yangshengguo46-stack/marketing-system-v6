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

from deerflow.config.app_config import get_app_config
from deerflow.content_intelligence.lexical_evidence import (
    LexicalEvidence,
    LexicalEvidenceMode,
)
from deerflow.models import create_chat_model
from deerflow.tools.builtins.incubation_tool_support import create_lexical_evidence_provider
from experiments.lexical_candidate_lab.datasets import HeldOutCandidateCase, load_held_out_cases
from experiments.lexical_candidate_lab.evaluation import CandidateRecallScore, score_case, summarize_scores
from experiments.lexical_candidate_lab.lab import (
    build_dictionary_only_record,
    generate_candidate_record,
    render_candidate_input,
)


class _CountingStructuredRunnable:
    def __init__(self, owner: _CountingModel, runnable: Any) -> None:
        self._owner = owner
        self._runnable = runnable

    async def ainvoke(self, *args: Any, **kwargs: Any) -> Any:
        result = await self._runnable.ainvoke(*args, **kwargs)
        self._owner.calls += 1
        self._owner.record_usage(result)
        return result


class _CountingModel:
    def __init__(self, model: Any) -> None:
        self._model = model
        self.calls = 0
        self.usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}

    def with_structured_output(self, *args: Any, **kwargs: Any) -> _CountingStructuredRunnable:
        return _CountingStructuredRunnable(self, self._model.with_structured_output(*args, **kwargs))

    def record_usage(self, result: Any) -> None:
        raw = result.get("raw") if isinstance(result, Mapping) else result
        usage = getattr(raw, "usage_metadata", None)
        if not isinstance(usage, Mapping):
            response_metadata = getattr(raw, "response_metadata", None)
            if isinstance(response_metadata, Mapping):
                usage = response_metadata.get("token_usage") or response_metadata.get("usage")
        if not isinstance(usage, Mapping):
            return
        input_tokens = int(usage.get("input_tokens", usage.get("prompt_tokens", 0)) or 0)
        output_tokens = int(usage.get("output_tokens", usage.get("completion_tokens", 0)) or 0)
        total_tokens = int(usage.get("total_tokens", input_tokens + output_tokens) or 0)
        self.usage["input_tokens"] += input_tokens
        self.usage["output_tokens"] += output_tokens
        self.usage["total_tokens"] += total_tokens


def _create_model(model_name: str) -> Any:
    return create_chat_model(
        name=model_name,
        thinking_enabled=False,
        app_config=get_app_config(),
        attach_tracing=False,
        model_overrides={"temperature": 0},
    )


async def _run_model_case(
    case: HeldOutCandidateCase,
    *,
    model_name: str,
    lexical_evidence: LexicalEvidence | None,
) -> dict[str, Any]:
    model = _CountingModel(_create_model(model_name))
    started = time.perf_counter()
    try:
        record = await generate_candidate_record(
            subject_expression=case.subject_expression,
            commercial_object=case.commercial_object,
            model=model,
            lexical_evidence=lexical_evidence,
        )
        labels = tuple(candidate.label for candidate in record.candidates)
        score = score_case(case, labels)
        rendered_input = render_candidate_input(
            subject_expression=case.subject_expression,
            commercial_object=case.commercial_object,
            lexical_evidence=lexical_evidence,
        )
        return {
            "case_id": case.case_id,
            "status": "succeeded",
            "record": record.model_dump(mode="json"),
            "model_calls": model.calls,
            "usage": model.usage,
            "input_bytes": len(rendered_input.encode("utf-8")),
            "duration_seconds": round(time.perf_counter() - started, 3),
            "automatic_score": score.model_dump(mode="json"),
        }
    except Exception as exc:
        return {
            "case_id": case.case_id,
            "status": "failed",
            "error_type": type(exc).__name__,
            "error": str(exc)[:800],
            "model_calls": model.calls,
            "usage": model.usage,
            "duration_seconds": round(time.perf_counter() - started, 3),
            "automatic_score": score_case(
                case,
                (),
                contract_success=False,
            ).model_dump(mode="json"),
        }


def _run_dictionary_case(
    case: HeldOutCandidateCase,
    lexical_evidence: LexicalEvidence,
) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        record = build_dictionary_only_record(
            subject_expression=case.subject_expression,
            commercial_object=case.commercial_object,
            lexical_evidence=lexical_evidence,
        )
        labels = tuple(candidate.label for candidate in record.candidates)
        return {
            "case_id": case.case_id,
            "status": "succeeded",
            "record": record.model_dump(mode="json"),
            "model_calls": 0,
            "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
            "duration_seconds": round(time.perf_counter() - started, 3),
            "automatic_score": score_case(case, labels).model_dump(mode="json"),
        }
    except Exception as exc:
        return {
            "case_id": case.case_id,
            "status": "failed",
            "error_type": type(exc).__name__,
            "error": str(exc)[:800],
            "model_calls": 0,
            "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
            "duration_seconds": round(time.perf_counter() - started, 3),
            "automatic_score": score_case(
                case,
                (),
                contract_success=False,
            ).model_dump(mode="json"),
        }


async def run_experiment(*, model_name: str) -> dict[str, Any]:
    provider = create_lexical_evidence_provider()
    if provider is None:
        raise RuntimeError("A86 requires the existing local CC-CEDICT index")
    dataset = load_held_out_cases()
    started_at = datetime.now(UTC)

    dictionary_results: list[dict[str, Any]] = []
    model_only_results: list[dict[str, Any]] = []
    evidence_results: list[dict[str, Any]] = []
    for case in dataset.cases:
        evidence = await provider.lookup(case.commercial_object, mode=LexicalEvidenceMode.RELATIONS)
        dictionary_results.append(_run_dictionary_case(case, evidence))
        model_only_results.append(await _run_model_case(case, model_name=model_name, lexical_evidence=None))
        evidence_results.append(await _run_model_case(case, model_name=model_name, lexical_evidence=evidence))

    return {
        "schema_version": "lexical-candidate-lab-receipt-v1",
        "experiment_id": "A86-lexical-candidate-recall-v1",
        "dataset_id": dataset.dataset_id,
        "dataset_status": dataset.status,
        "git_commit": _git_commit(),
        "model_name": model_name,
        "thinking_enabled": False,
        "temperature": 0,
        "network_evidence_enabled": False,
        "lexical_source": provider.source.model_dump(mode="json"),
        "started_at": started_at.isoformat(),
        "completed_at": datetime.now(UTC).isoformat(),
        "arms": {
            "dictionary_only": _arm_receipt(dictionary_results),
            "model_only": _arm_receipt(model_only_results),
            "model_with_cedict": _arm_receipt(evidence_results),
        },
        "manual_review_status": "pending",
        "promotion_status": "offline_only",
    }


def _arm_receipt(results: list[dict[str, Any]]) -> dict[str, Any]:
    scores = tuple(CandidateRecallScore.model_validate(result["automatic_score"]) for result in results)
    return {
        "status": "completed",
        "cases": results,
        "summary": summarize_scores(scores),
        "model_calls": sum(int(result.get("model_calls", 0)) for result in results),
        "usage": {key: sum(int(result.get("usage", {}).get(key, 0)) for result in results) for key in ("input_tokens", "output_tokens", "total_tokens")},
        "duration_seconds": round(
            sum(float(result.get("duration_seconds", 0.0)) for result in results),
            3,
        ),
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


def _default_output_path() -> Path:
    root = Path(__file__).parents[3]
    date = datetime.now(UTC).date().isoformat()
    return root / "docs" / "content-intelligence-v6" / "evidence" / f"lexical-candidate-a86-{date}.json"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the isolated A86 lexical candidate comparison.")
    parser.add_argument("--model", default="glm-5-2-260617")
    parser.add_argument("--output", type=Path, default=_default_output_path())
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    receipt = asyncio.run(run_experiment(model_name=args.model))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(args.output)


if __name__ == "__main__":
    main()
