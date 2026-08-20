from __future__ import annotations

import hashlib
import json
import unicodedata
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

from pydantic import Field

from deerflow.incubation.contracts import (
    ArtifactEnvelope,
    ArtifactParentRef,
    IncubationContract,
    NonEmptyStr,
    ProjectRef,
)
from deerflow.incubation.evidence import (
    EvidenceCoverageReceipt,
    EvidenceItem,
    EvidenceSnapshot,
    seal_evidence_snapshot,
)

from .contracts import CapabilityContext
from .evidence import build_video_search_evidence_snapshot
from .router import DomainRouter

_VIDEO_SEARCH_SCOPE = "aweme.dy.video_search"
_VIDEO_SEARCH_V2_SCOPE = "aweme.dy.video_search_v2"
_MAX_PAGE_SIZE = 20


class BenchmarkCandidateCollectionError(RuntimeError):
    """A bounded official-search collection failure without provider secrets."""


class BenchmarkCandidateRequest(IncubationContract):
    query: NonEmptyStr = Field(max_length=200)
    actor_label: NonEmptyStr = Field(max_length=200)
    max_posts: int = Field(default=24, ge=1, le=24)
    max_pages: int = Field(default=5, ge=1, le=5)
    publish_time: Literal[0, 1, 7, 180] = 0
    sort_type: Literal[0, 1, 2] = 0
    viewer_open_id: NonEmptyStr | None = Field(default=None, max_length=255)


class BenchmarkDiscoveryRequest(IncubationContract):
    query: NonEmptyStr = Field(max_length=200)
    max_accounts: int = Field(default=8, ge=1, le=8)
    max_posts_per_account: int = Field(default=6, ge=1, le=6)
    max_pages: int = Field(default=5, ge=1, le=5)
    publish_time: Literal[0, 1, 7, 180] = 0
    sort_type: Literal[0, 1, 2] = 0
    viewer_open_id: NonEmptyStr | None = Field(default=None, max_length=255)


@dataclass
class _DiscoveredActorGroup:
    display_name: str
    first_seen_index: int
    items: list[EvidenceItem] = field(default_factory=list)


def _actor_key(value: str | None) -> str:
    if value is None:
        return ""
    normalized = unicodedata.normalize("NFKC", value)
    return "".join(normalized.split()).casefold()


def _canonical_sha256(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _is_error_receipt(value: object) -> bool:
    if not isinstance(value, dict):
        return True
    if "error" in value:
        return True
    data = value.get("data")
    return isinstance(data, dict) and "error" in data


def _video_search_scope(context: CapabilityContext) -> str:
    if _VIDEO_SEARCH_SCOPE in context.granted_scopes:
        return _VIDEO_SEARCH_SCOPE
    if _VIDEO_SEARCH_V2_SCOPE in context.granted_scopes:
        return _VIDEO_SEARCH_V2_SCOPE
    return _VIDEO_SEARCH_SCOPE


def _require_video_search_route(
    router: DomainRouter,
    context: CapabilityContext,
) -> tuple[dict, str]:
    manifest = router.discover("search", context)
    children = manifest.get("children") if isinstance(manifest, dict) else None
    visible_children = children if isinstance(children, list) else []
    video_child = next(
        (child for child in visible_children if isinstance(child, dict) and child.get("name") == "video_search"),
        None,
    )
    if not isinstance(video_child, dict) or not video_child.get("callable"):
        raise BenchmarkCandidateCollectionError("Official Douyin video search is not callable for the current capability context")
    manifest_version = manifest.get("manifest_version")
    if not isinstance(manifest_version, str) or not manifest_version:
        raise BenchmarkCandidateCollectionError("Official Douyin search manifest is incomplete")
    return manifest, manifest_version


async def discover_benchmark_account_candidates(
    request: BenchmarkDiscoveryRequest,
    *,
    router: DomainRouter,
    context: CapabilityContext,
    captured_at: datetime | None = None,
) -> EvidenceSnapshot:
    """Discover bounded display-name candidates through official video search.

    Grouping only joins Unicode-normalized display names. It does not establish a
    stable account identity or promote the result to a formal benchmark snapshot.
    """

    if captured_at is not None and (captured_at.tzinfo is None or captured_at.utcoffset() is None):
        raise ValueError("captured_at must be timezone-aware")
    capture_time = (captured_at or datetime.now(UTC)).astimezone(UTC)
    manifest, manifest_version = _require_video_search_route(router, context)

    groups: dict[str, _DiscoveredActorGroup] = {}
    seen_source_refs: set[str] = set()
    seen_pagination: set[tuple[int, str | None]] = {(0, None)}
    warnings: list[str] = []
    page_receipt_hashes: list[str] = []
    pages_requested = 0
    pages_succeeded = 0
    actorless_count = 0
    duplicate_count = 0
    cursor = 0
    search_id: str | None = None
    has_more = False
    stopped_reason = "max_pages_reached"
    first_seen_index = 0

    for _page_number in range(1, request.max_pages + 1):
        arguments: dict[str, object] = {
            "query": request.query,
            "purpose": "benchmark_discovery",
            "max_results": _MAX_PAGE_SIZE,
            "cursor": cursor,
            "publish_time": request.publish_time,
            "sort_type": request.sort_type,
        }
        if search_id is not None:
            arguments["search_id"] = search_id
        if request.viewer_open_id is not None:
            arguments["open_id"] = request.viewer_open_id

        pages_requested += 1
        domain_result = await router.dispatch(
            domain_id="search",
            child_tool="video_search",
            arguments=arguments,
            manifest_version=manifest_version,
            context=context,
        )
        if _is_error_receipt(domain_result):
            if not pages_succeeded:
                raise BenchmarkCandidateCollectionError("Official Douyin candidate collection failed before any page was accepted")
            warnings.append("Collection stopped after a provider failure; earlier public observations were retained.")
            stopped_reason = "provider_error_after_partial_result"
            has_more = True
            break

        try:
            page_snapshot = build_video_search_evidence_snapshot(
                domain_result,
                requested_count=_MAX_PAGE_SIZE,
                captured_at=capture_time,
            )
        except Exception as exc:
            if not pages_succeeded:
                raise BenchmarkCandidateCollectionError("Official Douyin candidate collection failed before any page was accepted") from exc
            warnings.append("Collection stopped after an invalid provider page; earlier public observations were retained.")
            stopped_reason = "invalid_page_after_partial_result"
            has_more = True
            break
        if page_snapshot.evidence_role != "benchmark_account_candidate":
            if not pages_succeeded:
                raise BenchmarkCandidateCollectionError("Official Douyin candidate collection failed before any page was accepted")
            warnings.append("Collection stopped after an evidence-role mismatch; earlier public observations were retained.")
            stopped_reason = "role_mismatch_after_partial_result"
            has_more = True
            break

        pages_succeeded += 1
        page_receipt_hashes.append(_canonical_sha256(page_snapshot.route_receipt))
        has_more = bool(page_snapshot.coverage.has_more)
        next_cursor = page_snapshot.coverage.cursor
        if not isinstance(next_cursor, int):
            next_cursor = cursor
        next_search_id = page_snapshot.route_receipt.get("search_id")
        if not isinstance(next_search_id, str) or not next_search_id:
            next_search_id = search_id

        for item in page_snapshot.items:
            actor_key = _actor_key(item.actor_label)
            if not actor_key:
                actorless_count += 1
                continue
            if item.source_ref in seen_source_refs:
                duplicate_count += 1
                continue
            seen_source_refs.add(item.source_ref)
            group = groups.get(actor_key)
            if group is None:
                group = _DiscoveredActorGroup(
                    display_name=item.actor_label or "",
                    first_seen_index=first_seen_index,
                )
                groups[actor_key] = group
                first_seen_index += 1
            group.items.append(item)

        cursor = next_cursor
        search_id = next_search_id
        if not has_more:
            stopped_reason = "provider_exhausted"
            break
        pagination_key = (cursor, search_id)
        if pagination_key in seen_pagination:
            warnings.append("Collection stopped because the provider pagination receipt did not advance.")
            stopped_reason = "pagination_did_not_advance"
            has_more = True
            break
        if search_id is None:
            warnings.append("Collection stopped because the provider did not return the search_id required for another page.")
            stopped_reason = "pagination_receipt_incomplete"
            has_more = True
            break
        seen_pagination.add(pagination_key)

    ranked_groups = sorted(
        groups.values(),
        key=lambda group: (-len(group.items), group.first_seen_index),
    )
    selected_groups = ranked_groups[: request.max_accounts]
    omitted_groups = ranked_groups[request.max_accounts :]
    selected: list[EvidenceItem] = []
    account_candidates: list[dict[str, object]] = []
    sample_cap_omitted_count = 0
    for group in selected_groups:
        representative_items = group.items[: request.max_posts_per_account]
        sample_cap_omitted_count += len(group.items) - len(representative_items)
        selected.extend(item.model_copy(update={"actor_label": group.display_name}) for item in representative_items)
        account_candidates.append(
            {
                "display_name": group.display_name,
                "sample_count": len(representative_items),
                "observed_distinct_post_count": len(group.items),
            }
        )

    omitted_group_item_count = sum(len(group.items) for group in omitted_groups)
    locally_omitted = bool(omitted_groups or sample_cap_omitted_count)
    route_receipt = {
        "adapter": "douyin_openapi.search.video_search",
        "capability_version": _video_search_scope(context),
        "manifest_version": manifest_version,
        "catalog_version": manifest.get("metadata", {}).get("catalog_version"),
        "pages_requested": pages_requested,
        "pages_succeeded": pages_succeeded,
        "page_receipt_sha256": page_receipt_hashes,
        "actor_grouping": "unicode_normalized_display_name",
        "candidate_order": "distinct_post_count_desc_then_first_seen",
        "viewer_context_supplied": request.viewer_open_id is not None,
        "target_identity_status": "multiple_display_name_candidates",
        "account_candidates": account_candidates,
        "omitted_candidate_count": len(omitted_groups),
        "sample_cap_omitted_count": sample_cap_omitted_count,
        "stopped_reason": stopped_reason,
    }
    route_receipt = {key: value for key, value in route_receipt.items() if value is not None}

    return EvidenceSnapshot(
        provider="douyin_open_platform",
        collection_method="official_openapi_multi_page_search",
        evidence_role="benchmark_account_candidate",
        captured_at=capture_time,
        rights_basis="public search through the configured Douyin Open Platform application",
        query=request.query,
        items=tuple(selected),
        coverage=EvidenceCoverageReceipt(
            population_scope="public_video_search_results_grouped_by_actor_display_name",
            requested_count=request.max_accounts * request.max_posts_per_account,
            returned_count=len(selected),
            excluded_count=actorless_count + omitted_group_item_count,
            duplicate_count=duplicate_count,
            has_more=has_more or locally_omitted,
            cursor=cursor,
            limitations=("Coverage describes bounded search samples grouped by display name, not stable accounts.",),
        ),
        route_receipt=route_receipt,
        warnings=tuple(warnings),
        limitations=(
            "Unicode-normalized display-name grouping does not establish a stable target-account identity.",
            "Official keyword search is ranked and bounded; it is not a complete account post list.",
            "This is benchmark-account candidate evidence, not a BenchmarkSnapshot.",
            "Observed counts are point-in-time values and are not success causes or transferability claims.",
        ),
    )


async def collect_benchmark_account_candidate(
    request: BenchmarkCandidateRequest,
    *,
    router: DomainRouter,
    context: CapabilityContext,
    captured_at: datetime | None = None,
) -> EvidenceSnapshot:
    """Collect one bounded display-name candidate through official video search.

    The result remains candidate evidence because public search does not return a
    stable target-account identity or a complete author-consistent post list.
    """

    if captured_at is not None and (captured_at.tzinfo is None or captured_at.utcoffset() is None):
        raise ValueError("captured_at must be timezone-aware")
    capture_time = (captured_at or datetime.now(UTC)).astimezone(UTC)
    manifest, manifest_version = _require_video_search_route(router, context)

    target_key = _actor_key(request.actor_label)
    selected: list[EvidenceItem] = []
    seen_source_refs: set[str] = set()
    seen_pagination: set[tuple[int, str | None]] = {(0, None)}
    warnings: list[str] = []
    page_receipt_hashes: list[str] = []
    pages_requested = 0
    pages_succeeded = 0
    excluded_count = 0
    duplicate_count = 0
    sample_cap_omitted_count = 0
    cursor = 0
    search_id: str | None = None
    has_more = False
    stopped_reason = "max_pages_reached"

    for _page_number in range(1, request.max_pages + 1):
        arguments: dict[str, object] = {
            "query": request.query,
            "purpose": "benchmark_discovery",
            "max_results": _MAX_PAGE_SIZE,
            "cursor": cursor,
            "publish_time": request.publish_time,
            "sort_type": request.sort_type,
        }
        if search_id is not None:
            arguments["search_id"] = search_id
        if request.viewer_open_id is not None:
            # The provider documents this as an authorized viewer identifier. It
            # is not the identity of the target creator and is never persisted.
            arguments["open_id"] = request.viewer_open_id

        pages_requested += 1
        domain_result = await router.dispatch(
            domain_id="search",
            child_tool="video_search",
            arguments=arguments,
            manifest_version=manifest_version,
            context=context,
        )
        if _is_error_receipt(domain_result):
            if not pages_succeeded:
                raise BenchmarkCandidateCollectionError("Official Douyin candidate collection failed before any page was accepted")
            warnings.append("Collection stopped after a provider failure; earlier public observations were retained.")
            stopped_reason = "provider_error_after_partial_result"
            has_more = True
            break

        try:
            page_snapshot = build_video_search_evidence_snapshot(
                domain_result,
                requested_count=_MAX_PAGE_SIZE,
                captured_at=capture_time,
            )
        except Exception as exc:
            if not pages_succeeded:
                raise BenchmarkCandidateCollectionError("Official Douyin candidate collection failed before any page was accepted") from exc
            warnings.append("Collection stopped after an invalid provider page; earlier public observations were retained.")
            stopped_reason = "invalid_page_after_partial_result"
            has_more = True
            break
        if page_snapshot.evidence_role != "benchmark_account_candidate":
            if not pages_succeeded:
                raise BenchmarkCandidateCollectionError("Official Douyin candidate collection failed before any page was accepted")
            warnings.append("Collection stopped after an evidence-role mismatch; earlier public observations were retained.")
            stopped_reason = "role_mismatch_after_partial_result"
            has_more = True
            break

        pages_succeeded += 1
        page_receipt_hashes.append(_canonical_sha256(page_snapshot.route_receipt))
        has_more = bool(page_snapshot.coverage.has_more)
        next_cursor = page_snapshot.coverage.cursor
        if not isinstance(next_cursor, int):
            next_cursor = cursor
        next_search_id = page_snapshot.route_receipt.get("search_id")
        if not isinstance(next_search_id, str) or not next_search_id:
            next_search_id = search_id

        for item in page_snapshot.items:
            if _actor_key(item.actor_label) != target_key:
                excluded_count += 1
                continue
            if item.source_ref in seen_source_refs:
                duplicate_count += 1
                continue
            seen_source_refs.add(item.source_ref)
            if len(selected) < request.max_posts:
                selected.append(item)
            else:
                sample_cap_omitted_count += 1

        cursor = next_cursor
        search_id = next_search_id
        if len(selected) >= request.max_posts:
            stopped_reason = "sample_cap_reached"
            break
        if not has_more:
            stopped_reason = "provider_exhausted"
            break
        pagination_key = (cursor, search_id)
        if pagination_key in seen_pagination:
            warnings.append("Collection stopped because the provider pagination receipt did not advance.")
            stopped_reason = "pagination_did_not_advance"
            has_more = True
            break
        if search_id is None:
            warnings.append("Collection stopped because the provider did not return the search_id required for another page.")
            stopped_reason = "pagination_receipt_incomplete"
            has_more = True
            break
        seen_pagination.add(pagination_key)

    route_receipt = {
        "adapter": "douyin_openapi.search.video_search",
        "capability_version": _video_search_scope(context),
        "manifest_version": manifest_version,
        "catalog_version": manifest.get("metadata", {}).get("catalog_version"),
        "pages_requested": pages_requested,
        "pages_succeeded": pages_succeeded,
        "page_receipt_sha256": page_receipt_hashes,
        "actor_match": "unicode_normalized_exact",
        "target_actor_label": request.actor_label,
        "viewer_context_supplied": request.viewer_open_id is not None,
        "target_identity_status": "display_name_candidate_only",
        "sample_cap_omitted_count": sample_cap_omitted_count,
        "stopped_reason": stopped_reason,
    }
    route_receipt = {key: value for key, value in route_receipt.items() if value is not None}

    limitations = (
        "Actor display-name matching is a candidate filter, not a stable target-account identity.",
        "Official keyword search is ranked and bounded; it is not a complete account post list.",
        "This is benchmark-account discovery evidence, not a BenchmarkSnapshot.",
        "Public captions and counts are point-in-time observations, not positioning, audience, causality, or transferability claims.",
    )
    return EvidenceSnapshot(
        provider="douyin_open_platform",
        collection_method="official_openapi_multi_page_search",
        evidence_role="benchmark_account_candidate",
        captured_at=capture_time,
        rights_basis="public search through the configured Douyin Open Platform application",
        query=request.query,
        items=tuple(selected),
        coverage=EvidenceCoverageReceipt(
            population_scope="public_video_search_results_matching_actor_display_name",
            requested_count=request.max_posts,
            returned_count=len(selected),
            excluded_count=excluded_count,
            duplicate_count=duplicate_count,
            has_more=has_more,
            cursor=cursor,
            limitations=("Coverage describes the inspected search pages, not the creator's complete account.",),
        ),
        route_receipt=route_receipt,
        warnings=tuple(warnings),
        limitations=limitations,
    )


def seal_benchmark_account_candidate(
    *,
    project: ProjectRef,
    snapshot: EvidenceSnapshot,
    source_thread_id: str,
    source_run_id: str,
    parents: tuple[ArtifactParentRef, ...] = (),
) -> ArtifactEnvelope:
    if snapshot.evidence_role != "benchmark_account_candidate":
        raise ValueError("candidate sealing requires benchmark_account_candidate evidence")
    return seal_evidence_snapshot(
        project=project,
        snapshot=snapshot,
        parents=parents,
        source_thread_id=source_thread_id,
        source_run_id=source_run_id,
    )


__all__ = [
    "BenchmarkCandidateCollectionError",
    "BenchmarkCandidateRequest",
    "BenchmarkDiscoveryRequest",
    "collect_benchmark_account_candidate",
    "discover_benchmark_account_candidates",
    "seal_benchmark_account_candidate",
]
