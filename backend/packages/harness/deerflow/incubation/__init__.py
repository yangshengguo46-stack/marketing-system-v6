from deerflow.incubation.account_strategy import (
    AccountStrategyRepository,
    PreparedAccountStrategy,
    confirm_account_strategy,
    prepare_account_strategy,
    select_current_account_strategy,
)
from deerflow.incubation.adapted_draft import (
    AdaptedDraft,
    AdaptedDraftDraft,
    NarrativeTreatment,
    PresentationMode,
    PresentationUnit,
    PresentationUnitDraft,
    SourceExcerptAnchor,
    seal_adapted_draft,
)
from deerflow.incubation.adapted_draft_runtime import (
    ADAPTED_DRAFT_MODEL_INPUT_MAX_BYTES,
    ADAPTED_DRAFT_SYSTEM_PROMPT,
    AdaptedDraftModelError,
    StructuredAdaptedDraftModel,
    generate_adapted_draft,
)
from deerflow.incubation.approvals import ApprovalGrant, ApprovalKind
from deerflow.incubation.audience_intelligence import (
    HLLM_ADAPTER_VERSION,
    HLLM_UPSTREAM_COMMIT,
    MAX_HLLM_SEQUENCE_EVENTS,
    AudienceEvidenceArtifact,
    AudienceEvidenceSnapshot,
    HLLMBehaviorEvent,
    HLLMBehaviorSequence,
    HLLMInferenceEvent,
    HLLMInferenceReceipt,
    HLLMInferenceRequest,
    ObservedAudienceBehaviorBatch,
    ObservedAudienceProfile,
    ObservedAudienceSlice,
    build_hllm_inference_request,
    pseudonymize_audience_actor,
    seal_observed_audience_behavior_evidence,
    seal_observed_audience_evidence,
)
from deerflow.incubation.benchmark import (
    BENCHMARK_EPISTEMIC_NOTICE,
    BenchmarkCoverageReceipt,
    BenchmarkPostObservation,
    BenchmarkProfileObservation,
    BenchmarkRouteReceipt,
    BenchmarkSnapshot,
    seal_benchmark_snapshot,
)
from deerflow.incubation.brief_runtime import build_minimal_incubation_brief
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
    BaseDraftBinding,
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
from deerflow.incubation.format_runtime import (
    FORMAT_DECISION_MODEL_INPUT_MAX_BYTES,
    FORMAT_DECISION_SYSTEM_PROMPT,
    FormatDecisionModelError,
    StructuredFormatModel,
    generate_format_decision,
)
from deerflow.incubation.judgment import (
    AccountBusinessIntent,
    AccountPresentationPlan,
    AccountRouteOption,
    AccountStrategyStatus,
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
    AccountRouteOptionDraft,
    AccountStrategyProposalDraft,
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
from deerflow.incubation.media_artifact import (
    MediaArtifact,
    MediaArtifactDraft,
    MediaArtifactStage,
    MediaInputBinding,
    MediaProductionBinding,
    MediaQCCheck,
    MediaQCCheckStatus,
    MediaQCSummary,
    build_media_production_binding,
    seal_media_artifact,
)
from deerflow.incubation.production_plan import (
    AssemblyStep,
    ProductionAction,
    ProductionActionKind,
    ProductionAssetKind,
    ProductionAssetRequirement,
    ProductionAssetSource,
    ProductionPlan,
    ProductionPlanDraft,
    ProductionPlanStatus,
    seal_production_plan,
    validate_production_plan_parents,
)
from deerflow.incubation.production_runtime import (
    PRODUCTION_PLAN_MODEL_INPUT_MAX_BYTES,
    PRODUCTION_PLAN_SYSTEM_PROMPT,
    ProductionPlanModelError,
    StructuredProductionPlanModel,
    generate_production_plan,
)
from deerflow.incubation.project_bootstrap import (
    implicit_project_display_name,
    implicit_thread_project_ref,
)
from deerflow.incubation.project_evidence import (
    MAX_AUDIENCE_JUDGMENT_EVIDENCE,
    MAX_BENCHMARK_JUDGMENT_EVIDENCE,
    ProjectEvidenceSelection,
    select_project_judgment_evidence,
)
from deerflow.incubation.root_feedback import (
    RootCandidateDecision,
    RootCandidateFeedback,
    RootCandidateOrigin,
    RootFeasibility,
    RootFeedbackErrorKind,
    RootFeedbackRecord,
    RootFeedbackStatus,
    seal_root_feedback_record,
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
_MEDIA_EXECUTION_EXPORTS = frozenset(
    {
        "MediaKitLocalProductionOperation",
        "execute_local_media_operation",
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
    if name in _MEDIA_EXECUTION_EXPORTS:
        from deerflow.incubation import media_execution

        return getattr(media_execution, name)
    raise AttributeError(name)


__all__ = [
    "ADAPTED_DRAFT_MODEL_INPUT_MAX_BYTES",
    "ADAPTED_DRAFT_SYSTEM_PROMPT",
    "AccountConflictError",
    "ApprovalGrant",
    "ApprovalGrantConflictError",
    "ApprovalGrantRejectedError",
    "ApprovalKind",
    "AssemblyStep",
    "AccountBusinessIntent",
    "AccountPresentationPlan",
    "AccountRouteOption",
    "AccountRouteOptionDraft",
    "AccountStrategyProposalDraft",
    "AccountStrategyStatus",
    "AccountStrategyRepository",
    "AdaptedDraft",
    "AdaptedDraftDraft",
    "AdaptedDraftModelError",
    "ArtifactConflictError",
    "ArtifactEnvelope",
    "ArtifactParentRef",
    "BENCHMARK_EPISTEMIC_NOTICE",
    "BaseDraftBinding",
    "BenchmarkCoverageReceipt",
    "BenchmarkPostObservation",
    "BenchmarkProfileObservation",
    "BenchmarkRouteReceipt",
    "BenchmarkSnapshot",
    "build_minimal_incubation_brief",
    "AudienceHypothesis",
    "AudienceEvidenceArtifact",
    "AudienceEvidenceSnapshot",
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
    "FORMAT_DECISION_MODEL_INPUT_MAX_BYTES",
    "FORMAT_DECISION_SYSTEM_PROMPT",
    "FormatDecisionModelError",
    "HLLM_ADAPTER_VERSION",
    "HLLM_UPSTREAM_COMMIT",
    "HLLMBehaviorEvent",
    "HLLMBehaviorSequence",
    "HLLMInferenceEvent",
    "HLLMInferenceReceipt",
    "HLLMInferenceRequest",
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
    "MediaArtifact",
    "MediaArtifactDraft",
    "MediaArtifactStage",
    "MediaInputBinding",
    "MediaKitLocalProductionOperation",
    "MediaProductionBinding",
    "MediaObservationSnapshot",
    "MediaQCCheck",
    "MediaQCCheckStatus",
    "MediaQCSummary",
    "MediaSourceReceipt",
    "MAX_JUDGMENT_MODEL_INPUT_BYTES",
    "MAX_AUDIENCE_JUDGMENT_EVIDENCE",
    "MAX_BENCHMARK_JUDGMENT_EVIDENCE",
    "MAX_HLLM_SEQUENCE_EVENTS",
    "MessagePlanBinding",
    "MonetizationHypothesis",
    "NarrativeTreatment",
    "ObservedAudienceBehaviorBatch",
    "ObservedAudienceProfile",
    "ObservedAudienceSlice",
    "PlatformAccountRecord",
    "PlatformAccountRef",
    "PreparedAccountStrategy",
    "PersonaDecision",
    "PositioningDecision",
    "PresentationMode",
    "PresentationUnit",
    "PresentationUnitDraft",
    "ProjectConflictError",
    "ProjectRecord",
    "ProjectRef",
    "ProductionAction",
    "ProductionActionKind",
    "ProductionAssetKind",
    "ProductionAssetRequirement",
    "ProductionAssetSource",
    "ProductionPlan",
    "ProductionPlanDraft",
    "ProductionPlanModelError",
    "ProductionPlanStatus",
    "PRODUCTION_PLAN_MODEL_INPUT_MAX_BYTES",
    "PRODUCTION_PLAN_SYSTEM_PROMPT",
    "ProjectEvidenceSelection",
    "ResourceMatch",
    "RootCandidateDecision",
    "RootCandidateFeedback",
    "RootCandidateOrigin",
    "RootFeasibility",
    "RootFeedbackErrorKind",
    "RootFeedbackRecord",
    "RootFeedbackStatus",
    "StructuredJudgmentModel",
    "StructuredAdaptedDraftModel",
    "StructuredFormatModel",
    "StructuredProductionPlanModel",
    "VideoMetadataObservation",
    "SourceExcerptAnchor",
    "seal_content_world_version",
    "build_media_production_binding",
    "build_hllm_inference_request",
    "pseudonymize_audience_actor",
    "prepare_account_strategy",
    "confirm_account_strategy",
    "seal_content_run_artifacts",
    "select_used_topic_evidence_snapshots",
    "select_project_judgment_evidence",
    "select_current_account_strategy",
    "seal_benchmark_snapshot",
    "seal_evidence_snapshot",
    "seal_format_decision",
    "seal_media_observation_snapshot",
    "seal_media_artifact",
    "seal_media_source_receipt",
    "seal_production_plan",
    "seal_root_feedback_record",
    "seal_incubation_brief",
    "seal_incubation_judgment",
    "seal_observed_audience_behavior_evidence",
    "seal_observed_audience_evidence",
    "generate_incubation_judgment",
    "generate_adapted_draft",
    "generate_format_decision",
    "generate_production_plan",
    "implicit_project_display_name",
    "implicit_thread_project_ref",
    "execute_local_media_operation",
    "seal_adapted_draft",
    "validate_production_plan_parents",
]
