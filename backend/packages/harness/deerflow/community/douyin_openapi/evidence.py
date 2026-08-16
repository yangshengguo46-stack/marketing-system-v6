from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from deerflow.incubation.contracts import (
    ArtifactEnvelope,
    ArtifactParentRef,
    IncubationContract,
    NonEmptyStr,
    PlatformAccountRef,
    ProjectRef,
)
from deerflow.incubation.evidence import (
    EvidenceCoverageReceipt,
    EvidenceItem,
    EvidenceSnapshot,
    seal_evidence_snapshot,
)


class _VideoSearchItem(IncubationContract):
    title: NonEmptyStr = Field(max_length=500)
    url: NonEmptyStr = Field(max_length=1000)
    content: NonEmptyStr = Field(max_length=4000)
    source_type: Literal["douyin_video"]
    item_id: NonEmptyStr = Field(max_length=80)
    nickname: NonEmptyStr | None = Field(default=None, max_length=200)
    create_time: int | None = Field(default=None, ge=0)
    digg_count: int | None = Field(default=None, ge=0)


class _VideoSearchData(IncubationContract):
    query: NonEmptyStr = Field(max_length=500)
    provider: Literal["douyin_open_platform"]
    evidence_role: Literal["topic_evidence"]
    total_results: int = Field(ge=0)
    cursor: int = Field(ge=0)
    has_more: bool
    search_id: NonEmptyStr | None = Field(default=None, max_length=200)
    results: tuple[_VideoSearchItem, ...]

    @model_validator(mode="after")
    def validate_result_count(self) -> _VideoSearchData:
        if self.total_results != len(self.results):
            raise ValueError("total_results must match normalized video results")
        return self


class _RouteMetadata(IncubationContract):
    domain: NonEmptyStr = Field(max_length=64)
    child_tool: NonEmptyStr = Field(max_length=64)
    manifest_version: NonEmptyStr = Field(max_length=128)
    catalog_version: NonEmptyStr = Field(max_length=128)


class _DomainResult(IncubationContract):
    data: _VideoSearchData
    warnings: tuple[NonEmptyStr, ...] = ()
    metadata: _RouteMetadata


def build_video_search_evidence_snapshot(
    domain_result: dict,
    *,
    requested_count: int,
    captured_at: datetime,
) -> EvidenceSnapshot:
    receipt = _DomainResult.model_validate(domain_result)
    if receipt.metadata.domain != "search" or receipt.metadata.child_tool != "video_search":
        raise ValueError("Douyin topic evidence requires the search.video_search route")

    items = tuple(
        EvidenceItem(
            source_ref=f"douyin:video:{item.item_id}",
            source_type=item.source_type,
            title=item.title,
            excerpt=item.content,
            provenance="observed",
            public_uri=item.url,
            actor_label=item.nickname,
            observed_values={
                key: value
                for key, value in {
                    "item_id": item.item_id,
                    "create_time": item.create_time,
                    "digg_count": item.digg_count,
                }.items()
                if value is not None
            },
        )
        for item in receipt.data.results
    )
    route_receipt = {
        "domain": receipt.metadata.domain,
        "child_tool": receipt.metadata.child_tool,
        "manifest_version": receipt.metadata.manifest_version,
        "catalog_version": receipt.metadata.catalog_version,
    }
    if receipt.data.search_id is not None:
        route_receipt["search_id"] = receipt.data.search_id

    return EvidenceSnapshot(
        provider=receipt.data.provider,
        collection_method="official_openapi",
        evidence_role=receipt.data.evidence_role,
        captured_at=captured_at,
        rights_basis="public search through the configured Douyin Open Platform application",
        query=receipt.data.query,
        items=items,
        coverage=EvidenceCoverageReceipt(
            population_scope="public_video_search_results",
            requested_count=requested_count,
            returned_count=len(items),
            has_more=receipt.data.has_more,
            cursor=receipt.data.cursor,
            limitations=("Search ranking and available fields are bounded by the official API response.",),
        ),
        route_receipt=route_receipt,
        warnings=receipt.warnings,
        limitations=(
            "This snapshot is topic evidence, not a benchmark-account analysis.",
            "A single result cannot establish an account's positioning, audience, performance, or reproducible pattern.",
            "Observed counts are point-in-time platform values, not causal explanations.",
        ),
    )


def seal_video_search_evidence(
    *,
    project: ProjectRef,
    domain_result: dict,
    requested_count: int,
    captured_at: datetime,
    source_thread_id: str,
    source_run_id: str,
    account: PlatformAccountRef | None = None,
    parents: tuple[ArtifactParentRef, ...] = (),
) -> ArtifactEnvelope:
    snapshot = build_video_search_evidence_snapshot(
        domain_result,
        requested_count=requested_count,
        captured_at=captured_at,
    )
    return seal_evidence_snapshot(
        project=project,
        snapshot=snapshot,
        account=account,
        parents=parents,
        source_thread_id=source_thread_id,
        source_run_id=source_run_id,
    )
