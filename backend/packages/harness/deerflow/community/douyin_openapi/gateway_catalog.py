from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from .catalog import load_official_catalog
from .contracts import CapabilityEntry
from .domains import DOMAIN_DEFINITIONS
from .public_evidence import PUBLIC_EVIDENCE_AUTH_MODE

PUBLIC_EVIDENCE_CHILD_NAMES = frozenset(
    {
        "search_videos",
        "get_video_detail",
        "get_video_comments",
        "get_sub_comments",
        "get_user_info",
        "get_user_posts",
        "resolve_share_url",
    }
)

_RECEIPT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "provider",
        "revision",
        "collection",
        "requested",
        "returned",
        "limitations",
    ],
    "properties": {
        "provider": {"type": "string", "maxLength": 200},
        "revision": {"type": "string", "maxLength": 200},
        "collection": {"const": "authenticated_public_web"},
        "requested": {"type": "integer", "minimum": 0, "maximum": 20},
        "returned": {"type": "integer", "minimum": 0, "maximum": 20},
        "limitations": {
            "type": "array",
            "maxItems": 8,
            "items": {"type": "string", "maxLength": 500},
        },
    },
}

_METRICS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "likes",
        "comments",
        "shares",
        "collections",
        "plays",
    ],
    "properties": {name: {"type": "integer", "minimum": 0} for name in ("likes", "comments", "shares", "collections", "plays")},
}

_AWEME_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "aweme_id",
        "title",
        "description",
        "created_at",
        "duration_ms",
        "aweme_type",
        "author",
        "metrics",
        "image_count",
        "is_ai_generated",
    ],
    "properties": {
        "aweme_id": {"type": "string", "maxLength": 64},
        "title": {"type": "string", "maxLength": 320},
        "description": {"type": "string", "maxLength": 800},
        "created_at": {"type": "string", "maxLength": 64},
        "duration_ms": {"type": "integer", "minimum": 0},
        "aweme_type": {"type": "string", "maxLength": 32},
        "author": {
            "type": "object",
            "additionalProperties": False,
            "required": ["nickname", "sec_uid"],
            "properties": {
                "nickname": {"type": "string", "maxLength": 120},
                "sec_uid": {"type": "string", "maxLength": 256},
            },
        },
        "metrics": _METRICS_SCHEMA,
        "image_count": {"type": "integer", "minimum": 0},
        "is_ai_generated": {"type": "boolean"},
    },
}

_SEARCH_INPUT: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["keyword"],
    "properties": {
        "keyword": {"type": "string", "minLength": 1, "maxLength": 200},
        "offset": {"type": "integer", "minimum": 0},
        "count": {"type": "integer", "minimum": 1, "maximum": 10},
        "search_channel": {"type": "string", "minLength": 1, "maxLength": 32},
        "sort_type": {"type": "integer", "enum": [0, 1, 2]},
        "publish_time": {"type": "integer", "enum": [0, 1, 7, 180]},
    },
}

_SEARCH_OUTPUT: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "success",
        "query",
        "cursor",
        "has_more",
        "results",
        "receipt",
        "error",
    ],
    "properties": {
        "success": {"type": "boolean"},
        "query": {"type": "string", "maxLength": 200},
        "cursor": {"type": "string", "maxLength": 80},
        "has_more": {"type": "boolean"},
        "results": {
            "type": "array",
            "maxItems": 10,
            "items": _AWEME_SCHEMA,
        },
        "receipt": _RECEIPT_SCHEMA,
        "error": {"type": "string", "maxLength": 300},
    },
}

_ID_INPUT: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["aweme_id"],
    "properties": {"aweme_id": {"type": "string", "minLength": 1, "maxLength": 64}},
}

_DETAIL_OUTPUT: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["success", "aweme_id", "video", "receipt", "error"],
    "properties": {
        "success": {"type": "boolean"},
        "aweme_id": {"type": "string", "maxLength": 64},
        "video": {
            "oneOf": [
                _AWEME_SCHEMA,
                {"type": "object", "maxProperties": 0},
            ]
        },
        "receipt": _RECEIPT_SCHEMA,
        "error": {"type": "string", "maxLength": 300},
    },
}

_COMMENT_INPUT: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["aweme_id"],
    "properties": {
        "aweme_id": {"type": "string", "minLength": 1, "maxLength": 64},
        "cursor": {"type": "integer", "minimum": 0},
        "count": {"type": "integer", "minimum": 1, "maximum": 20},
        "source_keyword": {"type": "string", "maxLength": 200},
    },
}

_SUB_COMMENT_INPUT: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["comment_id"],
    "properties": {
        "comment_id": {"type": "string", "minLength": 1, "maxLength": 80},
        "cursor": {"type": "integer", "minimum": 0},
        "count": {"type": "integer", "minimum": 1, "maximum": 20},
        "source_keyword": {"type": "string", "maxLength": 200},
    },
}

_COMMENTS_OUTPUT: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "success",
        "aweme_id",
        "comments",
        "pagination",
        "population_scope",
        "receipt",
        "error",
    ],
    "properties": {
        "success": {"type": "boolean"},
        "aweme_id": {"type": "string", "maxLength": 64},
        "comments": {
            "type": "array",
            "maxItems": 20,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "comment_id",
                    "parent_comment_id",
                    "text",
                    "created_at",
                    "likes",
                    "reply_count",
                    "region",
                    "has_images",
                    "audience_actor",
                ],
                "properties": {
                    "comment_id": {"type": "string", "maxLength": 80},
                    "parent_comment_id": {"type": "string", "maxLength": 80},
                    "text": {"type": "string", "maxLength": 800},
                    "created_at": {"type": "string", "maxLength": 64},
                    "likes": {"type": "integer", "minimum": 0},
                    "reply_count": {"type": "integer", "minimum": 0},
                    "region": {"type": "string", "maxLength": 80},
                    "has_images": {"type": "boolean"},
                    "audience_actor": {"type": "string", "maxLength": 64},
                },
            },
        },
        "pagination": {
            "type": "object",
            "additionalProperties": False,
            "required": ["cursor", "has_more", "total"],
            "properties": {
                "cursor": {"type": "string", "maxLength": 80},
                "has_more": {"type": "boolean"},
                "total": {"type": "integer", "minimum": 0},
            },
        },
        "population_scope": {"const": "visible_commenters"},
        "receipt": _RECEIPT_SCHEMA,
        "error": {"type": "string", "maxLength": 300},
    },
}

_USER_INPUT: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["sec_user_id"],
    "properties": {"sec_user_id": {"type": "string", "minLength": 1, "maxLength": 256}},
}

_USER_OUTPUT: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["success", "user", "receipt", "error"],
    "properties": {
        "success": {"type": "boolean"},
        "user": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "sec_uid": {"type": "string", "maxLength": 256},
                "nickname": {"type": "string", "maxLength": 120},
                "description": {"type": "string", "maxLength": 800},
                "region": {"type": "string", "maxLength": 80},
                "gender": {"type": "string", "maxLength": 32},
                "following": {"type": "integer", "minimum": 0},
                "fans": {"type": "integer", "minimum": 0},
                "total_interactions": {"type": "integer", "minimum": 0},
                "videos_count": {"type": "integer", "minimum": 0},
            },
        },
        "receipt": _RECEIPT_SCHEMA,
        "error": {"type": "string", "maxLength": 300},
    },
}

_POSTS_INPUT: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["sec_user_id"],
    "properties": {
        "sec_user_id": {"type": "string", "minLength": 1, "maxLength": 256},
        "max_cursor": {"type": "string", "maxLength": 80},
        "count": {"type": "integer", "minimum": 1, "maximum": 12},
    },
}

_POSTS_OUTPUT: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "success",
        "account_sec_uid",
        "posts",
        "pagination",
        "receipt",
        "error",
    ],
    "properties": {
        "success": {"type": "boolean"},
        "account_sec_uid": {"type": "string", "maxLength": 256},
        "posts": {"type": "array", "maxItems": 12, "items": _AWEME_SCHEMA},
        "pagination": {
            "type": "object",
            "additionalProperties": False,
            "required": ["max_cursor", "has_more"],
            "properties": {
                "max_cursor": {"type": "string", "maxLength": 80},
                "has_more": {"type": "boolean"},
            },
        },
        "receipt": _RECEIPT_SCHEMA,
        "error": {"type": "string", "maxLength": 300},
    },
}

_SHARE_INPUT: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["share_url"],
    "properties": {"share_url": {"type": "string", "minLength": 1, "maxLength": 1000}},
}


def _entry(
    *,
    name: str,
    title: str,
    description: str,
    input_schema: dict[str, Any],
    output_schema: dict[str, Any],
) -> CapabilityEntry:
    return CapabilityEntry(
        capability_id=f"douyin.public_evidence.{name}.v1",
        section="公开证据",
        domain="public_evidence",
        name_zh=title,
        description_zh=description,
        documentation_url=(f"https://github.com/pazwusimple-netizen/douyin-mcp#deerflow-child-{name}"),
        interaction_direction="outbound",
        documentation_status="local_reviewed_contract",
        review_status="adopted",
        child_name=name,
        handler_key=f"public_evidence.{name}",
        auth_mode=PUBLIC_EVIDENCE_AUTH_MODE,
        risk_level="read",
        input_schema=input_schema,
        output_schema=output_schema,
    )


_PUBLIC_ENTRIES = (
    _entry(
        name="search_videos",
        title="搜索公开视频",
        description="搜索公开抖音视频，返回有界候选证据，不返回原始页面、Cookie 或临时媒体地址。",
        input_schema=_SEARCH_INPUT,
        output_schema=_SEARCH_OUTPUT,
    ),
    _entry(
        name="get_video_detail",
        title="读取视频详情",
        description="读取一条公开视频的文本、作者与公开互动指标。",
        input_schema=_ID_INPUT,
        output_schema=_DETAIL_OUTPUT,
    ),
    _entry(
        name="get_video_comments",
        title="读取视频受众互动",
        description="读取一页可见评论并对互动者标识做不可逆假名化。",
        input_schema=_COMMENT_INPUT,
        output_schema=_COMMENTS_OUTPUT,
    ),
    _entry(
        name="get_sub_comments",
        title="读取评论回复",
        description="读取一条可见评论的回复并对互动者标识做不可逆假名化。",
        input_schema=_SUB_COMMENT_INPUT,
        output_schema=_COMMENTS_OUTPUT,
    ),
    _entry(
        name="get_user_info",
        title="读取公开创作者资料",
        description="读取公开创作者资料与账号规模，不返回头像和临时媒体地址。",
        input_schema=_USER_INPUT,
        output_schema=_USER_OUTPUT,
    ),
    _entry(
        name="get_user_posts",
        title="读取公开创作者作品",
        description="读取创作者有界作品列表及公开互动指标。",
        input_schema=_POSTS_INPUT,
        output_schema=_POSTS_OUTPUT,
    ),
    _entry(
        name="resolve_share_url",
        title="解析抖音分享链接",
        description="把用户提供的抖音分享链接解析为一条有界视频证据。",
        input_schema=_SHARE_INPUT,
        output_schema=_DETAIL_OUTPUT,
    ),
)


@dataclass(frozen=True)
class GatewayCatalog:
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
        return [
            {
                "name": definition.tool_name,
                "domain": definition.domain_id,
                "description": definition.description,
                "includes": definition.includes,
                "excludes": definition.excludes,
            }
            for definition in DOMAIN_DEFINITIONS.values()
        ]


@lru_cache(maxsize=1)
def load_gateway_catalog() -> GatewayCatalog:
    official = load_official_catalog()
    entries = official.entries + _PUBLIC_ENTRIES
    contract_payload = [entry.__dict__ for entry in entries]
    catalog_version = hashlib.sha256(
        json.dumps(
            contract_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    entries_sha256 = hashlib.sha256(
        json.dumps(
            contract_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return GatewayCatalog(
        source_url=official.source_url,
        captured_at=official.captured_at,
        source_sha256=official.source_sha256,
        source_row_count=official.source_row_count,
        entries_sha256=entries_sha256,
        catalog_version=catalog_version,
        entries=entries,
    )


__all__ = [
    "GatewayCatalog",
    "PUBLIC_EVIDENCE_CHILD_NAMES",
    "load_gateway_catalog",
]
