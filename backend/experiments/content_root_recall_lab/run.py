from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import time
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from deerflow.config.app_config import get_app_config
from deerflow.models import create_chat_model
from experiments.content_root_recall_lab.contracts import ReaderKind
from experiments.content_root_recall_lab.datasets import HeldOutRecallCase, load_held_out_cases
from experiments.content_root_recall_lab.evaluation import RecallCaseScore, score_case, summarize_scores
from experiments.content_root_recall_lab.lab import (
    generate_open_recall,
    generate_parallel_recall,
    render_worker_messages,
)

_MAX_MODEL_INPUT_BYTES = 4_096


class _CountingStructuredRunnable:
    def __init__(self, owner: _CountingModel, runnable: Any) -> None:
        self._owner = owner
        self._runnable = runnable

    async def ainvoke(self, *args: Any, **kwargs: Any) -> Any:
        self._owner.calls += 1
        result = await self._runnable.ainvoke(*args, **kwargs)
        self._owner.record_usage(result)
        return result


class _CountingModel:
    def __init__(self, model: Any) -> None:
        self._model = model
        self.calls = 0
        self.usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}

    def with_structured_output(self, *args: Any, **kwargs: Any) -> _CountingStructuredRunnable:
        runnable = self._model.with_structured_output(*args, **kwargs)
        return _CountingStructuredRunnable(self, runnable)

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


def preflight_cases(cases: Sequence[HeldOutRecallCase]) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    reader_kinds = (
        ReaderKind.OPEN_RECALL,
        ReaderKind.OBJECT_ACTIVITY,
        ReaderKind.HUMAN_PRACTICE,
    )
    for case in cases:
        for reader_kind in reader_kinds:
            messages = render_worker_messages(
                reader_kind=reader_kind,
                subject_expression=case.subject_expression,
                commercial_object=case.commercial_object,
            )
            input_bytes = sum(len(str(message.content).encode("utf-8")) for message in messages)
            checks.append(
                {
                    "case_id": case.case_id,
                    "reader_kind": reader_kind.value,
                    "input_bytes": input_bytes,
                    "model_calls": 0,
                }
            )
    return {
        "case_count": len(cases),
        "message_count": len(checks),
        "all_within_budget": len(checks) == len(cases) * len(reader_kinds) and all(item["input_bytes"] <= _MAX_MODEL_INPUT_BYTES for item in checks),
        "max_input_bytes": max((item["input_bytes"] for item in checks), default=0),
        "model_calls": 0,
        "messages": checks,
    }


async def _run_baseline_case(case: HeldOutRecallCase, *, model_name: str) -> dict[str, Any]:
    model = _CountingModel(_create_model(model_name))
    started = time.perf_counter()
    try:
        record = await generate_open_recall(
            subject_expression=case.subject_expression,
            commercial_object=case.commercial_object,
            model=model,
        )
        return _success_result(case, record, (model,), started=started)
    except Exception as exc:
        return _failure_result(case, exc, (model,), started=started)


async def _run_parallel_case(case: HeldOutRecallCase, *, model_name: str) -> dict[str, Any]:
    object_model = _CountingModel(_create_model(model_name))
    practice_model = _CountingModel(_create_model(model_name))
    models = {
        ReaderKind.OBJECT_ACTIVITY: object_model,
        ReaderKind.HUMAN_PRACTICE: practice_model,
    }
    started = time.perf_counter()
    try:
        record = await generate_parallel_recall(
            subject_expression=case.subject_expression,
            commercial_object=case.commercial_object,
            models=models,
        )
        return _success_result(case, record, tuple(models.values()), started=started)
    except Exception as exc:
        return _failure_result(case, exc, tuple(models.values()), started=started)


def _success_result(
    case: HeldOutRecallCase,
    record: Any,
    models: tuple[_CountingModel, ...],
    *,
    started: float,
) -> dict[str, Any]:
    labels = tuple(candidate.label for candidate in record.candidates)
    return {
        "case_id": case.case_id,
        "status": "succeeded",
        "record": record.model_dump(mode="json"),
        "model_calls": sum(model.calls for model in models),
        "usage": _sum_usage(models),
        "duration_seconds": round(time.perf_counter() - started, 3),
        "automatic_score": score_case(case, labels).model_dump(mode="json"),
    }


def _failure_result(
    case: HeldOutRecallCase,
    exc: Exception,
    models: tuple[_CountingModel, ...],
    *,
    started: float,
) -> dict[str, Any]:
    return {
        "case_id": case.case_id,
        "status": "failed",
        "error_type": type(exc).__name__,
        "error": str(exc)[:800],
        "model_calls": sum(model.calls for model in models),
        "usage": _sum_usage(models),
        "duration_seconds": round(time.perf_counter() - started, 3),
        "automatic_score": score_case(case, (), contract_success=False).model_dump(mode="json"),
    }


def _sum_usage(models: tuple[_CountingModel, ...]) -> dict[str, int]:
    return {key: sum(model.usage[key] for model in models) for key in ("input_tokens", "output_tokens", "total_tokens")}


async def run_experiment(*, model_name: str) -> dict[str, Any]:
    dataset = load_held_out_cases()
    preflight = preflight_cases(dataset.cases)
    if not preflight["all_within_budget"]:
        raise RuntimeError("A90 preflight failed before model invocation")

    started_at = datetime.now(UTC)
    baseline_results: list[dict[str, Any]] = []
    parallel_results: list[dict[str, Any]] = []
    for case in dataset.cases:
        baseline_results.append(await _run_baseline_case(case, model_name=model_name))
        parallel_results.append(await _run_parallel_case(case, model_name=model_name))

    return {
        "schema_version": "content-root-recall-receipt-v1",
        "experiment_id": "A90-split-attention-content-root-recall-v1",
        "dataset_id": dataset.dataset_id,
        "dataset_status": dataset.status,
        "annotation_status": dataset.annotation_status,
        "git_commit": _git_commit(),
        "model_name": model_name,
        "thinking_enabled": False,
        "temperature": 0,
        "network_evidence_enabled": False,
        "dictionary_evidence_enabled": False,
        "preflight": preflight,
        "started_at": started_at.isoformat(),
        "completed_at": datetime.now(UTC).isoformat(),
        "arms": {
            "single_open_recall": _arm_receipt(baseline_results),
            "parallel_split_attention": _arm_receipt(parallel_results),
        },
        "manual_review_status": "pending",
        "promotion_status": "offline_only",
    }


def _arm_receipt(results: list[dict[str, Any]]) -> dict[str, Any]:
    scores = tuple(RecallCaseScore.model_validate(result["automatic_score"]) for result in results)
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
    return root / "docs" / "content-intelligence-v6" / "evidence" / f"content-root-recall-a90-{date}.json"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the isolated A90 content-root recall comparison.")
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
