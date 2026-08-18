from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from deerflow.content_intelligence import (
    ComprehensionRecord,
    ContentIntelligenceBundle,
    ContentWorldView,
    SourceItem,
)
from deerflow.incubation import (
    ArtifactEnvelope,
    ProjectRef,
    prepare_account_strategy,
    select_current_account_strategy,
)

NOW = datetime(2026, 8, 18, 8, 0, tzinfo=UTC)
PROJECT = ProjectRef(owner_user_id="user-1", project_id="golden-gift")


class _MemoryRepository:
    def __init__(self) -> None:
        self.artifacts: dict[str, ArtifactEnvelope] = {}

    async def put_artifact(self, artifact: ArtifactEnvelope) -> ArtifactEnvelope:
        self.artifacts[artifact.artifact_id] = artifact
        return artifact

    async def list_artifacts(
        self,
        project: ProjectRef,
        *,
        artifact_type: str | None = None,
        evidence_role: str | None = None,
    ) -> list[ArtifactEnvelope]:
        return [artifact for artifact in self.artifacts.values() if artifact.project == project and (artifact_type is None or artifact.artifact_type == artifact_type) and (evidence_role is None or artifact.evidence_role == evidence_role)]


def _bundle() -> ContentIntelligenceBundle:
    record = ComprehensionRecord(
        record_id="record-golden-gift",
        subject_expression="我是做黄金礼品的",
        sources=(
            SourceItem(
                source_id="source-user",
                kind="user_statement",
                content="我是做黄金礼品的",
            ),
        ),
    )
    world = ContentWorldView(
        record_id=record.record_id,
        source_object="黄金礼品",
        content_entry="送礼",
        content_root="人与人之间的相处与人情世故",
        root_rationale="礼品可经由礼进入人与人如何相处的候选内容世界。",
        editorial_promise="借具体人物与事件理解关系、分寸与秩序。",
        recurring_lens="从人物、时间、地点和事件观察人与人如何相处。",
    )
    return ContentIntelligenceBundle(record=record, content_world=world)


def _route_payload(
    option_id: str,
    name: str,
    form: str,
    *,
    basis_ids: tuple[str, ...],
) -> dict[str, object]:
    return {
        "option_id": option_id,
        "name": name,
        "content_subject": f"{name}视角下的人情、礼节和关系判断",
        "business_connection": "礼品从业位置提供观察角度，不把产品当成内容主体。",
        "long_term_promise": "用具体人物与事件理解人情与礼。",
        "audience_people": "关心人情与礼节的人",
        "recurring_interest": "人与人如何相处",
        "account_role": "从礼品生意观察人情的从业者",
        "primary_forms": [form],
        "supporting_forms": [],
        "monetization_path": None,
        "monetization_trust_required": None,
        "rationale": "与已知业务和候选地图相符。",
        "basis_artifact_ids": list(basis_ids),
        "confidence": "low",
        "unknowns": ["持续产能未确认。"],
        "resource_requirements": [],
        "tradeoffs": [],
    }


def _proposal_payload(
    *,
    map_version: str,
    basis_ids: tuple[str, ...],
) -> dict[str, object]:
    return {
        "content_map_version_id": map_version,
        "route_options": [
            _route_payload("route_a", "真人故事", "真人出镜口述", basis_ids=basis_ids),
            _route_payload("route_b", "AI情境叙事", "AI情景剧", basis_ids=basis_ids),
        ],
        "recommended_option_id": "route_a",
        "unknowns": ["尚未取得真实受众反馈。"],
    }


@pytest.mark.asyncio
async def test_account_strategy_reuses_identical_inputs_and_versions_real_changes() -> None:
    repository = _MemoryRepository()
    bundle = _bundle()
    map_version = bundle.content_world.content_map_version_id()
    model_calls = 0
    first_artifact_id: str | None = None

    async def structured_model(schema, messages):
        nonlocal model_calls
        model_calls += 1
        model_input = json.loads(messages[1].content)
        basis_ids = tuple(model_input["allowed_basis_artifact_ids"][:2])
        if model_calls == 1:
            return _proposal_payload(map_version=map_version, basis_ids=basis_ids)
        assert first_artifact_id is not None
        return _proposal_payload(map_version=map_version, basis_ids=basis_ids)

    first = await prepare_account_strategy(
        project=PROJECT,
        repository=repository,
        bundle=bundle,
        verbatim_user_request="我是做黄金礼品的，我要怎么起号？",
        structured_model=structured_model,
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-1",
    )
    first_artifact_id = first.judgment_artifact.artifact_id

    repeated = await prepare_account_strategy(
        project=PROJECT,
        repository=repository,
        bundle=bundle,
        verbatim_user_request="我是做黄金礼品的，我要怎么起号？",
        structured_model=structured_model,
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-2",
    )

    revised = await prepare_account_strategy(
        project=PROJECT,
        repository=repository,
        bundle=bundle,
        verbatim_user_request="我是做黄金礼品的，希望账号长期建立信任。",
        structured_model=structured_model,
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-3",
    )

    assert first.reused is False
    assert repeated.reused is True
    assert repeated.judgment_artifact.artifact_id == first.judgment_artifact.artifact_id
    assert revised.judgment.revision_number == 2
    assert revised.judgment.supersedes_judgment_artifact_id == first.judgment_artifact.artifact_id
    assert first.judgment_artifact.to_parent_ref() in revised.judgment_artifact.parents
    assert model_calls == 2
    assert repository.artifacts[first.judgment_artifact.artifact_id] == first.judgment_artifact


def test_current_account_strategy_can_be_resolved_for_the_exact_candidate_map() -> None:
    project = PROJECT
    first = ArtifactEnvelope.seal(
        project=project,
        artifact_type="incubation_judgment",
        version=1,
        payload={
            "revision_number": 1,
            "content_map_version_id": "map-1",
            "monetization": [],
            "unknowns": [],
            "alternatives": [],
        },
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-1",
    )

    selected = select_current_account_strategy(
        [first],
        content_map_version_id="map-1",
    )

    assert selected is not None
    assert selected.judgment_artifact == first
    assert select_current_account_strategy([first], content_map_version_id="map-2") is None
