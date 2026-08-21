from __future__ import annotations

import ast
from pathlib import Path

HARNESS_ROOT = Path(__file__).parents[1] / "packages" / "harness" / "deerflow"


def _source(relative_path: str) -> str:
    return (HARNESS_ROOT / relative_path).read_text(encoding="utf-8")


def test_content_tool_does_not_own_benchmark_selection_or_positioning_generation() -> None:
    source = _source("tools/builtins/content_intelligence_tool.py")
    tree = ast.parse(source)
    defined_functions = {node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}

    assert "_prepare_incubation_judgment" not in defined_functions
    assert "select_project_judgment_evidence" not in source
    assert "generate_incubation_judgment" not in source


def test_benchmark_collector_is_read_only_evidence_and_does_not_import_positioning() -> None:
    source = _source("tools/builtins/douyin_benchmark_tool.py")

    assert "IncubationJudgment" not in source
    assert "generate_incubation_judgment" not in source
    assert "analyze_content_intelligence" not in source


def test_topic_path_does_not_create_a_new_account_positioning_version() -> None:
    source = _source("tools/builtins/content_intelligence_tool.py")
    tree = ast.parse(source)
    explore = next(node for node in ast.walk(tree) if isinstance(node, ast.AsyncFunctionDef) and node.name == "explore_content_world_tool")
    calls = {node.func.id for node in ast.walk(explore) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}

    assert "prepare_account_strategy" not in calls
    assert "generate_incubation_judgment" not in calls


def test_lead_tool_catalog_does_not_expose_a_hidden_account_brain() -> None:
    source = _source("tools/tools.py")

    assert "develop_account_strategy_tool" not in source


def test_lead_prompt_does_not_force_an_account_cognition_pipeline() -> None:
    source = _source("agents/lead_agent/prompt.py")

    assert "<account_start_router>" not in source
    assert "first domain action" not in source
    assert "develop_account_strategy" not in source


def test_lead_prompt_converges_after_one_optional_content_map_call() -> None:
    source = _source("agents/lead_agent/prompt.py")
    normalized = " ".join(source.split())

    assert "Never call `explore_content_world` more than once in one user turn" in normalized
    assert "Analysis and `explore_content_world` are alternatives, not a required pair" in normalized


def test_account_direction_does_not_expand_into_an_unrequested_operations_plan() -> None:
    source = _source("agents/lead_agent/prompt.py")
    normalized = " ".join(source.split())

    assert "A broad account-starting question asks for a strategic direction" in normalized
    assert "Do not add calendars, cadence, time slots, ratios, ads, or 7/30-day plans unless requested" in normalized
    assert "Omit numeric precision unsupported by user facts or evidence" in normalized


def test_unfamiliar_term_verification_is_bounded_before_strategy_reasoning() -> None:
    source = _source("agents/lead_agent/prompt.py")
    normalized = " ".join(source.split())

    assert "use `verify_business_term` once" in normalized
    assert "this is not market or competitor research" in normalized


def test_agent_self_reference_routes_to_product_facts_without_a_fixed_workflow() -> None:
    source = _source("agents/lead_agent/prompt.py")
    normalized = " ".join(source.split())

    assert "When the user asks you to market yourself" in normalized
    assert "inspect_agent_product_profile" in normalized
    assert "do not reinterpret the Agent as the user's business" in normalized


def test_incubation_skill_discovery_happens_before_domain_questionnaires() -> None:
    source = _source("agents/lead_agent/prompt.py")
    normalized = " ".join(source.split())

    assert "matching `incubate-*` vertical Skill" in normalized
    assert "Inspect a matching Skill before domain-content questions" in normalized
    assert "A domain Skill supplies hypotheses, not the final route" in normalized


def test_one_clarification_is_not_a_multi_field_intake_form() -> None:
    source = _source("agents/lead_agent/prompt.py")
    normalized = " ".join(source.split())

    assert "exactly one decision question" in normalized
    assert "Never bundle optional profile fields into an intake form" in normalized


def test_account_routes_do_not_invent_specific_business_context_for_completeness() -> None:
    source = _source("agents/lead_agent/prompt.py")
    normalized = " ".join(source.split())

    assert "Do not introduce a specific occasion, audience subgroup, channel, format, or user resource" in normalized
    assert "State it as unknown or keep the route at the broader level" in normalized
    assert "Asserting an unstated capability and then softening it with uncertainty is still fabrication" in normalized
