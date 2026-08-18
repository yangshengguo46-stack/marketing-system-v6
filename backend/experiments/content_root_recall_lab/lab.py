from __future__ import annotations

import asyncio
import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from deerflow.content_intelligence.analyzer import _invoke_structured
from experiments.content_root_recall_lab.contracts import (
    CandidateWorkerDraft,
    ContentRootRecallRecord,
    ReaderKind,
    bind_recall_record,
)

_MAX_MODEL_INPUT_BYTES = 4_096

OPEN_RECALL_SYSTEM_PROMPT = """<open_content_root_recall>
你只负责开放召回商业对象在真实语义上连接的完整内容世界，不排序、不选择、不写选题。
可以检查完整对象、参与活动、长期实践、社会关系与文化对象。每个候选必须用连续 semantic_path 从已冻结的 commercial_object 走到候选本身，并说明它为何能独立容纳人物、时间、空间、事件或变化。
不要返回商业对象本身；代码会补入。排除销售、获客、经营、供应链、制作工艺、购买步骤、规格材质和空泛大词。复合名称先判断整体义项，禁止按字面拆解词汇化菜名、借词或专名。
最多六个平等候选；没有可靠候选可以返回空数组。不联网，不编造事实，不输出排名、分数、来源、候选 ID 或胜者。
只返回结构合同。
</open_content_root_recall>"""

OBJECT_ACTIVITY_SYSTEM_PROMPT = """<object_activity_reader>
你是独立的候选召回读者，只查看商业对象本身。寻找两类内容世界：它完整承载或嵌入的对象，以及参与者借它反复完成的具体活动。
每个候选必须用连续 semantic_path 从已冻结的 commercial_object 走到候选本身，并说明为何可独立容纳人物、时间、空间、事件或变化。
不要返回商业对象本身；代码会补入。排除销售、经营、获客、供应链、制作工艺、购买步骤、规格材质和空泛上位词。先判断复合名称整体义项，禁止按字面拆解词汇化菜名、借词或专名。
最多六个平等候选；不确定可以留空或写 unknowns。不联网，不输出排名、分数、来源、候选 ID 或胜者，也看不到另一位读者。
只返回结构合同。
</object_activity_reader>"""

HUMAN_PRACTICE_SYSTEM_PROMPT = """<human_practice_reader>
你是独立的候选召回读者，只寻找商业对象参与其中的长期人类实践、关系、仪式或反复出现的共同关切。
候选与商业对象之间必须能双向解释：人为何在该实践中需要它，它又如何回到该实践。用连续 semantic_path 从已冻结的 commercial_object 走到候选本身，并说明为何可独立容纳人物、时间、空间、事件或变化。
不要返回商业对象本身；代码会补入。排除销售、经营、获客、供应链、制作工艺、普通一次性使用，以及“生活、文化、人性”等没有边界的大词。先判断复合名称整体义项，禁止按字面拆解词汇化菜名、借词或专名。
最多六个平等候选；没有可靠候选可返回空数组。不联网，不输出排名、分数、来源、候选 ID 或胜者，也看不到另一位读者。
只返回结构合同。
</human_practice_reader>"""

_PROMPTS = {
    ReaderKind.OPEN_RECALL: OPEN_RECALL_SYSTEM_PROMPT,
    ReaderKind.OBJECT_ACTIVITY: OBJECT_ACTIVITY_SYSTEM_PROMPT,
    ReaderKind.HUMAN_PRACTICE: HUMAN_PRACTICE_SYSTEM_PROMPT,
}


def render_recall_input(*, subject_expression: str, commercial_object: str) -> str:
    payload = {
        "subject_expression": subject_expression.strip(),
        "commercial_object": commercial_object,
    }
    rendered = "--- BEGIN CONTENT ROOT RECALL INPUT ---\n" + json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n--- END CONTENT ROOT RECALL INPUT ---"
    if len(rendered.encode("utf-8")) > _MAX_MODEL_INPUT_BYTES:
        raise ValueError("content-root recall input exceeded its byte budget")
    return rendered


def render_worker_messages(
    *,
    reader_kind: ReaderKind,
    subject_expression: str,
    commercial_object: str,
) -> tuple[SystemMessage, HumanMessage]:
    return (
        SystemMessage(content=_PROMPTS[reader_kind]),
        HumanMessage(
            content=render_recall_input(
                subject_expression=subject_expression,
                commercial_object=commercial_object,
            )
        ),
    )


async def _invoke_worker(
    *,
    reader_kind: ReaderKind,
    subject_expression: str,
    commercial_object: str,
    model: Any,
    runnable_config: dict[str, Any] | None = None,
) -> CandidateWorkerDraft:
    return await _invoke_structured(
        model,
        CandidateWorkerDraft,
        render_worker_messages(
            reader_kind=reader_kind,
            subject_expression=subject_expression,
            commercial_object=commercial_object,
        ),
        runnable_config=runnable_config,
        include_raw=True,
        container_fields={"candidates", "unknowns"},
    )


async def generate_open_recall(
    *,
    subject_expression: str,
    commercial_object: str,
    model: Any,
    runnable_config: dict[str, Any] | None = None,
) -> ContentRootRecallRecord:
    draft = await _invoke_worker(
        reader_kind=ReaderKind.OPEN_RECALL,
        subject_expression=subject_expression,
        commercial_object=commercial_object,
        model=model,
        runnable_config=runnable_config,
    )
    return bind_recall_record(
        subject_expression=subject_expression,
        commercial_object=commercial_object,
        worker_drafts=((ReaderKind.OPEN_RECALL, draft),),
    )


async def generate_parallel_recall(
    *,
    subject_expression: str,
    commercial_object: str,
    models: dict[ReaderKind, Any],
    runnable_config: dict[str, Any] | None = None,
) -> ContentRootRecallRecord:
    reader_kinds = (ReaderKind.OBJECT_ACTIVITY, ReaderKind.HUMAN_PRACTICE)
    drafts = await asyncio.gather(
        *(
            _invoke_worker(
                reader_kind=reader_kind,
                subject_expression=subject_expression,
                commercial_object=commercial_object,
                model=models[reader_kind],
                runnable_config=runnable_config,
            )
            for reader_kind in reader_kinds
        )
    )
    return merge_worker_drafts(
        subject_expression=subject_expression,
        commercial_object=commercial_object,
        worker_drafts=tuple(zip(reader_kinds, drafts, strict=True)),
    )


def merge_worker_drafts(
    *,
    subject_expression: str,
    commercial_object: str,
    worker_drafts: tuple[tuple[ReaderKind, CandidateWorkerDraft], ...],
    max_candidates: int = 10,
) -> ContentRootRecallRecord:
    return bind_recall_record(
        subject_expression=subject_expression,
        commercial_object=commercial_object,
        worker_drafts=worker_drafts,
        max_candidates=max_candidates,
    )


__all__ = [
    "HUMAN_PRACTICE_SYSTEM_PROMPT",
    "OBJECT_ACTIVITY_SYSTEM_PROMPT",
    "OPEN_RECALL_SYSTEM_PROMPT",
    "generate_open_recall",
    "generate_parallel_recall",
    "merge_worker_drafts",
    "render_recall_input",
    "render_worker_messages",
]
