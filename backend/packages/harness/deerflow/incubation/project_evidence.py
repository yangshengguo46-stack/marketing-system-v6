from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from typing import Literal

from pydantic import Field, model_validator

from deerflow.incubation.benchmark import BenchmarkSnapshot
from deerflow.incubation.contracts import (
    ArtifactEnvelope,
    IncubationContract,
    NonEmptyStr,
    ProjectRef,
)
from deerflow.incubation.evidence import EvidenceSnapshot

MAX_BENCHMARK_JUDGMENT_EVIDENCE = 2
MAX_AUDIENCE_JUDGMENT_EVIDENCE = 2

AudienceEvidenceRole = Literal[
    "owned_audience_observation",
    "benchmark_audience_observation",
]
MissingProjectEvidence = Literal["benchmark_evidence", "audience_evidence"]

_AUDIENCE_EVIDENCE_ROLES = frozenset(
    {
        "owned_audience_observation",
        "benchmark_audience_observation",
    }
)


class ProjectEvidenceSelection(IncubationContract):
    """Bounded formal evidence that may parent an IncubationJudgment."""

    project: ProjectRef
    benchmark_evidence_artifacts: tuple[ArtifactEnvelope, ...] = ()
    audience_evidence_artifacts: tuple[ArtifactEnvelope, ...] = ()
    missing: tuple[MissingProjectEvidence, ...] = ()
    limitations: tuple[NonEmptyStr, ...] = ()
    input_artifact_count: int = Field(ge=0)
    unique_artifact_count: int = Field(ge=0)
    duplicate_count: int = Field(ge=0)
    rejected_formal_candidate_count: int = Field(ge=0)
    truncated_benchmark_count: int = Field(ge=0)
    truncated_audience_count: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_selection(self) -> ProjectEvidenceSelection:
        if len(self.benchmark_evidence_artifacts) > MAX_BENCHMARK_JUDGMENT_EVIDENCE:
            raise ValueError("too many benchmark evidence artifacts")
        if len(self.audience_evidence_artifacts) > MAX_AUDIENCE_JUDGMENT_EVIDENCE:
            raise ValueError("too many audience evidence artifacts")
        selected = (*self.benchmark_evidence_artifacts, *self.audience_evidence_artifacts)
        if len({artifact.artifact_id for artifact in selected}) != len(selected):
            raise ValueError("selected project evidence artifacts must be unique")
        if any(artifact.project != self.project for artifact in selected):
            raise ValueError("selected evidence must belong to the same project")
        return self


def _duplicate_choice_key(artifact: ArtifactEnvelope) -> tuple[object, ...]:
    return (
        -artifact.created_at.timestamp(),
        artifact.source_thread_id,
        artifact.source_run_id,
    )


def _selection_order(artifact: ArtifactEnvelope) -> tuple[object, ...]:
    return (-artifact.created_at.timestamp(), artifact.artifact_id)


def _deduplicate_artifacts(
    artifacts: tuple[ArtifactEnvelope, ...],
) -> tuple[tuple[ArtifactEnvelope, ...], int]:
    grouped: dict[str, list[ArtifactEnvelope]] = defaultdict(list)
    for artifact in artifacts:
        grouped[artifact.artifact_id].append(artifact)
    unique = tuple(min(grouped[artifact_id], key=_duplicate_choice_key) for artifact_id in sorted(grouped))
    return unique, len(artifacts) - len(unique)


def _is_formal_benchmark(artifact: ArtifactEnvelope) -> bool:
    if artifact.artifact_type != "benchmark_snapshot":
        return False
    if artifact.evidence_role != "benchmark_evidence":
        return False
    BenchmarkSnapshot.model_validate(artifact.payload)
    return True


def _is_formal_audience(artifact: ArtifactEnvelope) -> bool:
    if artifact.artifact_type != "evidence_snapshot":
        return False
    if artifact.evidence_role not in _AUDIENCE_EVIDENCE_ROLES:
        return False
    snapshot = EvidenceSnapshot.model_validate(artifact.payload)
    if snapshot.evidence_role != artifact.evidence_role or not snapshot.items:
        return False
    return {item.provenance for item in snapshot.items} == {"observed"}


def _looks_like_formal_candidate(artifact: ArtifactEnvelope) -> bool:
    if artifact.artifact_type == "audience_behavior_snapshot":
        return False
    return artifact.artifact_type == "benchmark_snapshot" or artifact.evidence_role == "benchmark_evidence" or artifact.evidence_role in _AUDIENCE_EVIDENCE_ROLES


def select_project_judgment_evidence(
    *,
    project: ProjectRef,
    artifacts: Iterable[ArtifactEnvelope],
) -> ProjectEvidenceSelection:
    """Select only formal, same-project evidence for one incubation judgment.

    Absence is reported but remains non-blocking. Cross-project input is rejected
    because silently filtering it could hide an ownership or caller-scope bug.
    """

    validated: list[ArtifactEnvelope] = []
    for artifact in artifacts:
        if not isinstance(artifact, ArtifactEnvelope):
            raise TypeError("project evidence inputs must be ArtifactEnvelope values")
        current = ArtifactEnvelope.model_validate(artifact.model_dump(mode="python"))
        if current.project != project:
            raise ValueError("all project evidence inputs must belong to the same project")
        validated.append(current)

    unique, duplicate_count = _deduplicate_artifacts(tuple(validated))
    benchmark_candidates: list[ArtifactEnvelope] = []
    audience_candidates: list[ArtifactEnvelope] = []
    rejected_formal_candidate_count = 0

    for artifact in unique:
        if not _looks_like_formal_candidate(artifact):
            continue
        try:
            if _is_formal_benchmark(artifact):
                benchmark_candidates.append(artifact)
            elif _is_formal_audience(artifact):
                audience_candidates.append(artifact)
            else:
                rejected_formal_candidate_count += 1
        except (TypeError, ValueError):
            rejected_formal_candidate_count += 1

    ordered_benchmarks = tuple(sorted(benchmark_candidates, key=_selection_order))
    ordered_audiences = tuple(sorted(audience_candidates, key=_selection_order))
    selected_benchmarks = ordered_benchmarks[:MAX_BENCHMARK_JUDGMENT_EVIDENCE]
    selected_audiences = ordered_audiences[:MAX_AUDIENCE_JUDGMENT_EVIDENCE]
    truncated_benchmark_count = len(ordered_benchmarks) - len(selected_benchmarks)
    truncated_audience_count = len(ordered_audiences) - len(selected_audiences)

    missing: list[MissingProjectEvidence] = []
    limitations: list[str] = []
    if duplicate_count:
        limitations.append(f"Ignored {duplicate_count} duplicate artifact occurrence(s).")
    if rejected_formal_candidate_count:
        limitations.append(f"Excluded {rejected_formal_candidate_count} artifact(s) that did not satisfy the formal evidence contracts.")
    if truncated_benchmark_count:
        limitations.append(f"Selected the newest {MAX_BENCHMARK_JUDGMENT_EVIDENCE} formal benchmark snapshot(s); omitted {truncated_benchmark_count} older snapshot(s).")
    if truncated_audience_count:
        limitations.append(f"Selected the newest {MAX_AUDIENCE_JUDGMENT_EVIDENCE} formal audience snapshot(s); omitted {truncated_audience_count} older snapshot(s).")
    if not selected_benchmarks:
        missing.append("benchmark_evidence")
        limitations.append("No formal benchmark snapshot is available; incubation judgment may proceed without benchmark evidence.")
    if not selected_audiences:
        missing.append("audience_evidence")
        limitations.append("No formal audience snapshot is available; incubation judgment may proceed without audience evidence.")

    return ProjectEvidenceSelection(
        project=project,
        benchmark_evidence_artifacts=selected_benchmarks,
        audience_evidence_artifacts=selected_audiences,
        missing=tuple(missing),
        limitations=tuple(limitations),
        input_artifact_count=len(validated),
        unique_artifact_count=len(unique),
        duplicate_count=duplicate_count,
        rejected_formal_candidate_count=rejected_formal_candidate_count,
        truncated_benchmark_count=truncated_benchmark_count,
        truncated_audience_count=truncated_audience_count,
    )


__all__ = [
    "MAX_AUDIENCE_JUDGMENT_EVIDENCE",
    "MAX_BENCHMARK_JUDGMENT_EVIDENCE",
    "ProjectEvidenceSelection",
    "select_project_judgment_evidence",
]
