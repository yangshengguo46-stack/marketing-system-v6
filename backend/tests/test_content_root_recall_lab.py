from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from experiments.content_root_recall_lab.contracts import (
    CandidateDraft,
    CandidateWorkerDraft,
    ReaderKind,
    SemanticPathStepDraft,
    bind_recall_record,
)
from experiments.content_root_recall_lab.datasets import RecallCohort, load_held_out_cases
from experiments.content_root_recall_lab.evaluation import score_case, summarize_scores
from experiments.content_root_recall_lab.lab import (
    generate_parallel_recall,
    merge_worker_drafts,
    render_recall_input,
)
from experiments.content_root_recall_lab.run import _CountingModel, preflight_cases


def _candidate(label: str, *, source: str = "商务伴手礼") -> CandidateDraft:
    return CandidateDraft(
        label=label,
        semantic_path=(
            SemanticPathStepDraft(
                source=source,
                relation="参与者用它完成",
                target=label,
            ),
        ),
        complete_world_reason=f"{label} 可以独立展开参与者、事件与变化。",
    )


def test_dataset_is_frozen_new_and_covers_transfer_and_guards() -> None:
    dataset = load_held_out_cases()

    assert dataset.dataset_id == "split-attention-content-root-recall-held-out-v1"
    assert dataset.status == "frozen_before_implementation_and_live_run"
    assert len(dataset.cases) == 12
    assert sum(case.cohort is RecallCohort.WORLD_TRANSFER for case in dataset.cases) == 9
    assert sum(case.cohort is RecallCohort.LEXICALIZED_GUARD for case in dataset.cases) == 3
    assert sum(len(case.required_concept_groups) for case in dataset.cases) == 16
    assert len({case.case_id for case in dataset.cases}) == 12

    consumed = {
        "我是做黄金礼品的",
        "我是开水果店的",
        "我是做海鲜的",
        "我是卖重庆火锅底料的",
        "我是开羽毛球馆的，我要怎么起号",
        "我是做麦克风的",
        "我是做老婆饼的",
    }
    assert not consumed.intersection(case.subject_expression for case in dataset.cases)


def test_model_candidate_contract_contains_no_selection_rank_or_source_fields() -> None:
    with pytest.raises(ValueError):
        CandidateDraft.model_validate(
            {
                **_candidate("送礼").model_dump(mode="json"),
                "selected": True,
                "rank": 1,
                "source_reader": "human_practice",
            }
        )


def test_binding_inserts_frozen_object_and_code_binds_reader_provenance() -> None:
    draft = CandidateWorkerDraft(candidates=(_candidate("送礼"),))

    record = bind_recall_record(
        subject_expression="我是做商务伴手礼的",
        commercial_object="商务伴手礼",
        worker_drafts=((ReaderKind.OPEN_RECALL, draft),),
    )

    assert [candidate.label for candidate in record.candidates] == ["商务伴手礼", "送礼"]
    assert record.candidates[0].semantic_path == ()
    assert record.candidates[1].source_readers == (ReaderKind.OPEN_RECALL,)
    assert "selected_candidate_id" not in record.model_dump(mode="json")
    assert "ranking" not in record.model_dump(mode="json")


def test_binding_rejects_disconnected_or_wrong_endpoint_path() -> None:
    disconnected = CandidateWorkerDraft(
        candidates=(
            CandidateDraft(
                label="商务往来",
                semantic_path=(SemanticPathStepDraft(source="礼品", relation="用于", target="商务往来"),),
                complete_world_reason="可独立展开人物和事件。",
            ),
        )
    )
    with pytest.raises(ValueError, match="frozen commercial object"):
        bind_recall_record(
            subject_expression="我是做商务伴手礼的",
            commercial_object="商务伴手礼",
            worker_drafts=((ReaderKind.OPEN_RECALL, disconnected),),
        )

    wrong_endpoint = CandidateWorkerDraft(
        candidates=(
            CandidateDraft(
                label="商务往来",
                semantic_path=(SemanticPathStepDraft(source="商务伴手礼", relation="用于", target="送礼"),),
                complete_world_reason="可独立展开人物和事件。",
            ),
        )
    )
    with pytest.raises(ValueError, match="candidate label"):
        bind_recall_record(
            subject_expression="我是做商务伴手礼的",
            commercial_object="商务伴手礼",
            worker_drafts=((ReaderKind.OPEN_RECALL, wrong_endpoint),),
        )


def test_merge_is_round_robin_deduplicated_bounded_and_never_selects() -> None:
    object_draft = CandidateWorkerDraft(candidates=tuple(_candidate(label) for label in ("伴手礼", "送礼", "礼品", "赠礼", "纪念品", "商务礼品")))
    practice_draft = CandidateWorkerDraft(candidates=tuple(_candidate(label) for label in ("送礼", "商务往来", "礼尚往来", "人情往来", "商务礼仪", "商业关系")))

    merged = merge_worker_drafts(
        subject_expression="我是做商务伴手礼的",
        commercial_object="商务伴手礼",
        worker_drafts=(
            (ReaderKind.OBJECT_ACTIVITY, object_draft),
            (ReaderKind.HUMAN_PRACTICE, practice_draft),
        ),
        max_candidates=10,
    )

    assert len(merged.candidates) == 10
    assert [candidate.label for candidate in merged.candidates[:5]] == ["商务伴手礼", "伴手礼", "送礼", "商务往来", "礼品"]
    sending_gifts = next(candidate for candidate in merged.candidates if candidate.label == "送礼")
    assert set(sending_gifts.source_readers) == {ReaderKind.OBJECT_ACTIVITY, ReaderKind.HUMAN_PRACTICE}
    assert merged.truncated is True


def test_rendered_input_is_bounded_and_hides_evaluation_labels_and_paths() -> None:
    case = load_held_out_cases().cases[0]

    rendered = render_recall_input(
        subject_expression=case.subject_expression,
        commercial_object=case.commercial_object,
    )

    assert len(rendered.encode("utf-8")) <= 4_096
    assert "required_concept_groups" not in rendered
    assert "forbidden_exact_labels" not in rendered
    assert "review_rationale" not in rendered
    assert "商务往来" not in rendered
    assert str(Path(__file__).parent) not in rendered


@pytest.mark.asyncio
async def test_parallel_readers_really_overlap_and_cannot_see_each_other(monkeypatch: pytest.MonkeyPatch) -> None:
    import experiments.content_root_recall_lab.lab as lab_module

    entered: set[ReaderKind] = set()
    both_entered = asyncio.Event()
    release = asyncio.Event()

    async def fake_invoke_worker(*, reader_kind, **_kwargs):
        entered.add(reader_kind)
        if len(entered) == 2:
            both_entered.set()
        await asyncio.wait_for(release.wait(), timeout=1)
        return CandidateWorkerDraft(candidates=(_candidate(reader_kind.value),))

    monkeypatch.setattr(lab_module, "_invoke_worker", fake_invoke_worker)
    task = asyncio.create_task(
        generate_parallel_recall(
            subject_expression="我是做商务伴手礼的",
            commercial_object="商务伴手礼",
            models={ReaderKind.OBJECT_ACTIVITY: object(), ReaderKind.HUMAN_PRACTICE: object()},
        )
    )

    await asyncio.wait_for(both_entered.wait(), timeout=1)
    release.set()
    record = await asyncio.wait_for(task, timeout=1)

    assert entered == {ReaderKind.OBJECT_ACTIVITY, ReaderKind.HUMAN_PRACTICE}
    assert {candidate.label for candidate in record.candidates} >= {"object_activity", "human_practice"}


def test_scoring_counts_required_groups_and_guard_noise_separately() -> None:
    dataset = load_held_out_cases()
    gift = next(case for case in dataset.cases if case.case_id == "business-courtesy-gift")
    guard = next(case for case in dataset.cases if case.case_id == "couple-lung-slices-guard")

    scores = (
        score_case(gift, ("商务伴手礼", "送礼", "商务往来")),
        score_case(guard, ("夫妻肺片预制菜", "川菜", "夫妻")),
    )

    assert scores[0].recalled_group_count == 2
    assert scores[0].complete_recall is True
    assert scores[1].recalled_group_count == 1
    assert scores[1].forbidden_hit is True
    assert summarize_scores(scores) == {
        "case_count": 2,
        "required_group_count": 3,
        "recalled_group_count": 3,
        "complete_case_recall": 2,
        "guard_case_count": 1,
        "guard_forbidden_hit": 1,
        "contract_success": 2,
        "candidate_count": 6,
    }


def test_preflight_checks_all_three_messages_for_all_cases_without_model_calls() -> None:
    report = preflight_cases(load_held_out_cases().cases)

    assert report["case_count"] == 12
    assert report["message_count"] == 36
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
