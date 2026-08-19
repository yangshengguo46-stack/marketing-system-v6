from __future__ import annotations

from deerflow.incubation.judgment import IncubationJudgment


def _render_route_proposal(judgment: IncubationJudgment) -> str:
    confidence_labels = {"low": "低", "medium": "中", "high": "高"}
    lines = [
        "# 账号路线候选",
        "",
        f"**提案版本：** v{judgment.revision_number}（待你确认）",
    ]
    for index, route in enumerate(judgment.route_options, start=1):
        recommended = "（推荐）" if route.option_id == judgment.recommended_option_id else ""
        lines.extend(
            (
                "",
                f"## {index}. {route.name}{recommended}",
                "",
                f"**路线编号：** `{route.option_id}`",
                "",
                f"**账号定位：** {route.positioning.decision}",
                "",
                f"**给观众的长期承诺：** {route.positioning.audience_promise}",
                "",
                f"**与业务如何连接：** {route.business_connection}",
            )
        )
        if route.business_intent is not None:
            intent = route.business_intent
            lines.extend(
                (
                    "",
                    f"**业务角色：** {intent.business_role}",
                    "",
                    f"**账号要完成的业务任务：** {intent.account_objective}",
                    "",
                    f"**需要影响的人：** {intent.target_people}",
                    "",
                    f"**对方的需求：** {intent.target_need}",
                    "",
                    f"**希望促成的行为：** {intent.desired_action}",
                    "",
                    f"**目标市场：** {intent.market_scope}",
                )
            )
        lines.extend(
            (
                "",
                f"**内容受众假设：** {route.audience.people}",
                "",
                f"**账号人设：** {route.persona.account_role}",
                "",
                "**主要表现形式：** " + "；".join(route.presentation.primary_forms),
            )
        )
        if route.presentation.supporting_forms:
            lines.extend(("", "**辅助表现形式：** " + "；".join(route.presentation.supporting_forms)))
        if route.monetization:
            lines.extend(("", "**变现假设：** " + "；".join(item.path for item in route.monetization)))
        lines.extend(
            (
                "",
                f"**为什么适合：** {route.recommendation_rationale}",
                "",
                f"**当前置信度：** {confidence_labels[route.positioning.confidence]}",
            )
        )
        if route.resource_requirements:
            lines.extend(("", "**需要的资源：** " + "；".join(route.resource_requirements)))
        if route.tradeoffs:
            lines.extend(("", "**代价与风险：** " + "；".join(route.tradeoffs)))
        route_unknowns = tuple(
            dict.fromkeys(
                (
                    *route.positioning.unknowns,
                    *((route.business_intent.unknowns) if route.business_intent is not None else ()),
                    *route.audience.unknowns,
                    *route.persona.unknowns,
                    *route.presentation.unknowns,
                    *(unknown for item in route.monetization for unknown in item.unknowns),
                )
            )
        )
        if route_unknowns:
            lines.extend(("", "**仍需确认：** " + "；".join(route_unknowns)))
    if judgment.unknowns:
        lines.extend(("", "## 共同未知", ""))
        lines.extend(f"- {unknown}" for unknown in judgment.unknowns)
    lines.extend(
        (
            "",
            "## 等你选择",
            "",
            "请回复路线编号，或者直接说你想要哪条。推荐只是建议，在你确认之前不会进入下一步。",
        )
    )
    return "\n".join(lines).strip()


def render_account_strategy(judgment: IncubationJudgment) -> str:
    if judgment.decision_status == "proposed":
        return _render_route_proposal(judgment)

    confidence_labels = {"low": "低", "medium": "中", "high": "高"}
    lines = ["# 已确认的账号路线", "", f"**定位版本：** v{judgment.revision_number}"]
    if judgment.selected_option_id is not None:
        selected = next(route for route in judgment.route_options if route.option_id == judgment.selected_option_id)
        lines.extend(("", f"**已选路线：** {selected.name}（`{selected.option_id}`）"))
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

    if judgment.business_intent is not None:
        item = judgment.business_intent
        lines.extend(
            (
                "",
                "## 账号的业务任务",
                "",
                f"**业务角色：** {item.business_role}",
                "",
                f"**账号要完成什么：** {item.account_objective}",
                "",
                f"**需要影响谁：** {item.target_people}",
                "",
                f"**对方需要什么：** {item.target_need}",
                "",
                f"**希望促成什么行为：** {item.desired_action}",
                "",
                f"**目标市场：** {item.market_scope}",
                "",
                f"**判断理由：** {item.rationale}",
                "",
                f"**置信度：** {confidence_labels[item.confidence]}",
            )
        )
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
