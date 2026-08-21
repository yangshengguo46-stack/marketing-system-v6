---
id: ADR-044
status: accepted
date: 2026-08-22
related:
  - A128-agent-owned-incubation-routing.md
  - A134-current-architecture-and-loop-reconciliation.md
  - ADR-040-agent-owned-incubation-routing.md
---

# ADR-044 用薄账号方向工件连接自主 Lead 与长期运营

## 决定

保留 ADR-040 的自主 Lead，不恢复 `develop_account_strategy` 固定认知流程。新增一组薄、追加式、逻辑账号
作用域的账号方向工件，连接首轮聊天判断与后续内容运营：

```text
AccountDirectionProposal
-> 用户明确选择或确认
-> AccountDirectionVersion
-> 可选 ContentMapCandidate / TopicBrief / AccountLaunchPlan
```

提案保存营销主体原话、业务目标、内容受众假设、长期内容主体、账号角色、表现方向、业务连接、变现假设、
依据、未知、备选与 Lead 推荐。字段允许不完整；缺失形成未知，不构成语义硬门。

## 权责

- Lead 负责业务理解、候选路线和推荐理由。
- 确定性代码只负责认证、项目/逻辑账号作用域、原话绑定、Schema、版本、哈希、幂等和用户确认。
- 内容地图、对标和受众观察是可选父级或后续证据，不是创建方向提案的前置条件。
- 用户确认生成新工件，不修改旧提案；新证据修订生成更高版本并记录原因。
- 内容循环可读取确认方向的有界编辑投影，但不得因热点、单条选题或形式适配自动修改账号方向。

## 兼容策略

旧 `IncubationJudgment` 及其地图父级保持只读兼容，直到已存数据完成投影或迁移验收。旧
`develop_account_strategy` 不重新注册；旧确认和起号计划工具先进入延迟发现，待新桥能够提供等价父对象后
再替换或退役。

## 不采用

- 不让 Gateway 或 Middleware 从最终回答中偷偷抽取营销结论。
- 不要求每次起号都先跑受众表、拆词、地图、对标或多路线。
- 不把聊天文本、Memory 或摘要当作账号长期真相源。
- 不修改旧 `IncubationJudgment` 使地图字段可空后继续叠兼容分支。
- 不把账号方向、内容地图和单条选题合并成一个万能工件。

## 理由

现役 Agent 已能在黄金礼品等案例中形成可用方向，继续调 Prompt 不能解决跨轮复用。真正缺失的是一个不
夺取营销判断权的持久化接缝。单独新建薄工件比放松旧地图绑定合同更清楚，也避免第四版式的流程回流。
