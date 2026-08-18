from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import Field, model_validator

from deerflow.content_intelligence.contracts import ContractModel, NonEmptyStr

ShortText = Annotated[str, Field(min_length=1, max_length=180)]
MediumText = Annotated[str, Field(min_length=1, max_length=360)]
SearchQuery = Annotated[str, Field(min_length=2, max_length=160)]
EvidenceRef = Annotated[str, Field(min_length=1, max_length=80)]


class QueryKind(StrEnum):
    DIRECT = "direct"
    DEMAND = "demand"
    MECHANISM = "mechanism"


class ArmId(StrEnum):
    DIRECT_ONLY = "A"
    BROAD_WITHOUT_WORLD = "B"
    BROAD_WITH_THIN_WORLD = "C"


class SearchStatus(StrEnum):
    SUCCEEDED = "succeeded"
    EMPTY = "empty"
    FAILED = "failed"


class BenchmarkSearchPlanDraft(ContractModel):
    demand_query: SearchQuery
    mechanism_query: SearchQuery
    unknowns: tuple[ShortText, ...] = Field(default=(), max_length=4)


class BenchmarkSearchPlan(BenchmarkSearchPlanDraft):
    schema_version: Literal["benchmark-search-plan-v1"] = "benchmark-search-plan-v1"
    case_id: NonEmptyStr
    direct_query: SearchQuery

    @model_validator(mode="after")
    def validate_distinct_queries(self) -> BenchmarkSearchPlan:
        queries = (self.direct_query, self.demand_query, self.mechanism_query)
        if len(set(query.casefold() for query in queries)) != 3:
            raise ValueError("benchmark search queries must be distinct")
        return self


class SearchCoverage(ContractModel):
    query_kind: QueryKind
    query: SearchQuery
    status: SearchStatus
    raw_result_count: int = Field(ge=0, le=100)
    accepted_result_count: int = Field(ge=0, le=5)
    error: Annotated[str, Field(max_length=240)] | None = None

    @model_validator(mode="after")
    def validate_status(self) -> SearchCoverage:
        if self.status is SearchStatus.FAILED and not self.error:
            raise ValueError("failed search coverage requires an error")
        if self.status is SearchStatus.SUCCEEDED and self.raw_result_count == 0:
            raise ValueError("successful search coverage requires at least one raw result")
        return self


class EvidenceMembership(ContractModel):
    query_kind: QueryKind
    query: SearchQuery
    rank: int = Field(ge=1, le=5)


class BenchmarkEvidenceItem(ContractModel):
    evidence_id: EvidenceRef
    query_kind: QueryKind
    query: SearchQuery
    memberships: tuple[EvidenceMembership, ...] = Field(min_length=1, max_length=3)
    title: Annotated[str, Field(min_length=1, max_length=300)]
    url: Annotated[str, Field(min_length=1, max_length=1_000)]
    snippet: Annotated[str, Field(max_length=600)] = ""
    content_hash: NonEmptyStr

    @model_validator(mode="after")
    def validate_identity(self) -> BenchmarkEvidenceItem:
        parsed = urlsplit(self.url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("evidence URL must be a public HTTP(S) URL")
        if parsed.username or parsed.password:
            raise ValueError("evidence URL cannot contain credentials")
        membership_keys = tuple((item.query_kind, item.query) for item in self.memberships)
        if len(membership_keys) != len(set(membership_keys)):
            raise ValueError("evidence memberships must be unique")
        if (self.query_kind, self.query) not in membership_keys:
            raise ValueError("primary evidence query must be present in memberships")
        expected_content_hash = evidence_content_hash(self.title, self.snippet)
        if self.content_hash != expected_content_hash:
            raise ValueError("evidence content hash does not match title and snippet")
        return self


class BenchmarkEvidencePack(ContractModel):
    schema_version: Literal["benchmark-evidence-pack-v1"] = "benchmark-evidence-pack-v1"
    case_id: NonEmptyStr
    collection_method: Literal["public_web_benchmark_discovery"] = "public_web_benchmark_discovery"
    provider: NonEmptyStr = "deerflow_ddg_search"
    search_plan: BenchmarkSearchPlan
    coverage: tuple[SearchCoverage, ...] = Field(min_length=3, max_length=3)
    items: tuple[BenchmarkEvidenceItem, ...] = Field(default=(), max_length=15)
    evidence_hash: NonEmptyStr

    @model_validator(mode="after")
    def validate_pack(self) -> BenchmarkEvidencePack:
        if self.search_plan.case_id != self.case_id:
            raise ValueError("search plan and evidence pack case ids must match")
        coverage_kinds = tuple(item.query_kind for item in self.coverage)
        if coverage_kinds != (QueryKind.DIRECT, QueryKind.DEMAND, QueryKind.MECHANISM):
            raise ValueError("search coverage must follow direct, demand, mechanism order")
        evidence_ids = tuple(item.evidence_id for item in self.items)
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("evidence ids must be unique")
        urls = tuple(item.url for item in self.items)
        if len(urls) != len(set(urls)):
            raise ValueError("evidence URLs must be deduplicated")
        expected_queries = {
            QueryKind.DIRECT: self.search_plan.direct_query,
            QueryKind.DEMAND: self.search_plan.demand_query,
            QueryKind.MECHANISM: self.search_plan.mechanism_query,
        }
        for item in self.items:
            for membership in item.memberships:
                if membership.query != expected_queries[membership.query_kind]:
                    raise ValueError("evidence membership query does not match the frozen search plan")
            expected_id = evidence_item_id(
                provider=self.provider,
                url=item.url,
                content_hash=item.content_hash,
            )
            if item.evidence_id != expected_id:
                raise ValueError("evidence id does not match provider, URL, and content")
        expected_hash = evidence_pack_hash(
            case_id=self.case_id,
            provider=self.provider,
            collection_method=self.collection_method,
            search_plan=self.search_plan,
            coverage=self.coverage,
            items=self.items,
        )
        if self.evidence_hash != expected_hash:
            raise ValueError("evidence hash does not match the sealed evidence pack")
        return self


class EvidenceProjection(ContractModel):
    schema_version: Literal["benchmark-evidence-projection-v1"] = "benchmark-evidence-projection-v1"
    case_id: NonEmptyStr
    evidence_hash: NonEmptyStr
    query_kinds: tuple[QueryKind, ...] = Field(min_length=1, max_length=3)
    included_evidence_ids: tuple[EvidenceRef, ...] = ()
    omitted_item_count: int = Field(ge=0)
    rendered: NonEmptyStr


class CommonRouteDraft(ContractModel):
    positioning: MediumText
    audience_situation: MediumText
    distinctive_viewpoint: MediumText
    repeatable_series: tuple[ShortText, ...] = Field(min_length=2, max_length=5)
    shootable_topics: tuple[ShortText, ...] = Field(min_length=3, max_length=6)
    presentation_options: tuple[ShortText, ...] = Field(min_length=1, max_length=4)
    business_connection: MediumText
    transferable_mechanisms: tuple[ShortText, ...] = Field(min_length=1, max_length=5)
    evidence_refs: tuple[EvidenceRef, ...] = Field(default=(), max_length=8)
    non_copy_boundaries: tuple[ShortText, ...] = Field(min_length=1, max_length=5)
    unknowns: tuple[ShortText, ...] = Field(default=(), max_length=6)

    @model_validator(mode="after")
    def validate_unique_lists(self) -> CommonRouteDraft:
        for label, values in (
            ("repeatable series", self.repeatable_series),
            ("shootable topics", self.shootable_topics),
            ("evidence refs", self.evidence_refs),
        ):
            if len(values) != len(set(value.casefold() for value in values)):
                raise ValueError(f"{label} must be unique")
        return self


class NeutralEvidenceDigestDraft(ContractModel):
    observed_patterns: tuple[ShortText, ...] = Field(min_length=2, max_length=5)
    transferable_mechanisms: tuple[ShortText, ...] = Field(min_length=1, max_length=4)
    evidence_refs: tuple[EvidenceRef, ...] = Field(default=(), max_length=8)
    limitations: tuple[ShortText, ...] = Field(min_length=1, max_length=5)
    unknowns: tuple[ShortText, ...] = Field(default=(), max_length=5)


class ThinWorldDigestDraft(NeutralEvidenceDigestDraft):
    long_term_subject: MediumText
    content_branches: tuple[ShortText, ...] = Field(min_length=2, max_length=5)
    business_return_path: MediumText


class BenchmarkIntermediateRecord(ContractModel):
    schema_version: Literal["benchmark-intermediate-v1"] = "benchmark-intermediate-v1"
    case_id: NonEmptyStr
    arm: Literal[ArmId.BROAD_WITHOUT_WORLD, ArmId.BROAD_WITH_THIN_WORLD]
    evidence_hash: NonEmptyStr
    digest: NeutralEvidenceDigestDraft | ThinWorldDigestDraft

    @model_validator(mode="after")
    def validate_arm_schema(self) -> BenchmarkIntermediateRecord:
        if self.arm is ArmId.BROAD_WITH_THIN_WORLD and not isinstance(self.digest, ThinWorldDigestDraft):
            raise ValueError("arm C requires a thin-world digest")
        if self.arm is ArmId.BROAD_WITHOUT_WORLD and isinstance(self.digest, ThinWorldDigestDraft):
            raise ValueError("arm B cannot contain thin-world fields")
        return self


class BenchmarkRouteRecord(ContractModel):
    schema_version: Literal["benchmark-route-v1"] = "benchmark-route-v1"
    case_id: NonEmptyStr
    arm: ArmId
    evidence_hash: NonEmptyStr
    route: CommonRouteDraft


class BlindCandidateScore(ContractModel):
    candidate_key: NonEmptyStr
    business_relevance: int = Field(ge=0, le=2)
    long_term_coherence: int = Field(ge=0, le=2)
    differentiation_and_transfer: int = Field(ge=0, le=2)
    shootability: int = Field(ge=0, le=2)
    evidence_honesty: int = Field(ge=0, le=2)
    conditional_boundary: int = Field(ge=0, le=2)
    fatal_issues: tuple[ShortText, ...] = Field(default=(), max_length=4)
    rationale: MediumText

    @property
    def total(self) -> int:
        return self.business_relevance + self.long_term_coherence + self.differentiation_and_transfer + self.shootability + self.evidence_honesty + self.conditional_boundary


class BlindCaseReviewDraft(ContractModel):
    scores: tuple[BlindCandidateScore, ...] = Field(min_length=3, max_length=3)
    ranking: tuple[NonEmptyStr, ...] = Field(min_length=3, max_length=3)
    review_unknowns: tuple[ShortText, ...] = Field(default=(), max_length=4)

    @model_validator(mode="after")
    def validate_candidates(self) -> BlindCaseReviewDraft:
        score_keys = tuple(score.candidate_key for score in self.scores)
        if len(set(score_keys)) != 3:
            raise ValueError("blind review candidate keys must be unique")
        if set(self.ranking) != set(score_keys):
            raise ValueError("blind review ranking must contain each candidate exactly once")
        return self


def bind_route_record(
    *,
    case_id: str,
    arm: ArmId | Literal["A", "B", "C"],
    evidence_pack: BenchmarkEvidencePack,
    draft: CommonRouteDraft,
    allowed_evidence_ids: set[str] | None = None,
) -> BenchmarkRouteRecord:
    arm_id = ArmId(arm)
    allowed_kinds = {QueryKind.DIRECT} if arm_id is ArmId.DIRECT_ONLY else set(QueryKind)
    if case_id != evidence_pack.case_id:
        raise ValueError("route case id must match the evidence pack case id")
    allowed_ids = {item.evidence_id for item in evidence_pack.items if any(membership.query_kind in allowed_kinds for membership in item.memberships)}
    if allowed_evidence_ids is not None:
        allowed_ids &= allowed_evidence_ids
    unknown_refs = tuple(ref for ref in draft.evidence_refs if ref not in allowed_ids)
    if unknown_refs:
        raise ValueError(f"evidence refs outside the frozen evidence pack: {unknown_refs}")
    return BenchmarkRouteRecord(
        case_id=case_id,
        arm=arm_id,
        evidence_hash=evidence_pack.evidence_hash,
        route=draft,
    )


def bind_intermediate_record(
    *,
    case_id: str,
    arm: Literal["B", "C"],
    evidence_pack: BenchmarkEvidencePack,
    draft: NeutralEvidenceDigestDraft | ThinWorldDigestDraft,
) -> BenchmarkIntermediateRecord:
    arm_id = ArmId(arm)
    if arm_id is ArmId.DIRECT_ONLY:
        raise ValueError("arm A has no intermediate digest")
    if case_id != evidence_pack.case_id:
        raise ValueError("intermediate case id must match the evidence pack case id")
    allowed_ids = {item.evidence_id for item in evidence_pack.items}
    unknown_refs = tuple(ref for ref in draft.evidence_refs if ref not in allowed_ids)
    if unknown_refs:
        raise ValueError(f"evidence refs outside the frozen evidence pack: {unknown_refs}")
    return BenchmarkIntermediateRecord(
        case_id=case_id,
        arm=arm_id,
        evidence_hash=evidence_pack.evidence_hash,
        digest=draft,
    )


def evidence_pack_hash(
    *,
    case_id: str,
    provider: str,
    collection_method: str,
    search_plan: BenchmarkSearchPlan,
    coverage: tuple[SearchCoverage, ...],
    items: tuple[BenchmarkEvidenceItem, ...],
) -> str:
    payload = {
        "case_id": case_id,
        "provider": provider,
        "collection_method": collection_method,
        "search_plan": search_plan.model_dump(mode="json"),
        "coverage": [entry.model_dump(mode="json") for entry in coverage],
        "items": [item.model_dump(mode="json") for item in items],
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return "benchmark-pack-" + hashlib.sha256(encoded).hexdigest()


def evidence_content_hash(title: str, snippet: str) -> str:
    return hashlib.sha256(f"{title}\0{snippet}".encode()).hexdigest()


def evidence_item_id(*, provider: str, url: str, content_hash: str) -> str:
    payload = f"{provider}\0{url}\0{content_hash}".encode()
    return "benchmark-evidence-" + hashlib.sha256(payload).hexdigest()[:20]


__all__ = [
    "ArmId",
    "BenchmarkEvidenceItem",
    "BenchmarkEvidencePack",
    "BenchmarkIntermediateRecord",
    "BenchmarkRouteRecord",
    "BenchmarkSearchPlan",
    "BenchmarkSearchPlanDraft",
    "BlindCandidateScore",
    "BlindCaseReviewDraft",
    "CommonRouteDraft",
    "EvidenceProjection",
    "EvidenceMembership",
    "NeutralEvidenceDigestDraft",
    "QueryKind",
    "SearchCoverage",
    "SearchStatus",
    "ThinWorldDigestDraft",
    "bind_intermediate_record",
    "bind_route_record",
    "evidence_content_hash",
    "evidence_item_id",
    "evidence_pack_hash",
]
