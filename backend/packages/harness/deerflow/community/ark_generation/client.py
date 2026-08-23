from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from deerflow.incubation.ark_generation import (
    ArkGenerationTaskSnapshot,
    ArkTextToVideoOperation,
)

_MAX_STDOUT_BYTES = 1024 * 1024
_STABLE_PROVIDER_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,254}$")
_TERMINAL_STATUSES = frozenset({"succeeded", "failed", "cancelled"})
_PARAMETER_ORDER = (
    "ratio",
    "resolution",
    "duration",
    "seed",
    "watermark",
    "generate_audio",
    "camera_fixed",
    "draft",
    "priority",
)
_CALLER_ENV = {
    "ARKCLI_CALLER_TYPE": "ai_agent",
    "ARKCLI_CALLER_NAME": "deerflow",
    "ARKCLI_SKILL_NAME": "arkcli-gen",
}


@dataclass(frozen=True, slots=True, repr=False)
class ArkCliCommandResult:
    returncode: int
    stdout: str
    stderr: str
    stdout_truncated: bool = False
    stderr_truncated: bool = False

    def __repr__(self) -> str:
        return f"ArkCliCommandResult(returncode={self.returncode!r}, stdout='<redacted>', stderr='<redacted>')"


class ArkCliRunner(Protocol):
    async def __call__(
        self,
        command: tuple[str, ...],
        timeout_seconds: float,
        env: dict[str, str],
    ) -> ArkCliCommandResult: ...


class ArkCliGenerationError(RuntimeError):
    """A bounded error that never includes Ark stdout, stderr, locators, or secrets."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)

    def __repr__(self) -> str:
        return f"ArkCliGenerationError(code={self.code!r}, message={str(self)!r})"


def _canonical_sha256(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _provider_id(value: object, *, code: str, label: str) -> str:
    if not isinstance(value, str):
        raise ArkCliGenerationError(code, f"Ark {label} is invalid")
    normalized = value.strip()
    if not _STABLE_PROVIDER_ID.fullmatch(normalized):
        raise ArkCliGenerationError(code, f"Ark {label} is invalid")
    return normalized


def _payload_body(payload: object, *, code: str, label: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ArkCliGenerationError(code, f"Ark {label} returned an invalid contract")
    data = payload.get("data")
    if isinstance(data, dict):
        return data
    return payload


def _reject_json_constant(_value: str) -> None:
    raise ValueError("non-finite JSON value")


class ArkCliTextToVideoClient:
    """Unregistered text-to-video V1 CLI boundary with an injected runner only."""

    def __init__(
        self,
        *,
        runner: ArkCliRunner,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._runner = runner
        self._clock = clock

    async def submit_once(
        self,
        operation: ArkTextToVideoOperation,
        *,
        existing: ArkGenerationTaskSnapshot | None = None,
    ) -> ArkGenerationTaskSnapshot:
        """Issue at most one ``+gen`` call during this adapter invocation.

        The caller-supplied ``existing`` check is only a short circuit, not a
        durable or atomic at-most-once fence. This adapter is unregistered and
        must remain behind a persistent submission policy before any live use.
        """

        operation = ArkTextToVideoOperation.model_validate(operation.model_dump(mode="python"))
        if existing is not None:
            validated_existing = ArkGenerationTaskSnapshot.model_validate(existing.model_dump(mode="python"))
            if validated_existing.operation_sha256 != operation.operation_sha256:
                raise ArkCliGenerationError(
                    "task_binding_mismatch",
                    "Existing Ark task belongs to a different operation",
                )
            if validated_existing.selected_model != operation.model:
                raise ArkCliGenerationError(
                    "task_binding_mismatch",
                    "Existing Ark task belongs to a different model selection",
                )
            return existing

        await self._require_auth(require_control_plane=True)
        selected_model = await self._resolve_resource(operation)
        if not selected_model.startswith("ep-"):
            await self._validate_supported_parameters(
                selected_model,
                operation.parameters.supplied(),
            )

        command: list[str] = [
            "arkcli",
            "+gen",
            "--model",
            selected_model,
            "--modality",
            "video",
            "--save-to",
            "",
            "--no-open",
            "--format",
            "json",
        ]
        supplied = operation.parameters.supplied()
        for name in _PARAMETER_ORDER:
            if name not in supplied:
                continue
            value = supplied[name]
            flag = f"--{name.replace('_', '-')}"
            if isinstance(value, bool):
                command.append(f"{flag}={str(value).lower()}")
            else:
                command.extend((flag, str(value)))
        # ArkCLI uses Cobra/pflag and accepts options after positional values.
        # Terminate option parsing so a model-authored prompt that begins with
        # ``--`` can never become an ArkCLI escape-hatch flag.
        command.extend(("--", operation.prompt))
        payload = await self._run_json(
            tuple(command),
            timeout_seconds=120,
            code="submission_failed",
            label="generation submission",
        )
        return self._task_snapshot(
            payload,
            operation_sha256=operation.operation_sha256,
            selected_model=selected_model,
            expected_task_id=None,
            code="submission_failed",
        )

    async def poll(
        self,
        task: ArkGenerationTaskSnapshot,
    ) -> ArkGenerationTaskSnapshot:
        """Query one existing task exactly once; this path contains no submit command."""

        validated_task = ArkGenerationTaskSnapshot.model_validate(task.model_dump(mode="python"))
        if validated_task.status in _TERMINAL_STATUSES:
            return task
        await self._require_auth(require_control_plane=False)
        payload = await self._run_json(
            (
                "arkcli",
                "gen",
                "get",
                validated_task.provider_task_id,
                "--save-to",
                "",
                "--no-open",
                "--format",
                "json",
            ),
            timeout_seconds=60,
            code="status_failed",
            label="generation status",
        )
        return self._task_snapshot(
            payload,
            operation_sha256=validated_task.operation_sha256,
            selected_model=validated_task.selected_model,
            expected_task_id=validated_task.provider_task_id,
            code="status_failed",
        )

    async def _require_auth(self, *, require_control_plane: bool) -> None:
        payload = await self._run_json(
            ("arkcli", "auth", "status", "--format", "json"),
            timeout_seconds=30,
            code="authentication_failed",
            label="authentication status",
        )
        body = _payload_body(
            payload,
            code="authentication_failed",
            label="authentication status",
        )
        if body.get("logged_in") is not True:
            raise ArkCliGenerationError(
                "authentication_required",
                "Ark authentication is required",
            )
        control_plane = body.get("control_plane_auth")
        if require_control_plane and isinstance(control_plane, Mapping) and control_plane.get("status") == "needs_login":
            raise ArkCliGenerationError(
                "control_plane_authentication_required",
                "Ark control-plane authentication is required",
            )

    async def _resolve_resource(self, operation: ArkTextToVideoOperation) -> str:
        requested = operation.model
        if requested.startswith("ep-"):
            payload = await self._run_json(
                (
                    "arkcli",
                    "resources",
                    "resolve",
                    requested,
                    "--format",
                    "json",
                ),
                timeout_seconds=60,
                code="resource_resolution_failed",
                label="resource resolution",
            )
            body = _payload_body(
                payload,
                code="resource_resolution_failed",
                label="resource resolution",
            )
            modality = body.get("generation_modality")
            if modality not in {None, "video", "image_or_video", "unknown"}:
                raise ArkCliGenerationError(
                    "resource_modality_mismatch",
                    "Ark resource does not support video generation",
                )
            return requested

        payload = await self._run_json(
            (
                "arkcli",
                "resources",
                "list",
                "--modality",
                "video",
                "--format",
                "json",
            ),
            timeout_seconds=60,
            code="resource_resolution_failed",
            label="resource listing",
        )
        body = _payload_body(
            payload,
            code="resource_resolution_failed",
            label="resource listing",
        )
        raw_items = body.get("items")
        if not isinstance(raw_items, list):
            raise ArkCliGenerationError(
                "resource_resolution_failed",
                "Ark resource listing returned an invalid contract",
            )
        candidates: list[tuple[str, bool]] = []
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            raw_id = item.get("id")
            if not isinstance(raw_id, str) or not _STABLE_PROVIDER_ID.fullmatch(raw_id.strip()):
                continue
            candidates.append((raw_id.strip(), item.get("is_default") is True))

        if not any(candidate == requested for candidate, _ in candidates):
            raise ArkCliGenerationError(
                "resource_not_available",
                "Requested Ark resource is not available for video generation",
            )
        return requested

    async def _validate_supported_parameters(
        self,
        model: str,
        requested: Mapping[str, str | int | bool],
    ) -> None:
        payload = await self._run_json(
            (
                "arkcli",
                "models",
                "get",
                model,
                "--transform",
                "supported_params",
                "--format",
                "json",
            ),
            timeout_seconds=60,
            code="parameter_contract_failed",
            label="supported parameter discovery",
        )
        supported: object = payload
        if isinstance(supported, dict):
            supported = supported.get("supported_params", supported.get("items"))
        if supported in (None, []):
            if requested:
                name = next(name for name in _PARAMETER_ORDER if name in requested)
                raise ArkCliGenerationError(
                    "parameter_contract_failed",
                    f"Ark model does not publish support for parameter: {name}",
                )
            return
        if not isinstance(supported, list):
            raise ArkCliGenerationError(
                "parameter_contract_failed",
                "Ark supported parameter contract is invalid",
            )
        metadata = {item["name"]: item for item in supported if isinstance(item, dict) and isinstance(item.get("name"), str) and item.get("support") is True}
        for name, value in requested.items():
            item = metadata.get(name)
            if item is None:
                raise ArkCliGenerationError(
                    "parameter_contract_failed",
                    f"Ark model does not support parameter: {name}",
                )
            self._validate_parameter_value(name, value, item)

    @staticmethod
    def _validate_parameter_value(
        name: str,
        value: str | int | bool,
        metadata: Mapping[str, Any],
    ) -> None:
        expected_type = metadata.get("type")
        type_matches = {
            "string": isinstance(value, str),
            "integer": isinstance(value, int) and not isinstance(value, bool),
            "int": isinstance(value, int) and not isinstance(value, bool),
            "number": isinstance(value, (int, float)) and not isinstance(value, bool),
            "float": isinstance(value, (int, float)) and not isinstance(value, bool),
            "boolean": isinstance(value, bool),
            "bool": isinstance(value, bool),
        }
        if isinstance(expected_type, str) and expected_type.casefold() in type_matches and not type_matches[expected_type.casefold()]:
            raise ArkCliGenerationError(
                "parameter_contract_failed",
                f"Ark parameter type is invalid: {name}",
            )
        choices = metadata.get("enum")
        if isinstance(choices, list) and value not in choices:
            raise ArkCliGenerationError(
                "parameter_contract_failed",
                f"Ark parameter value is outside the supported enum: {name}",
            )
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            minimum = metadata.get("min")
            maximum = metadata.get("max")
            if isinstance(minimum, (int, float)) and math.isfinite(minimum) and value < minimum:
                raise ArkCliGenerationError(
                    "parameter_contract_failed",
                    f"Ark parameter value is below the supported range: {name}",
                )
            if isinstance(maximum, (int, float)) and math.isfinite(maximum) and value > maximum:
                raise ArkCliGenerationError(
                    "parameter_contract_failed",
                    f"Ark parameter value is above the supported range: {name}",
                )

    def _task_snapshot(
        self,
        payload: object,
        *,
        operation_sha256: str,
        selected_model: str,
        expected_task_id: str | None,
        code: str,
    ) -> ArkGenerationTaskSnapshot:
        body = _payload_body(payload, code=code, label="generation task")
        raw_status = body.get("status")
        if not isinstance(raw_status, str):
            raise ArkCliGenerationError(code, "Ark generation task status is invalid")
        status = {
            "pending": "queued",
            "queued": "queued",
            "processing": "running",
            "running": "running",
            "success": "succeeded",
            "succeeded": "succeeded",
            "failed": "failed",
            "canceled": "cancelled",
            "cancelled": "cancelled",
        }.get(raw_status.strip().casefold())
        if status is None:
            raise ArkCliGenerationError(code, "Ark generation task status is invalid")
        task_id = _provider_id(
            body.get("task_id") or body.get("id"),
            code=code,
            label="generation task identity",
        )
        if expected_task_id is not None and task_id != expected_task_id:
            raise ArkCliGenerationError(
                "task_identity_mismatch",
                "Ark generation task identity changed during polling",
            )
        kind = body.get("kind") or body.get("modality")
        if isinstance(kind, str) and kind.casefold() not in {"video"}:
            raise ArkCliGenerationError(
                "resource_modality_mismatch",
                "Ark generation result is not a video task",
            )
        raw_model = body.get("model")
        if raw_model is not None:
            response_model = _provider_id(
                raw_model,
                code="task_model_mismatch",
                label="generation task model",
            )
            if response_model != selected_model:
                raise ArkCliGenerationError(
                    "task_model_mismatch",
                    "Ark generation task model changed from the sealed selection",
                )
        return ArkGenerationTaskSnapshot(
            operation_sha256=operation_sha256,
            provider_task_id=task_id,
            selected_model=selected_model,
            status=status,
            provider_result_sha256=_canonical_sha256(payload),
            updated_at=self._clock(),
        )

    async def _run_json(
        self,
        command: tuple[str, ...],
        *,
        timeout_seconds: float,
        code: str,
        label: str,
    ) -> object:
        try:
            result = await self._runner(
                command,
                timeout_seconds,
                dict(_CALLER_ENV),
            )
        except Exception:
            raise ArkCliGenerationError(code, f"Ark {label} failed") from None
        if not isinstance(result, ArkCliCommandResult) or result.returncode != 0 or result.stdout_truncated or not isinstance(result.stdout, str) or len(result.stdout.encode("utf-8")) > _MAX_STDOUT_BYTES:
            raise ArkCliGenerationError(code, f"Ark {label} failed")
        try:
            payload = json.loads(
                result.stdout,
                parse_constant=_reject_json_constant,
            )
        except (TypeError, ValueError, UnicodeError):
            raise ArkCliGenerationError(code, f"Ark {label} returned invalid JSON") from None
        if isinstance(payload, dict) and (payload.get("success") is False or payload.get("error")):
            raise ArkCliGenerationError(code, f"Ark {label} returned an error")
        return payload


__all__ = [
    "ArkCliCommandResult",
    "ArkCliGenerationError",
    "ArkCliRunner",
    "ArkCliTextToVideoClient",
]
