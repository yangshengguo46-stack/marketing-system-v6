from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import Field, field_validator, model_validator

from deerflow.content_intelligence.contracts import ContractModel, NonEmptyStr

RelationStatus = Literal[
    "lexical_observation",
    "commonsense_hypothesis",
    "user_correction",
]


class MarketingRelationDraft(ContractModel):
    source: NonEmptyStr
    relation: NonEmptyStr
    target: NonEmptyStr
    basis: NonEmptyStr
    status: RelationStatus


class MarketingRelation(ContractModel):
    relation_id: NonEmptyStr
    source: NonEmptyStr
    relation: NonEmptyStr
    target: NonEmptyStr
    basis: NonEmptyStr
    status: RelationStatus


class ContentRootCandidate(ContractModel):
    candidate_id: NonEmptyStr
    label: NonEmptyStr
    candidate_kind: NonEmptyStr
    relation_path: tuple[NonEmptyStr, ...] = ()
    return_path: NonEmptyStr
    content_capacity: NonEmptyStr
    limitations: tuple[NonEmptyStr, ...] = ()


class ContentRootCandidateDraft(ContractModel):
    label: NonEmptyStr
    candidate_kind: NonEmptyStr
    semantic_path: tuple[MarketingRelationDraft, ...] = Field(default=(), max_length=6)
    return_path: NonEmptyStr
    content_capacity: NonEmptyStr
    limitations: tuple[NonEmptyStr, ...] = ()


class SemanticComponentDraft(ContractModel):
    component_text: NonEmptyStr
    semantic_role: NonEmptyStr
    names_complete_world: bool
    rationale: NonEmptyStr
    return_path: NonEmptyStr | None = None
    content_capacity: NonEmptyStr | None = None
    limitations: tuple[NonEmptyStr, ...] = ()

    @field_validator("return_path", "content_capacity", mode="before")
    @classmethod
    def normalize_candidate_only_fields(cls, value):
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @model_validator(mode="after")
    def require_complete_world_fields(self) -> SemanticComponentDraft:
        if self.names_complete_world and (self.return_path is None or self.content_capacity is None):
            raise ValueError("complete-world semantic component requires return path and content capacity")
        return self


class ContentRootGraphDraft(ContractModel):
    commercial_object: NonEmptyStr
    candidates: tuple[ContentRootCandidateDraft, ...] = Field(min_length=2, max_length=6)
    semantic_components: tuple[SemanticComponentDraft, ...] = Field(default=(), max_length=8)
    unknowns: tuple[NonEmptyStr, ...] = ()

    @model_validator(mode="after")
    def validate_relation_graph(self) -> ContentRootGraphDraft:
        _validate_draft_parts(self.commercial_object, self.candidates)
        component_texts = tuple(item.component_text for item in self.semantic_components)
        if len(set(component_texts)) != len(component_texts):
            raise ValueError("semantic components must be unique")
        return self


class ContentRootGraph(ContractModel):
    subject_expression: NonEmptyStr
    commercial_object: NonEmptyStr
    relations: tuple[MarketingRelation, ...] = Field(default=(), max_length=24)
    candidates: tuple[ContentRootCandidate, ...] = Field(min_length=2, max_length=8)
    unknowns: tuple[NonEmptyStr, ...] = ()

    @model_validator(mode="after")
    def validate_relation_graph(self) -> ContentRootGraph:
        _validate_graph_parts(self.commercial_object, self.relations, self.candidates)
        return self

    def graph_id(self) -> str:
        canonical = json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return "root-graph-" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:20]


class CandidateAssessment(ContractModel):
    candidate_id: NonEmptyStr
    reason: NonEmptyStr
    limitation: NonEmptyStr | None = None


class PairwisePreference(ContractModel):
    left_candidate_id: NonEmptyStr
    right_candidate_id: NonEmptyStr
    preferred_candidate_id: NonEmptyStr
    reason: NonEmptyStr

    @model_validator(mode="after")
    def validate_pair(self) -> PairwisePreference:
        pair = {self.left_candidate_id, self.right_candidate_id}
        if len(pair) != 2:
            raise ValueError("pairwise comparison requires two distinct candidates")
        if self.preferred_candidate_id not in pair:
            raise ValueError("pairwise preference must select one compared candidate")
        return self


class ContentRootSelectionDraft(ContractModel):
    selected_candidate_id: NonEmptyStr
    comparison_order: tuple[NonEmptyStr, ...]
    assessments: tuple[CandidateAssessment, ...]
    pairwise_preferences: tuple[PairwisePreference, ...]
    rationale: NonEmptyStr
    unknowns: tuple[NonEmptyStr, ...] = ()


class ContentRootSelection(ContractModel):
    graph_id: NonEmptyStr
    selected_candidate_id: NonEmptyStr
    comparison_order: tuple[NonEmptyStr, ...]
    assessments: tuple[CandidateAssessment, ...]
    pairwise_preferences: tuple[PairwisePreference, ...] = ()
    rationale: NonEmptyStr
    unknowns: tuple[NonEmptyStr, ...] = ()
    frozen_candidate_ids: tuple[NonEmptyStr, ...] = Field(exclude=True, repr=False)

    @model_validator(mode="after")
    def validate_frozen_selection(self) -> ContentRootSelection:
        frozen = self.frozen_candidate_ids
        frozen_set = set(frozen)
        if len(frozen_set) != len(frozen):
            raise ValueError("frozen candidate ids must be unique")
        if self.selected_candidate_id not in frozen_set:
            raise ValueError("selected candidate must be frozen")
        if len(self.comparison_order) != len(frozen) or set(self.comparison_order) != frozen_set:
            raise ValueError("selection must rank every frozen candidate exactly once")
        if self.comparison_order[0] != self.selected_candidate_id:
            raise ValueError("selected candidate must lead the comparison order")

        assessed_ids = tuple(item.candidate_id for item in self.assessments)
        if len(assessed_ids) != len(frozen) or set(assessed_ids) != frozen_set:
            raise ValueError("selection must assess every frozen candidate exactly once")

        expected_pairs = {tuple(sorted((self.selected_candidate_id, candidate_id))) for candidate_id in frozen if candidate_id != self.selected_candidate_id}
        observed_pairs = {tuple(sorted((item.left_candidate_id, item.right_candidate_id))) for item in self.pairwise_preferences}
        if len(self.pairwise_preferences) != len(expected_pairs) or observed_pairs != expected_pairs:
            raise ValueError("selection must compare the winner with every alternative exactly once")
        if any(item.preferred_candidate_id not in frozen_set for item in self.pairwise_preferences):
            raise ValueError("pairwise preference must stay inside the frozen graph")
        return self


def bind_selection(
    graph: ContentRootGraph,
    draft: ContentRootSelectionDraft,
) -> ContentRootSelection:
    return ContentRootSelection(
        graph_id=graph.graph_id(),
        selected_candidate_id=draft.selected_candidate_id,
        comparison_order=draft.comparison_order,
        assessments=draft.assessments,
        pairwise_preferences=draft.pairwise_preferences,
        rationale=draft.rationale,
        unknowns=draft.unknowns,
        frozen_candidate_ids=tuple(candidate.candidate_id for candidate in graph.candidates),
    )


def bind_graph(
    subject_expression: str,
    draft: ContentRootGraphDraft,
) -> ContentRootGraph:
    candidate_drafts = _merge_candidate_drafts(draft)
    relation_by_fingerprint: dict[str, MarketingRelation] = {}
    candidates: list[ContentRootCandidate] = []
    for candidate in candidate_drafts:
        relation_path: list[str] = []
        for relation_draft in candidate.semantic_path:
            relation_payload = relation_draft.model_dump(mode="json")
            fingerprint = _content_fingerprint(relation_payload)
            relation_id = f"relation-{fingerprint[:16]}"
            relation = relation_by_fingerprint.setdefault(
                fingerprint,
                MarketingRelation(
                    relation_id=relation_id,
                    **relation_payload,
                ),
            )
            relation_path.append(relation.relation_id)

        candidate_payload = {
            "label": candidate.label,
            "candidate_kind": candidate.candidate_kind,
            "relation_path": relation_path,
        }
        candidates.append(
            ContentRootCandidate(
                candidate_id=f"candidate-{_content_fingerprint(candidate_payload)[:16]}",
                label=candidate.label,
                candidate_kind=candidate.candidate_kind,
                relation_path=tuple(relation_path),
                return_path=candidate.return_path,
                content_capacity=candidate.content_capacity,
                limitations=candidate.limitations,
            )
        )
    possible_labels = {
        *(candidate.label for candidate in draft.candidates),
        *(component.component_text for component in draft.semantic_components if component.names_complete_world),
    }
    truncated = len(candidate_drafts) < len(possible_labels)
    unknowns = draft.unknowns
    if truncated:
        unknowns = (
            *unknowns,
            "候选图受 8 项实验资源上限约束，部分低优先级开放候选未进入选择。",
        )
    return ContentRootGraph(
        subject_expression=subject_expression,
        commercial_object=draft.commercial_object,
        relations=tuple(relation_by_fingerprint.values()),
        candidates=tuple(candidates),
        unknowns=unknowns,
    )


def _merge_candidate_drafts(draft: ContentRootGraphDraft) -> tuple[ContentRootCandidateDraft, ...]:
    existing = {candidate.label: candidate for candidate in draft.candidates}
    commercial = existing[draft.commercial_object]
    ordered: list[ContentRootCandidateDraft] = [commercial]
    seen = {commercial.label}

    for component in draft.semantic_components:
        if not component.names_complete_world or component.component_text == draft.commercial_object:
            continue
        candidate = existing.get(component.component_text)
        if candidate is None:
            if component.return_path is None or component.content_capacity is None:
                raise ValueError("complete-world component is missing candidate fields")
            candidate = ContentRootCandidateDraft(
                label=component.component_text,
                candidate_kind=component.semantic_role,
                semantic_path=(
                    MarketingRelationDraft(
                        source=draft.commercial_object,
                        relation="contains_meaning_bearing_complete_component",
                        target=component.component_text,
                        basis=component.rationale,
                        status="commonsense_hypothesis",
                    ),
                ),
                return_path=component.return_path,
                content_capacity=component.content_capacity,
                limitations=component.limitations,
            )
        if candidate.label not in seen:
            ordered.append(candidate)
            seen.add(candidate.label)

    for candidate in draft.candidates:
        if candidate.label not in seen:
            ordered.append(candidate)
            seen.add(candidate.label)
    return tuple(ordered[:8])


def _validate_draft_parts(
    commercial_object: str,
    candidates: tuple[ContentRootCandidateDraft, ...],
) -> None:
    labels = tuple(item.label for item in candidates)
    if len(set(labels)) != len(labels):
        raise ValueError("candidate labels must be unique")
    object_candidates = [candidate for candidate in candidates if candidate.label == commercial_object and not candidate.semantic_path]
    if len(object_candidates) != 1:
        raise ValueError("candidate set must preserve the commercial object with an empty path")

    for candidate in candidates:
        if not candidate.semantic_path:
            if candidate.label != commercial_object:
                raise ValueError("only the commercial object may have an empty semantic path")
            continue
        current = commercial_object
        for relation in candidate.semantic_path:
            if relation.source != current:
                raise ValueError("candidate semantic path must form a continuous chain")
            current = relation.target
        if current != candidate.label:
            raise ValueError("candidate semantic path must terminate at the candidate label")


def _validate_graph_parts(
    commercial_object: str,
    relations: tuple[MarketingRelation, ...],
    candidates: tuple[ContentRootCandidate, ...],
) -> None:
    relation_ids = tuple(item.relation_id for item in relations)
    if len(set(relation_ids)) != len(relation_ids):
        raise ValueError("relation ids must be unique")
    candidate_ids = tuple(item.candidate_id for item in candidates)
    if len(set(candidate_ids)) != len(candidate_ids):
        raise ValueError("candidate ids must be unique")

    relation_by_id = {item.relation_id: item for item in relations}
    for candidate in candidates:
        if not candidate.relation_path:
            if candidate.label != commercial_object:
                raise ValueError("only the commercial object may have an empty relation path")
            continue

        current = commercial_object
        for relation_id in candidate.relation_path:
            relation = relation_by_id.get(relation_id)
            if relation is None:
                raise ValueError("candidate path must use a known relation")
            if relation.source != current:
                raise ValueError("candidate path relations must form a continuous chain")
            current = relation.target
        if current != candidate.label:
            raise ValueError("candidate path must terminate at the candidate label")


def _content_fingerprint(payload: dict) -> str:
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


__all__ = [
    "CandidateAssessment",
    "ContentRootCandidate",
    "ContentRootCandidateDraft",
    "ContentRootGraph",
    "ContentRootGraphDraft",
    "ContentRootSelection",
    "ContentRootSelectionDraft",
    "MarketingRelation",
    "MarketingRelationDraft",
    "PairwisePreference",
    "SemanticComponentDraft",
    "bind_graph",
    "bind_selection",
]
