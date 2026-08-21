from __future__ import annotations

import hashlib
import json
from collections.abc import Awaitable, Callable
from typing import Any, override

from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ModelCallResult, ModelRequest, ModelResponse
from langchain_core.messages import SystemMessage
from langchain_core.utils.function_calling import convert_to_openai_tool

from experiments.harness_business_e2e_lab.contracts import ModelRequestObservation

_ATTENTION_MARKER = "<business_attention>"


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
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
    names = []
    for tool in list(getattr(request, "tools", ()) or ()):
        name = getattr(tool, "name", None)
        if isinstance(name, str) and name:
            names.append(name)
    return tuple(names)


def _tool_schema_hash(request: ModelRequest) -> str:
    payload = []
    for tool in list(getattr(request, "tools", ()) or ()):
        name = getattr(tool, "name", None)
        description = getattr(tool, "description", None)
        try:
            schema = convert_to_openai_tool(tool)
        except Exception as exc:
            # Observability must never break a valid Agent call. The fallback
            # remains deterministic and makes an unconvertible schema visible
            # in the contract hash without serializing the exception message.
            schema = {
                "name": name if isinstance(name, str) else "",
                "description": description if isinstance(description, str) else "",
                "schema_unavailable": type(exc).__name__,
            }
        payload.append(schema)
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


class BusinessAttentionProbeMiddleware(AgentMiddleware):
    """Add candidate context and record the actual model-visible request contract."""

    def __init__(self, *, arm: str, attention_context: str | None = None) -> None:
        super().__init__()
        self.arm = arm
        self.attention_context = attention_context.strip() if attention_context else None
        self.observations: list[ModelRequestObservation] = []

    def _prepare(self, request: ModelRequest) -> ModelRequest:
        current = request.system_message
        base_text = _content_text(current.content) if current is not None else ""
        final_text = base_text
        if self.attention_context and _ATTENTION_MARKER not in base_text:
            final_text = f"{base_text}\n\n{self.attention_context}" if base_text else self.attention_context
            current = SystemMessage(
                content=final_text,
                id=getattr(current, "id", None),
                additional_kwargs=dict(getattr(current, "additional_kwargs", {}) or {}),
            )
            request = request.override(system_message=current)

        model_class, model_contract_hash = _model_contract(request)
        self.observations.append(
            ModelRequestObservation(
                arm=self.arm,
                call_index=len(self.observations) + 1,
                base_system_hash=_sha256(base_text),
                final_system_hash=_sha256(final_text),
                base_system_bytes=len(base_text.encode("utf-8")),
                final_system_bytes=len(final_text.encode("utf-8")),
                attention_hash=_sha256(self.attention_context) if self.attention_context else None,
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
