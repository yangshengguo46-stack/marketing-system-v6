from __future__ import annotations

import inspect
from datetime import UTC, datetime

import pytest

from deerflow.incubation.brief_runtime import build_minimal_incubation_brief
from deerflow.incubation.contracts import ProjectRef

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
    assert payload["unknowns"] == ["除用户逐字陈述的业务主体外，能力、资源、约束、目标、偏好、受众、变现方式和平台均未确认。"]


@pytest.mark.parametrize(
    ("user_text", "source_object"),
    (
        ("我是做黄金礼品的", "礼品与人情"),
        ("我是卖海鲜的", "海 鲜"),
        ("我是开火锅店的", ""),
        ("", "火锅"),
    ),
)
def test_rejects_non_verbatim_or_blank_inputs(user_text: str, source_object: str) -> None:
    with pytest.raises(ValueError):
        _build(verbatim_user_request=user_text, source_object=source_object)


def test_builder_has_no_model_questionnaire_or_guess_inputs() -> None:
    parameter_names = set(inspect.signature(build_minimal_incubation_brief).parameters)

    assert parameter_names == {
        "project",
        "verbatim_user_request",
        "source_object",
        "created_at",
        "source_thread_id",
        "source_run_id",
    }
