from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field, field_validator, model_validator

from deerflow.incubation.contracts import (
    ArtifactEnvelope,
    ArtifactParentRef,
    IncubationContract,
    NonEmptyStr,
    PlatformAccountRef,
    ProjectRef,
)

FactProvenance = Literal["user_stated", "authorized_observation"]
Confidence = Literal["low", "medium", "high"]
AccountStrategyStatus = Literal["proposed", "confirmed"]


def _canonical_ids(value: tuple[str, ...]) -> tuple[str, ...]:
    if len(set(value)) != len(value):
        raise ValueError("artifact references must be unique")
    return tuple(sorted(value))


class BriefFact(IncubationContract):
    statement: NonEmptyStr = Field(max_length=1000)
    provenance: FactProvenance
    source_quote: NonEmptyStr | None = Field(default=None, max_length=2000)
    basis_artifact_ids: tuple[NonEmptyStr, ...] = ()

    @field_validator("basis_artifact_ids")
    @classmethod
    def canonicalize_basis_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _canonical_ids(value)

    @model_validator(mode="after")
    def validate_provenance(self) -> BriefFact:
        if self.provenance == "user_stated":
            if self.source_quote is None:
                raise ValueError("a user-stated fact requires the user's own quoted words")
        elif not self.basis_artifact_ids:
            raise ValueError("an authorized observation requires a basis artifact")
        return self


class IncubationBrief(IncubationContract):
    """Project facts available before the Agent makes an incubation judgment."""

    subject_expression: NonEmptyStr = Field(max_length=8000)
    business_facts: tuple[BriefFact, ...] = ()
    capabilities: tuple[BriefFact, ...] = ()
    resources: tuple[BriefFact, ...] = ()
    constraints: tuple[BriefFact, ...] = ()
    goals: tuple[BriefFact, ...] = ()
    preferences: tuple[BriefFact, ...] = ()
    unknowns: tuple[NonEmptyStr, ...] = ()

    def all_facts(self) -> tuple[BriefFact, ...]:
        return (
            *self.business_facts,
            *self.capabilities,
            *self.resources,
            *self.constraints,
            *self.goals,
            *self.preferences,
        )


class JudgmentBasis(IncubationContract):
    rationale: NonEmptyStr = Field(max_length=3000)
    basis_artifact_ids: tuple[NonEmptyStr, ...] = ()
    confidence: Confidence = "low"
    unknowns: tuple[NonEmptyStr, ...] = ()

    @field_validator("basis_artifact_ids")
    @classmethod
    def canonicalize_basis_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _canonical_ids(value)


class PositioningDecision(JudgmentBasis):
    decision: NonEmptyStr = Field(max_length=2000)
    audience_promise: NonEmptyStr = Field(max_length=2000)
    boundaries: tuple[NonEmptyStr, ...] = ()


class AudienceHypothesis(JudgmentBasis):
    people: NonEmptyStr = Field(max_length=2000)
    recurring_interest: NonEmptyStr = Field(max_length=2000)
    why_return: NonEmptyStr = Field(max_length=2000)


class PersonaDecision(JudgmentBasis):
    account_role: NonEmptyStr = Field(max_length=2000)
    trust_basis: tuple[NonEmptyStr, ...] = ()
    boundaries: tuple[NonEmptyStr, ...] = ()


class AccountPresentationPlan(JudgmentBasis):
    """Sustainable account-level forms, not the format of one topic."""

    primary_forms: tuple[NonEmptyStr, ...] = Field(min_length=1, max_length=8)
    supporting_forms: tuple[NonEmptyStr, ...] = Field(default=(), max_length=8)
    constraints: tuple[NonEmptyStr, ...] = ()


class MonetizationHypothesis(JudgmentBasis):
    path: NonEmptyStr = Field(max_length=3000)
    trust_required: NonEmptyStr = Field(max_length=2000)
    preconditions: tuple[NonEmptyStr, ...] = ()


class AccountRouteOption(IncubationContract):
    """One coherent account route offered for explicit user selection."""

    option_id: NonEmptyStr = Field(max_length=80, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    name: NonEmptyStr = Field(max_length=200)
    positioning: PositioningDecision
    audience: AudienceHypothesis
    persona: PersonaDecision
    presentation: AccountPresentationPlan
    monetization: tuple[MonetizationHypothesis, ...] = ()
    business_connection: NonEmptyStr = Field(max_length=3000)
    recommendation_rationale: NonEmptyStr = Field(max_length=3000)
    resource_requirements: tuple[NonEmptyStr, ...] = ()
    tradeoffs: tuple[NonEmptyStr, ...] = ()

    def basis_artifact_ids(self) -> frozenset[str]:
        facets: tuple[JudgmentBasis, ...] = (
            self.positioning,
            self.audience,
            self.persona,
            self.presentation,
            *self.monetization,
        )
        return frozenset(artifact_id for facet in facets for artifact_id in facet.basis_artifact_ids)


class IncubationJudgment(IncubationContract):
    """A versionable proposal. Missing facets remain unknown rather than gates."""

    revision_number: int = Field(default=1, ge=1)
    supersedes_judgment_artifact_id: NonEmptyStr | None = None
    revision_reason: NonEmptyStr | None = Field(default=None, max_length=3000)
    content_map_version_id: NonEmptyStr = Field(max_length=80)
    decision_status: AccountStrategyStatus = "confirmed"
    route_options: tuple[AccountRouteOption, ...] = Field(default=(), max_length=5)
    recommended_option_id: NonEmptyStr | None = Field(default=None, max_length=80)
    selected_option_id: NonEmptyStr | None = Field(default=None, max_length=80)
    positioning: PositioningDecision | None = None
    audience: AudienceHypothesis | None = None
    persona: PersonaDecision | None = None
    presentation: AccountPresentationPlan | None = None
    monetization: tuple[MonetizationHypothesis, ...] = ()
    unknowns: tuple[NonEmptyStr, ...] = ()
    alternatives: tuple[NonEmptyStr, ...] = ()

    @model_validator(mode="after")
    def validate_revision_lineage(self) -> IncubationJudgment:
        if self.revision_number == 1:
            if self.supersedes_judgment_artifact_id is not None:
                raise ValueError("first judgment revision cannot supersede a previous judgment")
            return self
        if self.supersedes_judgment_artifact_id is None or self.revision_reason is None:
            raise ValueError("a revised judgment requires a previous judgment and revision reason")
        return self

    @model_validator(mode="after")
    def validate_route_choice(self) -> IncubationJudgment:
        option_ids = tuple(option.option_id for option in self.route_options)
        if len(set(option_ids)) != len(option_ids):
            raise ValueError("route_options must use unique option_id values")
        if self.decision_status == "proposed":
            if len(self.route_options) < 2:
                raise ValueError("a proposed judgment requires at least two route_options")
            if self.recommended_option_id not in option_ids:
                raise ValueError("a proposed judgment requires a valid recommended_option_id")
            if self.selected_option_id is not None:
                raise ValueError("a proposed judgment cannot select an option for the user")
            return self
        if self.route_options:
            if self.recommended_option_id not in option_ids:
                raise ValueError("a routed judgment requires a valid recommended_option_id")
            if self.selected_option_id not in option_ids:
                raise ValueError("a confirmed routed judgment requires a valid selected_option_id")
        elif self.recommended_option_id is not None or self.selected_option_id is not None:
            raise ValueError("route choice ids require route_options")
        return self

    def basis_artifact_ids(self) -> frozenset[str]:
        facets: list[JudgmentBasis] = []
        for facet in (
            self.positioning,
            self.audience,
            self.persona,
            self.presentation,
        ):
            if facet is not None:
                facets.append(facet)
        facets.extend(self.monetization)
        direct_ids = frozenset(artifact_id for facet in facets for artifact_id in facet.basis_artifact_ids)
        route_ids = frozenset(artifact_id for route in self.route_options for artifact_id in route.basis_artifact_ids())
        return direct_ids | route_ids


def _require_project(
    artifact: ArtifactEnvelope,
    *,
    project: ProjectRef,
    artifact_type: str,
) -> None:
    if artifact.project != project:
        raise ValueError(f"{artifact_type} parent project must match judgment project")
    if artifact.artifact_type != artifact_type:
        raise ValueError(f"expected {artifact_type} parent")


def seal_incubation_brief(
    *,
    project: ProjectRef,
    brief: IncubationBrief,
    created_at: datetime,
    source_thread_id: str,
    source_run_id: str,
    parents: tuple[ArtifactParentRef, ...] = (),
) -> ArtifactEnvelope:
    parent_ids = {parent.artifact_id for parent in parents}
    fact_basis_ids = {artifact_id for fact in brief.all_facts() for artifact_id in fact.basis_artifact_ids}
    missing = fact_basis_ids - parent_ids
    if missing:
        raise ValueError("brief fact basis artifact must be included as a parent")
    return ArtifactEnvelope.seal(
        project=project,
        artifact_type="incubation_brief",
        version=1,
        payload=brief.model_dump(mode="json"),
        parents=parents,
        created_at=created_at,
        source_thread_id=source_thread_id,
        source_run_id=source_run_id,
    )


def seal_incubation_judgment(
    *,
    project: ProjectRef,
    judgment: IncubationJudgment,
    brief_artifact: ArtifactEnvelope,
    content_world_artifact: ArtifactEnvelope,
    created_at: datetime,
    source_thread_id: str,
    source_run_id: str,
    account: PlatformAccountRef | None = None,
    evidence_artifacts: tuple[ArtifactEnvelope, ...] = (),
    previous_judgment_artifact: ArtifactEnvelope | None = None,
) -> ArtifactEnvelope:
    judgment = IncubationJudgment.model_validate(judgment.model_dump(mode="json"))
    _require_project(
        brief_artifact,
        project=project,
        artifact_type="incubation_brief",
    )
    _require_project(
        content_world_artifact,
        project=project,
        artifact_type="content_map_candidate",
    )
    for artifact in evidence_artifacts:
        if artifact.project != project:
            raise ValueError("evidence parent project must match judgment project")

    if judgment.revision_number == 1:
        if previous_judgment_artifact is not None:
            raise ValueError("first judgment revision cannot bind a previous judgment")
    else:
        if previous_judgment_artifact is None:
            raise ValueError("revised judgment requires its previous judgment parent")
        _require_project(
            previous_judgment_artifact,
            project=project,
            artifact_type="incubation_judgment",
        )
        if previous_judgment_artifact.account != account:
            raise ValueError("previous judgment account must match revised judgment account")
        if judgment.supersedes_judgment_artifact_id != previous_judgment_artifact.artifact_id:
            raise ValueError("previous judgment id must match supersedes_judgment_artifact_id")
        previous_judgment = IncubationJudgment.model_validate(previous_judgment_artifact.payload)
        if judgment.revision_number != previous_judgment.revision_number + 1:
            raise ValueError("judgment revision number must immediately follow the previous judgment")

    world_version = content_world_artifact.payload.get("content_map_version_id")
    if world_version != judgment.content_map_version_id:
        raise ValueError("incubation judgment content map version must match its candidate map")

    parent_artifacts = (
        brief_artifact,
        content_world_artifact,
        *evidence_artifacts,
        *((previous_judgment_artifact,) if previous_judgment_artifact is not None else ()),
    )
    parent_ids = {artifact.artifact_id for artifact in parent_artifacts}
    if not judgment.basis_artifact_ids().issubset(parent_ids):
        raise ValueError("every judgment basis artifact must be included as a parent")

    return ArtifactEnvelope.seal(
        project=project,
        artifact_type="incubation_judgment",
        version=judgment.revision_number,
        payload=judgment.model_dump(mode="json"),
        account=account,
        parents=tuple(artifact.to_parent_ref() for artifact in parent_artifacts),
        created_at=created_at,
        source_thread_id=source_thread_id,
        source_run_id=source_run_id,
    )


__all__ = [
    "AccountPresentationPlan",
    "AccountRouteOption",
    "AccountStrategyStatus",
    "AudienceHypothesis",
    "BriefFact",
    "Confidence",
    "FactProvenance",
    "IncubationBrief",
    "IncubationJudgment",
    "MonetizationHypothesis",
    "PersonaDecision",
    "PositioningDecision",
    "seal_incubation_brief",
    "seal_incubation_judgment",
]
