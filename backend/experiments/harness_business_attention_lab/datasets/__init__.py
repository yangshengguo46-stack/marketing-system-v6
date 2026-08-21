from __future__ import annotations

import json
from pathlib import Path

from experiments.harness_business_attention_lab.contracts import BusinessAttentionDataset


def load_business_attention_cases() -> BusinessAttentionDataset:
    path = Path(__file__).with_name("held_out_v1.json")
    dataset = BusinessAttentionDataset.model_validate(json.loads(path.read_text(encoding="utf-8")))
    case_ids = [case.case_id for case in dataset.cases]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("business attention case ids must be unique")
    return dataset


__all__ = ["load_business_attention_cases"]
