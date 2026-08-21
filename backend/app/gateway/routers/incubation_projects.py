from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.gateway.authz import require_permission
from app.gateway.deps import (
    get_incubation_ledger_repo,
    get_mediakit_quote_service,
    get_optional_user_from_request,
    get_thread_store,
)
from app.gateway.internal_auth import INTERNAL_SYSTEM_ROLE, get_trusted_internal_owner_user_id
from deerflow.community.mediakit import (
    MediaKitCloudApprovalRequest,
    MediaKitCommandError,
    MediaKitPricingConfigurationError,
)
from deerflow.incubation import INCUBATION_PROJECT_ID_KEY, ApprovalGrant, ProjectRecord, ProjectRef
from deerflow.incubation.contracts import (
    INCUBATION_LOGICAL_ACCOUNT_ID_KEY,
    LogicalAccountRecord,
    LogicalAccountRef,
)
from deerflow.persistence.incubation_ledger import (
    ApprovalGrantConflictError,
    LogicalAccountConflictError,
    ProjectConflictError,
)
from deerflow.utils.thread_id import ThreadId

router = APIRouter(prefix="/api/incubation", tags=["incubation"])


class IncubationProjectCreateRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    project_id: str | None = Field(default=None, min_length=1, max_length=64)
    display_name: str = Field(min_length=1, max_length=255)


class IncubationProjectResponse(BaseModel):
    project_id: str
    display_name: str
    created_at: datetime
    updated_at: datetime


class LogicalAccountCreateRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    logical_account_id: str | None = Field(default=None, min_length=1, max_length=64)
    display_name: str = Field(min_length=1, max_length=255)


class LogicalAccountResponse(BaseModel):
    project_id: str
    logical_account_id: str
    display_name: str
    created_at: datetime
    updated_at: datetime


class ThreadProjectBindingRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    project_id: str = Field(min_length=1, max_length=64)


class ThreadProjectBindingResponse(BaseModel):
    thread_id: str
    project: IncubationProjectResponse | None


class ThreadLogicalAccountBindingRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    project_id: str = Field(min_length=1, max_length=64)
    logical_account_id: str = Field(min_length=1, max_length=64)


class ThreadLogicalAccountBindingResponse(BaseModel):
    thread_id: str
    logical_account: LogicalAccountResponse | None


class MediaKitCloudApprovalConfirmRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    quote_artifact_id: str = Field(min_length=1, max_length=80)
    fee_quote_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    maximum_amount_micros: int = Field(gt=0)
    confirm_cloud_processing: Literal[True]
    confirm_fee_authorization: Literal[True]
    acknowledge_no_provider_hard_cap: Literal[True]


class MediaKitCloudApprovalResponse(BaseModel):
    quote_artifact_id: str
    operation_sha256: str
    cloud_processing_grant_id: str
    fee_authorization_grant_id: str
    currency: str
    estimated_amount_micros: int
    maximum_amount_micros: int
    provider_hard_cap_supported: bool
    expires_at: datetime
    replayed: bool


class MediaKitCloudApprovalReviewResponse(BaseModel):
    quote_artifact_id: str
    fee_quote_sha256: str
    pricing_evidence_sha256: str
    capability_domain: str
    capability_tool: str
    capability_schema_sha256: str
    tool_version: str
    source_duration_milliseconds: int
    output_resolution_tier: str
    output_fps: float
    currency: str
    amount_micros_per_minute: int
    estimated_amount_micros: int
    maximum_amount_micros: int
    provider_hard_cap_supported: bool
    requires_no_provider_hard_cap_acknowledgement: bool
    quoted_at: datetime
    valid_until: datetime
    expired: bool


class MediaKitEnhanceVideoQuoteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    media_observation_artifact_id: str = Field(pattern=r"^artifact_[0-9a-f]{64}$")
    tool_version: Literal["standard"]
    scene: Literal["common", "ugc", "short_series", "aigc", "old_film"]
    resolution: Literal["240p", "360p", "480p", "540p", "720p"]
    fps: float = Field(ge=15, le=30)
    bitrate_level: Literal["low", "medium", "high"]
    maximum_amount_micros: int = Field(gt=0)


async def _effective_owner_user_id(request: Request) -> str:
    user = getattr(request.state, "user", None)
    if user is None:
        user = await get_optional_user_from_request(request)
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    if getattr(user, "system_role", None) == INTERNAL_SYSTEM_ROLE:
        owner_user_id = get_trusted_internal_owner_user_id(request)
        if not owner_user_id:
            raise HTTPException(status_code=401, detail="Internal request requires an owner")
        return owner_user_id
    return str(user.id)


def _project_ref(owner_user_id: str, project_id: str) -> ProjectRef:
    try:
        return ProjectRef(owner_user_id=owner_user_id, project_id=project_id)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail="Invalid incubation project identity") from exc


def _logical_account_ref(
    owner_user_id: str,
    project_id: str,
    logical_account_id: str,
) -> LogicalAccountRef:
    try:
        return LogicalAccountRef(
            owner_user_id=owner_user_id,
            project_id=project_id,
            logical_account_id=logical_account_id,
        )
    except ValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail="Invalid logical account identity",
        ) from exc


def _response(record: ProjectRecord) -> IncubationProjectResponse:
    return IncubationProjectResponse(
        project_id=record.project.project_id,
        display_name=record.display_name,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _logical_account_response(
    record: LogicalAccountRecord,
) -> LogicalAccountResponse:
    return LogicalAccountResponse(
        project_id=record.logical_account.project_id,
        logical_account_id=record.logical_account.logical_account_id,
        display_name=record.display_name,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _approval_grant_id(kind: str, operation_sha256: str) -> str:
    digest = hashlib.sha256(f"{kind}\0{operation_sha256}".encode()).hexdigest()
    return f"approval-{kind}:{digest}"


def _approval_matches(
    grant: ApprovalGrant,
    *,
    project: ProjectRef,
    kind: str,
    approval: MediaKitCloudApprovalRequest,
    now: datetime,
) -> bool:
    return (
        grant.project == project
        and grant.kind == kind
        and grant.operation_sha256 == approval.operation_sha256
        and grant.expires_at == approval.valid_until
        and grant.revoked_at is None
        and grant.bound_local_task_id is None
        and grant.expires_at > now
        and (kind == "cloud_processing" or (grant.currency == approval.currency and grant.maximum_amount_micros == approval.maximum_amount_micros))
    )


async def _load_mediakit_approval_request(
    *,
    ledger,
    owner_user_id: str,
    project: ProjectRef,
    quote_artifact_id: str,
):
    artifact = await ledger.get_artifact(
        quote_artifact_id,
        owner_user_id=owner_user_id,
    )
    if artifact is None or artifact.project != project:
        raise HTTPException(status_code=404, detail="MediaKit approval request not found")
    if artifact.artifact_type != "mediakit_cloud_approval_request" or artifact.version != 1 or artifact.evidence_role is not None or len(artifact.parents) != 1 or artifact.parents[0].artifact_type != "media_observation":
        raise HTTPException(status_code=409, detail="MediaKit approval request is invalid")
    try:
        approval = MediaKitCloudApprovalRequest.model_validate(artifact.payload)
    except ValidationError as exc:
        raise HTTPException(status_code=409, detail="MediaKit approval request is invalid") from exc
    if artifact.created_at != approval.quoted_at:
        raise HTTPException(status_code=409, detail="MediaKit approval request is invalid")
    return artifact, approval


async def _load_mediakit_quote_lineage(
    *,
    ledger,
    owner_user_id: str,
    project: ProjectRef,
    media_observation_artifact_id: str,
):
    observation = await ledger.get_artifact(
        media_observation_artifact_id,
        owner_user_id=owner_user_id,
    )
    if observation is None or observation.project != project:
        raise HTTPException(status_code=404, detail="MediaKit media observation not found")
    if observation.artifact_type != "media_observation" or observation.version != 1 or observation.evidence_role != "user_material" or len(observation.parents) != 1 or observation.parents[0].artifact_type != "media_source_receipt":
        raise HTTPException(status_code=409, detail="MediaKit media observation is invalid")
    parent = observation.parents[0]
    source_receipt = await ledger.get_artifact(
        parent.artifact_id,
        owner_user_id=owner_user_id,
    )
    if (
        source_receipt is None
        or source_receipt.project != project
        or source_receipt.to_parent_ref() != parent
        or source_receipt.artifact_type != "media_source_receipt"
        or source_receipt.version != 1
        or source_receipt.evidence_role != "user_material"
    ):
        raise HTTPException(status_code=409, detail="MediaKit media source lineage is invalid")
    return source_receipt, observation


def _approval_review_response(
    *,
    artifact,
    approval: MediaKitCloudApprovalRequest,
    now: datetime,
) -> MediaKitCloudApprovalReviewResponse:
    return MediaKitCloudApprovalReviewResponse(
        quote_artifact_id=artifact.artifact_id,
        fee_quote_sha256=approval.fee_quote_sha256,
        pricing_evidence_sha256=approval.pricing_evidence_sha256,
        capability_domain=approval.capability_domain,
        capability_tool=approval.capability_tool,
        capability_schema_sha256=approval.capability_schema_sha256,
        tool_version=approval.tool_version,
        source_duration_milliseconds=approval.source_duration_milliseconds,
        output_resolution_tier=approval.output_resolution_tier,
        output_fps=approval.output_fps,
        currency=approval.currency,
        amount_micros_per_minute=approval.amount_micros_per_minute,
        estimated_amount_micros=approval.estimated_amount_micros,
        maximum_amount_micros=approval.maximum_amount_micros,
        provider_hard_cap_supported=approval.provider_hard_cap_supported,
        requires_no_provider_hard_cap_acknowledgement=(not approval.provider_hard_cap_supported),
        quoted_at=approval.quoted_at,
        valid_until=approval.valid_until,
        expired=now >= approval.valid_until,
    )


async def _require_thread(request: Request, *, thread_id: str, owner_user_id: str):
    thread_store = get_thread_store(request)
    if not await thread_store.check_access(thread_id, owner_user_id, require_existing=True):
        raise HTTPException(status_code=404, detail="Thread not found")
    return thread_store


@router.post(
    "/projects",
    response_model=IncubationProjectResponse,
    status_code=status.HTTP_201_CREATED,
)
@require_permission("threads", "write")
async def create_incubation_project(
    body: IncubationProjectCreateRequest,
    request: Request,
) -> IncubationProjectResponse:
    owner_user_id = await _effective_owner_user_id(request)
    project_id = body.project_id or f"project_{uuid.uuid4().hex}"
    try:
        record = await get_incubation_ledger_repo(request).create_project(
            _project_ref(owner_user_id, project_id),
            display_name=body.display_name,
        )
    except ProjectConflictError as exc:
        raise HTTPException(status_code=409, detail="Project identity already exists") from exc
    return _response(record)


@router.get("/projects", response_model=list[IncubationProjectResponse])
@require_permission("threads", "read")
async def list_incubation_projects(
    request: Request,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> list[IncubationProjectResponse]:
    owner_user_id = await _effective_owner_user_id(request)
    records = await get_incubation_ledger_repo(request).list_projects(
        owner_user_id,
        limit=limit,
        offset=offset,
    )
    return [_response(record) for record in records]


@router.get("/projects/{project_id}", response_model=IncubationProjectResponse)
@require_permission("threads", "read")
async def get_incubation_project(
    project_id: str,
    request: Request,
) -> IncubationProjectResponse:
    owner_user_id = await _effective_owner_user_id(request)
    record = await get_incubation_ledger_repo(request).get_project(_project_ref(owner_user_id, project_id))
    if record is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return _response(record)


@router.post(
    "/projects/{project_id}/logical-accounts",
    response_model=LogicalAccountResponse,
    status_code=status.HTTP_201_CREATED,
)
@require_permission("threads", "write")
async def create_logical_account(
    project_id: str,
    body: LogicalAccountCreateRequest,
    request: Request,
) -> LogicalAccountResponse:
    owner_user_id = await _effective_owner_user_id(request)
    project = _project_ref(owner_user_id, project_id)
    ledger = get_incubation_ledger_repo(request)
    if await ledger.get_project(project) is None:
        raise HTTPException(status_code=404, detail="Project not found")
    logical_account_id = body.logical_account_id or f"account_{uuid.uuid4().hex}"
    logical_account = _logical_account_ref(
        owner_user_id,
        project_id,
        logical_account_id,
    )
    if await ledger.get_logical_account(logical_account) is not None:
        raise HTTPException(status_code=409, detail="Logical account already exists")
    try:
        record = await ledger.create_logical_account(
            logical_account,
            display_name=body.display_name,
        )
    except LogicalAccountConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail="Logical account already exists",
        ) from exc
    return _logical_account_response(record)


@router.get(
    "/projects/{project_id}/logical-accounts",
    response_model=list[LogicalAccountResponse],
)
@require_permission("threads", "read")
async def list_logical_accounts(
    project_id: str,
    request: Request,
) -> list[LogicalAccountResponse]:
    owner_user_id = await _effective_owner_user_id(request)
    project = _project_ref(owner_user_id, project_id)
    ledger = get_incubation_ledger_repo(request)
    if await ledger.get_project(project) is None:
        raise HTTPException(status_code=404, detail="Project not found")
    records = await ledger.list_logical_accounts(project)
    return [_logical_account_response(record) for record in records]


@router.get(
    "/projects/{project_id}/logical-accounts/{logical_account_id}",
    response_model=LogicalAccountResponse,
)
@require_permission("threads", "read")
async def get_logical_account(
    project_id: str,
    logical_account_id: str,
    request: Request,
) -> LogicalAccountResponse:
    owner_user_id = await _effective_owner_user_id(request)
    record = await get_incubation_ledger_repo(request).get_logical_account(_logical_account_ref(owner_user_id, project_id, logical_account_id))
    if record is None:
        raise HTTPException(status_code=404, detail="Logical account not found")
    return _logical_account_response(record)


@router.post(
    "/projects/{project_id}/media/mediakit/enhance-video/quotes",
    response_model=MediaKitCloudApprovalReviewResponse,
    status_code=status.HTTP_201_CREATED,
)
@require_permission("threads", "write")
async def create_mediakit_enhance_video_quote(
    project_id: str,
    body: MediaKitEnhanceVideoQuoteRequest,
    request: Request,
) -> MediaKitCloudApprovalReviewResponse:
    owner_user_id = await _effective_owner_user_id(request)
    project = _project_ref(owner_user_id, project_id)
    ledger = get_incubation_ledger_repo(request)
    source_receipt, observation = await _load_mediakit_quote_lineage(
        ledger=ledger,
        owner_user_id=owner_user_id,
        project=project,
        media_observation_artifact_id=body.media_observation_artifact_id,
    )
    quote_service = get_mediakit_quote_service(request)
    quoted_at = datetime.now(UTC)
    try:
        artifact = await quote_service.prepare_approval_request(
            project=project,
            media_observation_artifact=observation,
            source_receipt_artifact=source_receipt,
            capability_arguments={
                "tool_version": body.tool_version,
                "scene": body.scene,
                "resolution": body.resolution,
                "fps": body.fps,
                "bitrate_level": body.bitrate_level,
            },
            maximum_amount_micros=body.maximum_amount_micros,
            quoted_at=quoted_at,
            source_run_id=f"gateway-mediakit-quote-{uuid.uuid4().hex}",
        )
    except (MediaKitPricingConfigurationError, MediaKitCommandError) as exc:
        raise HTTPException(status_code=503, detail="MediaKit quote evidence is unavailable") from exc
    except PermissionError as exc:
        raise HTTPException(status_code=409, detail="MediaKit quote is unavailable for the requested fee or time") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid MediaKit quote request") from exc
    stored = await ledger.put_artifact(artifact)
    try:
        approval = MediaKitCloudApprovalRequest.model_validate(stored.payload)
    except ValidationError as exc:
        raise HTTPException(status_code=409, detail="MediaKit quote artifact is invalid") from exc
    return _approval_review_response(
        artifact=stored,
        approval=approval,
        now=quoted_at,
    )


@router.get(
    "/projects/{project_id}/approvals/mediakit-cloud/{quote_artifact_id}",
    response_model=MediaKitCloudApprovalReviewResponse,
)
@require_permission("threads", "read")
async def review_mediakit_cloud_request(
    project_id: str,
    quote_artifact_id: str,
    request: Request,
) -> MediaKitCloudApprovalReviewResponse:
    owner_user_id = await _effective_owner_user_id(request)
    project = _project_ref(owner_user_id, project_id)
    artifact, approval = await _load_mediakit_approval_request(
        ledger=get_incubation_ledger_repo(request),
        owner_user_id=owner_user_id,
        project=project,
        quote_artifact_id=quote_artifact_id,
    )
    now = datetime.now(UTC)
    return _approval_review_response(
        artifact=artifact,
        approval=approval,
        now=now,
    )


@router.post(
    "/projects/{project_id}/approvals/mediakit-cloud",
    response_model=MediaKitCloudApprovalResponse,
    status_code=status.HTTP_201_CREATED,
)
@require_permission("threads", "write")
async def approve_mediakit_cloud_request(
    project_id: str,
    body: MediaKitCloudApprovalConfirmRequest,
    request: Request,
    response: Response,
) -> MediaKitCloudApprovalResponse:
    owner_user_id = await _effective_owner_user_id(request)
    project = _project_ref(owner_user_id, project_id)
    ledger = get_incubation_ledger_repo(request)
    artifact, approval = await _load_mediakit_approval_request(
        ledger=ledger,
        owner_user_id=owner_user_id,
        project=project,
        quote_artifact_id=body.quote_artifact_id,
    )
    now = datetime.now(UTC)
    if now >= approval.valid_until:
        raise HTTPException(status_code=409, detail="MediaKit approval request expired")
    if body.fee_quote_sha256 != approval.fee_quote_sha256 or body.currency != approval.currency or body.maximum_amount_micros != approval.maximum_amount_micros:
        raise HTTPException(status_code=409, detail="MediaKit approval confirmation changed")
    if approval.provider_hard_cap_supported:
        raise HTTPException(status_code=409, detail="MediaKit provider fee-cap evidence changed")

    cloud_id = _approval_grant_id("cloud", approval.operation_sha256)
    fee_id = _approval_grant_id("fee", approval.operation_sha256)
    existing_cloud = await ledger.get_approval_grant(cloud_id, owner_user_id=owner_user_id)
    existing_fee = await ledger.get_approval_grant(fee_id, owner_user_id=owner_user_id)
    replayed = existing_cloud is not None or existing_fee is not None
    if replayed:
        if (
            existing_cloud is None
            or existing_fee is None
            or not _approval_matches(
                existing_cloud,
                project=project,
                kind="cloud_processing",
                approval=approval,
                now=now,
            )
            or not _approval_matches(
                existing_fee,
                project=project,
                kind="fee_authorization",
                approval=approval,
                now=now,
            )
        ):
            raise HTTPException(status_code=409, detail="MediaKit approval pair is unavailable")
        cloud, fee = existing_cloud, existing_fee
        response.status_code = status.HTTP_200_OK
    else:
        cloud = ApprovalGrant.issue(
            grant_id=cloud_id,
            project=project,
            kind="cloud_processing",
            operation_sha256=approval.operation_sha256,
            issued_at=now,
            expires_at=approval.valid_until,
        )
        fee = ApprovalGrant.issue(
            grant_id=fee_id,
            project=project,
            kind="fee_authorization",
            operation_sha256=approval.operation_sha256,
            issued_at=now,
            expires_at=approval.valid_until,
            currency=approval.currency,
            maximum_amount_micros=approval.maximum_amount_micros,
        )
        try:
            cloud, fee = await ledger.issue_approval_pair(cloud, fee)
        except ApprovalGrantConflictError as exc:
            raise HTTPException(status_code=409, detail="MediaKit approval pair changed") from exc
        replayed = cloud.issued_at != now
        if replayed:
            response.status_code = status.HTTP_200_OK

    return MediaKitCloudApprovalResponse(
        quote_artifact_id=artifact.artifact_id,
        operation_sha256=approval.operation_sha256,
        cloud_processing_grant_id=cloud.grant_id,
        fee_authorization_grant_id=fee.grant_id,
        currency=approval.currency,
        estimated_amount_micros=approval.estimated_amount_micros,
        maximum_amount_micros=approval.maximum_amount_micros,
        provider_hard_cap_supported=approval.provider_hard_cap_supported,
        expires_at=approval.valid_until,
        replayed=replayed,
    )


@router.put(
    "/threads/{thread_id}/project",
    response_model=ThreadProjectBindingResponse,
)
@require_permission("threads", "write")
async def bind_thread_project(
    thread_id: ThreadId,
    body: ThreadProjectBindingRequest,
    request: Request,
) -> ThreadProjectBindingResponse:
    owner_user_id = await _effective_owner_user_id(request)
    thread_store = await _require_thread(
        request,
        thread_id=thread_id,
        owner_user_id=owner_user_id,
    )
    thread = await thread_store.get(thread_id, user_id=owner_user_id)
    metadata = thread.get("metadata") if thread is not None else None
    bound_project_id = metadata.get(INCUBATION_PROJECT_ID_KEY) if isinstance(metadata, dict) else None
    bound_logical_account_id = metadata.get(INCUBATION_LOGICAL_ACCOUNT_ID_KEY) if isinstance(metadata, dict) else None
    if isinstance(bound_logical_account_id, str) and bound_logical_account_id and bound_project_id != body.project_id:
        raise HTTPException(
            status_code=409,
            detail="Unbind the thread logical account before changing projects",
        )
    record = await get_incubation_ledger_repo(request).get_project(_project_ref(owner_user_id, body.project_id))
    if record is None:
        raise HTTPException(status_code=404, detail="Project not found")
    await thread_store.update_metadata(
        thread_id,
        {
            INCUBATION_PROJECT_ID_KEY: record.project.project_id,
            INCUBATION_LOGICAL_ACCOUNT_ID_KEY: (bound_logical_account_id if bound_project_id == record.project.project_id and isinstance(bound_logical_account_id, str) and bound_logical_account_id else None),
        },
        touch=False,
        user_id=owner_user_id,
    )
    return ThreadProjectBindingResponse(thread_id=thread_id, project=_response(record))


@router.get(
    "/threads/{thread_id}/project",
    response_model=ThreadProjectBindingResponse,
)
@require_permission("threads", "read")
async def get_thread_project(
    thread_id: ThreadId,
    request: Request,
) -> ThreadProjectBindingResponse:
    owner_user_id = await _effective_owner_user_id(request)
    thread_store = await _require_thread(
        request,
        thread_id=thread_id,
        owner_user_id=owner_user_id,
    )
    thread = await thread_store.get(thread_id, user_id=owner_user_id)
    metadata = thread.get("metadata") if thread is not None else None
    project_id = metadata.get(INCUBATION_PROJECT_ID_KEY) if isinstance(metadata, dict) else None
    if not isinstance(project_id, str) or not project_id:
        return ThreadProjectBindingResponse(thread_id=thread_id, project=None)
    record = await get_incubation_ledger_repo(request).get_project(_project_ref(owner_user_id, project_id))
    if record is None:
        raise HTTPException(status_code=409, detail="Thread project binding is stale")
    return ThreadProjectBindingResponse(thread_id=thread_id, project=_response(record))


@router.delete(
    "/threads/{thread_id}/project",
    response_model=ThreadProjectBindingResponse,
)
@require_permission("threads", "write")
async def unbind_thread_project(
    thread_id: ThreadId,
    request: Request,
) -> ThreadProjectBindingResponse:
    owner_user_id = await _effective_owner_user_id(request)
    thread_store = await _require_thread(
        request,
        thread_id=thread_id,
        owner_user_id=owner_user_id,
    )
    await thread_store.update_metadata(
        thread_id,
        {
            INCUBATION_PROJECT_ID_KEY: None,
            INCUBATION_LOGICAL_ACCOUNT_ID_KEY: None,
        },
        touch=False,
        user_id=owner_user_id,
    )
    return ThreadProjectBindingResponse(thread_id=thread_id, project=None)


@router.put(
    "/threads/{thread_id}/logical-account",
    response_model=ThreadLogicalAccountBindingResponse,
)
@require_permission("threads", "write")
async def bind_thread_logical_account(
    thread_id: ThreadId,
    body: ThreadLogicalAccountBindingRequest,
    request: Request,
) -> ThreadLogicalAccountBindingResponse:
    owner_user_id = await _effective_owner_user_id(request)
    thread_store = await _require_thread(
        request,
        thread_id=thread_id,
        owner_user_id=owner_user_id,
    )
    thread = await thread_store.get(thread_id, user_id=owner_user_id)
    metadata = thread.get("metadata") if thread is not None else None
    bound_project_id = metadata.get(INCUBATION_PROJECT_ID_KEY) if isinstance(metadata, dict) else None
    if isinstance(bound_project_id, str) and bound_project_id and bound_project_id != body.project_id:
        raise HTTPException(
            status_code=409,
            detail="Thread is bound to a different project",
        )

    ledger = get_incubation_ledger_repo(request)
    project = _project_ref(owner_user_id, body.project_id)
    if await ledger.get_project(project) is None:
        raise HTTPException(status_code=404, detail="Project not found")
    record = await ledger.get_logical_account(
        _logical_account_ref(
            owner_user_id,
            body.project_id,
            body.logical_account_id,
        )
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Logical account not found")
    await thread_store.update_metadata(
        thread_id,
        {
            INCUBATION_PROJECT_ID_KEY: body.project_id,
            INCUBATION_LOGICAL_ACCOUNT_ID_KEY: body.logical_account_id,
        },
        touch=False,
        user_id=owner_user_id,
    )
    return ThreadLogicalAccountBindingResponse(
        thread_id=thread_id,
        logical_account=_logical_account_response(record),
    )


@router.get(
    "/threads/{thread_id}/logical-account",
    response_model=ThreadLogicalAccountBindingResponse,
)
@require_permission("threads", "read")
async def get_thread_logical_account(
    thread_id: ThreadId,
    request: Request,
) -> ThreadLogicalAccountBindingResponse:
    owner_user_id = await _effective_owner_user_id(request)
    thread_store = await _require_thread(
        request,
        thread_id=thread_id,
        owner_user_id=owner_user_id,
    )
    thread = await thread_store.get(thread_id, user_id=owner_user_id)
    metadata = thread.get("metadata") if thread is not None else None
    project_id = metadata.get(INCUBATION_PROJECT_ID_KEY) if isinstance(metadata, dict) else None
    logical_account_id = metadata.get(INCUBATION_LOGICAL_ACCOUNT_ID_KEY) if isinstance(metadata, dict) else None
    if not isinstance(logical_account_id, str) or not logical_account_id:
        return ThreadLogicalAccountBindingResponse(
            thread_id=thread_id,
            logical_account=None,
        )
    if not isinstance(project_id, str) or not project_id:
        raise HTTPException(
            status_code=409,
            detail="Thread logical account binding is stale or mismatched",
        )
    record = await get_incubation_ledger_repo(request).get_logical_account(
        _logical_account_ref(
            owner_user_id,
            project_id,
            logical_account_id,
        )
    )
    if record is None:
        raise HTTPException(
            status_code=409,
            detail="Thread logical account binding is stale or mismatched",
        )
    return ThreadLogicalAccountBindingResponse(
        thread_id=thread_id,
        logical_account=_logical_account_response(record),
    )


@router.delete(
    "/threads/{thread_id}/logical-account",
    response_model=ThreadLogicalAccountBindingResponse,
)
@require_permission("threads", "write")
async def unbind_thread_logical_account(
    thread_id: ThreadId,
    request: Request,
) -> ThreadLogicalAccountBindingResponse:
    owner_user_id = await _effective_owner_user_id(request)
    thread_store = await _require_thread(
        request,
        thread_id=thread_id,
        owner_user_id=owner_user_id,
    )
    await thread_store.update_metadata(
        thread_id,
        {INCUBATION_LOGICAL_ACCOUNT_ID_KEY: None},
        touch=False,
        user_id=owner_user_id,
    )
    return ThreadLogicalAccountBindingResponse(
        thread_id=thread_id,
        logical_account=None,
    )
