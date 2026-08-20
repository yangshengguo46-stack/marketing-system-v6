from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from deerflow.content_intelligence.incubation_skill import (
    IncubationSkillProfileError,
    load_incubation_skill_profile,
)
from deerflow.skills.storage import get_or_new_skill_storage
from deerflow.skills.types import Skill, SkillCategory


def _skill(tmp_path: Path, *, name: str = "incubate-gift-human-relations", enabled: bool = True) -> Skill:
    skill_dir = tmp_path / "public" / name
    skill_dir.mkdir(parents=True)
    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text(
        f"---\nname: {name}\ndescription: test\n---\n\n# Test\n",
        encoding="utf-8",
    )
    return Skill(
        name=name,
        description="test",
        license=None,
        skill_dir=skill_dir,
        skill_file=skill_file,
        relative_path=Path(name),
        category=SkillCategory.PUBLIC,
        enabled=enabled,
    )


def _write_profile(skill: Skill, *, skill_name: str | None = None) -> None:
    references = skill.skill_dir / "references"
    references.mkdir()
    (references / "incubation-profile.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "skill_name": skill_name or skill.name,
                "domain": "礼赠与人情关系",
                "candidate_paths": [
                    {
                        "path": ["礼品", "送与收", "人情往来", "人与人之间的相处与人情世故"],
                        "root": "人与人之间的相处与人情世故",
                        "rationale": "礼品是送、收和回礼的关系媒介。",
                    }
                ],
                "default_root": "人与人之间的相处与人情世故",
                "branch_only_markers": [
                    {
                        "marker": "婚礼",
                        "reason": "只是礼赠与人情世界中的一个局部场景。",
                    }
                ],
                "do_not_assume": ["用户经营婚庆业务"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_loads_a_bounded_profile_only_from_the_selected_enabled_skill(tmp_path: Path) -> None:
    skill = _skill(tmp_path)
    _write_profile(skill)
    storage = SimpleNamespace(load_skills=lambda *, enabled_only: [skill] if enabled_only else [skill])

    profile = load_incubation_skill_profile(skill.name, storage=storage)

    assert profile.skill_name == skill.name
    assert profile.candidate_paths[0].root == "人与人之间的相处与人情世故"
    assert profile.default_root == "人与人之间的相处与人情世故"
    assert profile.branch_only_markers[0].marker == "婚礼"
    assert [item.marker for item in profile.inactive_map_branches("黄金礼品")] == ["婚礼"]
    assert profile.inactive_map_branches("婚礼伴手礼") == ()
    assert len(profile.content_sha256()) == 64


def test_rejects_a_profile_that_impersonates_another_skill(tmp_path: Path) -> None:
    skill = _skill(tmp_path)
    _write_profile(skill, skill_name="another-skill")
    storage = SimpleNamespace(load_skills=lambda *, enabled_only: [skill])

    with pytest.raises(IncubationSkillProfileError, match="does not match"):
        load_incubation_skill_profile(skill.name, storage=storage)


def test_rejects_a_profile_symlink_that_escapes_the_skill_package(tmp_path: Path) -> None:
    skill = _skill(tmp_path)
    outside = tmp_path / "outside.json"
    outside.write_text("{}", encoding="utf-8")
    references = skill.skill_dir / "references"
    references.mkdir()
    (references / "incubation-profile.json").symlink_to(outside)
    storage = SimpleNamespace(load_skills=lambda *, enabled_only: [skill])

    with pytest.raises(IncubationSkillProfileError, match="inside the selected skill"):
        load_incubation_skill_profile(skill.name, storage=storage)


def test_does_not_load_a_disabled_or_unknown_skill(tmp_path: Path) -> None:
    skill = _skill(tmp_path, enabled=False)
    _write_profile(skill)
    storage = SimpleNamespace(load_skills=lambda *, enabled_only: [])

    with pytest.raises(IncubationSkillProfileError, match="enabled incubation skill"):
        load_incubation_skill_profile(skill.name, storage=storage)


def test_rejects_a_non_incubation_skill_even_when_it_contains_a_profile(tmp_path: Path) -> None:
    skill = _skill(tmp_path, name="generic-writing")
    _write_profile(skill)
    storage = SimpleNamespace(load_skills=lambda *, enabled_only: [skill])

    with pytest.raises(IncubationSkillProfileError, match="incubate-"):
        load_incubation_skill_profile(skill.name, storage=storage)


def test_rejects_a_default_root_that_is_not_one_of_the_skill_candidates(tmp_path: Path) -> None:
    skill = _skill(tmp_path)
    _write_profile(skill)
    profile_path = skill.skill_dir / "references" / "incubation-profile.json"
    payload = json.loads(profile_path.read_text(encoding="utf-8"))
    payload["default_root"] = "另一个未声明的内容根"
    profile_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    storage = SimpleNamespace(load_skills=lambda *, enabled_only: [skill])

    with pytest.raises(IncubationSkillProfileError, match="invalid"):
        load_incubation_skill_profile(skill.name, storage=storage)


def test_bundled_gift_skill_is_discoverable_and_owns_its_profile() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    storage = get_or_new_skill_storage(skills_path=repo_root / "skills")
    skills = storage.load_skills(enabled_only=False)
    skill = next(item for item in skills if item.name == "incubate-gift-human-relations")
    enabled_storage = SimpleNamespace(load_skills=lambda *, enabled_only: [replace(skill, enabled=True)])

    profile = load_incubation_skill_profile(
        skill.name,
        storage=enabled_storage,
    )
    skill_body = skill.skill_file.read_text(encoding="utf-8")

    assert skill.category == SkillCategory.PUBLIC
    assert profile.skill_name == skill.name
    assert profile.candidate_paths[0].root == "人与人之间的相处与人情世故"
    assert profile.default_root == "人与人之间的相处与人情世故"
    assert (skill.skill_dir / "references" / "incubation-profile.json").is_file()
    assert 'incubation_skill="incubate-gift-human-relations"' in skill_body
    assert "does not choose the final account route" in skill_body
