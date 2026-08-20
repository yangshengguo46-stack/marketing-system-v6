"""Typed, bounded domain priors loaded from an explicitly selected Skill."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Literal

from pydantic import AwareDatetime, Field, TypeAdapter, model_validator

from deerflow.content_intelligence.contracts import ContractModel, NonEmptyStr
from deerflow.skills.frontmatter import split_skill_markdown

INCUBATION_PROFILE_RELATIVE_PATH = Path("references/incubation-profile.json")
INCUBATION_EVAL_MANIFEST_RELATIVE_PATH = Path("evals/evals.json")
INCUBATION_TRIGGER_EVAL_RELATIVE_PATH = Path("evals/trigger_eval_set.json")
MAX_INCUBATION_PROFILE_BYTES = 16_384
MAX_INCUBATION_EVAL_MANIFEST_BYTES = 65_536
MAX_INCUBATION_TRIGGER_EVAL_BYTES = 65_536
MAX_INCUBATION_ACCEPTANCE_RECEIPT_BYTES = 65_536
MAX_INCUBATION_ACCEPTANCE_EVIDENCE_BYTES = 262_144
ACTIVE_INCUBATION_SKILL_STATUS = "active"
REQUIRED_INCUBATION_EVAL_KINDS = frozenset({"trigger", "anti_trigger", "behavior", "held_out"})
INCUBATION_ACCEPTANCE_EVIDENCE_DIR = Path("evidence")

_CLAUSE_BOUNDARIES = "，,。；;！？!?\n"
_BUSINESS_NEGATION_PREFIX = re.compile(
    r"(?:不|没|未)(?:是)?(?:想|打算|准备|愿意|会)?(?:再)?"
    r"(?:做|经营|承接|从事|涉及|包含|提供|碰|接触|主营)[\s、：:]*$"
)
_EDITORIAL_NEGATION_PREFIX = re.compile(r"(?:不要|别|勿)(?:再)?(?:讲|提|聊|说|碰)[\s、：:]*$")
_RELATION_NEGATION_SUFFIX = re.compile(
    r"^(?:业务)?(?:跟|和|与)?(?:我|我们|本店|本公司|本业务)?(?:压根|完全|根本)?"
    r"(?:没有任何关系|没有关系|没关系|无关|不相关|不做|不碰|不涉及|不承接|不经营|不提供)"
)
_SCOPE_NEGATION_SUFFIX = re.compile(r"^(?:不在|不属于)[^，,。；;！？!?]{0,12}(?:范围|业务)")


class IncubationSkillProfileError(ValueError):
    """Raised when a selected Skill cannot provide a trustworthy domain profile."""


class IncubationCandidatePath(ContractModel):
    path: tuple[NonEmptyStr, ...] = Field(min_length=2, max_length=8)
    root: NonEmptyStr
    rationale: NonEmptyStr

    @model_validator(mode="after")
    def bind_root_to_path(self) -> IncubationCandidatePath:
        if self.path[-1] != self.root:
            raise ValueError("candidate path must end at its declared root")
        return self


class IncubationBranchOnlyMarker(ContractModel):
    marker: NonEmptyStr
    reason: NonEmptyStr


class IncubationEvalCase(ContractModel):
    case_id: NonEmptyStr
    case_kind: Literal["trigger", "anti_trigger", "behavior", "held_out"]
    prompt: NonEmptyStr
    expected_output: NonEmptyStr | None = None
    expected_root: NonEmptyStr | None = None
    expectations: tuple[NonEmptyStr, ...] = ()
    forbidden_root_fragments: tuple[NonEmptyStr, ...] = ()

    @model_validator(mode="after")
    def require_an_expected_result(self) -> IncubationEvalCase:
        if self.expected_output is None and self.expected_root is None and not self.expectations:
            raise ValueError("incubation eval case must declare an expected result")
        return self


class IncubationEvalAcceptance(ContractModel):
    status: Literal["passed", "failed", "partial"]
    profile_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    package_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    evidence_ref: NonEmptyStr


class IncubationEvalManifest(ContractModel):
    schema_version: Literal[1]
    skill_name: NonEmptyStr
    profile_version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")
    acceptance: IncubationEvalAcceptance
    evals: tuple[IncubationEvalCase, ...] = Field(min_length=4, max_length=128)

    @model_validator(mode="after")
    def require_unique_cases_and_all_kinds(self) -> IncubationEvalManifest:
        case_ids = [case.case_id for case in self.evals]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("incubation eval case ids must be unique")
        case_kinds = {case.case_kind for case in self.evals}
        if not REQUIRED_INCUBATION_EVAL_KINDS.issubset(case_kinds):
            raise ValueError("incubation eval manifest is missing required case kinds")
        return self


class IncubationTriggerEvalCase(ContractModel):
    query: NonEmptyStr
    should_trigger: bool
    rationale: NonEmptyStr


class IncubationCaseAcceptanceResult(ContractModel):
    case_id: NonEmptyStr
    outcome: Literal["passed", "failed", "not_run"]
    observation: NonEmptyStr
    evidence_ref: NonEmptyStr


class IncubationAcceptanceEvidenceRef(ContractModel):
    evidence_id: NonEmptyStr
    path: NonEmptyStr
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class IncubationPackageAcceptanceReceipt(ContractModel):
    schema_version: Literal[1]
    skill_name: NonEmptyStr
    profile_version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")
    package_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    decision: Literal["active"]
    evaluated_at: AwareDatetime
    source_refs: tuple[IncubationAcceptanceEvidenceRef, ...] = Field(min_length=1, max_length=16)
    case_results: tuple[IncubationCaseAcceptanceResult, ...] = Field(min_length=4, max_length=128)
    limitations: tuple[NonEmptyStr, ...] = Field(default=(), max_length=32)

    @model_validator(mode="after")
    def require_unique_case_results(self) -> IncubationPackageAcceptanceReceipt:
        case_ids = [result.case_id for result in self.case_results]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("incubation acceptance case ids must be unique")
        evidence_ids = [source.evidence_id for source in self.source_refs]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("incubation acceptance evidence ids must be unique")
        evidence_paths = [source.path for source in self.source_refs]
        if len(evidence_paths) != len(set(evidence_paths)):
            raise ValueError("incubation acceptance evidence paths must be unique")
        if any(result.evidence_ref not in evidence_ids for result in self.case_results):
            raise ValueError("incubation acceptance case evidence must resolve through source_refs")
        return self


def incubation_activation_package_sha256(
    *,
    skill_markdown: str,
    profile: IncubationSkillProfile,
    eval_manifest: IncubationEvalManifest,
    trigger_evals: tuple[IncubationTriggerEvalCase, ...],
    acceptance_receipt: IncubationPackageAcceptanceReceipt,
) -> str:
    """Bind every model-visible instruction and every declared evaluation."""

    payload = {
        "skill_markdown": skill_markdown.replace("\r\n", "\n"),
        "profile": profile.model_dump(mode="json"),
        "eval_manifest": eval_manifest.model_dump(
            mode="json",
            exclude={"acceptance": {"package_sha256"}},
        ),
        "trigger_evals": [case.model_dump(mode="json") for case in trigger_evals],
        "acceptance_receipt": acceptance_receipt.model_dump(
            mode="json",
            exclude={"package_sha256"},
        ),
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class IncubationSkillProfile(ContractModel):
    """Domain hypotheses supplied by a Skill, never an adopted root decision."""

    schema_version: Literal[2]
    skill_name: NonEmptyStr
    profile_version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")
    lifecycle_status: Literal["candidate", "shadow", "active", "contested", "superseded", "retired"]
    source_refs: tuple[NonEmptyStr, ...] = Field(min_length=1, max_length=16)
    applies_to: tuple[NonEmptyStr, ...] = Field(min_length=1, max_length=32)
    does_not_apply_to: tuple[NonEmptyStr, ...] = Field(default=(), max_length=32)
    domain: NonEmptyStr
    candidate_paths: tuple[IncubationCandidatePath, ...] = Field(default=(), max_length=8)
    selection_principles: tuple[NonEmptyStr, ...] = Field(default=(), max_length=16)
    default_root: NonEmptyStr | None = None
    branch_only_markers: tuple[IncubationBranchOnlyMarker, ...] = Field(default=(), max_length=32)
    do_not_assume: tuple[NonEmptyStr, ...] = Field(default=(), max_length=32)

    @model_validator(mode="after")
    def reject_duplicate_profile_entries(self) -> IncubationSkillProfile:
        if not self.candidate_paths and not self.selection_principles:
            raise ValueError("incubation profile must declare candidate paths or selection principles")
        roots = [item.root for item in self.candidate_paths]
        if len(roots) != len(set(roots)):
            raise ValueError("incubation profile candidate roots must be unique")
        if self.default_root is not None and self.default_root not in roots:
            raise ValueError("incubation profile default_root must identify one candidate path")
        markers = [item.marker for item in self.branch_only_markers]
        if len(markers) != len(set(markers)):
            raise ValueError("incubation profile branch-only markers must be unique")
        for field_name in (
            "source_refs",
            "applies_to",
            "does_not_apply_to",
            "selection_principles",
            "do_not_assume",
        ):
            entries = getattr(self, field_name)
            normalized = [entry.casefold() for entry in entries]
            if len(normalized) != len(set(normalized)):
                raise ValueError(f"incubation profile {field_name} entries must be unique")
        applies_to = {entry.casefold() for entry in self.applies_to}
        does_not_apply_to = {entry.casefold() for entry in self.does_not_apply_to}
        if applies_to & does_not_apply_to:
            raise ValueError("incubation profile apply and exclusion contracts must not overlap")
        return self

    def content_sha256(self) -> str:
        payload = json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def is_branch_only(self, label: str, *, source_object: str) -> bool:
        """Return true for a local scene unless the user's object names it explicitly."""

        normalized_label = label.casefold()
        return any(marker.marker.casefold() in normalized_label and not _mentions_marker_positively(marker.marker, source_object) for marker in self.branch_only_markers)

    def inactive_map_branches(self, source_object: str) -> tuple[IncubationBranchOnlyMarker, ...]:
        """Return local branches that this business expression did not activate."""

        return tuple(marker for marker in self.branch_only_markers if not _mentions_marker_positively(marker.marker, source_object))

    def decision_projection(self) -> dict[str, Any]:
        return {
            "incubation_skill": self.skill_name,
            "profile_version": self.profile_version,
            "lifecycle_status": self.lifecycle_status,
            "source_refs": list(self.source_refs),
            "applies_to": list(self.applies_to),
            "does_not_apply_to": list(self.does_not_apply_to),
            "domain": self.domain,
            "candidate_paths": [item.model_dump(mode="json") for item in self.candidate_paths],
            "selection_principles": list(self.selection_principles),
            "default_root": self.default_root,
            "branch_only_markers": [item.model_dump(mode="json") for item in self.branch_only_markers],
            "do_not_assume": list(self.do_not_assume),
            "profile_sha256": self.content_sha256(),
        }


def _read_bytes_inside_skill_package(
    skill_root: Path,
    relative_path: Path,
    *,
    max_bytes: int,
    label: str,
) -> bytes:
    if relative_path.is_absolute():
        raise IncubationSkillProfileError(f"The incubation {label} must exist inside the selected skill package.")
    try:
        path = (skill_root / relative_path).resolve(strict=True)
        path.relative_to(skill_root)
        if not path.is_file():
            raise OSError("not a regular file")
        raw = path.read_bytes()
    except (OSError, ValueError) as exc:
        raise IncubationSkillProfileError(f"The incubation {label} must exist inside the selected skill package.") from exc
    if len(raw) > max_bytes:
        raise IncubationSkillProfileError(f"The incubation {label} exceeds the byte limit.")
    return raw


def _read_json_inside_skill_package(
    skill_root: Path,
    relative_path: Path,
    *,
    max_bytes: int,
    label: str,
) -> Any:
    raw = _read_bytes_inside_skill_package(
        skill_root,
        relative_path,
        max_bytes=max_bytes,
        label=label,
    )
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise IncubationSkillProfileError(f"The incubation {label} is invalid.") from exc


def validate_incubation_activation_evidence(
    *,
    skill_root: Path,
    skill_markdown: str,
    profile: IncubationSkillProfile,
    eval_manifest: IncubationEvalManifest,
) -> str:
    """Validate the package-bound acceptance receipt and return its digest."""

    try:
        trigger_payload = _read_json_inside_skill_package(
            skill_root,
            INCUBATION_TRIGGER_EVAL_RELATIVE_PATH,
            max_bytes=MAX_INCUBATION_TRIGGER_EVAL_BYTES,
            label="trigger eval set",
        )
        trigger_evals = TypeAdapter(tuple[IncubationTriggerEvalCase, ...]).validate_python(trigger_payload)
    except ValueError as exc:
        if isinstance(exc, IncubationSkillProfileError):
            raise
        raise IncubationSkillProfileError("The incubation trigger eval set is invalid.") from exc
    if not trigger_evals or not any(case.should_trigger for case in trigger_evals) or not any(not case.should_trigger for case in trigger_evals):
        raise IncubationSkillProfileError("The incubation trigger eval set must contain positive and negative cases.")
    normalized_queries = [case.query.casefold() for case in trigger_evals]
    if len(normalized_queries) != len(set(normalized_queries)):
        raise IncubationSkillProfileError("The incubation trigger eval set contains duplicate cases.")

    if eval_manifest.acceptance.status != "passed":
        raise IncubationSkillProfileError("The incubation eval manifest does not record a passing acceptance result.")
    if eval_manifest.acceptance.profile_sha256 != profile.content_sha256():
        raise IncubationSkillProfileError("The incubation eval acceptance does not match the accepted profile content.")

    receipt_payload = _read_json_inside_skill_package(
        skill_root,
        INCUBATION_EVAL_MANIFEST_RELATIVE_PATH.parent / Path(eval_manifest.acceptance.evidence_ref),
        max_bytes=MAX_INCUBATION_ACCEPTANCE_RECEIPT_BYTES,
        label="acceptance receipt",
    )
    try:
        receipt = IncubationPackageAcceptanceReceipt.model_validate(receipt_payload)
    except ValueError as exc:
        raise IncubationSkillProfileError("The incubation acceptance receipt is invalid.") from exc
    expected_case_ids = {case.case_id for case in eval_manifest.evals}
    receipt_case_ids = {result.case_id for result in receipt.case_results}
    if receipt.skill_name != profile.skill_name or receipt.profile_version != profile.profile_version or receipt_case_ids != expected_case_ids or any(result.outcome != "passed" for result in receipt.case_results):
        raise IncubationSkillProfileError("The incubation acceptance receipt does not verify every declared case.")
    for evidence_ref in receipt.source_refs:
        evidence_path = Path(evidence_ref.path)
        if evidence_path.is_absolute() or ".." in evidence_path.parts or not evidence_path.is_relative_to(INCUBATION_ACCEPTANCE_EVIDENCE_DIR):
            raise IncubationSkillProfileError("The incubation acceptance evidence must stay inside the receipt's evidence directory.")
        evidence_raw = _read_bytes_inside_skill_package(
            skill_root,
            INCUBATION_EVAL_MANIFEST_RELATIVE_PATH.parent / evidence_path,
            max_bytes=MAX_INCUBATION_ACCEPTANCE_EVIDENCE_BYTES,
            label="acceptance evidence",
        )
        if hashlib.sha256(evidence_raw).hexdigest() != evidence_ref.sha256:
            raise IncubationSkillProfileError("The incubation acceptance evidence does not match its recorded digest.")

    package_sha256 = incubation_activation_package_sha256(
        skill_markdown=skill_markdown,
        profile=profile,
        eval_manifest=eval_manifest,
        trigger_evals=trigger_evals,
        acceptance_receipt=receipt,
    )
    if eval_manifest.acceptance.package_sha256 != package_sha256:
        raise IncubationSkillProfileError("The incubation activation package does not match its accepted content.")
    if receipt.package_sha256 != package_sha256:
        raise IncubationSkillProfileError("The incubation acceptance receipt does not verify the complete activation package.")
    return package_sha256


def _mentions_marker_positively(marker: str, source_object: str) -> bool:
    normalized_marker = marker.casefold()
    normalized_source = source_object.casefold()
    cursor = 0
    while (index := normalized_source.find(normalized_marker, cursor)) >= 0:
        after_start = index + len(normalized_marker)
        clause_start = max((normalized_source.rfind(boundary, 0, index) for boundary in _CLAUSE_BOUNDARIES), default=-1) + 1
        clause_ends = [end for boundary in _CLAUSE_BOUNDARIES if (end := normalized_source.find(boundary, after_start)) >= 0]
        clause_end = min(clause_ends, default=len(normalized_source))
        before = normalized_source[clause_start:index]
        after = normalized_source[after_start:clause_end]
        negated = (
            _BUSINESS_NEGATION_PREFIX.search(before)
            or _EDITORIAL_NEGATION_PREFIX.search(before)
            or (before.rstrip().endswith("非") and re.match(r"^\s*(?:业务|服务|赛道|领域)", after))
            or (re.search(r"(?:不要|别|勿)(?:再)?往\s*$", before) and re.match(r"^\s*上?(?:扯|带|引)", after))
            or _RELATION_NEGATION_SUFFIX.search(after)
            or _SCOPE_NEGATION_SUFFIX.search(after)
        )
        if not negated:
            return True
        cursor = after_start
    return False


def load_incubation_skill_profile(
    skill_name: str,
    *,
    user_id: str | None = None,
    storage: Any | None = None,
) -> IncubationSkillProfile:
    """Load one enabled Skill's optional incubation profile without reading its prose."""

    normalized_name = skill_name.strip()
    if not normalized_name:
        raise IncubationSkillProfileError("incubation skill name cannot be empty")
    if not normalized_name.startswith("incubate-"):
        raise IncubationSkillProfileError("incubation skill names must use the incubate- namespace")

    if storage is None:
        if user_id is None:
            from deerflow.skills.storage import get_or_new_skill_storage

            storage = get_or_new_skill_storage()
        else:
            from deerflow.skills.storage import get_or_new_user_skill_storage

            storage = get_or_new_user_skill_storage(user_id)

    selected = next(
        (skill for skill in storage.load_skills(enabled_only=True) if skill.name == normalized_name),
        None,
    )
    if selected is None:
        raise IncubationSkillProfileError(f"No enabled incubation skill named {normalized_name!r} is available.")

    try:
        skill_root = selected.skill_dir.resolve(strict=True)
        profile_path = (selected.skill_dir / INCUBATION_PROFILE_RELATIVE_PATH).resolve(strict=True)
        profile_path.relative_to(skill_root)
    except (FileNotFoundError, OSError, ValueError) as exc:
        raise IncubationSkillProfileError("The incubation profile must exist inside the selected skill package.") from exc

    if not profile_path.is_file():
        raise IncubationSkillProfileError("The selected incubation profile is not a regular file.")
    try:
        raw = profile_path.read_bytes()
    except OSError as exc:
        raise IncubationSkillProfileError("The selected incubation profile could not be read.") from exc
    if len(raw) > MAX_INCUBATION_PROFILE_BYTES:
        raise IncubationSkillProfileError("The selected incubation profile exceeds the byte limit.")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise IncubationSkillProfileError("The selected incubation profile is invalid.") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != 2:
        raise IncubationSkillProfileError("Unsupported incubation profile schema_version; expected 2.")
    try:
        profile = IncubationSkillProfile.model_validate(payload)
    except ValueError as exc:
        raise IncubationSkillProfileError("The selected incubation profile is invalid.") from exc
    if profile.skill_name != selected.name:
        raise IncubationSkillProfileError("The incubation profile skill_name does not match the selected skill.")
    if profile.lifecycle_status != ACTIVE_INCUBATION_SKILL_STATUS:
        raise IncubationSkillProfileError(f"The selected incubation profile is not active (status={profile.lifecycle_status!r}).")

    try:
        skill_text = selected.skill_file.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise IncubationSkillProfileError("The selected incubation Skill metadata could not be read.") from exc
    skill_parts, skill_error = split_skill_markdown(skill_text)
    if skill_parts is None:
        raise IncubationSkillProfileError(f"The selected incubation Skill metadata is invalid: {skill_error}")
    package_metadata = skill_parts.metadata.get("metadata")
    if not isinstance(package_metadata, dict):
        raise IncubationSkillProfileError("The selected incubation Skill must declare versioned lifecycle metadata.")
    package_version = str(package_metadata.get("version") or "").strip()
    package_lifecycle = str(package_metadata.get("lifecycle") or "").strip()
    if package_version != profile.profile_version or package_lifecycle != profile.lifecycle_status:
        raise IncubationSkillProfileError("The incubation profile version or lifecycle does not match SKILL.md metadata.")

    try:
        eval_path = (selected.skill_dir / INCUBATION_EVAL_MANIFEST_RELATIVE_PATH).resolve(strict=True)
        eval_path.relative_to(skill_root)
    except (FileNotFoundError, OSError, ValueError) as exc:
        raise IncubationSkillProfileError("The incubation eval manifest must exist inside the selected skill package.") from exc
    try:
        eval_raw = eval_path.read_bytes()
    except OSError as exc:
        raise IncubationSkillProfileError("The incubation eval manifest could not be read.") from exc
    if len(eval_raw) > MAX_INCUBATION_EVAL_MANIFEST_BYTES:
        raise IncubationSkillProfileError("The incubation eval manifest exceeds the byte limit.")
    try:
        eval_manifest = json.loads(eval_raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise IncubationSkillProfileError("The incubation eval manifest is invalid.") from exc
    try:
        manifest = IncubationEvalManifest.model_validate(eval_manifest)
    except ValueError as exc:
        raise IncubationSkillProfileError("The incubation eval manifest is invalid.") from exc
    if manifest.skill_name != profile.skill_name:
        raise IncubationSkillProfileError("The incubation eval manifest skill_name does not match the profile.")
    if manifest.profile_version != profile.profile_version:
        raise IncubationSkillProfileError("The incubation eval manifest version does not match the profile.")
    validate_incubation_activation_evidence(
        skill_root=skill_root,
        skill_markdown=skill_text,
        profile=profile,
        eval_manifest=manifest,
    )
    return profile


__all__ = [
    "INCUBATION_PROFILE_RELATIVE_PATH",
    "INCUBATION_EVAL_MANIFEST_RELATIVE_PATH",
    "MAX_INCUBATION_PROFILE_BYTES",
    "MAX_INCUBATION_EVAL_MANIFEST_BYTES",
    "MAX_INCUBATION_TRIGGER_EVAL_BYTES",
    "MAX_INCUBATION_ACCEPTANCE_RECEIPT_BYTES",
    "ACTIVE_INCUBATION_SKILL_STATUS",
    "REQUIRED_INCUBATION_EVAL_KINDS",
    "IncubationBranchOnlyMarker",
    "IncubationCandidatePath",
    "IncubationEvalAcceptance",
    "IncubationEvalCase",
    "IncubationEvalManifest",
    "IncubationTriggerEvalCase",
    "IncubationCaseAcceptanceResult",
    "IncubationPackageAcceptanceReceipt",
    "IncubationSkillProfile",
    "IncubationSkillProfileError",
    "incubation_activation_package_sha256",
    "load_incubation_skill_profile",
    "validate_incubation_activation_evidence",
]
