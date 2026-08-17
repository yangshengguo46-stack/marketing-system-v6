---
id: A77
status: implemented_real_partial
reviewed_at: 2026-08-18
decision: adopt_progressive_discovery_and_separate_fixed_overhead_from_pipeline_cost
sources:
  - backend/packages/harness/deerflow/agents/lead_agent/prompt.py
  - backend/packages/harness/deerflow/config/tool_search_config.py
  - backend/packages/harness/deerflow/tools/builtins/tool_search.py
  - config.example.yaml
  - frontend/src/core/settings/input-mode.ts
  - backend/tests/test_lead_agent_prompt.py
  - backend/tests/test_tool_search.py
  - backend/tests/test_deferred_setup.py
  - frontend/tests/unit/core/settings/input-mode.test.ts
  - docs/content-intelligence-v6/evidence/lead-context-overhead-a77-2026-08-18.md
---

# A77 Lead 固定上下文开销

## 故障

真实新会话只输入“你好”，没有调用工具或子 Agent，却在一次模型调用中产生
`14,695` 个输入 Token、`54` 个输出 Token。检查点中的实际对话仅约 63 Token，说明绝大部分
消耗来自每轮重复发送的系统提示、工具 Schema 和 Skill 元数据，而不是用户内容或业务推理。

同时，前端在支持思考的模型上把未设置的模式自动解析为 `pro`，使普通新会话默认启用计划模式；
本地配置又关闭了 Tool Search 和 Skill 延迟发现，因此 23 份 Skill 元数据、16 个抖音 MCP Schema、
17 个常用工具 Schema 和冗长 Lead 使用说明一并常驻。

## 修正

- 新会话未显式选择模式时，支持思考的模型默认使用 `thinking`；用户明确选择的 `pro` / `ultra`
  保持不变，不支持思考的模型仍回落到 `flash`。
- 第六版发行配置启用 `tool_search` 与 `skills.deferred_discovery`。
- `tool_search.defer_tools` 允许操作方把明确命名的本地工具和 MCP 工具一起延迟披露；孵化、语义、
  内容地图和证据入口仍保持即时可见。
- Lead 常驻提示只保留身份、事实边界、权限、澄清边界和内容孵化路由合同，删除重复示例与工具手册。
- 新增常驻提示 `9,000` UTF-8 字节上限，防止详细使用说明再次悄悄堆回每次模型调用。

延迟发现只减少模型每轮看到的 Schema，不改变工具授权。工具被发现或自动提升后仍经过原有权限、
Skill 策略和执行护栏；找不到延迟目录时保持 fail-closed。

## 真实测量

同一 GLM 模型、全新会话、输入“你好”的固定输入开销逐步下降：

| 运行 | 输入 Token | 相对原始值 |
| --- | ---: | ---: |
| 原始第六版 | 14,695 | 100% |
| 默认 Thinking + Skill/MCP 延迟发现 | 9,606 | 65.4% |
| 再延迟通用本地工具 | 5,503 | 37.4% |
| 再压缩 Lead 常驻提示 | 3,879 | 26.4% |

最终一次输出 `156` Token，总计 `4,035` Token；固定输入较原始值减少 `10,816`，即 `73.6%`。
这里没有增加“你好”本地短路或绕过模型，因此结果仍反映完整 Agent 的真实最低入口开销。

## 核心能力回归

压缩后用“我是做黄金礼品的，我要怎么起号？”做真实回归。系统把“黄金礼品”迁移到
“人际馈赠”，没有退回黄金工艺或产品展示；但最终选题落在彩礼嫁妆，地图仍被婚礼馈赠主导。
用户复核明确判定失败：这只是把“三金”改写成“婚礼馈赠”，没有继续进入“礼、人与人相处和社会
秩序”。因此这次回归只能证明渐进披露没有让工具失效，不能证明孵化主链成立。

该复杂运行仍消耗约 `54.3K` 输入、`15.2K` 输出，耗时 7 分 42 秒。它来自语义、地图、搜索、
证据阅读、选题与表达的多次真实认知调用，属于“管线开销”，不能和“你好”每轮固定注入的浪费混为
一谈。该语义失败由 A78 继续追踪；A77 的性能结论不依赖这次业务回归是否通过。

## 当前结论

- “你好”上万 Token 是真实架构故障，不是正常推理成本。
- 固定入口开销已降低 73.6%，并有配置、单测和提示体积预算防回退。
- 最初黄金礼品回归未通过业务验收，不能用来替固定上下文优化背书。
- 下一轮性能工作应测量各认知节点的独立输入、输出、缓存命中和重复证据，而不是继续删核心合同或
  给简单问候做伪快路径。
