from __future__ import annotations

import asyncio
import threading
import weakref
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

from pydantic import Field, field_validator, model_validator

from deerflow.incubation.contracts import (
    ArtifactEnvelope,
    IncubationContract,
    LogicalAccountRef,
    NonEmptyStr,
    ProjectRef,
)

_CONFIRMATION_LOCKS: weakref.WeakValueDictionary[tuple[int, str], asyncio.Lock] = weakref.WeakValueDictionary()
_CONFIRMATION_LOCKS_GUARD = threading.Lock()


def _confirmation_lock(
    *,
    logical_account: LogicalAccountRef,
    proposal_artifact_id: str,
) -> asyncio.Lock:
    """Serialize irreversible choices inside the current runtime process."""

    loop = asyncio.get_running_loop()
    identity = "\0".join(
        (
            logical_account.owner_user_id,
            logical_account.project_id,
            logical_account.logical_account_id,
            proposal_artifact_id,
        )
    )
    key = (id(loop), identity)
    with _CONFIRMATION_LOCKS_GUARD:
        lock = _CONFIRMATION_LOCKS.get(key)
        if lock is None:
            lock = asyncio.Lock()
            _CONFIRMATION_LOCKS[key] = lock
        return lock


class AccountDirectionRepository(Protocol):
    async def put_artifact(self, artifact: ArtifactEnvelope) -> ArtifactEnvelope: ...

    async def list_artifacts(
        self,
        project: ProjectRef,
        *,
        logical_account: LogicalAccountRef | None = None,
        artifact_type: str | None = None,
        evidence_role: str | None = None,
    ) -> list[ArtifactEnvelope]: ...


class AccountDirectionOptionDraft(IncubationContract):
    """One coherent account direction; optional fields may stay unknown."""

    name: NonEmptyStr = Field(max_length=160)
    content_root: NonEmptyStr | None = Field(
        default=None,
        max_length=160,
        description="Concise long-term content root; name the world to expand without rationale or business return text.",
    )
    long_term_content_subject: NonEmptyStr = Field(max_length=1_200)
    rationale: NonEmptyStr = Field(max_length=2_000)
    content_audience_hypothesis: NonEmptyStr | None = Field(default=None, max_length=1_200)
    audience_promise: NonEmptyStr | None = Field(default=None, max_length=1_200)
    account_role: NonEmptyStr | None = Field(default=None, max_length=1_200)
    presentation_directions: tuple[NonEmptyStr, ...] = Field(default=(), max_length=8)
    business_connection: NonEmptyStr | None = Field(default=None, max_length=1_600)
    monetization_hypothesis: NonEmptyStr | None = Field(default=None, max_length=1_600)
    unknowns: tuple[NonEmptyStr, ...] = Field(default=(), max_length=12)
    tradeoffs: tuple[NonEmptyStr, ...] = Field(default=(), max_length=8)


class AccountDirectionOption(AccountDirectionOptionDraft):
    option_id: NonEmptyStr = Field(max_length=80, pattern=r"^direction_[1-3]$")


class AccountDirectionProposalDraft(IncubationContract):
    """Lead-authored judgment before code binds identity and user source text."""

    marketing_subject: NonEmptyStr = Field(max_length=2_000)
    business_goal: NonEmptyStr | None = Field(default=None, max_length=2_000)
    direction_options: tuple[AccountDirectionOptionDraft, ...] = Field(min_length=1, max_length=3)
    recommended_option_number: int = Field(ge=1, le=3)
    basis_artifact_ids: tuple[NonEmptyStr, ...] = Field(default=(), max_length=16)
    unknowns: tuple[NonEmptyStr, ...] = Field(default=(), max_length=12)
    revision_reason: NonEmptyStr | None = Field(default=None, max_length=1_600)

    @field_validator("basis_artifact_ids")
    @classmethod
    def canonicalize_basis_artifact_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(value)) != len(value):
            raise ValueError("basis artifact ids must be unique")
        return tuple(sorted(value))

    @model_validator(mode="after")
    def validate_recommendation(self) -> AccountDirectionProposalDraft:
        if self.recommended_option_number > len(self.direction_options):
            raise ValueError("recommended option number must identify one offered direction")
        return self


class AccountDirectionProposal(IncubationContract):
    schema_version: Literal["v6-account-direction-proposal-v1"] = "v6-account-direction-proposal-v1"
    target_revision_number: int = Field(ge=1)
    source_user_text: NonEmptyStr = Field(max_length=8_000)
    marketing_subject: NonEmptyStr = Field(max_length=2_000)
    business_goal: NonEmptyStr | None = Field(default=None, max_length=2_000)
    direction_options: tuple[AccountDirectionOption, ...] = Field(min_length=1, max_length=3)
    recommended_option_id: NonEmptyStr = Field(max_length=80)
    basis_artifact_ids: tuple[NonEmptyStr, ...] = Field(default=(), max_length=16)
    unknowns: tuple[NonEmptyStr, ...] = Field(default=(), max_length=12)
    previous_direction_artifact_id: NonEmptyStr | None = Field(default=None, max_length=80)
    revision_reason: NonEmptyStr | None = Field(default=None, max_length=1_600)

    @model_validator(mode="after")
    def validate_option_binding(self) -> AccountDirectionProposal:
        option_ids = tuple(option.option_id for option in self.direction_options)
        if len(set(option_ids)) != len(option_ids):
            raise ValueError("direction option ids must be unique")
        if self.recommended_option_id not in option_ids:
            raise ValueError("recommended option must identify one offered direction")
        return self


class AccountDirectionVersion(IncubationContract):
    schema_version: Literal["v6-account-direction-v1"] = "v6-account-direction-v1"
    revision_number: int = Field(ge=1)
    proposal_artifact_id: NonEmptyStr = Field(max_length=80)
    source_user_text: NonEmptyStr = Field(max_length=8_000)
    confirmation_user_text: NonEmptyStr = Field(max_length=8_000)
    marketing_subject: NonEmptyStr = Field(max_length=2_000)
    business_goal: NonEmptyStr | None = Field(default=None, max_length=2_000)
    selected_option: AccountDirectionOption
    basis_artifact_ids: tuple[NonEmptyStr, ...] = Field(default=(), max_length=16)
    unknowns: tuple[NonEmptyStr, ...] = Field(default=(), max_length=12)
    previous_direction_artifact_id: NonEmptyStr | None = Field(default=None, max_length=80)
    revision_reason: NonEmptyStr | None = Field(default=None, max_length=1_600)


@dataclass(frozen=True, slots=True)
class PreparedAccountDirectionProposal:
    proposal: AccountDirectionProposal
    proposal_artifact: ArtifactEnvelope
    reused: bool


@dataclass(frozen=True, slots=True)
class PreparedAccountDirection:
    direction: AccountDirectionVersion
    direction_artifact: ArtifactEnvelope
    reused: bool


def select_latest_account_direction_proposal(
    artifacts: list[ArtifactEnvelope] | tuple[ArtifactEnvelope, ...],
    *,
    logical_account: LogicalAccountRef,
) -> PreparedAccountDirectionProposal | None:
    candidates: list[tuple[AccountDirectionProposal, ArtifactEnvelope]] = []
    for artifact in artifacts:
        if artifact.artifact_type != "account_direction_proposal" or artifact.logical_account != logical_account:
            continue
        proposal = AccountDirectionProposal.model_validate(artifact.payload)
        if artifact.version != proposal.target_revision_number:
            raise ValueError("account direction proposal version must match target revision")
        candidates.append((proposal, artifact))
    if not candidates:
        return None
    proposal, artifact = max(
        candidates,
        key=lambda item: (
            item[0].target_revision_number,
            item[1].created_at,
            item[1].artifact_id,
        ),
    )
    return PreparedAccountDirectionProposal(
        proposal=proposal,
        proposal_artifact=artifact,
        reused=True,
    )


def select_current_account_direction(
    artifacts: list[ArtifactEnvelope] | tuple[ArtifactEnvelope, ...],
    *,
    logical_account: LogicalAccountRef,
) -> PreparedAccountDirection | None:
    candidates: list[tuple[AccountDirectionVersion, ArtifactEnvelope]] = []
    artifact_ids_by_revision: dict[int, str] = {}
    for artifact in artifacts:
        if artifact.artifact_type != "account_direction_version" or artifact.logical_account != logical_account:
            continue
        direction = AccountDirectionVersion.model_validate(artifact.payload)
        if artifact.version != direction.revision_number:
            raise ValueError("account direction version must match revision number")
        existing_artifact_id = artifact_ids_by_revision.get(direction.revision_number)
        if existing_artifact_id is not None and existing_artifact_id != artifact.artifact_id:
            raise ValueError("account direction revision has conflicting artifacts")
        artifact_ids_by_revision[direction.revision_number] = artifact.artifact_id
        candidates.append((direction, artifact))
    if not candidates:
        return None
    direction, artifact = max(
        candidates,
        key=lambda item: (
            item[0].revision_number,
            item[1].created_at,
            item[1].artifact_id,
        ),
    )
    return PreparedAccountDirection(
        direction=direction,
        direction_artifact=artifact,
        reused=True,
    )


def _seal_options(
    options: tuple[AccountDirectionOptionDraft, ...],
) -> tuple[AccountDirectionOption, ...]:
    return tuple(
        AccountDirectionOption(
            option_id=f"direction_{index}",
            **option.model_dump(mode="python"),
        )
        for index, option in enumerate(options, start=1)
    )


def _option_without_identity(option: AccountDirectionOption) -> dict[str, object]:
    return option.model_dump(mode="python", exclude={"option_id"})


async def propose_account_direction(
    *,
    project: ProjectRef,
    logical_account: LogicalAccountRef,
    repository: AccountDirectionRepository,
    draft: AccountDirectionProposalDraft,
    source_user_text: str,
    created_at: datetime,
    source_thread_id: str,
    source_run_id: str,
) -> PreparedAccountDirectionProposal:
    """Seal a Lead judgment as a proposal without adopting it for the user."""

    artifacts = await repository.list_artifacts(
        project,
        logical_account=logical_account,
    )
    current = select_current_account_direction(
        artifacts,
        logical_account=logical_account,
    )
    if current is not None and draft.revision_reason is None:
        raise ValueError("an account direction revision requires a revision reason")

    sealed_options = _seal_options(draft.direction_options)
    if (
        current is not None
        and len(sealed_options) == 1
        and draft.marketing_subject == current.direction.marketing_subject
        and draft.business_goal == current.direction.business_goal
        and _option_without_identity(sealed_options[0]) == _option_without_identity(current.direction.selected_option)
    ):
        raise ValueError("the proposed account direction is unchanged")

    artifacts_by_id = {artifact.artifact_id: artifact for artifact in artifacts}
    basis_artifacts: list[ArtifactEnvelope] = []
    for artifact_id in draft.basis_artifact_ids:
        artifact = artifacts_by_id.get(artifact_id)
        if artifact is None or artifact.logical_account != logical_account:
            raise ValueError("account direction basis artifact is unavailable in this logical account")
        basis_artifacts.append(artifact)

    target_revision = current.direction.revision_number + 1 if current is not None else 1
    proposal = AccountDirectionProposal(
        target_revision_number=target_revision,
        source_user_text=source_user_text,
        marketing_subject=draft.marketing_subject,
        business_goal=draft.business_goal,
        direction_options=sealed_options,
        recommended_option_id=f"direction_{draft.recommended_option_number}",
        basis_artifact_ids=draft.basis_artifact_ids,
        unknowns=draft.unknowns,
        previous_direction_artifact_id=(current.direction_artifact.artifact_id if current is not None else None),
        revision_reason=draft.revision_reason,
    )
    parent_artifacts = {
        artifact.artifact_id: artifact
        for artifact in (
            *basis_artifacts,
            *((current.direction_artifact,) if current is not None else ()),
        )
    }
    proposal_artifact = ArtifactEnvelope.seal(
        project=project,
        logical_account=logical_account,
        artifact_type="account_direction_proposal",
        version=target_revision,
        payload=proposal.model_dump(mode="json"),
        parents=tuple(parent_artifacts[artifact_id].to_parent_ref() for artifact_id in sorted(parent_artifacts)),
        created_at=created_at,
        source_thread_id=source_thread_id,
        source_run_id=source_run_id,
    )
    reused = proposal_artifact.artifact_id in artifacts_by_id
    stored = await repository.put_artifact(proposal_artifact)
    return PreparedAccountDirectionProposal(
        proposal=AccountDirectionProposal.model_validate(stored.payload),
        proposal_artifact=stored,
        reused=reused,
    )


async def confirm_account_direction(
    *,
    project: ProjectRef,
    logical_account: LogicalAccountRef,
    repository: AccountDirectionRepository,
    proposal_artifact_id: str,
    option_id: str,
    confirmation_user_text: str,
    created_at: datetime,
    source_thread_id: str,
    source_run_id: str,
) -> PreparedAccountDirection:
    """Adopt exactly one option from the latest immutable proposal."""

    lock = _confirmation_lock(
        logical_account=logical_account,
        proposal_artifact_id=proposal_artifact_id,
    )
    async with lock:
        return await _confirm_account_direction_unlocked(
            project=project,
            logical_account=logical_account,
            repository=repository,
            proposal_artifact_id=proposal_artifact_id,
            option_id=option_id,
            confirmation_user_text=confirmation_user_text,
            created_at=created_at,
            source_thread_id=source_thread_id,
            source_run_id=source_run_id,
        )


async def _confirm_account_direction_unlocked(
    *,
    project: ProjectRef,
    logical_account: LogicalAccountRef,
    repository: AccountDirectionRepository,
    proposal_artifact_id: str,
    option_id: str,
    confirmation_user_text: str,
    created_at: datetime,
    source_thread_id: str,
    source_run_id: str,
) -> PreparedAccountDirection:

    artifacts = await repository.list_artifacts(
        project,
        logical_account=logical_account,
    )
    latest = select_latest_account_direction_proposal(
        artifacts,
        logical_account=logical_account,
    )
    if latest is None or latest.proposal_artifact.artifact_id != proposal_artifact_id:
        raise ValueError("the latest account direction proposal receipt is required")
    selected = next(
        (option for option in latest.proposal.direction_options if option.option_id == option_id),
        None,
    )
    if selected is None:
        raise ValueError("unknown account direction option")

    current = select_current_account_direction(
        artifacts,
        logical_account=logical_account,
    )
    confirmed_for_proposal = tuple(artifact for artifact in artifacts if artifact.artifact_type == "account_direction_version" and artifact.payload.get("proposal_artifact_id") == proposal_artifact_id)
    if confirmed_for_proposal:
        if len(confirmed_for_proposal) != 1:
            raise ValueError("account direction proposal has conflicting confirmations")
        existing_artifact = confirmed_for_proposal[0]
        existing = AccountDirectionVersion.model_validate(existing_artifact.payload)
        if existing.selected_option.option_id != option_id:
            raise ValueError("the account direction proposal is already confirmed with another option")
        return PreparedAccountDirection(
            direction=existing,
            direction_artifact=existing_artifact,
            reused=True,
        )

    if current is not None and current.direction.revision_number >= latest.proposal.target_revision_number:
        raise ValueError("the account direction proposal no longer targets a new revision")

    direction = AccountDirectionVersion(
        revision_number=latest.proposal.target_revision_number,
        proposal_artifact_id=proposal_artifact_id,
        source_user_text=latest.proposal.source_user_text,
        confirmation_user_text=confirmation_user_text,
        marketing_subject=latest.proposal.marketing_subject,
        business_goal=latest.proposal.business_goal,
        selected_option=selected,
        basis_artifact_ids=latest.proposal.basis_artifact_ids,
        unknowns=tuple(dict.fromkeys((*latest.proposal.unknowns, *selected.unknowns))),
        previous_direction_artifact_id=(current.direction_artifact.artifact_id if current is not None else None),
        revision_reason=latest.proposal.revision_reason,
    )
    parents = {
        latest.proposal_artifact.artifact_id: latest.proposal_artifact,
        **({current.direction_artifact.artifact_id: current.direction_artifact} if current is not None else {}),
    }
    direction_artifact = ArtifactEnvelope.seal(
        project=project,
        logical_account=logical_account,
        artifact_type="account_direction_version",
        version=direction.revision_number,
        payload=direction.model_dump(mode="json"),
        parents=tuple(parents[artifact_id].to_parent_ref() for artifact_id in sorted(parents)),
        created_at=created_at,
        source_thread_id=source_thread_id,
        source_run_id=source_run_id,
    )
    stored = await repository.put_artifact(direction_artifact)
    return PreparedAccountDirection(
        direction=AccountDirectionVersion.model_validate(stored.payload),
        direction_artifact=stored,
        reused=stored.created_at != direction_artifact.created_at,
    )


def render_account_direction_proposal(
    prepared: PreparedAccountDirectionProposal,
) -> str:
    proposal = prepared.proposal
    lines = [
        "# 账号方向提案",
        "",
        f"营销主体：{proposal.marketing_subject}",
    ]
    if proposal.business_goal is not None:
        lines.append(f"业务目标：{proposal.business_goal}")
    lines.extend(("", f"提案回执：`{prepared.proposal_artifact.artifact_id}`"))
    for option in proposal.direction_options:
        recommendation = "（推荐）" if option.option_id == proposal.recommended_option_id else ""
        lines.extend(
            (
                "",
                f"## {option.name}{recommendation}",
                f"方向 ID：`{option.option_id}`",
                f"长期内容主体：{option.long_term_content_subject}",
                f"依据：{option.rationale}",
            )
        )
        if option.content_audience_hypothesis is not None:
            lines.append(f"内容受众假设：{option.content_audience_hypothesis}")
        if option.audience_promise is not None:
            lines.append(f"长期承诺：{option.audience_promise}")
        if option.account_role is not None:
            lines.append(f"账号角色：{option.account_role}")
        if option.presentation_directions:
            lines.append("表现形式候选：" + "、".join(option.presentation_directions))
        if option.business_connection is not None:
            lines.append(f"业务连接：{option.business_connection}")
        if option.monetization_hypothesis is not None:
            lines.append(f"变现假设：{option.monetization_hypothesis}")
        if option.unknowns:
            lines.append("仍未知：" + "；".join(option.unknowns))
        if option.tradeoffs:
            lines.append("取舍：" + "；".join(option.tradeoffs))
    if proposal.unknowns:
        lines.extend(("", "共同未知：" + "；".join(proposal.unknowns)))
    lines.extend(("", "这只是候选。只有用户明确选择后，账号方向才会生效。"))
    return "\n".join(lines)


def render_account_direction(prepared: PreparedAccountDirection) -> str:
    direction = prepared.direction
    option = direction.selected_option
    return "\n".join(
        (
            f"# 已确认账号方向 v{direction.revision_number}",
            "",
            f"方向：{option.name}",
            f"长期内容主体：{option.long_term_content_subject}",
            *((f"内容受众假设：{option.content_audience_hypothesis}",) if option.content_audience_hypothesis is not None else ()),
            *((f"长期承诺：{option.audience_promise}",) if option.audience_promise is not None else ()),
            *((f"账号角色：{option.account_role}",) if option.account_role is not None else ()),
            f"方向回执：`{prepared.direction_artifact.artifact_id}`",
        )
    )


__all__ = [
    "AccountDirectionOption",
    "AccountDirectionOptionDraft",
    "AccountDirectionProposal",
    "AccountDirectionProposalDraft",
    "AccountDirectionRepository",
    "AccountDirectionVersion",
    "PreparedAccountDirection",
    "PreparedAccountDirectionProposal",
    "confirm_account_direction",
    "propose_account_direction",
    "render_account_direction",
    "render_account_direction_proposal",
    "select_current_account_direction",
    "select_latest_account_direction_proposal",
]
