import json
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from deerflow.community.douyin_openapi.evidence import (
    build_video_search_evidence_snapshot,
    seal_video_search_evidence,
)
from deerflow.incubation import ProjectRef

NOW = datetime(2026, 8, 16, 14, 0, tzinfo=UTC)


def _domain_result(*, evidence_role: str = "topic_evidence") -> dict:
    return {
        "data": {
            "query": "人情往来 送礼",
            "provider": "douyin_open_platform",
            "evidence_role": evidence_role,
            "total_results": 1,
            "cursor": 2,
            "has_more": True,
            "search_id": "search-session-id",
            "results": [
                {
                    "title": "送礼为什么最怕用力过猛",
                    "url": "https://www.douyin.com/video/7471252140422401337",
                    "content": "礼物真正传递的是关系中的分寸。",
                    "source_type": "douyin_video",
                    "item_id": "7471252140422401337",
                    "nickname": "礼物研究所",
                    "create_time": 1739536450,
                    "digg_count": 9254,
                }
            ],
        },
        "warnings": [],
        "metadata": {
            "domain": "search",
            "child_tool": "video_search",
            "manifest_version": "manifest-v1",
            "catalog_version": "catalog-v1",
        },
    }


def test_official_video_search_becomes_bounded_topic_evidence() -> None:
    snapshot = build_video_search_evidence_snapshot(
        _domain_result(),
        requested_count=5,
        captured_at=NOW,
    )

    assert snapshot.evidence_role == "topic_evidence"
    assert snapshot.provider == "douyin_open_platform"
    assert snapshot.collection_method == "official_openapi"
    assert snapshot.coverage.requested_count == 5
    assert snapshot.coverage.returned_count == 1
    assert snapshot.coverage.has_more is True
    assert snapshot.coverage.population_scope == "public_video_search_results"
    assert snapshot.items[0].source_ref == "douyin:video:7471252140422401337"
    assert snapshot.items[0].public_uri == "https://www.douyin.com/video/7471252140422401337"
    assert snapshot.items[0].provenance == "observed"
    assert snapshot.items[0].observed_values == {
        "item_id": "7471252140422401337",
        "create_time": 1739536450,
        "digg_count": 9254,
    }
    assert any("not a benchmark-account analysis" in item for item in snapshot.limitations)


def test_topic_evidence_artifact_keeps_route_receipt_without_raw_credentials() -> None:
    artifact = seal_video_search_evidence(
        project=ProjectRef(owner_user_id="user-1", project_id="project-1"),
        domain_result=_domain_result(),
        requested_count=5,
        captured_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-1",
    )

    assert artifact.artifact_type == "evidence_snapshot"
    assert artifact.evidence_role == "topic_evidence"
    assert artifact.payload["route_receipt"] == {
        "domain": "search",
        "child_tool": "video_search",
        "manifest_version": "manifest-v1",
        "catalog_version": "catalog-v1",
        "search_id": "search-session-id",
    }
    raw = artifact.model_dump_json()
    assert "client_secret" not in raw
    assert "access_token" not in raw
    assert "cookie" not in raw


def test_video_search_adapter_rejects_role_or_route_confusion() -> None:
    with pytest.raises(ValidationError):
        build_video_search_evidence_snapshot(
            _domain_result(evidence_role="benchmark_evidence"),
            requested_count=5,
            captured_at=NOW,
        )

    wrong_route = _domain_result()
    wrong_route["metadata"]["child_tool"] = "experience_search"
    with pytest.raises(ValueError, match="video_search route"):
        build_video_search_evidence_snapshot(
            wrong_route,
            requested_count=5,
            captured_at=NOW,
        )


def test_video_search_adapter_rejects_unreviewed_or_inconsistent_receipts() -> None:
    extra_raw_field = _domain_result()
    extra_raw_field["data"]["results"][0]["temporary_cover"] = "https://signed.example/cover"
    with pytest.raises(ValidationError):
        build_video_search_evidence_snapshot(
            extra_raw_field,
            requested_count=5,
            captured_at=NOW,
        )

    wrong_count = _domain_result()
    wrong_count["data"]["total_results"] = 9
    with pytest.raises(ValueError, match="total_results"):
        build_video_search_evidence_snapshot(
            wrong_count,
            requested_count=5,
            captured_at=NOW,
        )


def test_lead_projection_is_bounded_and_reports_omitted_evidence() -> None:
    domain_result = _domain_result()
    domain_result["data"]["results"] = [
        {
            "title": f"第 {index} 条送礼观察",
            "url": f"https://www.douyin.com/video/{index}",
            "content": "人与人相处需要看关系、场合和分寸。" * 120,
            "source_type": "douyin_video",
            "item_id": str(index),
            "nickname": "礼物研究所",
            "create_time": 1739536450 + index,
            "digg_count": 9000 + index,
        }
        for index in range(20)
    ]
    domain_result["data"]["total_results"] = 20
    snapshot = build_video_search_evidence_snapshot(
        domain_result,
        requested_count=20,
        captured_at=NOW,
    )

    projection = snapshot.to_lead_projection(max_bytes=4_000)
    raw = json.dumps(projection, ensure_ascii=False, separators=(",", ":")).encode()

    assert len(raw) <= 4_000
    assert projection["evidence_role"] == "topic_evidence"
    assert projection["snapshot_sha256"]
    assert projection["route_receipt_sha256"]
    assert projection["projection"]["total_items"] == 20
    assert projection["projection"]["omitted_items"] > 0
    assert projection["projection"]["truncated"] is True
    assert projection["items"]
