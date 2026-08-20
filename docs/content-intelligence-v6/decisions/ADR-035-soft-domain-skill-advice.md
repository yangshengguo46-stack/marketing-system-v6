---
id: ADR-035
status: accepted
date: 2026-08-21
decision: domain_skills_supply_soft_reviewable_advice_and_never_override_marketing_judgment
supersedes:
  - ADR-033 default-root authority
  - ADR-033 inactive-branch exclusion
---

# ADR-035 行业 Skill 只提供软先验

## 决策

保留 DeerFlow 的按需行业 Skill、一次最多一个 Skill、生命周期、完整激活包、事实边界和用户确认。
废止 ADR-033 中“版本化默认根覆盖通用裁决”和“未激活局部分支贯穿全链排除”两项设计。

Profile schema v3 只向内容根裁决提供：

- 可审查的 candidate_paths 与 selection_principles。
- 可拒绝的 preferred_root_candidate。
- 带稳定 ID、理由和 suggested_scope=supporting_branch 的分支提示。

applies_to、does_not_apply_to 只属于 Skill 路由。行业 Profile 不再拥有 do_not_assume 或其他事实
否定项；用户事实、能力、资源和未知只由通用项目 Brief 管理。以上路由字段以及 Skill 名、版本、生命周期、
来源和完整 Profile 哈希均不进入内容根模型上下文。模型显式选择的 content_entry 与 map_root 是营销
判断结果，代码不得再用 Profile 默认值或已复核共同世界覆盖。

## 机械边界

确定性代码继续校验 Profile 版本、大小、哈希、路径、候选索引、父工件和生命周期。它不再：

- 扫描用户自然语言判断某个分支是否“激活”。
- 删除含行业 marker 的地图字段。
- 因 Draft 出现某个词而整体拒绝账号方案。
- 在模型裁决后替换内容根。
- 向项目 Brief 注入行业 Profile 预设的事实否定项。

旧 IncubationBrief.excluded_content_branches 在读取历史工件时被丢弃，不再传播到新模型输入或新工件。
通用 example_branch 层级合同仍可阻止一个已经结构化标记为例子的节点冒充根，但行业 Skill 不得根据
关键词替节点写入该层级。

## 理由

A120 证明 v2 同时由 Profile、提示词、地图过滤和账号 Draft 校验控制营销判断，重现了第四版多层硬门
冲突。v3 的真实 GLM 验证表明，软候选足以让黄金礼品收敛到“人与人之间的相处与人情世故”；明确经营
婚礼伴手礼时，原始业务与局部地图路径也能保留，不再被关键词规则删除。该次真实运行仍选择较宽总根，
说明无需自然语言 denylist，但软偏好强度仍须继续校准。

## 后果

- 行业经验仍能影响注意力，但可能被模型有理由地拒绝。
- 错选 Skill 不再锁死内容根，错误影响被限制为可见的候选偏置。
- 局部场景可以作为支持内容存在，不再通过“完全不出现某词”伪装成正确性。
- 正确性依赖行为评测与真实留出，不再由硬门测试代替。
- 当前成功真实链仍需 79.3 至 108.776 秒、13262 至 17047 tokens；一个留出案例在节点修复耗尽后
  还需要有记录的整链重试。本 ADR 不处理性能优化或外层恢复策略。

实现与真实记录见 A120、A121 及礼赠 Skill 的 acceptance-evidence.json。
