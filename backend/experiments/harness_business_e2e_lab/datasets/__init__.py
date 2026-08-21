from __future__ import annotations

from pathlib import Path

from experiments.harness_business_e2e_lab.contracts import FullAgentBusinessDataset

_DATASET_PATH = Path(__file__).with_name("held_out_v1.json")


def load_harness_business_e2e_cases() -> FullAgentBusinessDataset:
    return FullAgentBusinessDataset.model_validate_json(_DATASET_PATH.read_text(encoding="utf-8"))
