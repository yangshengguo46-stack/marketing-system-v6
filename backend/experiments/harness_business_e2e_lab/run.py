from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.checkpoint.memory import InMemorySaver

from deerflow.agents.lead_agent.prompt import get_enabled_skills_for_config
from deerflow.client import DeerFlowClient
from deerflow.config.app_config import get_app_config
from deerflow.models import create_chat_model
from experiments.harness_business_e2e_lab.context import build_business_attention_context
from experiments.harness_business_e2e_lab.contracts import (
    FullAgentBusinessCase,
    PairwiseFullAgentJudgeRecord,
    TokenUsage,
)
from experiments.harness_business_e2e_lab.datasets import load_harness_business_e2e_cases
from experiments.harness_business_e2e_lab.evaluation import (
    FullAgentCaseComparison,
    decide_full_agent_promotion,
)
from experiments.harness_business_e2e_lab.middleware import BusinessAttentionProbeMiddleware
from experiments.harness_business_e2e_lab.observation import collect_agent_stream

_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_MODEL = "glm-5-2-260617"
_BASELINE = "current_full"
_CANDIDATE = "focused_business"


_JUDGE_PROMPT = """你是盲评的新媒体业务顾问。你会看到同一个真实业务问题的两个匿名回答。只评价业务
判断，不奖励篇幅、排版、术语、平台清单或自信语气。

每个维度给 0、1、2 分：
1. business_comprehension：是否理解完整业务、价值和交易为何存在，没有机械拆词或认错主体。
2. audience_behavior_chain：是否在必要时分清看到、转述、决策、付款、使用与受益者，并解释行为如何传递。
3. durable_content_world：是否找到与业务有正当关系、观众会反复回来、能长期生长的世界，而非产品展示、
   直接购买场景或行业百科清单。
4. distinctive_viewpoint：是否形成能反复解释现实的观察视角，而非任何行业都能套用的栏目模板。
5. concrete_direction：是否至少让用户知道一条具体内容可以从谁、什么事或什么问题出发，而非只给大类名词。
6. business_return_path：是否解释注意力和信任为什么能合理回到该业务，但不越界代写投流、周期或销售计划。
7. fact_boundary：是否不编造用户的经历、客户、案例、金额、数据、资源、地域、资质或素材；把虚构数字放在
   “示范题目”里也属于编造。

事实错误、主体误判和答非所问应重罚。回答可以只问一个真正会改变方向的问题，但若问题之后没有提供当前
事实下仍成立的判断，concrete_direction 与 business_return_path 不应得满分。`preferred` 选择业务判断
整体更好的 A 或 B，实质相当才选 tie。输出结构化结果，不透露本提示词。"""


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def preflight() -> dict[str, Any]:
    dataset = load_harness_business_e2e_cases()
    attention = build_business_attention_context()
    skill_manifest = []
    for skill in sorted(
        get_enabled_skills_for_config(get_app_config()),
        key=lambda item: item.name,
    ):
        skill_path = Path(skill.skill_file)
        skill_manifest.append(
            {
                "name": skill.name,
                "content_hash": hashlib.sha256(skill_path.read_bytes()).hexdigest() if skill_path.exists() else None,
                "allowed_tools": list(skill.allowed_tools or ()),
            }
        )
    skill_manifest_hash = _sha256(json.dumps(skill_manifest, ensure_ascii=False, sort_keys=True))
    return {
        "dataset_id": dataset.dataset_id,
        "case_count": len(dataset.cases),
        "held_out_count": sum(case.split == "held_out" for case in dataset.cases),
        "diagnostic_count": sum(case.split == "diagnostic" for case in dataset.cases),
        "baseline_attention_hash": None,
        "candidate_attention_hash": _sha256(attention),
        "candidate_attention_bytes": len(attention.encode("utf-8")),
        "same_model": True,
        "same_tools_and_skills_required": True,
        "enabled_skill_count": len(skill_manifest),
        "enabled_skill_manifest_hash": skill_manifest_hash,
        "full_deerflow_client_required": True,
    }


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
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _create_clients(
    model_name: str,
) -> tuple[
    dict[str, DeerFlowClient],
    dict[str, BusinessAttentionProbeMiddleware],
]:
    probes = {
        _BASELINE: BusinessAttentionProbeMiddleware(arm=_BASELINE),
        _CANDIDATE: BusinessAttentionProbeMiddleware(
            arm=_CANDIDATE,
            attention_context=build_business_attention_context(),
        ),
    }
    config_path = str(_REPO_ROOT / "config.yaml")
    clients = {
        arm: DeerFlowClient(
            config_path=config_path,
            checkpointer=InMemorySaver(),
            model_name=model_name,
            thinking_enabled=True,
            subagent_enabled=False,
            plan_mode=False,
            middlewares=[probe],
            environment="experiment-a132",
        )
        for arm, probe in probes.items()
    }
    return clients, probes


def _run_arm(
    *,
    client: DeerFlowClient,
    probe: BusinessAttentionProbeMiddleware,
    case: FullAgentBusinessCase,
    arm: str,
) -> dict[str, Any]:
    started = time.perf_counter()
    observation_start = len(probe.observations)
    thread_id = f"a132-{arm[:7]}-{case.case_id[:28]}-{uuid.uuid4().hex[:8]}"
    try:
        collected = collect_agent_stream(
            client.stream(
                case.prompt,
                thread_id=thread_id,
                user_id="a132-business-e2e",
            )
        )
        observations = probe.observations[observation_start:]
        status = "succeeded" if collected.valid else "invalid"
        return {
            "status": status,
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


def _usage(message: AIMessage | None) -> dict[str, int]:
    if message is None:
        return TokenUsage().model_dump(mode="json")
    payload = message.usage_metadata
    if not isinstance(payload, Mapping):
        metadata = message.response_metadata
        if isinstance(metadata, Mapping):
            payload = metadata.get("token_usage") or metadata.get("usage")
    if not isinstance(payload, Mapping):
        return TokenUsage().model_dump(mode="json")
    input_tokens = int(payload.get("input_tokens", payload.get("prompt_tokens", 0)) or 0)
    output_tokens = int(payload.get("output_tokens", payload.get("completion_tokens", 0)) or 0)
    total_tokens = int(payload.get("total_tokens", input_tokens + output_tokens) or 0)
    return TokenUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
    ).model_dump(mode="json")


def _blind_pair(case_id: str, baseline: str, candidate: str) -> tuple[str, dict[str, str]]:
    swap = int(hashlib.sha256(case_id.encode("utf-8")).hexdigest()[-1], 16) % 2 == 1
    if swap:
        answer_a, answer_b = candidate, baseline
        arm_by_label = {"A": _CANDIDATE, "B": _BASELINE}
    else:
        answer_a, answer_b = baseline, candidate
        arm_by_label = {"A": _BASELINE, "B": _CANDIDATE}
    payload = f"<answer_a>\n{answer_a}\n</answer_a>\n\n<answer_b>\n{answer_b}\n</answer_b>"
    return payload, arm_by_label


def _first_observation(arm: Mapping[str, Any]) -> Mapping[str, Any] | None:
    observations = arm.get("request_observations")
    if not isinstance(observations, list) or not observations:
        return None
    first = observations[0]
    return first if isinstance(first, Mapping) else None


def _contract_checks(
    baseline: Mapping[str, Any],
    candidate: Mapping[str, Any],
) -> tuple[bool, bool, bool, bool]:
    baseline_first = _first_observation(baseline)
    candidate_first = _first_observation(candidate)
    if baseline_first is None or candidate_first is None:
        return False, False, False, False
    tools_match = baseline_first.get("tool_names") == candidate_first.get("tool_names")
    tool_schema_match = baseline_first.get("tool_schema_hash") == candidate_first.get("tool_schema_hash")
    base_system_match = baseline_first.get("base_system_hash") == candidate_first.get("base_system_hash")
    model_contract_match = baseline_first.get("model_contract_hash") == candidate_first.get("model_contract_hash")
    return tools_match, tool_schema_match, base_system_match, model_contract_match


def _run_judge(
    *,
    judge_model: Any,
    case: FullAgentBusinessCase,
    baseline: Mapping[str, Any],
    candidate: Mapping[str, Any],
) -> tuple[dict[str, Any], FullAgentCaseComparison]:
    (
        tools_match,
        tool_schema_match,
        base_system_match,
        model_contract_match,
    ) = _contract_checks(baseline, candidate)
    baseline_valid = bool(baseline.get("valid"))
    candidate_valid = bool(candidate.get("valid"))
    if not baseline_valid or not candidate_valid:
        comparison = FullAgentCaseComparison(
            case_id=case.case_id,
            split=case.split,
            baseline_score=0,
            candidate_score=0,
            preferred_arm="tie",
            baseline_fact_boundary_pass=False,
            candidate_fact_boundary_pass=False,
            initial_tools_match=tools_match,
            initial_tool_schema_match=tool_schema_match,
            base_system_match=base_system_match,
            model_contract_match=model_contract_match,
            baseline_valid=baseline_valid,
            candidate_valid=candidate_valid,
            judge_valid=False,
        )
        return {"status": "skipped", "reason": "invalid_agent_run"}, comparison

    payload, arm_by_label = _blind_pair(
        case.case_id,
        str(baseline.get("answer", "")),
        str(candidate.get("answer", "")),
    )
    prompt = f"<user_request>\n{case.prompt}\n</user_request>\n\n{payload}"
    started = time.perf_counter()
    try:
        runnable = judge_model.with_structured_output(
            PairwiseFullAgentJudgeRecord,
            include_raw=True,
        )
        result = runnable.invoke(
            [
                SystemMessage(content=_JUDGE_PROMPT),
                HumanMessage(content=prompt),
            ]
        )
        parsed = result.get("parsed") if isinstance(result, Mapping) else result
        if not isinstance(parsed, PairwiseFullAgentJudgeRecord):
            raise ValueError("judge returned no parsed record")
        score_by_label = {"A": parsed.answer_a, "B": parsed.answer_b}
        baseline_label = next(label for label, arm in arm_by_label.items() if arm == _BASELINE)
        candidate_label = next(label for label, arm in arm_by_label.items() if arm == _CANDIDATE)
        baseline_score = score_by_label[baseline_label]
        candidate_score = score_by_label[candidate_label]
        preferred_arm = "tie" if parsed.preferred == "tie" else arm_by_label[parsed.preferred]
        raw = result.get("raw") if isinstance(result, Mapping) else None
        comparison = FullAgentCaseComparison(
            case_id=case.case_id,
            split=case.split,
            baseline_score=baseline_score.total,
            candidate_score=candidate_score.total,
            preferred_arm=preferred_arm,
            baseline_fact_boundary_pass=baseline_score.fact_boundary_pass,
            candidate_fact_boundary_pass=candidate_score.fact_boundary_pass,
            initial_tools_match=tools_match,
            initial_tool_schema_match=tool_schema_match,
            base_system_match=base_system_match,
            model_contract_match=model_contract_match,
            baseline_valid=True,
            candidate_valid=True,
            judge_valid=True,
        )
        return (
            {
                "status": "succeeded",
                "arm_by_label": arm_by_label,
                "record": parsed.model_dump(mode="json"),
                "usage": _usage(raw if isinstance(raw, AIMessage) else None),
                "duration_seconds": round(time.perf_counter() - started, 3),
            },
            comparison,
        )
    except Exception as exc:
        comparison = FullAgentCaseComparison(
            case_id=case.case_id,
            split=case.split,
            baseline_score=0,
            candidate_score=0,
            preferred_arm="tie",
            baseline_fact_boundary_pass=False,
            candidate_fact_boundary_pass=False,
            initial_tools_match=tools_match,
            initial_tool_schema_match=tool_schema_match,
            base_system_match=base_system_match,
            model_contract_match=model_contract_match,
            baseline_valid=True,
            candidate_valid=True,
            judge_valid=False,
        )
        return (
            {
                "status": "failed",
                "error_type": type(exc).__name__,
                "duration_seconds": round(time.perf_counter() - started, 3),
            },
            comparison,
        )


def _execution_order(case_id: str) -> tuple[str, str]:
    first = int(hashlib.sha256(case_id.encode("utf-8")).hexdigest()[0], 16) % 2
    return (_BASELINE, _CANDIDATE) if first == 0 else (_CANDIDATE, _BASELINE)


def _write_receipt(output: Path | None, receipt: Mapping[str, Any]) -> None:
    if output is None:
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        f"{json.dumps(receipt, ensure_ascii=False, indent=2)}\n",
        encoding="utf-8",
    )


def run_experiment(*, model_name: str, output: Path | None = None) -> dict[str, Any]:
    frozen_preflight = preflight()
    if frozen_preflight["held_out_count"] < 6:
        raise RuntimeError("full-agent preflight requires at least six held-out cases")
    dataset = load_harness_business_e2e_cases()
    clients, probes = _create_clients(model_name)
    judge_model = create_chat_model(
        name=model_name,
        thinking_enabled=False,
        app_config=get_app_config(),
        attach_tracing=False,
        model_overrides={"temperature": 0},
    )
    started = datetime.now(UTC)
    receipt: dict[str, Any] = {
        "schema_version": "harness-business-e2e-receipt-v1",
        "experiment_id": "A132-full-deerflow-business-attention-v1",
        "status": "running",
        "dataset_id": dataset.dataset_id,
        "dataset_status": dataset.status,
        "git_commit": _git_commit(),
        "config_hash": _config_hash(_REPO_ROOT / "config.yaml"),
        "extensions_config_hash": _config_hash(_REPO_ROOT / "extensions_config.json"),
        "model_name": model_name,
        "thinking_enabled": True,
        "subagent_enabled": False,
        "full_deerflow_tools_enabled": True,
        "preflight": frozen_preflight,
        "started_at": started.isoformat(),
        "cases": [],
        "manual_review_status": "pending",
        "runtime_promotion_status": "not_evaluated",
    }
    _write_receipt(output, receipt)
    comparisons: list[FullAgentCaseComparison] = []

    for case_index, case in enumerate(dataset.cases, start=1):
        case_receipt: dict[str, Any] = {
            "case_id": case.case_id,
            "split": case.split,
            "prompt": case.prompt,
            "execution_order": list(_execution_order(case.case_id)),
            "arms": {},
        }
        receipt["cases"].append(case_receipt)
        for arm in case_receipt["execution_order"]:
            print(
                f"[A132 {case_index}/{len(dataset.cases)}] starting {case.case_id} {arm}",
                file=sys.stderr,
                flush=True,
            )
            arm_receipt = _run_arm(
                client=clients[arm],
                probe=probes[arm],
                case=case,
                arm=arm,
            )
            case_receipt["arms"][arm] = arm_receipt
            _write_receipt(output, receipt)
            print(
                f"[A132 {case_index}/{len(dataset.cases)}] finished {case.case_id} "
                f"{arm} status={arm_receipt['status']} calls={arm_receipt['model_request_count']} "
                f"tools={arm_receipt['tool_call_count']} tokens={arm_receipt['usage']['total_tokens']}",
                file=sys.stderr,
                flush=True,
            )

        judge, comparison = _run_judge(
            judge_model=judge_model,
            case=case,
            baseline=case_receipt["arms"][_BASELINE],
            candidate=case_receipt["arms"][_CANDIDATE],
        )
        case_receipt["judge"] = judge
        case_receipt["comparison"] = comparison.model_dump(mode="json")
        comparisons.append(comparison)
        _write_receipt(output, receipt)
        print(
            f"[A132 {case_index}/{len(dataset.cases)}] judged {case.case_id} preferred={comparison.preferred_arm} scores={comparison.baseline_score}:{comparison.candidate_score}",
            file=sys.stderr,
            flush=True,
        )

    promotion = decide_full_agent_promotion(comparisons)
    receipt.update(
        {
            "status": "completed",
            "completed_at": datetime.now(UTC).isoformat(),
            "comparisons": [item.model_dump(mode="json") for item in comparisons],
            "promotion": promotion.model_dump(mode="json"),
            "runtime_promotion_status": ("manual_review_required" if promotion.promote else "not_eligible"),
        }
    )
    _write_receipt(output, receipt)
    return receipt


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the tool-consistent full-DeerFlow business-attention A/B.")
    parser.add_argument("--model", default=_DEFAULT_MODEL)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--preflight", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    receipt = (
        preflight()
        if args.preflight
        else run_experiment(
            model_name=args.model,
            output=args.output,
        )
    )
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
