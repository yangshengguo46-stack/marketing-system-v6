---
id: ADR-052
status: accepted
date: 2026-08-23
related:
  - ../audits/A144-agent-foundations-reference-library-and-v6-conformance.md
  - ../audits/A147-sourced-user-profile-projection.md
  - ADR-049-agent-foundation-and-context-layering-standard.md
  - ADR-051-content-free-context-manifest.md
---

# ADR-052 用显式、有来源的最小 UserProfile 建立员工连续性

## 决定

第六版新增独立于项目台账和通用 Memory 的用户级 `UserProfile`。它只保存用户明确说过的稳定跨项目事实与协作偏好，
支持 `remember / replace / forget`，并以追加式、内容寻址修订保存来源。

模型只能通过 Lead 专属 Tool 引用当前最后一条可见用户消息中的精确片段发起修改。每次 Lead 模型调用投影一份
2,400 字节以内的当前档案；当前用户消息优先。子 Agent 不获得修改 Tool，画像也不提供任何执行权限。

## 依据

- 员工连续性需要少量稳定用户信息，但不需要把聊天历史全部升级为长期事实；
- 项目、账号和产品会变化，必须继续由业务台账和版本父级管理；
- 精确原文和不可变修订使错误记忆可追溯、可纠正、可删除；
- 小上限和完整有界投影比首版引入向量检索更可检查；
- owner-token-bound Manifest 投影能证明某次调用使用了哪版画像，而不复制正文。

## 后果

- `.deer-flow/users/{user_id}/profile/revisions/` 成为用户档案唯一存储；旧全局 `USER.md` 不参与默认 Lead；
- `manage_user_profile` 是 Lead 内建能力，不能出现在原生子 Agent 工具集中；
- `ContextManifest` 增加画像版本、哈希和数量，不增加正文；
- 自动提取、相似度检索、跨用户学习和前端管理留给后续独立评测；
- 通用 DeerMem 仍可独立配置，但不能冒充项目真相或 UserProfile 的来源合同。

## 不采用

- 不自动把每轮聊天或摘要写成用户档案；
- 不保存模型推断、项目事实、一次性任务或权限；
- 不用向量数据库解决 16 条以内的稳定档案；
- 不把画像写进产品身份、核心 Prompt 或行业 Skill；
- 不让画像修改 Tool 成为子 Agent 的共享能力。
