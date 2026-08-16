from deerflow.incubation.benchmark import (
    BENCHMARK_EPISTEMIC_NOTICE,
    BenchmarkCoverageReceipt,
    BenchmarkPostObservation,
    BenchmarkProfileObservation,
    BenchmarkRouteReceipt,
    BenchmarkSnapshot,
    seal_benchmark_snapshot,
)
from deerflow.incubation.contracts import (
    INCUBATION_PROJECT_ID_KEY,
    ArtifactEnvelope,
    ArtifactParentRef,
    EvidenceRole,
    PlatformAccountRecord,
    PlatformAccountRef,
    ProjectRecord,
    ProjectRef,
)
from deerflow.incubation.evidence import (
    EvidenceCoverageReceipt,
    EvidenceItem,
    EvidenceSnapshot,
    seal_evidence_snapshot,
)
from deerflow.incubation.media import (
    EphemeralMediaSource,
    MediaSourceReceipt,
    seal_media_source_receipt,
)

_PERSISTENCE_EXPORTS = frozenset(
    {
        "AccountConflictError",
        "ArtifactConflictError",
        "IncubationLedgerError",
        "IncubationLedgerRepository",
        "MissingAccountError",
        "MissingParentArtifactError",
        "MissingProjectError",
        "ProjectConflictError",
    }
)

_CONTENT_EXPORTS = frozenset({"seal_content_world_version"})
_CONTENT_RUN_EXPORTS = frozenset(
    {
        "ContentRunArtifactSet",
        "seal_content_run_artifacts",
        "select_used_topic_evidence_snapshots",
    }
)


def __getattr__(name: str):
    if name in _PERSISTENCE_EXPORTS:
        from deerflow.persistence import incubation_ledger

        return getattr(incubation_ledger, name)
    if name in _CONTENT_EXPORTS:
        from deerflow.incubation import content_world

        return getattr(content_world, name)
    if name in _CONTENT_RUN_EXPORTS:
        from deerflow.incubation import content_run

        return getattr(content_run, name)
    raise AttributeError(name)


__all__ = [
    "AccountConflictError",
    "ArtifactConflictError",
    "ArtifactEnvelope",
    "ArtifactParentRef",
    "BENCHMARK_EPISTEMIC_NOTICE",
    "BenchmarkCoverageReceipt",
    "BenchmarkPostObservation",
    "BenchmarkProfileObservation",
    "BenchmarkRouteReceipt",
    "BenchmarkSnapshot",
    "ContentRunArtifactSet",
    "EvidenceRole",
    "EvidenceCoverageReceipt",
    "EvidenceItem",
    "EvidenceSnapshot",
    "INCUBATION_PROJECT_ID_KEY",
    "EphemeralMediaSource",
    "IncubationLedgerError",
    "IncubationLedgerRepository",
    "MissingAccountError",
    "MissingParentArtifactError",
    "MissingProjectError",
    "MediaSourceReceipt",
    "PlatformAccountRecord",
    "PlatformAccountRef",
    "ProjectConflictError",
    "ProjectRecord",
    "ProjectRef",
    "seal_content_world_version",
    "seal_content_run_artifacts",
    "select_used_topic_evidence_snapshots",
    "seal_benchmark_snapshot",
    "seal_evidence_snapshot",
    "seal_media_source_receipt",
]
