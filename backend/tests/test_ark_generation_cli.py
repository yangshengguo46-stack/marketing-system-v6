from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from deerflow.community.ark_generation import (
    ArkCliCommandResult,
    ArkCliGenerationError,
    ArkCliTextToVideoClient,
)
from deerflow.incubation.ark_generation import (
    ArkGenerationTaskSnapshot,
    ArkTextToVideoOperation,
)
from deerflow.incubation.contracts import ArtifactParentRef

NOW = datetime(2026, 8, 22, 12, 0, tzinfo=UTC)
HARNESS_ROOT = Path(__file__).parents[1] / "packages" / "harness" / "deerflow"


def _operation(
    *,
    model: str = "doubao-seedance-complete-version",
    parameters: dict[str, object] | None = None,
    prompt: str = "清晨的桌面上，一本深蓝色笔记本被缓慢打开。",
) -> ArkTextToVideoOperation:
    values: dict[str, object] = {
        "schema_version": "v6-ark-text-to-video-operation-v1",
        "operation_id": "ark-video-1",
        "production_plan_ref": ArtifactParentRef(
            owner_user_id="user-1",
            project_id="project-1",
            artifact_id="artifact-plan-1",
            artifact_type="production_plan",
            content_sha256="a" * 64,
        ),
        "production_action_id": "action-generate-video",
        "plan_asset_id": "asset-generated-video",
        "assembly_step_id": "step-generated-video",
        "prompt": prompt,
        "model": model,
        "parameters": (parameters if parameters is not None else {"ratio": "9:16", "resolution": "720p", "duration": 5}),
    }
    return ArkTextToVideoOperation.seal(**values)


def _task(
    operation: ArkTextToVideoOperation,
    *,
    status: str = "queued",
    task_id: str = "task-123",
) -> ArkGenerationTaskSnapshot:
    return ArkGenerationTaskSnapshot(
        operation_sha256=operation.operation_sha256,
        provider_task_id=task_id,
        selected_model=operation.model,
        status=status,
        provider_result_sha256="b" * 64,
        updated_at=NOW,
    )


class QueueRunner:
    def __init__(self, results: list[ArkCliCommandResult | BaseException]) -> None:
        self.results = list(results)
        self.calls: list[tuple[tuple[str, ...], float, dict[str, str]]] = []

    async def __call__(
        self,
        command: tuple[str, ...],
        timeout_seconds: float,
        env: dict[str, str],
    ) -> ArkCliCommandResult:
        self.calls.append((command, timeout_seconds, dict(env)))
        result = self.results.pop(0)
        if isinstance(result, BaseException):
            raise result
        return result


def _result(payload: object, *, returncode: int = 0, stderr: str = "") -> ArkCliCommandResult:
    return ArkCliCommandResult(
        returncode=returncode,
        stdout=json.dumps(payload, ensure_ascii=False),
        stderr=stderr,
    )


def test_boundary_has_no_default_runner_and_is_not_registered_to_the_lead() -> None:
    with pytest.raises(TypeError):
        ArkCliTextToVideoClient()  # type: ignore[call-arg]

    registered_surface = "\n".join(
        path.read_text(encoding="utf-8")
        for root in (
            HARNESS_ROOT / "tools",
            HARNESS_ROOT / "agents" / "lead_agent",
        )
        for path in root.rglob("*.py")
    )
    assert "ArkCliTextToVideoClient" not in registered_surface
    assert "prepare_ark_text_to_video_operation" not in registered_surface


def test_command_result_repr_never_exposes_cli_streams() -> None:
    result = ArkCliCommandResult(
        returncode=1,
        stdout='{"api_key":"ark-provider-super-secret"}',
        stderr="Authorization: Bearer provider-super-secret",
    )

    rendered = repr(result)
    assert "provider-super-secret" not in rendered
    assert "ark-provider" not in rendered


@pytest.mark.asyncio
async def test_submit_follows_auth_resource_model_contract_then_async_gen() -> None:
    runner = QueueRunner(
        [
            _result({"logged_in": True}),
            _result(
                {
                    "items": [
                        {
                            "id": "doubao-seedance-complete-version",
                            "is_default": True,
                        }
                    ]
                }
            ),
            _result(
                [
                    {"name": "ratio", "support": True, "type": "string", "enum": ["9:16", "16:9"]},
                    {"name": "resolution", "support": True, "type": "string", "enum": ["720p", "1080p"]},
                    {"name": "duration", "support": True, "type": "integer", "min": 3, "max": 10},
                    {"name": "camera_fixed", "support": True, "type": "boolean"},
                ]
            ),
            _result({"kind": "video", "status": "queued", "task_id": "task-123"}),
        ]
    )
    operation = _operation(
        parameters={
            "ratio": "9:16",
            "resolution": "720p",
            "duration": 5,
            "camera_fixed": True,
        },
    )

    snapshot = await ArkCliTextToVideoClient(runner=runner, clock=lambda: NOW).submit_once(operation)

    assert snapshot.status == "queued"
    assert snapshot.provider_task_id == "task-123"
    assert snapshot.operation_sha256 == operation.operation_sha256
    assert [call[0][1:3] for call in runner.calls[:3]] == [
        ("auth", "status"),
        ("resources", "list"),
        ("models", "get"),
    ]
    submit = runner.calls[-1][0]
    assert submit[:2] == ("arkcli", "+gen")
    assert "--no-open" in submit
    assert "--format" in submit and submit[submit.index("--format") + 1] == "json"
    assert "--modality" in submit and submit[submit.index("--modality") + 1] == "video"
    assert "--ratio" in submit and submit[submit.index("--ratio") + 1] == "9:16"
    assert "--resolution" in submit and submit[submit.index("--resolution") + 1] == "720p"
    assert "--duration" in submit and submit[submit.index("--duration") + 1] == "5"
    assert "--camera-fixed=true" in submit
    assert submit[-2:] == ("--", operation.prompt)
    assert not {
        "--input",
        "--callback-url",
        "--extra-body",
        "--force",
        "--wait",
        "--open",
        "--api-key",
        "--base-url",
    }.intersection(submit)
    assert runner.calls[-1][2] == {
        "ARKCLI_CALLER_TYPE": "ai_agent",
        "ARKCLI_CALLER_NAME": "deerflow",
        "ARKCLI_SKILL_NAME": "arkcli-gen",
    }


@pytest.mark.asyncio
async def test_prompt_cannot_be_reinterpreted_as_an_arkcli_flag() -> None:
    runner = QueueRunner(
        [
            _result({"logged_in": True}),
            _result({"items": [{"id": "ep-video-default", "is_default": True}]}),
            _result({"kind": "video", "status": "queued", "task_id": "task-flag-prompt"}),
        ]
    )
    operation = _operation(model="ep-video-default", prompt="--force")

    await ArkCliTextToVideoClient(runner=runner, clock=lambda: NOW).submit_once(operation)

    submit = runner.calls[-1][0]
    assert submit[-2:] == ("--", "--force")
    assert submit.count("--force") == 1
    assert submit.index("--force") > submit.index("--")


@pytest.mark.asyncio
async def test_explicit_endpoint_resolves_and_skips_model_supported_params() -> None:
    runner = QueueRunner(
        [
            _result({"logged_in": True}),
            _result({"generation_modality": "video"}),
            _result({"kind": "video", "status": "queued", "task_id": "task-ep"}),
        ]
    )

    snapshot = await ArkCliTextToVideoClient(runner=runner, clock=lambda: NOW).submit_once(_operation(model="ep-explicit"))

    assert snapshot.selected_model == "ep-explicit"
    assert runner.calls[1][0] == (
        "arkcli",
        "resources",
        "resolve",
        "ep-explicit",
        "--format",
        "json",
    )
    assert all("models" not in call[0] for call in runner.calls)


@pytest.mark.asyncio
async def test_unsupported_parameter_stops_before_generation_with_safe_error() -> None:
    runner = QueueRunner(
        [
            _result({"logged_in": True}),
            _result({"items": [{"id": "doubao-seedance-complete-version", "is_default": True}]}),
            _result([{"name": "ratio", "support": True}]),
        ]
    )

    with pytest.raises(ArkCliGenerationError, match="resolution") as caught:
        await ArkCliTextToVideoClient(runner=runner, clock=lambda: NOW).submit_once(_operation(parameters={"ratio": "9:16", "resolution": "720p", "duration": 5}))

    assert caught.value.code == "parameter_contract_failed"
    assert all("+gen" not in call[0] for call in runner.calls)


@pytest.mark.asyncio
async def test_existing_queued_task_is_returned_without_any_resubmission() -> None:
    operation = _operation()
    existing = _task(operation)
    runner = QueueRunner([])

    returned = await ArkCliTextToVideoClient(
        runner=runner,
        clock=lambda: NOW,
    ).submit_once(operation, existing=existing)

    assert returned is existing
    assert runner.calls == []


@pytest.mark.asyncio
async def test_existing_task_must_bind_the_exact_selected_model() -> None:
    operation = _operation()
    existing = _task(operation).model_copy(update={"selected_model": "different-model-v9"})
    runner = QueueRunner([])

    with pytest.raises(ArkCliGenerationError) as caught:
        await ArkCliTextToVideoClient(runner=runner, clock=lambda: NOW).submit_once(
            operation,
            existing=existing,
        )

    assert caught.value.code == "task_binding_mismatch"
    assert runner.calls == []


@pytest.mark.asyncio
async def test_submit_rejects_a_provider_response_for_another_model() -> None:
    runner = QueueRunner(
        [
            _result({"logged_in": True}),
            _result({"generation_modality": "video"}),
            _result(
                {
                    "kind": "video",
                    "status": "queued",
                    "task_id": "task-wrong-model",
                    "model": "ep-another-model",
                }
            ),
        ]
    )

    with pytest.raises(ArkCliGenerationError) as caught:
        await ArkCliTextToVideoClient(runner=runner, clock=lambda: NOW).submit_once(_operation(model="ep-explicit"))

    assert caught.value.code == "task_model_mismatch"


@pytest.mark.asyncio
async def test_poll_is_independent_and_can_never_submit_a_new_generation() -> None:
    operation = _operation()
    existing = _task(operation)
    runner = QueueRunner(
        [
            _result(
                {
                    "logged_in": True,
                    "control_plane_auth": {"status": "needs_login"},
                }
            ),
            _result(
                {
                    "id": "task-123",
                    "model": "doubao-seedance-complete-version",
                    "status": "succeeded",
                    "output_url": "https://temporary.example.test/private-result.mp4",
                    "local_path": "/private/tmp/private-result.mp4",
                }
            ),
        ]
    )

    updated = await ArkCliTextToVideoClient(runner=runner, clock=lambda: NOW).poll(existing)

    assert updated.status == "succeeded"
    assert updated.provider_task_id == existing.provider_task_id
    assert len(updated.provider_result_sha256) == 64
    assert [call[0][1:3] for call in runner.calls] == [
        ("auth", "status"),
        ("gen", "get"),
    ]
    poll_command = runner.calls[-1][0]
    assert poll_command[:4] == ("arkcli", "gen", "get", "task-123")
    assert "--save-to" in poll_command
    assert poll_command[poll_command.index("--save-to") + 1] == ""
    assert "--no-open" in poll_command
    assert all("+gen" not in call[0] for call in runner.calls)
    serialized = updated.model_dump_json()
    assert "temporary.example" not in serialized
    assert "/private/tmp" not in serialized


@pytest.mark.asyncio
async def test_terminal_task_poll_is_a_noop() -> None:
    operation = _operation()
    existing = _task(operation, status="succeeded")
    runner = QueueRunner([])

    updated = await ArkCliTextToVideoClient(runner=runner, clock=lambda: NOW).poll(existing)

    assert updated is existing
    assert runner.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure",
    [
        ArkCliCommandResult(
            returncode=1,
            stdout="",
            stderr="Authorization: Bearer provider-super-secret",
        ),
        ArkCliCommandResult(
            returncode=0,
            stdout='{"api_key":"ark-provider-super-secret"',
            stderr="",
        ),
        RuntimeError("https://private.example.test/?token=provider-super-secret"),
    ],
)
async def test_every_cli_failure_surface_is_redacted(
    failure: ArkCliCommandResult | BaseException,
) -> None:
    runner = QueueRunner([failure])

    with pytest.raises(ArkCliGenerationError) as caught:
        await ArkCliTextToVideoClient(runner=runner, clock=lambda: NOW).submit_once(_operation())

    rendered = f"{caught.value!s} {caught.value!r}"
    assert "provider-super-secret" not in rendered
    assert "private.example" not in rendered
    assert "ark-provider" not in rendered
