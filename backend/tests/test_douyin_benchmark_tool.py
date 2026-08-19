from __future__ import annotations

import importlib
import json
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from langchain_core.utils.function_calling import convert_to_openai_tool

from deerflow.community.douyin_openapi import BenchmarkCandidateCollectionError
from deerflow.incubation import (
    BenchmarkCoverageReceipt,
    BenchmarkPostObservation,
    BenchmarkProfileObservation,
    BenchmarkRouteReceipt,
    BenchmarkSnapshot,
    EvidenceCoverageReceipt,
    EvidenceItem,
    EvidenceSnapshot,
    ProjectRecord,
    ProjectRef,
)
from deerflow.tools.builtins.douyin_benchmark_tool import (
    douyin_benchmark_account_tool,
    douyin_benchmark_candidate_tool,
)
from deerflow.tools.tools import BUILTIN_TOOLS

tool_module = importlib.import_module("deerflow.tools.builtins.douyin_benchmark_tool")
NOW = datetime(2026, 8, 17, 12, 0, tzinfo=UTC)


def _snapshot() -> EvidenceSnapshot:
    return EvidenceSnapshot(
        provider="douyin_open_platform",
        collection_method="official_openapi_multi_page_search",
        evidence_role="benchmark_account_candidate",
        captured_at=NOW,
        rights_basis="public search through the configured Douyin Open Platform application",
        query="大能 腕表",
        items=(
            EvidenceItem(
                source_ref="douyin:video:1",
                source_type="douyin_video",
                title="为什么腕表不只是计时工具",
                excerpt="公开视频文本",
                provenance="observed",
                public_uri="https://www.douyin.com/video/1",
                actor_label="大能",
                observed_values={
                    "published_at": NOW.isoformat(),
                    "digg_count": 100,
                },
            ),
        ),
        coverage=EvidenceCoverageReceipt(
            population_scope="public_video_search_results_matching_actor_display_name",
            requested_count=12,
            returned_count=1,
            has_more=False,
        ),
        route_receipt={
            "adapter": "douyin_openapi.search.video_search",
            "capability_version": "aweme.dy.video_search_v2",
            "target_identity_status": "display_name_candidate_only",
        },
        limitations=("Actor display-name matching is a candidate filter, not a stable target-account identity.",),
    )


def _account_snapshot() -> BenchmarkSnapshot:
    return BenchmarkSnapshot(
        provider="douyin_authenticated_browser",
        collection_method="authenticated_browser_network_capture",
        captured_at=NOW,
        rights_basis="public account pages viewed through a local authenticated browser",
        requested_url="https://www.douyin.com/user/watch-account",
        profile=BenchmarkProfileObservation(
            platform="douyin",
            external_account_id="watch-account",
            canonical_url="https://www.douyin.com/user/watch-account",
            display_name="大能",
            captured_at=NOW,
            public_metrics={"followers": 9_000_000},
        ),
        posts=(
            BenchmarkPostObservation(
                platform="douyin",
                external_post_id="watch-1",
                author_external_account_id="watch-account",
                canonical_url="https://www.douyin.com/video/watch-1",
                caption="手表为什么不只是看时间",
                captured_at=NOW,
                public_metrics={"likes": 88},
            ),
        ),
        coverage=BenchmarkCoverageReceipt(
            population_scope="author_qualified_posts_visible_on_the_bounded_account_page",
            requested_count=12,
            returned_count=1,
            sample_basis="bounded account page",
        ),
        route_receipt=BenchmarkRouteReceipt(
            adapter="douyin.browser.network_capture",
            capability_version="douyin-browser-fallback-v1",
            route="account_posts",
        ),
        limitations=("Bounded public account observation.",),
    )


def _runtime(*, project_id: str | None = None, user_id: str = "user-1") -> SimpleNamespace:
    context = {
        "thread_id": "thread-1",
        "run_id": "run-1",
        "user_id": user_id,
    }
    if project_id is not None:
        context["incubation_project_id"] = project_id
    return SimpleNamespace(context=context)


def test_douyin_benchmark_tool_is_available_without_exposing_runtime_or_credentials() -> None:
    assert douyin_benchmark_candidate_tool in BUILTIN_TOOLS
    assert douyin_benchmark_account_tool in BUILTIN_TOOLS
    schema = convert_to_openai_tool(douyin_benchmark_candidate_tool)["function"]

    assert schema["name"] == "collect_douyin_benchmark_candidate"
    assert set(schema["parameters"]["properties"]) == {
        "query",
        "actor_label",
        "max_posts",
    }
    serialized_parameters = json.dumps(
        schema["parameters"],
        ensure_ascii=False,
    ).casefold()
    for forbidden in (
        "runtime",
        "user_id",
        "thread_id",
        "run_id",
        "project_id",
        "client_secret",
        "access_token",
        "cookie",
        "cursor",
        "search_id",
    ):
        assert forbidden not in serialized_parameters

    account_schema = convert_to_openai_tool(douyin_benchmark_account_tool)["function"]
    assert account_schema["name"] == "collect_douyin_benchmark_account"
    assert set(account_schema["parameters"]["properties"]) == {
        "account_url",
        "max_posts",
    }
    serialized_account_parameters = json.dumps(account_schema["parameters"], ensure_ascii=False).casefold()
    for forbidden in (
        "runtime",
        "user_id",
        "project_id",
        "cookie",
        "storage_state",
        "client_secret",
    ):
        assert forbidden not in serialized_account_parameters


@pytest.mark.asyncio
async def test_douyin_benchmark_account_tool_uses_direct_link_and_returns_formal_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    collect = AsyncMock(return_value=_account_snapshot())
    monkeypatch.setattr(tool_module, "collect_browser_benchmark_account", collect)

    raw = await tool_module._collect_douyin_benchmark_account(
        runtime=_runtime(),
        account_url="https://www.douyin.com/user/watch-account",
        max_posts=12,
    )
    result = json.loads(raw)

    assert result["status"] == "ok"
    assert result["evidence"]["evidence_role"] == "benchmark_evidence"
    assert result["evidence"]["profile"]["external_account_id"] == "watch-account"
    request = collect.await_args.args[0]
    assert request.requested_url == "https://www.douyin.com/user/watch-account"
    assert request.max_posts == 12


@pytest.mark.asyncio
async def test_douyin_benchmark_tool_returns_read_only_evidence_without_forcing_a_project(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    collect = AsyncMock(return_value=_snapshot())
    monkeypatch.setattr(tool_module, "collect_benchmark_account_candidate", collect)
    monkeypatch.setattr(tool_module, "build_default_router", Mock(return_value=object()))
    monkeypatch.setattr(tool_module, "context_from_environment", Mock(return_value=object()))
    repository = Mock()
    monkeypatch.setattr(tool_module, "_get_repository", Mock(return_value=repository))

    raw = await tool_module._collect_douyin_benchmark_candidate(
        runtime=_runtime(),
        query="大能 腕表",
        actor_label="大能",
        max_posts=12,
    )
    result = json.loads(raw)

    assert result["status"] == "ok"
    assert result["persistence"] == {"status": "not_selected"}
    assert result["evidence"]["evidence_role"] == "benchmark_account_candidate"
    assert result["evidence"]["items"][0]["actor_label"] == "大能"
    assert "positioning" not in result
    assert "audience" not in result
    repository.get_project.assert_not_called()
    request = collect.await_args.args[0]
    assert request.query == "大能 腕表"
    assert request.actor_label == "大能"
    assert request.max_posts == 12
    assert request.max_pages == 5


@pytest.mark.asyncio
async def test_douyin_benchmark_tool_seals_into_the_authenticated_users_selected_project(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = _snapshot()
    collect = AsyncMock(return_value=snapshot)
    monkeypatch.setattr(tool_module, "collect_benchmark_account_candidate", collect)
    monkeypatch.setattr(tool_module, "build_default_router", Mock(return_value=object()))
    monkeypatch.setattr(tool_module, "context_from_environment", Mock(return_value=object()))
    project = ProjectRef(owner_user_id="user-1", project_id="project-1")
    repository = SimpleNamespace(
        get_project=AsyncMock(
            return_value=ProjectRecord(
                project=project,
                display_name="腕表项目",
                created_at=NOW,
                updated_at=NOW,
            )
        ),
        put_artifact=AsyncMock(side_effect=lambda artifact: artifact),
    )
    monkeypatch.setattr(tool_module, "_get_repository", Mock(return_value=repository))

    raw = await tool_module._collect_douyin_benchmark_candidate(
        runtime=_runtime(project_id="project-1"),
        query="大能 腕表",
        actor_label="大能",
        max_posts=12,
    )
    result = json.loads(raw)

    repository.get_project.assert_awaited_once_with(project)
    artifact = repository.put_artifact.await_args.args[0]
    assert artifact.project == project
    assert artifact.source_thread_id == "thread-1"
    assert artifact.source_run_id == "run-1"
    assert artifact.evidence_role == "benchmark_account_candidate"
    assert result["persistence"]["status"] == "stored"
    assert result["persistence"]["project_id"] == "project-1"
    assert result["persistence"]["artifact_id"] == artifact.artifact_id
    assert "user-1" not in raw


@pytest.mark.asyncio
async def test_douyin_benchmark_tool_rejects_an_unowned_project_before_platform_collection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    collect = AsyncMock(return_value=_snapshot())
    repository = SimpleNamespace(
        get_project=AsyncMock(return_value=None),
        put_artifact=AsyncMock(),
    )
    monkeypatch.setattr(tool_module, "collect_benchmark_account_candidate", collect)
    monkeypatch.setattr(tool_module, "_get_repository", Mock(return_value=repository))

    raw = await tool_module._collect_douyin_benchmark_candidate(
        runtime=_runtime(project_id="someone-elses-project"),
        query="大能 腕表",
        actor_label="大能",
        max_posts=12,
    )
    result = json.loads(raw)

    assert result == {
        "status": "invalid_project",
        "message": "The selected incubation project is unavailable for the authenticated user.",
    }
    collect.assert_not_awaited()
    repository.put_artifact.assert_not_awaited()


@pytest.mark.asyncio
async def test_douyin_benchmark_tool_redacts_provider_failure_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    collect = AsyncMock(side_effect=BenchmarkCandidateCollectionError("provider failed with client_secret=private-value and access_token=private-token"))
    browser_collect = AsyncMock(return_value=_snapshot().model_copy(update={"provider": "douyin_authenticated_browser"}))
    monkeypatch.setattr(tool_module, "collect_benchmark_account_candidate", collect)
    monkeypatch.setattr(tool_module, "collect_browser_benchmark_candidate", browser_collect)
    monkeypatch.setattr(tool_module, "build_default_router", Mock(return_value=object()))
    monkeypatch.setattr(tool_module, "context_from_environment", Mock(return_value=object()))

    raw = await tool_module._collect_douyin_benchmark_candidate(
        runtime=_runtime(),
        query="大能 腕表",
        actor_label="大能",
        max_posts=12,
    )

    result = json.loads(raw)
    assert result["status"] == "ok"
    assert result["evidence"]["provider"] == "douyin_authenticated_browser"
    browser_request = browser_collect.await_args.args[0]
    assert browser_request.query == "大能 腕表"
    assert browser_request.actor_label == "大能"
    assert "private-value" not in raw
    assert "private-token" not in raw


@pytest.mark.asyncio
async def test_douyin_benchmark_tool_does_not_open_browser_when_official_search_works(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    collect = AsyncMock(return_value=_snapshot())
    browser_collect = AsyncMock()
    monkeypatch.setattr(tool_module, "collect_benchmark_account_candidate", collect)
    monkeypatch.setattr(tool_module, "collect_browser_benchmark_candidate", browser_collect)
    monkeypatch.setattr(tool_module, "build_default_router", Mock(return_value=object()))
    monkeypatch.setattr(tool_module, "context_from_environment", Mock(return_value=object()))

    raw = await tool_module._collect_douyin_benchmark_candidate(
        runtime=_runtime(),
        query="大能 腕表",
        actor_label="大能",
        max_posts=12,
    )

    assert json.loads(raw)["status"] == "ok"
    browser_collect.assert_not_awaited()


@pytest.mark.asyncio
async def test_douyin_benchmark_tool_keeps_collected_evidence_when_project_storage_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = _snapshot()
    monkeypatch.setattr(
        tool_module,
        "collect_benchmark_account_candidate",
        AsyncMock(return_value=snapshot),
    )
    monkeypatch.setattr(tool_module, "build_default_router", Mock(return_value=object()))
    monkeypatch.setattr(tool_module, "context_from_environment", Mock(return_value=object()))
    project = ProjectRef(owner_user_id="user-1", project_id="project-1")
    repository = SimpleNamespace(
        get_project=AsyncMock(
            return_value=ProjectRecord(
                project=project,
                display_name="腕表项目",
                created_at=NOW,
                updated_at=NOW,
            )
        ),
        put_artifact=AsyncMock(side_effect=RuntimeError("database failed with password=private-value and access_token=private-token")),
    )
    monkeypatch.setattr(tool_module, "_get_repository", Mock(return_value=repository))

    raw = await tool_module._collect_douyin_benchmark_candidate(
        runtime=_runtime(project_id="project-1"),
        query="大能 腕表",
        actor_label="大能",
        max_posts=12,
    )
    result = json.loads(raw)

    assert result["status"] == "ok"
    assert result["evidence"]["items"][0]["actor_label"] == "大能"
    assert result["persistence"] == {
        "status": "failed",
        "project_id": "project-1",
        "message": "The collected evidence could not be stored in the selected project.",
    }
    assert "private-value" not in raw
    assert "private-token" not in raw
