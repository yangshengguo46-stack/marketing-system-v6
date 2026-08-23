---
id: A140
status: adopted
date: 2026-08-22
sources:
  - A123-short-video-launch-planning-audit.md
  - A135-thin-account-direction-ledger-implementation.md
  - ADR-036-versioned-account-launch-plan.md
  - ADR-044-thin-account-direction-ledger-bridge.md
  - backend/packages/harness/deerflow/incubation/account_launch_plan.py
  - backend/packages/harness/deerflow/incubation/launch_plan.py
  - backend/packages/harness/deerflow/incubation/launch_plan_runtime.py
  - backend/packages/harness/deerflow/tools/builtins/account_launch_plan_tool.py
  - backend/tests/test_account_launch_plan.py
  - backend/tests/test_account_launch_plan_runtime.py
  - backend/tests/test_account_launch_plan_tool.py
---

# A140 新账号方向到可选起号计划桥接

## 本轮目标

A135 已让自主 Lead 的账号判断形成 `AccountDirectionVersion`，但历史 `AccountLaunchPlan` 仍只接受旧
`IncubationJudgment + content_map_candidate`。这会让“方向已经确认，用户接着要起号安排”退回旧固定路线，
也无法稳定把某一版方向、某一张地图和后续具体选题串起来。

本轮只补这个兼容接缝，不把 7/30 天计划恢复成首次起号必经流程，也不把计划题眼冒充选题、证据或脚本。

## 已落地父级合同

新的计划父级为二选一：

```text
AccountDirectionVersion + exact linked content_map_candidate
  -> proposed AccountLaunchPlan
  -> exact proposal receipt + `确认起号计划 <proposal-id>`
  -> confirmed AccountLaunchPlan
  -> exact confirmed plan receipt + exact seed_id
  -> evidence research -> TopicBrief -> MessagePlan -> BaseDraft

legacy confirmed IncubationJudgment + exact historical map
  -> AccountLaunchPlan（只读兼容路径继续可用）
```

`AccountLaunchPlan` 必须且只能保存 `direction_artifact_id` 或 `strategy_artifact_id` 之一。新方向路径统一通过
`account_direction_content_root` 取得冻结根：优先使用显式 `content_root`；旧方向缺失时只按已封存
`long_term_content_subject` 的确定性前缀推导，工具、计划和选题不得各自再解释。地图还必须满足以下精确谱系之一：

1. 地图直接保存当前方向版本为父级；或
2. 地图是该方向提案明确列出的 `basis_artifact_id`，且提案自身也保存该地图父级。

无论采用哪一种地图连接，方向都必须保留同项目/账号的精确提案父级，且 revision、选中 option 和 basis 与
提案载荷一致；“地图是方向直接子级”不能绕过提案验证。

只按相同根或“最新地图”猜测不够。存在多个合法地图时，调用方必须回传准确
`content_map_artifact_id`；陌生、跨账号或不同内容根的地图失败关闭。

## 用户确认与幂等

- 待确认展示返回“计划提案编号”、每个题眼的 `seed_id / source_kind / evidence_need`，以及唯一确认命令
  `确认起号计划 <proposal-id>`；已确认展示改为“已确认回执编号”，不会把子工件 ID 误标成提案。
- 确认工具只接收精确 `plan_artifact_id`，并要求最近一条真实用户消息严格等于该命令；领域函数再次校验，
  模型不能用自由参数或含糊的“可以”代替用户确认。
- 只有当前最新提案可首次确认；确认产生新工件并保留提案父级，不覆盖旧提案。
- 同一提案的重复确认只有在子工件版本连续、父集合精确且除确认元字段外的计划内容完全不变时才返回已有回执；
  发现篡改子工件或同一提案有两个不同确认子工件时失败关闭。
- `0017_account_launch_plan_unique` 在 owner/project/logical-account/version 上增加数据库 partial UNIQUE；同内容
  并发重放幂等，不同内容并发/后到显式冲突。升级发现存量重复时失败关闭，不挑选或删除历史工件。

## 与内容生产的衔接

起号计划仍只拥有栏目、题眼、行动节奏、观察问题和调整条件。用户选择题眼时必须同时提交当前已确认计划
回执和准确 `seed_id`；系统从计划精确父级重水化地图，把该 seed 的具体问题作为研究入口，并重新进入：

```text
evidence research -> TopicBrief -> MessagePlan -> BaseDraft
-> explicit FormatDecision -> AdaptedDraft -> explicit ProductionPlan
```

本轮同时让按已确认方向生成的 `content_map_candidate` 保存该方向为精确父级，给计划桥提供可验证连接。
新 `content_reading` 载荷和 `TopicBrief` 父级同时记录精确计划回执与 seed ID，并验证 TopicBrief 使用计划的
地图版本和 path。普通具体选题仍可以不经过 `AccountLaunchPlan`；计划也不能直接启动制作、发布或写入长期学习。

## 模型注意力与兼容

- 新方向优先于旧地图绑定战略；只有当前逻辑账号没有 `AccountDirectionVersion` 时才回退旧战略。
- 计划模型只读取有界方向投影，不接收方向原始用户文本、确认原话或无界理由；输入仍受 24 KB 上限约束。
- `plan_account_launch` 与 `confirm_account_launch_plan` 保持延迟发现，不进入普通首轮工具 Schema。
- `develop_account_strategy` 没有恢复注册，账号受众、语义、地图和对标没有重新变成固定前置流水线。

## 明确未做

- 没有真实模型运行“方向 -> 计划 -> 用户确认 -> 题眼 -> TopicBrief”；本轮状态是代码实现并通过模拟合同
  回归，不是业务效果验收。
- 没有让模型为无 `content_root` 的旧方向补写新判断；只复用同一个确定性前缀函数，推导失败仍关闭。
- 没有迁移历史 `IncubationJudgment`，也没有生成私有 Account Skill 投影。
- 没有自动调度、拍摄、生成、剪辑或发布。

## 验证回执

最终命令、数字和完整套件限制统一记录在
`evidence/a140-a141-video-production-2026-08-22.md`。覆盖新旧父级二选一、统一方向根、精确提案/地图、
严格确认命令、数据库并发唯一、计划 seed 到 TopicBrief 的精确父链、跨逻辑账号隔离与旧战略兼容；不得用
并行期间的旧数字替代最终回执。

## 回滚点

若新方向计划桥产生错误父级或注意力回归，可先停止从 `AccountDirectionVersion` 进入计划，保留已封存工件
可读，并继续允许具体选题直接从确认方向进入内容链。不得通过恢复 `develop_account_strategy` 默认工具、按根
猜最新地图或删除历史工件回滚。
