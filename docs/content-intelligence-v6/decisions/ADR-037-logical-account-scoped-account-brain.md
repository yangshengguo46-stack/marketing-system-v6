---
id: ADR-037
status: proposed
date: 2026-08-21
related:
  - A124-account-brain-memory-and-skill-architecture.md
  - ADR-036-versioned-account-launch-plan.md
---

# ADR-037 逻辑账号作用域的 AccountBrain

## 候选决定

为每个待孵化账号建立平台无关的 `LogicalAccountRef`，并以
`(owner_user_id, logical_account_id)` 作为账号长期状态和检索的可信隔离边界。一个逻辑账号可以绑定零个
或多个平台账号。

账号事实进入版本化台账，账号经历进入证据资料库，稳定采用的方法投影为只读私有 Account Skill；Lead
只按当前任务组装有界上下文。通用方法继续由共享 Skill 提供。

## 未授权事项

- 不把完整账号历史、完整 30 天日历或原始数据写进 Skill。
- 不让模型选择或覆盖 `owner_user_id`、`logical_account_id`。
- 不根据一次结果自动更新账号程序性方法。
- 不因采用语义记忆而默认引入向量数据库。
- 不把 `AccountLaunchPlan` 变成默认工作流、TopicBrief 前置门或平台成功保证。

## 2026-08-21 实施断点

`LogicalAccountRef`、数据库迁移、Gateway 可信绑定、账号策略到制作计划的工件隔离，以及双账号测试已
完成。`AccountLaunchPlan` 只以用户明确请求时调用的可选 Lead 工具接入，读取已确认策略和同账号冻结
地图；它不阻断日常选题，也不依赖平台登录。

ADR 仍保持 `proposed`，因为可重建 Account Skill 投影及完整真实模型链路尚未验收。

## 接受条件

完成同用户双逻辑账号隔离测试、线程切换清理测试、Skill 投影重建/hash 测试，以及未绑定平台账号的
完整“定位 -> 内容地图 -> 计划 -> TopicBrief”测试后，方可将状态改为 `accepted`。
