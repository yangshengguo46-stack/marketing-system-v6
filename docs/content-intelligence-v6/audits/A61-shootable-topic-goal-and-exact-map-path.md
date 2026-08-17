---
id: A61
title: 可拍选题目标与精确地图路径审计
status: implemented
date: 2026-08-17
---

# A61 可拍选题目标与精确地图路径审计

## 问题

第六版已经能够形成长期内容地图和证据选题，但运行时把“只看长期定位”和“给一个今天能拍的
选题”当成同一种回答。研究阶段还会把一条完整路径压扁为“内容根 -> 最终实例”，导致地图已经
走到作品、人物或事件，最终选题却重新变宽。用户点名热点、人物、作品或问题时，失败路线还可能
静默换成另一个普通地图选题。

## 决定

- `explore_content_world` 显式区分 `long_term_positioning` 与
  `one_shootable_topic`。普通“怎么起号”默认继续到一条具体可拍内容，同时保留长期定位依据；
  只有用户明确只问定位或内容疆域时才停在地图。
- 用户点名的 `topic_seed` 必须是当前原话中的连续逐字片段。它只作为
  `user_provided / unverified_lead_not_evidence` 进入命名召回，不能自行成为证据。
- 命名候选必须绑定冻结地图中真实存在的 `dimension + map_path_id`。证据阅读和
  `TopicBrief` 保留该路径的全部中间节点，再把最后一个已取证对象接到路径末端。
- 用户题眼未被公开证据和冻结地图共同验证时，返回明确未知；禁止拿另一个普通地图题替换。
- 可拍目标在研究、`TopicBrief`、`MessagePlan` 或 `BaseDraft` 任一处失败时明确报告
  “定位完成但未形成可拍选题”，不再把长期地图伪装成用户要求的成品。
- 成功交付把“今日建议拍摄”放在首位，长期定位只作为依据。此层仍不选择平台、表现形式、
  销售、实验或发布。

## 代码与验证

- `backend/packages/harness/deerflow/tools/builtins/content_intelligence_tool.py`
- `backend/packages/harness/deerflow/content_intelligence/research.py`
- `backend/packages/harness/deerflow/content_intelligence/contracts.py`
- `backend/packages/harness/deerflow/agents/lead_agent/prompt.py`
- `backend/tests/test_content_intelligence_tool.py`
- `backend/tests/test_content_intelligence_research.py`
- `backend/tests/test_content_intelligence_contracts.py`

聚焦回归覆盖回答目标、逐字题眼、无证据弃权、错误路线拒绝、精确路径保留、断裂路径拒绝及旧无题眼
行为，共 `90 passed`；上述代码通过 Ruff 与 `git diff --check`。这只验收结构与路由，真实模型案例
仍需单独回执，因此状态是 `implemented`，不是 `verified` 或 `production`。

## 对发布前主链的影响

A61 没有把系统缩成选题工具。它只修复发布前主链中的内容目标边界：

```text
长期孵化判断与内容地图
-> 一条精确地图路径
-> 公开证据
-> TopicBrief
-> MessagePlan
-> BaseDraft
```

下一步继续接 `IncubationBrief / IncubationJudgment` 运行时、单条 `FormatDecision`、素材方案、
MediaKit 制作和 `MediaArtifact`。`PreflightPrediction` 及之后仍按当前决定延期。
