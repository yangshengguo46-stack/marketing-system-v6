from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import SystemMessage

from experiments.agent_core_prompt_lab import run as run_module
from experiments.agent_core_prompt_lab.datasets import load_agent_core_cases
from experiments.agent_core_prompt_lab.middleware import AgentCoreProbeMiddleware
from experiments.agent_core_prompt_lab.run import DEFAULT_MODELS, preflight

_A138_LEGACY_PROMPT = """<role>
You are {agent_name}, a content incubation and new-media operations agent built on DeerFlow.
</role>
<account_incubation>
Offer a few coherent routes and recommend one without adopting it.
</account_incubation>
<response_style>
Give clear advice.
</response_style>"""


def _request(system_text: str):
    request = MagicMock()
    request.system_message = SystemMessage(content=system_text)
    request.messages = []
    request.tools = [MagicMock(name="read_file"), MagicMock(name="web_search")]
    request.tools[0].name = "read_file"
    request.tools[1].name = "web_search"

    def override(**updates):
        clone = _request(system_text)
        clone.system_message = updates.get("system_message", request.system_message)
        clone.messages = updates.get("messages", request.messages)
        clone.tools = updates.get("tools", request.tools)
        return clone

    request.override = override
    return request


def test_dataset_freezes_six_distinct_agent_work_classes() -> None:
    dataset = load_agent_core_cases()

    assert dataset.status == "frozen_before_live_run"
    assert {case.task_class for case in dataset.cases} == {
        "greeting",
        "research",
        "account_strategy",
        "creative_delivery",
        "reversible_execution",
        "irreversible_external_action",
    }
    assert len(dataset.cases) == 6
    assert len({case.case_id for case in dataset.cases}) == 6
    for case in dataset.cases:
        assert all(term not in case.prompt for term in ("黄金礼品", "TikTok公会", "水果店"))


def test_probe_replaces_only_candidate_system_contract_and_preserves_tools() -> None:
    baseline = AgentCoreProbeMiddleware(arm="current_full")
    candidate = AgentCoreProbeMiddleware(arm="agent_core_candidate")
    baseline_seen = []
    candidate_seen = []

    baseline.wrap_model_call(_request(_A138_LEGACY_PROMPT), lambda req: baseline_seen.append(req) or "ok")
    candidate.wrap_model_call(_request(_A138_LEGACY_PROMPT), lambda req: candidate_seen.append(req) or "ok")

    baseline_observation = baseline.observations[0]
    candidate_observation = candidate.observations[0]
    assert baseline_seen[0].system_message.content == _A138_LEGACY_PROMPT
    assert "<work_ownership>" in candidate_seen[0].system_message.content
    assert "recommend one without adopting it" not in candidate_seen[0].system_message.content
    assert baseline_observation.base_system_hash == candidate_observation.base_system_hash
    assert baseline_observation.final_system_hash != candidate_observation.final_system_hash
    assert baseline_observation.tool_names == candidate_observation.tool_names
    assert baseline_observation.tool_schema_hash == candidate_observation.tool_schema_hash
    assert candidate_observation.final_system_bytes != baseline_observation.final_system_bytes


def test_preflight_rejects_rerunning_consumed_a138_against_the_new_kernel() -> None:
    assert len(DEFAULT_MODELS) >= 3
    with pytest.raises(RuntimeError, match="retired comparison"):
        preflight()


def test_probe_fails_closed_when_experiment_model_call_budget_is_exceeded() -> None:
    middleware = AgentCoreProbeMiddleware(arm="agent_core_candidate", max_model_calls=2)

    middleware.wrap_model_call(_request(_A138_LEGACY_PROMPT), lambda req: "first")
    middleware.wrap_model_call(_request(_A138_LEGACY_PROMPT), lambda req: "second")
    with pytest.raises(RuntimeError, match="A138 model call budget exceeded"):
        middleware.wrap_model_call(_request(_A138_LEGACY_PROMPT), lambda req: "third")


def test_full_runner_creates_fresh_clients_for_every_case(monkeypatch) -> None:
    cases = (
        SimpleNamespace(case_id="one", task_class="greeting", prompt="hi"),
        SimpleNamespace(case_id="two", task_class="research", prompt="read"),
    )
    create_calls = []

    monkeypatch.setattr(run_module, "preflight", lambda: {"case_count": 2})
    monkeypatch.setattr(
        run_module,
        "load_agent_core_cases",
        lambda: SimpleNamespace(dataset_id="test", cases=cases),
    )
    monkeypatch.setattr(run_module, "_git_commit", lambda: "commit")
    monkeypatch.setattr(run_module, "_config_hash", lambda path: None)
    monkeypatch.setattr(
        run_module,
        "_create_clients",
        lambda model: (
            create_calls.append(model)
            or (
                {"current_full": object(), "agent_core_candidate": object()},
                {"current_full": object(), "agent_core_candidate": object()},
            )
        ),
    )
    monkeypatch.setattr(
        run_module,
        "_run_arm",
        lambda **kwargs: {
            "status": "succeeded",
            "valid": True,
            "request_observations": [],
            "usage": {"total_tokens": 0},
            "model_request_count": 0,
            "tool_call_count": 0,
        },
    )

    run_module.run_experiment(model_names=("model",))

    assert create_calls == ["model", "model"]
