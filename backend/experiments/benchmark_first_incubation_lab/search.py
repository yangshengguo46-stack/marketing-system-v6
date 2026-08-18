from __future__ import annotations

import asyncio
import inspect
import json
import re
from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from experiments.benchmark_first_incubation_lab.contracts import (
    BenchmarkEvidenceItem,
    BenchmarkEvidencePack,
    BenchmarkSearchPlan,
    EvidenceMembership,
    EvidenceProjection,
    QueryKind,
    SearchCoverage,
    SearchStatus,
    evidence_content_hash,
    evidence_item_id,
    evidence_pack_hash,
)

SearchProvider = Callable[[str, int], Awaitable[str | Mapping[str, Any]] | str | Mapping[str, Any]]

_MAX_RESULTS_PER_QUERY = 5
_MAX_EVIDENCE_PROJECTION_BYTES = 10_000


async def ddg_search_provider(query: str, max_results: int) -> str:
    if max_results != _MAX_RESULTS_PER_QUERY:
        raise ValueError("A99 DDG adapter requires exactly five results per query")
    return await asyncio.to_thread(_typed_ddg_search, query)


async def collect_shared_evidence(
    *,
    plan: BenchmarkSearchPlan,
    search_provider: SearchProvider,
    provider_name: str = "a99_typed_ddg_search",
) -> BenchmarkEvidencePack:
    requests = (
        (QueryKind.DIRECT, plan.direct_query),
        (QueryKind.DEMAND, plan.demand_query),
        (QueryKind.MECHANISM, plan.mechanism_query),
    )
    raw_batches = await asyncio.gather(*(_search_once(search_provider, query=query) for _, query in requests))

    coverage: list[SearchCoverage] = []
    grouped: dict[str, dict[str, Any]] = {}
    for (query_kind, query), batch in zip(requests, raw_batches, strict=True):
        accepted_urls: set[str] = set()
        for raw_item in batch["results"]:
            candidate = _normalize_candidate(raw_item)
            if candidate is None or candidate["url"] in accepted_urls:
                continue
            accepted_urls.add(candidate["url"])
            membership = EvidenceMembership(
                query_kind=query_kind,
                query=query,
                rank=len(accepted_urls),
            )
            entry = grouped.setdefault(
                candidate["url"],
                {"memberships": {}, "variants": []},
            )
            entry["memberships"][(query_kind, query)] = membership
            entry["variants"].append((candidate["title"], candidate["snippet"]))
            if len(accepted_urls) == _MAX_RESULTS_PER_QUERY:
                break

        raw_count = int(batch["raw_result_count"])
        if batch["error"] is not None:
            status = SearchStatus.FAILED
        elif raw_count == 0:
            status = SearchStatus.EMPTY
        else:
            status = SearchStatus.SUCCEEDED
        coverage.append(
            SearchCoverage(
                query_kind=query_kind,
                query=query,
                status=status,
                raw_result_count=raw_count,
                accepted_result_count=len(accepted_urls),
                error=batch["error"],
            )
        )

    items: list[BenchmarkEvidenceItem] = []
    for url, entry in grouped.items():
        title, snippet = max(
            entry["variants"],
            key=lambda value: (len(value[1]), len(value[0]), value[1], value[0]),
        )
        memberships = tuple(
            sorted(
                entry["memberships"].values(),
                key=lambda item: (_query_kind_index(item.query_kind), item.rank, item.query),
            )
        )
        primary = memberships[0]
        content_hash = evidence_content_hash(title, snippet)
        items.append(
            BenchmarkEvidenceItem(
                evidence_id=evidence_item_id(
                    provider=provider_name,
                    url=url,
                    content_hash=content_hash,
                ),
                query_kind=primary.query_kind,
                query=primary.query,
                memberships=memberships,
                title=title,
                url=url,
                snippet=snippet,
                content_hash=content_hash,
            )
        )
    items.sort(
        key=lambda item: (
            min(_query_kind_index(membership.query_kind) for membership in item.memberships),
            min(membership.rank for membership in item.memberships),
            item.url,
        )
    )

    coverage_tuple = tuple(coverage)
    items_tuple = tuple(items)
    pack_hash = evidence_pack_hash(
        case_id=plan.case_id,
        provider=provider_name,
        collection_method="public_web_benchmark_discovery",
        search_plan=plan,
        coverage=coverage_tuple,
        items=items_tuple,
    )
    return BenchmarkEvidencePack(
        case_id=plan.case_id,
        provider=provider_name,
        search_plan=plan,
        coverage=coverage_tuple,
        items=items_tuple,
        evidence_hash=pack_hash,
    )


def project_evidence(
    pack: BenchmarkEvidencePack,
    *,
    query_kinds: Sequence[QueryKind | str],
    max_bytes: int = _MAX_EVIDENCE_PROJECTION_BYTES,
) -> EvidenceProjection:
    kinds = tuple(QueryKind(kind) for kind in query_kinds)
    if len(kinds) != len(set(kinds)):
        raise ValueError("evidence projection query kinds must be unique")

    eligible = tuple(item for item in pack.items if any(membership.query_kind in kinds for membership in item.memberships))
    items_by_kind = {
        kind: tuple(
            sorted(
                (item for item in eligible if any(membership.query_kind is kind for membership in item.memberships)),
                key=lambda item: (
                    min(membership.rank for membership in item.memberships if membership.query_kind is kind),
                    item.url,
                ),
            )
        )
        for kind in kinds
    }
    balanced: list[BenchmarkEvidenceItem] = []
    balanced_ids: set[str] = set()
    for index in range(max((len(items) for items in items_by_kind.values()), default=0)):
        for kind in kinds:
            if index >= len(items_by_kind[kind]):
                continue
            item = items_by_kind[kind][index]
            if item.evidence_id in balanced_ids:
                continue
            balanced_ids.add(item.evidence_id)
            balanced.append(item)

    included: list[dict[str, Any]] = []
    base = {
        "case_id": pack.case_id,
        "collection_method": pack.collection_method,
        "provider": pack.provider,
        "evidence_hash": pack.evidence_hash,
        "query_kinds": [kind.value for kind in kinds],
        "coverage": [
            {
                "query_kind": entry.query_kind.value,
                "query": entry.query,
                "status": entry.status.value,
                "accepted_result_count": entry.accepted_result_count,
                "error": entry.error,
            }
            for entry in pack.coverage
            if entry.query_kind in kinds
        ],
        "items": included,
    }
    for item in balanced:
        candidate = {
            "evidence_id": item.evidence_id,
            "query_kind": item.query_kind.value,
            "memberships": [
                {
                    "query_kind": membership.query_kind.value,
                    "query": membership.query,
                    "rank": membership.rank,
                }
                for membership in item.memberships
            ],
            "title": item.title,
            "url": item.url,
            "snippet": item.snippet,
        }
        included.append(candidate)
        rendered = _compact_json(base)
        if len(rendered.encode("utf-8")) > max_bytes:
            included.pop()

    rendered = _compact_json(base)
    if len(rendered.encode("utf-8")) > max_bytes:
        raise ValueError("evidence projection metadata exceeded its byte budget")
    return EvidenceProjection(
        case_id=pack.case_id,
        evidence_hash=pack.evidence_hash,
        query_kinds=kinds,
        included_evidence_ids=tuple(str(item["evidence_id"]) for item in included),
        omitted_item_count=len(eligible) - len(included),
        rendered=rendered,
    )


async def _search_once(
    provider: SearchProvider,
    *,
    query: str,
) -> dict[str, Any]:
    try:
        raw = provider(query, _MAX_RESULTS_PER_QUERY)
        if inspect.isawaitable(raw):
            raw = await raw
        payload = json.loads(raw) if isinstance(raw, str) else dict(raw)
        raw_results = payload.get("results", ())
        results = tuple(item for item in raw_results if isinstance(item, Mapping))
        error = payload.get("error")
        if error and not results:
            return {
                "results": (),
                "raw_result_count": 0,
                "error": None if str(error).casefold() == "no results found" else _clean_text(str(error), 240),
            }
        return {
            "results": results,
            "raw_result_count": len(results),
            "error": None,
        }
    except Exception as exc:
        return {
            "results": (),
            "raw_result_count": 0,
            "error": _clean_text(f"{type(exc).__name__}: {exc}", 240),
        }


def _normalize_candidate(raw_item: Mapping[str, Any]) -> dict[str, str] | None:
    raw_url = _clean_text(
        str(raw_item.get("url") or raw_item.get("href") or raw_item.get("link") or ""),
        1_000,
    )
    url = _canonicalize_public_url(raw_url)
    if not url:
        return None
    title = _clean_text(str(raw_item.get("title") or url), 300)
    snippet = _clean_text(
        str(raw_item.get("content") or raw_item.get("body") or raw_item.get("snippet") or ""),
        600,
    )
    return {"title": title, "url": url, "snippet": snippet}


def _canonicalize_public_url(value: str) -> str | None:
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        return None
    scheme = parsed.scheme.casefold()
    if scheme not in {"http", "https"} or not parsed.hostname:
        return None
    if parsed.username or parsed.password:
        return None
    hostname = parsed.hostname.casefold()
    if port is not None and not (scheme == "http" and port == 80 or scheme == "https" and port == 443):
        hostname = f"{hostname}:{port}"
    filtered_query = sorted((key, val) for key, val in parse_qsl(parsed.query, keep_blank_values=True) if not key.casefold().startswith("utm_") and key.casefold() not in {"spm", "from", "source", "ref"})
    return urlunsplit(
        (
            scheme,
            hostname,
            parsed.path or "",
            urlencode(filtered_query, doseq=True),
            "",
        )
    )


def _typed_ddg_search(query: str) -> str:
    from ddgs import DDGS

    results = DDGS(timeout=30).text(
        query,
        region="cn-zh",
        safesearch="moderate",
        max_results=_MAX_RESULTS_PER_QUERY,
        backend="auto",
    )
    normalized = [
        {
            "title": result.get("title", ""),
            "url": result.get("href", result.get("link", "")),
            "content": result.get("body", result.get("snippet", "")),
        }
        for result in (results or ())
    ]
    return json.dumps(
        {
            "query": query,
            "total_results": len(normalized),
            "results": normalized,
        },
        ensure_ascii=False,
    )


def _query_kind_index(kind: QueryKind) -> int:
    return (QueryKind.DIRECT, QueryKind.DEMAND, QueryKind.MECHANISM).index(kind)


def _clean_text(value: str, limit: int) -> str:
    value = re.sub(r"[\x00-\x1f\x7f]+", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value[:limit]


def _compact_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


__all__ = [
    "SearchProvider",
    "collect_shared_evidence",
    "ddg_search_provider",
    "project_evidence",
]
