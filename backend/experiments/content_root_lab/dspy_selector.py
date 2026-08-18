from __future__ import annotations

import hashlib
import importlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from experiments.content_root_lab.contracts import ContentRootGraph
from experiments.content_root_lab.datasets import DevelopmentPreference
from experiments.content_root_lab.evaluation import normalize_label


@dataclass(frozen=True)
class CompiledDSPySelector:
    program: Any
    lm: Any
    state_sha256: str
    compile_calls: int
    compile_usage: dict[str, int]


@dataclass(frozen=True)
class DSPySelection:
    selected_candidate_id: str
    rationale: str
    inference_calls: int
    inference_usage: dict[str, int]


def render_dspy_graph_input(graph: ContentRootGraph) -> str:
    payload = {
        "subject_expression": graph.subject_expression,
        "commercial_object": graph.commercial_object,
        "relations": [item.model_dump(mode="json") for item in graph.relations],
        "candidates": [item.model_dump(mode="json") for item in graph.candidates],
        "unknowns": graph.unknowns,
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def compile_dspy_selector(
    *,
    model_name: str,
    development_examples: tuple[DevelopmentPreference, ...],
) -> CompiledDSPySelector:
    dspy = _load_dspy()
    lm = _create_lm(dspy, model_name)
    dspy.configure(lm=lm)

    class SelectFrozenContentRoot(dspy.Signature):
        """
        从冻结候选中选择最大有效内容世界。候选必须与业务有可返回的语义路径，能长期展开具体的人、
        地方、时间、事件、行为、关系与变化，但不能泛化成任何行业都能套用的大词。对象本身足够丰富时可以
        获胜。卖方获客、销售、门店经营或制作流程通常不是观众长期内容世界。不得创造或改名候选，只输出其中一个
        candidate_id。
        """

        frozen_graph_json: str = dspy.InputField(desc="包含候选 ID、语义路径、内容容量与限制的冻结图")
        selected_candidate_id: str = dspy.OutputField(desc="必须精确复制一个冻结 candidate_id")
        rationale: str = dspy.OutputField(desc="简要比较其为何是最大有效世界")

    student = dspy.Predict(SelectFrozenContentRoot)
    trainset = [
        dspy.Example(
            frozen_graph_json=_render_development_input(example),
            selected_candidate_id=example.preferred_candidate_id,
            rationale=example.preference_reason,
        ).with_inputs("frozen_graph_json")
        for example in development_examples
    ]

    def exact_candidate_metric(example, prediction, trace=None) -> bool:
        del trace
        return normalize_label(str(prediction.selected_candidate_id)) == normalize_label(str(example.selected_candidate_id))

    before_calls = len(lm.history)
    before_usage = _history_usage(lm.history)
    optimizer = dspy.BootstrapFewShot(
        metric=exact_candidate_metric,
        max_bootstrapped_demos=min(2, len(trainset)),
        max_labeled_demos=min(5, len(trainset)),
        max_rounds=1,
        max_errors=2,
    )
    compiled = optimizer.compile(student, trainset=trainset)
    after_usage = _history_usage(lm.history)
    state = json.dumps(
        compiled.dump_state(),
        ensure_ascii=False,
        sort_keys=True,
        default=str,
        separators=(",", ":"),
    )
    return CompiledDSPySelector(
        program=compiled,
        lm=lm,
        state_sha256=hashlib.sha256(state.encode("utf-8")).hexdigest(),
        compile_calls=len(lm.history) - before_calls,
        compile_usage=_usage_delta(before_usage, after_usage),
    )


def run_dspy_selector(
    compiled: CompiledDSPySelector,
    graph: ContentRootGraph,
) -> DSPySelection:
    before_calls = len(compiled.lm.history)
    before_usage = _history_usage(compiled.lm.history)
    prediction = compiled.program(frozen_graph_json=render_dspy_graph_input(graph))
    raw_candidate_id = str(prediction.selected_candidate_id).strip().strip("`'\"")
    candidate_ids = {candidate.candidate_id for candidate in graph.candidates}
    selected_candidate_id = next(
        (candidate_id for candidate_id in candidate_ids if normalize_label(raw_candidate_id) == normalize_label(candidate_id)),
        None,
    )
    if selected_candidate_id is None:
        raise ValueError("DSPy selector returned a candidate outside the frozen graph")
    after_usage = _history_usage(compiled.lm.history)
    return DSPySelection(
        selected_candidate_id=selected_candidate_id,
        rationale=str(prediction.rationale).strip(),
        inference_calls=len(compiled.lm.history) - before_calls,
        inference_usage=_usage_delta(before_usage, after_usage),
    )


def _render_development_input(example: DevelopmentPreference) -> str:
    payload = {
        "subject_expression": example.subject_expression,
        "candidates": [item.model_dump(mode="json") for item in example.candidates],
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _create_lm(dspy: Any, model_name: str) -> Any:
    from deerflow.config.app_config import get_app_config
    from deerflow.models import create_chat_model

    app_config = get_app_config()
    if app_config.get_model_config(model_name) is None:
        raise ValueError(f"unknown configured model: {model_name}")

    chat_model = create_chat_model(
        name=model_name,
        thinking_enabled=False,
        app_config=app_config,
        attach_tracing=False,
        model_overrides={"temperature": 0},
    )

    class DeerFlowDSPyLM(dspy.BaseLM):
        forward_contract = "typed_lm"

        def __init__(self) -> None:
            super().__init__(
                model=f"deerflow/{model_name}",
                model_type="chat",
                temperature=0,
                max_tokens=1_600,
                cache=False,
                num_retries=1,
            )

        def forward(self, request):
            from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

            message_types = {
                "assistant": AIMessage,
                "system": SystemMessage,
                "user": HumanMessage,
            }
            messages = [message_types.get(message.role, HumanMessage)(content=message.text) for message in request.messages]
            response = chat_model.invoke(messages)
            text = _extract_langchain_text(response)
            if not text:
                raise ValueError("DeerFlow DSPy adapter received an empty model response")
            return dspy.LMResponse.from_text(
                text,
                model=self.model,
                usage=_extract_langchain_usage(response),
            )

    return DeerFlowDSPyLM()


def _extract_langchain_text(response: Any) -> str:
    content = getattr(response, "content", response)
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for block in content:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict) and isinstance(block.get("text"), str):
            parts.append(block["text"])
    return "\n".join(parts).strip()


def _extract_langchain_usage(response: Any) -> dict[str, int]:
    usage = getattr(response, "usage_metadata", None)
    if not isinstance(usage, dict):
        metadata = getattr(response, "response_metadata", None)
        usage = metadata.get("token_usage", {}) if isinstance(metadata, dict) else {}
    input_tokens = int(usage.get("input_tokens", usage.get("prompt_tokens", 0)) or 0)
    output_tokens = int(usage.get("output_tokens", usage.get("completion_tokens", 0)) or 0)
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": int(usage.get("total_tokens", input_tokens + output_tokens) or 0),
    }


def _load_dspy() -> Any:
    try:
        return importlib.import_module("dspy")
    except ModuleNotFoundError as exc:
        raise RuntimeError("DSPy is an experiment-only dependency; run with uv --with 'dspy>=3.0,<4'.") from exc


def _history_usage(history: list[Any]) -> dict[str, int]:
    totals = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    for item in history:
        usage = item.get("usage") if isinstance(item, Mapping) else getattr(item, "usage", None)
        if not isinstance(usage, Mapping) and hasattr(usage, "model_dump"):
            usage = usage.model_dump()
        if not isinstance(usage, Mapping):
            continue
        totals["input_tokens"] += int(usage.get("prompt_tokens", usage.get("input_tokens", 0)) or 0)
        totals["output_tokens"] += int(usage.get("completion_tokens", usage.get("output_tokens", 0)) or 0)
        totals["total_tokens"] += int(usage.get("total_tokens", 0) or 0)
    if totals["total_tokens"] == 0:
        totals["total_tokens"] = totals["input_tokens"] + totals["output_tokens"]
    return totals


def _usage_delta(before: dict[str, int], after: dict[str, int]) -> dict[str, int]:
    return {key: after[key] - before[key] for key in before}


__all__ = [
    "CompiledDSPySelector",
    "DSPySelection",
    "compile_dspy_selector",
    "render_dspy_graph_input",
    "run_dspy_selector",
]
