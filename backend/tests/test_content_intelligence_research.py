from __future__ import annotations

import asyncio
from typing import Any

import pytest
from pydantic import ValidationError

from deerflow.content_intelligence import (
    AnalysisFocus,
    ContentDimension,
    ContentIntelligenceRequest,
    ContentPath,
    ContentPathStep,
    ContentRootDecisionDraft,
    EvidenceReadingDraft,
    ResearchBudget,
    ResearchDiscoveryDraft,
    ResearchSearchResult,
    SemanticFamilyExpansionDraft,
    SharedWorldReviewDraft,
    SharedWorldSynthesisDraft,
    TopicEditorialDecisionDraft,
    enrich_content_world_with_research,
    render_content_world_narration,
)
from deerflow.content_intelligence.analyzer import FrozenContentMapDraft, SemanticReadingDraft, analyze_content_intelligence
from deerflow.content_intelligence.research import (
    EVIDENCE_READING_SYSTEM_PROMPT,
    RESEARCH_DISCOVERY_SYSTEM_PROMPT,
    TOPIC_EDITOR_SYSTEM_PROMPT,
)


class SequencedStructuredFakeModel:
    def __init__(self, payloads: dict[type, dict[str, Any] | list[dict[str, Any]]]) -> None:
        self.payloads = payloads
        self.schemas: list[type] = []
        self.message_batches: list[tuple[object, ...]] = []
        self.call_schemas: list[type] = []
        self.schema_call_counts: dict[type, int] = {}

    def with_structured_output(self, schema, *, include_raw: bool = False):
        self.schemas.append(schema)
        return BoundStructuredFakeModel(self, schema)

    async def _ainvoke_for(self, schema, messages, config=None):
        self.message_batches.append(tuple(messages))
        self.call_schemas.append(schema)
        payload = self.payloads[schema]
        if isinstance(payload, list):
            call_index = self.schema_call_counts.get(schema, 0)
            selected = payload[min(call_index, len(payload) - 1)]
            self.schema_call_counts[schema] = call_index + 1
            payload = selected
        return schema.model_validate(payload)


class BoundStructuredFakeModel:
    def __init__(self, parent: SequencedStructuredFakeModel, schema: type) -> None:
        self.parent = parent
        self.schema = schema

    async def ainvoke(self, messages, config=None):
        return await self.parent._ainvoke_for(self.schema, messages, config)


def _semantic_payload() -> dict[str, Any]:
    return {
        "source_object": "regional meal base",
        "lexical_head": "base",
        "modifiers": [],
        "offering_role": "intermediate_enabler",
        "role_rationale": "The base helps complete a meal.",
        "served_objects": ["shared meal"],
        "served_activities": ["preparing the shared meal"],
        "defining_functions_or_uses": ["forming its characteristic flavor"],
        "social_or_cultural_frames": ["communal dining"],
        "seller_actions": [],
        "uncertainties": [],
    }


def _root_candidates_payload() -> dict[str, Any]:
    return {
        "source_object": "regional meal base",
        "candidates": [
            {
                "level": "served_object_or_activity",
                "label": "shared meal",
                "scope_role": "root_candidate",
                "relation_to_business": "complete object served by the base",
                "strength": "complete and durable",
                "overreach_risk": "unrelated dining must stay outside the map",
            }
        ],
        "unknowns": [],
    }


def _shared_world_payload() -> dict[str, Any]:
    return {
        "common_action_or_relation": "sharing a meal",
        "participant_relationship": "people eating together",
        "world_label": "shared meals",
        "semantic_path": ["meal base", "eating together", "shared meals"],
        "covered_frames": ["communal dining"],
        "limitations": [],
    }


def _shared_world_review_payload() -> dict[str, Any]:
    return {
        "reviewed_world_label": "shared meals",
        "entry_path_is_explanatory": False,
        "substitution_counterfactual": "People can share many unrelated meals without this particular served object.",
        "rationale": "The social setting is adjacent to the object rather than constitutive of it.",
    }


def _root_decision_payload() -> dict[str, Any]:
    return {
        "selected_candidate_index": 2,
        "audience_territory_candidate_index": 2,
        "root_rationale": "The base is an enabler and the meal is the complete world.",
        "unknowns": [],
    }


def _map_payload() -> dict[str, Any]:
    return {
        "editorial_promise": "Use shared meals to understand people, places, customs, and change over time.",
        "recurring_lens": "Enter through one documented person, place, practice, or change and explain its connection to shared meals.",
        "drift_boundaries": ["A popular event without a rooted path to shared meals stays outside the map."],
        "map_directions": [
            {
                "dimension": "emotion and relationships",
                "actual_directions": ["how the shared meal carries emotion and group belonging"],
            },
            {
                "dimension": "history and public records",
                "actual_directions": ["documented changes in the shared meal over time"],
            },
        ],
        "named_candidates": [],
        "unknowns": [],
    }


async def _content_world_bundle():
    model = SequencedStructuredFakeModel(
        {
            SemanticReadingDraft: _semantic_payload(),
            SemanticFamilyExpansionDraft: {
                "components": [],
                "branches": [],
                "limitations": [],
            },
            SharedWorldSynthesisDraft: _shared_world_payload(),
            SharedWorldReviewDraft: _shared_world_review_payload(),
            ContentRootDecisionDraft: _root_decision_payload(),
            FrozenContentMapDraft: _map_payload(),
        }
    )
    bundle = await analyze_content_intelligence(
        ContentIntelligenceRequest(
            user_request="Help this business start an account",
            subject_expression="regional meal base",
            focus=AnalysisFocus.CONTENT_WORLD,
        ),
        model=model,
    )
    assert SemanticFamilyExpansionDraft in model.call_schemas
    return bundle


def _discovery_payload() -> dict[str, Any]:
    return {
        "candidates": [
            {
                "candidate_id": "candidate-public-record",
                "map_dimension": "history and public records",
                "map_path_id": "path-direction-2-1",
                "entity": "a documented public event",
                "relation_to_root": "the event changed how the shared meal was understood",
                "why_worth_reading": "it may turn a broad history branch into a concrete question",
                "search_queries": ["shared meal documented public event"],
            }
        ],
        "unknowns": [],
    }


def _reading_payload(*, source_ref: str = "source-web-1") -> dict[str, Any]:
    return {
        "selected_candidate_id": "candidate-public-record",
        "selected_entity": "a documented public event",
        "selected_entity_observation_refs": ["reading-observation-1"],
        "observations": [
            {
                "observation_id": "reading-observation-1",
                "claim": "The supplied search evidence reports a dated public event.",
                "source_refs": [source_ref],
            }
        ],
        "relations": [
            {
                "subject": "documented public event",
                "predicate": "changed public understanding of",
                "object": "shared meal",
                "observation_refs": ["reading-observation-1"],
            }
        ],
        "state_changes": [],
        "interpretations": [
            {
                "interpretation_id": "reading-interpretation-1",
                "claim": "The event is a useful lens for explaining a change in meaning.",
                "observation_refs": ["reading-observation-1"],
                "limitations": ["A search-result snippet is not the full primary source."],
            }
        ],
        "limitations": ["The current receipt contains a search snippet rather than the full record."],
        "unknowns": ["The full primary record still needs to be read."],
    }


def _editorial_payload(
    *,
    candidate_id: str = "candidate-public-record",
    narrative_frame: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "selected_candidate_id": candidate_id,
        "topic_brief": {
            "question": "How did one public event change what this shared meal meant to people?",
            "central_claim": "The event made an existing social meaning newly visible.",
            "mechanism": "The documented event connects a concrete change with the frozen content root.",
            "counterpoint": "The available snippet cannot establish a universal historical cause.",
            "evidence_observation_refs": ["reading-observation-1"],
            "narrative_frame": narrative_frame,
            "limitations": ["The current topic is supported by one bounded evidence receipt."],
            "unknowns": ["The full primary record still needs to be read."],
            "research_needed": ["Open and compare the full source before drafting."],
        },
        "abstention_reason": None,
    }


@pytest.mark.asyncio
async def test_map_direction_search_runs_in_parallel_with_latent_recall_and_can_win() -> None:
    bundle = await _content_world_bundle()
    discovery = _discovery_payload()
    discovery["candidates"][0].update(
        {
            "entity": "an unsupported recalled anecdote",
            "search_queries": ["unsupported recalled anecdote shared meal"],
        }
    )
    reading = _reading_payload()
    reading.update(
        {
            "selected_candidate_id": "map-direction-1-1",
            "selected_entity": "a verified community supper event",
        }
    )
    research_model = SequencedStructuredFakeModel(
        {
            ResearchDiscoveryDraft: discovery,
            EvidenceReadingDraft: reading,
            TopicEditorialDecisionDraft: _editorial_payload(candidate_id="map-direction-1-1"),
        }
    )
    started_queries: list[str] = []
    both_lanes_started = asyncio.Event()

    async def search(query: str, max_results: int) -> tuple[ResearchSearchResult, ...]:
        started_queries.append(query)
        if len(started_queries) >= 2:
            both_lanes_started.set()
        await asyncio.wait_for(both_lanes_started.wait(), timeout=0.25)
        if query == "unsupported recalled anecdote shared meal":
            return (
                ResearchSearchResult(
                    title="Weak recollection",
                    url="https://example.com/weak-recollection",
                    content="A page that does not verify the recalled anecdote.",
                ),
            )
        return (
            ResearchSearchResult(
                title="Community supper archive",
                url="https://example.com/community-supper",
                content="A dated public record identifies a community supper event.",
            ),
        )

    enriched = await enrich_content_world_with_research(
        bundle,
        model=research_model,
        search=search,
        budget=ResearchBudget(max_queries=2, max_results_per_query=1, max_evidence_items=2),
    )

    assert both_lanes_started.is_set()
    assert "unsupported recalled anecdote shared meal" in started_queries
    assert any("how the shared meal carries emotion and group belonging" in query for query in started_queries)
    reading_input = research_model.message_batches[1][1].content
    assert '"discovery_mode": "map_direction_search"' in reading_input
    assert '"discovery_mode": "latent_recall"' in reading_input
    assert '"candidate_id": "map-direction-1-1"' in reading_input
    assert '"candidate_id": "candidate-public-record"' in reading_input
    assert "why_worth_reading" not in reading_input
    assert "search_queries" not in reading_input

    assert enriched.topic_brief is not None
    assert enriched.topic_brief.path.steps[0].to_label == "how the shared meal carries emotion and group belonging"
    assert enriched.topic_brief.path.steps[-1].to_label == "a verified community supper event"


@pytest.mark.asyncio
async def test_map_direction_search_still_works_when_latent_recall_is_empty() -> None:
    bundle = await _content_world_bundle()
    research_model = SequencedStructuredFakeModel(
        {
            ResearchDiscoveryDraft: {"candidates": [], "unknowns": ["No reliable name was recalled."]},
            EvidenceReadingDraft: {
                **_reading_payload(),
                "selected_candidate_id": "map-direction-1-1",
                "selected_entity": "a documented neighborhood meal",
            },
            TopicEditorialDecisionDraft: _editorial_payload(candidate_id="map-direction-1-1"),
        }
    )

    async def search(query: str, max_results: int) -> tuple[ResearchSearchResult, ...]:
        return (
            ResearchSearchResult(
                title="Neighborhood meal record",
                url="https://example.com/neighborhood-meal",
                content="A public record names and dates a neighborhood meal.",
            ),
        )

    enriched = await enrich_content_world_with_research(bundle, model=research_model, search=search)

    assert research_model.schemas == [
        ResearchDiscoveryDraft,
        EvidenceReadingDraft,
        TopicEditorialDecisionDraft,
    ]
    assert enriched.topic_brief is not None
    assert enriched.topic_brief.path.steps[-1].to_label == "a documented neighborhood meal"


@pytest.mark.asyncio
async def test_user_topic_seed_reaches_discovery_as_an_unverified_lead() -> None:
    bundle = await _content_world_bundle()
    discovery = _discovery_payload()
    discovery["candidates"][0].update(
        {
            "candidate_id": "candidate-user-seed",
            "entity": "the 1914 Christmas Truce",
            "relation_to_root": "the reported shared meal would instantiate the frozen shared-meal map",
            "search_queries": ["1914 Christmas Truce shared meal primary source"],
        }
    )
    reading = _reading_payload()
    reading.update(
        {
            "selected_candidate_id": "candidate-user-seed",
            "selected_entity": "the 1914 Christmas Truce",
        }
    )
    research_model = SequencedStructuredFakeModel(
        {
            ResearchDiscoveryDraft: discovery,
            EvidenceReadingDraft: reading,
            TopicEditorialDecisionDraft: _editorial_payload(candidate_id="candidate-user-seed"),
        }
    )
    seen_queries: list[str] = []

    async def search(query: str, max_results: int) -> tuple[ResearchSearchResult, ...]:
        seen_queries.append(query)
        return (
            ResearchSearchResult(
                title="Public record",
                url="https://example.com/public-record",
                content="A public source that must be read before treating the lead as fact.",
            ),
        )

    topic_seed = "  Did the 1914 Christmas Truce include a shared meal?  "
    await enrich_content_world_with_research(
        bundle,
        model=research_model,
        search=search,
        topic_seed=topic_seed,
    )

    discovery_input = research_model.message_batches[0][1].content
    assert '"user_topic_seed"' in discovery_input
    assert f'"text": "{topic_seed}"' in discovery_input
    assert '"provenance": "user_provided"' in discovery_input
    assert '"epistemic_status": "unverified_lead_not_evidence"' in discovery_input
    assert "regional meal base" not in discovery_input
    assert "business_semantics" not in discovery_input
    discovery_system_prompt = research_model.message_batches[0][0].content
    assert "user_topic_seed" in discovery_system_prompt
    assert "不是事实或证据" in discovery_system_prompt
    assert "不能成立" in discovery_system_prompt
    assert "1914 Christmas Truce shared meal primary source" in seen_queries


@pytest.mark.asyncio
async def test_topic_seed_candidate_must_bind_an_existing_frozen_map_dimension() -> None:
    bundle = await _content_world_bundle()
    rejected_entity = "an unrelated red-carpet rumor"
    rejected_query = "unrelated red-carpet rumor"
    research_model = SequencedStructuredFakeModel(
        {
            ResearchDiscoveryDraft: {
                "candidates": [
                    {
                        "candidate_id": "seed-off-map",
                        "map_dimension": "celebrity gossip",
                        "map_path_id": "path-that-does-not-exist",
                        "entity": rejected_entity,
                        "relation_to_root": "none established",
                        "why_worth_reading": "the user mentioned it",
                        "search_queries": [rejected_query],
                    }
                ],
                "unknowns": [],
            },
            EvidenceReadingDraft: {
                **_reading_payload(),
                "selected_candidate_id": "map-direction-1-1",
                "selected_entity": "a documented neighborhood meal",
            },
            TopicEditorialDecisionDraft: _editorial_payload(candidate_id="map-direction-1-1"),
        }
    )
    seen_queries: list[str] = []

    async def search(query: str, max_results: int) -> tuple[ResearchSearchResult, ...]:
        seen_queries.append(query)
        return (
            ResearchSearchResult(
                title="Neighborhood meal record",
                url="https://example.com/neighborhood-meal",
                content="A public record names and dates a neighborhood meal.",
            ),
        )

    enriched = await enrich_content_world_with_research(
        bundle,
        model=research_model,
        search=search,
        topic_seed=rejected_entity,
    )

    assert rejected_query not in seen_queries
    assert any(rejected_entity in unknown.question for unknown in enriched.record.unknowns)
    assert research_model.schemas == [ResearchDiscoveryDraft]
    assert enriched.topic_brief is None


@pytest.mark.asyncio
async def test_rejected_topic_seed_unknown_survives_when_search_returns_no_evidence() -> None:
    bundle = await _content_world_bundle()
    rejection_unknown = "The user lead has no verified path to the frozen map."
    research_model = SequencedStructuredFakeModel(
        {
            ResearchDiscoveryDraft: {
                "candidates": [],
                "unknowns": [rejection_unknown],
            },
        }
    )

    async def search(query: str, max_results: int) -> tuple[ResearchSearchResult, ...]:
        return ()

    enriched = await enrich_content_world_with_research(
        bundle,
        model=research_model,
        search=search,
        topic_seed="unverified current-event claim",
    )

    assert research_model.schemas == [ResearchDiscoveryDraft]
    assert rejection_unknown in {unknown.question for unknown in enriched.record.unknowns}


@pytest.mark.asyncio
async def test_topic_seed_with_no_public_evidence_gets_an_explicit_unknown() -> None:
    bundle = await _content_world_bundle()
    discovery = _discovery_payload()
    discovery["candidates"][0].update(
        {
            "candidate_id": "candidate-user-seed",
            "entity": "an alleged public event",
            "search_queries": ["alleged public event primary source"],
        }
    )
    research_model = SequencedStructuredFakeModel({ResearchDiscoveryDraft: discovery})

    async def search(query: str, max_results: int) -> tuple[ResearchSearchResult, ...]:
        return ()

    enriched = await enrich_content_world_with_research(
        bundle,
        model=research_model,
        search=search,
        topic_seed="Did the alleged public event really happen?",
    )

    assert research_model.schemas == [ResearchDiscoveryDraft]
    assert any("could not be verified against public evidence" in unknown.question for unknown in enriched.record.unknowns)


@pytest.mark.asyncio
async def test_user_topic_seed_cannot_enter_the_evidence_receipt_by_itself() -> None:
    bundle = await _content_world_bundle()
    original_source_ids = {source.source_id for source in bundle.record.sources}
    rejected_seed = "An unsupported celebrity rumor about a restaurant"
    rejection_unknown = "The user-provided lead has no verified path to the frozen shared-meal map."
    research_model = SequencedStructuredFakeModel(
        {
            ResearchDiscoveryDraft: {
                "candidates": [],
                "unknowns": [rejection_unknown],
            },
            EvidenceReadingDraft: {
                **_reading_payload(),
                "selected_candidate_id": "map-direction-1-1",
                "selected_entity": "a documented neighborhood meal",
            },
            TopicEditorialDecisionDraft: _editorial_payload(candidate_id="map-direction-1-1"),
        }
    )

    async def search(query: str, max_results: int) -> tuple[ResearchSearchResult, ...]:
        return (
            ResearchSearchResult(
                title="Neighborhood meal record",
                url="https://example.com/neighborhood-meal-record",
                content="A dated public record identifies a neighborhood meal.",
            ),
        )

    enriched = await enrich_content_world_with_research(
        bundle,
        model=research_model,
        search=search,
        topic_seed=rejected_seed,
    )

    discovery_input = research_model.message_batches[0][1].content
    assert rejected_seed in discovery_input
    research_sources = tuple(source for source in enriched.record.sources if source.source_id not in original_source_ids)
    assert research_sources == ()
    assert all(rejected_seed not in observation.claim for observation in enriched.record.observations)
    assert research_model.schemas == [ResearchDiscoveryDraft]


@pytest.mark.asyncio
async def test_discovery_can_reject_a_topic_seed_and_expose_the_unknown() -> None:
    bundle = await _content_world_bundle()
    rejected_seed = "An unrelated celebrity red-carpet rumor"
    rejection_unknown = "The supplied lead does not yet have a rooted path through this content map."
    research_model = SequencedStructuredFakeModel(
        {
            ResearchDiscoveryDraft: {
                "candidates": [],
                "unknowns": [rejection_unknown],
            },
            EvidenceReadingDraft: {
                **_reading_payload(),
                "selected_candidate_id": "map-direction-1-1",
                "selected_entity": "a documented neighborhood meal",
            },
            TopicEditorialDecisionDraft: _editorial_payload(candidate_id="map-direction-1-1"),
        }
    )
    seen_queries: list[str] = []

    async def search(query: str, max_results: int) -> tuple[ResearchSearchResult, ...]:
        seen_queries.append(query)
        return (
            ResearchSearchResult(
                title="Neighborhood meal record",
                url="https://example.com/neighborhood-meal",
                content="A public record names and dates a neighborhood meal.",
            ),
        )

    enriched = await enrich_content_world_with_research(
        bundle,
        model=research_model,
        search=search,
        topic_seed=rejected_seed,
    )

    assert all(rejected_seed not in query for query in seen_queries)
    assert rejection_unknown in {unknown.question for unknown in enriched.record.unknowns}
    assert enriched.topic_brief is None
    assert research_model.schemas == [ResearchDiscoveryDraft]


@pytest.mark.asyncio
async def test_topic_seed_cannot_fall_back_to_an_unrelated_generic_map_topic() -> None:
    bundle = await _content_world_bundle()
    rejection_unknown = "The supplied film has no verified path through this content map."
    research_model = SequencedStructuredFakeModel(
        {
            ResearchDiscoveryDraft: {
                "candidates": [],
                "unknowns": [rejection_unknown],
            },
        }
    )

    async def search(query: str, max_results: int) -> tuple[ResearchSearchResult, ...]:
        return (
            ResearchSearchResult(
                title="A generic shared-meal record",
                url="https://example.com/generic-shared-meal",
                content="This source supports a map direction but says nothing about the user's film.",
            ),
        )

    enriched = await enrich_content_world_with_research(
        bundle,
        model=research_model,
        search=search,
        topic_seed="今天的《牛来》为什么会火？",
    )

    assert research_model.schemas == [ResearchDiscoveryDraft]
    assert enriched.topic_brief is None
    assert rejection_unknown in {unknown.question for unknown in enriched.record.unknowns}


@pytest.mark.asyncio
async def test_topic_brief_preserves_the_exact_frozen_map_path_before_the_grounded_anchor() -> None:
    bundle = await _content_world_bundle()
    world = bundle.content_world
    assert world is not None and world.content_root is not None
    frozen_path = ContentPath(
        path_id="path-oyster-literature",
        steps=(
            ContentPathStep(
                from_label=world.content_root,
                relation="向下进入具体食材",
                to_label="共享餐桌上的海鲜",
                status="candidate",
                verification_needed=True,
            ),
            ContentPathStep(
                from_label="共享餐桌上的海鲜",
                relation="继续细分",
                to_label="牡蛎",
                status="candidate",
                verification_needed=True,
            ),
            ContentPathStep(
                from_label="牡蛎",
                relation="进入文学作品中的具体场面",
                to_label="文学中的牡蛎场景",
                status="candidate",
                verification_needed=True,
            ),
        ),
        rationale="沿具体食材进入一部作品中的人物关系变化。",
    )
    world = world.model_copy(
        update={
            "dimensions": (
                ContentDimension(
                    name="食物与文学",
                    rationale="食物怎样进入具体作品并照见人物关系。",
                    paths=(frozen_path,),
                ),
            )
        }
    )
    bundle = bundle.model_copy(update={"content_world": world})
    reading = _reading_payload(source_ref="source-web-2")
    reading.update(
        {
            "selected_candidate_id": "candidate-my-uncle-jules",
            "selected_entity": "《我的叔叔于勒》",
        }
    )
    research_model = SequencedStructuredFakeModel(
        {
            ResearchDiscoveryDraft: {
                "candidates": [
                    {
                        "candidate_id": "candidate-my-uncle-jules",
                        "map_dimension": "食物与文学",
                        "map_path_id": frozen_path.path_id,
                        "entity": "《我的叔叔于勒》",
                        "relation_to_root": "作品中的牡蛎场景沿冻结路径显出一家人对身份和金钱的态度变化",
                        "why_worth_reading": "它把宽泛地图落到一篇具体作品和一个具体场面",
                        "search_queries": ["我的叔叔于勒 牡蛎 原文"],
                    }
                ],
                "unknowns": [],
            },
            EvidenceReadingDraft: reading,
            TopicEditorialDecisionDraft: _editorial_payload(candidate_id="candidate-my-uncle-jules"),
        }
    )

    async def search(query: str, max_results: int) -> tuple[ResearchSearchResult, ...]:
        return (
            ResearchSearchResult(
                title=query,
                url=f"https://example.com/source-{abs(hash(query))}",
                content="A bounded public text connects the named work, its oyster scene, and the family's changed treatment of Yule.",
            ),
        )

    enriched = await enrich_content_world_with_research(
        bundle,
        model=research_model,
        search=search,
        topic_seed="《我的叔叔于勒》里为什么一定要写牡蛎？",
    )

    assert enriched.topic_brief is not None
    actual_steps = enriched.topic_brief.path.steps
    assert actual_steps[: len(frozen_path.steps)] == frozen_path.steps
    assert actual_steps[-1].from_label == "文学中的牡蛎场景"
    assert actual_steps[-1].to_label == "《我的叔叔于勒》"
    assert actual_steps[-1].status == "grounded"


@pytest.mark.asyncio
async def test_research_without_topic_seed_preserves_the_existing_discovery_input_and_queries() -> None:
    bundle = await _content_world_bundle()
    research_model = SequencedStructuredFakeModel(
        {
            ResearchDiscoveryDraft: _discovery_payload(),
            EvidenceReadingDraft: _reading_payload(),
            TopicEditorialDecisionDraft: _editorial_payload(),
        }
    )
    seen_queries: list[str] = []

    async def search(query: str, max_results: int) -> tuple[ResearchSearchResult, ...]:
        seen_queries.append(query)
        return (
            ResearchSearchResult(
                title="Public archive entry",
                url="https://example.com/archive-entry",
                content="A dated archive snippet describing the public event and the shared meal.",
            ),
        )

    await enrich_content_world_with_research(
        bundle,
        model=research_model,
        search=search,
    )

    discovery_input = research_model.message_batches[0][1].content
    reading_input = research_model.message_batches[1][1].content
    assert '"user_topic_seed"' not in discovery_input
    assert '"frozen_map_dimensions"' not in reading_input
    assert research_model.message_batches[0][0].content == RESEARCH_DISCOVERY_SYSTEM_PROMPT
    assert research_model.message_batches[1][0].content == EVIDENCE_READING_SYSTEM_PROMPT
    assert set(seen_queries) == {
        "shared meal how the shared meal carries emotion and group belonging",
        "shared meal documented changes in the shared meal over time",
        "shared meal documented public event",
    }


@pytest.mark.asyncio
async def test_latent_recall_route_cannot_launder_a_different_selected_entity() -> None:
    bundle = await _content_world_bundle()
    reading = _reading_payload(source_ref="source-web-2")
    reading["selected_entity"] = "a different unsupported event"
    research_model = SequencedStructuredFakeModel(
        {
            ResearchDiscoveryDraft: _discovery_payload(),
            EvidenceReadingDraft: reading,
            TopicEditorialDecisionDraft: _editorial_payload(),
        }
    )

    async def search(query: str, max_results: int) -> tuple[ResearchSearchResult, ...]:
        return (
            ResearchSearchResult(
                title=query,
                url=f"https://example.com/{abs(hash(query))}",
                content=f"Evidence for {query}.",
            ),
        )

    with pytest.raises(ValueError, match="changed the latent recall entity"):
        await enrich_content_world_with_research(
            bundle,
            model=research_model,
            search=search,
            budget=ResearchBudget(max_queries=3, max_results_per_query=1, max_evidence_items=3),
        )


@pytest.mark.asyncio
async def test_latent_entity_drift_gets_one_bounded_contract_repair() -> None:
    bundle = await _content_world_bundle()
    invalid_reading = _reading_payload(source_ref="source-web-2")
    invalid_reading["selected_entity"] = "a renamed event"
    research_model = SequencedStructuredFakeModel(
        {
            ResearchDiscoveryDraft: _discovery_payload(),
            EvidenceReadingDraft: [
                invalid_reading,
                _reading_payload(source_ref="source-web-2"),
            ],
            TopicEditorialDecisionDraft: _editorial_payload(),
        }
    )

    async def search(query: str, max_results: int) -> tuple[ResearchSearchResult, ...]:
        return (
            ResearchSearchResult(
                title=query,
                url=f"https://example.com/{abs(hash(query))}",
                content=f"Evidence for {query}.",
            ),
        )

    enriched = await enrich_content_world_with_research(
        bundle,
        model=research_model,
        search=search,
        budget=ResearchBudget(max_queries=3, max_results_per_query=1, max_evidence_items=3),
    )

    assert enriched.topic_brief is not None
    assert research_model.call_schemas.count(EvidenceReadingDraft) == 2
    repair_messages = research_model.message_batches[2]
    assert "a documented public event" in repair_messages[-1].content
    assert "a renamed event" in repair_messages[-1].content


@pytest.mark.asyncio
async def test_frozen_map_can_grow_into_an_evidence_bound_topic_brief() -> None:
    bundle = await _content_world_bundle()
    assert bundle.content_world is not None
    frozen_map_version = bundle.content_world.content_map_version_id()
    research_model = SequencedStructuredFakeModel(
        {
            ResearchDiscoveryDraft: _discovery_payload(),
            EvidenceReadingDraft: _reading_payload(),
            TopicEditorialDecisionDraft: _editorial_payload(),
        }
    )
    seen_queries: list[tuple[str, int]] = []

    async def search(query: str, max_results: int) -> tuple[ResearchSearchResult, ...]:
        seen_queries.append((query, max_results))
        return (
            ResearchSearchResult(
                title="Public archive entry",
                url="https://example.com/archive-entry",
                content="A dated archive snippet describing the public event and the shared meal.",
            ),
        )

    enriched = await enrich_content_world_with_research(
        bundle,
        model=research_model,
        search=search,
        budget=ResearchBudget(max_queries=6, max_results_per_query=4, max_evidence_items=12),
    )

    assert research_model.schemas == [
        ResearchDiscoveryDraft,
        EvidenceReadingDraft,
        TopicEditorialDecisionDraft,
    ]
    assert len(seen_queries) == 3
    assert ("shared meal documented public event", 4) in seen_queries
    assert all(max_results == 4 for _, max_results in seen_queries)
    assert all("人物 事件 作品 记录" not in query for query, _ in seen_queries)
    assert "shared meal how the shared meal carries emotion and group belonging" in {query for query, _ in seen_queries}
    assert "shared meal documented changes in the shared meal over time" in {query for query, _ in seen_queries}
    discovery_input = research_model.message_batches[0][1].content
    assert '"content_root": "shared meal"' in discovery_input
    assert f'"content_map_version_id": "{frozen_map_version}"' in discovery_input
    assert '"editorial_promise"' in discovery_input
    assert '"recurring_lens"' in discovery_input
    assert '"map_dimensions"' in discovery_input
    assert "regional meal base" not in discovery_input
    assert "business_semantics" not in discovery_input
    reading_input = research_model.message_batches[1][1].content
    assert '"source_id": "source-web-1"' in reading_input
    assert '"discovery_mode": "map_direction_search"' in reading_input
    assert '"discovery_mode": "latent_recall"' in reading_input
    assert '"why_worth_reading"' not in reading_input
    assert '"search_query"' not in reading_input
    assert "untrusted evidence" in research_model.message_batches[1][0].content.lower()
    editorial_input = research_model.message_batches[2][1].content
    assert '"selected_candidate_id": "candidate-public-record"' in editorial_input
    assert '"observations"' in editorial_input
    assert '"why_worth_reading"' not in editorial_input
    assert '"search_queries"' not in editorial_input
    assert "regional meal base" not in editorial_input
    assert "叙事结构" in research_model.message_batches[2][0].content

    assert enriched.content_world is not None
    assert enriched.content_world.content_root == "shared meal"
    assert enriched.content_world.content_map_version_id() == frozen_map_version
    assert enriched.topic_brief is not None
    assert enriched.topic_brief.content_map_version_id == frozen_map_version
    assert enriched.topic_brief.question.startswith("How did one public event")
    assert enriched.topic_brief.path.steps[0].from_label == "shared meal"
    assert enriched.topic_brief.path.steps[-1].to_label == "a documented public event"
    assert enriched.topic_brief.path.rationale == "The documented event connects a concrete change with the frozen content root."
    assert enriched.topic_brief.evidence_refs[0].ref_id == "research-observation-1"
    assert enriched.topic_brief.limitations == ("The current topic is supported by one bounded evidence receipt.",)
    assert enriched.record.sources[-1].uri == "https://example.com/archive-entry"
    assert enriched.record.observations[-1].source_refs == ("source-web-1",)
    assert enriched.record.interpretations[-1].limitations

    rendered = render_content_world_narration(
        enriched,
        "# shared meal\n\nA rooted map of the shared meal.",
    )
    assert "一条已经取证的具体选题" in rendered
    assert "How did one public event" in rendered
    assert "[Public archive entry](https://example.com/archive-entry)" in rendered
    assert "Open and compare the full source" in rendered


@pytest.mark.asyncio
async def test_search_result_is_opened_before_evidence_reading_when_fetch_is_available() -> None:
    bundle = await _content_world_bundle()
    research_model = SequencedStructuredFakeModel(
        {
            ResearchDiscoveryDraft: _discovery_payload(),
            EvidenceReadingDraft: _reading_payload(),
            TopicEditorialDecisionDraft: _editorial_payload(),
        }
    )
    fetched_urls: list[str] = []

    async def search(query: str, max_results: int) -> tuple[ResearchSearchResult, ...]:
        return (
            ResearchSearchResult(
                title="Primary public record",
                url="https://example.com/primary-record",
                content="SEARCH RESULT SNIPPET ONLY",
            ),
        )

    async def fetch(url: str) -> str | None:
        fetched_urls.append(url)
        return "FULL PAGE: the dated public record describes the event, action, and outcome."

    enriched = await enrich_content_world_with_research(
        bundle,
        model=research_model,
        search=search,
        fetch=fetch,
    )

    assert fetched_urls == ["https://example.com/primary-record"]
    reading_input = research_model.message_batches[1][1].content
    assert "FULL PAGE: the dated public record" in reading_input
    assert "SEARCH RESULT SNIPPET ONLY" not in reading_input
    assert enriched.record.sources[-1].kind == "web_page"
    assert enriched.record.sources[-1].content.startswith("FULL PAGE:")


@pytest.mark.asyncio
async def test_fetch_failure_keeps_the_search_receipt_available_to_evidence_reading() -> None:
    bundle = await _content_world_bundle()
    research_model = SequencedStructuredFakeModel(
        {
            ResearchDiscoveryDraft: _discovery_payload(),
            EvidenceReadingDraft: _reading_payload(),
            TopicEditorialDecisionDraft: _editorial_payload(),
        }
    )

    async def search(query: str, max_results: int) -> tuple[ResearchSearchResult, ...]:
        return (
            ResearchSearchResult(
                title="Public record search result",
                url="https://example.com/unavailable-page",
                content="BOUNDED SEARCH RECEIPT",
            ),
        )

    async def failed_fetch(url: str) -> str | None:
        return "Error: upstream reader unavailable"

    enriched = await enrich_content_world_with_research(
        bundle,
        model=research_model,
        search=search,
        fetch=failed_fetch,
    )

    assert "BOUNDED SEARCH RECEIPT" in research_model.message_batches[1][1].content
    assert enriched.record.sources[-1].kind == "web_search_result"
    assert enriched.record.sources[-1].evidence_role == "topic_evidence"
    assert '"evidence_role": "topic_evidence"' in research_model.message_batches[1][1].content
    assert "benchmark_account" not in research_model.message_batches[1][1].content


@pytest.mark.asyncio
async def test_evidence_bound_story_frame_is_preserved_and_rendered_after_the_map() -> None:
    bundle = await _content_world_bundle()
    narrative_frame = {
        "protagonist": "a participant",
        "goal": "preserve the public meal",
        "obstacle": "the original gathering could no longer proceed",
        "action_or_choice": "the participant reorganized the event",
        "stakes_or_consequence": "a shared practice might disappear",
        "outcome_or_change": "the practice continued with a changed public meaning",
        "evidence_observation_refs": ["reading-observation-1"],
        "limitations": ["The full record still needs verification."],
    }
    research_model = SequencedStructuredFakeModel(
        {
            ResearchDiscoveryDraft: _discovery_payload(),
            EvidenceReadingDraft: _reading_payload(),
            TopicEditorialDecisionDraft: _editorial_payload(narrative_frame=narrative_frame),
        }
    )

    async def search(query: str, max_results: int) -> tuple[ResearchSearchResult, ...]:
        return (
            ResearchSearchResult(
                title="Public archive entry",
                url="https://example.com/story-record",
                content="A dated record of the participant's goal, obstacle, action, stakes, and outcome.",
            ),
        )

    enriched = await enrich_content_world_with_research(bundle, model=research_model, search=search)

    assert enriched.topic_brief is not None
    assert enriched.topic_brief.narrative_frame is not None
    assert enriched.topic_brief.narrative_frame.goal == "preserve the public meal"
    assert enriched.topic_brief.narrative_frame.basis_refs[0].ref_id == "research-observation-1"

    rendered = render_content_world_narration(enriched, "# shared meal\n\nA rooted map.")
    assert "**叙事骨架：**" in rendered
    assert "**主体：** a participant" in rendered
    assert "**阻碍：** the original gathering could no longer proceed" in rendered
    assert enriched.record.sources[-1].uri == "https://example.com/story-record"


@pytest.mark.asyncio
async def test_search_failure_preserves_the_rooted_map_without_inventing_a_topic() -> None:
    bundle = await _content_world_bundle()
    research_model = SequencedStructuredFakeModel(
        {
            ResearchDiscoveryDraft: _discovery_payload(),
            EvidenceReadingDraft: _reading_payload(),
            TopicEditorialDecisionDraft: _editorial_payload(),
        }
    )

    async def no_results(query: str, max_results: int) -> tuple[ResearchSearchResult, ...]:
        return ()

    enriched = await enrich_content_world_with_research(
        bundle,
        model=research_model,
        search=no_results,
    )

    assert research_model.schemas == [ResearchDiscoveryDraft]
    assert enriched is bundle
    assert enriched.content_world.content_root == "shared meal"
    assert enriched.topic_brief is None


@pytest.mark.asyncio
async def test_weak_evidence_can_abstain_without_forcing_a_topic() -> None:
    bundle = await _content_world_bundle()
    research_model = SequencedStructuredFakeModel(
        {
            ResearchDiscoveryDraft: _discovery_payload(),
            EvidenceReadingDraft: _reading_payload(),
            TopicEditorialDecisionDraft: {
                "selected_candidate_id": "candidate-public-record",
                "topic_brief": None,
                "abstention_reason": "The promotional receipt cannot support a topic claim.",
            },
        }
    )

    async def weak_search(query: str, max_results: int) -> tuple[ResearchSearchResult, ...]:
        return (
            ResearchSearchResult(
                title="Promotional course listing",
                url="https://example.com/buy-this-course",
                content="Book this experience now.",
            ),
        )

    enriched = await enrich_content_world_with_research(bundle, model=research_model, search=weak_search)

    assert enriched is bundle
    assert enriched.content_world.content_root == "shared meal"
    assert enriched.topic_brief is None
    assert research_model.schemas == [
        ResearchDiscoveryDraft,
        EvidenceReadingDraft,
        TopicEditorialDecisionDraft,
    ]


@pytest.mark.asyncio
async def test_search_budget_gives_both_lanes_a_turn_before_reusing_a_latent_candidate() -> None:
    bundle = await _content_world_bundle()
    discovery = _discovery_payload()
    discovery["candidates"] = [
        {
            "candidate_id": f"candidate-{index}",
            "map_dimension": "history and public records",
            "map_path_id": "path-direction-2-1",
            "entity": f"public subject {index}",
            "relation_to_root": "reveals one rooted public meaning",
            "why_worth_reading": "turns one map branch into a concrete question",
            "search_queries": [f"candidate {index} first", f"candidate {index} second"],
        }
        for index in range(1, 4)
    ]
    reading = _reading_payload(source_ref="source-web-2")
    reading["selected_candidate_id"] = "candidate-1"
    reading["selected_entity"] = "public subject 1"
    research_model = SequencedStructuredFakeModel(
        {
            ResearchDiscoveryDraft: discovery,
            EvidenceReadingDraft: reading,
            TopicEditorialDecisionDraft: _editorial_payload(candidate_id="candidate-1"),
        }
    )
    seen_queries: list[str] = []

    async def search(query: str, max_results: int) -> tuple[ResearchSearchResult, ...]:
        seen_queries.append(query)
        return (
            ResearchSearchResult(
                title=query,
                url=f"https://example.com/{len(seen_queries)}",
                content=f"Evidence for {query}.",
            ),
        )

    enriched = await enrich_content_world_with_research(
        bundle,
        model=research_model,
        search=search,
        budget=ResearchBudget(max_queries=5, max_results_per_query=1, max_evidence_items=5),
    )

    assert seen_queries[0].startswith("shared meal ")
    assert {f"candidate {index} first" for index in range(1, 4)}.issubset(seen_queries)
    assert not any(query.endswith("second") for query in seen_queries)
    assert all("人物 事件 作品 记录" not in query for query in seen_queries)
    assert enriched.topic_brief is not None
    editorial_input = research_model.message_batches[2][1].content
    assert "candidate 1 first" in editorial_input
    assert "candidate 2 first" not in editorial_input
    assert "candidate 3 first" not in editorial_input


@pytest.mark.asyncio
async def test_reading_cannot_reference_evidence_outside_the_search_receipt() -> None:
    bundle = await _content_world_bundle()
    research_model = SequencedStructuredFakeModel(
        {
            ResearchDiscoveryDraft: _discovery_payload(),
            EvidenceReadingDraft: _reading_payload(source_ref="source-web-invented"),
            TopicEditorialDecisionDraft: _editorial_payload(),
        }
    )

    async def search(query: str, max_results: int) -> tuple[ResearchSearchResult, ...]:
        return (
            ResearchSearchResult(
                title="Known source",
                url="https://example.com/known",
                content="Known evidence.",
            ),
        )

    with pytest.raises(ValueError, match="outside the search receipt"):
        await enrich_content_world_with_research(bundle, model=research_model, search=search)


@pytest.mark.asyncio
async def test_reading_cannot_use_another_candidates_evidence() -> None:
    bundle = await _content_world_bundle()
    discovery = _discovery_payload()
    discovery["candidates"].append(
        {
            "candidate_id": "candidate-other-record",
            "map_dimension": "history and public records",
            "map_path_id": "path-direction-2-1",
            "entity": "another documented event",
            "relation_to_root": "a separate candidate path",
            "why_worth_reading": "it may support a different question",
            "search_queries": ["another documented event"],
        }
    )
    research_model = SequencedStructuredFakeModel(
        {
            ResearchDiscoveryDraft: discovery,
            EvidenceReadingDraft: _reading_payload(source_ref="source-web-4"),
            TopicEditorialDecisionDraft: _editorial_payload(),
        }
    )

    async def search(query: str, max_results: int) -> tuple[ResearchSearchResult, ...]:
        return (
            ResearchSearchResult(
                title=query,
                url=f"https://example.com/{query.replace(' ', '-')}",
                content=f"Evidence only for {query}.",
            ),
        )

    with pytest.raises(ValueError, match="selected candidate"):
        await enrich_content_world_with_research(bundle, model=research_model, search=search)


@pytest.mark.asyncio
async def test_unselected_route_noise_is_excluded_without_discarding_the_selected_reading() -> None:
    bundle = await _content_world_bundle()
    reading = _reading_payload(source_ref="source-web-1")
    reading.update(
        {
            "selected_candidate_id": "map-direction-1-1",
            "selected_entity": "a documented community meal",
        }
    )
    reading["observations"].append(
        {
            "observation_id": "reading-noise-observation",
            "claim": "A different candidate returned an unrelated promotional result.",
            "source_refs": ["source-web-2"],
        }
    )
    research_model = SequencedStructuredFakeModel(
        {
            ResearchDiscoveryDraft: _discovery_payload(),
            EvidenceReadingDraft: reading,
            TopicEditorialDecisionDraft: _editorial_payload(candidate_id="map-direction-1-1"),
        }
    )

    async def search(query: str, max_results: int) -> tuple[ResearchSearchResult, ...]:
        return (
            ResearchSearchResult(
                title=query,
                url=f"https://example.com/{abs(hash(query))}",
                content=f"Evidence for {query}.",
            ),
        )

    enriched = await enrich_content_world_with_research(bundle, model=research_model, search=search)

    assert enriched.topic_brief is not None
    assert all(observation.claim != reading["observations"][-1]["claim"] for observation in enriched.record.observations)
    assert len(enriched.record.sources) == len(bundle.record.sources) + 1
    assert enriched.record.sources[-1].source_id == "source-web-1"


@pytest.mark.asyncio
async def test_narrative_only_evidence_is_preserved_in_topic_refs_and_citations() -> None:
    bundle = await _content_world_bundle()
    reading = _reading_payload()
    reading["observations"].append(
        {
            "observation_id": "reading-observation-2",
            "claim": "A second source records the participant's action and outcome.",
            "source_refs": ["source-web-2"],
        }
    )
    editorial = _editorial_payload(
        narrative_frame={
            "protagonist": "a participant",
            "goal": "preserve the public meal",
            "obstacle": "the original gathering could no longer proceed",
            "action_or_choice": "the participant reorganized the event",
            "stakes_or_consequence": "a shared practice might disappear",
            "outcome_or_change": "the practice continued with a changed public meaning",
            "evidence_observation_refs": ["reading-observation-2"],
            "limitations": ["The action chain is supported by the second source."],
        }
    )
    research_model = SequencedStructuredFakeModel(
        {
            ResearchDiscoveryDraft: _discovery_payload(),
            EvidenceReadingDraft: reading,
            TopicEditorialDecisionDraft: editorial,
        }
    )

    async def search(query: str, max_results: int) -> tuple[ResearchSearchResult, ...]:
        return (
            ResearchSearchResult(
                title="Context record",
                url="https://example.com/context-record",
                content="Evidence for the topic's central claim.",
            ),
            ResearchSearchResult(
                title="Action record",
                url="https://example.com/action-record",
                content="Evidence for the participant's action and outcome.",
            ),
        )

    enriched = await enrich_content_world_with_research(bundle, model=research_model, search=search)

    assert enriched.topic_brief is not None
    assert [ref.ref_id for ref in enriched.topic_brief.evidence_refs] == [
        "research-observation-1",
        "research-observation-2",
    ]
    rendered = render_content_world_narration(enriched, "# shared meal\n\nA rooted map.")
    assert "[Context record](https://example.com/context-record)" in rendered
    assert "[Action record](https://example.com/action-record)" in rendered


def test_research_contract_has_no_required_candidate_or_query_quota() -> None:
    discovery_schema = ResearchDiscoveryDraft.model_json_schema()

    assert "minItems" not in discovery_schema["properties"]["candidates"]
    assert "maxItems" not in discovery_schema["properties"]["candidates"]
    assert "content_root" not in EvidenceReadingDraft.model_json_schema()["properties"]
    assert "selected_entity" in EvidenceReadingDraft.model_json_schema()["required"]
    assert "selected_entity_observation_refs" in EvidenceReadingDraft.model_json_schema()["required"]


def test_topic_editor_keeps_story_structure_optional_but_complete_when_used() -> None:
    explanatory = TopicEditorialDecisionDraft.model_validate(_editorial_payload())

    assert explanatory.topic_brief is not None
    assert explanatory.topic_brief.narrative_frame is None

    complete_story = _editorial_payload(
        narrative_frame={
            "protagonist": "a participant",
            "goal": "preserve the public meal",
            "obstacle": "the original gathering could no longer proceed",
            "action_or_choice": "the participant reorganized the event",
            "stakes_or_consequence": "a shared practice might disappear",
            "outcome_or_change": "the practice continued with a changed public meaning",
            "evidence_observation_refs": ["reading-observation-1"],
            "limitations": ["The full record still needs verification."],
        }
    )

    story = TopicEditorialDecisionDraft.model_validate(complete_story)
    assert story.topic_brief is not None
    assert story.topic_brief.narrative_frame is not None
    assert story.topic_brief.narrative_frame.obstacle.startswith("the original")

    incomplete_story = _editorial_payload(
        narrative_frame={
            "protagonist": "a participant",
            "goal": "preserve the public meal",
            "obstacle": "the original gathering could no longer proceed",
            "evidence_observation_refs": ["reading-observation-1"],
        }
    )
    with pytest.raises(ValidationError):
        TopicEditorialDecisionDraft.model_validate(incomplete_story)


def test_topic_editor_requires_an_explicit_abstention_instead_of_an_empty_answer() -> None:
    with pytest.raises(ValidationError, match="topic or an abstention"):
        TopicEditorialDecisionDraft.model_validate(
            {
                "selected_candidate_id": "candidate-public-record",
                "topic_brief": None,
                "abstention_reason": None,
            }
        )


def test_research_defaults_bound_cost_without_becoming_a_business_quota() -> None:
    budget = ResearchBudget()

    assert (
        budget.max_queries,
        budget.max_concurrent_queries,
        budget.max_results_per_query,
        budget.max_evidence_items,
    ) == (6, 3, 3, 8)
    assert "人的行为、关系、情绪、选择、变化或共同记忆" in RESEARCH_DISCOVERY_SYSTEM_PROMPT
    assert "冲突" not in RESEARCH_DISCOVERY_SYSTEM_PROMPT
    assert "博弈" not in RESEARCH_DISCOVERY_SYSTEM_PROMPT
    assert "卖方经营案例" in RESEARCH_DISCOVERY_SYSTEM_PROMPT
    assert "可核验的专名对象" in RESEARCH_DISCOVERY_SYSTEM_PROMPT
    assert "泛化教程词" in RESEARCH_DISCOVERY_SYSTEM_PROMPT
    assert "售卖页、推广页、聚合页、社交收藏页" in EVIDENCE_READING_SYSTEM_PROMPT
    assert "不负责立题或编排故事" in EVIDENCE_READING_SYSTEM_PROMPT
    assert "topic_brief" not in EvidenceReadingDraft.model_json_schema()["properties"]
    assert "创意收敛器" in TOPIC_EDITOR_SYSTEM_PROMPT
    assert "主体想达成的具体目标" in TOPIC_EDITOR_SYSTEM_PROMPT
    assert "阻碍" in TOPIC_EDITOR_SYSTEM_PROMPT
    assert "采取的行动或选择" in TOPIC_EDITOR_SYSTEM_PROMPT
    assert "只有关系张力、观点差异、利益差异或情绪波动" in TOPIC_EDITOR_SYSTEM_PROMPT
    assert "narrative_frame 保持 null" in TOPIC_EDITOR_SYSTEM_PROMPT
    assert "召回理由和搜索词只是检索假设" in TOPIC_EDITOR_SYSTEM_PROMPT
    assert "同一命名对象内" in TOPIC_EDITOR_SYSTEM_PROMPT
    assert "不要求证据兑现召回理由" in TOPIC_EDITOR_SYSTEM_PROMPT
    assert "叙事主角必须是证据中的人或集体行动者" in TOPIC_EDITOR_SYSTEM_PROMPT
    assert "商品、品类、材质或抽象概念" in TOPIC_EDITOR_SYSTEM_PROMPT
    assert "人的关系、选择和变化" in TOPIC_EDITOR_SYSTEM_PROMPT
    assert "KTV" not in RESEARCH_DISCOVERY_SYSTEM_PROMPT
    assert "KTV" not in TOPIC_EDITOR_SYSTEM_PROMPT
