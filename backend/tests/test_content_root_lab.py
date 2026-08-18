from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from experiments.content_root_lab.contracts import (
    CandidateAssessment,
    ContentRootCandidate,
    ContentRootCandidateDraft,
    ContentRootGraph,
    ContentRootGraphDraft,
    ContentRootSelection,
    MarketingRelation,
    SemanticComponentDraft,
    bind_graph,
)
from experiments.content_root_lab.datasets import (
    load_development_preferences,
    load_held_out_cases,
)
from experiments.content_root_lab.dspy_selector import _history_usage
from experiments.content_root_lab.evaluation import score_case
from experiments.content_root_lab.lab import (
    CANDIDATE_GRAPH_SYSTEM_PROMPT,
    generate_candidate_graph,
    render_candidate_input,
    render_selection_input,
    select_content_root,
)


class _StructuredRunnable:
    def __init__(self, model: _StructuredModel, schema: type) -> None:
        self._model = model
        self._schema = schema

    async def ainvoke(self, messages, config=None):
        self._model.calls.append((self._schema, messages, config))
        return self._model.outputs.pop(0)


class _StructuredModel:
    def __init__(self, outputs: list[dict]) -> None:
        self.outputs = list(outputs)
        self.calls: list[tuple[type, object, object]] = []

    def with_structured_output(self, schema, *, include_raw=False):
        assert include_raw is True
        return _StructuredRunnable(self, schema)


def _graph() -> ContentRootGraph:
    return ContentRootGraph(
        subject_expression="我是做测试对象的",
        commercial_object="测试对象",
        relations=(
            MarketingRelation(
                relation_id="rel-object-practice",
                source="测试对象",
                relation="participates_in_practice",
                target="长期实践",
                basis="对象反复参与该实践",
                status="commonsense_hypothesis",
            ),
        ),
        candidates=(
            ContentRootCandidate(
                candidate_id="candidate-object",
                label="测试对象",
                candidate_kind="object",
                relation_path=(),
                return_path="它就是用户经营的对象。",
                content_capacity="可以展开对象本身的人、事、历史与变化。",
            ),
            ContentRootCandidate(
                candidate_id="candidate-practice",
                label="长期实践",
                candidate_kind="human_practice",
                relation_path=("rel-object-practice",),
                return_path="对象是该实践中的一种承载物。",
                content_capacity="可以展开参与者、关系、事件及长期变化。",
            ),
        ),
    )


def test_graph_rejects_a_candidate_path_with_an_unknown_relation() -> None:
    graph = _graph().model_dump(mode="python")
    graph["candidates"][1]["relation_path"] = ("missing-relation",)

    with pytest.raises(ValidationError, match="known relation"):
        ContentRootGraph.model_validate(graph)


def test_complete_semantic_component_is_promoted_with_deterministic_ids() -> None:
    draft = ContentRootGraphDraft(
        commercial_object="地域活动载体",
        candidates=(
            ContentRootCandidateDraft(
                label="地域活动载体",
                candidate_kind="commercial_object",
                semantic_path=(),
                return_path="用户直接经营的对象。",
                content_capacity="可以展开对象本身。",
            ),
            ContentRootCandidateDraft(
                label="广泛生活",
                candidate_kind="human_concern",
                semantic_path=(
                    {
                        "source": "地域活动载体",
                        "relation": "可以引出",
                        "target": "广泛生活",
                        "basis": "存在较弱的一般关联",
                        "status": "commonsense_hypothesis",
                    },
                ),
                return_path="存在间接返回路径。",
                content_capacity="容量大但可能过泛。",
            ),
        ),
        semantic_components=(
            SemanticComponentDraft(
                component_text="活动",
                semantic_role="complete_activity",
                names_complete_world=True,
                rationale="该成分本身仍是完整活动。",
                return_path="原对象是参与该活动的具体载体。",
                content_capacity="可以展开活动中的人、事、时间和地方。",
            ),
        ),
    )

    graph = bind_graph("我是做地域活动载体的", draft)
    promoted = next(candidate for candidate in graph.candidates if candidate.label == "活动")

    assert promoted.relation_path
    assert promoted.candidate_id.startswith("candidate-")
    assert graph.relations[0].relation_id.startswith("relation-")


def test_non_world_semantic_component_may_omit_candidate_only_fields() -> None:
    component = SemanticComponentDraft(
        component_text="地域修饰",
        semantic_role="modifier",
        names_complete_world=False,
        rationale="单独不命名完整内容世界。",
        return_path="",
        content_capacity="",
    )

    assert component.return_path is None
    assert component.content_capacity is None


def test_selection_must_rank_every_frozen_candidate_once() -> None:
    graph = _graph()

    with pytest.raises(ValidationError, match="rank every frozen candidate exactly once"):
        ContentRootSelection(
            graph_id=graph.graph_id(),
            selected_candidate_id="candidate-practice",
            comparison_order=("candidate-practice",),
            assessments=(
                CandidateAssessment(
                    candidate_id="candidate-practice",
                    reason="长期容量更大。",
                ),
            ),
            rationale="选择长期实践。",
            frozen_candidate_ids=tuple(candidate.candidate_id for candidate in graph.candidates),
        )


def test_selection_cannot_invent_a_candidate() -> None:
    graph = _graph()

    with pytest.raises(ValidationError, match="selected candidate must be frozen"):
        ContentRootSelection(
            graph_id=graph.graph_id(),
            selected_candidate_id="invented",
            comparison_order=("invented", "candidate-object"),
            assessments=(
                CandidateAssessment(candidate_id="invented", reason="虚构"),
                CandidateAssessment(candidate_id="candidate-object", reason="备选"),
            ),
            rationale="不应成立。",
            frozen_candidate_ids=tuple(candidate.candidate_id for candidate in graph.candidates),
        )


def test_selection_compares_the_winner_to_each_alternative_without_full_matrix() -> None:
    base = _graph()
    graph = ContentRootGraph(
        subject_expression=base.subject_expression,
        commercial_object=base.commercial_object,
        relations=(
            *base.relations,
            MarketingRelation(
                relation_id="rel-object-concern",
                source="测试对象",
                relation="may_raise",
                target="广泛关切",
                basis="对象可能引出该关切",
                status="commonsense_hypothesis",
            ),
        ),
        candidates=(
            *base.candidates,
            ContentRootCandidate(
                candidate_id="candidate-concern",
                label="广泛关切",
                candidate_kind="human_concern",
                relation_path=("rel-object-concern",),
                return_path="对象可以引出该关切。",
                content_capacity="容量较大，但容易过泛。",
            ),
        ),
    )

    selection = ContentRootSelection(
        graph_id=graph.graph_id(),
        selected_candidate_id="candidate-practice",
        comparison_order=("candidate-practice", "candidate-object", "candidate-concern"),
        assessments=(
            CandidateAssessment(candidate_id="candidate-practice", reason="容量与路径兼具。"),
            CandidateAssessment(candidate_id="candidate-object", reason="具体但较窄。"),
            CandidateAssessment(candidate_id="candidate-concern", reason="过泛。"),
        ),
        pairwise_preferences=(
            {
                "left_candidate_id": "candidate-practice",
                "right_candidate_id": "candidate-object",
                "preferred_candidate_id": "candidate-practice",
                "reason": "容量更大。",
            },
            {
                "left_candidate_id": "candidate-practice",
                "right_candidate_id": "candidate-concern",
                "preferred_candidate_id": "candidate-practice",
                "reason": "语义路径更稳。",
            },
        ),
        rationale="选择长期实践。",
        frozen_candidate_ids=tuple(candidate.candidate_id for candidate in graph.candidates),
    )

    assert len(selection.pairwise_preferences) == len(graph.candidates) - 1


def test_held_out_expectations_never_enter_model_inputs() -> None:
    held_out = load_held_out_cases()
    for case in held_out.cases:
        candidate_input = render_candidate_input(case.subject_expression)
        selection_input = render_selection_input(_graph(), development_examples=())
        assert '"accepted_aliases"' not in candidate_input
        assert '"rejected_exact_labels"' not in candidate_input
        assert '"review_rationale"' not in candidate_input
        assert case.review_rationale not in candidate_input

        # The candidate prompt must contain the user's literal expression, which may
        # naturally overlap an evaluation alias. The frozen graph used for selection
        # is synthetic, so none of the hidden answer content may appear there.
        for alias in (*case.accepted_aliases, *case.rejected_exact_labels):
            assert alias not in selection_input
        assert case.review_rationale not in selection_input


def test_development_and_held_out_businesses_are_disjoint() -> None:
    development = load_development_preferences()
    held_out = load_held_out_cases()

    development_subjects = {example.subject_expression for example in development.examples}
    held_out_subjects = {case.subject_expression for case in held_out.cases}
    assert development_subjects.isdisjoint(held_out_subjects)


def test_candidate_recall_uses_generic_component_ablation_without_development_keywords() -> None:
    assert "成分消融" in CANDIDATE_GRAPH_SYSTEM_PROMPT
    for forbidden_keyword in ("黄金", "水果", "海鲜", "火锅", "腕表", "医美", "雪茄"):
        assert forbidden_keyword not in CANDIDATE_GRAPH_SYSTEM_PROMPT


def test_frozen_dataset_files_are_valid_json_and_have_stable_ids() -> None:
    dataset_dir = Path(__file__).parents[1] / "experiments" / "content_root_lab" / "datasets"
    payloads = [json.loads(path.read_text(encoding="utf-8")) for path in sorted(dataset_dir.glob("*.json"))]

    assert {payload["dataset_id"] for payload in payloads} == {
        "content-root-development-v1",
        "content-root-held-out-v1",
    }


@pytest.mark.asyncio
async def test_candidate_generation_binds_the_literal_subject_and_relation_graph() -> None:
    model = _StructuredModel(
        [
            {
                "commercial_object": "测试对象",
                "candidates": [
                    {
                        "label": "测试对象",
                        "candidate_kind": "object",
                        "semantic_path": [],
                        "return_path": "它就是用户经营的对象。",
                        "content_capacity": "可以展开对象本身的人、事、历史与变化。",
                        "limitations": [],
                    },
                    {
                        "label": "长期实践",
                        "candidate_kind": "human_practice",
                        "semantic_path": [
                            {
                                "source": "测试对象",
                                "relation": "participates_in_practice",
                                "target": "长期实践",
                                "basis": "对象反复参与该实践",
                                "status": "commonsense_hypothesis",
                            }
                        ],
                        "return_path": "对象是该实践中的一种承载物。",
                        "content_capacity": "可以展开参与者、关系、事件及长期变化。",
                        "limitations": [],
                    },
                ],
                "unknowns": [],
            }
        ]
    )

    graph = await generate_candidate_graph(
        "  我是做测试对象的  ",
        model=model,
    )

    assert graph.subject_expression == "我是做测试对象的"
    assert graph.candidates[0].candidate_id.startswith("candidate-")
    assert graph.candidates[1].relation_path == (graph.relations[0].relation_id,)
    assert graph.graph_id() == graph.graph_id()
    assert len(model.calls) == 1
    model_schema = json.dumps(model.calls[0][0].model_json_schema(), ensure_ascii=False)
    assert "candidate_id" not in model_schema
    assert "relation_id" not in model_schema


@pytest.mark.asyncio
async def test_selector_compares_only_the_frozen_graph() -> None:
    graph = _graph()
    model = _StructuredModel(
        [
            {
                "selected_candidate_id": "candidate-practice",
                "comparison_order": ["candidate-practice", "candidate-object"],
                "assessments": [
                    {"candidate_id": "candidate-practice", "reason": "长期容量更大。"},
                    {"candidate_id": "candidate-object", "reason": "可作为具体入口。"},
                ],
                "pairwise_preferences": [
                    {
                        "left_candidate_id": "candidate-object",
                        "right_candidate_id": "candidate-practice",
                        "preferred_candidate_id": "candidate-practice",
                        "reason": "包含对象且能展开人与事。",
                    }
                ],
                "rationale": "选择长期实践。",
                "unknowns": [],
            }
        ]
    )

    selection = await select_content_root(graph, model=model)

    assert selection.selected_candidate_id == "candidate-practice"
    assert selection.frozen_candidate_ids == ("candidate-object", "candidate-practice")
    assert set(selection.comparison_order) == set(selection.frozen_candidate_ids)
    assert len(model.calls) == 1


def test_automatic_score_uses_frozen_aliases_and_flags_seller_drift() -> None:
    coffee_case = next(case for case in load_held_out_cases().cases if case.case_id == "coffee-beans")

    accepted = score_case(
        case=coffee_case,
        candidate_labels=("咖啡豆", "咖啡", "早晨生活"),
        selected_label="咖啡",
    )
    rejected = score_case(
        case=coffee_case,
        candidate_labels=("咖啡豆", "咖啡豆销售"),
        selected_label="咖啡豆销售",
    )

    assert accepted.candidate_recall is True
    assert accepted.final_acceptance is True
    assert accepted.selected_rejected_label is False
    assert rejected.final_acceptance is False
    assert rejected.selected_rejected_label is True


def test_dspy_history_usage_accepts_typed_history_entries() -> None:
    usage = _history_usage(
        [
            SimpleNamespace(
                usage={
                    "input_tokens": 120,
                    "output_tokens": 30,
                    "total_tokens": 150,
                }
            )
        ]
    )

    assert usage == {
        "input_tokens": 120,
        "output_tokens": 30,
        "total_tokens": 150,
    }
