from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass, replace
from functools import lru_cache
from pathlib import Path
from typing import Any

from .contracts import CapabilityEntry
from .domains import DOMAIN_DEFINITIONS

_SNAPSHOT_PATH = Path(__file__).with_name("catalog_snapshot.json")
_EXPECTED_SOURCE_ROWS = 119
_MAX_DOMAIN_CHILDREN = 32
_MAX_TOOL_LIST_BYTES = 24 * 1024
_MAX_CHILD_DESCRIPTION_BYTES = 800
_MAX_SCHEMA_BYTES = 4 * 1024
_VIDEO_SEARCH_URL = "https://open.douyin.com/dy_open_api/v1/search/video/"
_VIDEO_SEARCH_SCOPE = "aweme.dy.video_search"
_VIDEO_SEARCH_V2_SCOPE = "aweme.dy.video_search_v2"

_VIDEO_SEARCH_INPUT_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "additionalProperties": False,
    "required": ["query"],
    "properties": {
        "query": {"type": "string", "minLength": 1, "maxLength": 200},
        "purpose": {
            "type": "string",
            "enum": ["topic_research", "benchmark_discovery"],
            "default": "topic_research",
        },
        "max_results": {"type": "integer", "minimum": 1, "maximum": 20, "default": 5},
        "cursor": {"type": "integer", "minimum": 0, "default": 0},
        "publish_time": {"type": "integer", "enum": [0, 1, 7, 180], "default": 0},
        "sort_type": {"type": "integer", "enum": [0, 1, 2], "default": 0},
        "search_id": {"type": "string", "minLength": 1, "maxLength": 200},
        "open_id": {"type": "string", "minLength": 1, "maxLength": 255},
    },
}

_VIDEO_RESULT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["title", "url", "content", "source_type", "item_id"],
    "properties": {
        "title": {"type": "string", "maxLength": 500},
        "url": {"type": "string", "maxLength": 1000},
        "content": {"type": "string", "maxLength": 4000},
        "source_type": {"const": "douyin_video"},
        "item_id": {"type": "string", "maxLength": 80},
        "nickname": {"type": "string", "maxLength": 200},
        "create_time": {"type": "integer", "minimum": 0},
        "digg_count": {"type": "integer", "minimum": 0},
    },
}

_VIDEO_SEARCH_OUTPUT_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "oneOf": [
        {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "query",
                "provider",
                "evidence_role",
                "total_results",
                "cursor",
                "has_more",
                "results",
            ],
            "properties": {
                "query": {"type": "string", "maxLength": 200},
                "provider": {"const": "douyin_open_platform"},
                "evidence_role": {"enum": ["topic_evidence", "benchmark_account_candidate"]},
                "total_results": {"type": "integer", "minimum": 0, "maximum": 20},
                "cursor": {"type": "integer", "minimum": 0},
                "has_more": {"type": "boolean"},
                "search_id": {"type": "string", "maxLength": 200},
                "results": {"type": "array", "maxItems": 20, "items": _VIDEO_RESULT_SCHEMA},
            },
        },
        {
            "type": "object",
            "additionalProperties": False,
            "required": ["error", "query"],
            "properties": {
                "error": {"type": "string", "maxLength": 300},
                "message": {"type": "string", "maxLength": 300},
                "log_id": {"type": "string", "maxLength": 300},
                "query": {"type": "string", "maxLength": 200},
            },
        },
    ],
}

_EXPERIENCE_SEARCH_INPUT_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "additionalProperties": False,
    "required": ["query"],
    "properties": {
        "query": {"type": "string", "minLength": 1, "maxLength": 200},
        "max_results": {"type": "integer", "minimum": 1, "maximum": 10, "default": 5},
        "cursor": {"type": "integer", "minimum": 0, "default": 0},
        "content_type": {"type": "integer", "enum": [1, 2]},
        "sort_type": {"type": "integer", "enum": [0, 1, 2], "default": 0},
        "search_id": {"type": "string", "minLength": 1, "maxLength": 200},
    },
}

_EXPERIENCE_RESULT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["title", "source_type", "item_id"],
    "properties": {
        "title": {"type": "string", "maxLength": 500},
        "source_type": {"const": "douyin_experience"},
        "item_id": {"type": "string", "maxLength": 80},
        "content_type": {"type": "integer", "enum": [1, 2]},
        "duration": {"type": "integer", "minimum": 0},
        "nickname": {"type": "string", "maxLength": 200},
    },
}

_EXPERIENCE_SEARCH_OUTPUT_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "oneOf": [
        {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "query",
                "provider",
                "evidence_role",
                "total_results",
                "cursor",
                "has_more",
                "results",
            ],
            "properties": {
                "query": {"type": "string", "maxLength": 200},
                "provider": {"const": "douyin_open_platform"},
                "evidence_role": {"const": "topic_evidence"},
                "total_results": {"type": "integer", "minimum": 0, "maximum": 10},
                "cursor": {"type": "integer", "minimum": 0},
                "has_more": {"type": "boolean"},
                "search_id": {"type": "string", "maxLength": 200},
                "results": {
                    "type": "array",
                    "maxItems": 10,
                    "items": _EXPERIENCE_RESULT_SCHEMA,
                },
            },
        },
        {
            "type": "object",
            "additionalProperties": False,
            "required": ["error", "query"],
            "properties": {
                "error": {"type": "string", "maxLength": 300},
                "message": {"type": "string", "maxLength": 300},
                "log_id": {"type": "string", "maxLength": 300},
                "query": {"type": "string", "maxLength": 200},
            },
        },
    ],
}


def _contract_overrides(entry: CapabilityEntry) -> CapabilityEntry:
    if entry.name_zh == "抖音视频搜索":
        return replace(
            entry,
            child_name="video_search",
            handler_key="search.video_search",
            http_url=_VIDEO_SEARCH_URL,
            scope=_VIDEO_SEARCH_SCOPE,
            required_scope_any_of=(_VIDEO_SEARCH_SCOPE, _VIDEO_SEARCH_V2_SCOPE),
            auth_mode="client_token",
            risk_level="read",
            input_schema=_VIDEO_SEARCH_INPUT_SCHEMA,
            output_schema=_VIDEO_SEARCH_OUTPUT_SCHEMA,
            review_status="adopted",
        )
    if entry.name_zh == "抖音图文搜索":
        return replace(
            entry,
            child_name="experience_search",
            handler_key="search.experience_search",
            required_scopes=("aweme.experience.search",),
            auth_mode="client_token",
            risk_level="read",
            input_schema=_EXPERIENCE_SEARCH_INPUT_SCHEMA,
            output_schema=_EXPERIENCE_SEARCH_OUTPUT_SCHEMA,
            review_status="adopted",
        )
    return entry


@dataclass(frozen=True)
class OfficialCatalog:
    source_url: str
    captured_at: str
    source_sha256: str
    source_row_count: int
    entries_sha256: str
    catalog_version: str
    entries: tuple[CapabilityEntry, ...]

    @property
    def section_counts(self) -> dict[str, int]:
        return dict(Counter(entry.section for entry in self.entries))

    def entries_for_domain(self, domain_id: str) -> tuple[CapabilityEntry, ...]:
        return tuple(entry for entry in self.entries if entry.domain == domain_id)

    def list_domain_tools(self) -> list[dict[str, str]]:
        tools = [
            {
                "name": definition.tool_name,
                "domain": definition.domain_id,
                "description": definition.description,
                "includes": definition.includes,
                "excludes": definition.excludes,
            }
            for definition in DOMAIN_DEFINITIONS.values()
        ]
        encoded = json.dumps(tools, ensure_ascii=False, separators=(",", ":")).encode()
        if len(encoded) > _MAX_TOOL_LIST_BYTES:
            raise ValueError("Douyin domain tool list exceeds its byte budget")
        return tools


def _optional_text(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _parse_entry(raw: dict[str, Any]) -> CapabilityEntry:
    entry = CapabilityEntry(
        capability_id=str(raw["capability_id"]),
        section=str(raw["section"]),
        domain=str(raw["domain"]),
        name_zh=str(raw["name_zh"]),
        description_zh=str(raw["description_zh"]),
        documentation_url=str(raw["documentation_url"]),
        interaction_direction=raw["interaction_direction"],
        documentation_status=str(raw["documentation_status"]),
        review_status=raw["review_status"],
        http_method=_optional_text(raw.get("http_method")),
        http_url=_optional_text(raw.get("http_url")),
        scope=_optional_text(raw.get("scope")),
        permission_requirement_zh=_optional_text(raw.get("permission_requirement_zh")),
    )
    return _contract_overrides(entry)


def _validate_catalog(entries: tuple[CapabilityEntry, ...], source_row_count: int) -> None:
    if source_row_count != _EXPECTED_SOURCE_ROWS or len(entries) != _EXPECTED_SOURCE_ROWS:
        raise ValueError("Douyin catalog snapshot row count drifted")
    if len({entry.capability_id for entry in entries}) != len(entries):
        raise ValueError("Douyin catalog contains duplicate capability IDs")
    if len({entry.documentation_url for entry in entries}) != len(entries):
        raise ValueError("Douyin catalog contains duplicate documentation URLs")
    if any(entry.domain not in DOMAIN_DEFINITIONS for entry in entries):
        raise ValueError("Douyin catalog contains an unknown domain")
    for domain_id in DOMAIN_DEFINITIONS:
        if sum(entry.domain == domain_id for entry in entries) > _MAX_DOMAIN_CHILDREN:
            raise ValueError(f"Douyin domain {domain_id} exceeds its child budget")
    for entry in entries:
        if len(entry.description_zh.encode()) > _MAX_CHILD_DESCRIPTION_BYTES:
            raise ValueError(f"Douyin capability {entry.capability_id} description is too large")
        for schema in (entry.input_schema, entry.output_schema):
            if schema is not None and len(json.dumps(schema, ensure_ascii=False, separators=(",", ":")).encode()) > _MAX_SCHEMA_BYTES:
                raise ValueError(f"Douyin capability {entry.capability_id} schema is too large")


@lru_cache(maxsize=1)
def load_official_catalog() -> OfficialCatalog:
    payload = json.loads(_SNAPSHOT_PATH.read_text(encoding="utf-8"))
    raw_entries = payload.get("entries")
    if not isinstance(raw_entries, list):
        raise ValueError("Douyin catalog snapshot has no entries")
    actual_entries_sha256 = hashlib.sha256(
        json.dumps(
            raw_entries,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    if actual_entries_sha256 != payload.get("entries_sha256"):
        raise ValueError("Douyin catalog snapshot content hash drifted")
    entries = tuple(_parse_entry(raw) for raw in raw_entries if isinstance(raw, dict))
    source_row_count = int(payload.get("source_row_count", 0))
    _validate_catalog(entries, source_row_count)
    contract_payload = [
        {
            "entry": entry.__dict__,
            "domain": DOMAIN_DEFINITIONS[entry.domain].__dict__,
        }
        for entry in entries
    ]
    catalog_version = hashlib.sha256(
        json.dumps(
            contract_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    return OfficialCatalog(
        source_url=str(payload["source_url"]),
        captured_at=str(payload["captured_at"]),
        source_sha256=str(payload["source_sha256"]),
        source_row_count=source_row_count,
        entries_sha256=str(payload["entries_sha256"]),
        catalog_version=catalog_version,
        entries=entries,
    )
