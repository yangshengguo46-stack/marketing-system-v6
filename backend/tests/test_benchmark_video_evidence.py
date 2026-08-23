import json
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from deerflow.incubation.benchmark_video import (
    BenchmarkVideoCapabilityVersion,
    BenchmarkVideoCoverageReceipt,
    BenchmarkVideoEditorialInterpretation,
    BenchmarkVideoEvidence,
    BenchmarkVideoExcludedOrFailedRange,
    BenchmarkVideoMachineObservation,
    BenchmarkVideoModalityAvailability,
    BenchmarkVideoNonTransferableTrait,
    BenchmarkVideoSourceBinding,
    BenchmarkVideoTimeRange,
    BenchmarkVideoTransferablePattern,
    BenchmarkVideoUnknown,
    seal_benchmark_video_evidence,
)
from deerflow.incubation.contracts import ArtifactEnvelope, LogicalAccountRef, ProjectRef
from deerflow.incubation.media import (
    MediaKitExecutionReceipt,
    MediaObservationSnapshot,
    MediaSourceReceipt,
    VideoMetadataObservation,
    seal_media_observation_snapshot,
    seal_media_source_receipt,
)

NOW = datetime(2026, 8, 22, 12, 0, tzinfo=UTC)
PROJECT = ProjectRef(owner_user_id="user-1", project_id="project-1")
LOGICAL_ACCOUNT = LogicalAccountRef(
    owner_user_id="user-1",
    project_id="project-1",
    logical_account_id="account-1",
)


def _parent_artifacts(
    *,
    project: ProjectRef = PROJECT,
    evidence_role: str = "benchmark_evidence",
    source_ref: str = "benchmark-video:123",
) -> tuple[ArtifactEnvelope, ArtifactEnvelope]:
    receipt = MediaSourceReceipt(
        source_ref=source_ref,
        media_kind="video",
        transport="local_file",
        resolver="user_upload:v1",
        rights_ref="rights:user-supplied-benchmark-review",
        locator_sha256="a" * 64,
        resolved_at=NOW,
    )
    source_artifact = seal_media_source_receipt(
        project=project,
        receipt=receipt,
        evidence_role=evidence_role,
        source_thread_id="thread-1",
        source_run_id="run-1",
    )
    execution = MediaKitExecutionReceipt(
        capability_domain="video",
        capability_tool="probe-video-metadata",
        cli_version="0.2.0",
        schema_sha256="b" * 64,
        execution_mode="local",
        request_sha256="c" * 64,
        source_content_sha256="d" * 64,
        output_sha256="e" * 64,
        completed_at=NOW,
        cloud_processing_approved=False,
    )
    snapshot = MediaObservationSnapshot(
        source_ref=source_ref,
        observation_kind="video_metadata",
        observed_at=NOW,
        observation=VideoMetadataObservation.model_validate(
            {
                "format_meta": {
                    "container": "mov,mp4",
                    "duration": 28.4,
                    "size": 1_024_000,
                },
                "video_stream_meta": {
                    "codec": "h264",
                    "duration": 28.4,
                    "width": 1080,
                    "height": 1920,
                    "fps": 30,
                },
            }
        ),
        execution=execution,
    )
    observation_artifact = seal_media_observation_snapshot(
        project=project,
        snapshot=snapshot,
        source_receipt_artifact=source_artifact,
        source_thread_id="thread-1",
        source_run_id="run-1",
    )
    return source_artifact, observation_artifact


def _evidence(
    source_artifact: ArtifactEnvelope,
    observation_artifact: ArtifactEnvelope,
    *,
    source_ref: str = "benchmark-video:123",
    rights_ref: str = "rights:user-supplied-benchmark-review",
) -> BenchmarkVideoEvidence:
    return BenchmarkVideoEvidence(
        source=BenchmarkVideoSourceBinding(
            source_ref=source_ref,
            rights_ref=rights_ref,
            rights_basis_status="declared_reference_not_verified",
            locator_sha256="a" * 64,
            source_content_sha256="d" * 64,
            source_receipt_artifact_id=source_artifact.artifact_id,
            source_receipt_content_sha256=source_artifact.content_sha256,
            media_observation_artifact_id=observation_artifact.artifact_id,
            media_observation_content_sha256=observation_artifact.content_sha256,
        ),
        coverage=BenchmarkVideoCoverageReceipt(
            sampling_method="The complete file was probed once for technical metadata; no frame, speech, text, scene, or sound analysis ran.",
            analyzed_ranges=(BenchmarkVideoTimeRange(start_seconds=0, end_seconds=28.4),),
            capability_versions=(
                BenchmarkVideoCapabilityVersion(
                    capability_domain="video",
                    capability_tool="probe-video-metadata",
                    version="0.2.0",
                    schema_sha256="b" * 64,
                ),
            ),
            excluded_or_failed_ranges=(),
            modalities_available=(
                BenchmarkVideoModalityAvailability(
                    modality="technical_metadata",
                    status="observed",
                    basis_or_limitation="MediaKit returned container, duration, stream, dimension, and frame-rate metadata.",
                ),
                BenchmarkVideoModalityAvailability(
                    modality="speech",
                    status="not_run",
                    basis_or_limitation="No ASR capability ran.",
                ),
                BenchmarkVideoModalityAvailability(
                    modality="on_screen_text",
                    status="not_run",
                    basis_or_limitation="No OCR capability ran.",
                ),
                BenchmarkVideoModalityAvailability(
                    modality="scene_structure",
                    status="not_run",
                    basis_or_limitation="No shot-boundary or scene capability ran.",
                ),
                BenchmarkVideoModalityAvailability(
                    modality="sound",
                    status="not_run",
                    basis_or_limitation="No audio-event capability ran.",
                ),
                BenchmarkVideoModalityAvailability(
                    modality="visual_framing",
                    status="not_run",
                    basis_or_limitation="No frame-level visual analysis ran.",
                ),
            ),
            observation_count=1,
            allowed_use="analysis_only",
        ),
        interpreted_at=NOW,
        machine_observations=(
            BenchmarkVideoMachineObservation(
                observation_id="obs-duration",
                kind="technical_metadata",
                statement="视频时长为 28.4 秒，画幅为 1080×1920。",
                source_field_paths=(
                    "observation.format_meta.duration",
                    "observation.video_stream_meta.width",
                    "observation.video_stream_meta.height",
                ),
            ),
        ),
        editorial_interpretations=(
            BenchmarkVideoEditorialInterpretation(
                interpretation_id="interpret-pacing",
                statement="短时长与竖屏画幅可以支持紧凑的信息推进；这是编辑判断，不是效果因果解释。",
                based_on_observation_ids=("obs-duration",),
                uncertainty="没有逐镜头与平台留存数据，无法判断具体节奏效果。",
            ),
        ),
        transferable_patterns=(
            BenchmarkVideoTransferablePattern(
                pattern_id="pattern-compact-vertical",
                statement="可迁移的是短竖屏内容的紧凑信息结构，具体镜头和表达必须重新设计。",
                basis_observation_ids=("obs-duration",),
                basis_interpretation_ids=("interpret-pacing",),
            ),
        ),
        non_transferable_traits=(
            BenchmarkVideoNonTransferableTrait(
                trait_id="no-creator-identity",
                category="creator_identity",
                description="原作者的姓名、声音、肖像和人格识别特征。",
                reason="这些特征属于原作者身份，不属于可迁移结构。",
            ),
            BenchmarkVideoNonTransferableTrait(
                trait_id="no-brand-trade-dress",
                category="brand_trade_dress",
                description="原视频的品牌标识、专属包装、固定片头与独特视觉装潢。",
                reason="品牌装潢不能作为复刻目标。",
            ),
        ),
        unknowns=(
            BenchmarkVideoUnknown(
                unknown_id="unknown-retention",
                question="观众在哪些时间点流失？",
                why_unresolved="当前父级只有技术元数据，没有留存曲线。",
                needed_evidence="该视频对应的合法平台留存数据。",
            ),
        ),
    )


def test_seal_benchmark_video_evidence_binds_exact_project_account_declared_rights_reference_and_parent_hashes() -> None:
    source, observation = _parent_artifacts()
    evidence = _evidence(source, observation)

    artifact = seal_benchmark_video_evidence(
        project=PROJECT,
        logical_account=LOGICAL_ACCOUNT,
        evidence=evidence,
        source_receipt_artifact=source,
        media_observation_artifact=observation,
        source_thread_id="thread-2",
        source_run_id="run-2",
    )

    assert artifact.artifact_type == "benchmark_video_evidence"
    assert artifact.evidence_role == "benchmark_evidence"
    assert artifact.logical_account == LOGICAL_ACCOUNT
    assert artifact.parents == tuple(sorted((source.to_parent_ref(), observation.to_parent_ref()), key=lambda item: item.artifact_id))
    assert artifact.payload["source"]["source_receipt_content_sha256"] == source.content_sha256
    assert artifact.payload["source"]["media_observation_content_sha256"] == observation.content_sha256
    assert artifact.payload["source"]["rights_basis_status"] == "declared_reference_not_verified"
    assert artifact.payload["coverage"]["allowed_use"] == "analysis_only"
    assert artifact.payload["coverage"]["observation_count"] == 1
    assert artifact.payload["boundary"] == {
        "account_direction_authority": "none",
        "causal_claim_status": "not_established",
        "replication_scope": "abstract_structure_only",
    }


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("source_ref", "benchmark-video:other", "source_ref"),
        ("rights_ref", "rights:other", "rights_ref"),
        ("locator_sha256", "f" * 64, "locator_sha256"),
        ("source_content_sha256", "f" * 64, "source content hash"),
        ("source_receipt_content_sha256", "f" * 64, "source receipt hash"),
        ("media_observation_content_sha256", "f" * 64, "media observation hash"),
    ],
)
def test_seal_rejects_source_rights_reference_and_parent_hash_identity_drift(field: str, value: str, message: str) -> None:
    source, observation = _parent_artifacts()
    payload = _evidence(source, observation).model_dump(mode="json")
    payload["source"][field] = value

    with pytest.raises(ValueError, match=message):
        seal_benchmark_video_evidence(
            project=PROJECT,
            logical_account=LOGICAL_ACCOUNT,
            evidence=BenchmarkVideoEvidence.model_validate(payload),
            source_receipt_artifact=source,
            media_observation_artifact=observation,
            source_thread_id="thread-2",
            source_run_id="run-2",
        )


def test_seal_requires_benchmark_media_parents_and_exact_observation_lineage() -> None:
    source, observation = _parent_artifacts(evidence_role="user_material")
    with pytest.raises(ValueError, match="benchmark_evidence"):
        seal_benchmark_video_evidence(
            project=PROJECT,
            logical_account=LOGICAL_ACCOUNT,
            evidence=_evidence(source, observation),
            source_receipt_artifact=source,
            media_observation_artifact=observation,
            source_thread_id="thread-2",
            source_run_id="run-2",
        )

    benchmark_source, benchmark_observation = _parent_artifacts()
    unrelated_source, _ = _parent_artifacts(source_ref="benchmark-video:other")
    forged_observation = ArtifactEnvelope.seal(
        project=PROJECT,
        artifact_type="media_observation",
        version=1,
        payload=benchmark_observation.payload,
        parents=(unrelated_source.to_parent_ref(),),
        evidence_role="benchmark_evidence",
        created_at=NOW,
        source_thread_id="thread-1",
        source_run_id="run-1",
    )
    with pytest.raises(ValueError, match="exact media source receipt parent"):
        seal_benchmark_video_evidence(
            project=PROJECT,
            logical_account=LOGICAL_ACCOUNT,
            evidence=_evidence(benchmark_source, forged_observation),
            source_receipt_artifact=benchmark_source,
            media_observation_artifact=forged_observation,
            source_thread_id="thread-2",
            source_run_id="run-2",
        )


def test_seal_rejects_cross_project_or_cross_logical_account_inputs() -> None:
    source, observation = _parent_artifacts()
    other_project = ProjectRef(owner_user_id="user-1", project_id="project-2")
    with pytest.raises(ValueError, match="project"):
        seal_benchmark_video_evidence(
            project=other_project,
            logical_account=LogicalAccountRef(owner_user_id="user-1", project_id="project-2", logical_account_id="account-1"),
            evidence=_evidence(source, observation),
            source_receipt_artifact=source,
            media_observation_artifact=observation,
            source_thread_id="thread-2",
            source_run_id="run-2",
        )

    account_bound_source = source.model_copy(update={"logical_account": LogicalAccountRef(owner_user_id="user-1", project_id="project-1", logical_account_id="another-account")})
    with pytest.raises((ValidationError, ValueError)):
        seal_benchmark_video_evidence(
            project=PROJECT,
            logical_account=LOGICAL_ACCOUNT,
            evidence=_evidence(source, observation),
            source_receipt_artifact=account_bound_source,
            media_observation_artifact=observation,
            source_thread_id="thread-2",
            source_run_id="run-2",
        )


def test_evidence_contract_requires_traceable_interpretation_and_non_transferable_identity_boundaries() -> None:
    source, observation = _parent_artifacts()
    payload = _evidence(source, observation).model_dump(mode="json")
    payload["editorial_interpretations"][0]["based_on_observation_ids"] = ["missing-observation"]
    with pytest.raises(ValidationError, match="unknown machine observation"):
        BenchmarkVideoEvidence.model_validate(payload)

    payload = _evidence(source, observation).model_dump(mode="json")
    payload["non_transferable_traits"][1]["category"] = "creator_identity"
    with pytest.raises(ValidationError, match="brand_trade_dress"):
        BenchmarkVideoEvidence.model_validate(payload)

    payload = _evidence(source, observation).model_dump(mode="json")
    payload["boundary"]["causal_claim_status"] = "established"
    with pytest.raises(ValidationError):
        BenchmarkVideoEvidence.model_validate(payload)

    payload = _evidence(source, observation).model_dump(mode="json")
    payload["account_direction"] = {"positioning": "copy the benchmark"}
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        BenchmarkVideoEvidence.model_validate(payload)


def test_coverage_contract_is_required_complete_and_does_not_claim_rights_verification() -> None:
    source, observation = _parent_artifacts()

    payload = _evidence(source, observation).model_dump(mode="json")
    payload.pop("coverage")
    with pytest.raises(ValidationError, match="coverage"):
        BenchmarkVideoEvidence.model_validate(payload)

    payload = _evidence(source, observation).model_dump(mode="json")
    payload["coverage"].pop("allowed_use")
    with pytest.raises(ValidationError, match="allowed_use"):
        BenchmarkVideoEvidence.model_validate(payload)

    payload = _evidence(source, observation).model_dump(mode="json")
    payload["coverage"]["modalities_available"][-1]["modality"] = "speech"
    with pytest.raises(ValidationError, match="modalities_available"):
        BenchmarkVideoEvidence.model_validate(payload)

    payload = _evidence(source, observation).model_dump(mode="json")
    payload["coverage"]["observation_count"] = 2
    with pytest.raises(ValidationError, match="observation_count"):
        BenchmarkVideoEvidence.model_validate(payload)

    payload = _evidence(source, observation).model_dump(mode="json")
    payload["source"]["rights_basis_status"] = "verified"
    with pytest.raises(ValidationError, match="rights_basis_status"):
        BenchmarkVideoEvidence.model_validate(payload)


def test_seal_rejects_unreceipted_capability_versions_and_ranges_outside_the_source() -> None:
    source, observation = _parent_artifacts()

    payload = _evidence(source, observation).model_dump(mode="json")
    payload["coverage"]["capability_versions"][0]["version"] = "9.9.9"
    with pytest.raises(ValueError, match="capability_versions"):
        seal_benchmark_video_evidence(
            project=PROJECT,
            logical_account=LOGICAL_ACCOUNT,
            evidence=BenchmarkVideoEvidence.model_validate(payload),
            source_receipt_artifact=source,
            media_observation_artifact=observation,
            source_thread_id="thread-2",
            source_run_id="run-2",
        )

    payload = _evidence(source, observation).model_dump(mode="json")
    payload["coverage"]["analyzed_ranges"] = [{"start_seconds": 0, "end_seconds": 30}]
    payload["coverage"]["excluded_or_failed_ranges"] = [
        BenchmarkVideoExcludedOrFailedRange(
            time_range=BenchmarkVideoTimeRange(start_seconds=28.4, end_seconds=30),
            outcome="failed",
            reason="Synthetic out-of-bounds range for contract validation.",
        ).model_dump(mode="json")
    ]
    evidence = BenchmarkVideoEvidence.model_validate(payload)
    with pytest.raises(ValueError, match="source duration"):
        seal_benchmark_video_evidence(
            project=PROJECT,
            logical_account=LOGICAL_ACCOUNT,
            evidence=evidence,
            source_receipt_artifact=source,
            media_observation_artifact=observation,
            source_thread_id="thread-2",
            source_run_id="run-2",
        )


def test_seal_validates_machine_source_paths_against_exact_observation_payload() -> None:
    source, observation = _parent_artifacts()
    payload = _evidence(source, observation).model_dump(mode="json")
    payload["machine_observations"][0]["source_field_paths"] = ["observation.scene_boundaries"]

    with pytest.raises(ValueError, match="source_field_paths"):
        seal_benchmark_video_evidence(
            project=PROJECT,
            logical_account=LOGICAL_ACCOUNT,
            evidence=BenchmarkVideoEvidence.model_validate(payload),
            source_receipt_artifact=source,
            media_observation_artifact=observation,
            source_thread_id="thread-2",
            source_run_id="run-2",
        )


def test_lead_projection_is_bounded_separates_epistemic_layers_and_preserves_safety_boundary() -> None:
    source, observation = _parent_artifacts()
    payload = _evidence(source, observation).model_dump(mode="json")
    for index in range(30):
        payload["machine_observations"].append(
            {
                "observation_id": f"obs-{index}",
                "kind": "technical_metadata",
                "statement": "这是机器观察，不是创作结论。" * 80,
                "source_field_paths": ["observation.format_meta.duration"],
                "confidence": None,
                "time_range": None,
            }
        )
    payload["coverage"]["observation_count"] = len(payload["machine_observations"])
    evidence = BenchmarkVideoEvidence.model_validate(payload)

    projection = evidence.to_lead_projection(max_bytes=4_096)
    encoded = json.dumps(projection, ensure_ascii=False, separators=(",", ":")).encode("utf-8")

    assert len(encoded) <= 4_096
    assert set(projection) >= {
        "coverage",
        "machine_observations",
        "editorial_interpretations",
        "transferable_patterns",
        "non_transferable_traits",
        "unknowns",
        "boundary",
    }
    assert projection["projection"]["truncated"] is True
    assert projection["boundary"]["account_direction_authority"] == "none"
    assert projection["boundary"]["causal_claim_status"] == "not_established"
    assert projection["boundary"]["replication_scope"] == "abstract_structure_only"
    assert projection["coverage"]["allowed_use"] == "analysis_only"
    assert projection["coverage"]["modalities_available"][0]["modality"] == "technical_metadata"
    assert projection["source"]["rights_basis_status"] == "declared_reference_not_verified"
    assert "cannot write or revise account direction" in projection["epistemic_notice"]
    assert "creator identity or brand trade dress" in projection["epistemic_notice"]
    assert "does not verify permission" in projection["epistemic_notice"]
