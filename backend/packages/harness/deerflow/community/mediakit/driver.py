from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any

from deerflow.incubation.media import EphemeralMediaSource
from deerflow.mcp.tasks import TaskReference, TaskSnapshot, TaskStatus, TaskSubmission, TaskSubmitRequest

from .contracts import (
    MediaKitCloudAuthorizationContext,
    MediaKitCloudMaterializationContext,
    MediaKitCloudMaterializedOutput,
)
from .router import MediaKitCapabilityRouter, MediaKitCommandError

CloudAuthorizer = Callable[[MediaKitCloudAuthorizationContext], Awaitable[None]]
CloudSourceResolver = Callable[[str, str, str], Awaitable[EphemeralMediaSource]]
CloudResultMaterializer = Callable[
    [MediaKitCloudMaterializationContext],
    Awaitable[MediaKitCloudMaterializedOutput],
]

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_COMMAND_TOKEN = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
_STABLE_REFERENCE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,254}$")
_WINDOWS_PATH = re.compile(r"^[A-Za-z]:[\\/]")
_SPEC_KEYS = frozenset(
    {
        "project_id",
        "source_ref",
        "rights_ref",
        "source_content_sha256",
        "capability_domain",
        "capability_tool",
        "capability_arguments",
        "expected_schema_sha256",
        "cloud_processing_approval_ref",
        "fee_authorization_ref",
        "currency",
        "maximum_amount_micros",
    }
)
_EXECUTION_ONLY_KEY_PARTS = (
    "api_key",
    "apikey",
    "authorization",
    "client_token",
    "cookie",
    "credential",
    "password",
    "path",
    "secret",
    "token",
    "url",
)
_DURABLE_ARGUMENT_BUDGET_BYTES = 16 * 1024
_CLOUD_OPERATION_CONTRACT_VERSION = "mediakit-cloud-operation-v1"


def _text(value: Any, *, name: str, maximum: int) -> str:
    if not isinstance(value, str):
        raise ValueError(f"MediaKit {name} must be a string")
    normalized = value.strip()
    if not normalized or len(normalized) > maximum:
        raise ValueError(f"MediaKit {name} must contain between 1 and {maximum} characters")
    return normalized


def _stable_reference(value: Any, *, name: str, maximum: int = 255) -> str:
    normalized = _text(value, name=name, maximum=maximum)
    if not _STABLE_REFERENCE.fullmatch(normalized):
        raise ValueError(f"MediaKit {name} must be a stable reference")
    return normalized


def _sha256(value: Any, *, name: str) -> str:
    normalized = _text(value, name=name, maximum=64)
    if not _SHA256.fullmatch(normalized):
        raise ValueError(f"MediaKit {name} must be a SHA-256 digest")
    return normalized


def _canonical_sha256(value: Mapping[str, Any]) -> str:
    serialized = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def _contains_execution_only_value(value: Any, *, key: str | None = None) -> bool:
    if key is not None:
        normalized_key = key.casefold().replace("-", "_")
        if any(part in normalized_key for part in _EXECUTION_ONLY_KEY_PARTS):
            return True
    if isinstance(value, Mapping):
        return any(not isinstance(child_key, str) or _contains_execution_only_value(child, key=child_key) for child_key, child in value.items())
    if isinstance(value, (list, tuple)):
        return any(_contains_execution_only_value(child) for child in value)
    if isinstance(value, str):
        normalized = value.strip().casefold()
        return normalized.startswith(("http://", "https://", "file:", "mediakit://", "/", "~/", "./", "../", "\\\\")) or bool(_WINDOWS_PATH.match(normalized))
    return False


@dataclass(frozen=True, slots=True)
class _CloudTaskSpec:
    project_id: str
    source_ref: str
    rights_ref: str
    source_content_sha256: str
    capability_domain: str
    capability_tool: str
    capability_arguments: dict[str, Any]
    expected_schema_sha256: str
    cloud_processing_approval_ref: str
    fee_authorization_ref: str
    currency: str
    maximum_amount_micros: int

    @property
    def operation_sha256(self) -> str:
        return _canonical_sha256(
            {
                "contract_version": _CLOUD_OPERATION_CONTRACT_VERSION,
                "project_id": self.project_id,
                "source_ref": self.source_ref,
                "rights_ref": self.rights_ref,
                "source_content_sha256": self.source_content_sha256,
                "capability_domain": self.capability_domain,
                "capability_tool": self.capability_tool,
                "capability_arguments": self.capability_arguments,
                "expected_schema_sha256": self.expected_schema_sha256,
                "currency": self.currency,
                "maximum_amount_micros": self.maximum_amount_micros,
            }
        )

    @classmethod
    def from_arguments(cls, value: Mapping[str, Any]) -> _CloudTaskSpec:
        if set(value) != _SPEC_KEYS:
            raise ValueError("MediaKit durable cloud request has an invalid contract")
        capability_arguments = value.get("capability_arguments")
        if not isinstance(capability_arguments, dict):
            raise ValueError("MediaKit capability_arguments must be an object")
        if _contains_execution_only_value(capability_arguments):
            raise ValueError("MediaKit durable arguments contain execution-only values")
        try:
            serialized = json.dumps(
                capability_arguments,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise ValueError("MediaKit capability_arguments must be JSON serializable") from exc
        if len(serialized) > _DURABLE_ARGUMENT_BUDGET_BYTES:
            raise ValueError("MediaKit capability_arguments exceed the durable budget")

        expected_schema_sha256 = _sha256(
            value.get("expected_schema_sha256"),
            name="expected_schema_sha256",
        )
        currency = _text(value.get("currency"), name="currency", maximum=3).upper()
        if len(currency) != 3 or not currency.isalpha():
            raise ValueError("MediaKit currency must be a three-letter code")
        maximum_amount_micros = value.get("maximum_amount_micros")
        if not isinstance(maximum_amount_micros, int) or isinstance(maximum_amount_micros, bool) or maximum_amount_micros <= 0:
            raise ValueError("MediaKit maximum_amount_micros must be a positive integer")
        return cls(
            project_id=_stable_reference(
                value.get("project_id"),
                name="project_id",
                maximum=64,
            ),
            source_ref=_stable_reference(value.get("source_ref"), name="source_ref"),
            rights_ref=_stable_reference(value.get("rights_ref"), name="rights_ref"),
            source_content_sha256=_sha256(
                value.get("source_content_sha256"),
                name="source_content_sha256",
            ),
            capability_domain=_text(
                value.get("capability_domain"),
                name="capability_domain",
                maximum=64,
            ),
            capability_tool=_text(
                value.get("capability_tool"),
                name="capability_tool",
                maximum=64,
            ),
            capability_arguments=dict(capability_arguments),
            expected_schema_sha256=expected_schema_sha256,
            cloud_processing_approval_ref=_stable_reference(
                value.get("cloud_processing_approval_ref"),
                name="cloud_processing_approval_ref",
                maximum=80,
            ),
            fee_authorization_ref=_stable_reference(
                value.get("fee_authorization_ref"),
                name="fee_authorization_ref",
                maximum=80,
            ),
            currency=currency,
            maximum_amount_micros=maximum_amount_micros,
        )


def mediakit_cloud_operation_sha256(arguments: Mapping[str, Any]) -> str:
    """Return the exact approval digest without exposing execution-only data."""

    return _CloudTaskSpec.from_arguments(arguments).operation_sha256


def _required_driver_text(data: Mapping[str, Any], name: str, *, maximum: int = 255) -> str:
    return _text(data.get(name), name=f"driver_data.{name}", maximum=maximum)


def _required_driver_sha256(data: Mapping[str, Any], name: str) -> str:
    value = _required_driver_text(data, name, maximum=64)
    if not _SHA256.fullmatch(value):
        raise ValueError(f"driver_data.{name} must be a SHA-256 digest")
    return value


def _required_driver_amount(data: Mapping[str, Any]) -> int:
    value = data.get("maximum_amount_micros")
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError("driver_data.maximum_amount_micros must be a positive integer")
    return value


def _required_driver_currency(data: Mapping[str, Any]) -> str:
    value = _required_driver_text(data, "currency", maximum=3).upper()
    if len(value) != 3 or any(character not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ" for character in value):
        raise ValueError("driver_data.currency must be a three-letter code")
    return value


@dataclass(frozen=True, slots=True)
class _CloudRecoveryData:
    project_id: str
    source_ref: str
    rights_ref: str
    source_content_sha256: str
    capability_domain: str
    capability_tool: str
    cli_version: str
    capability_schema_sha256: str
    query_schema_sha256: str
    request_sha256: str
    operation_sha256: str
    client_token_sha256: str
    cloud_processing_approval_ref: str
    fee_authorization_ref: str
    currency: str
    maximum_amount_micros: int

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> _CloudRecoveryData:
        source_ref = _stable_reference(data.get("source_ref"), name="driver_data.source_ref")
        rights_ref = _stable_reference(data.get("rights_ref"), name="driver_data.rights_ref")
        capability_domain = _required_driver_text(data, "capability_domain", maximum=64)
        capability_tool = _required_driver_text(data, "capability_tool", maximum=64)
        if not _COMMAND_TOKEN.fullmatch(capability_domain) or not _COMMAND_TOKEN.fullmatch(capability_tool):
            raise ValueError("MediaKit recovery capability contains unsupported characters")
        request_id_sha256 = data.get("request_id_sha256")
        if request_id_sha256 is not None and (not isinstance(request_id_sha256, str) or not _SHA256.fullmatch(request_id_sha256)):
            raise ValueError("driver_data.request_id_sha256 must be a SHA-256 digest")
        return cls(
            project_id=_stable_reference(
                data.get("project_id"),
                name="driver_data.project_id",
                maximum=64,
            ),
            source_ref=source_ref,
            rights_ref=rights_ref,
            source_content_sha256=_required_driver_sha256(
                data,
                "source_content_sha256",
            ),
            capability_domain=capability_domain,
            capability_tool=capability_tool,
            cli_version=_required_driver_text(data, "cli_version", maximum=64),
            capability_schema_sha256=_required_driver_sha256(
                data,
                "capability_schema_sha256",
            ),
            query_schema_sha256=_required_driver_sha256(data, "query_schema_sha256"),
            request_sha256=_required_driver_sha256(data, "request_sha256"),
            operation_sha256=_required_driver_sha256(data, "operation_sha256"),
            client_token_sha256=_required_driver_sha256(data, "client_token_sha256"),
            cloud_processing_approval_ref=_stable_reference(
                data.get("cloud_processing_approval_ref"),
                name="driver_data.cloud_processing_approval_ref",
                maximum=80,
            ),
            fee_authorization_ref=_stable_reference(
                data.get("fee_authorization_ref"),
                name="driver_data.fee_authorization_ref",
                maximum=80,
            ),
            currency=_required_driver_currency(data),
            maximum_amount_micros=_required_driver_amount(data),
        )


class MediaKitCloudDriver:
    """Idempotent MediaKit CLI driver for the durable task runtime."""

    def __init__(
        self,
        *,
        router: MediaKitCapabilityRouter,
        authorize: CloudAuthorizer,
        resolve_source: CloudSourceResolver,
        materialize_result: CloudResultMaterializer,
        poll_after_seconds: float = 5,
        submission_timeout_seconds: float = 180,
        query_timeout_seconds: float = 60,
    ) -> None:
        if poll_after_seconds <= 0:
            raise ValueError("MediaKit poll interval must be positive")
        if submission_timeout_seconds <= 0 or query_timeout_seconds <= 0:
            raise ValueError("MediaKit driver timeouts must be positive")
        self._router = router
        self._authorize = authorize
        self._resolve_source = resolve_source
        self._materialize_result = materialize_result
        self._poll_after_seconds = poll_after_seconds
        self._submission_timeout_seconds = submission_timeout_seconds
        self._query_timeout_seconds = query_timeout_seconds

    async def submit(self, request: TaskSubmitRequest) -> TaskSubmission:
        spec = _CloudTaskSpec.from_arguments(request.arguments)
        local_task_id = _text(
            request.local_task_id,
            name="local_task_id",
            maximum=64,
        )
        capability = await self._router.discover_capability(
            spec.capability_domain,
            spec.capability_tool,
        )
        if capability.schema_sha256 != spec.expected_schema_sha256:
            raise MediaKitCommandError("MediaKit capability schema changed")
        query_capability = await self._router.discover_capability("shared", "query-task")

        authorization = MediaKitCloudAuthorizationContext(
            user_id=request.user_id,
            project_id=spec.project_id,
            local_task_id=local_task_id,
            source_ref=spec.source_ref,
            rights_ref=spec.rights_ref,
            source_content_sha256=spec.source_content_sha256,
            capability_domain=spec.capability_domain,
            capability_tool=spec.capability_tool,
            operation_sha256=spec.operation_sha256,
            cloud_processing_approval_ref=spec.cloud_processing_approval_ref,
            fee_authorization_ref=spec.fee_authorization_ref,
            currency=spec.currency,
            maximum_amount_micros=spec.maximum_amount_micros,
        )
        try:
            await self._authorize(authorization)
        except Exception:
            raise PermissionError("MediaKit cloud authorization failed") from None

        try:
            source = await self._resolve_source(
                request.user_id,
                spec.source_ref,
                spec.rights_ref,
            )
        except Exception:
            raise MediaKitCommandError("MediaKit media source resolution failed") from None
        if not isinstance(source, EphemeralMediaSource):
            raise MediaKitCommandError("MediaKit source resolver returned an invalid contract")
        if source.source_ref != spec.source_ref or source.rights_ref != spec.rights_ref:
            raise MediaKitCommandError("MediaKit resolved source identity mismatch")
        prepared = await self._router.prepare_video_call(
            domain=spec.capability_domain,
            tool=spec.capability_tool,
            source=source,
            mode="cloud",
            arguments=spec.capability_arguments,
            client_token=local_task_id,
        )
        submitted = await self._router.submit_cloud(
            prepared,
            timeout_seconds=self._submission_timeout_seconds,
        )
        driver_data = {
            "project_id": spec.project_id,
            "source_ref": spec.source_ref,
            "rights_ref": spec.rights_ref,
            "source_content_sha256": spec.source_content_sha256,
            "capability_domain": spec.capability_domain,
            "capability_tool": spec.capability_tool,
            "cli_version": capability.cli_version,
            "capability_schema_sha256": capability.schema_sha256,
            "query_schema_sha256": query_capability.schema_sha256,
            "request_sha256": prepared.input_sha256,
            "operation_sha256": spec.operation_sha256,
            "client_token_sha256": prepared.client_token_sha256,
            "request_id_sha256": submitted.request_id_sha256,
            "cloud_processing_approval_ref": spec.cloud_processing_approval_ref,
            "fee_authorization_ref": spec.fee_authorization_ref,
            "currency": spec.currency,
            "maximum_amount_micros": spec.maximum_amount_micros,
        }
        return TaskSubmission(
            remote_task_id=submitted.remote_task_id,
            snapshot=TaskSnapshot(
                status=TaskStatus.SUBMITTED,
                poll_after_seconds=self._poll_after_seconds,
            ),
            driver_data=driver_data,
        )

    async def get_status(self, task: TaskReference) -> TaskSnapshot:
        data = task.driver_data
        try:
            recovery = _CloudRecoveryData.from_mapping(data)
        except (TypeError, ValueError):
            raise MediaKitCommandError("MediaKit task recovery data is invalid") from None
        queried = await self._router.query_cloud_task(
            task.remote_task_id,
            expected_schema_sha256=recovery.query_schema_sha256,
            timeout_seconds=self._query_timeout_seconds,
        )
        status = queried.provider_status
        if status in {"queued", "pending", "submitted"}:
            return TaskSnapshot(
                status=TaskStatus.SUBMITTED,
                poll_after_seconds=self._poll_after_seconds,
            )
        if status in {"processing", "running", "working"}:
            return TaskSnapshot(
                status=TaskStatus.WORKING,
                poll_after_seconds=self._poll_after_seconds,
            )
        if status in {"failed", "error"}:
            return TaskSnapshot(
                status=TaskStatus.FAILED,
                error="MediaKit cloud task failed",
            )
        if status in {"canceled", "cancelled"}:
            return TaskSnapshot(
                status=TaskStatus.CANCELLED,
                error="MediaKit cloud task was cancelled",
            )
        if status not in {"completed", "succeeded", "success"}:
            raise MediaKitCommandError("MediaKit returned an unsupported task status")
        if queried.provider_output.get("success") is False:
            raise MediaKitCommandError("MediaKit completed task carried a failure signal")

        context = MediaKitCloudMaterializationContext(
            local_task_id=task.local_task_id,
            user_id=task.user_id,
            project_id=recovery.project_id,
            thread_id=task.thread_id,
            remote_task_id=task.remote_task_id,
            source_ref=recovery.source_ref,
            rights_ref=recovery.rights_ref,
            source_content_sha256=recovery.source_content_sha256,
            capability_domain=recovery.capability_domain,
            capability_tool=recovery.capability_tool,
            cli_version=recovery.cli_version,
            capability_schema_sha256=recovery.capability_schema_sha256,
            request_sha256=recovery.request_sha256,
            operation_sha256=recovery.operation_sha256,
            client_token_sha256=recovery.client_token_sha256,
            cloud_processing_approval_ref=recovery.cloud_processing_approval_ref,
            fee_authorization_ref=recovery.fee_authorization_ref,
            currency=recovery.currency,
            maximum_amount_micros=recovery.maximum_amount_micros,
            provider_output=queried.provider_output,
            provider_output_sha256=queried.provider_output_sha256,
        )
        try:
            materialized = await self._materialize_result(context)
        except Exception:
            raise MediaKitCommandError("MediaKit result materialization failed") from None
        if not isinstance(materialized, MediaKitCloudMaterializedOutput):
            raise MediaKitCommandError("MediaKit result materializer returned an invalid contract")
        result = materialized.as_result()
        result["provider_output_sha256"] = queried.provider_output_sha256
        return TaskSnapshot(status=TaskStatus.COMPLETED, result=result)

    async def cancel(self, task: TaskReference) -> TaskSnapshot:
        del task
        raise MediaKitCommandError("MediaKit cloud tasks do not support cancellation")


__all__ = [
    "CloudAuthorizer",
    "CloudResultMaterializer",
    "CloudSourceResolver",
    "MediaKitCloudDriver",
    "mediakit_cloud_operation_sha256",
]
