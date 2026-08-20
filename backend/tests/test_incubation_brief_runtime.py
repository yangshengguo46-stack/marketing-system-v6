from __future__ import annotations

import inspect
from datetime import UTC, datetime

import pytest

import deerflow.incubation.brief_runtime as brief_runtime
from deerflow.incubation.brief_runtime import build_minimal_incubation_brief
from deerflow.incubation.contracts import ProjectRef
from deerflow.incubation.judgment import IncubationBrief

NOW = datetime(2026, 8, 17, 18, 0, tzinfo=UTC)
PROJECT = ProjectRef(owner_user_id="user-1", project_id="golden-gift")


def _build(**overrides: object):
    arguments = {
        "project": PROJECT,
        "verbatim_user_request": "我是做黄金礼品的，我要怎么起号？",
        "source_object": "黄金礼品",
        "created_at": NOW,
        "source_thread_id": "thread-1",
        "source_run_id": "run-1",
    }
    arguments.update(overrides)
    return build_minimal_incubation_brief(**arguments)


def test_builds_only_one_verbatim_user_stated_business_fact() -> None:
    artifact = _build()

    assert artifact.artifact_type == "incubation_brief"
    assert artifact.project == PROJECT
    assert artifact.parents == ()
    assert artifact.source_thread_id == "thread-1"
    assert artifact.source_run_id == "run-1"
    assert artifact.payload["subject_expression"] == "我是做黄金礼品的，我要怎么起号？"
    assert artifact.payload["business_facts"] == [
        {
            "statement": "黄金礼品",
            "provenance": "user_stated",
            "source_quote": "黄金礼品",
            "basis_artifact_ids": [],
        }
    ]


def test_leaves_unstated_facts_empty_and_explicitly_unknown() -> None:
    payload = _build().payload

    for field in ("capabilities", "resources", "constraints", "goals", "preferences"):
        assert payload[field] == []
    assert payload["prohibited_assumptions"] == ["用户的业务身份本身不能证明其拥有相关专业能力、经验、客户案例、素材、供应链、销售渠道、出镜或制作能力。"]
    assert payload["unknowns"] == ["除用户逐字陈述的业务主体外，能力、资源、约束、目标、偏好、受众、变现方式和平台均未确认。"]


def test_seals_skill_supplied_prohibited_assumptions_without_turning_them_into_facts() -> None:
    payload = _build(
        prohibited_assumptions=(
            "用户拥有大量真实客户案例",
            "用户拥有大量真实客户案例",
            "用户具有真人出镜能力",
        ),
        excluded_content_branches=("婚礼", "婚礼", "彩礼"),
    ).payload

    assert payload["prohibited_assumptions"] == [
        "用户的业务身份本身不能证明其拥有相关专业能力、经验、客户案例、素材、供应链、销售渠道、出镜或制作能力。",
        "用户拥有大量真实客户案例",
        "用户具有真人出镜能力",
    ]
    assert all(assumption not in {fact["statement"] for fact in payload[field]} for assumption in payload["prohibited_assumptions"] for field in ("business_facts", "capabilities", "resources", "constraints", "goals", "preferences"))
    assert payload["excluded_content_branches"] == ["婚礼", "彩礼"]


@pytest.mark.parametrize(
    ("user_text", "source_object"),
    (
        ("我是做黄金礼品的", "礼品与人情"),
        ("我是卖海鲜的", "海 鲜"),
        ("我是开火锅店的", ""),
        ("", "火锅"),
        ("   ", "火锅"),
        ("我是开火锅店的", "\t\n"),
    ),
)
def test_rejects_non_verbatim_or_blank_inputs(user_text: str, source_object: str) -> None:
    with pytest.raises(ValueError):
        _build(verbatim_user_request=user_text, source_object=source_object)


def test_builder_has_no_model_questionnaire_or_guess_inputs() -> None:
    parameter_names = set(inspect.signature(build_minimal_incubation_brief).parameters)
    module_source = inspect.getsource(brief_runtime).casefold()

    assert inspect.iscoroutinefunction(build_minimal_incubation_brief) is False
    assert parameter_names == {
        "project",
        "verbatim_user_request",
        "source_object",
        "created_at",
        "source_thread_id",
        "source_run_id",
        "prohibited_assumptions",
        "excluded_content_branches",
    }
    assert "langchain" not in module_source
    assert "questionnaire" not in module_source


def test_delegates_artifact_creation_to_seal_incubation_brief(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel = object()
    captured: dict[str, object] = {}

    def fake_seal_incubation_brief(**kwargs):
        captured.update(kwargs)
        return sentinel

    monkeypatch.setattr(
        brief_runtime,
        "seal_incubation_brief",
        fake_seal_incubation_brief,
    )

    result = _build()

    assert result is sentinel
    assert captured["project"] == PROJECT
    assert isinstance(captured["brief"], IncubationBrief)
    assert captured["brief"].business_facts[0].statement == "黄金礼品"
