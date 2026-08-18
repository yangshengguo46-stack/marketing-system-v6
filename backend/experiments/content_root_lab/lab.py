from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from deerflow.content_intelligence.analyzer import _invoke_structured
from experiments.content_root_lab.contracts import (
    ContentRootGraph,
    ContentRootGraphDraft,
    ContentRootSelection,
    ContentRootSelectionDraft,
    bind_graph,
    bind_selection,
)
from experiments.content_root_lab.datasets import DevelopmentPreference

CANDIDATE_GRAPH_SYSTEM_PROMPT = """<content_root_lab>
你只负责为用户的商业表达建立“可选内容根关系图”，不负责起号方案、账号定位、选题或写稿。

- 先如实识别用户经营的 commercial_object。
- 从该对象出发，开放召回语义上成立的完整对象、参与活动、人类实践、社会关系、长期关切或文化世界。这些只是平等候选，不预设越抽象越好。
- 开放召回时执行逐词的“语义成分拆解与成分消融”。在 semantic_components 中列出原表达里有意义的最小成分，必要时可同时保留嵌套成分。
- 对每个成分做反事实检查：去掉其他成分后，它是否仍独立命名一个完整、可长期研究的对象或活动？若是，names_complete_world 为 true，且必须填写 return_path 与 content_capacity；若否，这两项可为 null。
- 地域修饰、材质、规格、经营容器、实现手段、中间载体或语义残片本身通常不是完整世界。代码只会把 names_complete_world 为 true 的成分并入候选图，它们仍不拥有最终决定权。
- semantic_path 内的 relation 使用准确的自然语言关系，不套固定理论标签。每个非商业对象候选都必须有从 commercial_object 连续到该候选的 semantic_path；路径中上一步 target 必须等于下一步 source，最后一步 target 必须等于候选 label。
- 关系来自用户原话才是 lexical_observation；来自一般知识则是 commonsense_hypothesis，不得冒充已取证事实。
- 保留 commercial_object 本身作为一个候选，label 精确复制 commercial_object，其 semantic_path 为空。
- 不要生成 relation_id 或 candidate_id；这些标识由代码绑定。
- 卖方的获客、门店经营、供应链、销售和制作流程如果被召回，candidate_kind 必须明示为 seller_operation，不得包装成观众内容世界。
- candidates 中只保留商业对象和语义上真正不同的其他方向，不要重复 semantic_components，不为凑数量换说法。
- return_path 说明用户的业务为何能合理讲这个世界；content_capacity 说明该世界可否长期展开具体的人、地方、时间、事件、关系与变化。
- 不联网，不编造具体人物、事件、数据或市场结论。不确定的放入 unknowns 或 limitations。

只返回结构合同。
</content_root_lab>"""

SELECTION_SYSTEM_PROMPT = """<content_root_lab>
你只负责比较一张已经冻结的内容根候选图。不得增加、改名、合并或删除候选。

选择标准是“最大有效内容世界”：
- 与用户真实业务有可解释、可返回的语义路径；
- 能长期展开具体的人、地方、时间、事件、行为、关系与变化；
- 能包含更窄候选的有效内容，却不泛化成任何行业都能套用的大词；
- 对象本身已经足够丰富时，它可以正当获胜；不预设活动、需求或关系一定更好。
- seller_operation 通常是卖方怎么卖，不是观众长期要看什么；除非用户的商业对象本身就是该运营活动。

对每个候选给出 assessment，再让最终胜者与其他每个备选恰好做一次 pairwise preference；不要穷举备选之间的无关比较。comparison_order 必须从最优到最弱覆盖全部候选，selected_candidate_id 必须是排名第一。
输入若包含 development_preferences，它们只是跨行业比较原则，不是当前行业的关键词规则。

只返回结构合同。
</content_root_lab>"""


def render_candidate_input(subject_expression: str) -> str:
    payload = {"subject_expression": subject_expression.strip()}
    return _render_envelope("CONTENT ROOT CANDIDATE INPUT", payload)


def render_selection_input(
    graph: ContentRootGraph,
    development_examples: Sequence[DevelopmentPreference] = (),
) -> str:
    payload: dict[str, Any] = {
        "frozen_graph": graph.model_dump(mode="json"),
        "development_preferences": [
            {
                "subject_expression": example.subject_expression,
                "candidates": [candidate.model_dump(mode="json") for candidate in example.candidates],
                "preferred_candidate_id": example.preferred_candidate_id,
                "preference_reason": example.preference_reason,
            }
            for example in development_examples
        ],
    }
    return _render_envelope("CONTENT ROOT SELECTION INPUT", payload)


async def generate_candidate_graph(
    subject_expression: str,
    *,
    model: Any,
    runnable_config: dict[str, Any] | None = None,
) -> ContentRootGraph:
    literal_subject = subject_expression.strip()
    if not literal_subject:
        raise ValueError("subject expression must not be empty")
    draft = await _invoke_structured(
        model,
        ContentRootGraphDraft,
        (
            SystemMessage(content=CANDIDATE_GRAPH_SYSTEM_PROMPT),
            HumanMessage(content=render_candidate_input(literal_subject)),
        ),
        runnable_config=runnable_config,
        include_raw=True,
        container_fields={"candidates", "semantic_components", "unknowns"},
    )
    return bind_graph(literal_subject, draft)


async def select_content_root(
    graph: ContentRootGraph,
    *,
    model: Any,
    runnable_config: dict[str, Any] | None = None,
    development_examples: Sequence[DevelopmentPreference] = (),
) -> ContentRootSelection:
    draft = await _invoke_structured(
        model,
        ContentRootSelectionDraft,
        (
            SystemMessage(content=SELECTION_SYSTEM_PROMPT),
            HumanMessage(
                content=render_selection_input(
                    graph,
                    development_examples=development_examples,
                )
            ),
        ),
        runnable_config=runnable_config,
        include_raw=True,
        container_fields={
            "comparison_order",
            "assessments",
            "pairwise_preferences",
            "unknowns",
        },
    )
    return bind_selection(graph, draft)


def _render_envelope(label: str, payload: dict[str, Any]) -> str:
    return f"--- BEGIN {label} ---\n" + json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + f"\n--- END {label} ---"


__all__ = [
    "CANDIDATE_GRAPH_SYSTEM_PROMPT",
    "SELECTION_SYSTEM_PROMPT",
    "generate_candidate_graph",
    "render_candidate_input",
    "render_selection_input",
    "select_content_root",
]
