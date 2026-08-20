# A120 行业 Skill 硬门独立审计

- 日期：2026-08-21
- 状态：reviewed
- 审计对象：`048ad1e2 feat: govern vertical incubation skills`
- 上游：A116-A119、ADR-033、ADR-034
- 方法：独立子智能体只读审查调用链、Git 历史、现役实现与聚焦测试

## 结论

按需行业 Skill、一次最多激活一个、包完整性校验、事实边界和用户最终确认可以保留。但礼赠 Skill
当前不只是向总脑提供行业先验，而是形成了四层营销硬控：Profile 写入默认答案、确定性代码覆盖模型
选根、提示词禁止局部分支、最终 Draft 再按自然语言子串整体拒绝。这与第四版“多个层同时拥有营销
判断权”的失败模式同构，只是污染范围缩小到了单个行业 Skill。

相关测试通过只能证明这些硬门按设计工作，不能证明营销判断正确。

## 主要发现

### P1 局部分支被实现成全局禁词

内容地图提示禁止生成未激活局部分支，随后运行时删除含 marker 的地图字段；账号判断又要求所有字段
都不得重新引入，并将完整 Draft 序列化后做子串拒绝：

- `backend/packages/harness/deerflow/content_intelligence/analyzer.py:559`
- `backend/packages/harness/deerflow/content_intelligence/analyzer.py:1871`
- `backend/packages/harness/deerflow/incubation/judgment_runtime.py:174`
- `backend/packages/harness/deerflow/incubation/judgment_runtime.py:320`

因此“婚礼只是人情世界中的一个支持分支”“不要把婚礼作为长期主线”也无法持久化。现役行为实际是
“任何地方都不能出现婚礼”，而不是“婚礼可以出现，但不能抢占人情世故这个长期内容根”。

### P1 Skill 默认根会覆盖模型判断

Skill 包加载会验证版本和验收回执，却不验证当前请求是否真正满足 `applies_to` 与
`does_not_apply_to`。根裁决完成后，`default_root` 又会确定性覆盖模型选择：

- `backend/packages/harness/deerflow/tools/builtins/account_incubation_tool.py:145`
- `backend/packages/harness/deerflow/content_intelligence/analyzer.py:1831`
- `skills/public/incubate-gift-human-relations/references/incubation-profile.json:27`

因此一次错误 Skill 路由可以直接锁死内容根，Skill 实际取得了总脑本应独占的营销判断权。

### P2 关键词否定分类无法承担开放语义

`_mentions_marker_positively` 使用分句和有限正则判断 marker 是否被正向激活：

- `backend/packages/harness/deerflow/content_intelligence/incubation_skill.py:374`

独立探测发现“这不是婚礼业务”“婚礼不是我们的业务”“婚礼可以作为案例但不能做长期根”仍可能被
判为正向激活；`婚宴`、`喜宴`、`婚俗`等近义场景又会漏检。`五金`还可能指五金行业，`三金`也可能
处于非婚嫁语境。词表适合作为待审行业知识，不能作为自然语言 denylist。

地图链使用模型抽取的 `source_object` 判断，账号路线链使用完整 `user_request` 判断，同一请求还可能
得到不同边界。

### P3 A119 对影响范围的描述不准确

A119 声称否定作用域只决定局部分支是否激活、不参与内容根或营销判断；现役代码实际上会改变候选资格、
删除地图节点并拒绝账号路线。本审计修正该结论，不回写历史审计文本。

## 最小修正边界

保留：

1. Skill 延迟发现、单 Skill 上限与生命周期。
2. Schema、路径、大小、版本、摘要、评测和回执完整性校验。
3. 用户原话隔离、`do_not_assume`、事实与父工件边界、用户最终确认。

降级为软先验：

1. 将 `default_root` 改为不具否决权的 `preferred_root_candidate`。
2. 将局部分支改为带稳定 ID、理由和 `suggested_scope=local_branch` 的候选关系。
3. `candidate_paths` 与 `selection_principles` 只参与模型比较，不能覆盖最终根。

删除：

1. `_mentions_marker_positively` 的运行时营销裁决职责。
2. 内容地图中的 marker 子串删除。
3. 账号 Draft 全文子串拒绝。
4. “任何字段不得重新引入局部分支”的提示词要求。

结构化代码只校验候选 ID、父子关系、版本，以及已标记为局部分支的节点不能冒充
`primary_root_candidate_id`。内容地图可以保存 `supporting_branch_ids`，从而表达“可以讲婚礼，但婚礼
只是人情世故世界中的一个分支”。

## 必要测试

1. 路线提到婚礼作为支持分支、主根仍是人情关系时，必须成功持久化。
2. 同一分支被提升为 `primary_root` 时才触发层级校验，证明检查的是结构而非词面。
3. 覆盖否定、部分允许、近义场景以及“五金行业”“五险三金”等歧义表达。
4. 错选礼赠 Skill 时不得锁死人情根；无 Skill 基线仍能完成判断。
5. 用退休、节庆、乔迁、丧葬等留出场景验证“局部分支不抢根”的泛化。
6. Skill 与无 Skill 采用盲评比较长期根、业务连接与支持分支，禁止以“输出未出现 marker”作为营销
   正确性的验收条件。

## 验证与边界

- 独立审计聚焦测试：`139 passed`。
- 审计前后工作树干净，子智能体没有修改运行时代码。
- 本轮结论是架构审计，不代表修正方案已实现或通过真实端到端验收。
