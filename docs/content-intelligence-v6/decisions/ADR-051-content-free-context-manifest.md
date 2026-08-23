---
id: ADR-051
status: accepted
date: 2026-08-23
related:
  - ../audits/A143-effective-agent-context-and-deerflow-residue-audit.md
  - ../audits/A144-agent-foundations-reference-library-and-v6-conformance.md
  - ../audits/A146-shadow-context-manifest.md
  - ADR-041-selective-harness-reference-adoption.md
  - ADR-049-agent-foundation-and-context-layering-standard.md
  - ADR-050-explicit-run-scoped-skill-activation.md
---

# ADR-051 每次物理模型调用追加不含正文的 ContextManifest

## 决定

第六版 Lead 在所有模型请求变换完成后，为每次真实供应商调用追加一条 `context:manifest`。该投影
只用于身份、上下文、Skill、Tool Schema 和 Token 的运行对账，不改变模型请求或营销判断。

`ContextManifestMiddleware` 同时作为 Lead `MODEL_PHYSICAL` 扩展的稳定主锚点。扩展观察者位于其内侧，
看到同一份最终请求；它们必须保持只读。

## 数据边界

允许保存身份/Schema/目录哈希、大小、数量、模型/工具/Skill 名称、激活模式、调用结果和供应商 Token。
禁止保存消息正文、Tool 描述/参数、Skill 路径、凭据、runtime secret 或报错原文。

字节账是可重建估算，不宣称精确的供应商网络载荷或 Token。供应商没有返回 usage 时必须保留未知。

## 后果

- 可以从 RunEvent 按物理调用解释问候、重试、工具循环和长会话成本；
- 产品身份和 Skill 激活拥有可验证的运行版本投影；
- 用户内容不会为了调试而被再复制一份；
- 新的上下文来源应先在 Manifest 中拥有可识别的有界投影，再进入产品验收；
- 前端可视化、成本归因和子 Agent 清单是后续增量工作，本轮不强行扩大范围。

## 不采用

- 不把完整 Prompt 或聊天正文写入事件库；
- 不把 Manifest 变成业务门禁、打分器或 Prompt 改写中间件；
- 不把字节数假装成 Token；
- 不用清单取代 RunJournal、checkpoint 或孵化业务台账；
- 不因为可观测需求而提高模型上下文成本。
