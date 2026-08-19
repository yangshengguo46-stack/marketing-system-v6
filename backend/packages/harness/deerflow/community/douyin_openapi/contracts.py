from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

InteractionDirection = Literal[
    "auth",
    "outbound",
    "inbound_webhook",
    "provider_implemented",
    "local_utility",
]
ReviewStatus = Literal["discovered", "traced", "reviewed", "adopted", "rejected"]
RiskLevel = Literal["read", "write", "irreversible", "chargeable", "unknown"]


@dataclass(frozen=True)
class CapabilityContext:
    """Request-scoped capability state without credential values."""

    granted_scopes: frozenset[str] = field(default_factory=frozenset)
    configured_auth_modes: frozenset[str] = field(default_factory=frozenset)
    approved_capabilities: frozenset[str] = field(default_factory=frozenset)
    capability_generation: str = "default"


@dataclass(frozen=True)
class CapabilityEntry:
    capability_id: str
    section: str
    domain: str
    name_zh: str
    description_zh: str
    documentation_url: str
    interaction_direction: InteractionDirection
    documentation_status: str
    review_status: ReviewStatus
    http_method: str | None = None
    http_url: str | None = None
    scope: str | None = None
    permission_requirement_zh: str | None = None
    child_name: str | None = None
    handler_key: str | None = None
    required_scopes: tuple[str, ...] = ()
    required_scope_any_of: tuple[str, ...] = ()
    auth_mode: str | None = None
    risk_level: RiskLevel = "unknown"
    input_schema: dict[str, Any] | None = None
    output_schema: dict[str, Any] | None = None

    @property
    def is_child_contract(self) -> bool:
        return bool(self.child_name and self.handler_key and self.input_schema is not None and self.output_schema is not None)
