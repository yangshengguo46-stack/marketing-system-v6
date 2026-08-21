from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from deerflow.content_intelligence.term_resolution import (
    TermEvidenceSearchResult,
    TermResolutionStatus,
    TermResolver,
    parse_term_search_payload,
)


class StubKnownTermStore:
    def __init__(self, known_terms: set[str]) -> None:
        self.known_terms = known_terms
        self.calls: list[str] = []

    async def is_known(self, term: str) -> bool:
        self.calls.append(term)
        return term in self.known_terms


@pytest.mark.asyncio
async def test_stable_known_terms_bypass_web_search() -> None:
    store = StubKnownTermStore({"黄金", "礼品"})
    search = AsyncMock()
    resolver = TermResolver(known_term_store=store, search=search)

    resolution = await resolver.resolve(
        source_object="黄金礼品",
        lexical_head="礼品",
        modifier_terms=("黄金",),
    )

    assert resolution.status == TermResolutionStatus.KNOWN
    assert resolution.checked_terms == ("礼品", "黄金")
    assert resolution.unknown_terms == ()
    assert resolution.sources == ()
    assert store.calls == ["礼品", "黄金"]
    search.assert_not_awaited()


@pytest.mark.asyncio
async def test_one_unknown_term_runs_one_exact_bounded_search_and_returns_term_evidence() -> None:
    store = StubKnownTermStore({"公会"})
    search = AsyncMock(
        return_value=(
            TermEvidenceSearchResult(
                title="MENA 区域说明",
                url="https://example.com/mena",
                content="MENA 是中东和北非地区的常用缩写。",
            ),
            TermEvidenceSearchResult(
                title="直播公会行业说明",
                url="https://example.com/live-guild",
                content="一条用于核实业务术语的公开摘要。",
            ),
        )
    )
    resolver = TermResolver(known_term_store=store, search=search)

    resolution = await resolver.resolve(
        source_object="MENA TikTok直播公会",
        lexical_head="公会",
        modifier_terms=("MENA", "TikTok直播"),
    )

    assert resolution.status == TermResolutionStatus.VERIFIED
    assert resolution.query == "MENA TikTok直播公会"
    assert resolution.unknown_terms == ("MENA", "TikTok直播")
    search.assert_awaited_once_with("MENA TikTok直播公会", 3)
    assert len(resolution.sources) == 2
    assert all(source.evidence_role == "term_evidence" for source in resolution.sources)
    assert all(source.kind == "term_evidence" for source in resolution.sources)
    assert {source.uri for source in resolution.sources} == {
        "https://example.com/mena",
        "https://example.com/live-guild",
    }


@pytest.mark.asyncio
async def test_empty_search_keeps_the_unknown_visible_without_inventing_a_definition() -> None:
    resolver = TermResolver(
        known_term_store=StubKnownTermStore(set()),
        search=AsyncMock(return_value=()),
    )

    resolution = await resolver.resolve(
        source_object="走个面",
        lexical_head="走个面",
        modifier_terms=(),
    )

    assert resolution.status == TermResolutionStatus.UNRESOLVED
    assert resolution.sources == ()
    assert resolution.unknown_terms == ("走个面",)
    assert any("没有取得可用公开证据" in limitation for limitation in resolution.limitations)


@pytest.mark.asyncio
async def test_search_failure_is_fail_soft_and_does_not_expose_provider_details() -> None:
    resolver = TermResolver(
        known_term_store=None,
        search=AsyncMock(side_effect=RuntimeError("secret provider payload")),
    )

    resolution = await resolver.resolve(
        source_object="某个近期新名词",
        lexical_head="某个近期新名词",
        modifier_terms=(),
    )

    assert resolution.status == TermResolutionStatus.UNRESOLVED
    assert resolution.sources == ()
    assert "secret provider payload" not in resolution.model_dump_json()
    assert any("暂时不可用" in limitation for limitation in resolution.limitations)


def test_term_search_normalizes_byted_web_results_with_a_strict_small_budget() -> None:
    payload = {
        "Result": {
            "WebResults": [
                {
                    "Title": "近期术语官方说明",
                    "Url": "https://example.com/new-term",
                    "Summary": "用于核实新词含义的公开摘要。",
                },
                {
                    "Title": "第二来源",
                    "Url": "https://example.com/new-term-2",
                    "Snippet": "第二条摘要。",
                },
            ]
        }
    }

    results = parse_term_search_payload(json.dumps(payload), max_results=1)

    assert len(results) == 1
    assert results[0].title == "近期术语官方说明"
    assert results[0].content == "用于核实新词含义的公开摘要。"


@pytest.mark.parametrize("evidence_role", ("topic_evidence", "benchmark_evidence"))
def test_term_search_rejects_topic_and_benchmark_receipts(evidence_role: str) -> None:
    raw = json.dumps(
        {
            "evidence_role": evidence_role,
            "results": [
                {
                    "title": "错误证据角色",
                    "url": "https://example.com/wrong-role",
                    "content": "不能进入词项核实。",
                }
            ],
        }
    )

    assert parse_term_search_payload(raw) == ()
