from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from deerflow.content_intelligence.incubation_skill import (
    IncubationEvalManifest,
    IncubationPackageAcceptanceReceipt,
    IncubationSkillProfile,
    IncubationSkillProfileError,
    IncubationTriggerEvalCase,
    incubation_activation_package_sha256,
    load_incubation_skill_profile,
)
from deerflow.skills.frontmatter import split_skill_markdown
from deerflow.skills.parser import parse_skill_file
from deerflow.skills.storage import get_or_new_skill_storage
from deerflow.skills.types import Skill, SkillCategory


def _skill(tmp_path: Path, *, name: str = "incubate-gift-human-relations", enabled: bool = True) -> Skill:
    skill_dir = tmp_path / "public" / name
    skill_dir.mkdir(parents=True)
    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text(
        (f'---\nname: {name}\ndescription: test\nlicense: MIT\nmetadata:\n  version: "1.0.0"\n  lifecycle: active\n---\n\n# Test\n'),
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
    profile_payload = {
        "schema_version": 3,
        "skill_name": skill_name or skill.name,
        "profile_version": "1.0.0",
        "lifecycle_status": "active",
        "source_refs": ["docs/content-intelligence-v6/audits/A116-vertical-incubation-skills.md"],
        "applies_to": ["礼品、礼物、伴手礼或馈赠是用户实际经营对象"],
        "does_not_apply_to": ["黄金投资、普通珠宝或婚庆业务，但礼赠不是经营对象"],
        "selection_principles": ["完整礼品对象要与送、收、回和关系世界比较。"],
        "domain": "礼赠与人情关系",
        "candidate_paths": [
            {
                "path": ["礼品", "送与收", "人情往来", "人与人之间的相处与人情世故"],
                "root": "人与人之间的相处与人情世故",
                "rationale": "礼品是送、收和回礼的关系媒介。",
            }
        ],
        "preferred_root_candidate": "人与人之间的相处与人情世故",
        "supporting_branch_hints": [
            {
                "branch_id": "wedding-gifting",
                "label": "婚礼与婚嫁馈赠",
                "suggested_scope": "supporting_branch",
                "reason": "只是礼赠与人情世界中的一个局部场景。",
            }
        ],
    }
    (references / "incubation-profile.json").write_text(
        json.dumps(profile_payload, ensure_ascii=False),
        encoding="utf-8",
    )
    profile = IncubationSkillProfile.model_validate(profile_payload)
    evals = skill.skill_dir / "evals"
    evals.mkdir()
    evidence_dir = evals / "evidence"
    evidence_dir.mkdir()
    evidence_path = evidence_dir / "synthetic-acceptance.json"
    evidence_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "kind": "synthetic-test-fixture",
                "observation": "All declared synthetic cases passed their fixture assertions.",
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    evidence_sha256 = hashlib.sha256(evidence_path.read_bytes()).hexdigest()
    eval_payload = {
        "schema_version": 1,
        "skill_name": skill_name or skill.name,
        "profile_version": "1.0.0",
        "acceptance": {
            "status": "passed",
            "profile_sha256": profile.content_sha256(),
            "package_sha256": "0" * 64,
            "evidence_ref": "acceptance.json",
        },
        "evals": [
            {
                "case_id": "trigger",
                "case_kind": "trigger",
                "prompt": "我是做礼品的",
                "expected_output": "加载礼赠 Skill",
            },
            {
                "case_id": "anti",
                "case_kind": "anti_trigger",
                "prompt": "我是做珠宝的",
                "expected_output": "不加载礼赠 Skill",
            },
            {
                "case_id": "behavior",
                "case_kind": "behavior",
                "prompt": "我是做黄金礼品的",
                "expected_output": "内容根到达人情关系",
            },
            {
                "case_id": "held-out",
                "case_kind": "held_out",
                "prompt": "我是做退休纪念礼的",
                "expected_output": "识别纪念、感谢与关系确认",
            },
        ],
    }
    trigger_payload = [
        {"query": "我是做礼品的", "should_trigger": True, "rationale": "礼品是经营对象。"},
        {"query": "我是做珠宝的", "should_trigger": False, "rationale": "礼赠不是经营对象。"},
    ]
    receipt_payload = {
        "schema_version": 1,
        "skill_name": skill_name or skill.name,
        "profile_version": "1.0.0",
        "package_sha256": "0" * 64,
        "decision": "active",
        "evaluated_at": "2026-08-20T00:00:00Z",
        "source_refs": [
            {
                "evidence_id": "synthetic-evidence",
                "path": "evidence/synthetic-acceptance.json",
                "sha256": evidence_sha256,
            }
        ],
        "case_results": [
            {
                "case_id": case["case_id"],
                "outcome": "passed",
                "observation": "Synthetic package fixture passed its declared contract.",
                "evidence_ref": "synthetic-evidence",
            }
            for case in eval_payload["evals"]
        ],
        "limitations": ["Synthetic fixture only."],
    }
    manifest = IncubationEvalManifest.model_validate(eval_payload)
    trigger_evals = tuple(IncubationTriggerEvalCase.model_validate(case) for case in trigger_payload)
    receipt = IncubationPackageAcceptanceReceipt.model_validate(receipt_payload)
    package_sha256 = incubation_activation_package_sha256(
        skill_markdown=skill.skill_file.read_text(encoding="utf-8"),
        profile=profile,
        eval_manifest=manifest,
        trigger_evals=trigger_evals,
        acceptance_receipt=receipt,
    )
    eval_payload["acceptance"]["package_sha256"] = package_sha256
    receipt_payload["package_sha256"] = package_sha256
    (evals / "evals.json").write_text(
        json.dumps(eval_payload, ensure_ascii=False),
        encoding="utf-8",
    )
    (evals / "trigger_eval_set.json").write_text(json.dumps(trigger_payload, ensure_ascii=False), encoding="utf-8")
    (evals / "acceptance.json").write_text(
        json.dumps(receipt_payload, ensure_ascii=False),
        encoding="utf-8",
    )


def test_loads_a_bounded_profile_only_from_the_selected_enabled_skill(tmp_path: Path) -> None:
    skill = _skill(tmp_path)
    _write_profile(skill)
    storage = SimpleNamespace(load_skills=lambda *, enabled_only: [skill] if enabled_only else [skill])

    profile = load_incubation_skill_profile(skill.name, storage=storage)

    assert profile.skill_name == skill.name
    assert profile.profile_version == "1.0.0"
    assert profile.lifecycle_status == "active"
    assert profile.source_refs == ("docs/content-intelligence-v6/audits/A116-vertical-incubation-skills.md",)
    assert profile.candidate_paths[0].root == "人与人之间的相处与人情世故"
    assert profile.preferred_root_candidate == "人与人之间的相处与人情世故"
    assert profile.supporting_branch_hints[0].branch_id == "wedding-gifting"
    assert profile.supporting_branch_hints[0].label == "婚礼与婚嫁馈赠"
    assert not hasattr(profile, "inactive_map_branches")
    assert len(profile.content_sha256()) == 64
    assert "profile_version" not in profile.decision_projection()


@pytest.mark.parametrize("status", ["candidate", "shadow", "contested", "superseded", "retired"])
def test_generic_skill_parser_rejects_non_active_incubation_packages(tmp_path: Path, status: str) -> None:
    skill = _skill(tmp_path)
    skill.skill_file.write_text(
        skill.skill_file.read_text(encoding="utf-8").replace("lifecycle: active", f"lifecycle: {status}"),
        encoding="utf-8",
    )

    assert parse_skill_file(skill.skill_file, SkillCategory.PUBLIC) is None


def test_rejects_a_profile_that_impersonates_another_skill(tmp_path: Path) -> None:
    skill = _skill(tmp_path)
    _write_profile(skill, skill_name="another-skill")
    storage = SimpleNamespace(load_skills=lambda *, enabled_only: [skill])

    with pytest.raises(IncubationSkillProfileError, match="does not match"):
        load_incubation_skill_profile(skill.name, storage=storage)


def test_rejects_unsupported_profile_schema_with_a_migration_error(tmp_path: Path) -> None:
    skill = _skill(tmp_path)
    _write_profile(skill)
    profile_path = skill.skill_dir / "references" / "incubation-profile.json"
    payload = json.loads(profile_path.read_text(encoding="utf-8"))
    payload["schema_version"] = 1
    profile_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    storage = SimpleNamespace(load_skills=lambda *, enabled_only: [skill])

    with pytest.raises(IncubationSkillProfileError, match="schema_version.*3"):
        load_incubation_skill_profile(skill.name, storage=storage)


def test_wraps_unreadable_skill_metadata_in_the_domain_error(tmp_path: Path) -> None:
    skill = _skill(tmp_path)
    _write_profile(skill)
    skill.skill_file.write_bytes(b"\xff")
    storage = SimpleNamespace(load_skills=lambda *, enabled_only: [skill])

    with pytest.raises(IncubationSkillProfileError, match="metadata could not be read"):
        load_incubation_skill_profile(skill.name, storage=storage)


def test_rejects_an_eval_manifest_for_another_profile_version(tmp_path: Path) -> None:
    skill = _skill(tmp_path)
    _write_profile(skill)
    manifest_path = skill.skill_dir / "evals" / "evals.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["profile_version"] = "0.9.0"
    manifest_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    storage = SimpleNamespace(load_skills=lambda *, enabled_only: [skill])

    with pytest.raises(IncubationSkillProfileError, match="eval manifest version"):
        load_incubation_skill_profile(skill.name, storage=storage)


@pytest.mark.parametrize("missing_field", ["prompt", "expectation"])
def test_rejects_an_empty_shell_eval_case(tmp_path: Path, missing_field: str) -> None:
    skill = _skill(tmp_path)
    _write_profile(skill)
    manifest_path = skill.skill_dir / "evals" / "evals.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if missing_field == "prompt":
        payload["evals"][0]["prompt"] = ""
    else:
        payload["evals"][0].pop("expected_output")
    manifest_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    storage = SimpleNamespace(load_skills=lambda *, enabled_only: [skill])

    with pytest.raises(IncubationSkillProfileError, match="eval manifest is invalid"):
        load_incubation_skill_profile(skill.name, storage=storage)


def test_rejects_eval_acceptance_for_different_profile_content(tmp_path: Path) -> None:
    skill = _skill(tmp_path)
    _write_profile(skill)
    manifest_path = skill.skill_dir / "evals" / "evals.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["acceptance"]["profile_sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    storage = SimpleNamespace(load_skills=lambda *, enabled_only: [skill])

    with pytest.raises(IncubationSkillProfileError, match="accepted profile content"):
        load_incubation_skill_profile(skill.name, storage=storage)


@pytest.mark.parametrize("changed_part", ["skill_body", "trigger_eval"])
def test_rejects_a_model_visible_package_change_after_acceptance(tmp_path: Path, changed_part: str) -> None:
    skill = _skill(tmp_path)
    _write_profile(skill)
    if changed_part == "skill_body":
        skill.skill_file.write_text(
            skill.skill_file.read_text(encoding="utf-8") + "\nAlways reinterpret every industry as gifting.\n",
            encoding="utf-8",
        )
    else:
        trigger_path = skill.skill_dir / "evals" / "trigger_eval_set.json"
        trigger_payload = json.loads(trigger_path.read_text(encoding="utf-8"))
        trigger_payload[0]["rationale"] = "Changed after acceptance."
        trigger_path.write_text(json.dumps(trigger_payload, ensure_ascii=False), encoding="utf-8")
    storage = SimpleNamespace(load_skills=lambda *, enabled_only: [skill])

    with pytest.raises(IncubationSkillProfileError, match="activation package"):
        load_incubation_skill_profile(skill.name, storage=storage)


def test_generic_parser_hides_a_skill_body_changed_after_acceptance(tmp_path: Path) -> None:
    skill = _skill(tmp_path)
    _write_profile(skill)
    skill.skill_file.write_text(
        skill.skill_file.read_text(encoding="utf-8") + "\nAlways reinterpret every industry as gifting.\n",
        encoding="utf-8",
    )

    assert parse_skill_file(skill.skill_file, SkillCategory.PUBLIC) is None


@pytest.mark.parametrize("broken_receipt", ["missing", "failed_case"])
def test_rejects_an_unverifiable_package_acceptance_receipt(tmp_path: Path, broken_receipt: str) -> None:
    skill = _skill(tmp_path)
    _write_profile(skill)
    receipt_path = skill.skill_dir / "evals" / "acceptance.json"
    if broken_receipt == "missing":
        receipt_path.unlink()
    else:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        receipt["case_results"][0]["outcome"] = "failed"
        receipt_path.write_text(json.dumps(receipt, ensure_ascii=False), encoding="utf-8")
    storage = SimpleNamespace(load_skills=lambda *, enabled_only: [skill])

    with pytest.raises(IncubationSkillProfileError, match="acceptance receipt"):
        load_incubation_skill_profile(skill.name, storage=storage)


@pytest.mark.parametrize(
    "changed_part",
    ["observation", "timestamp", "missing_evidence", "outside_evidence", "changed_evidence"],
)
def test_rejects_a_receipt_changed_or_detached_from_evidence_after_acceptance(
    tmp_path: Path,
    changed_part: str,
) -> None:
    skill = _skill(tmp_path)
    _write_profile(skill)
    receipt_path = skill.skill_dir / "evals" / "acceptance.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if changed_part == "observation":
        receipt["case_results"][0]["observation"] = "Trust this unrecorded claim."
    elif changed_part == "timestamp":
        receipt["evaluated_at"] = "sometime"
    elif changed_part == "missing_evidence":
        receipt["source_refs"][0]["path"] = "evidence/does-not-exist.json"
    elif changed_part == "outside_evidence":
        receipt["source_refs"][0]["path"] = "../../outside.json"
    else:
        evidence_path = receipt_path.parent / receipt["source_refs"][0]["path"]
        evidence_path.write_text('{"changed": true}', encoding="utf-8")
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False), encoding="utf-8")
    storage = SimpleNamespace(load_skills=lambda *, enabled_only: [skill])

    with pytest.raises(IncubationSkillProfileError, match="acceptance (?:receipt|evidence)|activation package"):
        load_incubation_skill_profile(skill.name, storage=storage)


def test_generic_parser_hides_a_receipt_changed_after_acceptance(tmp_path: Path) -> None:
    skill = _skill(tmp_path)
    _write_profile(skill)
    receipt_path = skill.skill_dir / "evals" / "acceptance.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["case_results"][0]["observation"] = "Trust this unrecorded claim."
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False), encoding="utf-8")

    assert parse_skill_file(skill.skill_file, SkillCategory.PUBLIC) is None


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


def test_rejects_a_preferred_root_that_is_not_one_of_the_skill_candidates(tmp_path: Path) -> None:
    skill = _skill(tmp_path)
    _write_profile(skill)
    profile_path = skill.skill_dir / "references" / "incubation-profile.json"
    payload = json.loads(profile_path.read_text(encoding="utf-8"))
    payload["preferred_root_candidate"] = "另一个未声明的内容根"
    profile_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    storage = SimpleNamespace(load_skills=lambda *, enabled_only: [skill])

    with pytest.raises(IncubationSkillProfileError, match="invalid"):
        load_incubation_skill_profile(skill.name, storage=storage)


@pytest.mark.parametrize("status", ["candidate", "shadow", "contested", "superseded", "retired"])
def test_runtime_rejects_a_profile_that_is_not_active(tmp_path: Path, status: str) -> None:
    skill = _skill(tmp_path)
    _write_profile(skill)
    profile_path = skill.skill_dir / "references" / "incubation-profile.json"
    payload = json.loads(profile_path.read_text(encoding="utf-8"))
    payload["lifecycle_status"] = status
    profile_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    storage = SimpleNamespace(load_skills=lambda *, enabled_only: [skill])

    with pytest.raises(IncubationSkillProfileError, match="not active"):
        load_incubation_skill_profile(skill.name, storage=storage)


def test_rejects_overlapping_apply_and_exclusion_contracts(tmp_path: Path) -> None:
    skill = _skill(tmp_path)
    _write_profile(skill)
    profile_path = skill.skill_dir / "references" / "incubation-profile.json"
    payload = json.loads(profile_path.read_text(encoding="utf-8"))
    payload["does_not_apply_to"] = payload["applies_to"]
    profile_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    storage = SimpleNamespace(load_skills=lambda *, enabled_only: [skill])

    with pytest.raises(IncubationSkillProfileError, match="invalid"):
        load_incubation_skill_profile(skill.name, storage=storage)


def test_profile_schema_supports_an_active_principle_only_profile_without_static_roots(tmp_path: Path) -> None:
    skill = _skill(tmp_path, name="incubate-food-world")
    _write_profile(skill, skill_name=skill.name)
    profile_path = skill.skill_dir / "references" / "incubation-profile.json"
    payload = json.loads(profile_path.read_text(encoding="utf-8"))
    payload["candidate_paths"] = []
    payload["preferred_root_candidate"] = None
    payload["selection_principles"] = [
        "完整食物品类可以保持为根；中间载体应与它最终完成的食物对象比较。",
        "不要把商品、食用场景和社交功能拼成混合内容根。",
    ]
    profile = IncubationSkillProfile.model_validate(payload)

    assert profile.candidate_paths == ()
    assert profile.preferred_root_candidate is None
    assert profile.decision_projection()["selection_principles"] == payload["selection_principles"]


def test_supporting_branch_hints_are_advice_and_never_classify_user_text(tmp_path: Path) -> None:
    skill = _skill(tmp_path)
    _write_profile(skill)
    storage = SimpleNamespace(load_skills=lambda *, enabled_only: [skill])
    profile = load_incubation_skill_profile(skill.name, storage=storage)

    projection = profile.decision_projection()
    assert set(projection) == {
        "domain",
        "candidate_paths",
        "selection_principles",
        "preferred_root_candidate",
        "supporting_branch_hints",
    }
    assert "incubation_skill" not in projection
    assert "profile_version" not in projection
    assert "profile_sha256" not in projection
    assert "applies_to" not in projection
    assert "does_not_apply_to" not in projection
    assert "do_not_assume" not in projection
    assert "source_refs" not in projection
    assert "lifecycle_status" not in projection
    assert projection["supporting_branch_hints"] == [
        {
            "branch_id": "wedding-gifting",
            "label": "婚礼与婚嫁馈赠",
            "suggested_scope": "supporting_branch",
            "reason": "只是礼赠与人情世界中的一个局部场景。",
        }
    ]
    assert "branch_only_markers" not in projection
    assert not hasattr(profile, "is_branch_only")
    assert not hasattr(profile, "inactive_map_branches")


def test_vertical_profile_cannot_inject_fact_denials_into_the_project_brief(tmp_path: Path) -> None:
    skill = _skill(tmp_path)
    _write_profile(skill)
    profile_path = skill.skill_dir / "references" / "incubation-profile.json"
    payload = json.loads(profile_path.read_text(encoding="utf-8"))
    payload["do_not_assume"] = ["用户经营婚庆或婚嫁业务"]
    profile_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    storage = SimpleNamespace(load_skills=lambda *, enabled_only: [skill])

    with pytest.raises(IncubationSkillProfileError, match="invalid"):
        load_incubation_skill_profile(skill.name, storage=storage)


@pytest.mark.parametrize(
    "broken_part",
    [
        "profile_lifecycle",
        "profile_version",
        "invalid_profile",
        "duplicate_eval_case_id",
        "missing_eval",
        "missing_receipt",
        "failed_receipt",
    ],
)
def test_generic_parser_rejects_a_cross_file_activation_mismatch(tmp_path: Path, broken_part: str) -> None:
    skill = _skill(tmp_path)
    _write_profile(skill)
    profile_path = skill.skill_dir / "references" / "incubation-profile.json"
    if broken_part in {"profile_lifecycle", "profile_version", "invalid_profile"}:
        payload = json.loads(profile_path.read_text(encoding="utf-8"))
        if broken_part == "profile_lifecycle":
            payload["lifecycle_status"] = "shadow"
        elif broken_part == "profile_version":
            payload["profile_version"] = "0.9.0"
        else:
            payload["does_not_apply_to"] = payload["applies_to"]
        profile_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    elif broken_part == "duplicate_eval_case_id":
        manifest_path = skill.skill_dir / "evals" / "evals.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["evals"][1]["case_id"] = manifest["evals"][0]["case_id"]
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    elif broken_part == "missing_eval":
        (skill.skill_dir / "evals" / "evals.json").unlink()
    elif broken_part == "missing_receipt":
        (skill.skill_dir / "evals" / "acceptance.json").unlink()
    else:
        receipt_path = skill.skill_dir / "evals" / "acceptance.json"
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        receipt["case_results"][0]["outcome"] = "failed"
        receipt_path.write_text(json.dumps(receipt, ensure_ascii=False), encoding="utf-8")

    assert parse_skill_file(skill.skill_file, SkillCategory.PUBLIC) is None


def test_rejects_a_profile_without_paths_or_selection_principles(tmp_path: Path) -> None:
    skill = _skill(tmp_path)
    _write_profile(skill)
    profile_path = skill.skill_dir / "references" / "incubation-profile.json"
    payload = json.loads(profile_path.read_text(encoding="utf-8"))
    payload["candidate_paths"] = []
    payload["preferred_root_candidate"] = None
    payload["selection_principles"] = []
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
    parts, error = split_skill_markdown(skill_body)
    eval_manifest = json.loads((skill.skill_dir / "evals" / "evals.json").read_text(encoding="utf-8"))
    trigger_manifest = json.loads((skill.skill_dir / "evals" / "trigger_eval_set.json").read_text(encoding="utf-8"))

    assert error is None
    assert parts is not None
    assert skill.category == SkillCategory.PUBLIC
    assert parts.metadata["license"] == "MIT"
    assert parts.metadata["metadata"]["version"] == "1.1.0"
    assert parts.metadata["metadata"]["lifecycle"] == "active"
    assert profile.skill_name == skill.name
    assert profile.schema_version == 3
    assert profile.profile_version == "1.1.0"
    assert profile.lifecycle_status == "active"
    assert profile.candidate_paths[0].root == "人与人之间的相处与人情世故"
    assert profile.preferred_root_candidate == "人与人之间的相处与人情世故"
    assert profile.supporting_branch_hints[0].suggested_scope == "supporting_branch"
    assert (skill.skill_dir / "references" / "incubation-profile.json").is_file()
    assert 'incubation_skill="incubate-gift-human-relations"' in skill_body
    assert "does not choose the root or final account route" in skill_body
    assert eval_manifest["skill_name"] == skill.name
    case_kinds = {case["case_kind"] for case in eval_manifest["evals"]}
    assert case_kinds == {"trigger", "anti_trigger", "behavior", "held_out"}
    assert sum(case["case_kind"] == "trigger" for case in eval_manifest["evals"]) >= 3
    assert sum(case["case_kind"] == "anti_trigger" for case in eval_manifest["evals"]) >= 4
    assert sum(case["should_trigger"] is True for case in trigger_manifest) >= 3
    assert sum(case["should_trigger"] is False for case in trigger_manifest) >= 4


def test_food_world_candidate_is_shadowed_outside_the_runtime_registry() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    candidate_dir = repo_root / "backend" / "experiments" / "incubation_skill_lab" / "candidates" / "incubate-food-world"
    skill_text = (candidate_dir / "SKILL.md").read_text(encoding="utf-8")
    parts, error = split_skill_markdown(skill_text)
    profile = IncubationSkillProfile.model_validate_json((candidate_dir / "references" / "incubation-profile.json").read_text(encoding="utf-8"))
    eval_manifest = IncubationEvalManifest.model_validate_json((candidate_dir / "evals" / "evals.json").read_text(encoding="utf-8"))

    assert error is None
    assert parts is not None
    assert parts.metadata["metadata"]["lifecycle"] == "shadow"
    assert profile.skill_name == "incubate-food-world"
    assert profile.lifecycle_status == "shadow"
    assert profile.candidate_paths == ()
    assert profile.preferred_root_candidate is None
    assert any("中间载体" in principle for principle in profile.selection_principles)
    assert any("混合内容根" in principle for principle in profile.selection_principles)
    assert eval_manifest.acceptance.status == "failed"
    assert eval_manifest.acceptance.profile_sha256 == profile.content_sha256()
    assert {case.case_id for case in eval_manifest.evals} >= {
        "fruit-shop",
        "seafood",
        "hotpot-base",
    }
    assert {case.case_kind for case in eval_manifest.evals} == {
        "trigger",
        "anti_trigger",
        "behavior",
        "held_out",
    }
    assert not (repo_root / "skills" / "public" / profile.skill_name).exists()
