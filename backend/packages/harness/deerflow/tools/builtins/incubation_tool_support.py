from __future__ import annotations

import logging
import os
from typing import Any

from langchain_core.runnables import RunnableConfig

from deerflow.config.runtime_paths import runtime_home
from deerflow.content_intelligence.analyzer import _invoke_structured
from deerflow.content_intelligence.lexical_evidence import CedictLexicalEvidenceProvider
from deerflow.incubation import ArtifactEnvelope
from deerflow.models import create_chat_model
from deerflow.tools.types import Runtime

logger = logging.getLogger(__name__)


def create_content_intelligence_model(config: RunnableConfig):
    from deerflow.config.app_config import get_app_config

    app_config = get_app_config()
    runtime_options: dict[str, Any] = {}
    for section_name in ("configurable", "context"):
        section = (config or {}).get(section_name) or {}
        if isinstance(section, dict):
            runtime_options.update(section)

    model_name = runtime_options.get("model_name")
    if model_name is None or app_config.get_model_config(model_name) is None:
        model_name = app_config.models[0].name if app_config.models else None
    if model_name is None:
        raise ValueError("No chat models are configured for content intelligence analysis.")
    return create_chat_model(
        name=model_name,
        thinking_enabled=False,
        app_config=app_config,
        attach_tracing=False,
    )


def create_lexical_evidence_provider() -> CedictLexicalEvidenceProvider | None:
    configured_path = os.getenv("CONTENT_INTELLIGENCE_CEDICT_INDEX", "").strip()
    index_path = configured_path or str(runtime_home() / "lexicons" / "cc-cedict.sqlite3")
    if not configured_path and not os.path.isfile(index_path):
        return None
    try:
        return CedictLexicalEvidenceProvider(index_path)
    except (OSError, ValueError, KeyError) as exc:
        logger.warning(
            "Configured lexical evidence index was unavailable; preserving the model-only path: %s",
            type(exc).__name__,
        )
        return None


def get_incubation_repository():
    from deerflow.persistence.engine import get_session_factory
    from deerflow.persistence.incubation_ledger import IncubationLedgerRepository

    session_factory = get_session_factory()
    if session_factory is None:
        return None
    return IncubationLedgerRepository(session_factory)


def runtime_context_text(runtime: Runtime, name: str) -> str | None:
    context = runtime.context or {}
    if not isinstance(context, dict):
        return None
    value = context.get(name)
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


def runtime_context_bool(runtime: Runtime, name: str, *, default: bool) -> bool:
    context = runtime.context or {}
    if not isinstance(context, dict):
        return default
    value = context.get(name)
    return value if isinstance(value, bool) else default


def artifact_receipt(artifact: ArtifactEnvelope) -> dict[str, str]:
    return {
        "artifact_type": artifact.artifact_type,
        "artifact_id": artifact.artifact_id,
        "content_sha256": artifact.content_sha256,
    }


def structured_model_runner(model: Any, config: RunnableConfig):
    async def invoke(schema, messages):
        try:
            return await _invoke_structured(
                model,
                schema,
                tuple(messages),
                runnable_config=config,
                include_raw=True,
                container_fields=set(getattr(schema, "model_fields", {})),
            )
        except ValueError as exc:
            raise ValueError("structured model output could not be parsed") from exc

    return invoke


__all__ = [
    "artifact_receipt",
    "create_content_intelligence_model",
    "create_lexical_evidence_provider",
    "get_incubation_repository",
    "runtime_context_bool",
    "runtime_context_text",
    "structured_model_runner",
]
