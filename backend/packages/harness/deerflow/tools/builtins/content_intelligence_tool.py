from __future__ import annotations

import asyncio
import json
import logging
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
from deerflow.content_intelligence import (
    AnalysisFocus,
    BusinessSemanticView,
    ComprehensionRecord,
    ContentIntelligenceBundle,
    ContentIntelligenceRequest,
    ContentWorldView,
    ResearchEditorialContext,
    ResearchSearchResult,
    ShootingDelivery,
    SourceMaterial,
    analyze_content_intelligence,
    enrich_content_world_with_research,
    render_shooting_delivery,
    synthesize_shooting_delivery,
)
from deerflow.incubation import (
    AdaptedDraft,
    ArtifactEnvelope,
    EvidenceSnapshot,
    FormatDecision,
    LogicalAccountRef,
    PreparedAccountStrategy,
    ProductionPlan,
    ProjectRef,
    generate_adapted_draft,
    generate_format_decision,
    generate_production_plan,
    implicit_thread_logical_account_ref,
    seal_content_run_artifacts,
    seal_evidence_snapshot,
    select_current_account_strategy,
    select_used_topic_evidence_snapshots,
)
from deerflow.incubation.account_strategy_presentation import render_account_strategy as render_account_strategy
from deerflow.incubation.judgment import IncubationJudgment
from deerflow.tools.builtins.douyin_topic_evidence import DouyinMcpTopicEvidenceSearch
from deerflow.tools.builtins.incubation_tool_support import (
    artifact_receipt as _artifact_receipt,
)
from deerflow.tools.builtins.incubation_tool_support import (
    create_content_intelligence_model as _create_content_intelligence_model,
)
from deerflow.tools.builtins.incubation_tool_support import (
    create_lexical_evidence_provider as _create_lexical_evidence_provider,
)
from deerflow.tools.builtins.incubation_tool_support import (
    create_term_resolver as _create_term_resolver,
)
from deerflow.tools.builtins.incubation_tool_support import (
    get_incubation_repository as _get_incubation_repository,
)
from deerflow.tools.builtins.incubation_tool_support import (
    runtime_context_bool as _runtime_context_bool,
)
from deerflow.tools.builtins.incubation_tool_support import (
    runtime_context_text as _runtime_context_text,
)
from deerflow.tools.builtins.incubation_tool_support import (
    structured_model_runner as _structured_model_runner,
)
from deerflow.tools.types import Runtime
from deerflow.utils.readability import ReadabilityExtractor

logger = logging.getLogger(__name__)

_DIRECT_FETCH_MAX_BYTES = 2_000_000
_DIRECT_FETCH_MAX_REDIRECTS = 3
_DIRECT_FETCH_USER_AGENT = "Mozilla/5.0 (compatible; DeerFlowContentResearch/1.0)"
_direct_readability_extractor = ReadabilityExtractor()


def _runtime_logical_account(
    runtime: Runtime,
    *,
    project: ProjectRef,
) -> LogicalAccountRef | None:
    logical_account_id = _runtime_context_text(
        runtime,
        "incubation_logical_account_id",
    )
    if logical_account_id is not None:
        return LogicalAccountRef(
            owner_user_id=project.owner_user_id,
            project_id=project.project_id,
            logical_account_id=logical_account_id,
        )
    thread_id = _runtime_context_text(runtime, "thread_id")
    if thread_id is None:
        return None
    return implicit_thread_logical_account_ref(
        project=project,
        thread_id=thread_id,
    )


class ToolAnalysisFocus(StrEnum):
    BUSINESS_SEMANTICS = "business_semantics"
    TOPIC_BRIEF = "topic_brief"


class ContentWorldAnswerGoal(StrEnum):
    CONTENT_OPPORTUNITIES = "content_opportunities"
    ONE_SHOOTABLE_TOPIC = "one_shootable_topic"


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


async def _persist_content_run(
    *,
    bundle: ContentIntelligenceBundle,
    delivery: ShootingDelivery | None,
    runtime: Runtime,
    topic_evidence_snapshots: tuple[EvidenceSnapshot, ...],
    incubation_judgment_artifact: ArtifactEnvelope | None = None,
    model: Any | None = None,
    include_presentation_adaptation: bool = False,
    include_production_plan: bool = False,
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
        logical_account = _runtime_logical_account(runtime, project=project)
        if logical_account is None:
            return failure
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
                logical_account=logical_account,
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
        created_at = datetime.now(UTC)
        sealed = seal_content_run_artifacts(
            project=project,
            bundle=bundle,
            delivery=delivery,
            created_at=created_at,
            source_thread_id=thread_id,
            source_run_id=run_id,
            logical_account=logical_account,
            reading_parents=tuple(evidence_parents),
            incubation_judgment_artifact=incubation_judgment_artifact,
        )
        stored_content_artifacts: dict[str, ArtifactEnvelope] = {}
        for artifact in sealed.storage_order():
            stored = await repository.put_artifact(artifact)
            stored_content_artifacts[stored.artifact_type] = stored
            stored_receipts.append(
                {
                    "artifact_type": stored.artifact_type,
                    "artifact_id": stored.artifact_id,
                    "content_sha256": stored.content_sha256,
                }
            )
        answer_sections: list[str] = []
        if delivery is not None and model is not None and (include_presentation_adaptation or include_production_plan):
            try:
                resource_artifacts = await repository.list_artifacts(
                    project,
                    logical_account=logical_account,
                    artifact_type="media_observation",
                    evidence_role="user_material",
                )
                bounded_resources = tuple(resource_artifacts[-8:])
                message_plan_artifact = stored_content_artifacts["message_plan"]
                base_draft_artifact = stored_content_artifacts["draft_version"]
                format_artifact = await generate_format_decision(
                    project=project,
                    message_plan_artifact=message_plan_artifact,
                    base_draft_artifact=base_draft_artifact,
                    incubation_judgment_artifact=incubation_judgment_artifact,
                    resource_evidence_artifacts=bounded_resources,
                    structured_model=_structured_model_runner(model, runtime.config),
                    created_at=created_at,
                    source_thread_id=thread_id,
                    source_run_id=run_id,
                    logical_account=logical_account,
                )
                format_artifact = await repository.put_artifact(format_artifact)
                stored_receipts.append(_artifact_receipt(format_artifact))
                answer_sections.append(_render_format_decision_artifact(format_artifact))

                adapted_artifact = await generate_adapted_draft(
                    project=project,
                    base_draft_artifact=base_draft_artifact,
                    format_decision_artifact=format_artifact,
                    structured_model=_structured_model_runner(model, runtime.config),
                    created_at=created_at,
                    source_thread_id=thread_id,
                    source_run_id=run_id,
                    logical_account=logical_account,
                )
                adapted_artifact = await repository.put_artifact(adapted_artifact)
                stored_receipts.append(_artifact_receipt(adapted_artifact))
                answer_sections.append(_render_adapted_draft_artifact(adapted_artifact))

                if include_production_plan:
                    production_artifact = await generate_production_plan(
                        project=project,
                        adapted_draft_artifact=adapted_artifact,
                        format_decision_artifact=format_artifact,
                        user_material_artifacts=bounded_resources,
                        structured_model=_structured_model_runner(model, runtime.config),
                        created_at=created_at,
                        source_thread_id=thread_id,
                        source_run_id=run_id,
                        logical_account=logical_account,
                    )
                    production_artifact = await repository.put_artifact(production_artifact)
                    stored_receipts.append(_artifact_receipt(production_artifact))
                    answer_sections.append(_render_production_plan_artifact(production_artifact))
            except Exception as exc:
                logger.warning(
                    "Post-draft expression or production continuation was unavailable: %s",
                    type(exc).__name__,
                )

        result: dict[str, Any] = {
            "status": "stored",
            "project_id": project_id,
            "logical_account_id": logical_account.logical_account_id,
            "artifacts": stored_receipts,
        }
        if answer_sections:
            result["_answer_appendix"] = "\n\n".join(answer_sections)
        return result
    except Exception as exc:
        logger.warning(
            "Content-run persistence failed: %s",
            type(exc).__name__,
        )
        return failure


async def _load_current_account_strategy(
    *,
    bundle: ContentIntelligenceBundle,
    runtime: Runtime,
):
    project_id = _runtime_context_text(runtime, "incubation_project_id")
    owner_user_id = _runtime_context_text(runtime, "user_id")
    if project_id is None or owner_user_id is None:
        return None
    world = getattr(bundle, "content_world", None)
    if world is None or world.content_root is None:
        return None
    repository = _get_incubation_repository()
    if repository is None:
        return None
    project = ProjectRef(owner_user_id=owner_user_id, project_id=project_id)
    logical_account = _runtime_logical_account(runtime, project=project)
    if logical_account is None:
        return None
    if await repository.get_project(project) is None:
        return None
    artifacts = await repository.list_artifacts(
        project,
        logical_account=logical_account,
        artifact_type="incubation_judgment",
    )
    return select_current_account_strategy(
        artifacts,
        logical_account=logical_account,
        content_map_version_id=world.content_map_version_id(),
        require_confirmed=True,
    )


def _research_editorial_context(
    judgment: IncubationJudgment | None,
) -> ResearchEditorialContext | None:
    """Project only the confirmed content route into topic research."""

    if judgment is None or judgment.decision_status != "confirmed" or judgment.selected_option_id is None or judgment.positioning is None or judgment.audience is None or judgment.persona is None:
        return None
    return ResearchEditorialContext(
        route_id=judgment.selected_option_id,
        content_subject=judgment.positioning.decision,
        audience_promise=judgment.positioning.audience_promise,
        audience_people=judgment.audience.people,
        recurring_interest=judgment.audience.recurring_interest,
        account_role=judgment.persona.account_role,
    )


async def _load_confirmed_topic_context(
    *,
    runtime: Runtime,
) -> tuple[ContentIntelligenceBundle, PreparedAccountStrategy] | None:
    """Rehydrate the exact frozen map selected by the confirmed account route."""

    project_id = _runtime_context_text(runtime, "incubation_project_id")
    owner_user_id = _runtime_context_text(runtime, "user_id")
    if project_id is None or owner_user_id is None:
        return None
    repository = _get_incubation_repository()
    if repository is None:
        return None
    project = ProjectRef(owner_user_id=owner_user_id, project_id=project_id)
    logical_account = _runtime_logical_account(runtime, project=project)
    if logical_account is None:
        return None
    if await repository.get_project(project) is None:
        return None

    artifacts = await repository.list_artifacts(
        project,
        logical_account=logical_account,
    )
    strategy = select_current_account_strategy(
        artifacts,
        logical_account=logical_account,
        require_confirmed=True,
    )
    if strategy is None:
        return None

    by_id = {artifact.artifact_id: artifact for artifact in artifacts}
    map_parents = tuple(parent for parent in strategy.judgment_artifact.parents if parent.artifact_type == "content_map_candidate")
    if len(map_parents) != 1:
        raise ValueError("confirmed account strategy requires exactly one candidate-map parent")
    map_parent = map_parents[0]
    map_artifact = by_id.get(map_parent.artifact_id)
    if map_artifact is None or map_artifact.artifact_type != map_parent.artifact_type or map_artifact.content_sha256 != map_parent.content_sha256:
        raise ValueError("confirmed account strategy candidate-map receipt does not match storage")
    if map_artifact.payload.get("content_map_version_id") != strategy.judgment.content_map_version_id:
        raise ValueError("confirmed account strategy does not match its candidate-map version")

    reading_candidates = tuple(
        artifact
        for artifact in artifacts
        if artifact.artifact_type == "content_reading"
        and artifact.source_thread_id == map_artifact.source_thread_id
        and artifact.source_run_id == map_artifact.source_run_id
        and isinstance(artifact.payload.get("root_selection"), dict)
        and artifact.payload["root_selection"].get("content_map_version_id") == strategy.judgment.content_map_version_id
    )
    if len(reading_candidates) != 1:
        raise ValueError("confirmed candidate map requires one exact source reading")
    reading_artifact = reading_candidates[0]
    root_selection = reading_artifact.payload["root_selection"]
    record = ComprehensionRecord.model_validate(reading_artifact.payload.get("record"))
    business_payload = reading_artifact.payload.get("business_semantics")
    business_semantics = BusinessSemanticView.model_validate(business_payload) if business_payload is not None else None
    content_world = ContentWorldView.model_validate(
        {
            "record_id": record.record_id,
            "source_object": root_selection.get("source_object"),
            "content_entry": root_selection.get("content_entry"),
            "content_root": map_artifact.payload.get("content_root"),
            "root_rationale": root_selection.get("root_rationale"),
            "editorial_promise": map_artifact.payload.get("editorial_promise"),
            "recurring_lens": map_artifact.payload.get("recurring_lens"),
            "drift_boundaries": map_artifact.payload.get("drift_boundaries", []),
            "root_candidates": root_selection.get("root_candidates", []),
            "dimensions": map_artifact.payload.get("dimensions", []),
            "named_candidates": root_selection.get("named_candidates", []),
            "unknown_refs": root_selection.get("unknown_refs", []),
        }
    )
    if content_world.content_map_version_id() != strategy.judgment.content_map_version_id:
        raise ValueError("rehydrated candidate map does not match the confirmed account strategy")
    return (
        ContentIntelligenceBundle(
            record=record,
            business_semantics=business_semantics,
            content_world=content_world,
        ),
        strategy,
    )


async def _analyze_content_intelligence(
    user_request: str,
    subject_expression: str,
    focus: ToolAnalysisFocus = ToolAnalysisFocus.BUSINESS_SEMANTICS,
    source_materials: list[SourceMaterial] | None = None,
    config: Annotated[RunnableConfig, InjectedToolArg] = None,
) -> str:
    model = _create_content_intelligence_model(config)
    lexical_evidence_provider = _create_lexical_evidence_provider()
    term_resolver = _create_term_resolver(lexical_evidence_provider)
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
            lexical_evidence_provider=lexical_evidence_provider,
            term_resolver=term_resolver,
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
    answer_goal: ContentWorldAnswerGoal = ContentWorldAnswerGoal.ONE_SHOOTABLE_TOPIC,
    subject_expression: str | None = None,
    topic_seed: str | None = None,
) -> Command:
    """Build a candidate content-opportunity map or one evidence-bound shootable topic.

    Both goals freeze business semantics, one map root, and its candidate map.
    Content opportunities stop there. A shootable-topic goal continues through
    research, TopicBrief, MessagePlan, and BaseDraft. With a selected project it
    may also persist a per-topic FormatDecision, AdaptedDraft, and ProductionPlan.
    It still stops before MediaKit execution, platform, cadence, sales,
    experiments, or questionnaires.

    Args:
        user_request: The current content-opportunity or concrete-topic request, copied without adding requirements.
        answer_goal: Whether to return candidate content opportunities or one concrete shootable topic.
        subject_expression: Optional exact business or content subject copied as one contiguous span from user_request. Omit it when continuing a selected project's confirmed route so the tool reuses that route's frozen map.
        topic_seed: Optional hotspot, person, work, event, or question copied as one contiguous verbatim span from user_request.
    """
    try:
        validated_topic_seed = _validate_topic_seed(user_request, topic_seed)
    except ValueError:
        validated_topic_seed = None

    config = runtime.config
    tool_call_id = runtime.tool_call_id
    model = _create_content_intelligence_model(config)
    lexical_evidence_provider = _create_lexical_evidence_provider()
    term_resolver = _create_term_resolver(lexical_evidence_provider)

    try:
        confirmed_context = None
        if answer_goal == ContentWorldAnswerGoal.ONE_SHOOTABLE_TOPIC:
            confirmed_context = await _load_confirmed_topic_context(runtime=runtime)
        reuse_confirmed_context = confirmed_context is not None and (
            subject_expression is None
            or _subject_expression_matches_confirmed_context(
                subject_expression,
                bundle=confirmed_context[0],
                strategy=confirmed_context[1],
            )
        )
        if not reuse_confirmed_context:
            try:
                validated_subject_expression = _validate_subject_expression(user_request, subject_expression)
            except ValueError:
                return _terminal_content_world_command(
                    "内容主体必须来自当前原话或已确认项目，因此这次没有用一个陌生主体覆盖现有路线。",
                    tool_call_id=runtime.tool_call_id,
                )
            request = ContentIntelligenceRequest(
                user_request=user_request,
                subject_expression=validated_subject_expression or user_request,
                focus=AnalysisFocus.CONTENT_WORLD,
                source_materials=(),
            )
            bundle = await analyze_content_intelligence(
                request,
                model=model,
                runnable_config=config,
                lexical_evidence_provider=lexical_evidence_provider,
                term_resolver=term_resolver,
            )
            current_strategy = None
        else:
            assert confirmed_context is not None
            bundle, current_strategy = confirmed_context
        if answer_goal == ContentWorldAnswerGoal.CONTENT_OPPORTUNITIES:
            persistence = await _persist_content_run(
                bundle=bundle,
                delivery=None,
                runtime=runtime,
                topic_evidence_snapshots=(),
            )
            return _terminal_content_world_command(
                _render_content_opportunity_map(bundle),
                tool_call_id=tool_call_id,
                persistence=persistence,
            )

        if current_strategy is None:
            current_strategy = await _load_current_account_strategy(
                bundle=bundle,
                runtime=runtime,
            )
        douyin_topic_search: DouyinMcpTopicEvidenceSearch | None = None
        try:
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

            bundle = await enrich_content_world_with_research(
                bundle,
                model=model,
                search=search_content_evidence,
                topic_seed=validated_topic_seed,
                fetch=_fetch_content_world_evidence,
                editorial_context=_research_editorial_context(current_strategy.judgment if current_strategy is not None else None),
                runnable_config=config,
            )
        except Exception as exc:
            logger.warning(
                "Post-map research was unavailable; no shootable topic was formed: %s",
                type(exc).__name__,
            )
            persistence = await _persist_content_run(
                bundle=bundle,
                delivery=None,
                runtime=runtime,
                topic_evidence_snapshots=(douyin_topic_search.snapshots if douyin_topic_search is not None else ()),
            )
            return _terminal_content_world_command(
                _render_shootable_topic_failure(bundle),
                tool_call_id=tool_call_id,
                persistence=persistence,
            )

        topic_evidence_snapshots = douyin_topic_search.snapshots
        if bundle.topic_brief is None:
            persistence = await _persist_content_run(
                bundle=bundle,
                delivery=None,
                runtime=runtime,
                topic_evidence_snapshots=topic_evidence_snapshots,
            )
            return _terminal_content_world_command(
                _render_shootable_topic_failure(bundle),
                tool_call_id=tool_call_id,
                persistence=persistence,
            )

        try:
            shooting_delivery = await synthesize_shooting_delivery(
                bundle,
                user_request=user_request,
                model=model,
                runnable_config=config,
                incubation_judgment=(current_strategy.judgment if current_strategy is not None else None),
            )
            if shooting_delivery is None:
                raise ValueError("shootable-topic delivery returned no MessagePlan or BaseDraft")
            rendered_delivery = _prioritize_shooting_delivery(render_shooting_delivery(bundle, shooting_delivery))
            if current_strategy is not None:
                rendered_delivery += "\n\n" + _render_confirmed_route_reference(current_strategy.judgment)
        except Exception as exc:
            logger.warning(
                "Evidence topic delivery was unavailable; no shootable topic was formed: %s",
                type(exc).__name__,
            )
            shooting_delivery = None
        persistence = await _persist_content_run(
            bundle=bundle,
            delivery=shooting_delivery,
            runtime=runtime,
            topic_evidence_snapshots=topic_evidence_snapshots,
            incubation_judgment_artifact=(current_strategy.judgment_artifact if current_strategy is not None and shooting_delivery is not None else None),
            model=model,
            include_presentation_adaptation=_runtime_context_bool(
                runtime,
                "content_include_presentation_adaptation",
                default=False,
            ),
            include_production_plan=_runtime_context_bool(
                runtime,
                "content_include_production_plan",
                default=False,
            ),
        )
        if shooting_delivery is None:
            return _terminal_content_world_command(
                _render_shootable_topic_failure(bundle),
                tool_call_id=tool_call_id,
                persistence=persistence,
            )
        answer_appendix = persistence.get("_answer_appendix")
        if isinstance(answer_appendix, str) and answer_appendix.strip():
            rendered_delivery += "\n\n" + answer_appendix.strip()
        return _terminal_content_world_command(
            rendered_delivery,
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


def _validate_topic_seed(user_request: str, topic_seed: str | None) -> str | None:
    if topic_seed is None:
        return None
    if not topic_seed.strip() or topic_seed not in user_request:
        raise ValueError("topic_seed must be a non-empty contiguous verbatim span of user_request")
    return topic_seed


def _validate_subject_expression(user_request: str, subject_expression: str | None) -> str | None:
    if subject_expression is None:
        return None
    if not subject_expression.strip() or subject_expression not in user_request:
        raise ValueError("subject_expression must be a non-empty contiguous verbatim span of user_request")
    return subject_expression


def _subject_expression_matches_confirmed_context(
    subject_expression: str,
    *,
    bundle: ContentIntelligenceBundle,
    strategy: PreparedAccountStrategy,
) -> bool:
    candidate = "".join(subject_expression.split())
    if not candidate:
        return False
    world = bundle.content_world
    aliases = {
        bundle.record.subject_expression,
        *((world.source_object, world.content_entry, world.content_root) if world is not None else ()),
    }
    selected_option = next(
        (option for option in strategy.judgment.route_options if option.option_id == strategy.judgment.selected_option_id),
        None,
    )
    if selected_option is not None:
        aliases.update((selected_option.name, selected_option.positioning.decision))
    for alias in aliases:
        if alias is None:
            continue
        normalized_alias = "".join(alias.split())
        if candidate in normalized_alias or normalized_alias in candidate:
            return True
    return False


def _render_content_opportunity_map(bundle: ContentIntelligenceBundle) -> str:
    world = bundle.content_world
    if world is None or world.content_root is None:
        raise ValueError("content opportunity rendering requires a frozen map root")

    lines = [
        "# 候选内容机会地图",
        "",
        f"**地图从哪里展开：** {world.content_root}",
    ]
    if world.editorial_promise is not None:
        lines.extend(("", f"**可能持续提供的价值：** {world.editorial_promise}"))
    if world.recurring_lens is not None:
        lines.extend(("", f"**稳定观察方法：** {world.recurring_lens}"))
    if world.dimensions:
        lines.extend(("", "## 内容地图", ""))
        for dimension in world.dimensions:
            directions = tuple(dict.fromkeys(path.steps[-1].to_label for path in dimension.paths if path.steps))
            suffix = f" 可展开：{'；'.join(directions)}" if directions else ""
            lines.append(f"- **{dimension.name}：** {dimension.rationale}{suffix}")
    if world.drift_boundaries:
        lines.extend(("", "## 地图边界", ""))
        lines.extend(f"- {boundary}" for boundary in world.drift_boundaries)
    return "\n".join(lines).strip()


def _render_format_decision_artifact(artifact: ArtifactEnvelope) -> str:
    decision = FormatDecision.model_validate(artifact.payload)
    format_labels = {
        "spoken_delivery": "口述表达",
        "micro_drama": "微短剧",
        "situational_drama": "情景剧",
        "image_text": "图文",
        "material_only": "纯素材",
        "interview": "访谈",
        "documentary_observation": "纪录观察",
        "custom": decision.selected_format.custom_name or "自定义形式",
    }
    status_label = "已确认" if decision.status == "confirmed" else "暂定"
    lines = [
        "# 本条表现形式",
        "",
        f"**建议形式：** {format_labels[decision.selected_format.kind]}（{status_label}）",
        "",
        f"**为什么：** {decision.selection_rationale}",
    ]
    if decision.resource_matches:
        lines.extend(("", "## 已匹配资源", ""))
        lines.extend(f"- **{item.resource}：** {item.fit}" for item in decision.resource_matches)
    if decision.resource_gaps:
        lines.extend(("", "## 还缺什么", ""))
        lines.extend(f"- {item}" for item in decision.resource_gaps)
    if decision.sustainability_risks:
        lines.extend(("", "## 持续生产风险", ""))
        lines.extend(f"- {item}" for item in decision.sustainability_risks)
    if decision.alternatives:
        lines.extend(("", "## 备选形式", ""))
        lines.extend(f"- **{format_labels[item.format.kind]}：** {item.rationale}" for item in decision.alternatives)
    if decision.unknowns:
        lines.extend(("", "## 仍未知", ""))
        lines.extend(f"- {item}" for item in decision.unknowns)
    return "\n".join(lines).strip()


def _render_adapted_draft_artifact(artifact: ArtifactEnvelope) -> str:
    adapted = AdaptedDraft.model_validate(artifact.payload)
    mode_labels = {
        "spoken_line": "口述",
        "voiceover": "旁白",
        "on_screen_text": "屏幕文字",
        "visual_only": "纯画面",
        "interview_prompt": "采访提问",
        "interview_response": "采访回答",
        "observed_action": "纪录动作",
        "dialogue": "对白",
        "narration": "叙述",
    }
    lines = ["# 形式适配稿"]
    for index, unit in enumerate(adapted.units, start=1):
        lines.extend(
            (
                "",
                f"## {index}. {mode_labels[unit.mode]}",
                "",
                unit.adapted_expression,
            )
        )
        if unit.visual_treatment is not None:
            lines.extend(("", f"**画面承载：** {unit.visual_treatment}"))
        if unit.narrative_treatment is not None:
            lines.extend(
                (
                    "",
                    f"**场面目的：** {unit.narrative_treatment.scene_purpose}",
                    "",
                    f"**表演意图：** {unit.narrative_treatment.performance_intent}",
                )
            )
    return "\n".join(lines).strip()


def _render_production_plan_artifact(artifact: ArtifactEnvelope) -> str:
    plan = ProductionPlan.model_validate(artifact.payload)
    source_labels = {
        "existing_user_material": "已有用户素材",
        "to_capture": "需要拍摄",
        "to_record": "需要录制",
        "to_create": "需要制作",
        "derived_from_adapted_draft": "由适配稿生成",
    }
    status_label = "可执行" if plan.status == "ready" else "暂定"
    lines = ["# 制作方案", "", f"**状态：** {status_label}"]
    if plan.asset_requirements:
        lines.extend(("", "## 素材需求", ""))
        lines.extend(f"- **{item.asset_id}（{source_labels[item.source]}）：** {item.purpose}" for item in plan.asset_requirements)
    if plan.production_actions:
        lines.extend(("", "## 拍摄与制作动作", ""))
        lines.extend(f"- {item.instruction}" for item in plan.production_actions)
    if plan.assembly_steps:
        lines.extend(("", "## 装配顺序", ""))
        lines.extend(f"{index}. {item.instruction}" for index, item in enumerate(plan.assembly_steps, start=1))
    if plan.resource_gaps:
        lines.extend(("", "## 还缺什么", ""))
        lines.extend(f"- {item}" for item in plan.resource_gaps)
    if plan.unknowns:
        lines.extend(("", "## 仍未知", ""))
        lines.extend(f"- {item}" for item in plan.unknowns)
    if plan.limitations:
        lines.extend(("", "## 制作边界", ""))
        lines.extend(f"- {item}" for item in plan.limitations)
    return "\n".join(lines).strip()


def _render_shootable_topic_failure(bundle: ContentIntelligenceBundle) -> str:
    return "# 本轮选题结果\n\n**候选内容地图已形成，但没有形成可拍选题。** 研究、证据阅读或内容交付没有形成完整合同，因此本轮不会把地图方向冒充成具体选题。\n\n" + _render_content_opportunity_map(bundle)


def _render_confirmed_route_reference(judgment: IncubationJudgment) -> str:
    selected = next(
        (option for option in judgment.route_options if option.option_id == judgment.selected_option_id),
        None,
    )
    if selected is None:
        if judgment.positioning is None:
            raise ValueError("confirmed account strategy has no selected route or positioning")
        label = judgment.positioning.decision
    else:
        label = f"{selected.name}（{selected.option_id}）"
    return f"## 已确认路线\n\n**沿用：** {label}"


def _prioritize_shooting_delivery(rendered: str) -> str:
    content = rendered.strip()
    topic_heading = "# 今日建议拍摄"
    if content.startswith(topic_heading):
        return content
    if topic_heading not in content:
        raise ValueError("shooting delivery did not contain the concrete-topic heading")

    opportunity_map, topic = content.split(topic_heading, 1)
    opportunity_lines = opportunity_map.strip().splitlines()
    if opportunity_lines and opportunity_lines[0].strip() == "# 内容机会依据":
        opportunity_lines = opportunity_lines[1:]
    opportunity_basis = "\n".join(opportunity_lines).strip()
    prioritized = topic_heading + topic.rstrip()
    if opportunity_basis:
        prioritized += "\n\n# 内容机会依据\n\n" + opportunity_basis
    return prioritized


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
        additional_kwargs["incubation_persistence"] = {key: value for key, value in persistence.items() if not key.startswith("_")}
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
