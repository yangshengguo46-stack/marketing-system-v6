from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import pytest

from deerflow.incubation import generate_incubation_judgment as exported_generate_incubation_judgment
from deerflow.incubation.benchmark import (
    BenchmarkCoverageReceipt,
    BenchmarkPostObservation,
    BenchmarkProfileObservation,
    BenchmarkRouteReceipt,
    BenchmarkSnapshot,
    seal_benchmark_snapshot,
)
from deerflow.incubation.contracts import ArtifactEnvelope, ProjectRef
from deerflow.incubation.evidence import (
    EvidenceCoverageReceipt,
    EvidenceItem,
    EvidenceSnapshot,
    seal_evidence_snapshot,
)
from deerflow.incubation.judgment import (
    IncubationBrief,
    seal_incubation_brief,
)
from deerflow.incubation.judgment_runtime import (
    INCUBATION_JUDGMENT_SYSTEM_PROMPT,
    MAX_JUDGMENT_MODEL_INPUT_BYTES,
    AccountStrategyProposalDraft,
    IncubationJudgmentModelError,
    generate_incubation_judgment,
)

NOW = datetime(2026, 8, 17, 20, 0, tzinfo=UTC)
PROJECT = ProjectRef(owner_user_id="user-1", project_id="golden-gift")


def test_judgment_runtime_is_exported_from_the_incubation_package() -> None:
    assert exported_generate_incubation_judgment is generate_incubation_judgment


def _brief_artifact(*, project: ProjectRef = PROJECT) -> ArtifactEnvelope:
    return seal_incubation_brief(
        project=project,
        brief=IncubationBrief(
            subject_expression="我是做黄金礼品的，我要怎么起号？",
            unknowns=("尚不知道用户是否愿意出镜。",),
        ),
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-1",
    )


def _content_world_artifact(*, project: ProjectRef = PROJECT) -> ArtifactEnvelope:
    return ArtifactEnvelope.seal(
        project=project,
        artifact_type="content_map_candidate",
        version=1,
        payload={
            "content_map_version_id": "map-gift-relations-v1",
            "content_root": "礼与人与人相处",
            "audience_territory": "关心人情、礼节和关系判断的人",
            "editorial_promise": "借具体的人、事、时间和地方理解人与人怎样相处。",
            "recurring_lens": "从一件具体的礼或关系事件进入。",
            "drift_boundaries": ["不退回黄金产品目录。"],
            "dimensions": [],
        },
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-1",
    )


def _evidence_artifact(
    *,
    artifact_type: str,
    evidence_role: str,
    project: ProjectRef = PROJECT,
    item_count: int = 1,
    excerpt: str = "一份有界证据摘要。",
) -> ArtifactEnvelope:
    if artifact_type == "benchmark_snapshot":
        account_id = "benchmark-account-1"
        snapshot = BenchmarkSnapshot(
            provider="douyin-openapi",
            collection_method="authorized-public-search",
            captured_at=NOW,
            rights_basis="public-account-research",
            requested_url="https://www.douyin.com/user/benchmark-account-1",
            profile=BenchmarkProfileObservation(
                platform="douyin",
                external_account_id=account_id,
                canonical_url="https://www.douyin.com/user/benchmark-account-1",
                display_name="对标账号",
                captured_at=NOW,
            ),
            posts=tuple(
                BenchmarkPostObservation(
                    platform="douyin",
                    external_post_id=f"post-{index}",
                    author_external_account_id=account_id,
                    canonical_url=f"https://www.douyin.com/video/{index}",
                    caption=excerpt,
                    captured_at=NOW,
                )
                for index in range(item_count)
            ),
            coverage=BenchmarkCoverageReceipt(
                population_scope="public account posts",
                requested_count=item_count,
                returned_count=item_count,
                sample_basis="bounded recent public sample",
                limitations=("不能代表账号全部历史。",),
            ),
            route_receipt=BenchmarkRouteReceipt(
                adapter="douyin-openapi",
                capability_version="v2",
            ),
            limitations=("不能直接证明账号定位、受众或成功原因。",),
        )
        return seal_benchmark_snapshot(
            project=project,
            snapshot=snapshot,
            source_thread_id="thread-1",
            source_run_id="run-1",
        )

    snapshot = EvidenceSnapshot(
        provider="authorized-audience-source",
        collection_method="bounded-observation",
        evidence_role=evidence_role,
        captured_at=NOW,
        rights_basis="account-owner-authorization",
        items=tuple(
            EvidenceItem(
                source_ref=f"audience-{index}",
                source_type="audience_observation",
                title=f"受众观察 {index}",
                excerpt=excerpt,
                provenance="observed",
            )
            for index in range(item_count)
        ),
        coverage=EvidenceCoverageReceipt(
            population_scope="authorized audience sample",
            requested_count=item_count,
            returned_count=item_count,
            limitations=("不能代表全部受众。",),
        ),
        limitations=("不能代表全部受众。",),
    )
    return seal_evidence_snapshot(
        project=project,
        snapshot=snapshot,
        source_thread_id="thread-1",
        source_run_id="run-1",
    )


def _judgment_payload(*, basis_ids: tuple[str, ...]) -> dict[str, Any]:
    def route(option_id: str, name: str, form: str) -> dict[str, Any]:
        return {
            "option_id": option_id,
            "name": name,
            "content_subject": f"{name}视角下的人情、礼节和关系判断",
            "business_connection": "礼品从业位置提供观察角度，不把产品当成内容主体。",
            "business_role": "提供黄金礼品解决方案的从业者",
            "account_objective": f"通过{name}建立懂送礼与人情分寸的信任，并承接真实礼品需求",
            "target_people": "正在为具体关系和场合选择礼物的人",
            "target_need": "判断送什么、怎么送才合适且不失分寸",
            "desired_action": "在出现礼品需求时主动咨询用户已有的黄金礼品业务",
            "market_scope": "用户未说明经营地区，首版保留为未知",
            "long_term_promise": "每次借一件具体人情事件讲清人怎样相处。",
            "audience_people": "关心人情、礼节和关系判断的人",
            "recurring_interest": "具体关系如何被安排",
            "account_role": "从礼品生意观察人情的从业者",
            "primary_forms": [form],
            "supporting_forms": [],
            "monetization_path": "先建立长期内容信任，再承接用户已有的礼品服务。",
            "monetization_trust_required": "观众先确认账号懂礼与关系。",
            "rationale": "与已冻结的内容根一致。",
            "basis_artifact_ids": list(basis_ids),
            "confidence": "low",
            "unknowns": ["仍需真实反馈校正。"],
            "resource_requirements": [f"持续生产{form}所需素材"],
            "tradeoffs": [f"{form}的成本待确认"],
        }

    return {
        "content_map_version_id": "map-gift-relations-v1",
        "route_options": [
            route("route_a", "真人故事", "真人出镜口述"),
            route("route_b", "无人素材", "无人素材旁白"),
        ],
        "recommended_option_id": "route_a",
        "unknowns": ["尚无真实受众反馈。"],
    }


@pytest.mark.asyncio
async def test_runtime_binds_exact_brief_world_and_optional_evidence_parents() -> None:
    brief = _brief_artifact()
    world = _content_world_artifact()
    benchmark = _evidence_artifact(
        artifact_type="benchmark_snapshot",
        evidence_role="benchmark_evidence",
    )
    audience = _evidence_artifact(
        artifact_type="evidence_snapshot",
        evidence_role="owned_audience_observation",
    )
    seen: dict[str, object] = {}

    async def structured_model(schema, messages):
        seen["schema"] = schema
        seen["messages"] = messages
        return _judgment_payload(basis_ids=(brief.artifact_id, world.artifact_id, benchmark.artifact_id, audience.artifact_id))

    sealed = await generate_incubation_judgment(
        project=PROJECT,
        brief_artifact=brief,
        content_world_artifact=world,
        structured_model=structured_model,
        benchmark_evidence_artifacts=(benchmark,),
        audience_evidence_artifacts=(audience,),
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-2",
    )

    assert seen["schema"] is AccountStrategyProposalDraft
    assert sealed.artifact_type == "incubation_judgment"
    assert set(sealed.parents) == {
        brief.to_parent_ref(),
        world.to_parent_ref(),
        benchmark.to_parent_ref(),
        audience.to_parent_ref(),
    }
    assert sealed.payload["content_map_version_id"] == "map-gift-relations-v1"

    messages = seen["messages"]
    assert isinstance(messages, tuple)
    prompt_input = messages[1].content
    assert brief.artifact_id in prompt_input
    assert world.artifact_id in prompt_input
    assert benchmark.artifact_id in prompt_input
    assert audience.artifact_id in prompt_input


@pytest.mark.asyncio
async def test_runtime_uses_bounded_evidence_projection_instead_of_full_snapshot() -> None:
    brief = _brief_artifact()
    world = _content_world_artifact()
    audience = _evidence_artifact(
        artifact_type="evidence_snapshot",
        evidence_role="owned_audience_observation",
        item_count=20,
        excerpt="受众原始观察" * 300,
    )
    seen_input = ""

    async def structured_model(schema, messages):
        nonlocal seen_input
        seen_input = messages[1].content
        return _judgment_payload(basis_ids=(brief.artifact_id, world.artifact_id, audience.artifact_id))

    await generate_incubation_judgment(
        project=PROJECT,
        brief_artifact=brief,
        content_world_artifact=world,
        structured_model=structured_model,
        audience_evidence_artifacts=(audience,),
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-2",
    )

    model_input = json.loads(seen_input)
    projection = model_input["audience_evidence"][0]["projection"]
    assert len(seen_input.encode("utf-8")) <= MAX_JUDGMENT_MODEL_INPUT_BYTES
    assert projection["projection"]["total_items"] == 20
    assert projection["projection"]["omitted_items"] > 0
    assert "payload" not in model_input["audience_evidence"][0]


@pytest.mark.asyncio
async def test_runtime_rejects_an_evidence_role_wrapped_in_the_wrong_artifact_type() -> None:
    wrong_type = ArtifactEnvelope.seal(
        project=PROJECT,
        artifact_type="generic_report",
        version=1,
        payload={"summary": "not a BenchmarkSnapshot"},
        evidence_role="benchmark_evidence",
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-1",
    )

    async def structured_model(schema, messages):
        raise AssertionError("model must not run")

    with pytest.raises(ValueError, match="benchmark_snapshot"):
        await generate_incubation_judgment(
            project=PROJECT,
            brief_artifact=_brief_artifact(),
            content_world_artifact=_content_world_artifact(),
            structured_model=structured_model,
            benchmark_evidence_artifacts=(wrong_type,),
            created_at=NOW,
            source_thread_id="thread-1",
            source_run_id="run-2",
        )


@pytest.mark.asyncio
async def test_runtime_rejects_cross_project_parent_before_calling_model() -> None:
    other_project = ProjectRef(owner_user_id="user-2", project_id="golden-gift")
    called = False

    async def structured_model(schema, messages):
        nonlocal called
        called = True
        return _judgment_payload(basis_ids=())

    with pytest.raises(ValueError, match="brief parent project"):
        await generate_incubation_judgment(
            project=PROJECT,
            brief_artifact=_brief_artifact(project=other_project),
            content_world_artifact=_content_world_artifact(),
            structured_model=structured_model,
            created_at=NOW,
            source_thread_id="thread-1",
            source_run_id="run-2",
        )

    assert called is False


@pytest.mark.asyncio
async def test_runtime_surfaces_structured_model_failure_without_sealing() -> None:
    provider_error = RuntimeError("provider unavailable")

    async def failing_model(schema, messages):
        raise provider_error

    with pytest.raises(IncubationJudgmentModelError, match="structured model") as exc_info:
        await generate_incubation_judgment(
            project=PROJECT,
            brief_artifact=_brief_artifact(),
            content_world_artifact=_content_world_artifact(),
            structured_model=failing_model,
            created_at=NOW,
            source_thread_id="thread-1",
            source_run_id="run-2",
        )

    assert exc_info.value.__cause__ is provider_error


@pytest.mark.asyncio
async def test_runtime_rejects_an_unknown_only_result_instead_of_hiding_missing_routes() -> None:
    async def unknown_only_model(schema, messages):
        return {
            "content_map_version_id": "map-gift-relations-v1",
            "unknowns": ["用户可持续投入的出镜与制作资源仍未知。"],
            "alternatives": ["待资源确认后再在口述与图文之间判断。"],
        }

    with pytest.raises(IncubationJudgmentModelError, match="invalid incubation judgment"):
        await generate_incubation_judgment(
            project=PROJECT,
            brief_artifact=_brief_artifact(),
            content_world_artifact=_content_world_artifact(),
            structured_model=unknown_only_model,
            created_at=NOW,
            source_thread_id="thread-1",
            source_run_id="run-2",
        )


@pytest.mark.asyncio
async def test_monetization_stays_in_judgment_and_cannot_rewrite_content_map() -> None:
    brief = _brief_artifact()
    world = _content_world_artifact()
    frozen_world = world.model_dump(mode="json")

    async def monetization_model(schema, messages):
        assert "变现路径不属于内容地图" in messages[0].content
        return _judgment_payload(basis_ids=(brief.artifact_id, world.artifact_id))

    sealed = await generate_incubation_judgment(
        project=PROJECT,
        brief_artifact=brief,
        content_world_artifact=world,
        structured_model=monetization_model,
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-2",
    )

    assert world.model_dump(mode="json") == frozen_world
    assert "monetization" not in world.payload
    assert sealed.payload["monetization"][0]["path"].startswith("先建立")
    assert "不要求固定模板" in INCUBATION_JUDGMENT_SYSTEM_PROMPT
    assert "不要求数字配额" in INCUBATION_JUDGMENT_SYSTEM_PROMPT
    assert "不要求实验" in INCUBATION_JUDGMENT_SYSTEM_PROMPT
    assert "业务身份不等于资源所有权" in INCUBATION_JUDGMENT_SYSTEM_PROMPT
    assert "已知资源" in INCUBATION_JUDGMENT_SYSTEM_PROMPT
    assert "resource_requirements" in INCUBATION_JUDGMENT_SYSTEM_PROMPT
