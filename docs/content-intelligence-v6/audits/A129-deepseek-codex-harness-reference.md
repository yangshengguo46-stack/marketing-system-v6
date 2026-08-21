---
id: A129
status: reviewed
date: 2026-08-22
sources:
  - backend/AGENTS.md
  - backend/packages/harness/deerflow/agents/lead_agent/agent.py
  - backend/packages/harness/deerflow/agents/lead_agent/prompt.py
  - backend/packages/harness/deerflow/agents/middlewares/AGENTS.md
  - backend/packages/harness/deerflow/runtime/AGENTS.md
  - backend/packages/harness/deerflow/runtime/journal.py
  - https://github.com/deepseek-ai/deepseek-harness
  - https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/architecture.md
  - https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/subsystems/session.md
  - https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/subsystems/system-prompt.md
  - https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/subsystems/tools.md
  - https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/subsystems/compaction.md
  - https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/subsystems/subagent.md
  - https://openai.com/index/unrolling-the-codex-agent-loop/
  - https://openai.com/index/unlocking-the-codex-harness/
  - https://openai.com/index/harness-engineering/
  - https://github.com/openai/codex/blob/main/codex-rs/app-server/README.md
  - https://github.com/openai/codex/blob/main/codex-rs/skills/src/assets/samples/skill-creator/SKILL.md
  - ADR-041-selective-harness-reference-adoption.md
---

# A129 DeepSeek 与 Codex Harness 参考价值审计

## 问题

第六版已经建立在 DeerFlow Harness 上，但真实运行仍反复出现三类问题：

1. 模型行为可能同时受到系统提示、动态上下文、Skill、中间件、工具描述、历史消息和业务投影影响，出错后
   很难回答“这一句到底从哪里来的”。
2. 一个简单轮次也可能携带大量常驻上下文和工具 Schema；虽然已有 Token 统计，却不能按来源解释成本。
3. LangGraph checkpoint、`RunEventStore` 和孵化业务台账各自合理，但缺少一份统一的“本次模型实际看见了
   什么”清单，排障仍依赖逐层追代码。

本审计比较 DeepSeek Harness 与 Codex Harness，目标不是追新或换底座，而是判断哪些设计能直接减少第六版
的暗箱、堆叠和上下文浪费。

## Harness 到底是什么

Harness 不是营销脑，也不是另一个模型。它是模型外面的运行系统，负责：

```text
用户输入
-> 组装模型可见上下文和工具
-> 调用模型
-> 执行工具并回填结果
-> 重复直到模型完成
-> 保存会话、事件、审批、用量和恢复状态
```

营销判断仍由 Lead 和按需方法承担。Harness 的质量决定模型能看到什么、能做什么、失败后能否恢复，以及
我们能否解释一次回答为何产生。

## 三套实现对照

| 维度 | DeerFlow（现役） | DeepSeek Harness | Codex Harness | 对第六版的意义 |
|---|---|---|---|---|
| 核心循环 | LangGraph agent 加最多 35 个有序中间件 | 默认 Agent Loop 可替换，其他能力作为插件和 capability seam | 极简的模型/工具循环，外围由 Codex core 承担 | 不应再把营销判断塞进中间件 |
| 扩展方式 | Middleware、Tool、MCP、Skill、Subagent、Extension 并存 | “Everything is a plugin”；Definition / Provider / Consumer 三角色 | Core 加 Skills、MCP、Apps 和稳定客户端协议 | DeepSeek 的能力接缝适合统一搜索、媒体和平台 Provider |
| 会话事实 | checkpoint 保存 Agent 状态，`RunEventStore` 保存运行事件，业务台账保存孵化事实 | 追加式 `SessionEvent` 是会话单一事实源，模型历史由日志派生 | Thread 持久化，Append-only 对话输入和 Item 生命周期供客户端恢复 | 先做只读可重建投影，不立即替换 LangGraph 持久化 |
| 模型可见上下文 | 静态 Prompt、动态消息、Skill、工具 Schema 和摘要由多处组装 | 命名 Prompt Section、动态 Context 和工具贡献按次组装；“模型可见即入日志” | 尽量保持精确前缀，运行变化追加而非重写；Skill 渐进披露 | 建立 `PromptManifest`，逐项显示来源、哈希和字节数 |
| 工具执行 | 多层过滤、授权、净化、预算和错误中间件 | 一条 guard -> execute -> post -> canonical result 管线；Guard 只能收紧 | 工具顺序稳定、延迟发现、输出有界 | 保留 DeerFlow 安全层，但统一工具能力元数据和最终回执 |
| Skill | 已支持元数据发现、按需加载和工具策略 | Skill 是可选能力，Provider 与面向模型的 Consumer 分离 | 元数据常驻、正文触发加载、资源继续按需读取 | 延续渐进披露，禁止把行业知识重新塞回常驻 Prompt |
| 子 Agent | `task`、并发限制、委派台账和摘要 | 可选 seam，可并存 in-process、fork、Codex、Claude 等 Provider | 只建议具体、独立、非关键路径的 sidecar 任务 | 证据研究可并行，最终营销判断仍只归 Lead |
| 客户端协议 | Gateway、LangGraph 兼容路由和 SSE | 会话事件天然供重放和 UI 投影 | App Server 用稳定 Item/Turn 事件驱动 CLI、IDE、桌面和 Web | 前端应消费稳定业务/运行事件，不能解析模型散文猜状态 |
| 成熟度 | 已经承载第六版、回归与本地数据 | 官方明确为 developer preview，兼容性会破坏 | 成熟但为软件工程场景优化 | 两者适合参考；都不构成立即迁移理由 |

## DeepSeek Harness 最有价值的部分

### 1. 模型可见即有记录

DeepSeek 要求任何进入模型请求的内容都能由追加式会话事件重建。这个原则比“我们保存了聊天”更严格：
动态提示、压缩摘要和工具结果也必须能解释。

第六版不必立刻改成事件溯源，但应该能回答：

```text
这次模型看见了哪版基础提示？
加载了哪个 Skill 的哪一段？
有哪些动态上下文？
暴露了哪些工具及其 Schema？
历史、工具结果和业务投影各占多少 Token？
```

### 2. Capability seam

DeepSeek 把能力拆成三个角色：接口定义、实现 Provider、消费该能力的 Tool 或组件。它适合第六版已有的
同类异构能力：

```text
ResearchCapability
  -> Web / 豆包搜索 / 抖音搜索 Provider

BenchmarkCapability
  -> 抖音 MCP / 本地浏览器 Provider

MediaUnderstandingCapability
  -> MediaKit / HLLM Provider
```

Lead 只看到稳定的高层工具合同，不需要知道后面是哪种 Provider，也不会同时看见一堆重复工具。

### 3. 可选能力不是核心循环

压缩、子 Agent、Web 和 Skill 都是可选 seam，不应该占据 Agent Loop 的决策权。这个设计与第六版刚刚接受的
ADR-040 一致：方法可以被 Lead 调用，但不能重新成为固定阶段。

## Codex Harness 最有价值的部分

### 1. 核心循环保持简单

Codex 将 Harness 的中心描述为用户、模型和工具之间的循环。项目说明、Skill、沙箱、审批和客户端都是为
循环提供环境，而不是替模型决定每个任务必须走哪条业务流程。这是第六版最需要长期守住的边界。

### 2. 上下文是公共资源

Codex Skill 指南明确要求只加入模型本身不知道且任务真正需要的内容，并采用三级渐进披露：元数据常驻、
Skill 正文触发加载、资源和脚本继续按需读取。这直接支持第六版现有方向，也能解释为什么行业治理历史、
完整账号档案和所有平台接口不应常驻。

### 3. 稳定前缀和延迟发现

同一轮里每次模型调用都会重复付出上下文成本。Codex 尽量保持历史和工具顺序稳定，把运行变化追加到末尾，
并延迟发现 MCP、Skill 和插件。该原则能同时改善 Token、缓存命中和问题复现。

### 4. 让环境对 Agent 可读

Codex Harness Engineering 强调把 UI、日志、指标和 Trace 变成 Agent 能直接读取的环境。映射到营销系统，
不是让 Lead 阅读更多自然语言，而是让它读取带来源和作用域的 `AudienceSnapshot`、`BenchmarkSnapshot`、
`MediaReceipt` 和真实指标。

## 对 DeerFlow 的诊断

DeerFlow 并不缺能力。它已经拥有 Harness/App 隔离、LangGraph 恢复、沙箱、授权、MCP、延迟工具、Skill、
子 Agent、摘要和前端事件流。现在的主要差距是**可解释的组装边界**：

- Lead 基础 Prompt 已压至 `7,907` UTF-8 字节，但实际模型请求还会叠加 35 项链路中的动态贡献、工具
  Schema、Skill、消息历史和工具输出。
- 中间件中既有必要的宿主安全与恢复，也有会改变模型可见内容的投影；二者缺少统一清单。
- checkpoint、运行事件和孵化台账分别服务 Agent 恢复、UI/审计和业务事实，职责合理，但当前无法从一份
  只读记录重建一次模型请求的非历史部分。

因此问题不是“DeerFlow Harness 不行”，而是我们此前在强大 Harness 上继续增加业务控制，导致运行能力和
营销方法搅在一起。换成另一套 Harness 只会把现有问题重写一遍。

## 采用矩阵

### 立即采用为工程原则

1. **Lead 拥有营销判断**：中间件只负责宿主能力、状态、权限、预算、恢复和可观测性。
2. **渐进披露**：Prompt 只放身份、权责和事实边界；方法、行业知识、账号档案和工具按需加载。
3. **稳定能力合同**：新增搜索、对标、媒体和平台能力采用 Definition / Provider / Consumer 命名与责任分离。
4. **追加而非暗改**：动态上下文变化以可辨识的追加项进入请求，不静默改写旧消息或旧业务工件。
5. **子 Agent 只做 sidecar**：证据搜索、代码审计和独立分析可以委派，最终账号方向不拆给多个平级裁判。

### 隔离验证后再决定

第一项实验应是无行为改动的 `Harness Manifest Shadow Probe`：

```text
PromptManifest
  model
  base_prompt_hash / bytes
  dynamic_context[name, source, hash, bytes]
  visible_tools[name, schema_hash, bytes, order]
  active_skills[name, version, metadata_bytes, body_bytes]
  message_history_bytes
  tool_result_bytes
  business_artifact_refs
  estimated_input_tokens_by_category
```

冻结样本至少覆盖“你好”、黄金礼品、陌生新词、Agent 自营销和 TikTok 公会。验收条件：

- 不改变模型请求、回答和工具轨迹；
- 至少 95% 的估算输入 Token 能归属到明确类别；
- 能检测基础 Prompt、工具顺序、Schema、Skill 或动态上下文变化；
- Manifest 不保存密钥、Cookie、完整用户隐私或大段原始工具输出；
- 能用一份记录解释“为什么简单问候也消耗很多 Token”。

第二项才是只读 `CanonicalTurnProjection`：把 checkpoint 和 `RunEventStore` 投影为稳定的 Turn/Item 生命周期，
用于重放和前端，不立即替换 LangGraph persistence。

### 明确不采用

- 不把第六版迁到 DeepSeek Harness；其 TypeScript/Cordis 技术栈与 developer preview 状态会带来整套重写。
- 不嵌入 Codex App Server 作为第二 Agent Runtime；它是优秀的软件工程 Harness，不是营销脑。
- 不因 DeepSeek “Everything is a plugin” 就把全部现有代码插件化；只在真实存在多个 Provider 时建 seam。
- 不开放运行时自我修改 Prompt、Skill 或规则；任何学习仍须进入事实台账、离线评测和 Git 审核。
- 不把会话事件日志当成孵化业务真相。Agent 运行事实与账号策略、发布回执、指标结果仍是两种不同账本。

## 结论

两套 Harness 都有很强参考价值，但价值不在“换掉 DeerFlow”。最优组合是：

> DeerFlow 保留现役运行与恢复；Codex 提供极简循环、渐进披露和上下文成本纪律；DeepSeek 提供可重建事件与
> 可替换能力接缝。

先把模型实际看见的内容和 Token 来源照亮，再决定是否重构 Prompt 组装或运行事件。这个顺序能直接帮助
第六版减少暗规则和屎山风险，同时不触碰已经跑通的孵化行为。
