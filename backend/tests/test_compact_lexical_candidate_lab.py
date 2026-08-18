from __future__ import annotations

import gzip
from pathlib import Path

import pytest

from deerflow.content_intelligence.lexical_evidence import (
    CedictLexicalEvidenceProvider,
    LexicalEvidenceMode,
    build_cc_cedict_index,
)
from experiments.compact_lexical_candidate_lab.contracts import (
    CandidateDraft,
    CandidateItemDraft,
    bind_candidate_record,
)
from experiments.compact_lexical_candidate_lab.datasets import load_held_out_cases
from experiments.compact_lexical_candidate_lab.evaluation import score_case, summarize_scores
from experiments.compact_lexical_candidate_lab.lab import (
    build_compact_lexical_projection,
    build_dictionary_only_record,
    render_candidate_input,
)
from experiments.compact_lexical_candidate_lab.run import _CountingModel, preflight_cases

CEDICT_SAMPLE = """# CC-CEDICT
#! version=1
#! subversion=0
#! entries=14
#! publisher=MDBG
#! license=https://creativecommons.org/licenses/by-sa/4.0/
#! date=2026-08-19T00:00:00Z
籃球 篮球 [lan2 qiu2] /basketball/
球 球 [qiu2] /ball/
架 架 [jia4] /frame/rack/
麥克風 麦克风 [mai4 ke4 feng1] /(loanword) microphone/
麥 麦 [mai4] /wheat/
克 克 [ke4] /to overcome/gram/
風 风 [feng1] /wind/
老婆餅 老婆饼 [lao3 po2 bing3] /wife cake; Cantonese pastry/
老婆 老婆 [lao3 po2] /wife/
老 老 [lao3] /old/
婆 婆 [po2] /old woman/
餅 饼 [bing3] /cake/
油畫 油画 [you2 hua4] /oil painting/
畫框 画框 [hua4 kuang1] /picture frame/
"""


@pytest.fixture()
def cedict_provider(tmp_path: Path) -> CedictLexicalEvidenceProvider:
    source_path = tmp_path / "cedict.txt.gz"
    with gzip.open(source_path, "wt", encoding="utf-8", newline="\n") as stream:
        stream.write(CEDICT_SAMPLE)
    index_path = tmp_path / "cedict.sqlite3"
    receipt = build_cc_cedict_index(source_path, index_path)
    assert receipt.entry_count == 14
    return CedictLexicalEvidenceProvider(index_path, max_related_expressions=16)


def test_dataset_is_new_frozen_and_balanced() -> None:
    dataset = load_held_out_cases()

    assert dataset.dataset_id == "compact-lexical-candidate-held-out-v1"
    assert dataset.status == "frozen_before_live_run"
    assert len(dataset.cases) == 10
    assert sum(case.cohort == "transparent" for case in dataset.cases) == 7
    assert sum(case.cohort == "guard" for case in dataset.cases) == 3
    assert len({case.case_id for case in dataset.cases}) == 10
    consumed = {
        "我是卖滑雪服的",
        "我是做冲浪板的",
        "我是卖古筝琴弦的",
        "我是做书法墨汁的",
        "我是卖围棋棋盘的",
        "我是做摄影补光灯的",
        "我是卖露营天幕的",
        "我是做巧克力的",
        "我是做沙发的",
        "我是做马桶的",
    }
    assert not consumed.intersection(case.subject_expression for case in dataset.cases)


@pytest.mark.asyncio
async def test_compact_projection_keeps_only_longest_multi_character_components(
    cedict_provider: CedictLexicalEvidenceProvider,
) -> None:
    evidence = await cedict_provider.lookup("篮球架", mode=LexicalEvidenceMode.EXACT)

    projection = build_compact_lexical_projection(evidence)

    assert [component["term"] for component in projection["longest_components"]] == ["篮球"]
    assert "related_expressions" not in str(projection)
    assert "球" not in {component["term"] for component in projection["longest_components"]}
    assert projection["source"]["content_sha256"]


@pytest.mark.asyncio
async def test_compact_projection_preserves_whole_word_loanword_guard(
    cedict_provider: CedictLexicalEvidenceProvider,
) -> None:
    evidence = await cedict_provider.lookup("麦克风", mode=LexicalEvidenceMode.EXACT)

    projection = build_compact_lexical_projection(evidence)

    assert projection["whole_word_senses"][0]["composition_hint"] == "loanword_or_transliteration"
    assert projection["longest_components"] == []


@pytest.mark.asyncio
async def test_compact_projection_exposes_lexicalized_multiword_guard(
    cedict_provider: CedictLexicalEvidenceProvider,
) -> None:
    evidence = await cedict_provider.lookup("老婆饼", mode=LexicalEvidenceMode.EXACT)

    projection = build_compact_lexical_projection(evidence)

    assert [component["term"] for component in projection["longest_components"]] == ["老婆"]


def test_model_contract_has_no_source_self_report_fields() -> None:
    with pytest.raises(ValueError):
        CandidateItemDraft.model_validate(
            {
                "label": "篮球",
                "candidate_kind": "activity",
                "relation_from_object": "篮球架用于篮球运动",
                "basis": "lexical_evidence",
            }
        )


def test_binding_preserves_object_without_asking_model_for_provenance() -> None:
    draft = CandidateDraft(
        commercial_object="篮球架",
        candidates=(
            CandidateItemDraft(
                label="篮球架",
                candidate_kind="commercial_object",
                relation_from_object=None,
            ),
            CandidateItemDraft(
                label="篮球",
                candidate_kind="activity",
                relation_from_object="篮球架承载篮球运动",
            ),
        ),
    )
    record = bind_candidate_record(
        subject_expression="我是卖篮球架的",
        commercial_object="篮球架",
        draft=draft,
        lexical_projection={"source": {"name": "sample"}},
    )

    assert [candidate.label for candidate in record.candidates] == ["篮球架", "篮球"]
    assert record.lexical_evidence_used is True
    assert record.lexical_payload_sha256
    assert record.selected_candidate_id is None


def test_binding_rejects_missing_or_duplicate_object() -> None:
    missing = CandidateDraft(
        commercial_object="篮球架",
        candidates=(
            CandidateItemDraft(
                label="篮球",
                candidate_kind="activity",
                relation_from_object="篮球架承载篮球运动",
            ),
        ),
    )
    with pytest.raises(ValueError, match="commercial object candidate"):
        bind_candidate_record(
            subject_expression="我是卖篮球架的",
            commercial_object="篮球架",
            draft=missing,
            lexical_projection=None,
        )

    with pytest.raises(ValueError, match="candidate labels must be unique"):
        CandidateDraft(
            commercial_object="篮球架",
            candidates=(
                CandidateItemDraft(
                    label="篮球架",
                    candidate_kind="commercial_object",
                    relation_from_object=None,
                ),
                CandidateItemDraft(
                    label="篮 球 架",
                    candidate_kind="commercial_object",
                    relation_from_object=None,
                ),
            ),
        )


@pytest.mark.asyncio
async def test_rendered_input_is_compact_and_contains_no_hidden_fields_or_paths(
    cedict_provider: CedictLexicalEvidenceProvider,
) -> None:
    case = next(case for case in load_held_out_cases().cases if case.case_id == "basketball-hoop")
    evidence = await cedict_provider.lookup(case.commercial_object, mode=LexicalEvidenceMode.EXACT)
    projection = build_compact_lexical_projection(evidence)

    rendered = render_candidate_input(
        subject_expression=case.subject_expression,
        commercial_object=case.commercial_object,
        lexical_projection=projection,
    )

    assert len(rendered.encode("utf-8")) <= 4_096
    assert str(cedict_provider._index_path) not in rendered
    assert "accepted_aliases" not in rendered
    assert "forbidden_exact_labels" not in rendered
    assert "review_rationale" not in rendered
    assert "篮球运动" not in rendered


@pytest.mark.asyncio
async def test_dictionary_arm_is_diagnostic_and_does_not_select(
    cedict_provider: CedictLexicalEvidenceProvider,
) -> None:
    evidence = await cedict_provider.lookup("篮球架", mode=LexicalEvidenceMode.EXACT)
    projection = build_compact_lexical_projection(evidence)

    record = build_dictionary_only_record(
        subject_expression="我是卖篮球架的",
        commercial_object="篮球架",
        lexical_projection=projection,
    )

    assert [candidate.label for candidate in record.candidates] == ["篮球架", "篮球"]
    assert record.selected_candidate_id is None


@pytest.mark.asyncio
async def test_preflight_checks_every_case_before_any_model_call(
    cedict_provider: CedictLexicalEvidenceProvider,
) -> None:
    report = await preflight_cases(load_held_out_cases().cases, provider=cedict_provider)

    assert report["case_count"] == 10
    assert report["all_within_budget"] is True
    assert report["max_input_bytes"] <= 4_096
    assert all(item["model_calls"] == 0 for item in report["cases"])


def test_scoring_keeps_recall_and_guard_noise_separate() -> None:
    basketball = next(case for case in load_held_out_cases().cases if case.case_id == "basketball-hoop")
    wife_cake = next(case for case in load_held_out_cases().cases if case.case_id == "wife-cake-lexicalized-guard")

    scores = (
        score_case(basketball, ("篮球架", "篮球")),
        score_case(wife_cake, ("老婆饼", "老婆")),
    )

    assert summarize_scores(scores) == {
        "case_count": 2,
        "transparent_case_count": 1,
        "transparent_candidate_recall": 1,
        "guard_case_count": 1,
        "guard_forbidden_hit": 1,
        "contract_success": 2,
    }


@pytest.mark.asyncio
async def test_model_call_is_counted_even_when_structured_parsing_fails() -> None:
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
