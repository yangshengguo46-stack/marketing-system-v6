---
id: A71
status: implemented
date: 2026-08-18
---

# A71 表现形式与适配稿主链接线

## 本轮接通

选中项目且已经形成有效 `BaseDraft` 的可拍选题，现在继续执行：

```text
MessagePlan + BaseDraft
-> FormatDecision
-> AdaptedDraft
```

- 形式运行时只读取精确 MessagePlan、其直接派生的 BaseDraft、可选孵化判断，以及最多八份同项目
  `user_material` 媒体观察。
- 对标证据、选题证据和模型猜测不能冒充用户已有的拍摄资源；资源未知时允许返回暂定形式和缺口。
- 适配稿每个表现单元保留 BaseDraft 的连续逐字锚点；只有微短剧或情景剧可以增加场面与表演提示。
- 最终回答在原有具体选题、MessagePlan、BaseDraft 和孵化判断之后，单独展示本条表现形式与形式适配稿。
- `_answer_appendix` 只用于工具内部拼接，返回给前端的持久化回执会移除所有下划线开头的内部字段。
- 形式或适配模型失败时，已经有效的选题、基础稿和孵化判断仍然保留，不伪装为全链成功。

## 验证

先以失败测试固定“附加正文必须展示、内部字段不得泄露”的缺口；补线后，内容工具、内容交付、
FormatDecision 和 AdaptedDraft 联合回归 `103 passed`。ProductionPlan 与 MediaKit 仍是后续独立断点。
