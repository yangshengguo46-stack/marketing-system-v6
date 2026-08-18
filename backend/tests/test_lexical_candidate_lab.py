from __future__ import annotations

import gzip
from pathlib import Path

import pytest

from deerflow.content_intelligence.lexical_evidence import (
    CedictLexicalEvidenceProvider,
    LexicalEvidenceMode,
    build_cc_cedict_index,
)
from experiments.lexical_candidate_lab.contracts import (
    CandidateBasis,
    CandidateRecallDraft,
    CandidateRecallItem,
    bind_candidate_record,
)
from experiments.lexical_candidate_lab.datasets import load_held_out_cases
from experiments.lexical_candidate_lab.evaluation import score_case, summarize_scores
from experiments.lexical_candidate_lab.lab import (
    build_dictionary_only_record,
    render_candidate_input,
)

CEDICT_SAMPLE = """# CC-CEDICT
#! version=1
#! subversion=0
#! entries=11
#! publisher=MDBG
#! license=https://creativecommons.org/licenses/by-sa/4.0/
#! date=2026-08-19T00:00:00Z
滑雪 滑雪 [hua2 xue3] /to ski/skiing/
滑雪服 滑雪服 [hua2 xue3 fu2] /ski suit/
雪 雪 [xue3] /snow/
服 服 [fu2] /clothes/to serve/
巧克力 巧克力 [qiao3 ke4 li4] /(loanword) chocolate/
巧 巧 [qiao3] /opportunely/skilful/
克 克 [ke4] /to overcome/gram/
力 力 [li4] /power/force/
馬桶 马桶 [ma3 tong3] /toilet bowl/
馬 马 [ma3] /horse/
桶 桶 [tong3] /bucket/barrel/
"""


@pytest.fixture()
def cedict_provider(tmp_path: Path) -> CedictLexicalEvidenceProvider:
    source_path = tmp_path / "cedict.txt.gz"
    with gzip.open(source_path, "wt", encoding="utf-8", newline="\n") as stream:
        stream.write(CEDICT_SAMPLE)
    index_path = tmp_path / "cedict.sqlite3"
    receipt = build_cc_cedict_index(source_path, index_path)
    assert receipt.entry_count == 11
    return CedictLexicalEvidenceProvider(index_path, max_related_expressions=4)


def test_held_out_dataset_is_new_frozen_and_balanced() -> None:
    dataset = load_held_out_cases()

    assert dataset.dataset_id == "lexical-candidate-held-out-v1"
    assert dataset.status == "frozen_before_live_run"
    assert len(dataset.cases) == 10
    assert sum(case.cohort == "transparent" for case in dataset.cases) == 7
    assert sum(case.cohort == "guard" for case in dataset.cases) == 3
    assert len({case.case_id for case in dataset.cases}) == 10
    assert not {
        "我是做黄金礼品的",
        "我是开水果店的",
        "我是做海鲜的",
        "我是卖重庆火锅底料的",
        "我是卖咖啡豆的",
    }.intersection(case.subject_expression for case in dataset.cases)


def test_bind_candidate_record_preserves_object_and_binds_real_lexical_terms() -> None:
    draft = CandidateRecallDraft(
        commercial_object="滑雪服",
        candidates=(
            CandidateRecallItem(
                label="滑雪服",
                candidate_kind="commercial_object",
                relation_from_object=None,
                basis=CandidateBasis.LITERAL_EXPRESSION,
            ),
            CandidateRecallItem(
                label="滑雪",
                candidate_kind="activity",
                relation_from_object="滑雪服用于滑雪",
                basis=CandidateBasis.LEXICAL_EVIDENCE,
                support_terms=("滑雪",),
            ),
        ),
        unknowns=(),
    )

    record = bind_candidate_record(
        subject_expression="我是卖滑雪服的",
        commercial_object="滑雪服",
        draft=draft,
        allowed_lexical_terms={"滑雪", "雪", "服"},
        lexical_evidence_used=True,
    )

    assert record.commercial_object == "滑雪服"
    assert [candidate.label for candidate in record.candidates] == ["滑雪服", "滑雪"]
    assert record.lexical_evidence_used is True


def test_bind_candidate_record_rejects_missing_object_candidate() -> None:
    draft = CandidateRecallDraft(
        commercial_object="滑雪服",
        candidates=(
            CandidateRecallItem(
                label="滑雪",
                candidate_kind="activity",
                relation_from_object="滑雪服用于滑雪",
                basis=CandidateBasis.COMMONSENSE_HYPOTHESIS,
            ),
        ),
    )

    with pytest.raises(ValueError, match="commercial object candidate"):
        bind_candidate_record(
            subject_expression="我是卖滑雪服的",
            commercial_object="滑雪服",
            draft=draft,
            allowed_lexical_terms=set(),
            lexical_evidence_used=False,
        )


def test_bind_candidate_record_rejects_unbound_lexical_claim() -> None:
    draft = CandidateRecallDraft(
        commercial_object="滑雪服",
        candidates=(
            CandidateRecallItem(
                label="滑雪服",
                candidate_kind="commercial_object",
                relation_from_object=None,
                basis=CandidateBasis.LITERAL_EXPRESSION,
            ),
            CandidateRecallItem(
                label="冬季运动",
                candidate_kind="activity",
                relation_from_object="滑雪服用于冬季运动",
                basis=CandidateBasis.LEXICAL_EVIDENCE,
                support_terms=("冬季运动",),
            ),
        ),
    )

    with pytest.raises(ValueError, match="unbound lexical evidence"):
        bind_candidate_record(
            subject_expression="我是卖滑雪服的",
            commercial_object="滑雪服",
            draft=draft,
            allowed_lexical_terms={"滑雪", "雪", "服"},
            lexical_evidence_used=True,
        )


def test_candidate_labels_must_be_unique_after_normalization() -> None:
    with pytest.raises(ValueError, match="candidate labels must be unique"):
        CandidateRecallDraft(
            commercial_object="滑雪服",
            candidates=(
                CandidateRecallItem(
                    label="滑雪服",
                    candidate_kind="commercial_object",
                    relation_from_object=None,
                    basis=CandidateBasis.LITERAL_EXPRESSION,
                ),
                CandidateRecallItem(
                    label="滑 雪 服",
                    candidate_kind="commercial_object",
                    relation_from_object=None,
                    basis=CandidateBasis.LITERAL_EXPRESSION,
                ),
            ),
        )


@pytest.mark.asyncio
async def test_dictionary_only_arm_recalls_true_component_without_selecting_it(
    cedict_provider: CedictLexicalEvidenceProvider,
) -> None:
    evidence = await cedict_provider.lookup("滑雪服", mode=LexicalEvidenceMode.RELATIONS)

    record = build_dictionary_only_record(
        subject_expression="我是卖滑雪服的",
        commercial_object="滑雪服",
        lexical_evidence=evidence,
    )

    labels = tuple(candidate.label for candidate in record.candidates)
    assert "滑雪服" in labels
    assert "滑雪" in labels
    assert record.selected_candidate_id is None
    assert all(candidate.basis is CandidateBasis.LEXICAL_EVIDENCE for candidate in record.candidates[1:])


@pytest.mark.asyncio
async def test_dictionary_only_arm_respects_loanword_guard(
    cedict_provider: CedictLexicalEvidenceProvider,
) -> None:
    evidence = await cedict_provider.lookup("巧克力", mode=LexicalEvidenceMode.RELATIONS)

    record = build_dictionary_only_record(
        subject_expression="我是做巧克力的",
        commercial_object="巧克力",
        lexical_evidence=evidence,
    )

    assert [candidate.label for candidate in record.candidates] == ["巧克力"]


@pytest.mark.asyncio
async def test_dictionary_only_arm_exposes_non_loanword_substring_noise(
    cedict_provider: CedictLexicalEvidenceProvider,
) -> None:
    case = next(case for case in load_held_out_cases().cases if case.case_id == "toilet-lexicalized-guard")
    evidence = await cedict_provider.lookup("马桶", mode=LexicalEvidenceMode.RELATIONS)
    record = build_dictionary_only_record(
        subject_expression=case.subject_expression,
        commercial_object=case.commercial_object,
        lexical_evidence=evidence,
    )

    score = score_case(case, tuple(candidate.label for candidate in record.candidates))

    assert score.candidate_recall is True
    assert score.forbidden_hit is True
    assert set(score.matched_forbidden_labels) == {"马", "桶"}


@pytest.mark.asyncio
async def test_model_input_is_bounded_and_contains_no_hidden_labels_or_local_path(
    cedict_provider: CedictLexicalEvidenceProvider,
) -> None:
    case = next(case for case in load_held_out_cases().cases if case.case_id == "ski-clothes")
    evidence = await cedict_provider.lookup(case.commercial_object, mode=LexicalEvidenceMode.RELATIONS)

    rendered = render_candidate_input(
        subject_expression=case.subject_expression,
        commercial_object=case.commercial_object,
        lexical_evidence=evidence,
    )

    assert len(rendered.encode("utf-8")) <= 8_000
    assert str(cedict_provider._index_path) not in rendered
    assert "accepted_aliases" not in rendered
    assert "forbidden_exact_labels" not in rendered
    assert "review_rationale" not in rendered
    assert "滑雪运动" not in rendered


def test_scoring_separates_recall_from_forbidden_noise() -> None:
    ski_case = next(case for case in load_held_out_cases().cases if case.case_id == "ski-clothes")
    toilet_case = next(case for case in load_held_out_cases().cases if case.case_id == "toilet-lexicalized-guard")

    ski_score = score_case(ski_case, ("滑雪服", "滑雪"))
    toilet_score = score_case(toilet_case, ("马桶", "马", "如厕与卫生"))
    summary = summarize_scores((ski_score, toilet_score))

    assert ski_score.candidate_recall is True
    assert ski_score.forbidden_hit is False
    assert toilet_score.candidate_recall is True
    assert toilet_score.forbidden_hit is True
    assert summary == {
        "case_count": 2,
        "transparent_case_count": 1,
        "transparent_candidate_recall": 1,
        "guard_case_count": 1,
        "guard_forbidden_hit": 1,
        "contract_success": 2,
    }
