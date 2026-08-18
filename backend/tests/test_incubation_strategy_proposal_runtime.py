from __future__ import annotations

from datetime import UTC, datetime

import pytest

from deerflow.incubation import ArtifactEnvelope, ProjectRef
from deerflow.incubation.judgment import IncubationBrief, seal_incubation_brief
from deerflow.incubation.judgment_runtime import (
    AccountStrategyProposalDraft,
    IncubationJudgmentModelError,
    generate_incubation_judgment,
)

NOW = datetime(2026, 8, 18, 11, 0, tzinfo=UTC)
PROJECT = ProjectRef(owner_user_id="user-1", project_id="project-1")


def _brief() -> ArtifactEnvelope:
    return seal_incubation_brief(
        project=PROJECT,
        brief=IncubationBrief(
            subject_expression="我是做宠物殡葬的，我要怎么起号？",
            unknowns=("用户是否愿意出镜仍未知。",),
        ),
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-1",
    )


def _world() -> ArtifactEnvelope:
    return ArtifactEnvelope.seal(
        project=PROJECT,
        artifact_type="content_map_candidate",
        version=1,
        payload={
            "content_map_version_id": "map-companion-v1",
            "content_root": "人与伴侣动物如何告别",
            "editorial_promise": "用具体告别经历理解陪伴、失去与纪念。",
            "recurring_lens": "从人、动物、时间、地方和事件展开。",
            "drift_boundaries": ["不把服务流程当成唯一内容。"],
        },
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-1",
    )


def _route(option_id: str, name: str, form: str, *, basis_ids: tuple[str, ...]) -> dict[str, object]:
    return {
        "option_id": option_id,
        "name": name,
        "content_subject": f"{name}中的陪伴、告别与纪念",
        "business_connection": "用户的宠物殡葬从业经历提供观察位置，服务只在需要时承接。",
        "long_term_promise": "每次讲清一次具体告别里的陪伴与选择。",
        "audience_people": "正在养宠、经历失去或关心动物陪伴的人",
        "recurring_interest": "如何理解陪伴、告别和纪念",
        "account_role": "从真实服务现场观察人与宠物关系的从业者",
        "primary_forms": [form],
        "supporting_forms": [],
        "monetization_path": "先建立告别和纪念的信任，再承接用户已有服务。",
        "monetization_trust_required": "观众相信账号能理解失去者的感受且不消费悲伤。",
        "rationale": "路线与业务位置和候选内容地图一致。",
        "basis_artifact_ids": list(basis_ids),
        "confidence": "low",
        "unknowns": ["真实表现能力和持续产能未确认。"],
        "resource_requirements": [f"持续生产{form}需要的素材"],
        "tradeoffs": [f"{form}的制作成本待确认"],
    }


@pytest.mark.asyncio
async def test_runtime_uses_a_flat_proposal_draft_and_code_owns_confirmation_state() -> None:
    brief = _brief()
    world = _world()
    basis_ids = (brief.artifact_id, world.artifact_id)

    async def structured_model(schema, messages):
        assert schema is AccountStrategyProposalDraft
        assert "selected_option_id" not in schema.model_fields
        assert "revision_number" not in schema.model_fields
        return {
            "content_map_version_id": "map-companion-v1",
            "route_options": [
                _route("route_a", "真人纪录", "真人纪录叙事", basis_ids=basis_ids),
                _route("route_b", "无人素材", "无人素材旁白", basis_ids=basis_ids),
            ],
            "recommended_option_id": "route_a",
            "unknowns": ["尚无正式对标和受众证据。"],
        }

    sealed = await generate_incubation_judgment(
        project=PROJECT,
        brief_artifact=brief,
        content_world_artifact=world,
        structured_model=structured_model,
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-2",
    )

    assert sealed.payload["decision_status"] == "proposed"
    assert sealed.payload["selected_option_id"] is None
    assert sealed.payload["recommended_option_id"] == "route_a"
    assert sealed.payload["positioning"]["decision"] == "真人纪录中的陪伴、告别与纪念"
    assert sealed.payload["route_options"][0]["business_connection"].startswith("用户的宠物殡葬从业经历")
    assert sealed.payload["presentation"]["primary_forms"] == ["真人纪录叙事"]
    assert len(sealed.payload["route_options"]) == 2


@pytest.mark.asyncio
async def test_runtime_rejects_a_single_route_instead_of_padding_it() -> None:
    brief = _brief()
    world = _world()

    async def structured_model(schema, messages):
        return {
            "content_map_version_id": "map-companion-v1",
            "route_options": [
                _route(
                    "route_a",
                    "真人纪录",
                    "真人纪录叙事",
                    basis_ids=(brief.artifact_id, world.artifact_id),
                )
            ],
            "recommended_option_id": "route_a",
            "unknowns": [],
        }

    with pytest.raises(IncubationJudgmentModelError, match="invalid incubation judgment"):
        await generate_incubation_judgment(
            project=PROJECT,
            brief_artifact=brief,
            content_world_artifact=world,
            structured_model=structured_model,
            created_at=NOW,
            source_thread_id="thread-1",
            source_run_id="run-2",
        )
