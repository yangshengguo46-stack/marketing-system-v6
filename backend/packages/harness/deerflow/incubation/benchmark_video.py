from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from typing import Annotated, Literal

from pydantic import Field, JsonValue, field_validator, model_validator

from deerflow.incubation.contracts import (
    ArtifactEnvelope,
    IncubationContract,
    LogicalAccountRef,
    NonEmptyStr,
    ProjectRef,
)
from deerflow.incubation.media import MediaObservationSnapshot, MediaSourceReceipt

BENCHMARK_VIDEO_EPISTEMIC_NOTICE = (
    "This single-video evidence cannot write or revise account direction, does not establish causal performance claims, "
    "and, when allowed_use permits transfer, limits it to abstract structure only; it must not replicate creator identity or brand trade dress. "
    "A rights_ref is only a declared provenance reference and does not verify permission to analyze, adapt, or publish the source."
)

_SOURCE_PATH_PATTERN = re.compile(r"^(?:source_ref|observed_at|observation_kind|observation|execution)(?:\.[A-Za-z0-9_-]+)*$")
_BENCHMARK_MODALITIES = (
    "technical_metadata",
    "speech",
    "on_screen_text",
    "scene_structure",
    "sound",
    "visual_framing",
)
_OBSERVATION_KIND_MODALITY = {
    "technical_metadata": "technical_metadata",
    "speech_transcript": "speech",
    "on_screen_text": "on_screen_text",
    "shot_boundary": "scene_structure",
    "visual_motion": "visual_framing",
    "audio_event": "sound",
}


def _aware_utc(value: datetime, *, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


def _payload_sha256(value: JsonValue) -> str:
    canonical = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _payload_size(value: JsonValue) -> int:
    return len(
        json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    )


def _path_exists(payload: JsonValue, path: str) -> bool:
    current: JsonValue = payload
    for segment in path.split("."):
        if not isinstance(current, dict) or segment not in current:
            return False
        current = current[segment]
    return True


class BenchmarkVideoSourceBinding(IncubationContract):
    """Content-addressed source and parent identity; never a raw locator."""

    source_ref: NonEmptyStr = Field(max_length=255)
    rights_ref: NonEmptyStr = Field(
        max_length=255,
        description="A declared provenance or rights-basis reference; its presence is not permission verification.",
    )
    rights_basis_status: Literal["declared_reference_not_verified"]
    locator_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_receipt_artifact_id: NonEmptyStr = Field(max_length=80)
    source_receipt_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    media_observation_artifact_id: NonEmptyStr = Field(max_length=80)
    media_observation_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class BenchmarkVideoTimeRange(IncubationContract):
    start_seconds: float = Field(ge=0)
    end_seconds: float = Field(gt=0)

    @model_validator(mode="after")
    def validate_range(self) -> BenchmarkVideoTimeRange:
        if self.end_seconds <= self.start_seconds:
            raise ValueError("end_seconds must be after start_seconds")
        return self


class BenchmarkVideoCapabilityVersion(IncubationContract):
    """One capability version receipted by the exact media observation parent."""

    capability_domain: NonEmptyStr = Field(max_length=64)
    capability_tool: NonEmptyStr = Field(max_length=64)
    version: NonEmptyStr = Field(max_length=64)
    schema_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class BenchmarkVideoExcludedOrFailedRange(IncubationContract):
    time_range: BenchmarkVideoTimeRange
    outcome: Literal["excluded", "failed"]
    reason: NonEmptyStr = Field(max_length=1_000)


class BenchmarkVideoModalityAvailability(IncubationContract):
    modality: Literal[
        "technical_metadata",
        "speech",
        "on_screen_text",
        "scene_structure",
        "sound",
        "visual_framing",
    ]
    status: Literal["observed", "partially_observed", "not_run", "unavailable", "failed"]
    basis_or_limitation: NonEmptyStr = Field(max_length=1_000)


class BenchmarkVideoCoverageReceipt(IncubationContract):
    """Bounded coverage and declared-use receipt for one exact video reading."""

    sampling_method: NonEmptyStr = Field(max_length=1_000)
    analyzed_ranges: Annotated[
        tuple[BenchmarkVideoTimeRange, ...],
        Field(min_length=1, max_length=32),
    ]
    capability_versions: Annotated[
        tuple[BenchmarkVideoCapabilityVersion, ...],
        Field(min_length=1, max_length=16),
    ]
    excluded_or_failed_ranges: Annotated[
        tuple[BenchmarkVideoExcludedOrFailedRange, ...],
        Field(max_length=32),
    ]
    modalities_available: Annotated[
        tuple[BenchmarkVideoModalityAvailability, ...],
        Field(min_length=6, max_length=6),
    ]
    observation_count: int = Field(ge=1, le=64)
    allowed_use: Literal["analysis_only", "analysis_and_abstract_structure_transfer"]

    @field_validator("analyzed_ranges")
    @classmethod
    def canonicalize_analyzed_ranges(
        cls,
        value: tuple[BenchmarkVideoTimeRange, ...],
    ) -> tuple[BenchmarkVideoTimeRange, ...]:
        ordered = tuple(sorted(value, key=lambda item: (item.start_seconds, item.end_seconds)))
        for previous, current in zip(ordered, ordered[1:], strict=False):
            if current.start_seconds < previous.end_seconds:
                raise ValueError("analyzed_ranges must not overlap")
        return ordered

    @field_validator("capability_versions")
    @classmethod
    def canonicalize_capability_versions(
        cls,
        value: tuple[BenchmarkVideoCapabilityVersion, ...],
    ) -> tuple[BenchmarkVideoCapabilityVersion, ...]:
        identities = tuple((item.capability_domain, item.capability_tool) for item in value)
        if len(set(identities)) != len(identities):
            raise ValueError("capability_versions must identify unique capabilities")
        return tuple(sorted(value, key=lambda item: (item.capability_domain, item.capability_tool)))

    @field_validator("excluded_or_failed_ranges")
    @classmethod
    def canonicalize_excluded_or_failed_ranges(
        cls,
        value: tuple[BenchmarkVideoExcludedOrFailedRange, ...],
    ) -> tuple[BenchmarkVideoExcludedOrFailedRange, ...]:
        identities = tuple(
            (
                item.time_range.start_seconds,
                item.time_range.end_seconds,
                item.outcome,
            )
            for item in value
        )
        if len(set(identities)) != len(identities):
            raise ValueError("excluded_or_failed_ranges must be unique")
        return tuple(
            sorted(
                value,
                key=lambda item: (
                    item.time_range.start_seconds,
                    item.time_range.end_seconds,
                    item.outcome,
                ),
            )
        )

    @field_validator("modalities_available")
    @classmethod
    def require_all_modalities_once(
        cls,
        value: tuple[BenchmarkVideoModalityAvailability, ...],
    ) -> tuple[BenchmarkVideoModalityAvailability, ...]:
        by_modality = {item.modality: item for item in value}
        if len(by_modality) != len(value) or set(by_modality) != set(_BENCHMARK_MODALITIES):
            raise ValueError("modalities_available must state each required modality exactly once")
        return tuple(by_modality[modality] for modality in _BENCHMARK_MODALITIES)


class BenchmarkVideoMachineObservation(IncubationContract):
    observation_id: NonEmptyStr = Field(max_length=80)
    kind: Literal[
        "technical_metadata",
        "speech_transcript",
        "on_screen_text",
        "shot_boundary",
        "visual_motion",
        "audio_event",
        "other_machine_observation",
    ]
    statement: NonEmptyStr = Field(max_length=2_000)
    source_field_paths: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1, max_length=16)]
    time_range: BenchmarkVideoTimeRange | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)

    @field_validator("source_field_paths")
    @classmethod
    def validate_source_paths(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(value)) != len(value):
            raise ValueError("source_field_paths must be unique")
        if any(not _SOURCE_PATH_PATTERN.fullmatch(path) for path in value):
            raise ValueError("source_field_paths must address the media observation payload")
        return value


class BenchmarkVideoEditorialInterpretation(IncubationContract):
    interpretation_id: NonEmptyStr = Field(max_length=80)
    statement: NonEmptyStr = Field(max_length=2_000)
    based_on_observation_ids: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1, max_length=24)]
    uncertainty: NonEmptyStr = Field(max_length=1_000)
    epistemic_status: Literal["editorial_interpretation", "creative_hypothesis"] = "editorial_interpretation"
    causal_claim: Literal[False] = False

    @field_validator("based_on_observation_ids")
    @classmethod
    def validate_observation_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(value)) != len(value):
            raise ValueError("based_on_observation_ids must be unique")
        return value


class BenchmarkVideoTransferablePattern(IncubationContract):
    pattern_id: NonEmptyStr = Field(max_length=80)
    statement: NonEmptyStr = Field(max_length=2_000)
    basis_observation_ids: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1, max_length=24)]
    basis_interpretation_ids: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1, max_length=24)]
    transfer_scope: Literal["abstract_structure_only"] = "abstract_structure_only"
    adaptation_required: Literal[True] = True

    @field_validator("basis_observation_ids", "basis_interpretation_ids")
    @classmethod
    def validate_basis_ids(cls, value: tuple[str, ...], info) -> tuple[str, ...]:
        if len(set(value)) != len(value):
            raise ValueError(f"{info.field_name} must be unique")
        return value


class BenchmarkVideoNonTransferableTrait(IncubationContract):
    trait_id: NonEmptyStr = Field(max_length=80)
    category: Literal[
        "creator_identity",
        "brand_trade_dress",
        "rights_restricted_material",
        "source_specific_context",
        "unverified_context",
    ]
    description: NonEmptyStr = Field(max_length=1_500)
    reason: NonEmptyStr = Field(max_length=1_000)


class BenchmarkVideoUnknown(IncubationContract):
    unknown_id: NonEmptyStr = Field(max_length=80)
    question: NonEmptyStr = Field(max_length=1_000)
    why_unresolved: NonEmptyStr = Field(max_length=1_000)
    needed_evidence: NonEmptyStr | None = Field(default=None, max_length=1_000)


class BenchmarkVideoBoundary(IncubationContract):
    account_direction_authority: Literal["none"] = "none"
    causal_claim_status: Literal["not_established"] = "not_established"
    replication_scope: Literal["abstract_structure_only"] = "abstract_structure_only"


class BenchmarkVideoEvidence(IncubationContract):
    """A provider-independent, single-video evidence reading.

    The payload deliberately separates machine output from human/editorial
    interpretation. Its fixed boundary is a positive contract: it grants no
    authority to write account direction, causal explanations, identity, or
    brand trade-dress replication instructions.
    """

    source: BenchmarkVideoSourceBinding
    coverage: BenchmarkVideoCoverageReceipt
    interpreted_at: datetime
    machine_observations: Annotated[
        tuple[BenchmarkVideoMachineObservation, ...],
        Field(min_length=1, max_length=64),
    ]
    editorial_interpretations: Annotated[
        tuple[BenchmarkVideoEditorialInterpretation, ...],
        Field(min_length=1, max_length=32),
    ]
    transferable_patterns: Annotated[
        tuple[BenchmarkVideoTransferablePattern, ...],
        Field(min_length=1, max_length=24),
    ]
    non_transferable_traits: Annotated[
        tuple[BenchmarkVideoNonTransferableTrait, ...],
        Field(min_length=2, max_length=24),
    ]
    unknowns: Annotated[
        tuple[BenchmarkVideoUnknown, ...],
        Field(min_length=1, max_length=24),
    ]
    boundary: BenchmarkVideoBoundary = Field(default_factory=BenchmarkVideoBoundary)
    limitations: Annotated[tuple[NonEmptyStr, ...], Field(min_length=1, max_length=20)] = ("Machine observations can be incomplete or wrong; editorial interpretations remain hypotheses until separately evidenced.",)

    @field_validator("interpreted_at")
    @classmethod
    def normalize_interpreted_at(cls, value: datetime) -> datetime:
        return _aware_utc(value, field_name="interpreted_at")

    @model_validator(mode="after")
    def validate_epistemic_lineage(self) -> BenchmarkVideoEvidence:
        if self.coverage.observation_count != len(self.machine_observations):
            raise ValueError("coverage observation_count must match machine_observations")

        availability = {item.modality: item.status for item in self.coverage.modalities_available}
        observed_modalities: set[str] = set()
        for observation in self.machine_observations:
            modality = _OBSERVATION_KIND_MODALITY.get(observation.kind)
            if modality is None:
                continue
            observed_modalities.add(modality)
            if availability[modality] not in {"observed", "partially_observed"}:
                raise ValueError(f"modalities_available marks {modality} unavailable despite a machine observation")
        declared_observed_modalities = {modality for modality, status in availability.items() if status in {"observed", "partially_observed"}}
        unsupported_modalities = declared_observed_modalities - observed_modalities
        if unsupported_modalities:
            raise ValueError(f"modalities_available claims observations that are absent: {sorted(unsupported_modalities)}")

        groups = {
            "machine observation": tuple(item.observation_id for item in self.machine_observations),
            "editorial interpretation": tuple(item.interpretation_id for item in self.editorial_interpretations),
            "transferable pattern": tuple(item.pattern_id for item in self.transferable_patterns),
            "non-transferable trait": tuple(item.trait_id for item in self.non_transferable_traits),
            "unknown": tuple(item.unknown_id for item in self.unknowns),
        }
        for label, identifiers in groups.items():
            if len(set(identifiers)) != len(identifiers):
                raise ValueError(f"{label} ids must be unique")
        flattened = tuple(identifier for identifiers in groups.values() for identifier in identifiers)
        if len(set(flattened)) != len(flattened):
            raise ValueError("benchmark video evidence ids must be globally unique")

        observation_ids = set(groups["machine observation"])
        interpretation_ids = set(groups["editorial interpretation"])
        for interpretation in self.editorial_interpretations:
            missing = set(interpretation.based_on_observation_ids) - observation_ids
            if missing:
                raise ValueError(f"editorial interpretation references unknown machine observation ids: {sorted(missing)}")
        for pattern in self.transferable_patterns:
            missing_observations = set(pattern.basis_observation_ids) - observation_ids
            if missing_observations:
                raise ValueError(f"transferable pattern references unknown machine observation ids: {sorted(missing_observations)}")
            missing_interpretations = set(pattern.basis_interpretation_ids) - interpretation_ids
            if missing_interpretations:
                raise ValueError(f"transferable pattern references unknown editorial interpretation ids: {sorted(missing_interpretations)}")

        categories = {trait.category for trait in self.non_transferable_traits}
        required_categories = {"creator_identity", "brand_trade_dress"}
        missing_categories = required_categories - categories
        if missing_categories:
            raise ValueError(f"non_transferable_traits must explicitly include: {sorted(missing_categories)}")
        return self

    def to_lead_projection(self, *, max_bytes: int = 12_000) -> dict[str, JsonValue]:
        if max_bytes < 4_096:
            raise ValueError("benchmark video Lead projection budget must be at least 4096 bytes")

        projected: dict[str, list[dict[str, JsonValue]]] = {
            "machine_observations": [],
            "editorial_interpretations": [],
            "transferable_patterns": [],
            "non_transferable_traits": [],
            "unknowns": [],
        }
        totals = {
            "machine_observations": len(self.machine_observations),
            "editorial_interpretations": len(self.editorial_interpretations),
            "transferable_patterns": len(self.transferable_patterns),
            "non_transferable_traits": len(self.non_transferable_traits),
            "unknowns": len(self.unknowns),
        }

        coverage_range_limit = 12
        coverage_capability_limit = 8
        coverage_exception_limit = 8
        coverage_projection: dict[str, JsonValue] = {
            "sampling_method_excerpt": self.coverage.sampling_method[:360],
            "analyzed_ranges": [item.model_dump(mode="json") for item in self.coverage.analyzed_ranges[:coverage_range_limit]],
            "capability_versions": [item.model_dump(mode="json") for item in self.coverage.capability_versions[:coverage_capability_limit]],
            "excluded_or_failed_ranges": [
                {
                    "time_range": item.time_range.model_dump(mode="json"),
                    "outcome": item.outcome,
                    "reason_excerpt": item.reason[:180],
                }
                for item in self.coverage.excluded_or_failed_ranges[:coverage_exception_limit]
            ],
            "modalities_available": [
                {
                    "modality": item.modality,
                    "status": item.status,
                    "basis_or_limitation_excerpt": item.basis_or_limitation[:180],
                }
                for item in self.coverage.modalities_available
            ],
            "observation_count": self.coverage.observation_count,
            "allowed_use": self.coverage.allowed_use,
            "projection": {
                "analyzed_ranges_total": len(self.coverage.analyzed_ranges),
                "analyzed_ranges_omitted": max(0, len(self.coverage.analyzed_ranges) - coverage_range_limit),
                "capability_versions_total": len(self.coverage.capability_versions),
                "capability_versions_omitted": max(0, len(self.coverage.capability_versions) - coverage_capability_limit),
                "excluded_or_failed_ranges_total": len(self.coverage.excluded_or_failed_ranges),
                "excluded_or_failed_ranges_omitted": max(0, len(self.coverage.excluded_or_failed_ranges) - coverage_exception_limit),
            },
        }

        def render() -> dict[str, JsonValue]:
            included = {name: len(items) for name, items in projected.items()}
            omitted = {name: totals[name] - included[name] for name in totals}
            return {
                "evidence_sha256": _payload_sha256(self.model_dump(mode="json")),
                "evidence_role": "benchmark_evidence",
                "evidence_scope": "single_video",
                "source": self.source.model_dump(mode="json"),
                "coverage": coverage_projection,
                "interpreted_at": self.interpreted_at.isoformat(),
                "boundary": self.boundary.model_dump(mode="json"),
                **projected,
                "unknowns": projected["unknowns"],
                "limitations": list(self.limitations),
                "projection": {
                    "total": totals,
                    "included": included,
                    "omitted": omitted,
                    "truncated": any(omitted.values()),
                },
                "epistemic_notice": BENCHMARK_VIDEO_EPISTEMIC_NOTICE,
            }

        compact_items: dict[str, list[dict[str, JsonValue]]] = {
            "machine_observations": [
                {
                    "observation_id": item.observation_id,
                    "kind": item.kind,
                    "statement_excerpt": item.statement[:360],
                    "source_field_paths": list(item.source_field_paths),
                    "time_range": item.time_range.model_dump(mode="json") if item.time_range is not None else None,
                    "confidence": item.confidence,
                }
                for item in self.machine_observations
            ],
            "editorial_interpretations": [
                {
                    "interpretation_id": item.interpretation_id,
                    "statement_excerpt": item.statement[:360],
                    "based_on_observation_ids": list(item.based_on_observation_ids),
                    "uncertainty_excerpt": item.uncertainty[:240],
                    "epistemic_status": item.epistemic_status,
                    "causal_claim": False,
                }
                for item in self.editorial_interpretations
            ],
            "transferable_patterns": [
                {
                    "pattern_id": item.pattern_id,
                    "statement_excerpt": item.statement[:360],
                    "basis_observation_ids": list(item.basis_observation_ids),
                    "basis_interpretation_ids": list(item.basis_interpretation_ids),
                    "transfer_scope": item.transfer_scope,
                    "adaptation_required": True,
                }
                for item in self.transferable_patterns
            ],
            "non_transferable_traits": [
                {
                    "trait_id": item.trait_id,
                    "category": item.category,
                    "description_excerpt": item.description[:280],
                    "reason_excerpt": item.reason[:240],
                }
                for item in self.non_transferable_traits
            ],
            "unknowns": [
                {
                    "unknown_id": item.unknown_id,
                    "question_excerpt": item.question[:280],
                    "why_unresolved_excerpt": item.why_unresolved[:240],
                    "needed_evidence_excerpt": item.needed_evidence[:240] if item.needed_evidence is not None else None,
                }
                for item in self.unknowns
            ],
        }

        if _payload_size(render()) > max_bytes:
            raise ValueError("benchmark video metadata exceeds the Lead projection budget")

        offsets = {name: 0 for name in projected}
        while True:
            advanced = False
            for name in projected:
                offset = offsets[name]
                if offset >= len(compact_items[name]):
                    continue
                projected[name].append(compact_items[name][offset])
                if _payload_size(render()) > max_bytes:
                    projected[name].pop()
                    continue
                offsets[name] += 1
                advanced = True
            if not advanced:
                break
        return render()


def seal_benchmark_video_evidence(
    *,
    project: ProjectRef,
    logical_account: LogicalAccountRef,
    evidence: BenchmarkVideoEvidence,
    source_receipt_artifact: ArtifactEnvelope,
    media_observation_artifact: ArtifactEnvelope,
    source_thread_id: str,
    source_run_id: str,
) -> ArtifactEnvelope:
    """Seal a benchmark-video reading against exact existing media parents."""

    source_artifact = ArtifactEnvelope.model_validate(source_receipt_artifact.model_dump(mode="python"))
    observation_artifact = ArtifactEnvelope.model_validate(media_observation_artifact.model_dump(mode="python"))
    if logical_account.owner_user_id != project.owner_user_id or logical_account.project_id != project.project_id:
        raise ValueError("benchmark video logical account must match project")
    for artifact in (source_artifact, observation_artifact):
        if artifact.project != project:
            raise ValueError("benchmark video parents must match project")
        if artifact.logical_account is not None and artifact.logical_account != logical_account:
            raise ValueError("benchmark video parent logical account must match output logical account")
        if artifact.evidence_role != "benchmark_evidence":
            raise ValueError("benchmark video parents must carry benchmark_evidence role")
    if source_artifact.artifact_type != "media_source_receipt":
        raise ValueError("benchmark video source parent must be a media_source_receipt")
    if observation_artifact.artifact_type != "media_observation":
        raise ValueError("benchmark video observation parent must be a media_observation")
    if observation_artifact.parents != (source_artifact.to_parent_ref(),):
        raise ValueError("media observation must retain the exact media source receipt parent")

    source_receipt = MediaSourceReceipt.model_validate(source_artifact.payload)
    observation = MediaObservationSnapshot.model_validate(observation_artifact.payload)
    if observation.source_ref != source_receipt.source_ref:
        raise ValueError("media observation source_ref must match source receipt")
    if observation.execution.source_content_sha256 is None:
        raise ValueError("benchmark video evidence requires a source content hash")
    if evidence.interpreted_at < observation.observed_at:
        raise ValueError("benchmark video interpretation cannot predate its media observation")

    expected_capability = BenchmarkVideoCapabilityVersion(
        capability_domain=observation.execution.capability_domain,
        capability_tool=observation.execution.capability_tool,
        version=observation.execution.cli_version,
        schema_sha256=observation.execution.schema_sha256,
    )
    if evidence.coverage.capability_versions != (expected_capability,):
        raise ValueError("benchmark video coverage capability_versions must exactly match the media observation execution receipt")

    source_duration = observation.observation.format_meta.duration
    coverage_ranges = (
        *evidence.coverage.analyzed_ranges,
        *(item.time_range for item in evidence.coverage.excluded_or_failed_ranges),
    )
    if any(item.end_seconds > source_duration for item in coverage_ranges):
        raise ValueError("benchmark video coverage ranges cannot exceed the observed source duration")
    for machine_observation in evidence.machine_observations:
        time_range = machine_observation.time_range
        if time_range is None:
            continue
        if not any(analyzed.start_seconds <= time_range.start_seconds and time_range.end_seconds <= analyzed.end_seconds for analyzed in evidence.coverage.analyzed_ranges):
            raise ValueError("machine observation time_range must fall within analyzed_ranges")

    binding = evidence.source
    if binding.source_ref != source_receipt.source_ref:
        raise ValueError("benchmark video source_ref must match source receipt")
    if binding.rights_ref != source_receipt.rights_ref:
        raise ValueError("benchmark video rights_ref must match source receipt")
    if binding.locator_sha256 != source_receipt.locator_sha256:
        raise ValueError("benchmark video locator_sha256 must match source receipt")
    if binding.source_content_sha256 != observation.execution.source_content_sha256:
        raise ValueError("benchmark video source content hash must match media observation")
    if binding.source_receipt_artifact_id != source_artifact.artifact_id:
        raise ValueError("benchmark video source receipt artifact id must match parent")
    if binding.source_receipt_content_sha256 != source_artifact.content_sha256:
        raise ValueError("benchmark video source receipt hash must match parent")
    if binding.media_observation_artifact_id != observation_artifact.artifact_id:
        raise ValueError("benchmark video media observation artifact id must match parent")
    if binding.media_observation_content_sha256 != observation_artifact.content_sha256:
        raise ValueError("benchmark video media observation hash must match parent")

    observation_payload = observation.model_dump(mode="json")
    for machine_observation in evidence.machine_observations:
        missing_paths = tuple(path for path in machine_observation.source_field_paths if not _path_exists(observation_payload, path))
        if missing_paths:
            raise ValueError(f"machine observation source_field_paths do not exist in the exact media observation parent: {missing_paths}")

    return ArtifactEnvelope.seal(
        project=project,
        artifact_type="benchmark_video_evidence",
        version=1,
        payload=evidence.model_dump(mode="json"),
        logical_account=logical_account,
        parents=(source_artifact.to_parent_ref(), observation_artifact.to_parent_ref()),
        evidence_role="benchmark_evidence",
        created_at=evidence.interpreted_at,
        source_thread_id=source_thread_id,
        source_run_id=source_run_id,
    )


__all__ = [
    "BENCHMARK_VIDEO_EPISTEMIC_NOTICE",
    "BenchmarkVideoBoundary",
    "BenchmarkVideoCapabilityVersion",
    "BenchmarkVideoCoverageReceipt",
    "BenchmarkVideoEditorialInterpretation",
    "BenchmarkVideoEvidence",
    "BenchmarkVideoExcludedOrFailedRange",
    "BenchmarkVideoMachineObservation",
    "BenchmarkVideoModalityAvailability",
    "BenchmarkVideoNonTransferableTrait",
    "BenchmarkVideoSourceBinding",
    "BenchmarkVideoTimeRange",
    "BenchmarkVideoTransferablePattern",
    "BenchmarkVideoUnknown",
    "seal_benchmark_video_evidence",
]
