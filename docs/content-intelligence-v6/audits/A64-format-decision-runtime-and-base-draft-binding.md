---
id: A64
title: 表现形式运行时与基础稿绑定
status: implemented
date: 2026-08-17
---

# A64 表现形式运行时与基础稿绑定

## 发现

A62 首版把 `FormatDecision` 只挂在 `MessagePlan` 上，与 ADR-018 的
`MessagePlan -> BaseDraft -> FormatDecision` 生产顺序不一致。这样即使基础稿后来变化，形式决定仍可能
看起来有效，也会把“写了什么”和“怎么呈现”拆成两条兄弟线。

## 修正

- `FormatDecision` 现在同时绑定精确 `MessagePlan` 和由它直接派生的
  `draft_version(stage=base)`，保存基础稿身份、内容哈希和正文哈希。
- 父级项目、类型、`message_plan_id`、直接谱系和基础稿阶段都在模型调用前校验；错误输入不会消耗一次
  形式判断，也不会封存半份结果。
- 薄运行器只读取有界 MessagePlan、BaseDraft、可选孵化判断和最多八份已封存用户素材观察。
  对标证据不能冒充用户已有素材；总输入不超过 32,000 UTF-8 字节。
- 模型只返回 `FormatDecisionDraft`。它不能改写基础稿、选题、观点或证据，也不能加入平台、销售、发布、
  固定时长、镜头数、条数、频率和配额。资源未知时保持 `provisional`。

## 验证

领域合同与运行时聚焦回归 `41 passed`；Ruff、格式和差异检查通过。当前已具备真实生成服务，但尚未接入
`explore_content_world` 的项目运行链，也未生成形式适配稿、素材方案或 MediaArtifact，因此仍是
`implemented`，不是端到端完成。
