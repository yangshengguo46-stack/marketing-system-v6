"""Contract tests for the product-native generic account-incubation Skill."""

from pathlib import Path

import yaml

from deerflow.skills.describe import build_skill_search_setup, get_skill_index_prompt_section
from deerflow.skills.frontmatter import split_skill_markdown
from deerflow.skills.storage import get_or_new_skill_storage
from deerflow.skills.types import SkillCategory


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_generic_account_incubation_skill_is_discoverable_without_a_vertical_profile() -> None:
    repo_root = _repo_root()
    storage = get_or_new_skill_storage(skills_path=repo_root / "skills")
    skills = storage.load_skills(enabled_only=False)

    skill = next(item for item in skills if item.name == "account-incubation")
    content = skill.skill_file.read_text(encoding="utf-8")
    parts, error = split_skill_markdown(content)

    assert error is None
    assert parts is not None
    assert skill.category == SkillCategory.PUBLIC
    assert skill.name == "account-incubation"
    assert skill.description.startswith("通用起号判断")
    assert len(skill.description) <= 120
    assert [(budget.tools, budget.max_calls) for budget in skill.tool_call_budgets] == [
        (("tool_search",), 2),
        (("web_search", "web_fetch"), 3),
        (("collect_douyin_benchmark_account", "collect_douyin_benchmark_candidate"), 2),
    ]
    assert not (skill.skill_dir / "references" / "incubation-profile.json").exists()


def test_generic_account_incubation_skill_stays_outcome_oriented() -> None:
    skill_path = _repo_root() / "skills" / "public" / "account-incubation" / "SKILL.md"
    content = " ".join(skill_path.read_text(encoding="utf-8").split())

    assert "公开内容账号" in content
    assert "行业经营或后台操作教程" in content
    assert "业务目标" in content
    assert "内容受众" in content
    assert "真实对标" in content
    assert "具体主体、事件或问题" in content
    assert "直接进入拍摄或成稿" in content
    assert "select:web_search,web_fetch,collect_douyin_benchmark_account" in content
    assert "产品或服务是否具备某项能力" in content
    assert "待确认的前提" in content
    assert "搜索结果页只用于发现候选来源" in content
    assert "无法读取原文" in content
    assert "不要并行发起多个近义查询" in content
    assert "一次正文读取失败后" in content
    assert "删除这条细节并继续交付" in content
    assert "我服务过的一个客户" in content
    assert "发送前只做一次事实清理" in content
    assert "没有固定步骤" in content
    assert "没有固定样本数" in content
    assert "7天" not in content
    assert "30天" not in content
    assert "90天" not in content


def test_product_skill_index_exposes_generic_and_vertical_incubation_only() -> None:
    repo_root = _repo_root()
    config = yaml.safe_load((repo_root / "config.example.yaml").read_text(encoding="utf-8"))
    patterns = config["skills"]["prompt_index_patterns"]
    storage = get_or_new_skill_storage(skills_path=repo_root / "skills")
    skills = storage.load_skills(enabled_only=False)

    setup = build_skill_search_setup(
        skills,
        enabled=True,
        prompt_index_patterns=patterns,
    )

    assert setup.skill_names == frozenset(
        {
            "account-incubation",
            "incubate-gift-human-relations",
        }
    )
    prompt = get_skill_index_prompt_section(
        skill_names=setup.skill_names,
        skill_descriptions={skill.name: skill.description for skill in skills},
    )
    assert "account-incubation: 通用起号判断" in prompt
    assert "为用户建立一个公开内容账号" not in prompt
    assert "marketing-video-production" not in prompt
