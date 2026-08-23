---
id: A146
status: reviewed
date: 2026-08-23
sources:
  - A143-effective-agent-context-and-deerflow-residue-audit.md
  - A144-agent-foundations-reference-library-and-v6-conformance.md
  - A145-product-identity-and-explicit-skill-lifecycle.md
  - ../decisions/ADR-049-agent-foundation-and-context-layering-standard.md
  - ../decisions/ADR-051-content-free-context-manifest.md
  - backend/packages/harness/deerflow/agents/middlewares/context_manifest_middleware.py
  - contracts/run_event_stream_contract.json
  - backend/tests/test_context_manifest_middleware.py
---

# A146 Shadow-only ContextManifest

## 问题

A77、A129 和 A143 多次证明，只统计核心 Prompt 字面大小会漏掉动态系统消息、历史、隐藏消息、
Skill、Tool Schema、结构化输出和重试。因此无法稳定回答“一句你好为什么消耗这么多 Token”，
也无法证明某次运行真正使用了哪版产品身份和哪个 Skill。

## 实现

`ContextManifestMiddleware` 位于 Lead 请求变换链的最终观测边界。每次真正调用供应商都追加一条
`context:manifest` 运行事件，包含：

- 产品身份是否存在、资源来源、版本和内容哈希；
- 模型名称、类型和设置键名；
- 消息数量、按角色的 UTF-8 大小、隐藏上下文分层大小；
- 可见工具名、单项 Schema 大小/哈希、工具目录哈希与结构化输出 Schema 大小/哈希；
- 摘要、委派和已检查 Skill 的状态计数；
- 当前 Run 的 Skill 激活模式、名称和内容哈希；
- 供应商返回的输入、输出、总 Token 和缓存命中用量（如有）；
- 失败时只记录异常类型，不记录报错原文。

中间件不改写 `ModelRequest`、不决定工具、不触发 Skill、不作业务评分或拦截。多次物理调用各有
`call_index`，所以重试或工具循环不会被合并成一笔模糊开销。

## 隐私与精度边界

清单不保存消息正文、Tool 描述/参数、Skill 路径、Cookie、API Key、runtime secret 或供应商报错原文。
`estimated_payload_utf8_bytes` 是 DeerFlow 对最终消息、Tool Schema 和输出 Schema 的可重建字节估算，不等于
供应商序列化后的网络包，也不等于 Token。只有 `response_usage` 是供应商返回的 Token 证据；供应商未返回时保留
`null`，禁止伪造精确用量。

## 验收

- 内容泄露、Skill 路径、报错正文、同步/异步、实际 Token 和多次调用测试通过；
- 真实 Lead 中间件装配、`MODEL_PHYSICAL` 扩展边界、RunJournal 和 JSON 契约聚焦回归 `204 passed`；
- 关闭可选 Safety 中间件时仍使用稳定 Manifest 主锚点，真正缺失主锚点的底层告警测试保留；
- 本轮没有改动产品身份正文、营销方法、孵化对象、工具可见性或模型输出。

下一步是 UserProfile：先定义有来源、可纠正、有作用域的用户稳定事实，再借助 Manifest 证明每次任务实际投影了多少，
禁止把所有历史对话自动升格为用户档案。
