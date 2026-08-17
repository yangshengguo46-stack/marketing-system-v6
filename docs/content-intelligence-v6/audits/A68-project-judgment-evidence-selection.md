---
id: A68
status: implemented
date: 2026-08-18
---

# A68 项目孵化证据选择

## 目的

孵化判断需要对标与受众证据，但不能把选题搜索、用户素材、候选账号、浏览器原文或普通阅读记录混入。
A68 增加一层纯确定性的项目证据选择，不调用模型和网络。

## 规则

- 所有输入必须属于精确同一项目，跨项目输入直接拒绝。
- 对标只接受通过现有 `BenchmarkSnapshot` 合同验证、角色为 `benchmark_evidence` 的正式快照。
- 受众只接受通过现有 `EvidenceSnapshot` 合同验证、角色为 `owned_audience_observation` 或
  `benchmark_audience_observation` 的正式快照。
- `topic_evidence`、`user_material`、`benchmark_account_candidate`、浏览器原始内容与
  `content_reading` 均不进入孵化判断证据。
- 选择结果稳定去重、最新优先，对标与受众各最多两份；截断、近似但不合格的候选和缺失情况都留下限制说明。
- 没有正式证据时返回 `missing`，但不形成语义或孵化硬门。

## 验证

选择器测试 `6 passed`，与孵化判断运行时联合回归 `14 passed`；Ruff、格式和差异检查通过。
该模块尚未由内容工具自动读取项目产物，主链编排继续进行。

