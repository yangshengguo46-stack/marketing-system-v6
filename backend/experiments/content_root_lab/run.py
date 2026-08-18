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
from deerflow.content_intelligence.analyzer import (
    AnalysisFocus,
    ContentIntelligenceRequest,
    analyze_content_intelligence,
)
from deerflow.models import create_chat_model
from deerflow.tools.builtins.incubation_tool_support import create_lexical_evidence_provider
from experiments.content_root_lab.contracts import ContentRootGraph
from experiments.content_root_lab.datasets import (
    HeldOutCase,
    load_development_preferences,
    load_held_out_cases,
)
from experiments.content_root_lab.evaluation import score_case
from experiments.content_root_lab.lab import (
    generate_candidate_graph,
    select_content_root,
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
        return _CountingStructuredRunnable(
            self,
            self._model.with_structured_output(*args, **kwargs),
        )

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


async def _run_baseline_case(case: HeldOutCase, model_name: str) -> dict[str, Any]:
    model = _CountingModel(_create_model(model_name))
    started = time.perf_counter()
    try:
        bundle = await analyze_content_intelligence(
            ContentIntelligenceRequest(
                user_request=case.subject_expression,
                subject_expression=case.subject_expression,
                focus=AnalysisFocus.CONTENT_WORLD,
            ),
            model=model,
            runnable_config=None,
            lexical_evidence_provider=create_lexical_evidence_provider(),
        )
        world = bundle.content_world
        selected_label = world.content_root if world is not None else None
        candidate_labels = tuple(candidate.label for candidate in world.root_candidates) if world is not None else ()
        return {
            "case_id": case.case_id,
            "status": "succeeded",
            "selected_label": selected_label,
            "candidate_labels": candidate_labels,
            "root_rationale": world.root_rationale if world is not None else None,
            "model_calls": model.calls,
            "usage": model.usage,
            "duration_seconds": round(time.perf_counter() - started, 3),
            "automatic_score": score_case(
                case=case,
                candidate_labels=candidate_labels,
                selected_label=selected_label,
            ).model_dump(mode="json"),
        }
    except Exception as exc:
        return _error_case(case, exc, model, started)


async def _run_relation_graph_case(
    case: HeldOutCase,
    model_name: str,
) -> tuple[dict[str, Any], ContentRootGraph | None]:
    model = _CountingModel(_create_model(model_name))
    started = time.perf_counter()
    try:
        graph = await generate_candidate_graph(case.subject_expression, model=model)
        selection = await select_content_root(graph, model=model)
        selected = next(candidate for candidate in graph.candidates if candidate.candidate_id == selection.selected_candidate_id)
        candidate_labels = tuple(candidate.label for candidate in graph.candidates)
        return (
            {
                "case_id": case.case_id,
                "status": "succeeded",
                "selected_label": selected.label,
                "candidate_labels": candidate_labels,
                "graph": graph.model_dump(mode="json"),
                "graph_id": graph.graph_id(),
                "selection": selection.model_dump(mode="json"),
                "model_calls": model.calls,
                "usage": model.usage,
                "duration_seconds": round(time.perf_counter() - started, 3),
                "automatic_score": score_case(
                    case=case,
                    candidate_labels=candidate_labels,
                    selected_label=selected.label,
                ).model_dump(mode="json"),
            },
            graph,
        )
    except Exception as exc:
        return _error_case(case, exc, model, started), None


async def _run_dspy_arm(
    *,
    cases: tuple[HeldOutCase, ...],
    graphs: dict[str, ContentRootGraph],
    model_name: str,
) -> dict[str, Any]:
    from experiments.content_root_lab.dspy_selector import (
        compile_dspy_selector,
        run_dspy_selector,
    )

    started = time.perf_counter()
    try:
        compiled = await asyncio.to_thread(
            compile_dspy_selector,
            model_name=model_name,
            development_examples=load_development_preferences().examples,
        )
    except Exception as exc:
        return {
            "status": "compile_failed",
            "error_type": type(exc).__name__,
            "error": str(exc)[:800],
            "duration_seconds": round(time.perf_counter() - started, 3),
            "cases": [],
        }

    results: list[dict[str, Any]] = []
    for case in cases:
        graph = graphs.get(case.case_id)
        if graph is None:
            results.append(
                {
                    "case_id": case.case_id,
                    "status": "skipped_missing_graph",
                }
            )
            continue
        case_started = time.perf_counter()
        try:
            selection = await asyncio.to_thread(run_dspy_selector, compiled, graph)
            selected = next(candidate for candidate in graph.candidates if candidate.candidate_id == selection.selected_candidate_id)
            candidate_labels = tuple(candidate.label for candidate in graph.candidates)
            results.append(
                {
                    "case_id": case.case_id,
                    "status": "succeeded",
                    "selected_candidate_id": selection.selected_candidate_id,
                    "selected_label": selected.label,
                    "rationale": selection.rationale,
                    "inference_calls": selection.inference_calls,
                    "usage": selection.inference_usage,
                    "duration_seconds": round(time.perf_counter() - case_started, 3),
                    "automatic_score": score_case(
                        case=case,
                        candidate_labels=candidate_labels,
                        selected_label=selected.label,
                    ).model_dump(mode="json"),
                }
            )
        except Exception as exc:
            results.append(
                {
                    "case_id": case.case_id,
                    "status": "failed",
                    "error_type": type(exc).__name__,
                    "error": str(exc)[:800],
                    "duration_seconds": round(time.perf_counter() - case_started, 3),
                }
            )
    return {
        "status": "completed",
        "compiled_state_sha256": compiled.state_sha256,
        "compile_calls": compiled.compile_calls,
        "compile_usage": compiled.compile_usage,
        "duration_seconds": round(time.perf_counter() - started, 3),
        "cases": results,
        "summary": _summarize(results),
    }


async def run_experiment(
    *,
    model_name: str,
    include_baseline: bool,
    include_dspy: bool,
) -> dict[str, Any]:
    held_out = load_held_out_cases()
    cases = held_out.cases
    started_at = datetime.now(UTC)

    baseline_results: list[dict[str, Any]] = []
    if include_baseline:
        for case in cases:
            baseline_results.append(await _run_baseline_case(case, model_name))

    graph_results: list[dict[str, Any]] = []
    graphs: dict[str, ContentRootGraph] = {}
    for case in cases:
        result, graph = await _run_relation_graph_case(case, model_name)
        graph_results.append(result)
        if graph is not None:
            graphs[case.case_id] = graph

    dspy_result: dict[str, Any] | None = None
    if include_dspy:
        dspy_result = await _run_dspy_arm(
            cases=cases,
            graphs=graphs,
            model_name=model_name,
        )

    return {
        "schema_version": "content-root-lab-receipt-v1",
        "experiment_id": "A84-content-root-lab-v1",
        "dataset_id": held_out.dataset_id,
        "dataset_status": held_out.status,
        "git_commit": _git_commit(),
        "model_name": model_name,
        "thinking_enabled": False,
        "temperature": 0,
        "network_evidence_enabled": False,
        "started_at": started_at.isoformat(),
        "completed_at": datetime.now(UTC).isoformat(),
        "arms": {
            "production_baseline": {
                "status": "completed" if include_baseline else "skipped",
                "cases": baseline_results,
                "summary": _summarize(baseline_results),
            },
            "relation_candidate_graph": {
                "status": "completed",
                "cases": graph_results,
                "summary": _summarize(graph_results),
            },
            "dspy_compiled_selector": dspy_result or {"status": "skipped"},
        },
        "manual_review_status": "pending",
        "promotion_status": "offline_only",
    }


def _error_case(
    case: HeldOutCase,
    exc: Exception,
    model: _CountingModel,
    started: float,
) -> dict[str, Any]:
    return {
        "case_id": case.case_id,
        "status": "failed",
        "error_type": type(exc).__name__,
        "error": str(exc)[:800],
        "model_calls": model.calls,
        "usage": model.usage,
        "duration_seconds": round(time.perf_counter() - started, 3),
    }


def _summarize(results: list[dict[str, Any]]) -> dict[str, int]:
    scores = [item["automatic_score"] for item in results if isinstance(item.get("automatic_score"), dict)]
    return {
        "case_count": len(results),
        "succeeded": sum(item.get("status") == "succeeded" for item in results),
        "candidate_recall": sum(bool(score.get("candidate_recall")) for score in scores),
        "final_acceptance": sum(bool(score.get("final_acceptance")) for score in scores),
        "selected_rejected_label": sum(bool(score.get("selected_rejected_label")) for score in scores),
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
    return root / "docs" / "content-intelligence-v6" / "evidence" / f"content-root-lab-a84-{date}.json"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the isolated A84 content-root comparison.")
    parser.add_argument("--model", default="glm-5-2-260617")
    parser.add_argument("--skip-baseline", action="store_true")
    parser.add_argument("--skip-dspy", action="store_true")
    parser.add_argument("--output", type=Path, default=_default_output_path())
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    receipt = asyncio.run(
        run_experiment(
            model_name=args.model,
            include_baseline=not args.skip_baseline,
            include_dspy=not args.skip_dspy,
        )
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(args.output)
    print(json.dumps({name: arm.get("summary", {}) for name, arm in receipt["arms"].items()}, ensure_ascii=False))


if __name__ == "__main__":
    main()
