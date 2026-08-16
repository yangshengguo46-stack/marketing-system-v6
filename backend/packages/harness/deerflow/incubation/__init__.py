from deerflow.incubation.contracts import (
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


def __getattr__(name: str):
    if name in _PERSISTENCE_EXPORTS:
        from deerflow.persistence import incubation_ledger

        return getattr(incubation_ledger, name)
    if name in _CONTENT_EXPORTS:
        from deerflow.incubation import content_world

        return getattr(content_world, name)
    raise AttributeError(name)


__all__ = [
    "AccountConflictError",
    "ArtifactConflictError",
    "ArtifactEnvelope",
    "ArtifactParentRef",
    "EvidenceRole",
    "EvidenceCoverageReceipt",
    "EvidenceItem",
    "EvidenceSnapshot",
    "IncubationLedgerError",
    "IncubationLedgerRepository",
    "MissingAccountError",
    "MissingParentArtifactError",
    "MissingProjectError",
    "PlatformAccountRecord",
    "PlatformAccountRef",
    "ProjectConflictError",
    "ProjectRecord",
    "ProjectRef",
    "seal_content_world_version",
    "seal_evidence_snapshot",
]
