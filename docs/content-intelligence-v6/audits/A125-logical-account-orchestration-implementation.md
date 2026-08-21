---
id: A125
status: reviewed
date: 2026-08-21
sources:
  - A124-account-brain-memory-and-skill-architecture.md
  - ADR-036-versioned-account-launch-plan.md
  - ADR-037-logical-account-scoped-account-brain.md
  - backend/packages/harness/deerflow/incubation/contracts.py
  - backend/packages/harness/deerflow/persistence/migrations/versions/0015_incubation_logical_accounts.py
  - backend/app/gateway/routers/incubation_projects.py
  - backend/packages/harness/deerflow/tools/builtins/account_launch_plan_tool.py
  - https://github.com/xingtaxueshu/literature-review-skills/tree/84de3ba1f3853334d565fbbe6ac4f321cba6bd6b
---

# A125 逻辑账号编排实施与起号计划接线

## 本轮问题

账号定位、对标、内容地图、选题和长期学习不能继续堆在一个调用里，也不能要求用户先登录平台。需要
先建立稳定的账号身份，再让不同能力读写同一账号的版本化工件，同时保留按需调用，不制造新硬流程。

## 实施结果

```text
User / Project
-> LogicalAccountRef（平台登录前存在）
-> AccountStrategyProposal
-> 用户选择 -> ConfirmedAccountStrategy
-> 可选 AccountLaunchPlan
-> TopicBrief / MessagePlan / Draft
-> 可选 Format / Adaptation / Production
```

- `LogicalAccountRef(owner_user_id, project_id, logical_account_id)` 成为账号长期状态的隔离边界。
- 一个逻辑账号可绑定零到多个平台账号；平台账号不再充当孵化身份。
- 账号策略、地图、证据、稿件、形式、适配、制作和起号计划均携带同一逻辑账号及父工件引用。
- Gateway 只从服务端线程元数据恢复账号；调用方在 config、context、metadata 或 configurable 中伪造的
  账号字段会被剥离。跨项目或失效绑定返回冲突，同项目切换账号允许，解绑项目同步清理账号。
- `0015` 为旧项目创建稳定 legacy 逻辑账号并只回填旧平台账号。旧工件保持
  `logical_account_id=NULL`，原 canonical ID、内容哈希和父引用不变。
- `plan_account_launch` 与 `confirm_account_launch_plan` 是可选工具。前者只在账号路线已确认且用户明确
  要求 7/30 天计划时运行；后者只封存用户接受的当前提案。两者都不阻断 TopicBrief。

## 为什么不是一个大工作流

语义、地图、定位、计划和单条内容分别产生可检查工件，由 Lead 按当前请求选择下一步。确定性代码负责
账号隔离、版本、父级、哈希和状态；模型负责判断和表达。没有工具可以强迫每次请求依次经过所有模块。

7 天表示首轮产能与方向验证，30 天表示第一版滚动运营视窗。非发布日可以用于研究、取证、写稿、试拍
和复盘；计划不写平台硬阈值，不保证起号成功，也不把未取证人物或事件冒充 TopicBrief。

## 科研 Skill 的使用边界

为 Codex 开发过程安装了 `compare-research-methods` 与 `map-literature-contradictions`，固定来源提交为
`84de3ba1f3853334d565fbbe6ac4f321cba6bd6b`。它们位于用户本机 `~/.codex/skills/`，只帮助开发者比较
方法和审计证据矛盾；没有注册进 DeerFlow Lead、产品 Skill 目录或用户运行时。带强制图表、重型依赖或
固定审查门的候选没有采用。

## 验证

- 逻辑账号领域、起号计划与 Lead 工具聚焦回归：`31 passed`。
- Gateway 账号 CRUD、可信绑定、切换、分支继承和伪造字段清理：`226 passed, 1 warning`。
- `0012 -> 0015` 迁移、升降级、旧 ID 与 ORM/Alembic 对齐：`29 passed`，其中 `0015` 专项 `4 passed`。
- 同一用户、同一项目的两个未登录逻辑账号拥有不同策略与计划 ID；确认第一个不会改变第二个。
- 按 `backend/Makefile` 的正式认证环境完成全量非 live 回归：`12379 passed, 75 skipped, 17 warnings`，
  `484.09s`，退出码 `0`。

## 仍未完成

- 从台账确定性生成、校验并重建只读 `account-{logical_account_id}` Account Skill 投影。
- 用真实模型完成两个未登录账号的“定位 -> 用户确认 -> 7/30 计划 -> 具体 TopicBrief”验收。
- 计划后的真实发布、回执和学习提升仍属于后续循环，本轮没有提前接入。

因此本轮完成的是账号脑的可信编排脊柱和可选计划层，不宣称完整 AccountBrain 或全生命周期闭环已验收。
