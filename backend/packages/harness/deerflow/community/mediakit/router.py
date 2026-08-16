from __future__ import annotations

import asyncio
import hashlib
import json
import re
from collections.abc import Awaitable, Callable, Mapping
from datetime import UTC, datetime
from typing import Any

from jsonschema import Draft202012Validator

from deerflow.incubation.media import EphemeralMediaSource

from .contracts import (
    CommandResult,
    ExecutionMode,
    MediaKitCapability,
    MediaKitCloudQueryResult,
    MediaKitCloudSubmissionResult,
    MediaKitExecutionResult,
    PreparedMediaKitCall,
)

CommandRunner = Callable[[tuple[str, ...], float], Awaitable[CommandResult]]

_COMMAND_TOKEN = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
_VERSION_LINE = re.compile(r"^mediakit-cli(?:\s+version)?\s+([^\s]+)$", re.MULTILINE)
_MAX_PROCESS_OUTPUT_BYTES = 1024 * 1024


class MediaKitCommandError(RuntimeError):
    """A bounded error that never includes command arguments or provider payloads."""


async def _default_runner(
    command: tuple[str, ...],
    timeout_seconds: float,
) -> CommandResult:
    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except OSError as exc:
        raise MediaKitCommandError("MediaKit CLI could not be started") from exc
    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(),
            timeout=timeout_seconds,
        )
    except TimeoutError as exc:
        process.kill()
        await process.communicate()
        raise MediaKitCommandError("MediaKit CLI timed out") from exc
    stdout_truncated = len(stdout) > _MAX_PROCESS_OUTPUT_BYTES
    stderr_truncated = len(stderr) > _MAX_PROCESS_OUTPUT_BYTES
    return CommandResult(
        returncode=process.returncode or 0,
        stdout=stdout[:_MAX_PROCESS_OUTPUT_BYTES].decode("utf-8", errors="replace"),
        stderr=stderr[:_MAX_PROCESS_OUTPUT_BYTES].decode("utf-8", errors="replace"),
        stdout_truncated=stdout_truncated,
        stderr_truncated=stderr_truncated,
    )


def _canonical_sha256(value: Any) -> str:
    canonical = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _require_command_token(value: str, *, name: str) -> str:
    if not _COMMAND_TOKEN.fullmatch(value):
        raise ValueError(f"MediaKit {name} contains unsupported characters")
    return value


def _json_payload(
    result: CommandResult,
    *,
    operation: str,
    allow_structured_failure: bool = False,
) -> dict[str, Any]:
    if result.returncode != 0 and not allow_structured_failure:
        raise MediaKitCommandError(f"MediaKit {operation} failed")
    if result.stdout_truncated or len(result.stdout.encode("utf-8")) > _MAX_PROCESS_OUTPUT_BYTES:
        raise MediaKitCommandError(f"MediaKit {operation} exceeded its output budget")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise MediaKitCommandError(f"MediaKit {operation} returned invalid JSON") from exc
    if not isinstance(payload, dict):
        raise MediaKitCommandError(f"MediaKit {operation} returned an invalid payload")
    if result.returncode != 0 and payload.get("success") is not False:
        raise MediaKitCommandError(f"MediaKit {operation} failed")
    return payload


def _notice_messages(value: Any) -> tuple[str, ...]:
    messages: list[str] = []

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            message = node.get("message")
            if isinstance(message, str) and message.strip():
                messages.append(message.strip()[:500])
            for child in node.values():
                visit(child)
        elif isinstance(node, list):
            for child in node:
                visit(child)

    visit(value)
    return tuple(dict.fromkeys(messages))


def _validate_client_token(value: str) -> str:
    if not 1 <= len(value) <= 64 or any(ord(character) < 33 or ord(character) > 126 for character in value):
        raise ValueError("MediaKit client_token must contain 1-64 visible ASCII characters")
    return value


def _file_sha256(path: str) -> str:
    digest = hashlib.sha256()
    try:
        with open(path, "rb") as source_file:  # noqa: PTH123 - execution-only absolute media path
            while chunk := source_file.read(1024 * 1024):
                digest.update(chunk)
    except OSError as exc:
        raise MediaKitCommandError("MediaKit source content could not be hashed") from exc
    return digest.hexdigest()


def _flag_arguments(name: str, value: Any) -> tuple[str, ...]:
    flag = f"--{name.replace('_', '-')}"
    if isinstance(value, bool):
        return (f"{flag}={'true' if value else 'false'}",)
    if isinstance(value, (dict, list)):
        return (flag, json.dumps(value, ensure_ascii=False, separators=(",", ":")))
    if isinstance(value, (str, int, float)) and not isinstance(value, bool):
        return (flag, str(value))
    raise ValueError(f"MediaKit argument {name!r} has an unsupported value type")


class MediaKitCapabilityRouter:
    def __init__(
        self,
        *,
        cli_path: str = "mediakit-cli",
        runner: CommandRunner = _default_runner,
        discovery_timeout_seconds: float = 30,
    ) -> None:
        if not cli_path.strip():
            raise ValueError("MediaKit CLI path cannot be empty")
        if discovery_timeout_seconds <= 0:
            raise ValueError("MediaKit discovery timeout must be positive")
        self._cli_path = cli_path
        self._runner = runner
        self._discovery_timeout_seconds = discovery_timeout_seconds
        self._cli_version: str | None = None
        self._capabilities: dict[tuple[str, str], MediaKitCapability] = {}

    async def discover_cli_version(self) -> str:
        if self._cli_version is not None:
            return self._cli_version
        result = await self._runner(
            (self._cli_path, "version"),
            self._discovery_timeout_seconds,
        )
        if result.returncode != 0:
            raise MediaKitCommandError("MediaKit version discovery failed")
        match = _VERSION_LINE.search(result.stdout.strip())
        if match is None:
            raise MediaKitCommandError("MediaKit version discovery returned an invalid result")
        self._cli_version = match.group(1)
        return self._cli_version

    async def discover_capability(self, domain: str, tool: str) -> MediaKitCapability:
        domain = _require_command_token(domain, name="domain")
        tool = _require_command_token(tool, name="tool")
        cache_key = (domain, tool)
        cached = self._capabilities.get(cache_key)
        if cached is not None:
            return cached

        cli_version = await self.discover_cli_version()
        result = await self._runner(
            (self._cli_path, domain, tool, "--schema"),
            self._discovery_timeout_seconds,
        )
        payload = _json_payload(result, operation="schema discovery")
        notices = _notice_messages(payload.get("_notice"))
        schema_payload = {key: value for key, value in payload.items() if key != "_notice"}
        input_schema = schema_payload.get("input_schema")
        output_schema = schema_payload.get("output_schema")
        if not isinstance(input_schema, dict) or not isinstance(output_schema, dict):
            raise MediaKitCommandError("MediaKit schema discovery returned an invalid contract")
        try:
            Draft202012Validator.check_schema(input_schema)
            Draft202012Validator.check_schema(output_schema)
        except Exception as exc:
            raise MediaKitCommandError("MediaKit schema discovery returned an invalid JSON Schema") from exc

        name = schema_payload.get("name")
        description = schema_payload.get("description")
        capability = MediaKitCapability(
            domain=domain,
            tool=tool,
            name=name.strip() if isinstance(name, str) and name.strip() else tool,
            description=(description.strip() if isinstance(description, str) and description.strip() else ""),
            cli_version=cli_version,
            schema_sha256=_canonical_sha256(schema_payload),
            input_schema=input_schema,
            output_schema=output_schema,
            notices=notices,
        )
        self._capabilities[cache_key] = capability
        return capability

    async def prepare_video_call(
        self,
        *,
        domain: str,
        tool: str,
        source: EphemeralMediaSource,
        mode: ExecutionMode = "auto",
        arguments: Mapping[str, Any] | None = None,
        client_token: str | None = None,
    ) -> PreparedMediaKitCall:
        if mode not in {"auto", "local", "cloud"}:
            raise ValueError("unsupported MediaKit execution mode")
        if source.expires_at is not None and source.expires_at <= datetime.now(UTC):
            raise ValueError("resolved media source has expired")
        capability = await self.discover_capability(domain, tool)
        properties = capability.input_schema.get("properties")
        if not isinstance(properties, dict) or "video_url" not in properties:
            raise MediaKitCommandError("MediaKit capability does not accept video_url")

        supplied = dict(arguments or {})
        reserved = {"video_url", "audio_url", "client_token"} & supplied.keys()
        if reserved:
            raise ValueError("MediaKit source and client_token must use their dedicated arguments")
        input_payload: dict[str, Any] = {"video_url": source.locator, **supplied}
        if client_token is not None:
            input_payload["client_token"] = _validate_client_token(client_token)
        errors = sorted(
            Draft202012Validator(capability.input_schema).iter_errors(input_payload),
            key=lambda error: list(error.absolute_path),
        )
        if errors:
            raise ValueError("MediaKit arguments do not match the discovered capability schema")

        command: list[str] = [self._cli_path]
        if mode != "auto":
            command.append(f"--{mode}")
        command.extend((capability.domain, capability.tool))
        command.extend(_flag_arguments("video_url", source.locator))
        for name, value in supplied.items():
            command.extend(_flag_arguments(name, value))
        if client_token is not None:
            command.extend(_flag_arguments("client_token", client_token))

        return PreparedMediaKitCall(
            capability=capability,
            source=source,
            mode=mode,
            command=tuple(command),
            input_sha256=_canonical_sha256(input_payload),
            client_token_sha256=(hashlib.sha256(client_token.encode("utf-8")).hexdigest() if client_token is not None else None),
        )

    async def execute_local(
        self,
        prepared: PreparedMediaKitCall,
        *,
        timeout_seconds: float = 300,
    ) -> MediaKitExecutionResult:
        """Execute one local-file call without persisting its locator or raw output."""
        if prepared.mode != "local":
            raise ValueError("local execution requires local mode")
        if prepared.source.transport != "local_file":
            raise ValueError("local execution requires a local file source")
        if timeout_seconds <= 0:
            raise ValueError("MediaKit execution timeout must be positive")
        if prepared.source.expires_at is not None and prepared.source.expires_at <= datetime.now(UTC):
            raise ValueError("resolved media source has expired")

        source_content_sha256 = await asyncio.to_thread(
            _file_sha256,
            prepared.source.locator,
        )
        result = await self._runner(prepared.command, timeout_seconds)
        raw_payload = _json_payload(result, operation="local execution")
        notices = _notice_messages(raw_payload.get("_notice"))
        payload = {key: value for key, value in raw_payload.items() if key != "_notice"}
        errors = sorted(
            Draft202012Validator(prepared.capability.output_schema).iter_errors(payload),
            key=lambda error: list(error.absolute_path),
        )
        if errors:
            raise MediaKitCommandError("MediaKit local execution returned an invalid result")

        completed_source_sha256 = await asyncio.to_thread(
            _file_sha256,
            prepared.source.locator,
        )
        if completed_source_sha256 != source_content_sha256:
            raise MediaKitCommandError("MediaKit source content changed during execution")
        return MediaKitExecutionResult(
            prepared=prepared,
            output=payload,
            output_sha256=_canonical_sha256(payload),
            source_content_sha256=source_content_sha256,
            executed_at=datetime.now(UTC),
            notices=notices,
        )

    async def submit_cloud(
        self,
        prepared: PreparedMediaKitCall,
        *,
        timeout_seconds: float = 180,
    ) -> MediaKitCloudSubmissionResult:
        """Submit once and return only the durable handle projection."""
        if prepared.mode != "cloud":
            raise ValueError("cloud submission requires cloud mode")
        if timeout_seconds <= 0:
            raise ValueError("MediaKit submission timeout must be positive")
        if prepared.source.expires_at is not None and prepared.source.expires_at <= datetime.now(UTC):
            raise ValueError("resolved media source has expired")

        result = await self._runner(prepared.command, timeout_seconds)
        raw_payload = _json_payload(result, operation="cloud submission")
        notices = _notice_messages(raw_payload.get("_notice"))
        payload = {key: value for key, value in raw_payload.items() if key != "_notice"}
        errors = sorted(
            Draft202012Validator(prepared.capability.output_schema).iter_errors(payload),
            key=lambda error: list(error.absolute_path),
        )
        if errors or payload.get("success") is False or payload.get("error"):
            raise MediaKitCommandError("MediaKit cloud submission returned an invalid result")
        remote_task_id = payload.get("task_id")
        if not isinstance(remote_task_id, str) or not remote_task_id.strip():
            raise MediaKitCommandError("MediaKit cloud submission did not return task_id")
        request_id = payload.get("request_id")
        request_id_sha256 = None
        if isinstance(request_id, str) and request_id.strip():
            request_id_sha256 = hashlib.sha256(request_id.strip().encode("utf-8")).hexdigest()
        return MediaKitCloudSubmissionResult(
            remote_task_id=remote_task_id,
            request_id_sha256=request_id_sha256,
            submitted_at=datetime.now(UTC),
            notices=notices,
        )

    async def query_cloud_task(
        self,
        remote_task_id: str,
        *,
        expected_schema_sha256: str,
        timeout_seconds: float = 60,
    ) -> MediaKitCloudQueryResult:
        """Query exactly once; the durable worker owns repetition and leases."""
        task_id = remote_task_id.strip()
        if not task_id or len(task_id) > 255:
            raise ValueError("MediaKit remote task id must contain 1-255 characters")
        if timeout_seconds <= 0:
            raise ValueError("MediaKit query timeout must be positive")
        query_capability = await self.discover_capability("shared", "query-task")
        if query_capability.schema_sha256 != expected_schema_sha256:
            raise MediaKitCommandError("MediaKit query-task schema changed")

        result = await self._runner(
            (self._cli_path, "shared", "query-task", "--task-id", task_id),
            timeout_seconds,
        )
        raw_payload = _json_payload(
            result,
            operation="cloud task query",
            allow_structured_failure=True,
        )
        notices = _notice_messages(raw_payload.get("_notice"))
        payload = {key: value for key, value in raw_payload.items() if key != "_notice"}
        errors = sorted(
            Draft202012Validator(query_capability.output_schema).iter_errors(payload),
            key=lambda error: list(error.absolute_path),
        )
        if errors:
            raise MediaKitCommandError("MediaKit cloud task query returned an invalid result")
        returned_task_id = payload.get("task_id")
        if not isinstance(returned_task_id, str) or returned_task_id.strip() != task_id:
            raise MediaKitCommandError("MediaKit cloud task identity mismatch")
        provider_status = payload.get("status")
        if not isinstance(provider_status, str) or not provider_status.strip():
            raise MediaKitCommandError("MediaKit cloud task query omitted status")
        return MediaKitCloudQueryResult(
            remote_task_id=task_id,
            provider_status=provider_status,
            provider_output=payload,
            provider_output_sha256=_canonical_sha256(payload),
            query_schema_sha256=query_capability.schema_sha256,
            notices=notices,
        )


__all__ = ["MediaKitCapabilityRouter", "MediaKitCommandError"]
