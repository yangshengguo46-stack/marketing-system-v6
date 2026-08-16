from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.gateway.authz import require_permission
from app.gateway.deps import (
    get_incubation_ledger_repo,
    get_optional_user_from_request,
    get_thread_store,
)
from app.gateway.internal_auth import INTERNAL_SYSTEM_ROLE, get_trusted_internal_owner_user_id
from deerflow.incubation import INCUBATION_PROJECT_ID_KEY, ProjectRecord, ProjectRef
from deerflow.persistence.incubation_ledger import ProjectConflictError
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


class ThreadProjectBindingRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    project_id: str = Field(min_length=1, max_length=64)


class ThreadProjectBindingResponse(BaseModel):
    thread_id: str
    project: IncubationProjectResponse | None


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


def _response(record: ProjectRecord) -> IncubationProjectResponse:
    return IncubationProjectResponse(
        project_id=record.project.project_id,
        display_name=record.display_name,
        created_at=record.created_at,
        updated_at=record.updated_at,
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
    record = await get_incubation_ledger_repo(request).get_project(_project_ref(owner_user_id, body.project_id))
    if record is None:
        raise HTTPException(status_code=404, detail="Project not found")
    await thread_store.update_metadata(
        thread_id,
        {INCUBATION_PROJECT_ID_KEY: record.project.project_id},
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
        {INCUBATION_PROJECT_ID_KEY: None},
        touch=False,
        user_id=owner_user_id,
    )
    return ThreadProjectBindingResponse(thread_id=thread_id, project=None)
