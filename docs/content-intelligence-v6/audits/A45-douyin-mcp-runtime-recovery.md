---
id: A45
status: reviewed
reviewed_at: 2026-08-17
decision: restore_existing_mcp_runtime_without_reimplementation
sources:
  - docs/content-intelligence-v6/LEDGER.md
  - docs/content-intelligence-v6/decisions/ADR-010-douyin-openapi-mcp-capability-router.md
  - docs/content-intelligence-v6/audits/A41-douyin-official-first-evidence-routing.md
  - docs/content-intelligence-v6/audits/A42-douyin-public-benchmark-candidate-aggregation.md
  - docs/content-intelligence-v6/audits/A43-douyin-benchmark-lead-tool.md
  - git: f752d3a1, 762e1886, 8f43f91a, 8c749d0d
---

# A45 抖音 MCP 运行配置恢复审计

## 问题

第六版已经实现抖音 OpenAPI MCP，但当前 Gateway 报告零个 MCP 工具。需要判断这是代码缺失、
能力回退，还是本地运行配置断线。

## 发现

1. Git 与 A27 证明 `douyin-openapi-mcp` 已完成真实 MCP 协议初始化，并提供 16 个领域工具。
2. A41-A43 已完成 v2 视频搜索、候选聚合和 Lead 高层工具，均明确等待本地真实授权回执。
3. 当前仓库缺少被忽略的 `extensions_config.json`，Gateway 因而以空 MCP 配置启动。
4. 恢复现有配置后，Gateway 与 Agent 均加载 16 个 MCP 工具；无需重写 API、网页采集器或
   新的业务工具。
5. MCP 是能力与鉴权边界，不是免授权代理。应用身份尚未绑定时，搜索 Child 正确返回
   `auth_not_configured`，且不发送网络请求。

## 决定

- 恢复并继续使用既有 `douyin-openapi-mcp` 主链。
- 运行配置保持本地、未跟踪；密钥不写入 Git、台账、日志或模型上下文。
- 下一项验收只做现有应用身份绑定与官方 v2 真实回执，不另造连接器。
- 以后恢复工作时先核对最新台账、提交和运行配置，不能由当前运行故障反推历史实现状态。

## 状态

`reviewed -> runtime restored; live credential verification pending`
