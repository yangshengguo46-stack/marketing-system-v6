"""Typed, bounded domain priors loaded from an explicitly selected Skill."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, model_validator

from deerflow.content_intelligence.contracts import ContractModel, NonEmptyStr

INCUBATION_PROFILE_RELATIVE_PATH = Path("references/incubation-profile.json")
MAX_INCUBATION_PROFILE_BYTES = 16_384


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


class IncubationSkillProfile(ContractModel):
    """Domain hypotheses supplied by a Skill, never an adopted root decision."""

    schema_version: Literal[1]
    skill_name: NonEmptyStr
    domain: NonEmptyStr
    candidate_paths: tuple[IncubationCandidatePath, ...] = Field(min_length=1, max_length=8)
    default_root: NonEmptyStr | None = None
    branch_only_markers: tuple[IncubationBranchOnlyMarker, ...] = Field(default=(), max_length=32)
    do_not_assume: tuple[NonEmptyStr, ...] = Field(default=(), max_length=32)

    @model_validator(mode="after")
    def reject_duplicate_profile_entries(self) -> IncubationSkillProfile:
        roots = [item.root for item in self.candidate_paths]
        if len(roots) != len(set(roots)):
            raise ValueError("incubation profile candidate roots must be unique")
        if self.default_root is not None and self.default_root not in roots:
            raise ValueError("incubation profile default_root must identify one candidate path")
        markers = [item.marker for item in self.branch_only_markers]
        if len(markers) != len(set(markers)):
            raise ValueError("incubation profile branch-only markers must be unique")
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
        normalized_source = source_object.casefold()
        return any(marker.marker.casefold() in normalized_label and marker.marker.casefold() not in normalized_source for marker in self.branch_only_markers)

    def inactive_map_branches(self, source_object: str) -> tuple[IncubationBranchOnlyMarker, ...]:
        """Return local branches that this business expression did not activate."""

        normalized_source = source_object.casefold()
        return tuple(marker for marker in self.branch_only_markers if marker.marker.casefold() not in normalized_source)

    def decision_projection(self) -> dict[str, Any]:
        return {
            "incubation_skill": self.skill_name,
            "domain": self.domain,
            "candidate_paths": [item.model_dump(mode="json") for item in self.candidate_paths],
            "default_root": self.default_root,
            "branch_only_markers": [item.model_dump(mode="json") for item in self.branch_only_markers],
            "do_not_assume": list(self.do_not_assume),
            "profile_sha256": self.content_sha256(),
        }


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
    raw = profile_path.read_bytes()
    if len(raw) > MAX_INCUBATION_PROFILE_BYTES:
        raise IncubationSkillProfileError("The selected incubation profile exceeds the byte limit.")
    try:
        payload = json.loads(raw.decode("utf-8"))
        profile = IncubationSkillProfile.model_validate(payload)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise IncubationSkillProfileError("The selected incubation profile is invalid.") from exc
    if profile.skill_name != selected.name:
        raise IncubationSkillProfileError("The incubation profile skill_name does not match the selected skill.")
    return profile


__all__ = [
    "INCUBATION_PROFILE_RELATIVE_PATH",
    "MAX_INCUBATION_PROFILE_BYTES",
    "IncubationBranchOnlyMarker",
    "IncubationCandidatePath",
    "IncubationSkillProfile",
    "IncubationSkillProfileError",
    "load_incubation_skill_profile",
]
