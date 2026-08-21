from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable, Iterable
from enum import StrEnum
from typing import Any, Protocol
from urllib.parse import urlparse

from pydantic import Field, field_validator, model_validator

from deerflow.content_intelligence.contracts import ContractModel, NonEmptyStr, SourceItem
from deerflow.content_intelligence.lexical_evidence import (
    LexicalEvidenceMode,
    LexicalEvidenceProvider,
)

logger = logging.getLogger(__name__)

_MAX_QUERY_CHARS = 240
_MAX_RESULT_CONTENT_CHARS = 800
_MAX_EVIDENCE_BYTES = 4_096
_DEFAULT_MAX_RESULTS = 3


class TermResolutionStatus(StrEnum):
    KNOWN = "known"
    VERIFIED = "verified"
    UNRESOLVED = "unresolved"


class TermEvidenceSearchResult(ContractModel):
    title: NonEmptyStr = Field(max_length=240)
    url: NonEmptyStr = Field(max_length=2_048)
    content: NonEmptyStr = Field(max_length=_MAX_RESULT_CONTENT_CHARS)

    @field_validator("url")
    @classmethod
    def require_public_http_url(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("term evidence URL must use http or https")
        return value


class TermResolution(ContractModel):
    status: TermResolutionStatus
    query: NonEmptyStr | None = None
    checked_terms: tuple[NonEmptyStr, ...] = ()
    unknown_terms: tuple[NonEmptyStr, ...] = ()
    sources: tuple[SourceItem, ...] = ()
    limitations: tuple[NonEmptyStr, ...] = ()

    @model_validator(mode="after")
    def validate_state(self) -> TermResolution:
        if self.status == TermResolutionStatus.KNOWN:
            if self.unknown_terms or self.sources:
                raise ValueError("known term resolution cannot contain unknown terms or external sources")
        elif self.status == TermResolutionStatus.VERIFIED:
            if not self.sources:
                raise ValueError("verified term resolution requires external sources")
        elif self.sources:
            raise ValueError("unresolved term resolution cannot contain external sources")
        if any(source.evidence_role != "term_evidence" for source in self.sources):
            raise ValueError("term resolution sources must use the term_evidence role")
        return self

    @classmethod
    def known(cls, *, checked_terms: tuple[str, ...]) -> TermResolution:
        return cls(
            status=TermResolutionStatus.KNOWN,
            checked_terms=checked_terms,
        )

    @classmethod
    def unresolved(
        cls,
        *,
        query: str,
        checked_terms: tuple[str, ...],
        unknown_terms: tuple[str, ...],
        limitation: str,
    ) -> TermResolution:
        return cls(
            status=TermResolutionStatus.UNRESOLVED,
            query=query,
            checked_terms=checked_terms,
            unknown_terms=unknown_terms,
            limitations=(limitation,),
        )

    @classmethod
    def from_search_results(
        cls,
        *,
        query: str,
        checked_terms: tuple[str, ...],
        unknown_terms: tuple[str, ...],
        results: Iterable[TermEvidenceSearchResult],
    ) -> TermResolution:
        sources: list[SourceItem] = []
        seen_urls: set[str] = set()
        used_bytes = 0
        for result in results:
            if result.url in seen_urls or len(sources) >= _DEFAULT_MAX_RESULTS:
                continue
            source = SourceItem(
                source_id=f"source-term-evidence-{len(sources) + 1}",
                kind="term_evidence",
                content=result.content,
                evidence_role="term_evidence",
                title=result.title,
                uri=result.url,
            )
            source_bytes = len(source.model_dump_json(exclude_none=True).encode("utf-8"))
            if used_bytes + source_bytes > _MAX_EVIDENCE_BYTES:
                continue
            seen_urls.add(result.url)
            used_bytes += source_bytes
            sources.append(source)
        if not sources:
            return cls.unresolved(
                query=query,
                checked_terms=checked_terms,
                unknown_terms=unknown_terms,
                limitation="词项核实没有取得可用公开证据，当前具体含义保持未知。",
            )
        return cls(
            status=TermResolutionStatus.VERIFIED,
            query=query,
            checked_terms=checked_terms,
            unknown_terms=unknown_terms,
            sources=tuple(sources),
            limitations=("公开搜索摘要只用于核实词项含义；它不是选题、对标账号或市场效果证据。",),
        )


class KnownTermStore(Protocol):
    async def is_known(self, term: str) -> bool: ...


class LexicalKnownTermStore:
    """Treat exact local lexical entries as stable-known terms."""

    def __init__(self, provider: LexicalEvidenceProvider) -> None:
        self._provider = provider

    async def is_known(self, term: str) -> bool:
        evidence = await self._provider.lookup(
            term,
            mode=LexicalEvidenceMode.EXACT,
        )
        return bool(evidence.whole_word_entries)


TermEvidenceSearch = Callable[
    [str, int],
    Awaitable[tuple[TermEvidenceSearchResult, ...]],
]


class TermResolver:
    """Verify unfamiliar literal terms before downstream content judgment."""

    def __init__(
        self,
        *,
        known_term_store: KnownTermStore | None,
        search: TermEvidenceSearch | None,
        max_results: int = _DEFAULT_MAX_RESULTS,
    ) -> None:
        if not 1 <= max_results <= _DEFAULT_MAX_RESULTS:
            raise ValueError("term evidence max_results must be between 1 and 3")
        self._known_term_store = known_term_store
        self._search = search
        self._max_results = max_results

    async def resolve(
        self,
        *,
        source_object: str,
        lexical_head: str,
        modifier_terms: tuple[str, ...],
    ) -> TermResolution:
        checked_terms = _unique_terms((lexical_head, *modifier_terms))
        unknown_terms: list[str] = []
        store_unavailable = self._known_term_store is None
        for term in checked_terms:
            if self._known_term_store is None:
                unknown_terms.append(term)
                continue
            try:
                known = await self._known_term_store.is_known(term)
            except Exception as exc:
                logger.warning(
                    "Local known-term lookup was unavailable: %s",
                    type(exc).__name__,
                )
                store_unavailable = True
                known = False
            if not known:
                unknown_terms.append(term)

        if not unknown_terms:
            return TermResolution.known(checked_terms=checked_terms)

        query = source_object.strip()[:_MAX_QUERY_CHARS]
        if self._search is None:
            return TermResolution.unresolved(
                query=query,
                checked_terms=checked_terms,
                unknown_terms=tuple(unknown_terms),
                limitation="词项核实搜索暂时不可用，当前具体含义保持未知。",
            )
        try:
            results = await self._search(query, self._max_results)
        except Exception as exc:
            logger.warning(
                "Bounded term evidence search was unavailable: %s",
                type(exc).__name__,
            )
            return TermResolution.unresolved(
                query=query,
                checked_terms=checked_terms,
                unknown_terms=tuple(unknown_terms),
                limitation="词项核实搜索暂时不可用，当前具体含义保持未知。",
            )
        limitation = "本地词项库暂时不可用，且公开搜索没有取得可用证据，当前具体含义保持未知。" if store_unavailable else "词项核实没有取得可用公开证据，当前具体含义保持未知。"
        if not results:
            return TermResolution.unresolved(
                query=query,
                checked_terms=checked_terms,
                unknown_terms=tuple(unknown_terms),
                limitation=limitation,
            )
        return TermResolution.from_search_results(
            query=query,
            checked_terms=checked_terms,
            unknown_terms=tuple(unknown_terms),
            results=results,
        )


def parse_term_search_payload(
    raw: Any,
    *,
    max_results: int = _DEFAULT_MAX_RESULTS,
) -> tuple[TermEvidenceSearchResult, ...]:
    """Normalize configured web-search output without accepting other evidence roles."""

    if not isinstance(raw, str):
        return ()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return ()
    if isinstance(payload, dict):
        declared_role = payload.get("evidence_role")
        if declared_role not in {None, "term_evidence"}:
            return ()
    items = _search_result_items(payload)
    results: list[TermEvidenceSearchResult] = []
    for item in items[:max_results]:
        if not isinstance(item, dict):
            continue
        title = _first_text(item, "title", "Title")
        url = _first_text(item, "url", "Url", "link", "href")
        content = _first_text(
            item,
            "content",
            "snippet",
            "summary",
            "body",
            "Content",
            "Snippet",
            "Summary",
        )
        try:
            results.append(
                TermEvidenceSearchResult(
                    title=title[:240],
                    url=url[:2_048],
                    content=content[:_MAX_RESULT_CONTENT_CHARS],
                )
            )
        except ValueError:
            continue
    return tuple(results)


def _unique_terms(terms: Iterable[str]) -> tuple[str, ...]:
    unique: list[str] = []
    seen: set[str] = set()
    for term in terms:
        normalized = term.strip()
        key = normalized.casefold()
        if not normalized or key in seen:
            continue
        seen.add(key)
        unique.append(normalized)
    return tuple(unique)


def _search_result_items(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    for key in ("results", "data", "items"):
        value = payload.get(key)
        if isinstance(value, list):
            return value
    result = payload.get("Result")
    if isinstance(result, dict):
        for key in ("WebResults", "Results", "items"):
            value = result.get(key)
            if isinstance(value, list):
                return value
    return []


def _first_text(item: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


__all__ = [
    "KnownTermStore",
    "LexicalKnownTermStore",
    "TermEvidenceSearch",
    "TermEvidenceSearchResult",
    "TermResolution",
    "TermResolutionStatus",
    "TermResolver",
    "parse_term_search_payload",
]
