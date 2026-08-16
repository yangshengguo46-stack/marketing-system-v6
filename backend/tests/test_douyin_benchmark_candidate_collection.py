from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import pytest

from deerflow.community.douyin_openapi.benchmark_candidates import (
    BenchmarkCandidateCollectionError,
    BenchmarkCandidateRequest,
    collect_benchmark_account_candidate,
    seal_benchmark_account_candidate,
)
from deerflow.community.douyin_openapi.catalog import load_official_catalog
from deerflow.community.douyin_openapi.contracts import CapabilityContext
from deerflow.community.douyin_openapi.router import DomainRouter
from deerflow.config.database_config import DatabaseConfig
from deerflow.incubation import IncubationLedgerRepository, ProjectRef
from deerflow.persistence.engine import close_engine, get_session_factory, init_engine_from_config

NOW = datetime(2026, 8, 17, 10, 0, tzinfo=UTC)


def _context() -> CapabilityContext:
    return CapabilityContext(
        granted_scopes=frozenset({"aweme.dy.video_search_v2"}),
        configured_auth_modes=frozenset({"client_token"}),
        capability_generation="candidate-test-generation",
    )


def _video(
    item_id: str,
    *,
    nickname: str,
    title: str | None = None,
    digg_count: int = 10,
) -> dict[str, Any]:
    return {
        "title": title or f"作品 {item_id}",
        "url": f"https://www.douyin.com/video/{item_id}",
        "content": f"作品 {item_id} 的公开文本",
        "source_type": "douyin_video",
        "item_id": item_id,
        "nickname": nickname,
        "create_time": 1_700_000_000 + int(item_id),
        "digg_count": digg_count,
    }


def _page(
    arguments: dict[str, Any],
    *,
    cursor: int,
    has_more: bool,
    search_id: str,
    results: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "query": arguments["query"],
        "provider": "douyin_open_platform",
        "evidence_role": "benchmark_account_candidate",
        "total_results": len(results),
        "cursor": cursor,
        "has_more": has_more,
        "search_id": search_id,
        "results": results,
    }


@pytest.mark.asyncio
async def test_official_candidate_collection_filters_one_actor_across_pages_and_deduplicates() -> None:
    calls: list[dict[str, Any]] = []

    async def handler(arguments: dict[str, Any], context: CapabilityContext) -> dict[str, Any]:
        del context
        calls.append(arguments)
        if arguments["cursor"] == 0:
            return _page(
                arguments,
                cursor=20,
                has_more=True,
                search_id="search-session-1",
                results=[
                    _video("1", nickname="大能"),
                    _video("2", nickname="其他腕表博主"),
                    _video("3", nickname="大能"),
                ],
            )
        return _page(
            arguments,
            cursor=40,
            has_more=True,
            search_id="search-session-1",
            results=[
                _video("3", nickname="大能"),
                _video("4", nickname="大能"),
                _video("5", nickname="其他腕表博主"),
            ],
        )

    router = DomainRouter(
        load_official_catalog(),
        handlers={"search.video_search": handler},
    )
    snapshot = await collect_benchmark_account_candidate(
        BenchmarkCandidateRequest(
            query="大能 腕表",
            actor_label="大能",
            max_posts=3,
            max_pages=4,
            viewer_open_id="authorized-viewer-open-id",
        ),
        router=router,
        context=_context(),
        captured_at=NOW,
    )

    assert [item.source_ref for item in snapshot.items] == [
        "douyin:video:1",
        "douyin:video:3",
        "douyin:video:4",
    ]
    assert {item.actor_label for item in snapshot.items} == {"大能"}
    assert snapshot.evidence_role == "benchmark_account_candidate"
    assert snapshot.coverage.requested_count == 3
    assert snapshot.coverage.returned_count == 3
    assert snapshot.coverage.excluded_count == 2
    assert snapshot.coverage.duplicate_count == 1
    assert snapshot.coverage.has_more is True
    assert snapshot.route_receipt["pages_succeeded"] == 2
    assert snapshot.route_receipt["actor_match"] == "unicode_normalized_exact"
    assert snapshot.route_receipt["target_actor_label"] == "大能"
    assert snapshot.route_receipt["viewer_context_supplied"] is True
    assert snapshot.route_receipt["target_identity_status"] == "display_name_candidate_only"
    assert calls[0]["purpose"] == "benchmark_discovery"
    assert calls[0]["open_id"] == "authorized-viewer-open-id"
    assert calls[1]["cursor"] == 20
    assert calls[1]["search_id"] == "search-session-1"
    raw = snapshot.model_dump_json()
    assert "authorized-viewer-open-id" not in raw
    assert "external_account_id" not in raw


@pytest.mark.asyncio
async def test_candidate_collection_keeps_partial_observations_after_later_provider_failure() -> None:
    calls = 0

    async def handler(arguments: dict[str, Any], context: CapabilityContext) -> dict[str, Any]:
        nonlocal calls
        del context
        calls += 1
        if calls == 1:
            return _page(
                arguments,
                cursor=20,
                has_more=True,
                search_id="search-session-2",
                results=[_video("6", nickname="田永成")],
            )
        return {
            "error": "Douyin video search error 28001018",
            "message": "应用未获得该能力",
            "log_id": "provider-log-id",
            "query": arguments["query"],
        }

    router = DomainRouter(
        load_official_catalog(),
        handlers={"search.video_search": handler},
    )
    snapshot = await collect_benchmark_account_candidate(
        BenchmarkCandidateRequest(
            query="田永成 医美",
            actor_label="田永成",
            max_posts=5,
        ),
        router=router,
        context=_context(),
        captured_at=NOW,
    )

    assert snapshot.coverage.returned_count == 1
    assert snapshot.coverage.has_more is True
    assert snapshot.route_receipt["pages_succeeded"] == 1
    assert snapshot.route_receipt["stopped_reason"] == "provider_error_after_partial_result"
    assert any("provider failure" in warning for warning in snapshot.warnings)
    assert "provider-log-id" not in snapshot.model_dump_json()


@pytest.mark.asyncio
async def test_candidate_collection_rejects_first_page_failure_without_fabricating_an_empty_sample() -> None:
    async def handler(arguments: dict[str, Any], context: CapabilityContext) -> dict[str, Any]:
        del context
        return {
            "error": "Douyin video search error 28001018",
            "message": "应用未获得该能力",
            "query": arguments["query"],
        }

    router = DomainRouter(
        load_official_catalog(),
        handlers={"search.video_search": handler},
    )

    with pytest.raises(BenchmarkCandidateCollectionError, match="before any page"):
        await collect_benchmark_account_candidate(
            BenchmarkCandidateRequest(
                query="雪茄馆",
                actor_label="目标账号",
            ),
            router=router,
            context=_context(),
            captured_at=NOW,
        )


@pytest.mark.asyncio
async def test_candidate_snapshot_seals_as_candidate_evidence_not_formal_benchmark() -> None:
    async def handler(arguments: dict[str, Any], context: CapabilityContext) -> dict[str, Any]:
        del context
        return _page(
            arguments,
            cursor=0,
            has_more=False,
            search_id="search-session-3",
            results=[_video("7", nickname="海鲜老板")],
        )

    snapshot = await collect_benchmark_account_candidate(
        BenchmarkCandidateRequest(
            query="海鲜老板 饮食文化",
            actor_label="海鲜老板",
        ),
        router=DomainRouter(
            load_official_catalog(),
            handlers={"search.video_search": handler},
        ),
        context=_context(),
        captured_at=NOW,
    )
    artifact = seal_benchmark_account_candidate(
        project=ProjectRef(owner_user_id="user-1", project_id="project-1"),
        snapshot=snapshot,
        source_thread_id="thread-1",
        source_run_id="run-1",
    )

    assert artifact.artifact_type == "evidence_snapshot"
    assert artifact.evidence_role == "benchmark_account_candidate"
    assert artifact.account is None
    assert artifact.payload["coverage"]["returned_count"] == 1
    assert any("not a BenchmarkSnapshot" in item for item in artifact.payload["limitations"])


@pytest.mark.asyncio
async def test_candidate_artifact_is_idempotently_persisted_and_projects_a_bounded_sample(
    tmp_path,
) -> None:
    async def handler(arguments: dict[str, Any], context: CapabilityContext) -> dict[str, Any]:
        del context
        return _page(
            arguments,
            cursor=0,
            has_more=False,
            search_id="search-session-4",
            results=[
                {
                    **_video(
                        str(index),
                        nickname="礼物研究所",
                        title=f"第 {index} 条人情往来观察",
                    ),
                    "content": "人与人相处的分寸" * 50,
                }
                for index in range(1, 20)
            ],
        )

    snapshot = await collect_benchmark_account_candidate(
        BenchmarkCandidateRequest(
            query="礼物研究所 人情往来",
            actor_label="礼物研究所",
            max_posts=19,
        ),
        router=DomainRouter(
            load_official_catalog(),
            handlers={"search.video_search": handler},
        ),
        context=_context(),
        captured_at=NOW,
    )
    project = ProjectRef(owner_user_id="user-1", project_id="project-1")
    artifact = seal_benchmark_account_candidate(
        project=project,
        snapshot=snapshot,
        source_thread_id="thread-1",
        source_run_id="run-1",
    )

    await init_engine_from_config(DatabaseConfig(backend="sqlite", sqlite_dir=str(tmp_path)))
    try:
        session_factory = get_session_factory()
        assert session_factory is not None
        repository = IncubationLedgerRepository(session_factory)
        await repository.create_project(project, display_name="Golden Gift")
        first = await repository.put_artifact(artifact)
        replay = await repository.put_artifact(artifact)
        stored = await repository.list_artifacts(
            project,
            evidence_role="benchmark_account_candidate",
        )
    finally:
        await close_engine()

    projection = snapshot.to_lead_projection(max_bytes=4_000)
    encoded = json.dumps(
        projection,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")

    assert first == replay == artifact
    assert stored == [artifact]
    assert len(encoded) <= 4_000
    assert projection["evidence_role"] == "benchmark_account_candidate"
    assert projection["projection"]["omitted_items"] > 0
    assert projection["projection"]["truncated"] is True
