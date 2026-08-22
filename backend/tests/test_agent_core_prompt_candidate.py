from __future__ import annotations

from deerflow.agents.lead_agent.agent_core_contract import PRODUCTION_AGENT_KERNEL
from deerflow.agents.lead_agent.prompt import SYSTEM_PROMPT_TEMPLATE


def _normalized(text: str) -> str:
    return " ".join(text.split())


def test_agent_kernel_defines_employee_identity_and_enduring_mission() -> None:
    normalized = _normalized(PRODUCTION_AGENT_KERNEL)

    assert "new-media incubation and operations employee" in normalized
    assert "inside the user's team" in normalized
    assert "not an outside consultant or teacher" in normalized
    assert "earn attention" in normalized
    assert "build durable IP" in normalized
    assert "improve from actual outcomes" in normalized


def test_agent_kernel_preserves_independent_thought_and_dynamic_action() -> None:
    normalized = _normalized(PRODUCTION_AGENT_KERNEL)

    assert "Own the work the user gives you" in normalized
    assert "Think and act independently" in normalized
    assert "make judgments, create, research, use tools or Skills, execute, verify, and revise" in normalized
    assert "no capability or workflow is mandatory" in normalized
    assert "speak like a teammate rather than teaching the user a method" in normalized


def test_agent_kernel_keeps_truth_without_removing_intelligence() -> None:
    normalized = _normalized(PRODUCTION_AGENT_KERNEL)

    assert "Facts must be real; judgments can be bold" in normalized
    assert "observed facts, inferences, hypotheses, and creative proposals" in normalized
    assert "do not become timid or merely repeat the user" in normalized
    assert "missing user-owned fact truly blocks useful work" in normalized
    assert "explicit approval before irreversible external actions" in normalized


def test_agent_kernel_stays_thin_instead_of_becoming_a_business_contract() -> None:
    assert len(PRODUCTION_AGENT_KERNEL.encode("utf-8")) <= 1_600

    for stacked_instruction in (
        "exactly one decision question",
        "first-pass account direction",
        "concrete content idea has",
        "posting quotas",
        "named programs",
        "intake questionnaire",
        "Before sending the visible response",
        "propose_account_direction",
        "explore_content_world",
    ):
        assert stacked_instruction not in PRODUCTION_AGENT_KERNEL


def test_agent_kernel_is_model_neutral() -> None:
    lowered = PRODUCTION_AGENT_KERNEL.lower()

    for provider_or_model in ("glm", "deepseek", "doubao", "kimi", "openai", "anthropic", "gemini"):
        assert provider_or_model not in lowered


def test_live_system_prompt_uses_only_the_thin_agent_kernel_for_business_authority() -> None:
    assert SYSTEM_PROMPT_TEMPLATE.count("<agent_kernel>") == 1
    assert PRODUCTION_AGENT_KERNEL in SYSTEM_PROMPT_TEMPLATE
    for legacy_block in (
        "<account_incubation>",
        "<content_intelligence>",
        "<clarification_system>",
        "<work_ownership>",
        "<marketing_charter>",
        "<response_style>",
    ):
        assert legacy_block not in SYSTEM_PROMPT_TEMPLATE
    assert len(SYSTEM_PROMPT_TEMPLATE.encode("utf-8")) <= 5_000
