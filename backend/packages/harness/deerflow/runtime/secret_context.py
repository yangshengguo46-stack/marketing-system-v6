"""Request-scoped secret carrier in the run context (issue #3861).

Callers pass per-request secrets out-of-band in ``config.context.secrets`` — a
mapping of name -> value. The value never enters the prompt, tool arguments, or
the executed command string; it is injected as an environment variable into a
skill's sandbox subprocess only when an activated skill declares it via the
``required-secrets`` frontmatter field.

This module centralises the reserved key name and safe extraction so the carrier
contract lives in one place, consumed by the skill-activation middleware (to
build the per-turn injection set) and the tracing redactor (to strip it from
trace payloads).
"""

from __future__ import annotations

from typing import Any

# Reserved sub-key of the run context that holds request-scoped secrets supplied
# by the caller. Source of truth for what a skill *may* receive.
SECRETS_CONTEXT_KEY = "secrets"

# Reserved sub-key holding the secrets resolved for the currently activated skill
# (binding point A). Written by the skill-activation middleware, read by the bash
# tool. Both reserved keys are stripped from trace payloads (see tracing redactor).
ACTIVE_SECRETS_CONTEXT_KEY = "__active_skill_secrets"

# Reserved sub-key holding the active skill tool-policy decision for one model
# step. The decision includes a middleware-instance owner token that prevents a
# caller from forging an allow-all decision in its mergeable run context, so the
# entire value must be stripped from every observable serialization surface.
SKILL_TOOL_POLICY_DECISION_CONTEXT_KEY = "__skill_tool_policy_decision"

# Owner-token-bound counter used by the read-only ContextManifest middleware.
# It has no user data, but remains internal run-control state and must not be
# accepted as observable caller metadata or echoed from config.
CONTEXT_MANIFEST_COUNTER_CONTEXT_KEY = "__context_manifest_counter"

# Owner-token-bound metadata for the user-profile projection injected into one
# physical Lead model request. The carrier contains only version/hash/counts,
# never profile text, but remains authenticated internal state so callers
# cannot forge what ContextManifest reports.
USER_PROFILE_PROJECTION_CONTEXT_KEY = "__user_profile_projection"

# Owner-token-bound run counter for tool-call budgets declared by an active
# Skill. It contains only tool names and counts, but is internal execution
# state: callers must not forge, persist, or observe it.
SKILL_TOOL_CALL_BUDGET_CONTEXT_KEY = "__skill_tool_call_budget"

# Opaque carrier for a run's shared Skill tool budget. The value contains only
# a random registry token, run identity, and Skill paths; counts and locks stay
# process-local. It is copied to native subagents but never serialized.
SKILL_TOOL_CALL_BUDGET_SCOPE_CONTEXT_KEY = "__skill_tool_call_budget_scope"

LEGACY_AUTH_TOKEN_METADATA_KEY = "auth_token"


class LegacyRunMetadataSecretError(ValueError):
    """Raised when a run puts a request credential in persisted metadata."""


def validate_run_metadata_secrets(metadata: Any) -> None:
    """Reject the legacy credential field at run admission."""
    if isinstance(metadata, dict) and LEGACY_AUTH_TOKEN_METADATA_KEY in metadata:
        raise LegacyRunMetadataSecretError("Run metadata key 'auth_token' is not allowed; pass request-scoped credentials via config.context.secrets instead.")


def redact_metadata_secrets(metadata: Any) -> Any:
    """Return API-safe metadata without mutating historical storage objects."""
    if not isinstance(metadata, dict):
        return metadata
    return {key: value for key, value in metadata.items() if key != LEGACY_AUTH_TOKEN_METADATA_KEY}


def _string_pairs(raw: Any) -> dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    return {key: value for key, value in raw.items() if isinstance(key, str) and isinstance(value, str)}


def extract_request_secrets(context: Any) -> dict[str, str]:
    """Return the caller-supplied request-scoped secrets mapping, or ``{}``.

    Only string-keyed, string-valued entries are kept; anything else is ignored
    so a malformed carrier can never crash secret resolution or injection.
    """
    if not isinstance(context, dict):
        return {}
    return _string_pairs(context.get(SECRETS_CONTEXT_KEY))


def read_active_secrets(context: Any) -> dict[str, str]:
    """Return the secrets resolved for the active skill (the per-run injection
    set), or ``{}``. Read by the bash tool to build the subprocess env."""
    if not isinstance(context, dict):
        return {}
    return _string_pairs(context.get(ACTIVE_SECRETS_CONTEXT_KEY))


def write_slash_skill_source_path(context: Any, path: str, *, owner_token: str) -> None:
    """Persist an authenticated slash-activated skill path in a run context.

    The source contains a path reference plus a middleware-chain-local token.
    Consumers must authenticate the token and resolve the path against the live
    skill registry before trusting any skill metadata.
    """
    if isinstance(context, dict) and isinstance(path, str) and path and isinstance(owner_token, str) and owner_token:
        context[_SLASH_SECRET_SOURCE_KEY] = {"path": path, "owner_token": owner_token}


def read_slash_skill_source_path(context: Any, *, owner_token: str) -> str | None:
    """Return the authenticated slash-activated skill path, if well formed."""
    if not isinstance(context, dict):
        return None
    source = context.get(_SLASH_SECRET_SOURCE_KEY)
    if not isinstance(source, dict):
        return None
    path = source.get("path")
    source_owner_token = source.get("owner_token")
    if not isinstance(owner_token, str) or not owner_token or source_owner_token != owner_token:
        return None
    return path if isinstance(path, str) and path else None


def write_agent_skill_source_path(context: Any, path: str, *, owner_token: str) -> None:
    """Persist the latest Agent-selected Skill path for this run.

    This source is separate from slash activation so an autonomous tool call
    cannot overwrite a Skill the user explicitly selected. The owner token is
    local to the assembled middleware chain and never enters model context.
    """
    if isinstance(context, dict) and isinstance(path, str) and path and isinstance(owner_token, str) and owner_token:
        context[_AGENT_SKILL_ACTIVATION_SOURCE_KEY] = {"path": path, "owner_token": owner_token}


def read_agent_skill_source_path(context: Any, *, owner_token: str) -> str | None:
    """Return the authenticated Agent-selected Skill path, if well formed."""
    if not isinstance(context, dict):
        return None
    source = context.get(_AGENT_SKILL_ACTIVATION_SOURCE_KEY)
    if not isinstance(source, dict):
        return None
    path = source.get("path")
    source_owner_token = source.get("owner_token")
    if not isinstance(owner_token, str) or not owner_token or source_owner_token != owner_token:
        return None
    return path if isinstance(path, str) and path else None


def clear_user_profile_projection(context: Any) -> None:
    """Remove a prior per-call profile projection from a mutable run context."""
    if isinstance(context, dict):
        context.pop(USER_PROFILE_PROJECTION_CONTEXT_KEY, None)


def write_user_profile_projection(
    context: Any,
    *,
    owner_token: str,
    version: int,
    content_sha256: str,
    item_count: int,
    projected_item_count: int,
    omitted_item_count: int,
) -> None:
    """Write authenticated, content-free profile accounting for one call."""
    if not isinstance(context, dict) or not isinstance(owner_token, str) or not owner_token:
        return
    if type(version) is not int or version < 1:
        return
    if not isinstance(content_sha256, str) or len(content_sha256) != 64:
        return
    if any(character not in "0123456789abcdef" for character in content_sha256):
        return
    counts = (item_count, projected_item_count, omitted_item_count)
    if any(type(value) is not int or value < 0 for value in counts):
        return
    if projected_item_count + omitted_item_count != item_count:
        return
    context[USER_PROFILE_PROJECTION_CONTEXT_KEY] = {
        "owner_token": owner_token,
        "version": version,
        "content_sha256": content_sha256,
        "item_count": item_count,
        "projected_item_count": projected_item_count,
        "omitted_item_count": omitted_item_count,
    }


def read_user_profile_projection(context: Any, *, owner_token: str) -> dict[str, Any] | None:
    """Return authenticated, content-free profile accounting, if valid."""
    if not isinstance(context, dict) or not isinstance(owner_token, str) or not owner_token:
        return None
    projection = context.get(USER_PROFILE_PROJECTION_CONTEXT_KEY)
    if not isinstance(projection, dict) or projection.get("owner_token") != owner_token:
        return None
    version = projection.get("version")
    content_sha256 = projection.get("content_sha256")
    item_count = projection.get("item_count")
    projected_item_count = projection.get("projected_item_count")
    omitted_item_count = projection.get("omitted_item_count")
    if type(version) is not int or version < 1:
        return None
    if not isinstance(content_sha256, str) or len(content_sha256) != 64:
        return None
    if any(character not in "0123456789abcdef" for character in content_sha256):
        return None
    counts = (item_count, projected_item_count, omitted_item_count)
    if any(type(value) is not int or value < 0 for value in counts):
        return None
    if projected_item_count + omitted_item_count != item_count:
        return None
    return {
        "version": version,
        "content_sha256": content_sha256,
        "item_count": item_count,
        "projected_item_count": projected_item_count,
        "omitted_item_count": omitted_item_count,
    }


# Private run-context keys the skill-activation middleware uses to carry secret
# bindings across a run. Only ``secrets`` / ``__active_skill_secrets`` hold
# secret values; the slash source holds a middleware-chain owner token, while
# the audit keys hold names only. All are listed so the redaction allowlist
# remains a complete guard.
_SLASH_SECRET_SOURCE_KEY = "__slash_skill_secret_source"
_AGENT_SKILL_ACTIVATION_SOURCE_KEY = "__agent_skill_activation_source"
_SECRETS_BINDING_AUDIT_KEY = "__skill_secrets_binding_audit"

# Identity of the latest slash activation that has already fired in this run, so
# the reminder injection, skill disk read, and ``activate`` audit event happen
# once per user slash command rather than on every model call of the tool loop.
# The reminder is injected into the per-call model request only and never written
# back to graph state, so a scan of ``request.messages`` cannot detect a prior
# activation on the 2nd..Nth model call — the run context is the only signal that
# survives (mirroring ``_SLASH_SECRET_SOURCE_KEY``). Holds a message id / content
# digest, never a secret value; listed below to keep the redaction guard complete.
_SLASH_SKILL_ACTIVATION_RUN_KEY = "__slash_skill_activation_run"

# Run-context keys whose values are request-scoped secrets and must be stripped
# before a context mapping is serialized anywhere observable (traces, logs).
REDACTED_CONTEXT_KEYS = frozenset(
    {
        SECRETS_CONTEXT_KEY,
        ACTIVE_SECRETS_CONTEXT_KEY,
        _SLASH_SECRET_SOURCE_KEY,
        _AGENT_SKILL_ACTIVATION_SOURCE_KEY,
        _SECRETS_BINDING_AUDIT_KEY,
        _SLASH_SKILL_ACTIVATION_RUN_KEY,
        SKILL_TOOL_POLICY_DECISION_CONTEXT_KEY,
        CONTEXT_MANIFEST_COUNTER_CONTEXT_KEY,
        USER_PROFILE_PROJECTION_CONTEXT_KEY,
        SKILL_TOOL_CALL_BUDGET_CONTEXT_KEY,
        SKILL_TOOL_CALL_BUDGET_SCOPE_CONTEXT_KEY,
    }
)


def redact_secret_context_keys(context: Any) -> Any:
    """Return a shallow copy of ``context`` with secret-bearing keys removed.

    Defensive helper for any code path that serializes the run context into an
    observable surface. DeerFlow's own trace-metadata builder never copies the
    context, so this is belt-and-suspenders for future call sites and custom
    tracer configurations.
    """
    if not isinstance(context, dict):
        return context
    return {key: value for key, value in context.items() if key not in REDACTED_CONTEXT_KEYS}


def redact_config_secrets(config: Any) -> Any:
    """Return a copy of a run config safe to persist or echo back to clients.

    The request config (``body.config``) would otherwise be stored verbatim on
    the run record (``runs.kwargs_json``) and echoed by the run API. Strip secret-bearing keys
    from its ``context`` and legacy credentials from its ``metadata`` so neither
    protected config surface is persisted or returned, while the live config
    that drives the run (built separately) keeps them. Ordinary metadata is
    preserved. Non-dict configs pass through unchanged.
    """
    if not isinstance(config, dict):
        return config

    redacted = dict(config)
    context = config.get("context")
    if isinstance(context, dict):
        redacted["context"] = redact_secret_context_keys(context)

    metadata = config.get("metadata")
    if isinstance(metadata, dict):
        redacted["metadata"] = redact_metadata_secrets(metadata)

    return redacted
