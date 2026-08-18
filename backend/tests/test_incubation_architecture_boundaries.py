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
