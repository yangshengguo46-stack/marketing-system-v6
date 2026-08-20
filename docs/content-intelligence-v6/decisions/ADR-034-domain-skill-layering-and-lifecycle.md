---
id: ADR-034
status: accepted
date: 2026-08-20
decision: retain_deerflow_and_govern_domain_skills_as_progressively_loaded_evaluated_layers
---

# ADR-034 领域 Skill 分层与生命周期

## 决策

继续使用 DeerFlow 现有 SkillCatalog、`describe_skill`、`read_file`、工具权限、Skill 管理和评测设施，不引入
Superpowers、Deep Agents 或其他第二 Agent/Skill 运行时。

孵化能力固定为四层：

1. L0 通用孵化内核：事实、语义候选、内容根/地图合同、边界和最终收敛。
2. L1 `incubate-*` 行业 Skill：按需加载的行业语义与内容世界先验，一次最多一个。
3. L2 横向创作与运营 Skill：在内容根或账号路线确认后，按任务组合对标、选题、写作、表现形式和运营能力。
4. L3 确定性工具：抖音 MCP、MediaKit、HLLM、数据、持久化和发布，只提供证据、计算或执行。

Lead 保留唯一最终营销判断权。L1 不决定人设、形式和变现；L2 不重新选择内容根；L3 不产生营销结论。

## Skill 粒度

行业 Skill 按可跨多个商业对象复用的语义与内容世界机制组织，不按单个商品、单个案例或单一标准答案组织。
候选分类必须先在隔离评测中证明组合泛化，才能成为正式 Skill。一次请求不得自动叠加多个 `incubate-*`；
触发冲突时返回候选和不确定性，由 Lead 或用户选择，不能把冲突知识同时注入。

## 生命周期

行业 Skill 使用 `discovered -> candidate -> shadow -> active -> contested -> superseded/retired`。新 Skill 或
任何行为性修改必须先取得无 Skill 失败基线，再以最小修改运行有/无 Skill 对照、反触发、留出案例、事实边界、
真实端到端、成本和多次运行方差评测。单次成功不得进入 `active`。

机械约束使用 Schema、代码和测试；需要营销判断的内容保留在 Skill。每次变更生成新版本并保留旧证据，不得
静默覆盖已验收版本。

## 采用与拒绝

采用：

- Agent Skills 的渐进披露和标准元数据。
- Superpowers 的 Skill RED/GREEN/REFACTOR、对照评测和方差观测。
- 大型领域 Skill 库的版本、许可、Schema、fixture 和分层治理思路。
- 外部营销 Skill 中经逐项审计通过的横向方法。

拒绝：

- 全局强制 Skill 调用或固定业务工作流。
- 第二 Agent/Skill 运行时。
- 整包安装营销或社媒 Skill 库。
- 把行业样例、标准答案、对标数据或成功案例重新塞回通用提示词。
- 让工具、对标、案例记忆或行业 Skill 自动修改内容根和账号定位。

## 首批实施顺序

1. 为 `incubate-gift-human-relations` 补版本、来源、许可和触发/反触发评测，使 A116 的真实通过成为可重复验收。
2. 建立“食材与饮食世界”候选 Skill，用水果、海鲜、火锅底料的跨对象迁移验证正确粒度。
3. 审计第四、第五版营销与文案材料，只把通过对照评测的能力放入 L2。
4. 两个 L1 Skill 通过后再决定是否需要 Skill 注册状态和管理界面；不预建庞大行业库。

完整来源与对照见 `audits/A117-open-source-domain-skill-architecture.md`。
