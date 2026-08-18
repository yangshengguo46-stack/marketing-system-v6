from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from deerflow.content_intelligence.analyzer import _invoke_structured
from deerflow.content_intelligence.lexical_evidence import LexicalEntryEvidence, LexicalEvidence
from experiments.compact_lexical_candidate_lab.contracts import (
    CandidateDraft,
    CandidateItemDraft,
    CandidateRecord,
    bind_candidate_record,
)

_MAX_MODEL_INPUT_BYTES = 4_096

CANDIDATE_SYSTEM_PROMPT = """<compact_lexical_candidate_lab>
你只负责开放召回商业对象可能连接的完整内容世界，不排序、不推荐、不选择内容根，也不做账号定位或选题。

- commercial_object 已冻结，必须原样保留为一个候选；它的 relation_from_object 为 null。
- 最多返回八个平等候选。其他候选必须说明与商业对象的真实语义关系。
- 检查复合词中是否包含在当前整词里仍保持意义、并能独立命名完整对象或活动的多字成分。
- 输入可能有 compact_lexical_evidence。它只是带来源的词义观察，不是答案。先判断整词当前义项和组合透明度；借词、音译、同形异义和词汇化名称不得机械拆解。
- 词义投影缺失不代表候选不存在；可用通识补充语义成立的候选。
- 材质、规格、单字残片、经营后缀和实现手段通常不是独立内容世界。
- 不联网，不编造具体人物、事件、数据、市场结论或用户资源。不确定的写入 unknowns。
- 不输出来源字段、候选 ID、分数、排名或胜者。

只返回结构合同。
</compact_lexical_candidate_lab>"""


def build_compact_lexical_projection(evidence: LexicalEvidence) -> dict[str, Any]:
    multi_character = [component for component in evidence.component_candidates if len(component.term) >= 2]
    longest = [component for component in multi_character if not any(component.term != other.term and component.term in other.term for other in multi_character)]
    longest.sort(key=lambda component: (min(component.positions), -len(component.term), component.term))
    return {
        "lexical_head": evidence.lexical_head,
        "source": evidence.source.model_dump(mode="json"),
        "whole_word_senses": [_compact_entry(entry) for entry in evidence.whole_word_entries[:2]],
        "longest_components": [
            {
                "term": component.term,
                "positions": list(component.positions),
                "senses": [_compact_entry(entry) for entry in component.entries[:2]],
            }
            for component in longest[:4]
        ],
        "limitations": [
            "词典子串不证明该义项在整词中保持。",
            "缺失只表示未知；借词、音译和同形异义不得机械拆分。",
        ],
    }


def render_candidate_input(
    *,
    subject_expression: str,
    commercial_object: str,
    lexical_projection: dict[str, Any] | None,
) -> str:
    payload: dict[str, Any] = {
        "subject_expression": subject_expression.strip(),
        "commercial_object": commercial_object,
    }
    if lexical_projection is not None:
        payload["compact_lexical_evidence"] = lexical_projection
    rendered = "--- BEGIN COMPACT LEXICAL CANDIDATE INPUT ---\n" + json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n--- END COMPACT LEXICAL CANDIDATE INPUT ---"
    if len(rendered.encode("utf-8")) > _MAX_MODEL_INPUT_BYTES:
        raise ValueError("compact lexical candidate input exceeded its byte budget")
    return rendered


async def generate_candidate_record(
    *,
    subject_expression: str,
    commercial_object: str,
    model: Any,
    lexical_projection: dict[str, Any] | None,
    runnable_config: dict[str, Any] | None = None,
) -> CandidateRecord:
    draft = await _invoke_structured(
        model,
        CandidateDraft,
        (
            SystemMessage(content=CANDIDATE_SYSTEM_PROMPT),
            HumanMessage(
                content=render_candidate_input(
                    subject_expression=subject_expression,
                    commercial_object=commercial_object,
                    lexical_projection=lexical_projection,
                )
            ),
        ),
        runnable_config=runnable_config,
        include_raw=True,
        container_fields={"candidates", "unknowns"},
    )
    return bind_candidate_record(
        subject_expression=subject_expression,
        commercial_object=commercial_object,
        draft=draft,
        lexical_projection=lexical_projection,
    )


def build_dictionary_only_record(
    *,
    subject_expression: str,
    commercial_object: str,
    lexical_projection: dict[str, Any],
) -> CandidateRecord:
    candidates = [
        CandidateItemDraft(
            label=commercial_object,
            candidate_kind="commercial_object",
            relation_from_object=None,
        )
    ]
    for component in lexical_projection.get("longest_components", []):
        term = component.get("term")
        if not isinstance(term, str) or not term.strip() or term == commercial_object:
            continue
        candidates.append(
            CandidateItemDraft(
                label=term,
                candidate_kind="lexical_component_candidate",
                relation_from_object="CC-CEDICT 收录为商业对象中的最长多字真子串",
            )
        )
        if len(candidates) == 8:
            break
    draft = CandidateDraft(
        commercial_object=commercial_object,
        candidates=tuple(candidates),
        unknowns=("词典裸候选没有判断子串义项是否在整词中保持，也没有选择内容根。",),
    )
    return bind_candidate_record(
        subject_expression=subject_expression,
        commercial_object=commercial_object,
        draft=draft,
        lexical_projection=lexical_projection,
    )


def _compact_entry(entry: LexicalEntryEvidence) -> dict[str, Any]:
    return {
        "term": entry.term,
        "pinyin": entry.pinyin,
        "glosses": list(entry.glosses[:2]),
        "composition_hint": entry.composition_hint,
    }


__all__ = [
    "CANDIDATE_SYSTEM_PROMPT",
    "build_compact_lexical_projection",
    "build_dictionary_only_record",
    "generate_candidate_record",
    "render_candidate_input",
]
