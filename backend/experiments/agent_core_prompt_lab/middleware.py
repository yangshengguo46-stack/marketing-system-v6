from __future__ import annotations

import hashlib
import json
from collections.abc import Awaitable, Callable
from typing import Any, override

from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ModelCallResult, ModelRequest, ModelResponse
from langchain_core.messages import SystemMessage
from langchain_core.utils.function_calling import convert_to_openai_tool

from deerflow.agents.lead_agent.agent_core_contract import apply_agent_core_candidate
from experiments.agent_core_prompt_lab.contracts import CoreModelRequestObservation


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
            else:
                parts.append(str(item))
        return "\n".join(parts)
    return str(content)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _tool_names(request: ModelRequest) -> tuple[str, ...]:
    return tuple(name for tool in list(getattr(request, "tools", ()) or ()) if isinstance((name := getattr(tool, "name", None)), str) and name)


def _tool_schema_hash(request: ModelRequest) -> str:
    payload = []
    for tool in list(getattr(request, "tools", ()) or ()):
        try:
            payload.append(convert_to_openai_tool(tool))
        except Exception as exc:
            payload.append(
                {
                    "name": str(getattr(tool, "name", "")),
                    "schema_unavailable": type(exc).__name__,
                }
            )
    rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return _sha256(rendered)


def _model_contract(request: ModelRequest) -> tuple[str, str]:
    model = getattr(request, "model", None)
    model_class = f"{type(model).__module__}.{type(model).__qualname__}"
    payload: dict[str, Any] = {"class": model_class}
    for field in ("model_name", "model", "temperature", "reasoning_effort"):
        value = getattr(model, field, None)
        if isinstance(value, (str, int, float, bool)) or value is None:
            payload[field] = value
    rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return model_class, _sha256(rendered)


class AgentCoreProbeMiddleware(AgentMiddleware):
    """Replace only the candidate core contract and record model-visible parity."""

    def __init__(self, *, arm: str, max_model_calls: int = 12) -> None:
        super().__init__()
        if arm not in {"current_full", "agent_core_candidate"}:
            raise ValueError(f"unknown A138 arm: {arm}")
        if max_model_calls < 1:
            raise ValueError("max_model_calls must be positive")
        self.arm = arm
        self.max_model_calls = max_model_calls
        self.observations: list[CoreModelRequestObservation] = []

    def _prepare(self, request: ModelRequest) -> ModelRequest:
        if len(self.observations) >= self.max_model_calls:
            raise RuntimeError("A138 model call budget exceeded")
        current = request.system_message
        base_text = _content_text(current.content) if current is not None else ""
        final_text = apply_agent_core_candidate(base_text) if self.arm == "agent_core_candidate" else base_text
        if final_text != base_text:
            current = SystemMessage(
                content=final_text,
                id=getattr(current, "id", None),
                additional_kwargs=dict(getattr(current, "additional_kwargs", {}) or {}),
            )
            request = request.override(system_message=current)

        model_class, model_contract_hash = _model_contract(request)
        self.observations.append(
            CoreModelRequestObservation(
                arm=self.arm,
                call_index=len(self.observations) + 1,
                base_system_hash=_sha256(base_text),
                final_system_hash=_sha256(final_text),
                base_system_bytes=len(base_text.encode("utf-8")),
                final_system_bytes=len(final_text.encode("utf-8")),
                tool_names=_tool_names(request),
                tool_schema_hash=_tool_schema_hash(request),
                model_class=model_class,
                model_contract_hash=model_contract_hash,
                message_count=len(list(request.messages)),
            )
        )
        return request

    @override
    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelCallResult:
        return handler(self._prepare(request))

    @override
    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelCallResult:
        return await handler(self._prepare(request))
