from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Any
from urllib.parse import urljoin

import httpx
from langchain_core.messages import ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool, InjectedToolArg, StructuredTool, tool
from langgraph.types import Command
from pydantic import BaseModel, Field, ValidationError

from deerflow.community.url_safety import validate_public_http_url
from deerflow.config.runtime_paths import runtime_home
from deerflow.content_intelligence import (
    AnalysisFocus,
    ContentIntelligenceBundle,
    ContentIntelligenceRequest,
    ResearchSearchResult,
    ShootingDelivery,
    SourceMaterial,
    analyze_content_intelligence,
    enrich_content_world_with_research,
    render_content_world_narration,
    render_shooting_delivery,
    synthesize_content_world_narration,
    synthesize_shooting_delivery,
)
from deerflow.content_intelligence.lexical_evidence import CedictLexicalEvidenceProvider
from deerflow.incubation import (
    EvidenceSnapshot,
    ProjectRef,
    seal_content_run_artifacts,
    seal_evidence_snapshot,
    select_used_topic_evidence_snapshots,
)
from deerflow.models import create_chat_model
from deerflow.tools.builtins.douyin_topic_evidence import DouyinMcpTopicEvidenceSearch
from deerflow.tools.types import Runtime
from deerflow.utils.readability import ReadabilityExtractor

logger = logging.getLogger(__name__)

_DIRECT_FETCH_MAX_BYTES = 2_000_000
_DIRECT_FETCH_MAX_REDIRECTS = 3
_DIRECT_FETCH_USER_AGENT = "Mozilla/5.0 (compatible; DeerFlowContentResearch/1.0)"
_direct_readability_extractor = ReadabilityExtractor()


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
        # The parent Lead may use provider thinking, but these bounded workers
        # expose their reasoning through typed intermediate records. Some
        # providers also reject structured tool choice while thinking is on.
        thinking_enabled=False,
        app_config=app_config,
        attach_tracing=False,
    )


def _create_lexical_evidence_provider() -> CedictLexicalEvidenceProvider | None:
    configured_path = os.getenv("CONTENT_INTELLIGENCE_CEDICT_INDEX", "").strip()
    index_path = configured_path or str(runtime_home() / "lexicons" / "cc-cedict.sqlite3")
    if not configured_path and not os.path.isfile(index_path):
        return None
    try:
        return CedictLexicalEvidenceProvider(index_path)
    except (OSError, ValueError, KeyError) as exc:
        logger.warning(
            "Configured lexical evidence index was unavailable; preserving the model-only path: %s",
            type(exc).__name__,
        )
        return None


def _get_incubation_repository():
    from deerflow.persistence.engine import get_session_factory
    from deerflow.persistence.incubation_ledger import IncubationLedgerRepository

    session_factory = get_session_factory()
    if session_factory is None:
        return None
    return IncubationLedgerRepository(session_factory)


def _runtime_context_text(runtime: Runtime, name: str) -> str | None:
    context = runtime.context or {}
    if not isinstance(context, dict):
        return None
    value = context.get(name)
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


async def _persist_content_run(
    *,
    bundle: ContentIntelligenceBundle,
    delivery: ShootingDelivery | None,
    runtime: Runtime,
    topic_evidence_snapshots: tuple[EvidenceSnapshot, ...],
) -> dict[str, Any]:
    project_id = _runtime_context_text(runtime, "incubation_project_id")
    if project_id is None:
        return {"status": "not_selected"}

    owner_user_id = _runtime_context_text(runtime, "user_id")
    thread_id = _runtime_context_text(runtime, "thread_id")
    run_id = _runtime_context_text(runtime, "run_id")
    failure = {
        "status": "failed",
        "project_id": project_id,
        "message": "The generated content could not be stored in the selected project.",
    }
    if owner_user_id is None or thread_id is None or run_id is None:
        return failure

    try:
        project = ProjectRef(
            owner_user_id=owner_user_id,
            project_id=project_id,
        )
        repository = _get_incubation_repository()
        if repository is None or await repository.get_project(project) is None:
            return failure
        selected_snapshots = select_used_topic_evidence_snapshots(
            bundle,
            topic_evidence_snapshots,
        )
        evidence_artifacts = {}
        for snapshot in selected_snapshots:
            artifact = seal_evidence_snapshot(
                project=project,
                snapshot=snapshot,
                source_thread_id=thread_id,
                source_run_id=run_id,
            )
            evidence_artifacts[artifact.artifact_id] = artifact
        stored_receipts: list[dict[str, str]] = []
        evidence_parents = []
        for artifact_id in sorted(evidence_artifacts):
            stored = await repository.put_artifact(evidence_artifacts[artifact_id])
            evidence_parents.append(stored.to_parent_ref())
            stored_receipts.append(
                {
                    "artifact_type": stored.artifact_type,
                    "artifact_id": stored.artifact_id,
                    "content_sha256": stored.content_sha256,
                }
            )
        sealed = seal_content_run_artifacts(
            project=project,
            bundle=bundle,
            delivery=delivery,
            created_at=datetime.now(UTC),
            source_thread_id=thread_id,
            source_run_id=run_id,
            reading_parents=tuple(evidence_parents),
        )
        for artifact in sealed.storage_order():
            stored = await repository.put_artifact(artifact)
            stored_receipts.append(
                {
                    "artifact_type": stored.artifact_type,
                    "artifact_id": stored.artifact_id,
                    "content_sha256": stored.content_sha256,
                }
            )
        return {
            "status": "stored",
            "project_id": project_id,
            "artifacts": stored_receipts,
        }
    except Exception as exc:
        logger.warning(
            "Content-run persistence failed: %s",
            type(exc).__name__,
        )
        return failure


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


@tool("explore_content_world", parse_docstring=True, return_direct=True)
async def explore_content_world_tool(
    runtime: Runtime,
    user_request: str,
) -> Command:
    """Build the long-term content world for a broad account-starting request.

    This directly answers what human or object world the account can keep
    talking about after bounded semantic reading, root selection, pure map
    expansion, research, and editorial convergence. It stops before platform,
    presentation format, cadence, sales, experiments, or questionnaires.

    Args:
        user_request: The current broad account-starting or long-term-content request, copied without adding requirements.
    """
    config = runtime.config
    tool_call_id = runtime.tool_call_id
    model = _create_content_intelligence_model(config)
    lexical_evidence_provider = _create_lexical_evidence_provider()
    request = ContentIntelligenceRequest(
        user_request=user_request,
        subject_expression=user_request,
        focus=AnalysisFocus.CONTENT_WORLD,
        source_materials=(),
    )
    douyin_topic_search = DouyinMcpTopicEvidenceSearch(runtime)

    async def search_content_evidence(
        query: str,
        max_results: int,
    ) -> tuple[ResearchSearchResult, ...]:
        return await _search_content_world_evidence(
            query,
            max_results,
            douyin_search=douyin_topic_search,
        )

    try:
        bundle = await analyze_content_intelligence(
            request,
            model=model,
            runnable_config=config,
            lexical_evidence_provider=lexical_evidence_provider,
        )
        try:
            bundle = await enrich_content_world_with_research(
                bundle,
                model=model,
                search=search_content_evidence,
                fetch=_fetch_content_world_evidence,
                runnable_config=config,
            )
        except Exception as exc:
            logger.warning(
                "Post-map research was unavailable; preserving the rooted map: %s",
                type(exc).__name__,
            )
        try:
            shooting_delivery = await synthesize_shooting_delivery(
                bundle,
                user_request=user_request,
                model=model,
                runnable_config=config,
            )
        except Exception as exc:
            logger.warning(
                "Evidence topic delivery was unavailable; preserving the rooted map: %s",
                type(exc).__name__,
            )
            shooting_delivery = None
        persistence = await _persist_content_run(
            bundle=bundle,
            delivery=shooting_delivery,
            runtime=runtime,
            topic_evidence_snapshots=douyin_topic_search.snapshots,
        )
        if shooting_delivery is not None:
            return _terminal_content_world_command(
                render_shooting_delivery(bundle, shooting_delivery),
                tool_call_id=tool_call_id,
                persistence=persistence,
            )
        narration = await synthesize_content_world_narration(
            bundle,
            model=model,
            runnable_config=config,
        )
        return _terminal_content_world_command(
            render_content_world_narration(bundle, narration),
            tool_call_id=tool_call_id,
            persistence=persistence,
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


async def _search_content_world_evidence(
    query: str,
    max_results: int,
    *,
    douyin_search: Any | None = None,
) -> tuple[ResearchSearchResult, ...]:
    """Run web search and the official Douyin MCP as bounded topic evidence."""

    from deerflow.config import get_app_config
    from deerflow.reflection import resolve_variable

    app_config = get_app_config()
    web_search_config = app_config.get_tool_config("web_search")
    if web_search_config is None and douyin_search is None:
        return ()

    async def invoke_web_provider() -> tuple[ResearchSearchResult, ...]:
        assert web_search_config is not None
        search_config = web_search_config
        search_tool = resolve_variable(search_config.use, BaseTool)
        tool_input: dict[str, Any] = {"query": query}
        if "max_results" in search_tool.args:
            tool_input["max_results"] = max_results
        raw = await search_tool.ainvoke(tool_input)
        return _normalize_search_results(
            raw,
            max_results=max_results,
        )

    provider_calls = []
    if web_search_config is not None:
        provider_calls.append(invoke_web_provider())
    if douyin_search is not None:
        provider_calls.append(douyin_search(query, max_results))
    provider_results = await asyncio.gather(
        *provider_calls,
        return_exceptions=True,
    )
    successful_results: list[tuple[ResearchSearchResult, ...]] = []
    for result in provider_results:
        if isinstance(result, BaseException):
            logger.warning("Configured content research search failed: %s", type(result).__name__)
            continue
        successful_results.append(result)
    return _interleave_search_results(successful_results, max_results=max_results)


def _normalize_search_results(
    raw: Any,
    *,
    max_results: int,
    required_evidence_role: str | None = None,
) -> tuple[ResearchSearchResult, ...]:
    if not isinstance(raw, str):
        return ()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return ()
    declared_evidence_role = payload.get("evidence_role") if isinstance(payload, dict) else None
    if declared_evidence_role is not None and declared_evidence_role != "topic_evidence":
        return ()
    if required_evidence_role is not None:
        if declared_evidence_role != required_evidence_role:
            return ()
    results = _search_result_items(payload)

    normalized: list[ResearchSearchResult] = []
    for result in results[:max_results]:
        if not isinstance(result, dict):
            continue
        try:
            normalized.append(
                ResearchSearchResult(
                    title=_first_search_text(result, "title", "Title"),
                    url=_first_search_text(result, "url", "Url", "link", "href"),
                    content=_first_search_text(
                        result,
                        "content",
                        "snippet",
                        "summary",
                        "body",
                        "Content",
                        "Snippet",
                        "Summary",
                    ),
                )
            )
        except ValidationError:
            continue
    return tuple(normalized)


def _interleave_search_results(
    provider_results: list[tuple[ResearchSearchResult, ...]],
    *,
    max_results: int,
) -> tuple[ResearchSearchResult, ...]:
    interleaved: list[ResearchSearchResult] = []
    seen_urls: set[str] = set()
    max_provider_length = max((len(results) for results in provider_results), default=0)
    for index in range(max_provider_length):
        for results in provider_results:
            if index >= len(results):
                continue
            result = results[index]
            if result.url in seen_urls:
                continue
            seen_urls.add(result.url)
            interleaved.append(result)
            if len(interleaved) >= max_results:
                return tuple(interleaved)
    return tuple(interleaved)


def _search_result_items(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    results = payload.get("results")
    if isinstance(results, list):
        return results
    provider_result = payload.get("Result")
    if isinstance(provider_result, dict):
        web_results = provider_result.get("WebResults")
        if isinstance(web_results, list):
            return web_results
    return []


def _first_search_text(result: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = result.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


async def _fetch_content_world_evidence(url: str) -> str | None:
    """Open an exact search-result URL locally, then use the configured fallback."""

    url_error = await asyncio.to_thread(
        validate_public_http_url,
        url,
        action="read",
    )
    if url_error:
        return None
    direct_content = await _fetch_public_page_direct(url)
    if direct_content is not None:
        return direct_content
    return await _invoke_configured_web_fetch(url)


async def _invoke_configured_web_fetch(url: str) -> str | None:
    """Use the operator-configured reader for pages local HTTP cannot extract."""

    from deerflow.config import get_app_config
    from deerflow.reflection import resolve_variable

    fetch_config = next(
        (tool for tool in get_app_config().tools if tool.name == "web_fetch"),
        None,
    )
    if fetch_config is None:
        return None
    fetch_tool = resolve_variable(fetch_config.use, BaseTool)
    raw = await fetch_tool.ainvoke({"url": url})
    if not isinstance(raw, str):
        return None
    content = raw.strip()
    if not content or content.lower().startswith("error:"):
        return None
    return content


async def _fetch_public_page_direct(url: str) -> str | None:
    """Read bounded public HTML while rechecking every redirect target."""

    current_url = url
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(10.0),
            follow_redirects=False,
            trust_env=True,
            headers={"User-Agent": _DIRECT_FETCH_USER_AGENT},
        ) as client:
            for _ in range(_DIRECT_FETCH_MAX_REDIRECTS + 1):
                url_error = await asyncio.to_thread(
                    validate_public_http_url,
                    current_url,
                    action="read",
                )
                if url_error:
                    return None

                async with client.stream("GET", current_url) as response:
                    if response.status_code in {301, 302, 303, 307, 308}:
                        location = response.headers.get("location")
                        if not location:
                            return None
                        current_url = urljoin(current_url, location)
                        continue

                    response.raise_for_status()
                    content_type = response.headers.get("content-type", "").lower()
                    if content_type and not content_type.startswith(("text/html", "application/xhtml+xml", "text/plain")):
                        return None

                    chunks: list[bytes] = []
                    size = 0
                    async for chunk in response.aiter_bytes():
                        remaining = _DIRECT_FETCH_MAX_BYTES - size
                        if remaining <= 0:
                            break
                        chunks.append(chunk[:remaining])
                        size += min(len(chunk), remaining)
                        if size >= _DIRECT_FETCH_MAX_BYTES:
                            break
                    encoding = response.encoding or "utf-8"

                raw = b"".join(chunks)
                if not raw:
                    return None
                try:
                    html = raw.decode(encoding, errors="replace")
                except LookupError:
                    html = raw.decode("utf-8", errors="replace")
                article = await asyncio.to_thread(
                    _direct_readability_extractor.extract_article,
                    html,
                )
                markdown = article.to_markdown().strip()
                if not markdown or "No content could be extracted from this page" in markdown:
                    return None
                return markdown
    except (httpx.HTTPError, OSError, UnicodeError, ValueError):
        return None
    return None


def _terminal_content_world_command(
    content: str,
    *,
    tool_call_id: str,
    persistence: dict[str, Any] | None = None,
) -> Command:
    additional_kwargs: dict[str, Any] = {
        "hide_from_ui": True,
        "deerflow_direct_response": True,
    }
    if persistence is not None:
        additional_kwargs["incubation_persistence"] = persistence
    return Command(
        update={
            "messages": [
                ToolMessage(
                    id=f"{tool_call_id}:result",
                    content=content,
                    tool_call_id=tool_call_id,
                    name="explore_content_world",
                    additional_kwargs=additional_kwargs,
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
                "content_map_version_id": world.content_map_version_id() if world.content_root else None,
                "editorial_promise": world.editorial_promise,
                "recurring_lens": world.recurring_lens,
                "drift_boundaries": list(world.drift_boundaries),
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
                "content_map_version_id": world.content_map_version_id() if world.content_root else None,
                "editorial_promise": world.editorial_promise,
                "recurring_lens": world.recurring_lens,
                "drift_boundaries": list(world.drift_boundaries),
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
                "content_map_version_id": topic.content_map_version_id,
                "question": topic.question,
                "central_claim": topic.central_claim,
                "mechanism": topic.mechanism,
                "counterpoint": topic.counterpoint,
                "narrative_frame": (
                    {
                        "protagonist": topic.narrative_frame.protagonist,
                        "goal": topic.narrative_frame.goal,
                        "obstacle": topic.narrative_frame.obstacle,
                        "action_or_choice": topic.narrative_frame.action_or_choice,
                        "stakes_or_consequence": topic.narrative_frame.stakes_or_consequence,
                        "outcome_or_change": topic.narrative_frame.outcome_or_change,
                        "limitations": list(topic.narrative_frame.limitations),
                    }
                    if topic.narrative_frame is not None
                    else None
                ),
                "limitations": list(topic.limitations),
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
