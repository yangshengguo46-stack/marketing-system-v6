from __future__ import annotations

import subprocess
import sys


def test_content_intelligence_imports_in_a_fresh_process_without_media_runtime_cycle() -> None:
    result = subprocess.run(
        (
            sys.executable,
            "-c",
            "from deerflow.content_intelligence import AnalysisFocus, ContentIntelligenceRequest, analyze_content_intelligence; print('ok')",
        ),
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ok"


def test_incubation_keeps_media_execution_exports_lazy_and_compatible() -> None:
    result = subprocess.run(
        (
            sys.executable,
            "-c",
            ("from deerflow.incubation import MediaKitLocalProductionOperation, execute_local_media_operation; print(MediaKitLocalProductionOperation.__name__, execute_local_media_operation.__name__)"),
        ),
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "MediaKitLocalProductionOperation execute_local_media_operation"
