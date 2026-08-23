---
id: ADR-046
status: accepted
date: 2026-08-22
amends:
  - ADR-036-versioned-account-launch-plan.md
related:
  - A140-account-direction-launch-plan-bridge.md
  - ADR-044-thin-account-direction-ledger-bridge.md
---

# ADR-046 起号计划接受薄账号方向的精确父级

## 决定

`AccountLaunchPlan` 接受两种互斥的账号决策父级：新主路径的 `AccountDirectionVersion`，或历史兼容的已确认
`IncubationJudgment`。两种路径都必须同时绑定同项目、同逻辑账号的一张精确
`content_map_candidate`；不能只按内容根、版本号或创建时间寻找“看起来最新”的地图。

新方向路径只有在以下条件全部成立时可生成计划：

- 方向版本是当前逻辑账号的有效追加式版本；
- 选中方向通过唯一确定性函数得到冻结根（显式 `content_root` 优先，旧载荷只用已封存长期主体前缀）；
- 方向保留精确提案父级，revision、选中 option 和 basis 与提案一致；
- 地图内容根与方向完全一致；
- 地图直接保存方向父级，或是方向提案明确保存的同账号依据父级；
- 多个地图同时符合时，用户请求携带精确地图工件 ID。

确认必须绑定精确计划提案回执，且当前真实用户原话严格等于展示的
`确认起号计划 <proposal-id>`；确认生成不可变子工件，重复提交幂等复用。数据库按逻辑账号和 revision
原子拒绝不同内容分叉。

## 所有权

- `AccountDirectionVersion` 继续拥有长期内容主体、受众假设、账号角色、表现方向和业务连接。
- `content_map_candidate` 只拥有该内容根下的候选路径。
- `AccountLaunchPlan` 只拥有 7/30 天运营安排、计划题眼和检查问题。
- `TopicBrief` 继续独占单题证据与中心命题；计划题眼不能跳过它。
- `ProductionPlan` 与视频执行是更下游的显式继续，不由本 ADR 自动启动。

## 兼容与注意力

当新旧账号决策工件同时存在时，新 `AccountDirectionVersion` 优先。只有没有新方向时才使用旧战略。旧数据
不迁移、不覆盖，`develop_account_strategy` 不恢复默认注册。起号计划工具继续延迟发现；宽泛起号请求不因
本 ADR 自动获得日历、频率、发布时间、预算或成功承诺。

## 拒绝

- 拒绝让方向 ID 可空后在计划内混存新旧两种父级。
- 拒绝只凭相同 `content_root` 选择任意地图。
- 拒绝从聊天摘要或模型工具参数伪造用户确认原话。
- 拒绝把方向确认自动展开成 7/30 天计划。
- 拒绝把计划题眼直接发送到视频制作或发布。
- 拒绝只传自由文本题眼；计划续写必须同时绑定当前已确认计划回执和精确 `seed_id`，并把两者写入
  `content_reading` 与 `TopicBrief` 谱系。

## 实施与验收边界

A140 已实现合同、运行时、工具、展示、数据库唯一约束和 seed 到内容链的精确父级连接，并通过聚焦回归。尚未完成真实模型的完整
“方向确认 -> 起号计划 -> 计划确认 -> 单题取证”业务验收；因此 ADR-036 中关于真实 Account Skill 投影、
完整运营闭环和自动调度的未完成条件继续保留。
