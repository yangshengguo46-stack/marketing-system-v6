from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from deerflow.incubation.media import EphemeralMediaSource

ExecutionMode = Literal["auto", "local", "cloud"]


@dataclass(frozen=True, slots=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


@dataclass(frozen=True, slots=True)
class MediaKitCapability:
    domain: str
    tool: str
    name: str
    description: str
    cli_version: str
    schema_sha256: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    notices: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True, repr=False)
class PreparedMediaKitCall:
    capability: MediaKitCapability
    source: EphemeralMediaSource
    mode: ExecutionMode
    command: tuple[str, ...] = field(repr=False)
    input_sha256: str
    client_token_sha256: str | None = None

    def __repr__(self) -> str:
        return f"PreparedMediaKitCall(domain={self.capability.domain!r}, tool={self.capability.tool!r}, mode={self.mode!r}, source_ref={self.source.source_ref!r}, input_sha256={self.input_sha256!r}, command='<redacted>')"


__all__ = [
    "CommandResult",
    "ExecutionMode",
    "MediaKitCapability",
    "PreparedMediaKitCall",
]
