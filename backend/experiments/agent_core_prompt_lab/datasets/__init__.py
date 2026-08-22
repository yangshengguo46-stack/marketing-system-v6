from __future__ import annotations

import json
from pathlib import Path

from experiments.agent_core_prompt_lab.contracts import AgentCoreDataset

_DATASET_PATH = Path(__file__).with_name("held_out_v3.json")


def load_agent_core_cases() -> AgentCoreDataset:
    return AgentCoreDataset.model_validate_json(_DATASET_PATH.read_text(encoding="utf-8"))


def dataset_hash() -> str:
    import hashlib

    payload = json.loads(_DATASET_PATH.read_text(encoding="utf-8"))
    rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()
