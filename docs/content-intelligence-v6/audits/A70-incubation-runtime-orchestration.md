---
id: A70
status: implemented
date: 2026-08-18
---

# A70 孵化判断主链接线

## 本轮接通

选中项目的可拍选题请求现在按真实产物顺序执行：

```text
topic evidence
-> content_reading + content_world
-> minimal IncubationBrief
-> formal benchmark/audience evidence selection
-> IncubationJudgment
-> MessagePlan + BaseDraft
-> final content-run persistence
```

- 项目、用户、线程和运行身份只从服务端 `ToolRuntime.context` 读取，不进入模型参数。
- 当前阅读、冻结地图和已采用选题证据先落账，保证 Judgment 与后续 MessagePlan 的父级已真实存在。
- Brief 只记录用户逐字业务主体；对标/受众选择沿用 A68，缺失不形成硬门。
- 孵化判断只把定位、受众、人设和账号级表达方向投影给内容交付；变现不进入 TopicBrief/BaseDraft。
- `message_plan` 精确绑定实际使用的 Judgment，回答同时分栏展示定位、受众、人设、账号级表现方向、
  变现假设、未知和备选。
- 未选择项目、仓储不可用、证据不合格或判断模型失败时，保留原有证据选题能力，不吞掉回答。

## 验证

工具编排、内容交付、Brief、判断、证据选择和产物谱系联合回归 `79 passed`；Ruff 与格式检查通过。
当前 FormatDecision、AdaptedDraft 和 ProductionPlan 仍需继续接入同一运行，不能据此宣称发布前主链完成。

