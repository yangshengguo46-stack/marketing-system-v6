from deerflow.incubation.approvals import ApprovalGrant, ApprovalKind
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
from deerflow.incubation.format_decision import (
    FormatAlternative,
    FormatChoice,
    FormatDecision,
    FormatDecisionDraft,
    FormatDecisionStatus,
    FormatKind,
    MessagePlanBinding,
    ResourceMatch,
    seal_format_decision,
)
from deerflow.incubation.judgment import (
    AccountPresentationPlan,
    AudienceHypothesis,
    BriefFact,
    IncubationBrief,
    IncubationJudgment,
    MonetizationHypothesis,
    PersonaDecision,
    PositioningDecision,
    seal_incubation_brief,
    seal_incubation_judgment,
)
from deerflow.incubation.judgment_runtime import (
    INCUBATION_JUDGMENT_SYSTEM_PROMPT,
    MAX_JUDGMENT_MODEL_INPUT_BYTES,
    IncubationJudgmentModelError,
    StructuredJudgmentModel,
    generate_incubation_judgment,
)
from deerflow.incubation.media import (
    EphemeralMediaSource,
    MediaKitExecutionReceipt,
    MediaObservationSnapshot,
    MediaSourceReceipt,
    VideoMetadataObservation,
    seal_media_observation_snapshot,
    seal_media_source_receipt,
)

_PERSISTENCE_EXPORTS = frozenset(
    {
        "AccountConflictError",
        "ApprovalGrantConflictError",
        "ApprovalGrantRejectedError",
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
    "ApprovalGrant",
    "ApprovalGrantConflictError",
    "ApprovalGrantRejectedError",
    "ApprovalKind",
    "AccountPresentationPlan",
    "ArtifactConflictError",
    "ArtifactEnvelope",
    "ArtifactParentRef",
    "BENCHMARK_EPISTEMIC_NOTICE",
    "BenchmarkCoverageReceipt",
    "BenchmarkPostObservation",
    "BenchmarkProfileObservation",
    "BenchmarkRouteReceipt",
    "BenchmarkSnapshot",
    "AudienceHypothesis",
    "BriefFact",
    "ContentRunArtifactSet",
    "EvidenceRole",
    "EvidenceCoverageReceipt",
    "EvidenceItem",
    "EvidenceSnapshot",
    "FormatAlternative",
    "FormatChoice",
    "FormatDecision",
    "FormatDecisionDraft",
    "FormatDecisionStatus",
    "FormatKind",
    "INCUBATION_PROJECT_ID_KEY",
    "INCUBATION_JUDGMENT_SYSTEM_PROMPT",
    "EphemeralMediaSource",
    "IncubationLedgerError",
    "IncubationLedgerRepository",
    "IncubationBrief",
    "IncubationJudgment",
    "IncubationJudgmentModelError",
    "MissingAccountError",
    "MissingParentArtifactError",
    "MissingProjectError",
    "MediaKitExecutionReceipt",
    "MediaObservationSnapshot",
    "MediaSourceReceipt",
    "MAX_JUDGMENT_MODEL_INPUT_BYTES",
    "MessagePlanBinding",
    "MonetizationHypothesis",
    "PlatformAccountRecord",
    "PlatformAccountRef",
    "PersonaDecision",
    "PositioningDecision",
    "ProjectConflictError",
    "ProjectRecord",
    "ProjectRef",
    "ResourceMatch",
    "StructuredJudgmentModel",
    "VideoMetadataObservation",
    "seal_content_world_version",
    "seal_content_run_artifacts",
    "select_used_topic_evidence_snapshots",
    "seal_benchmark_snapshot",
    "seal_evidence_snapshot",
    "seal_format_decision",
    "seal_media_observation_snapshot",
    "seal_media_source_receipt",
    "seal_incubation_brief",
    "seal_incubation_judgment",
    "generate_incubation_judgment",
]
