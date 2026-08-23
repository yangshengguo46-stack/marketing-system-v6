from __future__ import annotations

import json
from pathlib import Path

from deerflow.config.extensions_config import ExtensionsConfig, SkillStateConfig

ROOT = Path(__file__).resolve().parents[2]


def test_project_routes_video_work_to_the_project_native_skill() -> None:
    config = json.loads((ROOT / "extensions_config.example.json").read_text(encoding="utf-8"))

    assert config["skills"]["marketing-video-production"]["enabled"] is True
    assert config["skills"]["video-generation"]["enabled"] is False


def test_legacy_video_skill_is_a_non_executable_migration_notice() -> None:
    skill_text = (ROOT / "skills" / "public" / "video-generation" / "SKILL.md").read_text(encoding="utf-8")

    assert "Disabled legacy compatibility package" in skill_text
    assert "Do not run `scripts/generate.py` on a user's behalf" in skill_text
    assert "marketing-video-production" in skill_text


def test_legacy_video_skill_is_default_disabled_for_existing_operator_configs() -> None:
    config = ExtensionsConfig()

    assert config.is_skill_enabled("video-generation", "public") is False
    assert config.is_skill_enabled("marketing-video-production", "public") is True
    assert config.is_skill_enabled("unrelated-public-skill", "public") is True

    opted_in = ExtensionsConfig(skills={"video-generation": SkillStateConfig(enabled=True)})
    assert opted_in.is_skill_enabled("video-generation", "public") is True
