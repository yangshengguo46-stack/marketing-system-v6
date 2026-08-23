from __future__ import annotations

from deerflow.incubation.account_launch_plan import account_launch_plan_confirmation_text
from deerflow.incubation.launch_plan import AccountLaunchPlan


def _bullet_lines(values: tuple[str, ...]) -> list[str]:
    return [f"- {value}" for value in values]


def render_account_launch_plan(
    plan: AccountLaunchPlan,
    *,
    artifact_id: str | None = None,
) -> str:
    """Render a compact, user-reviewable projection of a launch-plan artifact."""

    status = "已确认" if plan.decision_status == "confirmed" else "待确认"
    lines = [
        f"# 账号起号计划（{status}）",
        "",
        f"**计划版本：** v{plan.revision_number}",
        f"**产能状态：** {'用户已说明' if plan.capacity.status == 'user_stated' else '暂定，待真实产能校准'}",
        f"**当前节奏：** {plan.capacity.cadence_summary}",
        f"**依据：** {plan.capacity.basis}",
    ]
    if artifact_id is not None:
        receipt_label = "计划提案编号" if plan.decision_status == "proposed" else "已确认回执编号"
        lines.insert(3, f"**{receipt_label}：** `{artifact_id}`")
    if plan.capacity.planned_publish_days:
        days = "、".join(f"第 {day} 天" for day in plan.capacity.planned_publish_days)
        lines.append(f"**暂定发布日：** {days}")
    lines.extend(["", "## 栏目与题眼"])
    seeds_by_series: dict[str, list[str]] = {}
    for seed in plan.topic_seeds:
        seeds_by_series.setdefault(seed.series_id, []).append(f"[`{seed.seed_id}`] {seed.focal_subject}：{seed.concrete_event_or_question}（来源：{seed.source_kind}；执行前取证：{seed.evidence_need}）")
    for series in plan.series:
        lines.extend(
            [
                "",
                f"### {series.name}",
                series.purpose,
                f"**重复追问：** {series.repeatable_question}",
            ]
        )
        lines.extend(_bullet_lines(tuple(seeds_by_series.get(series.series_id, ()))))

    lines.extend(["", "## 前 7 天"])
    for day in plan.first_week:
        marker = "发布" if day.publish else "非发布"
        lines.extend(["", f"**第 {day.day} 天 · {marker} · {day.focus}**"])
        lines.extend(_bullet_lines(day.actions))
        if day.observation_questions:
            lines.extend(f"- 观察：{question}" for question in day.observation_questions)

    lines.extend(["", "## 第 8-30 天"])
    for phase in plan.later_phases:
        lines.extend(
            [
                "",
                f"**第 {phase.start_day}-{phase.end_day} 天：{phase.objective}**",
                *_bullet_lines(phase.actions),
                *(f"- 复盘：{question}" for question in phase.review_questions),
            ]
        )

    lines.extend(["", "## 调整点"])
    for checkpoint in plan.checkpoints:
        lines.append(f"**第 {checkpoint.day} 天：** {'；'.join(checkpoint.questions)}")
    if plan.unknowns:
        lines.extend(["", "## 仍未知", *_bullet_lines(plan.unknowns)])
    if plan.decision_status == "proposed":
        lines.extend(
            [
                "",
                "这是一份可修改提案，不是平台规律，也不会阻止继续做选题。你可以确认、删改栏目，或先补充真实产能。",
                *((f"若要精确确认，请单独发送：`{account_launch_plan_confirmation_text(artifact_id)}`",) if artifact_id is not None else ()),
            ]
        )
    return "\n".join(lines)


__all__ = ["render_account_launch_plan"]
