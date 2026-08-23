# 一手来源索引

检索日期：2026-08-23。优先采用课程官方页、厂商官方工程文档和官方代码仓库；社区解读只能用于发现线索，
不能成为本资料库的规范依据。机器可读版本见
[`evidence/source-manifest-2026-08-23.json`](evidence/source-manifest-2026-08-23.json)。

## 课程与通用 Agent 架构

| 来源 | 一手材料 | 本资料库采用的结论 | 不能据此推出 |
|---|---|---|---|
| Andrew Ng / DeepLearning.AI | [Agentic AI](https://www.deeplearning.ai/courses/agentic-ai) | Agentic workflow 依靠反思、工具使用、规划和多 Agent 等可组合模式；必须评测与迭代 | 每个 Agent 都必须固定经过四个阶段 |
| Harrison Chase、Rotem Weiss / DeepLearning.AI | [AI Agents in LangGraph](https://www.deeplearning.ai/short-courses/ai-agents-in-langgraph/) | 先理解模型与外围代码的分工，再用图、持久化和人工介入控制开放循环 | 图中的每个节点都应成为业务硬流程 |
| OpenAI | [A practical guide to building agents](https://openai.com/business/guides-and-resources/a-practical-guide-to-building-ai-agents/) | Agent 代表用户独立完成任务；模型管理执行并动态选择工具；基础由模型、工具、指令组成；优先发挥单 Agent 能力 | 单 Agent 永远优于多 Agent，或提示词足以承担权限和状态一致性 |
| Anthropic | [Building effective agents](https://www.anthropic.com/engineering/building-effective-agents) | Workflow 是预定代码路径，Agent 由模型动态决定过程；从简单、可组合模式开始 | 所有业务都应自由运行，确定性代码没有价值 |

## 上下文、评测与产品 Harness

| 来源 | 一手材料 | 本资料库采用的结论 | 不能据此推出 |
|---|---|---|---|
| Anthropic | [Effective context engineering for AI agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) | 上下文包括 Prompt、Tool、MCP、外部数据和历史；上下文窗口是有限注意力预算，应保留最小高信号集合 | Prompt 越短越好，或任何动态检索都一定比常驻上下文好 |
| Anthropic | [Demystifying evals for AI agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents) | Agent 评测评的是模型与 Harness 的共同结果；优先检查环境结果，结合代码、模型与人工评分 | 只看最终文字就足以判断 Agent 成败 |
| Claude Code | [How Claude Code works](https://code.claude.com/docs/en/how-claude-code-works) | 典型循环是收集上下文、行动、验证、重复；模型判断，Harness 提供工具、环境与会话恢复 | Claude Code 的具体编码流程应搬进营销 Agent |
| Claude Code | [Extend Claude Code](https://code.claude.com/docs/en/features-overview) | `CLAUDE.md`、Skill、MCP、子 Agent、Hook、Plugin 各自有不同责任；Skill 渐进披露；确定性约束放 Hook | 一份 `CLAUDE.md` 或一堆 Skill 就等于完整 Agent |
| Claude Code | [Manage Claude's memory](https://code.claude.com/docs/en/memory) | 用户写的长期指令与 Agent 自动沉淀的学习应分开 | 所有聊天都应自动写入长期记忆 |
| Claude Code | [Create custom subagents](https://code.claude.com/docs/en/sub-agents) | 子 Agent 适合隔离上下文、权限与专长，由主 Agent 委派并收敛结果 | 多个平级 Agent 投票天然提高营销判断 |

## Codex 官方代码

审计固定到 [`openai/codex@422239e`](https://github.com/openai/codex/tree/422239eb4b1e0d0f85fac7256a079a1befe78472)，
避免把随时变化的 `main` 当作不可变证据。

| 文件/目录 | 一手材料 | 采用的结论 |
|---|---|---|
| 基础 Agent Prompt | [`gpt_5_2_prompt.md`](https://github.com/openai/codex/blob/422239eb4b1e0d0f85fac7256a079a1befe78472/codex-rs/core/gpt_5_2_prompt.md) | Codex 没有依赖名为 SOUL 的文件，身份、工作关系、自主性、执行与验证可以是独立内置基础提示 |
| 项目指令 | [`agents_md.rs`](https://github.com/openai/codex/blob/422239eb4b1e0d0f85fac7256a079a1befe78472/codex-rs/core/src/agents_md.rs) | 项目规则按目录作用域发现，不应混入用户画像或模型记忆 |
| 类型化上下文 | [`core/src/context`](https://github.com/openai/codex/tree/422239eb4b1e0d0f85fac7256a079a1befe78472/codex-rs/core/src/context) | 权限、环境、用户指令、插件、协作模式等上下文使用有名字的类型与独立测试，而非匿名字符串拼接 |
| 世界状态 | [`context/world_state`](https://github.com/openai/codex/tree/422239eb4b1e0d0f85fac7256a079a1befe78472/codex-rs/core/src/context/world_state) | 可变化状态应有明确所有者、渲染和更新语义 |
| 历史与压缩 | [`context_manager`](https://github.com/openai/codex/tree/422239eb4b1e0d0f85fac7256a079a1befe78472/codex-rs/core/src/context_manager) | 历史规范化与运行上下文更新独立管理；压缩不是随意改写身份和项目事实 |
| 仓库开发规范 | [`AGENTS.md`](https://github.com/openai/codex/blob/422239eb4b1e0d0f85fac7256a079a1befe78472/AGENTS.md) | 模型可见上下文必须增量、稳定、有界；大注入需要人工审查和集成测试 |

## Hermes 官方代码与文档

| 一手材料 | 采用的结论 | 不能据此推出 |
|---|---|---|
| [Which File Does What](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/which-file-does-what.md) | `SOUL.md` 管身份，`USER.md` 管用户，`MEMORY.md` 管环境与经验，项目指令由 `AGENTS.md`/`HERMES.md` 管；文件责任明确分离 | 第六版必须照搬相同文件名或 Markdown 存储 |
| [Use SOUL with Hermes](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/guides/use-soul-with-hermes.md) | SOUL 应稳定、广泛适用，只写身份、语气、价值取向与不确定性风格，不微管理工作流 | SOUL 能解决内容根、营销判断或事实质量 |
| [Architecture](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/developer-guide/architecture.md) | Prompt builder、context engine、memory、trajectory、tool registry、approval、gateway、session、hooks 与 skills 分层 | Hermes 运行时应替换 DeerFlow |
| [Prompt Assembly](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/developer-guide/prompt-assembly.md) | 按稳定、上下文、易变顺序组装；身份、项目规则、程序性方法和运行数据分别归位 | 所有稳定信息都应永久注入每次模型调用 |
| [Skills](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/skills.md) | Skill 使用渐进披露，方法按任务加载 | 读过 Skill 就应永久激活 |

## 本地证据

- [`A129 DeepSeek 与 Codex Harness 参考`](../content-intelligence-v6/audits/A129-deepseek-codex-harness-reference.md)
- [`A137 跨模型 Agent 核心提示审计`](../content-intelligence-v6/audits/A137-model-neutral-agent-core-prompt-audit.md)
- [`A143 现役完整上下文审计`](../content-intelligence-v6/audits/A143-effective-agent-context-and-deerflow-residue-audit.md)
- [`ADR-048 极薄 Agent 内核`](../content-intelligence-v6/decisions/ADR-048-minimal-agent-kernel-and-bounded-skill-routing.md)

这些本地文件记录第六版的实现与实验事实；外部材料只提供架构参照，不能覆盖本地真实运行证据。
