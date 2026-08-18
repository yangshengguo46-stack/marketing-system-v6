from __future__ import annotations

from deerflow.incubation.judgment import IncubationJudgment


def render_account_strategy(judgment: IncubationJudgment) -> str:
    confidence_labels = {"low": "低", "medium": "中", "high": "高"}
    lines = ["# 账号孵化判断", "", f"**定位版本：** v{judgment.revision_number}"]
    if judgment.revision_reason is not None:
        lines.extend(("", f"**本版为什么调整：** {judgment.revision_reason}"))

    if judgment.positioning is not None:
        item = judgment.positioning
        lines.extend(
            (
                "",
                "## 定位",
                "",
                f"**账号定位：** {item.decision}",
                "",
                f"**给观众的长期承诺：** {item.audience_promise}",
                "",
                f"**判断理由：** {item.rationale}",
                "",
                f"**置信度：** {confidence_labels[item.confidence]}",
            )
        )
        if item.boundaries:
            lines.extend(("", "**边界：** " + "；".join(item.boundaries)))
        if item.unknowns:
            lines.extend(("", "**仍未知：** " + "；".join(item.unknowns)))

    if judgment.audience is not None:
        item = judgment.audience
        lines.extend(
            (
                "",
                "## 受众假设",
                "",
                f"**可能是谁：** {item.people}",
                "",
                f"**持续关心什么：** {item.recurring_interest}",
                "",
                f"**为什么回来：** {item.why_return}",
                "",
                f"**判断理由：** {item.rationale}",
                "",
                f"**置信度：** {confidence_labels[item.confidence]}",
            )
        )
        if item.unknowns:
            lines.extend(("", "**仍未知：** " + "；".join(item.unknowns)))

    if judgment.persona is not None:
        item = judgment.persona
        lines.extend(
            (
                "",
                "## 人设",
                "",
                f"**账号角色：** {item.account_role}",
                "",
                f"**判断理由：** {item.rationale}",
                "",
                f"**置信度：** {confidence_labels[item.confidence]}",
            )
        )
        if item.trust_basis:
            lines.extend(("", "**可信依据：** " + "；".join(item.trust_basis)))
        if item.boundaries:
            lines.extend(("", "**不能冒充：** " + "；".join(item.boundaries)))
        if item.unknowns:
            lines.extend(("", "**仍未知：** " + "；".join(item.unknowns)))

    if judgment.presentation is not None:
        item = judgment.presentation
        lines.extend(
            (
                "",
                "## 账号级表现方向",
                "",
                "**主要方向：** " + "；".join(item.primary_forms),
                "",
                f"**判断理由：** {item.rationale}",
                "",
                f"**置信度：** {confidence_labels[item.confidence]}",
            )
        )
        if item.supporting_forms:
            lines.extend(("", "**辅助方向：** " + "；".join(item.supporting_forms)))
        if item.constraints:
            lines.extend(("", "**约束：** " + "；".join(item.constraints)))
        if item.unknowns:
            lines.extend(("", "**仍未知：** " + "；".join(item.unknowns)))

    if judgment.monetization:
        lines.extend(("", "## 变现假设"))
        for index, item in enumerate(judgment.monetization, start=1):
            lines.extend(
                (
                    "",
                    f"**路径 {index}：** {item.path}",
                    "",
                    f"**需要先建立的信任：** {item.trust_required}",
                    "",
                    f"**判断理由：** {item.rationale}",
                    "",
                    f"**置信度：** {confidence_labels[item.confidence]}",
                )
            )
            if item.preconditions:
                lines.extend(("", "**成立前提：** " + "；".join(item.preconditions)))
            if item.unknowns:
                lines.extend(("", "**仍未知：** " + "；".join(item.unknowns)))

    if judgment.unknowns or judgment.alternatives:
        lines.extend(("", "## 未知与备选"))
        if judgment.unknowns:
            lines.extend(("", "**尚未确认：** " + "；".join(judgment.unknowns)))
        if judgment.alternatives:
            lines.extend(("", "**备选路线：** " + "；".join(judgment.alternatives)))
    return "\n".join(lines).strip()


__all__ = ["render_account_strategy"]
