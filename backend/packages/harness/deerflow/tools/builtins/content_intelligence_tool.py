from __future__ import annotations

import logging
from typing import Annotated, Any

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool, InjectedToolArg, StructuredTool
from pydantic import BaseModel, Field, ValidationError

from deerflow.content_intelligence import (
    AnalysisFocus,
    ContentIntelligenceRequest,
    SourceMaterial,
    analyze_content_intelligence,
)
from deerflow.models import create_chat_model

logger = logging.getLogger(__name__)


class _ContentIntelligenceToolInput(BaseModel):
    user_request: str = Field(description="The current user request, copied without adding requirements.")
    subject_expression: str = Field(description="The user's exact business, brand, product, expert, or content-subject expression.")
    focus: AnalysisFocus = Field(
        default=AnalysisFocus.COMBINED,
        description="The view currently needed. This is not a mandatory workflow stage.",
    )
    source_materials: list[SourceMaterial] = Field(
        default_factory=list,
        description="Optional source excerpts already obtained from the user or evidence tools. Do not pass unsupported model claims as source material.",
    )


async def _analyze_content_intelligence(
    user_request: str,
    subject_expression: str,
    focus: AnalysisFocus = AnalysisFocus.COMBINED,
    source_materials: list[SourceMaterial] | None = None,
    config: Annotated[RunnableConfig, InjectedToolArg] = None,
) -> str:
    from deerflow.config.app_config import get_app_config

    app_config = get_app_config()
    runtime_options: dict[str, Any] = {}
    for section_name in ("configurable", "context"):
        section = (config or {}).get(section_name) or {}
        if isinstance(section, dict):
            runtime_options.update(section)

    model_name = runtime_options.get("model_name")
    if model_name is None or app_config.get_model_config(model_name) is None:
        model_name = app_config.models[0].name if app_config.models else None
    if model_name is None:
        raise ValueError("No chat models are configured for content intelligence analysis.")

    model = create_chat_model(
        name=model_name,
        thinking_enabled=bool(runtime_options.get("thinking_enabled", False)),
        app_config=app_config,
        attach_tracing=False,
    )
    materials = tuple(material if isinstance(material, SourceMaterial) else SourceMaterial.model_validate(material) for material in (source_materials or []))
    request = ContentIntelligenceRequest(
        user_request=user_request,
        subject_expression=subject_expression,
        focus=focus,
        source_materials=materials,
    )
    try:
        bundle = await analyze_content_intelligence(
            request,
            model=model,
            runnable_config=config,
        )
    except ValidationError as exc:
        logger.warning(
            "Content intelligence model output failed %d contract check(s).",
            len(exc.errors()),
        )
        return (
            '{"status":"invalid_model_output","message":"The optional structured analysis was unavailable because its source or reference contract failed. '
            'Answer the current question directly, preserve unknowns, and do not invent the missing facts."}'
        )
    return bundle.model_dump_json(exclude_none=True)


content_intelligence_tool: BaseTool = StructuredTool.from_function(
    name="analyze_content_intelligence",
    description=(
        "Optional structured reading workspace for understanding a business expression, a long-term content world, or a concrete topic. "
        "It separates source observations, interpretations, hypotheses, counterevidence, and unknowns, then returns only the requested views over one shared record. "
        "Use it when that structure materially improves the answer. The Lead retains final incubation and new-media judgment."
    ),
    coroutine=_analyze_content_intelligence,
    args_schema=_ContentIntelligenceToolInput,
)
