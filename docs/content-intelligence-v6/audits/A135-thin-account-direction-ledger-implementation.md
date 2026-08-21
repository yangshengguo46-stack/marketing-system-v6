---
id: A135
status: adopted
date: 2026-08-22
sources:
  - A134-current-architecture-and-loop-reconciliation.md
  - ADR-044-thin-account-direction-ledger-bridge.md
  - backend/packages/harness/deerflow/incubation/account_direction.py
  - backend/packages/harness/deerflow/tools/builtins/account_direction_tool.py
  - backend/packages/harness/deerflow/tools/builtins/content_intelligence_tool.py
  - backend/packages/harness/deerflow/incubation/content_run.py
  - backend/tests/test_account_direction.py
  - backend/tests/test_account_direction_tool.py
---

# A135 薄账号方向台账桥实施审计

## 本轮目标

补上 A134 找到的入口断链，但不恢复第四、第五版式的强制孵化管线。Lead 继续自主完成营销判断；代码只把
值得跨轮延续的判断变成可确认、可追溯、可修订的账号级业务对象。

## 已落地对象

```text
AccountDirectionProposal
  - 绑定最近一条真实用户原话
  - 允许 1 至 3 个完整方向
  - 只是候选，不产生当前方向

用户明确确认 proposal_artifact_id + option_id
  -> AccountDirectionVersion
  - 保存本次确认的真实用户原话
  - 成为当前逻辑账号的有效方向
  - 后续修订生成更高版本
  - 旧版本和旧提案保持不可变
```

一个方向只有名称、长期内容主体和理由是必填项。受众假设、长期承诺、人设、表现方向、业务连接、变现
假设、未知和取舍都可以缺失；缺失不会形成语义硬门。提案不要求已有内容地图、对标快照、受众工件或平台
账号。

## 权限与事实边界

- 工具不接收 `user_request` 参数，而是从运行状态中读取最近一条真实 `HumanMessage`，优先使用中间件保存的
  `original_user_content`。提案和确认分别保存各自对应的真实用户原话，模型不能用工具参数替换它们。
- 无项目的首次正式提案可以创建确定性的线程级隐式项目和逻辑账号；普通聊天不会创建。已经显式选择但实际
  不存在的项目或账号不会被工具补建。
- 候选方向的 ID 由代码按提案内顺序生成。确认必须同时携带最新提案回执和其中一个准确方向 ID；旧提案、
  陌生方向或不同逻辑账号都会失败关闭。
- 内容寻址使相同提案和相同确认幂等；修订必须写原因，完全不变的单路线不能伪装成新版本。
- 当前单 Gateway 进程会按提案串行确认；同一提案的两个冲突选择只能有一个成功，重放同一选择返回原工件。
- 读取端发现同一修订存在两个不同方向工件时失败关闭，不按时间静默挑选一个。
- 可选依据只能引用同一项目、同一逻辑账号中的现存工件，并作为父级回执保存。

## 与内容循环的连接

现役 `explore_content_world(one_shootable_topic)` 会按需读取当前 `AccountDirectionVersion`，只投影以下编辑
上下文：

```text
方向 ID
长期内容主体
内容受众假设（可空）
长期承诺（可空）
账号角色（可空）
```

该投影同时进入选题取证和 MessagePlan/BaseDraft，但不包含变现假设，也不能修改内容根、替换 TopicBrief
或补造用户经历。生成的 `message_plan` 保存当前方向工件为父级，因此可以追溯“这条内容沿用了哪版账号
方向”。账号方向不绑定某一张内容地图；内容循环仍可为当前具体问题按需生成地图。

旧 confirmed `IncubationJudgment` 和精确地图重水化保持只读兼容。当新旧两种方向同时存在时，新
`AccountDirectionVersion` 的编辑投影优先；旧地图仍可作为该次选题的候选材料。内容循环不会自动创建、
确认或修订账号方向。

## 工具与注意力预算

- 新增 `propose_account_direction` 与 `confirm_account_direction` 两个高层工具。
- 两个 Schema 默认进入 `tool_search.defer_tools`，普通聊天和普通首轮模型调用不背负完整合同。
- Lead Prompt 只规定何时值得落账、候选不等于确认、一条完整路线也合法；没有新增固定提问顺序、固定地图、
  对标数量、路线数量或 7/30 天计划。
- 旧 `develop_account_strategy` 仍不注册；旧确认和起号计划继续仅作历史兼容，不是新主路径。

## 明确未做

- 没有迁移旧 `IncubationJudgment` 数据，也没有删除旧兼容代码。
- 没有让新方向自动复用或冻结某一张内容地图。
- 没有把新方向接入旧 `AccountLaunchPlan`，该对象仍依赖旧地图绑定策略。
- 没有修改对标 Provider、MediaKit、制作、发布、回执或学习循环。
- 没有新增数据库表或迁移；现有通用不可变工件表已经能够保存这两类对象。
- 进程内确认锁不是多副本分布式锁。未来若水平扩展多个 Gateway，生产发布前仍须增加数据库租约或“每个提案
  只能确认一次”的唯一声明；本轮不把单进程保证冒充多实例保证。

## 验证范围

测试覆盖：无地图提案、不完整字段、一条路线、候选不生效、精确确认、幂等重放、修订原因、无变化拒绝、
跨账号依据拒绝、真实用户原话绑定、隐式作用域、无效合同不遗留空项目、显式缺失项目失败关闭、单进程冲突
确认原话绑定、确认串行、冲突修订失败关闭、真实 SQLite 往返、新方向研究投影、基础稿立场、消息父级回执、
旧孵化判断兼容和延迟工具配置。

## 验收回执

- 账号方向、内容链和旧兼容相关回归：`123 passed`。
- Harness、孵化架构、Lead Prompt、导入边界、Gateway 项目投影和配置回归：`92 passed`。
- 后端全部非联网测试：`12473 passed, 75 skipped, 0 failed`；跳过项为既有条件性测试，本轮没有新增失败。
- 变更 Python 文件通过 `ruff format` 与 `ruff check`，仓库补丁通过 `git diff --check`。

本审计记录的是一座最小连接桥，不宣称完整孵化循环已经结束。下一步应先真实运行一次“起号请求 -> 方向
提案 -> 用户确认 -> 同账号具体选题”，再决定是否迁移旧起号计划。
