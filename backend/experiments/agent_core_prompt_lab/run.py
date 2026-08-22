from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
import uuid
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from langgraph.checkpoint.memory import InMemorySaver

from deerflow.agents.lead_agent.agent_core_contract import apply_agent_core_candidate
from deerflow.agents.lead_agent.prompt import SYSTEM_PROMPT_TEMPLATE, get_enabled_skills_for_config
from deerflow.client import DeerFlowClient
from deerflow.config.app_config import get_app_config
from experiments.agent_core_prompt_lab.contracts import AgentCoreCase
from experiments.agent_core_prompt_lab.datasets import dataset_hash, load_agent_core_cases
from experiments.agent_core_prompt_lab.middleware import AgentCoreProbeMiddleware
from experiments.harness_business_e2e_lab.contracts import TokenUsage
from experiments.harness_business_e2e_lab.observation import collect_agent_stream

_REPO_ROOT = Path(__file__).resolve().parents[3]
_BASELINE = "current_full"
_CANDIDATE = "agent_core_candidate"
_MAX_MODEL_CALLS_PER_ARM = 12
DEFAULT_MODELS = (
    "glm-5-2-260617",
    "deepseek-v4-pro",
    "deepseek-v4-flash",
)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _git_commit() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=_REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _config_hash(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def preflight() -> dict[str, Any]:
    if "<agent_kernel>" in SYSTEM_PROMPT_TEMPLATE:
        raise RuntimeError("A138 is a retired comparison and cannot be rerun against the superseding production agent kernel")
    dataset = load_agent_core_cases()
    candidate = apply_agent_core_candidate(SYSTEM_PROMPT_TEMPLATE)
    skills = []
    for skill in sorted(get_enabled_skills_for_config(get_app_config()), key=lambda item: item.name):
        path = Path(skill.skill_file)
        skills.append(
            {
                "name": skill.name,
                "content_hash": hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None,
                "allowed_tools": list(skill.allowed_tools or ()),
            }
        )
    skill_manifest = json.dumps(skills, ensure_ascii=False, sort_keys=True)
    return {
        "dataset_id": dataset.dataset_id,
        "dataset_hash": dataset_hash(),
        "case_count": len(dataset.cases),
        "model_names": list(DEFAULT_MODELS),
        "baseline_system_hash": _sha256(SYSTEM_PROMPT_TEMPLATE),
        "candidate_system_hash": _sha256(candidate),
        "baseline_system_bytes": len(SYSTEM_PROMPT_TEMPLATE.encode("utf-8")),
        "candidate_system_bytes": len(candidate.encode("utf-8")),
        "same_candidate_for_every_model": True,
        "same_tools_and_skills_required": True,
        "max_model_calls_per_arm": _MAX_MODEL_CALLS_PER_ARM,
        "enabled_skill_count": len(skills),
        "enabled_skill_manifest_hash": _sha256(skill_manifest),
    }


def _create_clients(
    model_name: str,
) -> tuple[dict[str, DeerFlowClient], dict[str, AgentCoreProbeMiddleware]]:
    probes = {
        _BASELINE: AgentCoreProbeMiddleware(
            arm=_BASELINE,
            max_model_calls=_MAX_MODEL_CALLS_PER_ARM,
        ),
        _CANDIDATE: AgentCoreProbeMiddleware(
            arm=_CANDIDATE,
            max_model_calls=_MAX_MODEL_CALLS_PER_ARM,
        ),
    }
    clients = {
        arm: DeerFlowClient(
            config_path=str(_REPO_ROOT / "config.yaml"),
            checkpointer=InMemorySaver(),
            model_name=model_name,
            thinking_enabled=True,
            subagent_enabled=False,
            plan_mode=False,
            middlewares=[probe],
            environment="experiment-a138",
        )
        for arm, probe in probes.items()
    }
    return clients, probes


def _run_arm(
    *,
    model_name: str,
    client: DeerFlowClient,
    probe: AgentCoreProbeMiddleware,
    case: AgentCoreCase,
    arm: str,
) -> dict[str, Any]:
    started = time.perf_counter()
    observation_start = len(probe.observations)
    thread_id = f"a138-{model_name[:12]}-{arm[:7]}-{case.case_id[:24]}-{uuid.uuid4().hex[:8]}"
    try:
        collected = collect_agent_stream(
            client.stream(
                case.prompt,
                thread_id=thread_id,
                user_id="a138-agent-core-lab",
            )
        )
        observations = probe.observations[observation_start:]
        return {
            "status": "succeeded" if collected.valid else "invalid",
            "answer": collected.answer,
            "answer_source": collected.answer_source,
            "termination_reason": collected.termination_reason,
            "valid": collected.valid,
            "repetitive": collected.repetitive,
            "tool_calls": list(collected.tool_calls),
            "tool_call_count": len(collected.tool_calls),
            "tool_result_count": collected.tool_result_count,
            "tool_failure_count": collected.tool_failure_count,
            "usage": collected.usage.model_dump(mode="json"),
            "duration_seconds": round(time.perf_counter() - started, 3),
            "model_request_count": len(observations),
            "request_observations": [item.model_dump(mode="json") for item in observations],
        }
    except Exception as exc:
        observations = probe.observations[observation_start:]
        return {
            "status": "failed",
            "error_type": type(exc).__name__,
            "termination_reason": "exception",
            "valid": False,
            "repetitive": False,
            "tool_calls": [],
            "tool_call_count": 0,
            "tool_result_count": 0,
            "tool_failure_count": 0,
            "usage": TokenUsage().model_dump(mode="json"),
            "duration_seconds": round(time.perf_counter() - started, 3),
            "model_request_count": len(observations),
            "request_observations": [item.model_dump(mode="json") for item in observations],
        }


def _execution_order(model_name: str, case_id: str) -> tuple[str, str]:
    digest = hashlib.sha256(f"{model_name}:{case_id}".encode()).hexdigest()
    return (_BASELINE, _CANDIDATE) if int(digest[0], 16) % 2 == 0 else (_CANDIDATE, _BASELINE)


def _initial_contract(arm: Mapping[str, Any]) -> Mapping[str, Any] | None:
    observations = arm.get("request_observations")
    if not isinstance(observations, list) or not observations:
        return None
    first = observations[0]
    return first if isinstance(first, Mapping) else None


def _pair_contract(baseline: Mapping[str, Any], candidate: Mapping[str, Any]) -> dict[str, bool]:
    left = _initial_contract(baseline)
    right = _initial_contract(candidate)
    if left is None or right is None:
        return {
            "initial_tools_match": False,
            "initial_tool_schema_match": False,
            "base_system_match": False,
            "model_contract_match": False,
        }
    return {
        "initial_tools_match": left.get("tool_names") == right.get("tool_names"),
        "initial_tool_schema_match": left.get("tool_schema_hash") == right.get("tool_schema_hash"),
        "base_system_match": left.get("base_system_hash") == right.get("base_system_hash"),
        "model_contract_match": left.get("model_contract_hash") == right.get("model_contract_hash"),
    }


def _write_receipt(output: Path | None, receipt: Mapping[str, Any]) -> None:
    if output is None:
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(f"{json.dumps(receipt, ensure_ascii=False, indent=2)}\n", encoding="utf-8")


def run_experiment(
    *,
    model_names: Sequence[str],
    output: Path | None = None,
    case_ids: set[str] | None = None,
) -> dict[str, Any]:
    frozen_preflight = preflight()
    dataset = load_agent_core_cases()
    cases = [case for case in dataset.cases if case_ids is None or case.case_id in case_ids]
    if not cases:
        raise ValueError("no A138 cases selected")
    unknown = set(case_ids or ()) - {case.case_id for case in dataset.cases}
    if unknown:
        raise ValueError(f"unknown A138 case ids: {sorted(unknown)}")

    receipt: dict[str, Any] = {
        "schema_version": "agent-core-prompt-receipt-v1",
        "experiment_id": "A138-model-neutral-agent-core-v1",
        "status": "running",
        "git_commit": _git_commit(),
        "config_hash": _config_hash(_REPO_ROOT / "config.yaml"),
        "extensions_config_hash": _config_hash(_REPO_ROOT / "extensions_config.json"),
        "models": list(model_names),
        "thinking_enabled": True,
        "subagent_enabled": False,
        "preflight": frozen_preflight,
        "started_at": datetime.now(UTC).isoformat(),
        "runs": [],
        "manual_review_status": "pending",
        "runtime_promotion_status": "not_evaluated",
    }
    _write_receipt(output, receipt)

    total = len(model_names) * len(cases)
    pair_index = 0
    for model_name in model_names:
        for case in cases:
            clients, probes = _create_clients(model_name)
            pair_index += 1
            pair: dict[str, Any] = {
                "model_name": model_name,
                "case_id": case.case_id,
                "task_class": case.task_class,
                "prompt": case.prompt,
                "execution_order": list(_execution_order(model_name, case.case_id)),
                "arms": {},
            }
            receipt["runs"].append(pair)
            for arm in pair["execution_order"]:
                print(
                    f"[A138 {pair_index}/{total}] start {model_name} {case.case_id} {arm}",
                    file=sys.stderr,
                    flush=True,
                )
                result = _run_arm(
                    model_name=model_name,
                    client=clients[arm],
                    probe=probes[arm],
                    case=case,
                    arm=arm,
                )
                pair["arms"][arm] = result
                _write_receipt(output, receipt)
                print(
                    f"[A138 {pair_index}/{total}] finish {arm} status={result['status']} calls={result['model_request_count']} tools={result['tool_call_count']} tokens={result['usage']['total_tokens']}",
                    file=sys.stderr,
                    flush=True,
                )
            pair["contract"] = _pair_contract(pair["arms"][_BASELINE], pair["arms"][_CANDIDATE])
            _write_receipt(output, receipt)

    receipt.update(
        {
            "status": "completed",
            "completed_at": datetime.now(UTC).isoformat(),
            "runtime_promotion_status": "manual_review_required",
        }
    )
    _write_receipt(output, receipt)
    return receipt


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the A138 full-Harness Agent core prompt A/B.")
    parser.add_argument("--model", action="append", dest="models")
    parser.add_argument("--case", action="append", dest="cases")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--preflight", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    result = (
        preflight()
        if args.preflight
        else run_experiment(
            model_names=tuple(args.models or DEFAULT_MODELS),
            case_ids=set(args.cases) if args.cases else None,
            output=args.output,
        )
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
