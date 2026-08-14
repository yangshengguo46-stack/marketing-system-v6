from __future__ import annotations

import json
import logging
from enum import StrEnum
from typing import Annotated, Any

from langchain_core.messages import ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool, InjectedToolArg, InjectedToolCallId, StructuredTool
from langgraph.types import Command
from pydantic import BaseModel, Field, ValidationError

from deerflow.content_intelligence import (
    AnalysisFocus,
    ContentIntelligenceBundle,
    ContentIntelligenceRequest,
    SourceMaterial,
    analyze_content_intelligence,
    render_content_world_narration,
    synthesize_content_world_narration,
)
from deerflow.models import create_chat_model

logger = logging.getLogger(__name__)


class ToolAnalysisFocus(StrEnum):
    BUSINESS_SEMANTICS = "business_semantics"
    TOPIC_BRIEF = "topic_brief"


class _ContentIntelligenceToolInput(BaseModel):
    user_request: str = Field(description="The current user request, copied without adding requirements.")
    subject_expression: str = Field(description="The user's exact business, brand, product, expert, or content-subject expression.")
    focus: ToolAnalysisFocus = Field(
        default=ToolAnalysisFocus.BUSINESS_SEMANTICS,
        description="The view currently needed. This is not a mandatory workflow stage.",
    )
    source_materials: list[SourceMaterial] = Field(
        default_factory=list,
        description="Optional source excerpts already obtained from the user or evidence tools. Do not pass unsupported model claims as source material.",
    )


class _ExploreContentWorldToolInput(BaseModel):
    user_request: str = Field(description="The current broad account-starting or long-term-content request, copied without adding requirements.")
    subject_expression: str = Field(description="The user's exact business, brand, product, expert, or content-subject expression.")
    tool_call_id: Annotated[str, InjectedToolCallId]
    source_materials: list[SourceMaterial] = Field(
        default_factory=list,
        description="Optional source excerpts already obtained from the user or evidence tools. Do not pass unsupported model claims as source material.",
    )


def _create_content_intelligence_model(config: RunnableConfig):
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
    return create_chat_model(
        name=model_name,
        thinking_enabled=bool(runtime_options.get("thinking_enabled", False)),
        app_config=app_config,
        attach_tracing=False,
    )


async def _analyze_content_intelligence(
    user_request: str,
    subject_expression: str,
    focus: ToolAnalysisFocus = ToolAnalysisFocus.BUSINESS_SEMANTICS,
    source_materials: list[SourceMaterial] | None = None,
    config: Annotated[RunnableConfig, InjectedToolArg] = None,
) -> str:
    model = _create_content_intelligence_model(config)
    materials = tuple(material if isinstance(material, SourceMaterial) else SourceMaterial.model_validate(material) for material in (source_materials or []))
    request = ContentIntelligenceRequest(
        user_request=user_request,
        subject_expression=subject_expression,
        focus=AnalysisFocus(focus),
        source_materials=materials,
    )
    try:
        bundle = await analyze_content_intelligence(
            request,
            model=model,
            runnable_config=config,
        )
    except (ValidationError, ValueError) as exc:
        if isinstance(exc, ValidationError):
            logger.warning(
                "Content intelligence model output failed %d contract check(s).",
                len(exc.errors()),
            )
        else:
            logger.warning("Content intelligence model output was not recoverable: %s", type(exc).__name__)
        return (
            '{"status":"invalid_model_output","message":"The optional structured analysis was unavailable because its source or reference contract failed. '
            'Answer the current question directly, preserve unknowns, and do not invent the missing facts."}'
        )
    return json.dumps(_lead_projection(bundle, focus=request.focus), ensure_ascii=False, separators=(",", ":"))


async def _explore_content_world(
    user_request: str,
    subject_expression: str,
    tool_call_id: Annotated[str, InjectedToolCallId],
    source_materials: list[SourceMaterial] | None = None,
    config: Annotated[RunnableConfig, InjectedToolArg] = None,
) -> Command:
    model = _create_content_intelligence_model(config)
    materials = tuple(material if isinstance(material, SourceMaterial) else SourceMaterial.model_validate(material) for material in (source_materials or []))
    request = ContentIntelligenceRequest(
        user_request=user_request,
        subject_expression=subject_expression,
        focus=AnalysisFocus.CONTENT_WORLD,
        source_materials=materials,
    )
    try:
        bundle = await analyze_content_intelligence(
            request,
            model=model,
            runnable_config=config,
        )
        narration = await synthesize_content_world_narration(
            bundle,
            model=model,
            runnable_config=config,
        )
        return _terminal_content_world_command(
            render_content_world_narration(bundle, narration),
            tool_call_id=tool_call_id,
        )
    except (ValidationError, ValueError) as exc:
        if isinstance(exc, ValidationError):
            logger.warning("Content-world direct answer failed %d contract check(s).", len(exc.errors()))
        else:
            logger.warning("Content-world direct answer was not recoverable: %s", type(exc).__name__)
        return _terminal_content_world_command(
            "这次内容世界分析没有通过结构校验，因此没有用不可核验的结果替你补出起号方案。",
            tool_call_id=tool_call_id,
        )


def _terminal_content_world_command(content: str, *, tool_call_id: str) -> Command:
    return Command(
        update={
            "messages": [
                ToolMessage(
                    id=f"{tool_call_id}:result",
                    content=content,
                    tool_call_id=tool_call_id,
                    name="explore_content_world",
                    additional_kwargs={
                        "hide_from_ui": True,
                        "deerflow_direct_response": True,
                    },
                ),
            ]
        },
    )


def _lead_projection(
    bundle: ContentIntelligenceBundle,
    *,
    focus: AnalysisFocus | None = None,
) -> dict[str, Any]:
    semantics = bundle.business_semantics
    world = bundle.content_world
    topic = bundle.topic_brief
    if focus == AnalysisFocus.CONTENT_WORLD and world is not None:
        return {
            "status": "ok",
            "record_id": bundle.record.record_id,
            "record_fingerprint": bundle.record.fingerprint(),
            "subject_expression": bundle.record.subject_expression,
            "semantic_transition": (
                {
                    "commercial_object": semantics.commercial_object.text if semantics and semantics.commercial_object else None,
                    "lexical_head": semantics.lexical_head.text if semantics and semantics.lexical_head else None,
                    "modifier_removals": [
                        {
                            "modifier": item.modifier,
                            "modifies": item.modifies,
                            "removal_counterfactual": item.removal_counterfactual,
                        }
                        for item in semantics.modifiers
                    ]
                    if semantics
                    else [],
                }
            ),
            "content_world": {
                "audience_territory": world.audience_territory.text if world.audience_territory else None,
                "content_root": world.content_root,
                "map_directions": [
                    {
                        "dimension": dimension.name,
                        "status": "research_direction",
                        "directions": [path.steps[-1].to_label for path in dimension.paths],
                    }
                    for dimension in world.dimensions
                ],
                "named_candidates": [
                    {
                        "name": item.name,
                        "connection": item.connection,
                        "verification_query": item.verification_query,
                        "limitations": list(item.limitations),
                    }
                    for item in world.named_candidates
                ],
            },
            "scope": {
                "answer_subject": world.content_root,
                "map_axis": world.content_root,
                "supports": [
                    "semantic transition",
                    "content root",
                    "audience territory",
                    "research directions",
                ],
                "does_not_support": [
                    "unrequested downstream operating plan",
                    "platform choice",
                    "presentation format",
                    "posting cadence",
                    "numeric quota",
                    "sales plan",
                    "experiment design",
                ],
            },
        }
    return {
        "status": "ok",
        "record_id": bundle.record.record_id,
        "record_fingerprint": bundle.record.fingerprint(),
        "subject_expression": bundle.record.subject_expression,
        "business_semantics": (
            {
                "commercial_object": semantics.commercial_object.text if semantics.commercial_object else None,
                "lexical_head": semantics.lexical_head.text if semantics.lexical_head else None,
                "modifiers": [
                    {
                        "modifier": item.modifier,
                        "modifies": item.modifies,
                        "semantic_role": item.semantic_role,
                        "removal_counterfactual": item.removal_counterfactual,
                    }
                    for item in semantics.modifiers
                ],
                "offering_role": semantics.offering_role,
                "role_rationale": semantics.role_rationale,
                "served_objects": [item.text for item in semantics.served_objects],
                "served_activities": [item.text for item in semantics.served_activities],
                "defining_functions_or_uses": [item.text for item in semantics.defining_functions_or_uses],
                "social_or_cultural_frames": [item.text for item in semantics.social_or_cultural_frames],
                "seller_actions": [item.text for item in semantics.subject_actions],
                "summary": semantics.summary,
            }
            if semantics
            else None
        ),
        "content_world": (
            {
                "source_object": world.source_object,
                "audience_territory": world.audience_territory.text if world.audience_territory else None,
                "content_root": world.content_root,
                "root_rationale": world.root_rationale,
                "root_candidates": [
                    {
                        "label": item.label,
                        "relation_to_business": item.relation_to_business,
                        "strength": item.strength,
                        "overreach_risk": item.overreach_risk,
                    }
                    for item in world.root_candidates
                ],
                "map_directions": [
                    {
                        "dimension": dimension.name,
                        "status": "research_direction",
                        "directions": [path.steps[-1].to_label for path in dimension.paths],
                    }
                    for dimension in world.dimensions
                ],
                "named_candidates": [
                    {
                        "name": item.name,
                        "connection": item.connection,
                        "verification_query": item.verification_query,
                        "limitations": list(item.limitations),
                    }
                    for item in world.named_candidates
                ],
            }
            if world
            else None
        ),
        "topic_brief": (
            {
                "question": topic.question,
                "central_claim": topic.central_claim,
                "mechanism": topic.mechanism,
                "counterpoint": topic.counterpoint,
                "research_needed": list(topic.research_needed),
            }
            if topic
            else None
        ),
        "unknowns": [item.question for item in bundle.record.unknowns],
        "scope": {
            "supports": [
                "business semantics",
                "content root",
                "audience territory",
                "research directions",
            ],
            "does_not_support": [
                "platform choice",
                "presentation format",
                "posting cadence",
                "numeric quota",
                "sales plan",
                "experiment design",
            ],
        },
    }


content_intelligence_tool: BaseTool = StructuredTool.from_function(
    name="analyze_content_intelligence",
    description=(
        "Optional structured reading workspace for understanding a business expression or a concrete topic. "
        "It separates source observations, interpretations, hypotheses, counterevidence, and unknowns, then returns a compact projection over one shared record. "
        "Use explore_content_world instead for broad account-starting or long-term-content requests. The Lead retains final judgment for this non-direct tool."
    ),
    coroutine=_analyze_content_intelligence,
    args_schema=_ContentIntelligenceToolInput,
)


explore_content_world_tool: BaseTool = StructuredTool.from_function(
    name="explore_content_world",
    description=(
        "Direct content-world answer for a broad account-starting, positioning, or long-term-content request. "
        "It delegates semantic reading, content-root selection, pure map expansion, and bounded editorial convergence to isolated specialists. "
        "Use it when the current answer should decide what human or object world the account can keep talking about. "
        "It stops at the content-world judgment and does not continue into downstream operations such as platform, presentation format, posting cadence, sales, experiments, or questionnaires."
    ),
    coroutine=_explore_content_world,
    args_schema=_ExploreContentWorldToolInput,
    return_direct=True,
)
