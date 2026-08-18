from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from deerflow.config.app_config import get_app_config
from deerflow.models import create_chat_model
from experiments.real_account_benchmark_smoke_lab.lab import (
    AccountEvidenceProjection,
    ArmId,
    SmokeCase,
    build_account_evidence_projection,
    expected_model_calls,
    generate_digest,
    generate_review,
    generate_route,
    preflight_smoke,
)

ModelFactory = Callable[[str], Any]


class _CountingRunnable:
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

    def with_structured_output(self, *args: Any, **kwargs: Any) -> _CountingRunnable:
        return _CountingRunnable(self, self._model.with_structured_output(*args, **kwargs))

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

    def receipt(self) -> dict[str, Any]:
        return {
            "calls": self.calls,
            "failed_calls": self.failed_calls,
            "usage_reported_calls": self.usage_reported_calls,
            "usage_unreported_calls": self.usage_unreported_calls,
            "usage": dict(self.usage),
        }


def create_model(model_name: str) -> Any:
    return create_chat_model(
        name=model_name,
        thinking_enabled=False,
        app_config=get_app_config(),
        attach_tracing=False,
        model_overrides={"temperature": 0},
    )


async def run_smoke(
    *,
    case: SmokeCase,
    evidence: AccountEvidenceProjection,
    model_name: str,
    model_factory: ModelFactory | None = None,
) -> dict[str, Any]:
    if case.case_id != evidence.case_id:
        raise ValueError("smoke case must match its frozen real-account evidence")
    preflight = preflight_smoke(case=case, evidence=evidence)
    if not preflight["all_within_budget"]:
        raise ValueError("real-account benchmark smoke failed model-input preflight")

    factory = model_factory or (lambda _stage: create_model(model_name))
    models: dict[str, _CountingModel] = {}
    digests: dict[ArmId, Any] = {}
    routes: dict[ArmId, Any] = {}
    for arm in ("benchmark_only", "thin_world"):
        digest_stage = f"{arm}_digest"
        digest_model = _CountingModel(factory(digest_stage))
        models[digest_stage] = digest_model
        digests[arm] = await generate_digest(
            case=case,
            arm=arm,
            evidence=evidence,
            model=digest_model,
        )

        route_stage = f"{arm}_route"
        route_model = _CountingModel(factory(route_stage))
        models[route_stage] = route_model
        routes[arm] = await generate_route(
            case=case,
            arm=arm,
            evidence=evidence,
            digest=digests[arm],
            model=route_model,
        )

    aliases = _blind_aliases(case.case_id, evidence.evidence_hash)
    review_model = _CountingModel(factory("blind_review"))
    models["blind_review"] = review_model
    review = await generate_review(
        case=case,
        evidence=evidence,
        candidates={aliases[arm]: routes[arm].route for arm in ("benchmark_only", "thin_world")},
        model=review_model,
    )

    stage_receipts = {stage: model.receipt() for stage, model in models.items()}
    total_calls = sum(item["calls"] for item in stage_receipts.values())
    total_usage = {key: sum(item["usage"][key] for item in stage_receipts.values()) for key in ("input_tokens", "output_tokens", "total_tokens")}
    expected = expected_model_calls()
    if total_calls != expected["total"] or any(item["calls"] != 1 for item in stage_receipts.values()):
        raise ValueError("real-account benchmark smoke violated its frozen model-call budget")

    return {
        "schema_version": "real-account-benchmark-smoke-receipt-v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "model_name": model_name,
        "thinking_enabled": False,
        "temperature": 0,
        "case": case.model_dump(mode="json"),
        "evidence_summary": {
            "evidence_hash": evidence.evidence_hash,
            "source_hashes": evidence.source_hashes,
            "account_ref": evidence.account_ref,
            "observed_post_count": evidence.observed_post_count,
            "projected_post_count": len(evidence.posts),
            "pattern_count": len(evidence.patterns),
            "audience_interaction_count": len(evidence.audience_interactions),
            "limitations": evidence.limitations,
        },
        "preflight": preflight,
        "digests": {arm: digests[arm].model_dump(mode="json") for arm in ("benchmark_only", "thin_world")},
        "routes": {arm: routes[arm].model_dump(mode="json") for arm in ("benchmark_only", "thin_world")},
        "blind_aliases": aliases,
        "blind_review": review.model_dump(mode="json"),
        "call_summary": {
            "expected": expected,
            "total_calls": total_calls,
            "total_usage": total_usage,
            "stages": stage_receipts,
        },
    }


def _blind_aliases(case_id: str, evidence_hash: str) -> dict[ArmId, str]:
    arms: tuple[ArmId, ArmId] = ("benchmark_only", "thin_world")
    ordered = sorted(arms, key=lambda arm: hashlib.sha256(f"{case_id}\0{evidence_hash}\0{arm}".encode()).hexdigest())
    return {ordered[0]: "候选甲", ordered[1]: "候选乙"}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the isolated real-account benchmark-first incubation smoke.")
    parser.add_argument("--source-snapshot", type=Path, required=True)
    parser.add_argument("--lead-projection", type=Path, required=True)
    parser.add_argument("--audience-snapshot", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--case-id", default="watch-account-smoke-v1")
    parser.add_argument("--user-request", default="我是做腕表的，该怎么起号？")
    parser.add_argument("--commercial-object", default="腕表")
    parser.add_argument("--model", default="glm-5-2-260617")
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    case = SmokeCase(
        case_id=args.case_id,
        user_request=args.user_request,
        commercial_object=args.commercial_object,
    )
    evidence = build_account_evidence_projection(
        args.source_snapshot,
        args.lead_projection,
        args.audience_snapshot,
        case_id=case.case_id,
    )
    receipt = asyncio.run(
        run_smoke(
            case=case,
            evidence=evidence,
            model_name=args.model,
        )
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(args.output),
                "evidence_hash": evidence.evidence_hash,
                "model_calls": receipt["call_summary"]["total_calls"],
                "token_usage": receipt["call_summary"]["total_usage"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
