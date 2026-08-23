from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from deerflow.incubation.ark_generation import (
    ArkTextToVideoOperationDraft,
    ArkTextToVideoParameters,
    prepare_ark_text_to_video_operation,
)
from deerflow.incubation.contracts import ArtifactEnvelope, ProjectRef

NOW = datetime(2026, 8, 22, 10, 0, tzinfo=UTC)
PROJECT = ProjectRef(owner_user_id="user-1", project_id="project-1")


def _artifact(
    *,
    artifact_type: str,
    payload: dict[str, object],
    parents: tuple = (),
) -> ArtifactEnvelope:
    return ArtifactEnvelope.seal(
        project=PROJECT,
        artifact_type=artifact_type,
        version=1,
        payload=payload,
        parents=parents,
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-1",
    )


def _production_plan(
    *,
    asset_kind: str = "video",
    asset_source: str = "to_create",
    action_kind: str = "media_generation",
    extra_action: bool = False,
    extra_asset: bool = False,
    extra_step: bool = False,
    status: str = "ready",
    retain_exact_parents: bool = True,
) -> ArtifactEnvelope:
    adapted = _artifact(
        artifact_type="adapted_draft",
        payload={"adapted_body_sha256": "a" * 64},
    )
    decision = _artifact(
        artifact_type="format_decision",
        payload={"selected_format": {"kind": "material_only", "custom_name": None}},
    )
    assets: list[dict[str, object]] = [
        {
            "asset_id": "asset-generated-video",
            "kind": asset_kind,
            "purpose": "把已确定的适配稿生成为一条竖屏视频。",
            "source": asset_source,
            "basis_artifact_ids": [],
        }
    ]
    if extra_asset:
        assets.append(
            {
                "asset_id": "asset-second",
                "kind": "video",
                "purpose": "不应进入 V1 的第二个资产。",
                "source": "to_create",
                "basis_artifact_ids": [],
            }
        )
    actions: list[dict[str, object]] = [
        {
            "action_id": "action-generate-video",
            "kind": action_kind,
            "instruction": "仅将已定表达翻译为文生视频画面。",
            "asset_ids": ["asset-generated-video"],
        }
    ]
    if extra_action:
        actions.append(
            {
                "action_id": "action-second",
                "kind": "media_generation",
                "instruction": "不应进入 V1 的第二个生成动作。",
                "asset_ids": ["asset-generated-video"],
            }
        )
    steps: list[dict[str, object]] = [
        {
            "step_id": "step-generated-video",
            "instruction": "把生成结果放入已定成片位置。",
            "input_asset_ids": ["asset-generated-video"],
        }
    ]
    if extra_step:
        steps.append(
            {
                "step_id": "step-second",
                "instruction": "不应进入 V1 的第二个装配步骤。",
                "input_asset_ids": ["asset-generated-video"],
            }
        )
    parents = (adapted.to_parent_ref(), decision.to_parent_ref()) if retain_exact_parents else ()
    return _artifact(
        artifact_type="production_plan",
        payload={
            "status": status,
            "asset_requirements": assets,
            "production_actions": actions,
            "assembly_steps": steps,
            "resource_gaps": [],
            "unknowns": [],
            "limitations": ["不改动上游选题和表达。"],
            "narrative_execution_hint": None,
            "adapted_draft_ref": adapted.to_parent_ref().model_dump(mode="json"),
            "adapted_body_sha256": "a" * 64,
            "format_decision_ref": decision.to_parent_ref().model_dump(mode="json"),
            "selected_format": {"kind": "material_only", "custom_name": None},
            "user_material_refs": [],
        },
        parents=parents,
    )


def _draft(**updates: object) -> ArkTextToVideoOperationDraft:
    values: dict[str, object] = {
        "operation_id": "ark-video-1",
        "production_action_id": "action-generate-video",
        "plan_asset_id": "asset-generated-video",
        "assembly_step_id": "step-generated-video",
        "prompt": "清晨的桌面上，一本深蓝色笔记本被缓慢打开，镜头轻微推近。",
        "model": "doubao-seedance-complete-version",
        "parameters": {
            "ratio": "9:16",
            "resolution": "720p",
            "duration": 5,
            "camera_fixed": True,
        },
    }
    values.update(updates)
    return ArkTextToVideoOperationDraft.model_validate(values)


def test_prepare_operation_binds_one_exact_plan_action_asset_and_step() -> None:
    plan = _production_plan()

    operation = prepare_ark_text_to_video_operation(
        production_plan_artifact=plan,
        draft=_draft(),
    )

    assert operation.production_plan_ref == plan.to_parent_ref()
    assert operation.production_action_id == "action-generate-video"
    assert operation.plan_asset_id == "asset-generated-video"
    assert operation.assembly_step_id == "step-generated-video"
    assert operation.parameters.duration == 5
    assert len(operation.operation_sha256) == 64
    assert operation == operation.model_validate(operation.model_dump(mode="json"))


@pytest.mark.parametrize(
    ("plan_updates", "message"),
    [
        ({"status": "provisional"}, "ready"),
        ({"asset_kind": "image"}, "video asset"),
        ({"asset_source": "to_capture"}, "to_create"),
        ({"action_kind": "capture_video"}, "media_generation"),
        ({"extra_action": True}, "exactly one production action"),
        ({"extra_asset": True}, "exactly one asset"),
        ({"extra_step": True}, "exactly one assembly step"),
        ({"retain_exact_parents": False}, "exact parents"),
    ],
)
def test_prepare_operation_rejects_any_plan_outside_the_v1_vertical(
    plan_updates: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        prepare_ark_text_to_video_operation(
            production_plan_artifact=_production_plan(**plan_updates),
            draft=_draft(),
        )


def test_prepare_operation_rejects_a_non_exact_lineage_selector() -> None:
    with pytest.raises(ValueError, match="exact production action"):
        prepare_ark_text_to_video_operation(
            production_plan_artifact=_production_plan(),
            draft=_draft(production_action_id="action-other"),
        )


@pytest.mark.parametrize(
    "forbidden_field",
    [
        "input",
        "reference_materials",
        "api_key",
        "base_url",
        "callback_url",
        "extra_body",
        "force",
        "save_to",
    ],
)
def test_operation_contract_forbids_execution_locators_and_escape_hatches(
    forbidden_field: str,
) -> None:
    values = _draft().model_dump(mode="python")
    values[forbidden_field] = "forbidden"

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ArkTextToVideoOperationDraft.model_validate(values)


@pytest.mark.parametrize(
    "prompt",
    [
        "使用 https://example.test/reference.mp4 作为参考。",
        "使用 s3://private-bucket/reference.mp4 作为参考。",
        "读取 /Users/alice/reference.mp4 后生成。",
        "读取 /mnt/user-data/uploads/reference.mp4 后生成。",
        r"读取 C:\\Users\\alice\\reference.mp4 后生成。",
        "Authorization: Bearer secret-token-value",
        "api_key=ark-super-secret-value",
        "api key is provider-super-secret-value",
        "访问密钥是 provider-super-secret-value",
        "密钥是 ark-super-secret-value",
        "AbCdEf0123456789AbCdEf0123456789",
        "用 @reference.mp4 作为首帧。",
    ],
)
def test_operation_prompt_cannot_smuggle_locators_credentials_or_reference_files(
    prompt: str,
) -> None:
    with pytest.raises(ValidationError, match="execution-only material") as caught:
        _draft(prompt=prompt)

    assert prompt not in str(caught.value)
    assert prompt not in repr(caught.value)


@pytest.mark.parametrize(
    "credential",
    [
        "api_key:provider-super-secret-value",
        "AbCdEf0123456789AbCdEf0123456789",
    ],
)
def test_model_field_cannot_be_used_as_an_ark_credential_channel(
    credential: str,
) -> None:

    with pytest.raises(ValidationError, match="credential") as caught:
        _draft(model=credential)

    assert credential not in str(caught.value)


def test_operation_requires_an_explicit_model_before_hashing_or_approval() -> None:
    values = _draft().model_dump(mode="python")
    values.pop("model")

    with pytest.raises(ValidationError, match="model"):
        ArkTextToVideoOperationDraft.model_validate(values)


@pytest.mark.parametrize("missing_parameter", ["ratio", "resolution", "duration"])
def test_operation_requires_explicit_cost_affecting_parameters_before_hashing(
    missing_parameter: str,
) -> None:
    parameters = _draft().parameters.model_dump(mode="python")
    parameters.pop(missing_parameter)

    with pytest.raises(ValidationError, match=missing_parameter):
        _draft(parameters=parameters)


def test_parameter_contract_is_a_closed_whitelist() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ArkTextToVideoParameters.model_validate(
            {
                "duration": 5,
                "callback_url": "https://example.test/callback",
            }
        )
