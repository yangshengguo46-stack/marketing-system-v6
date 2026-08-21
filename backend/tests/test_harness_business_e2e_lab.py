from __future__ import annotations

from collections.abc import Callable
from unittest.mock import MagicMock

from langchain_core.messages import SystemMessage
from pydantic import BaseModel

from deerflow.client import StreamEvent
from experiments.harness_business_e2e_lab.context import build_business_attention_context
from experiments.harness_business_e2e_lab.datasets import load_harness_business_e2e_cases
from experiments.harness_business_e2e_lab.evaluation import (
    FullAgentCaseComparison,
    decide_full_agent_promotion,
)
from experiments.harness_business_e2e_lab.middleware import BusinessAttentionProbeMiddleware
from experiments.harness_business_e2e_lab.observation import collect_agent_stream, detect_repetitive_answer
from experiments.harness_business_e2e_lab.run import preflight


def _request(system_text: str, tool_names: tuple[str, ...] = ("read_file", "web_search")):
    request = MagicMock()
    request.system_message = SystemMessage(content=system_text)
    request.messages = []
    request.tools = [MagicMock(name=name) for name in tool_names]
    for tool, name in zip(request.tools, tool_names, strict=True):
        tool.name = name

    def override(**updates):
        clone = _request(system_text, tool_names)
        clone.system_message = updates.get("system_message", request.system_message)
        clone.messages = updates.get("messages", request.messages)
        clone.tools = updates.get("tools", request.tools)
        return clone

    request.override = override
    return request


def test_attention_context_is_thin_generic_and_strengthens_business_chain() -> None:
    context = build_business_attention_context()

    assert len(context.encode("utf-8")) <= 3_072
    assert "谁会看到" in context
    assert "为什么会回来" in context
    assert "人际或组织行为" in context
    assert "事实" in context
    assert "固定流程" not in context
    for leaked_term in ("黄金", "水果", "婚礼", "机器人", "电梯", "宠物", "保密培训"):
        assert leaked_term not in context


def test_probe_middleware_changes_only_candidate_system_context() -> None:
    baseline = BusinessAttentionProbeMiddleware(arm="current_full")
    candidate = BusinessAttentionProbeMiddleware(
        arm="focused_business",
        attention_context="<business_attention>look wider</business_attention>",
    )

    baseline_seen = []
    candidate_seen = []
    baseline.wrap_model_call(_request("base prompt"), lambda req: baseline_seen.append(req) or "ok")
    candidate.wrap_model_call(_request("base prompt"), lambda req: candidate_seen.append(req) or "ok")

    assert baseline_seen[0].system_message.content == "base prompt"
    assert candidate_seen[0].system_message.content == ("base prompt\n\n<business_attention>look wider</business_attention>")
    assert baseline.observations[0].base_system_hash == candidate.observations[0].base_system_hash
    assert baseline.observations[0].tool_names == candidate.observations[0].tool_names
    assert baseline.observations[0].tool_schema_hash == candidate.observations[0].tool_schema_hash
    assert baseline.observations[0].model_class == candidate.observations[0].model_class
    assert baseline.observations[0].attention_hash is None
    assert candidate.observations[0].attention_hash is not None


def test_probe_middleware_never_duplicates_existing_attention_marker() -> None:
    context = "<business_attention>look wider</business_attention>"
    middleware = BusinessAttentionProbeMiddleware(
        arm="focused_business",
        attention_context=context,
    )
    captured = []

    middleware.wrap_model_call(
        _request(f"base prompt\n\n{context}"),
        lambda req: captured.append(req) or "ok",
    )

    assert captured[0].system_message.content.count("<business_attention>") == 1


def test_probe_observability_never_breaks_on_unserializable_tool_schema() -> None:
    class CallableArgs(BaseModel):
        callback: Callable[[], None]

    request = _request("base prompt", ("callable_tool",))
    request.tools[0].args_schema = CallableArgs
    middleware = BusinessAttentionProbeMiddleware(arm="current_full")

    result = middleware.wrap_model_call(request, lambda req: "model-result")

    assert result == "model-result"
    assert middleware.observations[0].tool_schema_hash


def test_dataset_uses_new_held_out_cases_and_keeps_known_gold_diagnostic_only() -> None:
    dataset = load_harness_business_e2e_cases()
    held_out = [case for case in dataset.cases if case.split == "held_out"]
    diagnostics = [case for case in dataset.cases if case.split == "diagnostic"]

    assert len(held_out) >= 6
    assert {case.case_id for case in diagnostics} == {"diagnostic-golden-gift-full-agent"}
    assert len({case.case_id for case in dataset.cases}) == len(dataset.cases)
    for case in held_out:
        assert all(term not in case.prompt for term in ("黄金礼品", "水果店", "宠物纪念", "工业机器人"))


def test_repetition_detector_flags_intent_loops_without_punishing_normal_answers() -> None:
    repeated = "\n".join(["我先检查一下匹配的技能。"] * 12)
    normal = "先判断谁会看到内容，再说明为什么会持续关注，最后解释信任如何回到业务。"

    assert detect_repetitive_answer(repeated) is True
    assert detect_repetitive_answer(normal) is False


def test_stream_collector_keeps_final_answer_tools_usage_and_clarification_fallback() -> None:
    events = [
        StreamEvent(
            type="messages-tuple",
            data={
                "type": "ai",
                "id": "planning",
                "content": "我先核实。",
            },
        ),
        StreamEvent(
            type="messages-tuple",
            data={
                "type": "ai",
                "id": "tool-call",
                "content": "",
                "tool_calls": [{"name": "web_search", "args": {}, "id": "call-1"}],
            },
        ),
        StreamEvent(
            type="messages-tuple",
            data={
                "type": "tool",
                "name": "web_search",
                "content": "evidence",
                "id": "result-1",
                "tool_call_id": "call-1",
            },
        ),
        StreamEvent(
            type="messages-tuple",
            data={"type": "ai", "id": "final", "content": "长期内容世界是"},
        ),
        StreamEvent(
            type="messages-tuple",
            data={"type": "ai", "id": "final", "content": "用户反复面对的问题。"},
        ),
        StreamEvent(
            type="end",
            data={"usage": {"input_tokens": 100, "output_tokens": 20, "total_tokens": 120}},
        ),
    ]

    receipt = collect_agent_stream(events)

    assert receipt.answer == "长期内容世界是用户反复面对的问题。"
    assert receipt.tool_calls == ("web_search",)
    assert receipt.tool_result_count == 1
    assert receipt.usage.total_tokens == 120
    assert receipt.termination_reason == "completed"
    assert receipt.valid is True

    clarification = collect_agent_stream(
        [
            StreamEvent(
                type="messages-tuple",
                data={
                    "type": "tool",
                    "name": "ask_clarification",
                    "content": "你的客户主要是个人还是企业？",
                    "id": "clarify-result",
                    "tool_call_id": "clarify-call",
                },
            ),
            StreamEvent(type="end", data={"usage": {}}),
        ]
    )
    assert clarification.answer == "你的客户主要是个人还是企业？"
    assert clarification.answer_source == "clarification"
    assert clarification.termination_reason == "clarification"
    assert clarification.valid is True

    framework_failure = collect_agent_stream(
        [
            StreamEvent(
                type="messages-tuple",
                data={
                    "type": "ai",
                    "id": "failure",
                    "content": "LLM request failed: provider schema error",
                },
            ),
            StreamEvent(type="end", data={"usage": {}}),
        ]
    )
    assert framework_failure.valid is False
    assert framework_failure.termination_reason == "framework_error"


def test_full_agent_promotion_requires_real_gain_and_identical_initial_tools() -> None:
    passing = [
        FullAgentCaseComparison(
            case_id=f"held-{index}",
            split="held_out",
            baseline_score=9,
            candidate_score=11,
            preferred_arm="focused_business",
            baseline_fact_boundary_pass=True,
            candidate_fact_boundary_pass=True,
            initial_tools_match=True,
            initial_tool_schema_match=True,
            base_system_match=True,
            model_contract_match=True,
            baseline_valid=True,
            candidate_valid=True,
            judge_valid=True,
        )
        for index in range(6)
    ]

    decision = decide_full_agent_promotion(passing)

    assert decision.promote is True
    invalid = list(passing)
    invalid[0] = invalid[0].model_copy(update={"initial_tools_match": False})
    invalid_decision = decide_full_agent_promotion(invalid)

    assert invalid_decision.promote is False
    assert "tool_contract_mismatch" in invalid_decision.reasons

    schema_invalid = list(passing)
    schema_invalid[0] = schema_invalid[0].model_copy(update={"initial_tool_schema_match": False})
    assert "tool_schema_contract_mismatch" in decide_full_agent_promotion(schema_invalid).reasons

    prompt_invalid = list(passing)
    prompt_invalid[0] = prompt_invalid[0].model_copy(update={"base_system_match": False})
    assert "base_prompt_mismatch" in decide_full_agent_promotion(prompt_invalid).reasons

    model_invalid = list(passing)
    model_invalid[0] = model_invalid[0].model_copy(update={"model_contract_match": False})
    assert "model_contract_mismatch" in decide_full_agent_promotion(model_invalid).reasons

    judge_invalid = list(passing)
    judge_invalid[0] = judge_invalid[0].model_copy(update={"judge_valid": False})
    assert "judge_failed" in decide_full_agent_promotion(judge_invalid).reasons


def test_full_agent_preflight_freezes_only_one_candidate_difference() -> None:
    receipt = preflight()

    assert receipt["held_out_count"] == 6
    assert receipt["diagnostic_count"] == 1
    assert receipt["baseline_attention_hash"] is None
    assert receipt["candidate_attention_hash"]
    assert receipt["candidate_attention_bytes"] <= 3_072
    assert receipt["same_model"] is True
    assert receipt["same_tools_and_skills_required"] is True
    assert receipt["enabled_skill_manifest_hash"]
    assert receipt["enabled_skill_count"] > 0
