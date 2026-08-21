from __future__ import annotations

import importlib
import json
from unittest.mock import AsyncMock

import pytest

from deerflow.content_intelligence import TermEvidenceSearchResult
from deerflow.tools.builtins.business_term_tool import verify_business_term_tool
from deerflow.tools.tools import BUILTIN_TOOLS

tool_module = importlib.import_module("deerflow.tools.builtins.business_term_tool")


def test_bounded_business_term_verifier_is_available_to_the_lead() -> None:
    assert verify_business_term_tool in BUILTIN_TOOLS
    assert verify_business_term_tool.name == "verify_business_term"
    assert verify_business_term_tool.return_direct is False
    assert "not market research" in " ".join(verify_business_term_tool.description.split())


@pytest.mark.asyncio
async def test_business_term_verifier_runs_one_bounded_search_and_preserves_evidence_role(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    search = AsyncMock(
        return_value=(
            TermEvidenceSearchResult(
                title="TikTok LIVE 官方说明",
                url="https://example.com/tiktok-live-guild",
                content="LIVE agency 是帮助主播运营直播业务的合作机构。MENA 指中东和北非。",
            ),
        )
    )
    monkeypatch.setattr(tool_module, "search_term_evidence", search)

    raw = await verify_business_term_tool.ainvoke({"term_expression": "TikTok直播公会，主要地区为MENA和CCA"})
    payload = json.loads(raw)

    search.assert_awaited_once_with("TikTok直播公会，主要地区为MENA和CCA", 3)
    assert payload["status"] == "verified"
    assert payload["sources"][0]["evidence_role"] == "term_evidence"
    assert "不是选题、对标账号或市场效果证据" in payload["limitations"][0]


@pytest.mark.asyncio
async def test_business_term_verifier_keeps_meaning_unknown_when_search_has_no_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    search = AsyncMock(return_value=())
    monkeypatch.setattr(tool_module, "search_term_evidence", search)

    raw = await verify_business_term_tool.ainvoke({"term_expression": "近一年出现的新业务名词"})
    payload = json.loads(raw)

    assert payload["status"] == "unresolved"
    assert payload["sources"] == []
    assert "保持未知" in payload["limitations"][0]
