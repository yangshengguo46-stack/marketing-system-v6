from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import UUID

from _router_auth_helpers import make_authed_test_app
from fastapi.testclient import TestClient
from langgraph.store.memory import InMemoryStore

from app.gateway.auth.models import User
from app.gateway.routers import incubation_projects
from deerflow.incubation import ProjectRecord, ProjectRef
from deerflow.persistence.thread_meta.memory import MemoryThreadMetaStore

NOW = datetime(2026, 8, 17, 12, 0, tzinfo=UTC)
USER_ID = "11111111-1111-4111-8111-111111111111"
OTHER_USER_ID = "22222222-2222-4222-8222-222222222222"


def _user() -> User:
    return User(
        email="incubation@example.com",
        password_hash="x",
        system_role="user",
        id=UUID(USER_ID),
    )


class _FakeLedger:
    def __init__(self) -> None:
        self.projects: dict[tuple[str, str], ProjectRecord] = {}

    async def create_project(self, project: ProjectRef, *, display_name: str) -> ProjectRecord:
        record = ProjectRecord(
            project=project,
            display_name=display_name,
            created_at=NOW,
            updated_at=NOW,
        )
        self.projects[(project.owner_user_id, project.project_id)] = record
        return record

    async def get_project(self, project: ProjectRef) -> ProjectRecord | None:
        return self.projects.get((project.owner_user_id, project.project_id))

    async def list_projects(self, owner_user_id: str, *, limit: int = 100, offset: int = 0) -> list[ProjectRecord]:
        rows = [record for (owner, _project_id), record in self.projects.items() if owner == owner_user_id]
        return rows[offset : offset + limit]


def _build_app() -> tuple[object, _FakeLedger, MemoryThreadMetaStore]:
    app = make_authed_test_app(user_factory=_user)
    ledger = _FakeLedger()
    thread_store = MemoryThreadMetaStore(InMemoryStore())
    app.state.incubation_ledger_repo = ledger
    app.state.thread_store = thread_store
    app.include_router(incubation_projects.router)
    return app, ledger, thread_store


def test_create_list_and_get_projects_do_not_expose_owner_identity() -> None:
    app, _ledger, _thread_store = _build_app()

    with TestClient(app) as client:
        created = client.post(
            "/api/incubation/projects",
            json={"project_id": "golden-gift", "display_name": "黄金礼品账号"},
        )
        listed = client.get("/api/incubation/projects")
        fetched = client.get("/api/incubation/projects/golden-gift")

    assert created.status_code == 201, created.text
    assert created.json()["project_id"] == "golden-gift"
    assert "owner_user_id" not in created.text
    assert listed.status_code == 200
    assert [row["project_id"] for row in listed.json()] == ["golden-gift"]
    assert fetched.status_code == 200
    assert fetched.json()["display_name"] == "黄金礼品账号"


def test_thread_binding_requires_owned_project_and_rehydrates_binding() -> None:
    app, ledger, thread_store = _build_app()

    async def seed() -> None:
        await thread_store.create("thread-1", user_id=USER_ID)
        await ledger.create_project(
            ProjectRef(owner_user_id=USER_ID, project_id="golden-gift"),
            display_name="黄金礼品账号",
        )
        await ledger.create_project(
            ProjectRef(owner_user_id=OTHER_USER_ID, project_id="other-user-project"),
            display_name="其他用户项目",
        )

    asyncio.run(seed())

    with TestClient(app) as client:
        bound = client.put(
            "/api/incubation/threads/thread-1/project",
            json={"project_id": "golden-gift"},
        )
        current = client.get("/api/incubation/threads/thread-1/project")
        missing = client.put(
            "/api/incubation/threads/thread-1/project",
            json={"project_id": "other-user-project"},
        )

    assert bound.status_code == 200, bound.text
    assert bound.json()["project"]["project_id"] == "golden-gift"
    assert current.status_code == 200
    assert current.json()["project"]["project_id"] == "golden-gift"
    assert missing.status_code == 404


def test_thread_binding_rejects_unknown_thread() -> None:
    app, ledger, _thread_store = _build_app()
    asyncio.run(
        ledger.create_project(
            ProjectRef(owner_user_id=USER_ID, project_id="golden-gift"),
            display_name="黄金礼品账号",
        )
    )

    with TestClient(app) as client:
        response = client.put(
            "/api/incubation/threads/missing-thread/project",
            json={"project_id": "golden-gift"},
        )

    assert response.status_code == 404
