from __future__ import annotations

import json
from pathlib import Path

import pytest

from experiments.thin_content_root_lab.contracts import (
    RootCandidateDraft,
    ThinRootDraft,
    bind_thin_root_record,
)
from experiments.thin_content_root_lab.datasets import RootCohort, load_held_out_cases
from experiments.thin_content_root_lab.evaluation import score_case, summarize_scores
from experiments.thin_content_root_lab.lab import generate_thin_root_candidates, render_thin_root_input
from experiments.thin_content_root_lab.run import _CountingModel, preflight_cases


def _candidate(label: str) -> RootCandidateDraft:
    return RootCandidateDraft(
        label=label,
        relation_to_business="该商业对象帮助参与者进入这个长期实践，这个实践也会持续需要该对象。",
        long_term_capacity="可以长期容纳不同人物、时间、空间与事件。",
        boundary="不包括具体单次事件、经营流程和相邻商品。",
    )


def test_dataset_is_frozen_new_and_covers_transfer_and_lexical_guards() -> None:
    dataset = load_held_out_cases()

    assert dataset.dataset_id == "thin-single-agent-content-root-held-out-v1"
    assert dataset.status == "frozen_before_implementation_and_live_run"
    assert len(dataset.cases) == 12
    assert sum(case.cohort is RootCohort.WORLD_TRANSFER for case in dataset.cases) == 9
    assert sum(case.cohort is RootCohort.LEXICALIZED_GUARD for case in dataset.cases) == 3
    assert sum(len(case.required_concept_groups) for case in dataset.cases) == 16

    current_dataset = Path(__file__).parents[1] / "experiments" / "thin_content_root_lab" / "datasets" / "held_out_v1.json"
    consumed_expressions: set[str] = set()
    for path in (Path(__file__).parents[1] / "experiments").glob("*/datasets/*.json"):
        if path == current_dataset:
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        consumed_expressions.update(str(case["subject_expression"]) for case in payload.get("cases", ()) if isinstance(case, dict) and "subject_expression" in case)
    assert not consumed_expressions.intersection(case.subject_expression for case in dataset.cases)


def test_model_contract_forbids_paths_selection_sources_maps_topics_and_facts() -> None:
    payload = _candidate("婴幼儿喂养").model_dump(mode="json")
    for forbidden_field, value in (
        ("semantic_path", []),
        ("selected", True),
        ("rank", 1),
        ("source_reader", "single"),
        ("map_nodes", []),
        ("topics", []),
        ("facts", []),
    ):
        with pytest.raises(ValueError):
            RootCandidateDraft.model_validate({**payload, forbidden_field: value})


def test_draft_rejects_duplicate_candidates_after_normalization() -> None:
    with pytest.raises(ValueError, match="candidate labels must be unique"):
        ThinRootDraft(candidates=(_candidate("职场形象"), _candidate("职 场 形 象")))


def test_binding_adds_ids_and_provenance_without_adding_or_selecting_candidates() -> None:
    record = bind_thin_root_record(
        subject_expression="我是做商务西装定制的",
        commercial_object="商务西装定制",
        draft=ThinRootDraft(candidates=(_candidate("商务着装"), _candidate("职场形象"))),
    )

    assert [candidate.label for candidate in record.candidates] == ["商务着装", "职场形象"]
    assert all(candidate.candidate_id.startswith("thin-root-") for candidate in record.candidates)
    assert all(candidate.source == "single_thin_reader" for candidate in record.candidates)
    dumped = record.model_dump(mode="json")
    assert "selected_candidate_id" not in dumped
    assert "ranking" not in dumped
    assert "semantic_path" not in str(dumped)


def test_scoring_uses_distinct_candidates_for_groups_and_substring_matching() -> None:
    case = next(case for case in load_held_out_cases().cases if case.case_id == "pour-over-coffee-tools")

    one_label = score_case(case, ("手冲咖啡",))
    two_labels = score_case(case, ("手冲咖啡的长期实践", "世界咖啡文化"))

    assert one_label.recalled_group_count == 1
    assert one_label.complete_recall is False
    assert two_labels.recalled_group_count == 2
    assert two_labels.complete_recall is True


def test_scoring_keeps_lexical_guard_noise_separate() -> None:
    case = next(case for case in load_held_out_cases().cases if case.case_id == "buddha-jumps-over-wall-guard")
    score = score_case(case, ("闽菜宴席", "佛教寺庙饮食"))

    assert score.recalled_group_count == 1
    assert score.forbidden_hit is True
    assert score.matched_forbidden_fragments == ("佛教", "寺庙")


def test_score_summary_counts_groups_cases_contracts_candidates_and_guards() -> None:
    dataset = load_held_out_cases()
    baby = next(case for case in dataset.cases if case.case_id == "baby-food-maker")
    guard = next(case for case in dataset.cases if case.case_id == "fish-fragrant-pork-guard")
    scores = (
        score_case(baby, ("婴幼儿辅食与喂养", "家庭育儿")),
        score_case(guard, ("川菜鱼香味型", "鱼类饮食")),
    )

    assert summarize_scores(scores) == {
        "case_count": 2,
        "required_group_count": 2,
        "recalled_group_count": 2,
        "complete_case_recall": 2,
        "guard_case_count": 1,
        "guard_forbidden_hit": 1,
        "contract_success": 2,
        "candidate_count": 4,
    }


def test_rendered_input_is_bounded_and_contains_no_hidden_or_consumed_examples() -> None:
    case = load_held_out_cases().cases[0]
    rendered = render_thin_root_input(
        subject_expression=case.subject_expression,
        commercial_object=case.commercial_object,
    )

    assert len(rendered.encode("utf-8")) <= 4_096
    assert "required_concept_groups" not in rendered
    assert "forbidden_label_fragments" not in rendered
    assert "review_rationale" not in rendered
    assert "黄金礼品" not in rendered
    assert "水果店" not in rendered
    assert str(Path(__file__).parent) not in rendered


@pytest.mark.asyncio
async def test_generation_uses_one_reader_and_preserves_an_empty_candidate_set(monkeypatch: pytest.MonkeyPatch) -> None:
    import experiments.thin_content_root_lab.lab as lab_module

    calls = 0

    async def fake_invoke_structured(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return ThinRootDraft(candidates=(), unknowns=("商业对象语义不足。",))

    monkeypatch.setattr(lab_module, "_invoke_structured", fake_invoke_structured)
    record = await generate_thin_root_candidates(
        subject_expression="我是做家庭收纳师的",
        commercial_object="家庭收纳师服务",
        model=object(),
    )

    assert calls == 1
    assert record.candidates == ()
    assert record.unknowns == ("商业对象语义不足。",)


def test_preflight_covers_every_case_before_any_model_call() -> None:
    report = preflight_cases(load_held_out_cases().cases)

    assert report["case_count"] == 12
    assert report["message_count"] == 12
    assert report["all_within_budget"] is True
    assert report["max_input_bytes"] <= 4_096
    assert report["model_calls"] == 0


@pytest.mark.asyncio
async def test_failed_structured_attempt_is_still_counted() -> None:
    class FailingRunnable:
        async def ainvoke(self, *_args, **_kwargs):
            raise ValueError("invalid structured output")

    class FailingModel:
        def with_structured_output(self, *_args, **_kwargs):
            return FailingRunnable()

    counted = _CountingModel(FailingModel())

    with pytest.raises(ValueError, match="invalid structured output"):
        await counted.with_structured_output(object).ainvoke([])

    assert counted.calls == 1
