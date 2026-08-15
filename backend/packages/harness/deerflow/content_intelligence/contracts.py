from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Iterable
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

NonEmptyStr = Annotated[str, Field(min_length=1)]
SourceRefs = Annotated[tuple[NonEmptyStr, ...], Field(min_length=1)]
BasisKind = Literal[
    "source",
    "observation",
    "entity",
    "role",
    "relation",
    "state_change",
    "interpretation",
    "counterevidence",
]
InterpretationKind = Literal["derived", "hypothesis"]
ClaimProvenance = Literal["observed", "derived", "hypothesis"]
EvidenceRole = Literal["user_material", "topic_evidence", "benchmark_account_candidate"]
OfferingRole = Literal[
    "complete_object_or_service",
    "intermediate_enabler",
    "operating_container",
    "ambiguous",
]


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class BasisRef(ContractModel):
    kind: BasisKind
    ref_id: NonEmptyStr


BasisRefs = Annotated[tuple[BasisRef, ...], Field(min_length=1)]


class SourceItem(ContractModel):
    source_id: NonEmptyStr
    kind: NonEmptyStr
    content: NonEmptyStr
    evidence_role: EvidenceRole | None = None
    title: NonEmptyStr | None = None
    uri: NonEmptyStr | None = None

    def content_hash(self) -> str:
        return hashlib.sha256(self.content.encode("utf-8")).hexdigest()


class Observation(ContractModel):
    observation_id: NonEmptyStr
    claim: NonEmptyStr
    source_refs: SourceRefs


class Entity(ContractModel):
    entity_id: NonEmptyStr
    label: NonEmptyStr
    entity_type: NonEmptyStr | None = None
    source_refs: SourceRefs


class RoleAssignment(ContractModel):
    role_id: NonEmptyStr
    entity_id: NonEmptyStr
    role: NonEmptyStr
    context: NonEmptyStr | None = None
    basis_refs: BasisRefs


class RelationEdge(ContractModel):
    relation_id: NonEmptyStr
    subject_entity_id: NonEmptyStr
    predicate: NonEmptyStr
    object_entity_id: NonEmptyStr
    provenance: ClaimProvenance
    basis_refs: tuple[BasisRef, ...] = ()
    limitations: tuple[NonEmptyStr, ...] = ()

    @model_validator(mode="after")
    def validate_grounding(self) -> RelationEdge:
        _validate_claim_grounding(
            label="relation",
            provenance=self.provenance,
            basis_refs=self.basis_refs,
            limitations=self.limitations,
        )
        return self


class StateChange(ContractModel):
    change_id: NonEmptyStr
    subject_entity_id: NonEmptyStr
    before: NonEmptyStr
    after: NonEmptyStr
    trigger: NonEmptyStr | None = None
    provenance: ClaimProvenance
    basis_refs: tuple[BasisRef, ...] = ()
    limitations: tuple[NonEmptyStr, ...] = ()

    @model_validator(mode="after")
    def validate_grounding(self) -> StateChange:
        _validate_claim_grounding(
            label="state change",
            provenance=self.provenance,
            basis_refs=self.basis_refs,
            limitations=self.limitations,
        )
        return self


class Interpretation(ContractModel):
    interpretation_id: NonEmptyStr
    claim: NonEmptyStr
    kind: InterpretationKind
    basis_refs: tuple[BasisRef, ...] = ()
    limitations: tuple[NonEmptyStr, ...] = ()

    @model_validator(mode="after")
    def validate_grounding(self) -> Interpretation:
        if self.kind == "derived" and not self.basis_refs:
            raise ValueError("derived interpretation requires at least one basis reference")
        if self.kind == "hypothesis" and not self.basis_refs and not self.limitations:
            raise ValueError("unsourced hypothesis requires a visible limitation")
        return self


class Counterevidence(ContractModel):
    counterevidence_id: NonEmptyStr
    claim: NonEmptyStr
    source_refs: SourceRefs
    challenges_refs: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1)]


class Unknown(ContractModel):
    unknown_id: NonEmptyStr
    question: NonEmptyStr
    affects: tuple[NonEmptyStr, ...] = ()


class ComprehensionRecord(ContractModel):
    record_id: NonEmptyStr
    subject_expression: NonEmptyStr
    sources: Annotated[tuple[SourceItem, ...], Field(min_length=1)]
    observations: tuple[Observation, ...] = ()
    entities: tuple[Entity, ...] = ()
    roles: tuple[RoleAssignment, ...] = ()
    relations: tuple[RelationEdge, ...] = ()
    state_changes: tuple[StateChange, ...] = ()
    interpretations: tuple[Interpretation, ...] = ()
    counterevidence: tuple[Counterevidence, ...] = ()
    unknowns: tuple[Unknown, ...] = ()

    @model_validator(mode="after")
    def validate_references(self) -> ComprehensionRecord:
        reference_index = self.reference_index()
        source_ids = {item.source_id for item in self.sources}
        entity_ids = {item.entity_id for item in self.entities}
        interpretation_ids = {item.interpretation_id for item in self.interpretations}

        for item in self.observations:
            _require_known_sources(item.source_refs, source_ids, item.observation_id)
        for item in self.entities:
            _require_known_sources(item.source_refs, source_ids, item.entity_id)
        for item in self.counterevidence:
            _require_known_sources(item.source_refs, source_ids, item.counterevidence_id)
            unknown_challenges = set(item.challenges_refs) - interpretation_ids
            if unknown_challenges:
                raise ValueError(f"counterevidence {item.counterevidence_id!r} challenges unknown interpretation(s): {sorted(unknown_challenges)}")

        for item in self.roles:
            if item.entity_id not in entity_ids:
                raise ValueError(f"role {item.role_id!r} references unknown entity {item.entity_id!r}")
            _require_known_basis_refs(item.basis_refs, reference_index, item.role_id)
        for item in self.relations:
            _require_known_entities(
                (item.subject_entity_id, item.object_entity_id),
                entity_ids,
                item.relation_id,
            )
            _require_known_basis_refs(item.basis_refs, reference_index, item.relation_id)
        for item in self.state_changes:
            _require_known_entities((item.subject_entity_id,), entity_ids, item.change_id)
            _require_known_basis_refs(item.basis_refs, reference_index, item.change_id)
        for item in self.interpretations:
            _require_known_basis_refs(item.basis_refs, reference_index, item.interpretation_id)

        return self

    def reference_index(self) -> dict[str, BasisKind | Literal["unknown"]]:
        entries: tuple[tuple[str, BasisKind | Literal["unknown"]], ...] = (
            *((item.source_id, "source") for item in self.sources),
            *((item.observation_id, "observation") for item in self.observations),
            *((item.entity_id, "entity") for item in self.entities),
            *((item.role_id, "role") for item in self.roles),
            *((item.relation_id, "relation") for item in self.relations),
            *((item.change_id, "state_change") for item in self.state_changes),
            *((item.interpretation_id, "interpretation") for item in self.interpretations),
            *((item.counterevidence_id, "counterevidence") for item in self.counterevidence),
            *((item.unknown_id, "unknown") for item in self.unknowns),
        )
        duplicate_ids = sorted(item_id for item_id, count in Counter(item_id for item_id, _ in entries).items() if count > 1)
        if duplicate_ids:
            raise ValueError(f"record ids must be globally unique: {duplicate_ids}")
        return dict(entries)

    def fingerprint(self) -> str:
        canonical = json.dumps(
            self.model_dump(mode="json", exclude_none=True),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class GroundedStatement(ContractModel):
    text: NonEmptyStr
    basis_refs: BasisRefs


class ModifierReading(ContractModel):
    modifier: NonEmptyStr
    modifies: NonEmptyStr
    semantic_role: NonEmptyStr
    removal_counterfactual: NonEmptyStr
    basis_refs: BasisRefs


class BusinessSemanticView(ContractModel):
    record_id: NonEmptyStr
    commercial_object: GroundedStatement | None = None
    lexical_head: GroundedStatement | None = None
    modifiers: tuple[ModifierReading, ...] = ()
    subject_actions: tuple[GroundedStatement, ...] = ()
    offering_role: OfferingRole | None = None
    role_rationale: NonEmptyStr | None = None
    served_objects: tuple[GroundedStatement, ...] = ()
    served_activities: tuple[GroundedStatement, ...] = ()
    defining_functions_or_uses: tuple[GroundedStatement, ...] = ()
    recurring_human_worlds: tuple[GroundedStatement, ...] = ()
    social_or_cultural_frames: tuple[GroundedStatement, ...] = ()
    summary: NonEmptyStr | None = None
    unknown_refs: tuple[NonEmptyStr, ...] = ()


class ContentPathStep(ContractModel):
    from_label: NonEmptyStr
    relation: NonEmptyStr
    to_label: NonEmptyStr
    basis_refs: tuple[BasisRef, ...] = ()
    status: Literal["grounded", "candidate"] = "grounded"
    verification_needed: bool = False

    @model_validator(mode="after")
    def validate_grounding(self) -> ContentPathStep:
        if self.status == "grounded" and not self.basis_refs:
            raise ValueError("grounded content path step requires at least one basis reference")
        if self.status == "candidate" and not self.basis_refs and not self.verification_needed:
            raise ValueError("ungrounded content path candidate must be marked for verification")
        return self


class ContentPath(ContractModel):
    path_id: NonEmptyStr
    steps: tuple[ContentPathStep, ...]
    rationale: NonEmptyStr

    @model_validator(mode="after")
    def require_a_step(self) -> ContentPath:
        if not self.steps:
            raise ValueError("content path requires at least one step")
        return self


class ContentDimension(ContractModel):
    name: NonEmptyStr
    rationale: NonEmptyStr
    paths: tuple[ContentPath, ...] = ()


class NamedCandidate(ContractModel):
    name: NonEmptyStr
    connection: NonEmptyStr
    kind: Literal["grounded", "hypothesis"]
    basis_refs: tuple[BasisRef, ...] = ()
    verification_query: NonEmptyStr | None = None
    limitations: tuple[NonEmptyStr, ...] = ()

    @model_validator(mode="after")
    def validate_grounding(self) -> NamedCandidate:
        if self.kind == "grounded" and not self.basis_refs:
            raise ValueError("grounded named candidate requires at least one basis reference")
        if self.kind == "hypothesis" and not self.basis_refs and not (self.verification_query or self.limitations):
            raise ValueError("unsourced named candidate hypothesis requires a verification query or limitation")
        return self


class ContentRootCandidate(ContractModel):
    candidate_id: NonEmptyStr
    label: NonEmptyStr
    scope_role: Literal["root_candidate", "example_branch"] = "root_candidate"
    relation_to_business: NonEmptyStr
    strength: NonEmptyStr
    overreach_risk: NonEmptyStr
    basis_refs: BasisRefs


class ContentWorldView(ContractModel):
    record_id: NonEmptyStr
    source_object: NonEmptyStr | None = None
    audience_territory: GroundedStatement | None = None
    content_root: NonEmptyStr | None = None
    root_rationale: NonEmptyStr | None = None
    root_candidates: tuple[ContentRootCandidate, ...] = ()
    dimensions: tuple[ContentDimension, ...] = ()
    named_candidates: tuple[NamedCandidate, ...] = ()
    unknown_refs: tuple[NonEmptyStr, ...] = ()


class NarrativeFrame(ContractModel):
    """Optional evidence-bound action chain for a topic that is genuinely narrative."""

    protagonist: NonEmptyStr
    goal: NonEmptyStr
    obstacle: NonEmptyStr
    action_or_choice: NonEmptyStr
    stakes_or_consequence: NonEmptyStr
    outcome_or_change: NonEmptyStr
    basis_refs: BasisRefs
    limitations: tuple[NonEmptyStr, ...] = ()


class TopicBrief(ContractModel):
    record_id: NonEmptyStr
    question: NonEmptyStr
    central_claim: NonEmptyStr
    mechanism: NonEmptyStr
    counterpoint: NonEmptyStr
    path: ContentPath
    evidence_refs: tuple[BasisRef, ...] = ()
    narrative_frame: NarrativeFrame | None = None
    limitations: tuple[NonEmptyStr, ...] = ()
    unknown_refs: tuple[NonEmptyStr, ...] = ()
    research_needed: tuple[NonEmptyStr, ...] = ()


class ContentIntelligenceBundle(ContractModel):
    record: ComprehensionRecord
    business_semantics: BusinessSemanticView | None = None
    content_world: ContentWorldView | None = None
    topic_brief: TopicBrief | None = None

    @model_validator(mode="after")
    def bind_projections_to_record(self) -> ContentIntelligenceBundle:
        projections = tuple(projection for projection in (self.business_semantics, self.content_world, self.topic_brief) if projection is not None)
        mismatched = [projection.record_id for projection in projections if projection.record_id != self.record.record_id]
        if mismatched:
            raise ValueError(f"projection record_id must match {self.record.record_id!r}: {mismatched}")

        reference_index = self.record.reference_index()
        for projection in projections:
            for basis_ref in _projection_basis_refs(projection):
                _require_known_basis_refs((basis_ref,), reference_index, projection.__class__.__name__)
            for unknown_ref in projection.unknown_refs:
                actual_kind = reference_index.get(unknown_ref)
                if actual_kind != "unknown":
                    raise ValueError(f"projection unknown_ref {unknown_ref!r} does not resolve to a record unknown")
        return self


def _validate_claim_grounding(
    *,
    label: str,
    provenance: ClaimProvenance,
    basis_refs: tuple[BasisRef, ...],
    limitations: tuple[str, ...],
) -> None:
    if provenance in {"observed", "derived"} and not basis_refs:
        raise ValueError(f"{provenance} {label} requires at least one basis reference")
    if provenance == "hypothesis" and not basis_refs and not limitations:
        raise ValueError(f"unsourced {label} hypothesis requires a visible limitation")


def _require_known_sources(refs: Iterable[str], known_sources: set[str], owner_id: str) -> None:
    unknown = set(refs) - known_sources
    if unknown:
        raise ValueError(f"{owner_id!r} references unknown source(s): {sorted(unknown)}")


def _require_known_entities(refs: Iterable[str], known_entities: set[str], owner_id: str) -> None:
    unknown = set(refs) - known_entities
    if unknown:
        raise ValueError(f"{owner_id!r} references unknown entity(s): {sorted(unknown)}")


def _require_known_basis_refs(
    refs: Iterable[BasisRef],
    reference_index: dict[str, BasisKind | Literal["unknown"]],
    owner_id: str,
) -> None:
    for ref in refs:
        actual_kind = reference_index.get(ref.ref_id)
        if actual_kind is None:
            raise ValueError(f"{owner_id!r} references unknown record item {ref.ref_id!r}")
        if actual_kind != ref.kind:
            raise ValueError(f"reference kind for {ref.ref_id!r} is {actual_kind!r}, not {ref.kind!r}")


def _path_basis_refs(path: ContentPath | None) -> Iterable[BasisRef]:
    if path is None:
        return ()
    return (basis_ref for step in path.steps for basis_ref in step.basis_refs)


def _projection_basis_refs(
    projection: BusinessSemanticView | ContentWorldView | TopicBrief,
) -> Iterable[BasisRef]:
    if isinstance(projection, BusinessSemanticView):
        statements = tuple(
            statement
            for statement in (
                projection.commercial_object,
                projection.lexical_head,
                *projection.subject_actions,
                *projection.served_objects,
                *projection.served_activities,
                *projection.defining_functions_or_uses,
                *projection.social_or_cultural_frames,
            )
            if statement is not None
        )
        return (
            *tuple(ref for statement in statements for ref in statement.basis_refs),
            *tuple(ref for modifier in projection.modifiers for ref in modifier.basis_refs),
        )
    if isinstance(projection, ContentWorldView):
        statements = tuple(statement for statement in (projection.audience_territory,) if statement is not None)
        return (
            *tuple(ref for statement in statements for ref in statement.basis_refs),
            *tuple(ref for candidate in projection.root_candidates for ref in candidate.basis_refs),
            *tuple(ref for dimension in projection.dimensions for path in dimension.paths for ref in _path_basis_refs(path)),
            *tuple(ref for candidate in projection.named_candidates for ref in candidate.basis_refs),
        )
    narrative_refs = projection.narrative_frame.basis_refs if projection.narrative_frame is not None else ()
    return (*tuple(_path_basis_refs(projection.path)), *projection.evidence_refs, *narrative_refs)
