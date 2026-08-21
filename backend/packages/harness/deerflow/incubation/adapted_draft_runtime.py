from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from pydantic import ValidationError

from deerflow.incubation.adapted_draft import (
    AdaptedDraftDraft,
    seal_adapted_draft,
    validate_adapted_draft_output,
    validate_adapted_draft_parents,
)
from deerflow.incubation.contracts import ArtifactEnvelope, LogicalAccountRef, ProjectRef

StructuredAdaptedDraftModel = Callable[
    [type[AdaptedDraftDraft], tuple[BaseMessage, ...]],
    Awaitable[Any],
]

ADAPTED_DRAFT_MODEL_INPUT_MAX_BYTES = 24_000
_BASE_TEXT_MAX_BYTES = 18_000
_RATIONALE_MAX_BYTES = 2_000
_NARRATIVE_HINT_MAX_BYTES = 1_200
_TRUNCATION_MARKER = "...[bounded source truncated]"

ADAPTED_DRAFT_SYSTEM_PROMPT = """<adapted_draft>
你只负责把一份已经封存的 BaseDraft 翻译成 FormatDecision 已选定的表现形式，并返回 AdaptedDraftDraft。

工作边界：
- 不得换题、改变中心观点、改变信息结论或重新解释 MessagePlan。
- 不得添加事实、证据、人物、案例、数字、历史细节、用户经历或因果；输入没有的内容保持没有。
- 每个 presentation unit 都必须引用 BaseDraft 中一个或多个连续逐字 source_excerpts。适配表达可以变化，但每个单元都必须显式保留来源锚点；禁止无来源单元。
- 单元按最终呈现顺序返回。口述、图文、纯素材、访谈、纪录观察、微短剧和情景剧共用这套单元结构。
- source_excerpts 只能逐字复制输入中可见的 BaseDraft 正文，不能引用截断标记。

形式边界：
- 图文和纯素材不要求 performer 或 dialogue，也不能被强行加入对白、演员调度或故事结构。
- 只有 micro_drama 和 situational_drama 才可填写高层 narrative_treatment 或使用 dialogue；它只能把基础稿已有关系变成场面表达，不能补造真实人物经历。
- visual_treatment 只说明同一句内容如何被看见，不能借画面增加新事实。

禁止事项：
- 不输出 TopicBrief、MessagePlan、evidence refs 或另一份选题方案。
- 不加入销售、商业回桥、平台、发布、投流、审批或运营安排。
- 不加入固定时长、镜头数、条数、频率、配额或拍摄日程。

只返回结构化合同。
</adapted_draft>"""


class AdaptedDraftModelError(RuntimeError):
    """The injected structured model did not produce a usable adaptation."""


def _clip_utf8(value: str, *, max_bytes: int) -> tuple[str, bool]:
    encoded = value.encode("utf-8")
    if len(encoded) <= max_bytes:
        return value, False
    marker = _TRUNCATION_MARKER.encode("utf-8")
    prefix = encoded[: max_bytes - len(marker)].decode("utf-8", errors="ignore")
    return f"{prefix}{_TRUNCATION_MARKER}", True


def _optional_clipped_text(
    payload: dict[str, object],
    field: str,
    *,
    max_bytes: int,
) -> str | None:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        return None
    return _clip_utf8(value, max_bytes=max_bytes)[0]


def _render_model_input(
    *,
    base_draft_artifact: ArtifactEnvelope,
    format_decision_artifact: ArtifactEnvelope,
) -> str:
    format_payload = format_decision_artifact.payload
    base_payload = base_draft_artifact.payload
    base_text = base_payload["text"]
    if not isinstance(base_text, str):
        raise ValueError("base draft text must be a string")
    bounded_text, truncated = _clip_utf8(base_text, max_bytes=_BASE_TEXT_MAX_BYTES)
    payload = {
        "base_draft": {
            "artifact_id": base_draft_artifact.artifact_id,
            "content_sha256": base_draft_artifact.content_sha256,
            "draft_id": base_payload["draft_id"],
            "body_sha256": format_payload["base_draft_binding"]["body_sha256"],
            "text": bounded_text,
            "text_truncated": truncated,
        },
        "format_decision": {
            "artifact_id": format_decision_artifact.artifact_id,
            "content_sha256": format_decision_artifact.content_sha256,
            "selected_format": format_payload["selected_format"],
            "selection_rationale": _optional_clipped_text(
                format_payload,
                "selection_rationale",
                max_bytes=_RATIONALE_MAX_BYTES,
            ),
            "narrative_method_hint": _optional_clipped_text(
                format_payload,
                "narrative_method_hint",
                max_bytes=_NARRATIVE_HINT_MAX_BYTES,
            ),
        },
    }
    rendered = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    if len(rendered.encode("utf-8")) > ADAPTED_DRAFT_MODEL_INPUT_MAX_BYTES:
        raise ValueError("bounded adapted draft model input exceeds its byte budget")
    return rendered


async def generate_adapted_draft(
    *,
    project: ProjectRef,
    base_draft_artifact: ArtifactEnvelope,
    format_decision_artifact: ArtifactEnvelope,
    structured_model: StructuredAdaptedDraftModel,
    created_at: datetime,
    source_thread_id: str,
    source_run_id: str,
    logical_account: LogicalAccountRef | None = None,
) -> ArtifactEnvelope:
    """Generate one bounded format translation below exact immutable parents."""

    _, selected_format, base_body = validate_adapted_draft_parents(
        project=project,
        base_draft_artifact=base_draft_artifact,
        format_decision_artifact=format_decision_artifact,
    )
    messages: tuple[BaseMessage, ...] = (
        SystemMessage(content=ADAPTED_DRAFT_SYSTEM_PROMPT),
        HumanMessage(
            content=_render_model_input(
                base_draft_artifact=base_draft_artifact,
                format_decision_artifact=format_decision_artifact,
            )
        ),
    )
    try:
        model_result = await structured_model(AdaptedDraftDraft, messages)
        draft = AdaptedDraftDraft.model_validate(model_result)
        validate_adapted_draft_output(
            draft=draft,
            base_body=base_body,
            selected_format=selected_format,
        )
    except (ValidationError, TypeError, ValueError) as error:
        raise AdaptedDraftModelError("structured model returned an invalid adapted draft") from error
    except Exception as error:
        raise AdaptedDraftModelError("structured model failed while generating an adapted draft") from error

    return seal_adapted_draft(
        project=project,
        draft=draft,
        base_draft_artifact=base_draft_artifact,
        format_decision_artifact=format_decision_artifact,
        logical_account=logical_account,
        created_at=created_at,
        source_thread_id=source_thread_id,
        source_run_id=source_run_id,
    )


__all__ = [
    "ADAPTED_DRAFT_MODEL_INPUT_MAX_BYTES",
    "ADAPTED_DRAFT_SYSTEM_PROMPT",
    "AdaptedDraftModelError",
    "StructuredAdaptedDraftModel",
    "generate_adapted_draft",
]
