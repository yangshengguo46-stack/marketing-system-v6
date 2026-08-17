---
id: A73
status: implemented
date: 2026-08-18
---

# A73 制作方案主链接线

## 本轮接通

选中项目的可拍选题主链现在继续到：

```text
FormatDecision
-> AdaptedDraft
-> ProductionPlan
```

- ProductionPlan 精确消费本轮已保存的 AdaptedDraft 和 FormatDecision。
- 传入的用户素材与表现形式阶段使用同一组最多八份、同项目、已授权 `user_material` 媒体观察。
- 方案保存后，在最终回答中单独展示状态、素材需求、拍摄/制作动作、装配顺序、资源缺口、未知和边界。
- 制作方案失败只降级后置制作段，不会抹除选题、MessagePlan、BaseDraft、表现形式或适配稿。
- 内部附加正文继续不进入前端持久化回执。

## 验证

先以失败测试固定“适配稿之后必须继续保存并展示 ProductionPlan”；实现后，内容工具、内容交付、
FormatDecision、AdaptedDraft 和 ProductionPlan 联合回归 `126 passed`。MediaKit 尚未执行本方案，
因此当前完成的是可审查的制作计划，不是已经生成媒体文件。
