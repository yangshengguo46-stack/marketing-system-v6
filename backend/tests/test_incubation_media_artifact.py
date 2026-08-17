from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from deerflow.incubation.contracts import ArtifactEnvelope, ProjectRef
from deerflow.incubation.media import MediaKitExecutionReceipt
from deerflow.incubation.media_artifact import (
    MediaArtifact,
    MediaArtifactDraft,
    MediaQCCheck,
    seal_media_artifact,
)

NOW = datetime(2026, 8, 17, 9, 0, tzinfo=UTC)
PROJECT = ProjectRef(owner_user_id="user-1", project_id="project-1")


def _artifact(
    *,
    artifact_type: str,
    payload: dict[str, object],
    project: ProjectRef = PROJECT,
    parents: tuple = (),
    evidence_role: str | None = None,
) -> ArtifactEnvelope:
    return ArtifactEnvelope.seal(
        project=project,
        artifact_type=artifact_type,
        version=1,
        payload=payload,
        parents=parents,
        evidence_role=evidence_role,
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-1",
    )


def _production_plan(
    *,
    user_material: ArtifactEnvelope | None = None,
    adapted_body_sha256: str = "b" * 64,
) -> ArtifactEnvelope:
    adapted_parent = _artifact(
        artifact_type="adapted_draft",
        payload={"adapted_body_sha256": adapted_body_sha256},
    )
    format_parent = _artifact(
        artifact_type="format_decision",
        payload={"selected_format": {"kind": "image_text", "custom_name": None}},
    )
    material_refs = [user_material.to_parent_ref().model_dump(mode="json")] if user_material is not None else []
    asset_requirements = (
        [
            {
                "asset_id": "asset-user-material",
                "kind": "video",
                "purpose": "作为本制作方案的已授权输入素材",
                "source": "existing_user_material",
                "basis_artifact_ids": [user_material.artifact_id],
            }
        ]
        if user_material is not None
        else []
    )
    return _artifact(
        artifact_type="production_plan",
        payload={
            "status": "provisional",
            "asset_requirements": asset_requirements,
            "production_actions": [],
            "assembly_steps": [],
            "resource_gaps": [],
            "unknowns": [],
            "limitations": [],
            "narrative_execution_hint": None,
            "adapted_draft_ref": adapted_parent.to_parent_ref().model_dump(mode="json"),
            "adapted_body_sha256": adapted_body_sha256,
            "format_decision_ref": format_parent.to_parent_ref().model_dump(mode="json"),
            "selected_format": {"kind": "image_text", "custom_name": None},
            "user_material_refs": material_refs,
        },
        parents=(
            adapted_parent.to_parent_ref(),
            format_parent.to_parent_ref(),
            *((user_material.to_parent_ref(),) if user_material is not None else ()),
        ),
    )


def _input_observation(
    *,
    source_hash: str = "d" * 64,
    project: ProjectRef = PROJECT,
    evidence_role: str = "user_material",
) -> ArtifactEnvelope:
    return _artifact(
        artifact_type="media_observation",
        project=project,
        evidence_role=evidence_role,
        payload={
            "source_ref": "user-upload:1",
            "observation_kind": "video_metadata",
            "observed_at": NOW.isoformat().replace("+00:00", "Z"),
            "observation": {
                "format_meta": {
                    "container": "mp4",
                    "duration": 12.5,
                    "size": 2048,
                    "bitrate": None,
                    "md5": None,
                },
                "video_stream_meta": {
                    "codec": "h264",
                    "duration": 12.5,
                    "width": 1080,
                    "height": 1920,
                    "fps": 25,
                    "bitrate": None,
                    "dynamic_range": None,
                },
                "audio_stream_meta": None,
            },
            "execution": {
                "capability_domain": "video",
                "capability_tool": "probe-video-metadata",
                "cli_version": "0.2.0",
                "schema_sha256": "1" * 64,
                "execution_mode": "local",
                "request_sha256": "2" * 64,
                "source_content_sha256": source_hash,
                "client_token_sha256": None,
                "task_id_sha256": None,
                "output_sha256": "3" * 64,
                "completed_at": NOW.isoformat().replace("+00:00", "Z"),
                "cloud_processing_approved": False,
                "fee_authorization_ref": None,
                "status": "completed",
                "limitations": ["The receipt proves deterministic execution lineage; MediaKit observations are not marketing conclusions."],
            },
            "limitations": ["Machine observations may be incomplete or wrong and require downstream evidence review."],
        },
    )


def _execution(*, source_hash: str | None = "d" * 64) -> MediaKitExecutionReceipt:
    return MediaKitExecutionReceipt(
        capability_domain="video",
        capability_tool="compose-video",
        cli_version="0.2.0",
        schema_sha256="4" * 64,
        execution_mode="local",
        request_sha256="5" * 64,
        source_content_sha256=source_hash,
        output_sha256="6" * 64,
        completed_at=NOW,
        cloud_processing_approved=False,
    )


def _draft(**updates: object) -> MediaArtifactDraft:
    values: dict[str, object] = {
        "stage": "final",
        "storage_ref": "artifact://mediakit/user-1/task-1/output.mp4",
        "media_sha256": "7" * 64,
        "mime_type": "video/mp4",
        "size_bytes": 8192,
        "duration_seconds": 12.5,
        "qc_status": "passed_with_warnings",
        "qc_checks": (
            MediaQCCheck(
                name="container-readable",
                status="passed",
                observation="容器与音视频流可以读取。",
            ),
            MediaQCCheck(
                name="subtitle-safe-area",
                status="warning",
                observation="仍需在目标画布做一次字幕安全区人工复核。",
            ),
        ),
        "limitations": ("尚未做平台上传后的转码复核。",),
    }
    values.update(updates)
    return MediaArtifactDraft.model_validate(values)


def test_media_artifact_binds_plan_exact_inputs_execution_and_deterministic_metadata() -> None:
    input_asset = _input_observation()
    plan = _production_plan(user_material=input_asset)
    execution = _execution()

    sealed = seal_media_artifact(
        project=PROJECT,
        draft=_draft(),
        production_plan_artifact=plan,
        input_asset_artifacts=(input_asset,),
        execution=execution,
        source_thread_id="thread-1",
        source_run_id="run-1",
    )

    assert sealed.artifact_type == "media_artifact"
    assert set(sealed.parents) == {
        plan.to_parent_ref(),
        input_asset.to_parent_ref(),
    }
    artifact = MediaArtifact.model_validate(sealed.payload)
    assert artifact.content_sha256 == "b" * 64
    assert artifact.media_sha256 == "7" * 64
    assert artifact.production_plan_ref == plan.to_parent_ref()
    assert artifact.input_assets[0].artifact_ref == input_asset.to_parent_ref()
    assert artifact.input_assets[0].media_sha256 == "d" * 64
    assert len(artifact.input_set_sha256) == 64
    assert artifact.execution == execution
    # MediaKit output_sha256 hashes the execution response; media_sha256 hashes actual bytes.
    assert artifact.execution.output_sha256 != artifact.media_sha256
    assert sealed.created_at == execution.completed_at


def test_media_artifact_rejects_unbound_or_wrong_project_input_assets() -> None:
    source = _input_observation(source_hash="8" * 64)
    plan = _production_plan(user_material=source)

    with pytest.raises(ValueError, match="execution source"):
        seal_media_artifact(
            project=PROJECT,
            draft=_draft(),
            production_plan_artifact=plan,
            input_asset_artifacts=(source,),
            execution=_execution(source_hash="9" * 64),
            source_thread_id="thread-1",
            source_run_id="run-1",
        )

    other_project = ProjectRef(owner_user_id="user-1", project_id="project-2")
    with pytest.raises(ValueError, match="project"):
        seal_media_artifact(
            project=PROJECT,
            draft=_draft(),
            production_plan_artifact=plan,
            input_asset_artifacts=(_input_observation(project=other_project),),
            execution=_execution(),
            source_thread_id="thread-1",
            source_run_id="run-1",
        )

    unapproved = _input_observation(source_hash="9" * 64)
    with pytest.raises(ValueError, match="authorized by the production plan"):
        seal_media_artifact(
            project=PROJECT,
            draft=_draft(),
            production_plan_artifact=_production_plan(),
            input_asset_artifacts=(unapproved,),
            execution=_execution(source_hash="9" * 64),
            source_thread_id="thread-1",
            source_run_id="run-1",
        )


def test_media_artifact_requires_a_supported_content_hashed_input_receipt() -> None:
    plan = _production_plan()
    source_receipt = _artifact(
        artifact_type="media_source_receipt",
        evidence_role="user_material",
        payload={"locator_sha256": "a" * 64},
    )

    with pytest.raises(ValueError, match="media_observation or media_artifact"):
        seal_media_artifact(
            project=PROJECT,
            draft=_draft(),
            production_plan_artifact=plan,
            input_asset_artifacts=(source_receipt,),
            execution=_execution(),
            source_thread_id="thread-1",
            source_run_id="run-1",
        )


def test_media_artifact_input_must_come_from_the_same_production_plan() -> None:
    first_plan = _production_plan(adapted_body_sha256="a" * 64)
    first_output = seal_media_artifact(
        project=PROJECT,
        draft=_draft(
            stage="intermediate",
            storage_ref="artifact://mediakit/user-1/task-1/intermediate.mp4",
            media_sha256="8" * 64,
        ),
        production_plan_artifact=first_plan,
        input_asset_artifacts=(),
        execution=_execution(source_hash=None),
        source_thread_id="thread-1",
        source_run_id="run-1",
    )

    second_plan = _production_plan(adapted_body_sha256="c" * 64)
    with pytest.raises(ValueError, match="same production plan"):
        seal_media_artifact(
            project=PROJECT,
            draft=_draft(),
            production_plan_artifact=second_plan,
            input_asset_artifacts=(first_output,),
            execution=_execution(source_hash="8" * 64),
            source_thread_id="thread-1",
            source_run_id="run-1",
        )


def test_same_plan_intermediate_media_can_feed_the_next_execution_step() -> None:
    plan = _production_plan()
    intermediate = seal_media_artifact(
        project=PROJECT,
        draft=_draft(
            stage="intermediate",
            storage_ref="artifact://mediakit/user-1/task-1/intermediate.mp4",
            media_sha256="8" * 64,
        ),
        production_plan_artifact=plan,
        input_asset_artifacts=(),
        execution=_execution(source_hash=None),
        source_thread_id="thread-1",
        source_run_id="run-1",
    )

    final = seal_media_artifact(
        project=PROJECT,
        draft=_draft(),
        production_plan_artifact=plan,
        input_asset_artifacts=(intermediate,),
        execution=_execution(source_hash="8" * 64),
        source_thread_id="thread-1",
        source_run_id="run-2",
    )

    assert final.payload["input_assets"][0]["artifact_ref"]["artifact_id"] == intermediate.artifact_id


def test_media_artifact_revalidates_plan_parents_and_material_role() -> None:
    material = _input_observation()
    valid_plan = _production_plan(user_material=material)
    missing_parent_plan = _artifact(
        artifact_type="production_plan",
        payload=valid_plan.payload,
    )

    with pytest.raises(ValueError, match="missing an exact declared parent"):
        seal_media_artifact(
            project=PROJECT,
            draft=_draft(),
            production_plan_artifact=missing_parent_plan,
            input_asset_artifacts=(material,),
            execution=_execution(),
            source_thread_id="thread-1",
            source_run_id="run-1",
        )

    wrong_role = _input_observation(evidence_role="topic_evidence")
    forged_plan = _production_plan(user_material=wrong_role)
    with pytest.raises(ValueError, match="user_material evidence role"):
        seal_media_artifact(
            project=PROJECT,
            draft=_draft(),
            production_plan_artifact=forged_plan,
            input_asset_artifacts=(wrong_role,),
            execution=_execution(),
            source_thread_id="thread-1",
            source_run_id="run-1",
        )


def test_media_artifact_can_record_text_derived_output_without_media_input() -> None:
    sealed = seal_media_artifact(
        project=PROJECT,
        draft=_draft(
            stage="intermediate",
            storage_ref="artifact://mediakit/user-1/task-2/title-card.png",
            media_sha256="a" * 64,
            mime_type="image/png",
            duration_seconds=None,
            qc_status="passed",
            qc_checks=(
                MediaQCCheck(
                    name="image-readable",
                    status="passed",
                    observation="图片可以解码。",
                ),
            ),
        ),
        production_plan_artifact=_production_plan(),
        input_asset_artifacts=(),
        execution=_execution(source_hash=None),
        source_thread_id="thread-1",
        source_run_id="run-1",
    )
    assert sealed.payload["input_assets"] == []


@pytest.mark.parametrize(
    ("updates", "error"),
    (
        ({"storage_ref": "/tmp/output.mp4"}, "artifact://"),
        ({"storage_ref": "https://temporary.example/output.mp4"}, "artifact://"),
        ({"mime_type": "not-a-mime"}, "MIME"),
        ({"size_bytes": 0}, "greater than 0"),
        ({"duration_seconds": -1}, "greater than or equal to 0"),
    ),
)
def test_media_output_metadata_rejects_unsafe_or_invalid_values(
    updates: dict[str, object],
    error: str,
) -> None:
    with pytest.raises(ValidationError, match=error):
        _draft(**updates)


@pytest.mark.parametrize(
    ("qc_status", "checks", "error"),
    (
        (
            "passed",
            (MediaQCCheck(name="check", status="warning", observation="有警告"),),
            "passed QC",
        ),
        (
            "passed_with_warnings",
            (MediaQCCheck(name="check", status="failed", observation="失败"),),
            "warning QC",
        ),
        (
            "failed",
            (MediaQCCheck(name="check", status="passed", observation="通过"),),
            "failed QC",
        ),
        (
            "not_run",
            (MediaQCCheck(name="check", status="passed", observation="通过"),),
            "not-run QC",
        ),
    ),
)
def test_qc_summary_must_match_recorded_checks(
    qc_status: str,
    checks: tuple[MediaQCCheck, ...],
    error: str,
) -> None:
    with pytest.raises(ValidationError, match=error):
        _draft(qc_status=qc_status, qc_checks=checks)


def test_media_artifact_contract_has_no_paths_credentials_commands_or_marketing_judgment() -> None:
    forbidden = {
        "local_path",
        "temporary_url",
        "cookie",
        "token",
        "raw_command",
        "api_key",
        "positioning",
        "audience",
        "persona",
        "monetization",
        "topic_title",
        "point_of_view",
        "publish_at",
        "approval",
    }
    assert forbidden.isdisjoint(MediaArtifactDraft.model_fields)
    assert forbidden.isdisjoint(MediaArtifact.model_fields)

    with pytest.raises(ValidationError):
        MediaArtifactDraft.model_validate(
            {
                **_draft().model_dump(mode="json"),
                "local_path": "/tmp/output.mp4",
                "raw_command": "mediakit-cli ...",
                "token": "secret",
            }
        )
