from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable, Mapping
from typing import Any

from experiments.harness_business_e2e_lab.contracts import (
    CollectedAgentStream,
    TokenUsage,
)

_UNIT_SPLIT = re.compile(r"[\n。！？!?]+")
_FRAMEWORK_ERROR_PREFIXES = (
    "LLM request failed:",
    "Agent failed:",
    "Model request failed:",
)


def detect_repetitive_answer(answer: str) -> bool:
    """Detect obvious repeated-intent loops without judging ordinary repetition."""

    units = [re.sub(r"\s+", "", unit) for unit in _UNIT_SPLIT.split(answer) if unit.strip()]
    if len(units) < 6:
        return False
    most_common = Counter(units).most_common(1)[0][1]
    return most_common >= 4 and most_common / len(units) >= 0.5


def _usage(payload: Any) -> TokenUsage:
    if not isinstance(payload, Mapping):
        return TokenUsage()
    input_tokens = int(payload.get("input_tokens", payload.get("prompt_tokens", 0)) or 0)
    output_tokens = int(payload.get("output_tokens", payload.get("completion_tokens", 0)) or 0)
    total_tokens = int(payload.get("total_tokens", input_tokens + output_tokens) or 0)
    return TokenUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
    )


def collect_agent_stream(events: Iterable[Any]) -> CollectedAgentStream:
    """Collect a DeerFlow stream without persisting tool arguments or results."""

    chunks: dict[str, list[str]] = {}
    last_text_id = ""
    clarification = ""
    tool_calls: list[str] = []
    tool_result_count = 0
    tool_failure_count = 0
    usage = TokenUsage()

    for event in events:
        event_type = getattr(event, "type", None)
        data = getattr(event, "data", {})
        if not isinstance(data, Mapping):
            continue
        if event_type == "messages-tuple" and data.get("type") == "ai":
            for call in data.get("tool_calls", ()) or ():
                if isinstance(call, Mapping) and isinstance(call.get("name"), str):
                    tool_calls.append(call["name"])
            content = data.get("content")
            if isinstance(content, str) and content:
                message_id = str(data.get("id") or "")
                chunks.setdefault(message_id, []).append(content)
                last_text_id = message_id
        elif event_type == "messages-tuple" and data.get("type") == "tool":
            tool_result_count += 1
            content = data.get("content")
            text = content if isinstance(content, str) else ""
            if text.lstrip().lower().startswith(("error", "failed", "tool error")):
                tool_failure_count += 1
            if data.get("name") == "ask_clarification" and text.strip():
                clarification = text.strip()
        elif event_type == "end":
            usage = _usage(data.get("usage"))

    assistant_answer = "".join(chunks.get(last_text_id, ())).strip()
    if assistant_answer:
        answer = assistant_answer
        answer_source = "assistant"
    elif clarification:
        answer = clarification
        answer_source = "clarification"
    else:
        answer = ""
        answer_source = "none"
    repetitive = detect_repetitive_answer(answer)
    framework_error = answer.lstrip().startswith(_FRAMEWORK_ERROR_PREFIXES)
    if framework_error:
        termination_reason = "framework_error"
    elif repetitive:
        termination_reason = "repetitive"
    elif answer_source == "clarification":
        termination_reason = "clarification"
    elif answer:
        termination_reason = "completed"
    else:
        termination_reason = "empty"
    return CollectedAgentStream(
        answer=answer,
        answer_source=answer_source,
        tool_calls=tuple(tool_calls),
        tool_result_count=tool_result_count,
        tool_failure_count=tool_failure_count,
        usage=usage,
        repetitive=repetitive,
        valid=bool(answer) and not repetitive and not framework_error,
        termination_reason=termination_reason,
    )
