---
id: A60
status: implemented_contract_runtime_pending
reviewed_at: 2026-08-17
decision: adopt_versioned_brief_and_incubation_judgment
sources:
  - docs/content-intelligence-v6/IMPLEMENTATION_PLAN.md
  - docs/content-intelligence-v6/decisions/ADR-018-artifact-graph-orchestration.md
  - backend/packages/harness/deerflow/incubation/contracts.py
  - backend/packages/harness/deerflow/incubation/content_run.py
---

# A60 项目事实与孵化判断谱系

## 问题

现有链已经能把用户原话、冻结地图、取证选题、讲述策划和基础文案写入项目台账，但
`MessagePlan.account_position_basis` 仍绑定整句当前请求。定位、受众、人设、账号级表现形式和变现
没有独立、可修订、可引用的业务对象，因此后续选题无法区分用户事实、Agent 假设和已经采用的账号判断。

## 决定

- `IncubationBrief` 只保存用户明说或授权观察得到的项目事实，以及资源、能力、限制、目标、偏好和未知。
  信息可以不完整；缺失产生未知，不形成问卷硬门。
- `IncubationJudgment` 分开保存定位、受众假设、人设、账号级表现形式和变现假设。每一项保留理由、
  置信度、未知和父产物引用，不把其中任何一项写回语义或内容地图。
- 账号级表现形式只回答该账号可持续使用哪些表达形态；单条内容的口播、短剧、图文、访谈或纯素材
  仍由后续 `FormatDecision` 决定。
- 变现只描述待验证的信任与承接路径，不进入内容地图、TopicBrief 或基础文案。
- 判断必须以同项目的 `incubation_brief + content_world` 为父级，可以额外引用对标和受众证据；
  `content_map_version_id` 不一致或引用未绑定父产物时确定性拒绝。

## 验证与边界

合同、封存和谱系测试为 `6 passed`；与现有项目台账、内容地图和内容纵切联合回归为 `24 passed`。
当前只完成领域合同和项目谱系，尚未实现从真实会话自动构造 Brief、调用模型形成判断、用户审阅或让
TopicBrief 引用已采用判断。因此状态不是“完整孵化脑已完成”，下一步仍需运行时接线与真实案例验收。
