from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
import subprocess
import time
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from deerflow.config.app_config import get_app_config
from deerflow.models import create_chat_model
from experiments.benchmark_first_incubation_lab.contracts import (
    BenchmarkEvidencePack,
    BenchmarkIntermediateRecord,
    BenchmarkRouteRecord,
    BenchmarkSearchPlanDraft,
    BlindCandidateScore,
    BlindCaseReviewDraft,
    CommonRouteDraft,
    NeutralEvidenceDigestDraft,
    ThinWorldDigestDraft,
)
from experiments.benchmark_first_incubation_lab.datasets import (
    BenchmarkIncubationCase,
    load_held_out_cases,
    load_review_labels,
)
from experiments.benchmark_first_incubation_lab.evaluation import decide_pilot, detect_fatal_drift
from experiments.benchmark_first_incubation_lab.lab import (
    RepairLedger,
    blind_arm_aliases,
    generate_blind_review,
    generate_intermediate,
    generate_route,
    generate_search_plan,
    render_blind_review_messages,
    render_intermediate_messages,
    render_planner_messages,
    render_route_messages,
    structured_input_bytes,
)
from experiments.benchmark_first_incubation_lab.search import (
    SearchProvider,
    collect_shared_evidence,
    ddg_search_provider,
)

_PLANNER_INPUT_BUDGET = 4_096
_MODEL_INPUT_BUDGET = 16_000
_REVIEW_INPUT_BUDGET = 32_000


class _CountingStructuredRunnable:
    def __init__(self, owner: _CountingModel, runnable: Any) -> None:
        self._owner = owner
        self._runnable = runnable

    async def ainvoke(self, *args: Any, **kwargs: Any) -> Any:
        self._owner.calls += 1
        try:
            result = await self._runnable.ainvoke(*args, **kwargs)
        except Exception:
            self._owner.failed_calls += 1
            self._owner.usage_unreported_calls += 1
            raise
        if self._owner.record_usage(result):
            self._owner.usage_reported_calls += 1
        else:
            self._owner.usage_unreported_calls += 1
        return result


class _CountingModel:
    def __init__(self, model: Any) -> None:
        self._model = model
        self.calls = 0
        self.failed_calls = 0
        self.usage_reported_calls = 0
        self.usage_unreported_calls = 0
        self.usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}

    def with_structured_output(self, *args: Any, **kwargs: Any) -> _CountingStructuredRunnable:
        return _CountingStructuredRunnable(
            self,
            self._model.with_structured_output(*args, **kwargs),
        )

    def record_usage(self, result: Any) -> bool:
        raw = result.get("raw") if isinstance(result, Mapping) else result
        usage = getattr(raw, "usage_metadata", None)
        if not isinstance(usage, Mapping):
            response_metadata = getattr(raw, "response_metadata", None)
            if isinstance(response_metadata, Mapping):
                usage = response_metadata.get("token_usage") or response_metadata.get("usage")
        if not isinstance(usage, Mapping):
            return False
        input_tokens = int(usage.get("input_tokens", usage.get("prompt_tokens", 0)) or 0)
        output_tokens = int(usage.get("output_tokens", usage.get("completion_tokens", 0)) or 0)
        total_tokens = int(usage.get("total_tokens", input_tokens + output_tokens) or 0)
        self.usage["input_tokens"] += input_tokens
        self.usage["output_tokens"] += output_tokens
        self.usage["total_tokens"] += total_tokens
        return True


def _create_model(model_name: str) -> Any:
    return create_chat_model(
        name=model_name,
        thinking_enabled=False,
        app_config=get_app_config(),
        attach_tracing=False,
        model_overrides={"temperature": 0},
    )


def preflight_planner_cases(cases: Sequence[BenchmarkIncubationCase]) -> dict[str, Any]:
    checks = []
    for case in cases:
        budget = structured_input_bytes(
            render_planner_messages(case=case),
            BenchmarkSearchPlanDraft,
            include_repair_instruction=True,
        )
        checks.append({"case_id": case.case_id, **budget, "model_calls": 0})
    return {
        "case_count": len(cases),
        "message_count": len(checks),
        "all_within_budget": len(checks) == len(cases) and all(item["repair_input_bytes"] <= _PLANNER_INPUT_BUDGET for item in checks),
        "max_input_bytes": max((item["initial_input_bytes"] for item in checks), default=0),
        "max_repair_input_bytes": max(
            (item["repair_input_bytes"] for item in checks),
            default=0,
        ),
        "max_schema_bytes": max((item["schema_bytes"] for item in checks), default=0),
        "model_calls": 0,
        "messages": checks,
    }


def preflight_route_cases(
    cases: Sequence[BenchmarkIncubationCase],
    evidence_packs: Mapping[str, BenchmarkEvidencePack],
) -> dict[str, Any]:
    checks = []
    for case in cases:
        pack = evidence_packs[case.case_id]
        for arm in ("A", "B", "C"):
            route_budget = structured_input_bytes(
                render_route_messages(case=case, arm=arm, evidence_pack=pack),
                CommonRouteDraft,
                include_repair_instruction=True,
            )
            intermediate_budget = _empty_budget()
            if arm != "A":
                schema = NeutralEvidenceDigestDraft if arm == "B" else ThinWorldDigestDraft
                intermediate_budget = structured_input_bytes(
                    render_intermediate_messages(
                        case=case,
                        arm=arm,
                        evidence_pack=pack,
                    ),
                    schema,
                    include_repair_instruction=True,
                )
            checks.append(
                {
                    "case_id": case.case_id,
                    "arm": arm,
                    **_join_route_budgets(route_budget, intermediate_budget),
                    "model_calls": 0,
                }
            )
    return _preflight_report(cases, checks)


def preflight_actual_route_cases(
    cases: Sequence[BenchmarkIncubationCase],
    evidence_packs: Mapping[str, BenchmarkEvidencePack],
    intermediates: Mapping[str, Mapping[str, BenchmarkIntermediateRecord]],
) -> dict[str, Any]:
    checks = []
    for case in cases:
        pack = evidence_packs[case.case_id]
        for arm in ("A", "B", "C"):
            intermediate = None if arm == "A" else intermediates[arm][case.case_id]
            route_budget = structured_input_bytes(
                render_route_messages(
                    case=case,
                    arm=arm,
                    evidence_pack=pack,
                    intermediate=intermediate,
                ),
                CommonRouteDraft,
                include_repair_instruction=True,
            )
            checks.append(
                {
                    "case_id": case.case_id,
                    "arm": arm,
                    **_join_route_budgets(route_budget, _empty_budget()),
                    "model_calls": 0,
                }
            )
    return _preflight_report(cases, checks)


def automatic_evidence_preflight(
    cases: Sequence[BenchmarkIncubationCase],
    evidence_packs: Mapping[str, BenchmarkEvidencePack],
) -> dict[str, Any]:
    reports = []
    for case in cases:
        pack = evidence_packs.get(case.case_id)
        missing: list[str] = []
        coverage = []
        if pack is None:
            missing = ["direct", "demand", "mechanism"]
        else:
            for item in pack.coverage:
                ready = item.status.value == "succeeded" and item.accepted_result_count > 0
                if not ready:
                    missing.append(item.query_kind.value)
                coverage.append(
                    {
                        "query_kind": item.query_kind.value,
                        "status": item.status.value,
                        "accepted_result_count": item.accepted_result_count,
                    }
                )
        reports.append(
            {
                "case_id": case.case_id,
                "ready": not missing,
                "missing_query_kinds": missing,
                "coverage": coverage,
            }
        )
    exact_case_set = set(evidence_packs) == {case.case_id for case in cases}
    return {
        "case_count": len(cases),
        "all_cases_ready": exact_case_set and all(item["ready"] for item in reports),
        "cases": reports,
        "search_attempt_count": sum(len(pack.coverage) for pack in evidence_packs.values()),
        "model_calls": 0,
    }


def validate_evidence_review(
    review: Mapping[str, Any],
    *,
    evidence_receipt_sha256: str,
    case_ids: Sequence[str],
) -> dict[str, Any]:
    if review.get("schema_version") != "benchmark-evidence-review-v1":
        raise ValueError("unsupported evidence review schema")
    if review.get("evidence_receipt_sha256") != evidence_receipt_sha256:
        raise ValueError("evidence review hash does not match the frozen evidence receipt")
    if review.get("status") != "approved":
        raise ValueError("evidence review is not approved")
    raw_cases = review.get("cases")
    if not isinstance(raw_cases, list) or not all(isinstance(item, Mapping) for item in raw_cases):
        raise ValueError("evidence review must contain case records")
    reviewed_ids = [str(item.get("case_id", "")) for item in raw_cases]
    if len(reviewed_ids) != len(set(reviewed_ids)) or set(reviewed_ids) != set(case_ids):
        raise ValueError("evidence review must cover every frozen case exactly once")
    if not all(item.get("relevant") is True for item in raw_cases):
        raise ValueError("evidence review is not approved for every frozen case")
    return {
        "schema_version": "benchmark-evidence-review-v1",
        "evidence_receipt_sha256": evidence_receipt_sha256,
        "status": "approved",
        "cases": [
            {
                "case_id": str(item["case_id"]),
                "relevant": True,
                "notes": str(item.get("notes", ""))[:500],
            }
            for item in raw_cases
        ],
    }


async def collect_evidence_stage(
    *,
    model_name: str,
    search_provider: SearchProvider = ddg_search_provider,
) -> dict[str, Any]:
    dataset = load_held_out_cases()
    preflight = preflight_planner_cases(dataset.cases)
    if not preflight["all_within_budget"]:
        raise RuntimeError("A99 planner preflight failed before model invocation")

    model = _CountingModel(_create_model(model_name))
    repair_ledger = RepairLedger(max_repairs=2)
    planner_results: list[dict[str, Any]] = []
    plans = {}
    started_at = datetime.now(UTC)
    for case in dataset.cases:
        started = time.perf_counter()
        before = _model_snapshot(model)
        try:
            plan = await generate_search_plan(
                case=case,
                model=model,
                repair_ledger=repair_ledger,
            )
            plans[case.case_id] = plan
            planner_results.append(
                {
                    "case_id": case.case_id,
                    "status": "succeeded",
                    "plan": plan.model_dump(mode="json"),
                    **_call_receipt(model, before, started),
                }
            )
        except Exception as exc:
            planner_results.append(
                {
                    "case_id": case.case_id,
                    "status": "failed",
                    "error": _redacted_error(exc),
                    **_call_receipt(model, before, started),
                }
            )

    packs = {}
    if len(plans) == len(dataset.cases):
        for case in dataset.cases:
            packs[case.case_id] = await collect_shared_evidence(
                plan=plans[case.case_id],
                search_provider=search_provider,
            )
    evidence_preflight = automatic_evidence_preflight(dataset.cases, packs)
    return {
        "schema_version": "benchmark-evidence-stage-v1",
        "experiment_id": "A99-benchmark-first-incubation-pilot-v1",
        "stage": "evidence_collection",
        "dataset_id": dataset.dataset_id,
        "dataset_status": dataset.status,
        "git_commit": _git_commit(),
        "artifact_hashes": _artifact_hashes(),
        "model_name": model_name,
        "thinking_enabled": False,
        "temperature": 0,
        "collection_method": "public_web_benchmark_discovery",
        "official_douyin_openapi_used": False,
        "started_at": started_at.isoformat(),
        "completed_at": datetime.now(UTC).isoformat(),
        "planner_preflight": preflight,
        "planner": {
            "cases": planner_results,
            **_model_totals(model, repair_ledger, initial_call_count=len(dataset.cases)),
        },
        "evidence": {
            "packs": {case_id: pack.model_dump(mode="json") for case_id, pack in packs.items()},
            "automatic_preflight": evidence_preflight,
            "manual_relevance_review": "pending",
        },
        "route_model_calls": 0,
        "promotion_status": "offline_only",
    }


async def run_route_stage(
    *,
    model_name: str,
    evidence_receipt: Mapping[str, Any],
    evidence_receipt_sha256: str,
    evidence_review: Mapping[str, Any],
) -> dict[str, Any]:
    dataset = load_held_out_cases()
    if evidence_receipt.get("dataset_id") != dataset.dataset_id:
        raise ValueError("evidence receipt dataset does not match the frozen dataset")
    if evidence_receipt.get("git_commit") != _git_commit():
        raise ValueError("route stage must use the same clean code commit as evidence collection")
    if evidence_receipt.get("artifact_hashes") != _artifact_hashes():
        raise ValueError("experiment source, prompt, schema, or dataset hash changed after evidence collection")

    raw_packs = evidence_receipt.get("evidence", {}).get("packs", {})
    packs = {case_id: BenchmarkEvidencePack.model_validate(payload) for case_id, payload in raw_packs.items()}
    evidence_preflight = automatic_evidence_preflight(dataset.cases, packs)
    if not evidence_preflight["all_cases_ready"]:
        raise RuntimeError("A99 evidence coverage failed before intermediate or route model invocation")
    validated_review = validate_evidence_review(
        evidence_review,
        evidence_receipt_sha256=evidence_receipt_sha256,
        case_ids=tuple(case.case_id for case in dataset.cases),
    )
    placeholder_preflight = preflight_route_cases(dataset.cases, packs)
    if not placeholder_preflight["all_within_budget"]:
        raise RuntimeError("A99 route placeholder preflight failed before model invocation")

    models = {
        "A_route": _CountingModel(_create_model(model_name)),
        "B_intermediate": _CountingModel(_create_model(model_name)),
        "B_route": _CountingModel(_create_model(model_name)),
        "C_intermediate": _CountingModel(_create_model(model_name)),
        "C_route": _CountingModel(_create_model(model_name)),
        "review": _CountingModel(_create_model(model_name)),
    }
    ledgers = {name: RepairLedger(max_repairs=2) for name in models}
    started_at = datetime.now(UTC)

    intermediates: dict[str, dict[str, BenchmarkIntermediateRecord]] = {"B": {}, "C": {}}
    intermediate_results: dict[str, list[dict[str, Any]]] = {"B": [], "C": []}
    for arm in ("B", "C"):
        phase = f"{arm}_intermediate"
        for case in dataset.cases:
            result, record = await _run_intermediate_case(
                case=case,
                arm=arm,
                pack=packs[case.case_id],
                model=models[phase],
                repair_ledger=ledgers[phase],
            )
            intermediate_results[arm].append(result)
            if record is not None:
                intermediates[arm][case.case_id] = record

    all_intermediates_ready = all(set(intermediates[arm]) == {case.case_id for case in dataset.cases} for arm in ("B", "C"))
    actual_preflight = None
    if all_intermediates_ready:
        actual_preflight = preflight_actual_route_cases(dataset.cases, packs, intermediates)
        if not actual_preflight["all_within_budget"]:
            raise RuntimeError("A99 actual route preflight failed before route model invocation")

    route_records: dict[str, dict[str, BenchmarkRouteRecord]] = {"A": {}, "B": {}, "C": {}}
    route_results: dict[str, list[dict[str, Any]]] = {"A": [], "B": [], "C": []}
    if all_intermediates_ready:
        for arm in ("A", "B", "C"):
            phase = f"{arm}_route"
            for case in dataset.cases:
                result, record = await _run_route_case(
                    case=case,
                    arm=arm,
                    pack=packs[case.case_id],
                    model=models[phase],
                    repair_ledger=ledgers[phase],
                    intermediate=(None if arm == "A" else intermediates[arm][case.case_id]),
                )
                route_results[arm].append(result)
                if record is not None:
                    route_records[arm][case.case_id] = record

    complete_case_ids = set.intersection(*(set(route_records[arm]) for arm in ("A", "B", "C")))
    review_preflight = _review_preflight(
        dataset.cases,
        packs,
        route_records,
        complete_case_ids,
    )
    if not review_preflight["all_within_budget"]:
        raise RuntimeError("A99 blind-review preflight failed before reviewer model invocation")

    review_results: list[dict[str, Any]] = []
    review_records = {}
    arm_aliases = {}
    for case in dataset.cases:
        if case.case_id not in complete_case_ids:
            continue
        aliases = blind_arm_aliases(case.case_id)
        arm_aliases[case.case_id] = aliases
        aliased = {aliases[arm]: route_records[arm][case.case_id].route for arm in ("A", "B", "C")}
        started = time.perf_counter()
        before = _model_snapshot(models["review"])
        try:
            review = await generate_blind_review(
                case=case,
                aliased_candidates=aliased,
                evidence_pack=packs[case.case_id],
                model=models["review"],
                repair_ledger=ledgers["review"],
            )
            review_records[case.case_id] = review
            review_results.append(
                {
                    "case_id": case.case_id,
                    "status": "succeeded",
                    "review": review.model_dump(mode="json"),
                    **_call_receipt(models["review"], before, started),
                }
            )
        except Exception as exc:
            review_results.append(
                {
                    "case_id": case.case_id,
                    "status": "failed",
                    "error": _redacted_error(exc),
                    **_call_receipt(models["review"], before, started),
                }
            )

    sealed_labels = load_review_labels()
    fatal_drifts: dict[str, dict[str, tuple[str, ...]]] = {}
    arm_scores: dict[str, dict[str, BlindCandidateScore]] = {}
    for case_id, review in review_records.items():
        inverse_aliases = {alias: arm for arm, alias in arm_aliases[case_id].items()}
        scores = {inverse_aliases[score.candidate_key]: score for score in review.scores}
        if set(scores) == {"A", "B", "C"}:
            arm_scores[case_id] = scores
        review_label = sealed_labels.for_case(case_id)
        fatal_drifts[case_id] = {arm: detect_fatal_drift(review_label, route_records[arm][case_id].route) for arm in ("A", "B", "C")}
    pilot_decision = (
        decide_pilot(arm_scores=arm_scores, fatal_drifts=fatal_drifts)
        if len(arm_scores) == len(dataset.cases)
        else {
            "decision": "inconclusive",
            "reason": "not every frozen case produced a complete blind review",
            "scored_case_count": len(arm_scores),
        }
    )

    return {
        "schema_version": "benchmark-route-stage-v1",
        "experiment_id": "A99-benchmark-first-incubation-pilot-v1",
        "stage": "route_comparison",
        "dataset_id": dataset.dataset_id,
        "git_commit": _git_commit(),
        "artifact_hashes": _artifact_hashes(),
        "model_name": model_name,
        "thinking_enabled": False,
        "temperature": 0,
        "evidence_receipt_sha256": evidence_receipt_sha256,
        "evidence_review": validated_review,
        "evidence_preflight": evidence_preflight,
        "placeholder_preflight": placeholder_preflight,
        "actual_route_preflight": actual_preflight,
        "review_preflight": review_preflight,
        "started_at": started_at.isoformat(),
        "completed_at": datetime.now(UTC).isoformat(),
        "intermediates": {
            arm: _phase_receipt(
                results=intermediate_results[arm],
                model=models[f"{arm}_intermediate"],
                repair_ledger=ledgers[f"{arm}_intermediate"],
                initial_call_count=len(dataset.cases),
            )
            for arm in ("B", "C")
        },
        "routes": {
            arm: _phase_receipt(
                results=route_results[arm],
                model=models[f"{arm}_route"],
                repair_ledger=ledgers[f"{arm}_route"],
                initial_call_count=(len(dataset.cases) if all_intermediates_ready else 0),
            )
            for arm in ("A", "B", "C")
        },
        "blind_review": {
            **_phase_receipt(
                results=review_results,
                model=models["review"],
                repair_ledger=ledgers["review"],
                initial_call_count=len(complete_case_ids),
            ),
            "arm_aliases_sealed_from_model": arm_aliases,
        },
        "fatal_drift_checks": {case_id: {arm: list(hits) for arm, hits in arm_hits.items()} for case_id, arm_hits in fatal_drifts.items()},
        "automatic_pilot_decision": pilot_decision,
        "manual_route_review_status": "pending",
        "promotion_status": "offline_only",
    }


async def _run_intermediate_case(
    *,
    case: BenchmarkIncubationCase,
    arm: str,
    pack: BenchmarkEvidencePack,
    model: _CountingModel,
    repair_ledger: RepairLedger,
) -> tuple[dict[str, Any], BenchmarkIntermediateRecord | None]:
    started = time.perf_counter()
    before = _model_snapshot(model)
    try:
        record = await generate_intermediate(
            case=case,
            arm=arm,
            evidence_pack=pack,
            model=model,
            repair_ledger=repair_ledger,
        )
        return (
            {
                "case_id": case.case_id,
                "status": "succeeded",
                "record": record.model_dump(mode="json"),
                **_call_receipt(model, before, started),
            },
            record,
        )
    except Exception as exc:
        return (
            {
                "case_id": case.case_id,
                "status": "failed",
                "error": _redacted_error(exc),
                **_call_receipt(model, before, started),
            },
            None,
        )


async def _run_route_case(
    *,
    case: BenchmarkIncubationCase,
    arm: str,
    pack: BenchmarkEvidencePack,
    model: _CountingModel,
    repair_ledger: RepairLedger,
    intermediate: BenchmarkIntermediateRecord | None,
) -> tuple[dict[str, Any], BenchmarkRouteRecord | None]:
    started = time.perf_counter()
    before = _model_snapshot(model)
    try:
        record = await generate_route(
            case=case,
            arm=arm,
            evidence_pack=pack,
            model=model,
            repair_ledger=repair_ledger,
            intermediate=intermediate,
        )
        return (
            {
                "case_id": case.case_id,
                "status": "succeeded",
                "record": record.model_dump(mode="json"),
                **_call_receipt(model, before, started),
            },
            record,
        )
    except Exception as exc:
        return (
            {
                "case_id": case.case_id,
                "status": "failed",
                "error": _redacted_error(exc),
                **_call_receipt(model, before, started),
            },
            None,
        )


def _review_preflight(
    cases: Sequence[BenchmarkIncubationCase],
    packs: Mapping[str, BenchmarkEvidencePack],
    route_records: Mapping[str, Mapping[str, BenchmarkRouteRecord]],
    complete_case_ids: set[str],
) -> dict[str, Any]:
    checks = []
    for case in cases:
        if case.case_id not in complete_case_ids:
            continue
        aliases = blind_arm_aliases(case.case_id)
        aliased = {aliases[arm]: route_records[arm][case.case_id].route for arm in ("A", "B", "C")}
        budget = structured_input_bytes(
            render_blind_review_messages(
                case=case,
                aliased_candidates=aliased,
                evidence_pack=packs[case.case_id],
            ),
            BlindCaseReviewDraft,
            include_repair_instruction=True,
        )
        checks.append({"case_id": case.case_id, **budget})
    return {
        "case_count": len(checks),
        "all_within_budget": all(item["repair_input_bytes"] <= _REVIEW_INPUT_BUDGET for item in checks),
        "max_repair_input_bytes": max(
            (item["repair_input_bytes"] for item in checks),
            default=0,
        ),
        "model_calls": 0,
        "cases": checks,
    }


def _empty_budget() -> dict[str, int]:
    return {
        "message_bytes": 0,
        "schema_bytes": 0,
        "initial_input_bytes": 0,
        "repair_input_bytes": 0,
    }


def _join_route_budgets(
    route: Mapping[str, int],
    intermediate: Mapping[str, int],
) -> dict[str, int]:
    return {
        "input_bytes": route["initial_input_bytes"],
        "repair_input_bytes": route["repair_input_bytes"],
        "schema_bytes": route["schema_bytes"],
        "intermediate_input_bytes": intermediate["initial_input_bytes"],
        "intermediate_repair_input_bytes": intermediate["repair_input_bytes"],
        "intermediate_schema_bytes": intermediate["schema_bytes"],
    }


def _preflight_report(
    cases: Sequence[BenchmarkIncubationCase],
    checks: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "case_count": len(cases),
        "message_count": len(checks),
        "all_within_budget": len(checks) == len(cases) * 3 and all(item["repair_input_bytes"] <= _MODEL_INPUT_BUDGET and item["intermediate_repair_input_bytes"] <= _MODEL_INPUT_BUDGET for item in checks),
        "max_input_bytes": max((item["input_bytes"] for item in checks), default=0),
        "max_repair_input_bytes": max(
            (item["repair_input_bytes"] for item in checks),
            default=0,
        ),
        "max_schema_bytes": max((item["schema_bytes"] for item in checks), default=0),
        "max_intermediate_input_bytes": max(
            (item["intermediate_input_bytes"] for item in checks),
            default=0,
        ),
        "max_intermediate_repair_input_bytes": max(
            (item["intermediate_repair_input_bytes"] for item in checks),
            default=0,
        ),
        "model_calls": 0,
        "messages": checks,
    }


def _phase_receipt(
    *,
    results: list[dict[str, Any]],
    model: _CountingModel,
    repair_ledger: RepairLedger,
    initial_call_count: int,
) -> dict[str, Any]:
    return {
        "cases": results,
        "contract_success_count": sum(result.get("status") == "succeeded" for result in results),
        **_model_totals(model, repair_ledger, initial_call_count=initial_call_count),
        "duration_seconds": round(
            sum(float(result.get("duration_seconds", 0.0)) for result in results),
            3,
        ),
    }


def _model_totals(
    model: _CountingModel,
    repair_ledger: RepairLedger,
    *,
    initial_call_count: int,
) -> dict[str, Any]:
    return {
        "model_calls": model.calls,
        "failed_calls": model.failed_calls,
        "usage": model.usage,
        "usage_reported_calls": model.usage_reported_calls,
        "usage_unreported_calls": model.usage_unreported_calls,
        "usage_complete": model.usage_unreported_calls == 0,
        "initial_call_count": initial_call_count,
        "repair_call_count": repair_ledger.repairs_used,
    }


def _model_snapshot(model: _CountingModel) -> dict[str, Any]:
    return {
        "calls": model.calls,
        "failed_calls": model.failed_calls,
        "usage_reported_calls": model.usage_reported_calls,
        "usage_unreported_calls": model.usage_unreported_calls,
        "usage": dict(model.usage),
    }


def _call_receipt(
    model: _CountingModel,
    before: Mapping[str, Any],
    started: float,
) -> dict[str, Any]:
    before_usage = before["usage"]
    return {
        "model_calls": model.calls - int(before["calls"]),
        "failed_calls": model.failed_calls - int(before["failed_calls"]),
        "usage_reported_calls": model.usage_reported_calls - int(before["usage_reported_calls"]),
        "usage_unreported_calls": model.usage_unreported_calls - int(before["usage_unreported_calls"]),
        "usage": {key: model.usage[key] - int(before_usage[key]) for key in ("input_tokens", "output_tokens", "total_tokens")},
        "duration_seconds": round(time.perf_counter() - started, 3),
    }


def _redacted_error(exc: Exception) -> str:
    value = f"{type(exc).__name__}: {exc}"[:1_000]
    value = re.sub(r"\bsk-[A-Za-z0-9_-]{8,}\b", "[REDACTED_API_KEY]", value)
    value = re.sub(r"(?i)bearer\s+[A-Za-z0-9._~-]+", "Bearer [REDACTED]", value)
    return value


def _artifact_hashes() -> dict[str, str]:
    lab_dir = Path(__file__).parent
    paths = (
        lab_dir / "contracts.py",
        lab_dir / "lab.py",
        lab_dir / "search.py",
        lab_dir / "evaluation.py",
        lab_dir / "run.py",
        lab_dir / "datasets" / "held_out_v1.json",
        lab_dir / "datasets" / "review_labels_v1.json",
    )
    return {str(path.relative_to(Path(__file__).parents[2])): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}


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


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_receipt(path: Path, receipt: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _default_output_path(stage: str) -> Path:
    root = Path(__file__).parents[3]
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    return root / "docs" / "content-intelligence-v6" / "evidence" / f"benchmark-first-a99-{stage}-{run_id}.json"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the isolated A99 benchmark-first incubation pilot.")
    subparsers = parser.add_subparsers(dest="stage", required=True)

    collect = subparsers.add_parser(
        "collect",
        help="Freeze search plans and public web evidence only.",
    )
    collect.add_argument("--model", default="glm-5-2-260617")
    collect.add_argument("--output", type=Path)

    routes = subparsers.add_parser(
        "routes",
        help="Run A/B/C only after a hash-bound evidence review.",
    )
    routes.add_argument("--model", default="glm-5-2-260617")
    routes.add_argument("--evidence", type=Path, required=True)
    routes.add_argument("--review", type=Path, required=True)
    routes.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    output = args.output or _default_output_path(args.stage)
    if args.stage == "collect":
        receipt = asyncio.run(collect_evidence_stage(model_name=args.model))
    else:
        receipt = asyncio.run(
            run_route_stage(
                model_name=args.model,
                evidence_receipt=_read_json(args.evidence),
                evidence_receipt_sha256=_file_sha256(args.evidence),
                evidence_review=_read_json(args.review),
            )
        )
    _write_receipt(output, receipt)
    print(output)


if __name__ == "__main__":
    main()


__all__ = [
    "_CountingModel",
    "automatic_evidence_preflight",
    "collect_evidence_stage",
    "preflight_actual_route_cases",
    "preflight_planner_cases",
    "preflight_route_cases",
    "run_route_stage",
    "validate_evidence_review",
]
