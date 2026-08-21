from __future__ import annotations

from experiments.harness_business_attention_lab.datasets import load_business_attention_cases
from experiments.harness_business_attention_lab.evaluation import (
    CaseComparison,
    decide_business_attention_promotion,
)
from experiments.harness_business_attention_lab.lab import (
    build_blind_pair,
    build_focused_business_prompt,
    build_minimal_host_prompt,
    build_prompt_manifest,
)


def test_dataset_keeps_known_cases_out_of_the_promotion_set() -> None:
    dataset = load_business_attention_cases()

    held_out = [case for case in dataset.cases if case.split == "held_out"]
    diagnostics = [case for case in dataset.cases if case.split == "diagnostic"]

    assert len(held_out) >= 6
    assert {case.case_id for case in diagnostics} == {
        "diagnostic-fruit-store",
        "diagnostic-golden-gift",
        "diagnostic-tiktok-guild",
    }
    assert len({case.case_id for case in dataset.cases}) == len(dataset.cases)
    assert all(case.prompt.strip() for case in dataset.cases)


def test_focused_business_prompt_is_thin_generic_and_non_procedural() -> None:
    prompt = build_focused_business_prompt()

    assert len(prompt.encode("utf-8")) <= 4_096
    assert "最终业务判断" in prompt
    assert "长期内容世界" in prompt
    assert "观众为什么会回来" in prompt
    assert "固定流程" not in prompt
    assert "第一步" not in prompt
    assert "第二步" not in prompt
    for leaked_case_term in ("黄金", "水果", "雪茄", "海鲜", "火锅", "婚礼", "TikTok"):
        assert leaked_case_term not in prompt


def test_minimal_host_prompt_preserves_authority_and_fact_boundary_without_business_method() -> None:
    prompt = build_minimal_host_prompt()

    assert "最终业务判断" in prompt
    assert "用户明确提供" in prompt
    assert "长期内容世界" not in prompt
    assert len(prompt.encode("utf-8")) < len(build_focused_business_prompt().encode("utf-8"))


def test_prompt_manifest_accounts_for_every_supplied_section_without_storing_text() -> None:
    manifest = build_prompt_manifest(
        arm="focused_business",
        sections=(
            ("host", "alpha"),
            ("business_attention", "中文"),
        ),
        user_prompt="我是做某项业务的，我该怎么起号？",
    )

    expected_bytes = len(b"alpha") + len("中文".encode()) + len("我是做某项业务的，我该怎么起号？".encode())
    assert manifest.total_bytes == expected_bytes
    assert manifest.section_bytes == {
        "host": len(b"alpha"),
        "business_attention": len("中文".encode()),
        "user_prompt": len("我是做某项业务的，我该怎么起号？".encode()),
    }
    assert manifest.section_hashes.keys() == manifest.section_bytes.keys()
    assert "alpha" not in manifest.model_dump_json()
    assert "某项业务" not in manifest.model_dump_json()


def test_blind_pair_hides_arm_names_and_is_stable_per_case() -> None:
    first = build_blind_pair(
        case_id="case-1",
        left_arm="current_full",
        left_text="current answer",
        right_arm="focused_business",
        right_text="focused answer",
    )
    second = build_blind_pair(
        case_id="case-1",
        left_arm="current_full",
        left_text="current answer",
        right_arm="focused_business",
        right_text="focused answer",
    )

    assert first == second
    assert {first.answer_a, first.answer_b} == {"current answer", "focused answer"}
    assert "current_full" not in first.judge_payload
    assert "focused_business" not in first.judge_payload
    assert set(first.arm_by_label) == {"A", "B"}


def test_promotion_requires_held_out_business_gain_without_fact_regression() -> None:
    passing = [
        CaseComparison(
            case_id=f"held-{index}",
            split="held_out",
            baseline_score=10,
            candidate_score=13,
            preferred_arm="focused_business",
            baseline_fact_boundary_pass=True,
            candidate_fact_boundary_pass=True,
        )
        for index in range(6)
    ]
    passing.append(
        CaseComparison(
            case_id="diagnostic-golden-gift",
            split="diagnostic",
            baseline_score=5,
            candidate_score=15,
            preferred_arm="focused_business",
            baseline_fact_boundary_pass=False,
            candidate_fact_boundary_pass=True,
        )
    )

    decision = decide_business_attention_promotion(passing)

    assert decision.promote is True
    assert decision.held_out_case_count == 6
    assert decision.candidate_wins == 6

    failing = list(passing)
    failing[0] = failing[0].model_copy(update={"candidate_fact_boundary_pass": False})
    failed_decision = decide_business_attention_promotion(failing)

    assert failed_decision.promote is False
    assert "fact_boundary_regression" in failed_decision.reasons
