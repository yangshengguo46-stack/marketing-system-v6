from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from deerflow.community.mediakit import (
    CommandResult,
    MediaKitCapabilityRouter,
    MediaKitCloudSourceContext,
    MediaKitCommandError,
    MediaKitLocalOutputPolicy,
    MediaKitLocalResultMaterializer,
    MediaKitTrustedSourceStore,
)
from deerflow.incubation import (
    ArtifactEnvelope,
    MediaArtifact,
    MediaKitExecutionReceipt,
    MediaKitLocalProductionOperation,
    MediaObservationSnapshot,
    MediaSourceReceipt,
    ProjectRef,
    VideoMetadataObservation,
    execute_local_media_operation,
    seal_media_observation_snapshot,
    seal_media_source_receipt,
)
from deerflow.incubation.media import EphemeralMediaSource

NOW = datetime(2026, 8, 18, 12, 0, tzinfo=UTC)
PROJECT = ProjectRef(owner_user_id="user-1", project_id="project-1")


def _canonical_sha256(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _schema_payload() -> dict[str, object]:
    return {
        "_notice": {"skills": {"message": "sync available"}},
        "name": "trim_video",
        "description": "trim",
        "input_schema": {
            "type": "object",
            "properties": {
                "video_url": {"type": "string"},
                "start_time": {"type": "number"},
                "end_time": {"type": "number"},
            },
            "required": ["video_url"],
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "video_url": {"type": "string"},
                "duration": {"type": "number"},
                "resolution": {"type": "string"},
            },
            "required": ["video_url"],
        },
    }


def _schema_sha256() -> str:
    payload = _schema_payload()
    return _canonical_sha256({key: value for key, value in payload.items() if key != "_notice"})


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
    material: ArtifactEnvelope,
    *,
    status: str = "ready",
) -> ArtifactEnvelope:
    adapted = _artifact(
        artifact_type="adapted_draft",
        payload={"adapted_body_sha256": "a" * 64},
    )
    decision = _artifact(
        artifact_type="format_decision",
        payload={"selected_format": {"kind": "material_only", "custom_name": None}},
    )
    return _artifact(
        artifact_type="production_plan",
        payload={
            "status": status,
            "asset_requirements": [
                {
                    "asset_id": "asset-user-video",
                    "kind": "video",
                    "purpose": "使用用户已授权视频完成既定表达。",
                    "source": "existing_user_material",
                    "basis_artifact_ids": [material.artifact_id],
                }
            ],
            "production_actions": [
                {
                    "action_id": "action-trim",
                    "kind": "select_existing",
                    "instruction": "从已授权素材中选取既定表达需要的部分。",
                    "asset_ids": ["asset-user-video"],
                }
            ],
            "assembly_steps": [
                {
                    "step_id": "step-final",
                    "instruction": "按适配稿顺序装配为本条视频。",
                    "input_asset_ids": ["asset-user-video"],
                }
            ],
            "resource_gaps": [] if status == "ready" else ["仍有未满足资源。"],
            "unknowns": [],
            "limitations": ["不改变上游选题与表达。"],
            "narrative_execution_hint": None,
            "adapted_draft_ref": adapted.to_parent_ref().model_dump(mode="json"),
            "adapted_body_sha256": "a" * 64,
            "format_decision_ref": decision.to_parent_ref().model_dump(mode="json"),
            "selected_format": {"kind": "material_only", "custom_name": None},
            "user_material_refs": [material.to_parent_ref().model_dump(mode="json")],
        },
        parents=(adapted.to_parent_ref(), decision.to_parent_ref(), material.to_parent_ref()),
    )


def _metadata_output(size_bytes: int) -> dict[str, object]:
    return {
        "format_meta": {
            "container": "mp4",
            "duration": 10.0,
            "size": size_bytes,
            "bitrate": None,
            "md5": None,
        },
        "video_stream_meta": {
            "codec": "h264",
            "duration": 10.0,
            "width": 720,
            "height": 1280,
            "fps": 25.0,
            "bitrate": None,
            "dynamic_range": None,
        },
        "audio_stream_meta": None,
    }


def _user_material(
    source: EphemeralMediaSource,
    *,
    source_bytes: bytes,
) -> tuple[ArtifactEnvelope, ArtifactEnvelope]:
    source_hash = hashlib.sha256(source_bytes).hexdigest()
    receipt = MediaSourceReceipt.from_ephemeral(source, resolved_at=NOW)
    receipt_artifact = seal_media_source_receipt(
        project=PROJECT,
        receipt=receipt,
        evidence_role="user_material",
        source_thread_id="thread-1",
        source_run_id="run-1",
    )
    execution = MediaKitExecutionReceipt(
        capability_domain="video",
        capability_tool="probe-video-metadata",
        cli_version="0.2.0",
        schema_sha256="1" * 64,
        execution_mode="local",
        request_sha256="2" * 64,
        source_content_sha256=source_hash,
        output_sha256="3" * 64,
        completed_at=NOW,
        cloud_processing_approved=False,
    )
    snapshot = MediaObservationSnapshot(
        source_ref=source.source_ref,
        observation_kind="video_metadata",
        observed_at=NOW,
        observation=VideoMetadataObservation.model_validate(_metadata_output(len(source_bytes))),
        execution=execution,
    )
    observation = seal_media_observation_snapshot(
        project=PROJECT,
        snapshot=snapshot,
        source_receipt_artifact=receipt_artifact,
        source_thread_id="thread-1",
        source_run_id="run-1",
    )
    return receipt_artifact, observation


async def _trusted_user_material(
    tmp_path: Path,
    *,
    source_bytes: bytes,
) -> tuple[MediaKitTrustedSourceStore, ArtifactEnvelope, ArtifactEnvelope]:
    upload_path = tmp_path / "uploaded-source.mp4"
    upload_path.write_bytes(source_bytes)
    store = MediaKitTrustedSourceStore(tmp_path / "trusted-source-store")
    staged = await store.stage_local_video(
        user_id=PROJECT.owner_user_id,
        project_id=PROJECT.project_id,
        source_path=upload_path,
        rights_ref="rights:user-upload-1",
    )
    source = await store.resolve(
        MediaKitCloudSourceContext(
            user_id=PROJECT.owner_user_id,
            project_id=PROJECT.project_id,
            local_task_id="observation-1",
            source_ref=staged.source_ref,
            rights_ref="rights:user-upload-1",
            source_content_sha256=staged.content_sha256,
        )
    )
    receipt, material = _user_material(source, source_bytes=source_bytes)
    return store, receipt, material


def _operation(**updates: object) -> MediaKitLocalProductionOperation:
    values: dict[str, object] = {
        "operation_id": "local-trim-1",
        "production_action_ids": ["action-trim"],
        "assembly_step_ids": ["step-final"],
        "plan_asset_ids": ["asset-user-video"],
        "capability_domain": "editing",
        "capability_tool": "trim-video",
        "expected_schema_sha256": _schema_sha256(),
        "arguments": {"start_time": 0, "end_time": 1},
        "output_field": "video_url",
        "stage": "final",
        "maximum_output_bytes": 1024 * 1024,
    }
    values.update(updates)
    return MediaKitLocalProductionOperation.model_validate(values)


@pytest.mark.asyncio
async def test_local_operation_executes_exact_plan_step_materializes_and_seals(
    tmp_path: Path,
) -> None:
    source_bytes = b"authorized-input-video"
    source_store, source_receipt, material = await _trusted_user_material(
        tmp_path,
        source_bytes=source_bytes,
    )
    plan = _production_plan(material)
    output_bytes = b"trimmed-video-output"
    calls: list[tuple[str, ...]] = []
    output_paths: list[Path] = []

    async def runner(command: tuple[str, ...], timeout_seconds: float) -> CommandResult:
        calls.append(command)
        if command[-1] == "version":
            return CommandResult(returncode=0, stdout="mediakit-cli 0.2.0\n", stderr="")
        if command[-1] == "--schema":
            return CommandResult(returncode=0, stdout=json.dumps(_schema_payload()), stderr="")
        output_root = Path(command[command.index("--output-path") + 1])
        output_path = output_root / "trimmed.mp4"
        output_path.write_bytes(output_bytes)
        output_paths.append(output_path)
        return CommandResult(
            returncode=0,
            stdout=json.dumps(
                {
                    "video_url": str(output_path),
                    "duration": 1.0,
                    "resolution": "720p",
                }
            ),
            stderr="",
        )

    async def quality_check(path: Path, policy, declared_content_type: str | None) -> str:
        assert path.read_bytes() == output_bytes
        assert policy.capability_tool == "trim-video"
        assert declared_content_type is None
        return "video/mp4"

    router = MediaKitCapabilityRouter(runner=runner)
    materializer = MediaKitLocalResultMaterializer(
        root=tmp_path / "private-results",
        policies=(
            MediaKitLocalOutputPolicy(
                capability_domain="editing",
                capability_tool="trim-video",
                path_field="video_url",
                media_kind="video",
                maximum_bytes=1024 * 1024,
            ),
        ),
        quality_check=quality_check,
    )

    artifact = await execute_local_media_operation(
        project=PROJECT,
        production_plan_artifact=plan,
        input_asset_artifact=material,
        source_receipt_artifact=source_receipt,
        operation=_operation(),
        router=router,
        source_store=source_store,
        materializer=materializer,
        source_thread_id="thread-1",
        source_run_id="run-2",
    )

    payload = MediaArtifact.model_validate(artifact.payload)
    serialized = json.dumps(artifact.model_dump(mode="json"), ensure_ascii=False)
    assert artifact.artifact_type == "media_artifact"
    assert payload.stage == "final"
    assert payload.media_sha256 == hashlib.sha256(output_bytes).hexdigest()
    assert payload.mime_type == "video/mp4"
    assert payload.size_bytes == len(output_bytes)
    assert payload.duration_seconds is None
    assert payload.qc_status == "passed"
    assert payload.production_binding.operation_id == "local-trim-1"
    assert payload.production_binding.production_action_ids == ("action-trim",)
    assert payload.production_binding.assembly_step_ids == ("step-final",)
    assert payload.execution.capability_tool == "trim-video"
    assert str(tmp_path / "uploaded-source.mp4") not in serialized
    assert all(str(path) not in serialized for path in output_paths)
    assert "rights:user-upload-1" not in serialized
    assert calls[-1][0:4] == ("mediakit-cli", "--local", "editing", "trim-video")
    assert "--output-path" in calls[-1]
    stored_files = tuple((tmp_path / "private-results").rglob("*.media"))
    assert len(stored_files) == 1
    assert stored_files[0].read_bytes() == output_bytes

    replay = await execute_local_media_operation(
        project=PROJECT,
        production_plan_artifact=plan,
        input_asset_artifact=material,
        source_receipt_artifact=source_receipt,
        operation=_operation(),
        router=router,
        source_store=source_store,
        materializer=materializer,
        source_thread_id="thread-1",
        source_run_id="run-3",
    )
    assert replay.artifact_id == artifact.artifact_id
    assert replay.payload == artifact.payload
    assert len(output_paths) == 2
    assert output_paths[0].parent != output_paths[1].parent
    assert all(not path.parent.exists() for path in output_paths)


@pytest.mark.asyncio
async def test_changed_trusted_source_stops_before_cli_execution(tmp_path: Path) -> None:
    source_store, source_receipt, material = await _trusted_user_material(
        tmp_path,
        source_bytes=b"original-video",
    )
    trusted_files = tuple((tmp_path / "trusted-source-store" / "sources").rglob("*.video"))
    assert len(trusted_files) == 1
    trusted_files[0].chmod(0o600)
    trusted_files[0].write_bytes(b"changed-after-approval")
    runner_calls = 0

    async def runner(command: tuple[str, ...], timeout_seconds: float) -> CommandResult:
        nonlocal runner_calls
        runner_calls += 1
        raise AssertionError("changed source must stop before MediaKit starts")

    async def quality_check(path: Path, policy, declared_content_type: str | None) -> str:
        raise AssertionError("changed source must not reach quality checking")

    with pytest.raises(MediaKitCommandError, match="source content verification failed"):
        await execute_local_media_operation(
            project=PROJECT,
            production_plan_artifact=_production_plan(material),
            input_asset_artifact=material,
            source_receipt_artifact=source_receipt,
            operation=_operation(),
            router=MediaKitCapabilityRouter(runner=runner),
            source_store=source_store,
            materializer=MediaKitLocalResultMaterializer(
                root=tmp_path / "results",
                policies=(
                    MediaKitLocalOutputPolicy(
                        capability_domain="editing",
                        capability_tool="trim-video",
                        path_field="video_url",
                        media_kind="video",
                        maximum_bytes=1024 * 1024,
                    ),
                ),
                quality_check=quality_check,
            ),
            source_thread_id="thread-1",
            source_run_id="run-2",
        )

    assert runner_calls == 0


@pytest.mark.asyncio
async def test_schema_drift_and_unbound_plan_nodes_stop_before_execution(
    tmp_path: Path,
) -> None:
    source_store, source_receipt, material = await _trusted_user_material(
        tmp_path,
        source_bytes=b"video",
    )
    plan = _production_plan(material)
    execution_calls = 0

    async def runner(command: tuple[str, ...], timeout_seconds: float) -> CommandResult:
        nonlocal execution_calls
        if command[-1] == "version":
            return CommandResult(returncode=0, stdout="mediakit-cli 0.2.0\n", stderr="")
        if command[-1] == "--schema":
            return CommandResult(returncode=0, stdout=json.dumps(_schema_payload()), stderr="")
        execution_calls += 1
        raise AssertionError("invalid operation must stop before execution")

    async def quality_check(path: Path, policy, declared_content_type: str | None) -> str:
        raise AssertionError("invalid operation must not reach materialization")

    router = MediaKitCapabilityRouter(runner=runner)
    materializer = MediaKitLocalResultMaterializer(
        root=tmp_path / "results",
        policies=(
            MediaKitLocalOutputPolicy(
                capability_domain="editing",
                capability_tool="trim-video",
                path_field="video_url",
                media_kind="video",
                maximum_bytes=1024 * 1024,
            ),
        ),
        quality_check=quality_check,
    )

    with pytest.raises(MediaKitCommandError, match="schema changed"):
        await execute_local_media_operation(
            project=PROJECT,
            production_plan_artifact=plan,
            input_asset_artifact=material,
            source_receipt_artifact=source_receipt,
            operation=_operation(expected_schema_sha256="f" * 64),
            router=router,
            source_store=source_store,
            materializer=materializer,
            source_thread_id="thread-1",
            source_run_id="run-2",
        )

    with pytest.raises(ValueError, match="production action"):
        await execute_local_media_operation(
            project=PROJECT,
            production_plan_artifact=plan,
            input_asset_artifact=material,
            source_receipt_artifact=source_receipt,
            operation=_operation(production_action_ids=("missing-action",)),
            router=router,
            source_store=source_store,
            materializer=materializer,
            source_thread_id="thread-1",
            source_run_id="run-2",
        )

    with pytest.raises(ValueError, match="provisional.*final"):
        await execute_local_media_operation(
            project=PROJECT,
            production_plan_artifact=_production_plan(material, status="provisional"),
            input_asset_artifact=material,
            source_receipt_artifact=source_receipt,
            operation=_operation(),
            router=router,
            source_store=source_store,
            materializer=materializer,
            source_thread_id="thread-1",
            source_run_id="run-2",
        )

    assert execution_calls == 0


@pytest.mark.asyncio
async def test_output_outside_allowed_cli_root_is_not_sealed(tmp_path: Path) -> None:
    source_store, source_receipt, material = await _trusted_user_material(
        tmp_path,
        source_bytes=b"video",
    )
    plan = _production_plan(material)
    outside = tmp_path / "outside.mp4"
    outside.write_bytes(b"not-approved-output")

    async def runner(command: tuple[str, ...], timeout_seconds: float) -> CommandResult:
        if command[-1] == "version":
            return CommandResult(returncode=0, stdout="mediakit-cli 0.2.0\n", stderr="")
        if command[-1] == "--schema":
            return CommandResult(returncode=0, stdout=json.dumps(_schema_payload()), stderr="")
        return CommandResult(returncode=0, stdout=json.dumps({"video_url": str(outside), "duration": 1.0}), stderr="")

    async def quality_check(path: Path, policy, declared_content_type: str | None) -> str:
        raise AssertionError("outside output must not reach quality check")

    with pytest.raises(MediaKitCommandError, match="output path is not allowed"):
        await execute_local_media_operation(
            project=PROJECT,
            production_plan_artifact=plan,
            input_asset_artifact=material,
            source_receipt_artifact=source_receipt,
            operation=_operation(),
            router=MediaKitCapabilityRouter(runner=runner),
            source_store=source_store,
            materializer=MediaKitLocalResultMaterializer(
                root=tmp_path / "results",
                policies=(
                    MediaKitLocalOutputPolicy(
                        capability_domain="editing",
                        capability_tool="trim-video",
                        path_field="video_url",
                        media_kind="video",
                        maximum_bytes=1024 * 1024,
                    ),
                ),
                quality_check=quality_check,
            ),
            source_thread_id="thread-1",
            source_run_id="run-2",
        )


def test_local_operation_rejects_secondary_locators() -> None:
    with pytest.raises(ValidationError, match="locator"):
        _operation(arguments={"subtitle_url": "/tmp/private.srt"})

    with pytest.raises(ValidationError, match="locator"):
        _operation(arguments={"output_path": "/tmp/output.mp4"})

    with pytest.raises(ValidationError, match="only start_time and end_time"):
        _operation(arguments={"unknown_option": 1})
