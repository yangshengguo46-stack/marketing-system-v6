from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from deerflow.content_intelligence.analyzer import _invoke_structured
from experiments.thin_content_root_lab.contracts import ThinRootDraft, ThinRootRecord, bind_thin_root_record

_MAX_MODEL_INPUT_BYTES = 4_096

THIN_ROOT_SYSTEM_PROMPT = """<thin_single_content_root_reader>
你只负责召回“可以成为账号最终长期内容根”的少量候选，不排序、不选择、不展开内容地图或选题。

判断标准：把候选填进“这个账号长期讲____”后应当自然；它与 commercial_object 有真实、双向可解释的关系；
它自身足以长期容纳不同人物、时间、空间和事件。候选可以处于不同抽象程度，但每一个都必须有资格被最终选为内容根，不能用一个根和它下游的具体节点凑数量。

只写候选主体及最短必要说明。不要返回 commercial_object 原文，不要写具体人物、单次事件、场景、地域、作品、热点、标题、脚本、账号定位、表现形式、变现、卖方经营、购买流程、供应链、相邻商品、数字、历史断言或其他需要查证的事实。
复合名称先判断完整词义；词汇化菜名、品牌、借词和专名不得按字面拆分。

候选为零至五个，没有可靠候选可以留空。不要输出路径、候选类型、来源、ID、分数、排名或选中项。不联网，不使用外部证据，不追求形式完整。
只返回结构合同。
</thin_single_content_root_reader>"""


def render_thin_root_input(*, subject_expression: str, commercial_object: str) -> str:
    payload = {
        "subject_expression": subject_expression.strip(),
        "commercial_object": commercial_object,
    }
    rendered = "--- BEGIN THIN CONTENT ROOT INPUT ---\n" + json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n--- END THIN CONTENT ROOT INPUT ---"
    if len(rendered.encode("utf-8")) > _MAX_MODEL_INPUT_BYTES:
        raise ValueError("thin content-root input exceeded its byte budget")
    return rendered


def render_thin_root_messages(
    *,
    subject_expression: str,
    commercial_object: str,
) -> tuple[SystemMessage, HumanMessage]:
    return (
        SystemMessage(content=THIN_ROOT_SYSTEM_PROMPT),
        HumanMessage(
            content=render_thin_root_input(
                subject_expression=subject_expression,
                commercial_object=commercial_object,
            )
        ),
    )


async def generate_thin_root_candidates(
    *,
    subject_expression: str,
    commercial_object: str,
    model: Any,
    runnable_config: dict[str, Any] | None = None,
) -> ThinRootRecord:
    draft = await _invoke_structured(
        model,
        ThinRootDraft,
        render_thin_root_messages(
            subject_expression=subject_expression,
            commercial_object=commercial_object,
        ),
        runnable_config=runnable_config,
        include_raw=True,
        container_fields={"candidates", "unknowns"},
    )
    return bind_thin_root_record(
        subject_expression=subject_expression,
        commercial_object=commercial_object,
        draft=draft,
    )


__all__ = [
    "THIN_ROOT_SYSTEM_PROMPT",
    "generate_thin_root_candidates",
    "render_thin_root_input",
    "render_thin_root_messages",
]
