---
id: A144
status: reviewed
date: 2026-08-23
sources:
  - ../../agent-foundations/README.md
  - ../../agent-foundations/SOURCE_INDEX.md
  - ../../agent-foundations/01-first-principles.md
  - ../../agent-foundations/02-reference-architectures.md
  - ../../agent-foundations/03-context-and-file-model.md
  - ../../agent-foundations/04-v6-agent-standard.md
  - ../../agent-foundations/05-v6-conformance-audit.md
  - ../../agent-foundations/06-file-and-subsystem-map.md
  - ../../agent-foundations/evidence/source-manifest-2026-08-23.json
  - A129-deepseek-codex-harness-reference.md
  - A137-model-neutral-agent-core-prompt-audit.md
  - A143-effective-agent-context-and-deerflow-residue-audit.md
  - ../decisions/ADR-049-agent-foundation-and-context-layering-standard.md
---

# A144 Agent Foundations 资料库与第六版符合性审计

## 用户问题

用户发现默认产品没有实际 `SOUL.md`，并要求重新研究吴恩达及另一位主流 Agent 课程作者、OpenAI Codex、
Claude Code 和 Hermes 的资料、文件与架构，从头判断第六版到底是不是正经 Agent，并把依据沉淀为以后开发
必须遵循的资料库。

用户随后澄清：该资料库是给 Codex、Claude Code 等**开发 Agent**使用，不是产品 Lead 的运行时知识库。

## 研究范围

本轮只采用一手材料：

- Andrew Ng 的 `Agentic AI`；
- Harrison Chase、Rotem Weiss 的 `AI Agents in LangGraph`；
- OpenAI Agent 实践指南与 `openai/codex` 固定提交 `422239e`；
- Anthropic 的 Agent 架构、上下文工程和评测文章；
- Claude Code 官方工作原理、扩展、Memory 与 Subagent 文档；
- NousResearch Hermes 的 Architecture、Prompt Assembly、文件职责、SOUL 和 Skill 文档。

Harrison Chase 被选为“那个谁”的最可能指代，因为他与吴恩达共同讲授的 LangGraph 课程直接讨论 Agent Loop、
模型与外围代码分工、持久化和人工介入。该推断只影响资料覆盖，不排除以后补充其他课程。

## 核心结论

### 没有 SOUL 文件不等于不是 Agent

Codex 没有采用名为 `SOUL.md` 的默认文件，但其基础 Prompt、类型化上下文、工具循环、项目指令、权限、状态和
评测共同构成完整 Agent。Hermes 使用 SOUL 的价值是把身份从 `USER.md`、`MEMORY.md`、项目指令和 Skills 中独立
出来，而不是依靠一份人格文件产生智能。

### 第六版是 Agent，但产品 Agent 化未完成

第六版已经有模型主导的 LangGraph 循环、动态 Tool/MCP、Skill、子 Agent、状态恢复、持久账本和不可逆动作
边界，因此运行时合法性通过。

主要缺口在产品装配：

- 员工身份语义最初只存在于 `PRODUCTION_AGENT_KERNEL` 代码字符串；本轮后续整改已迁入独立、只读、可哈希的
  `IDENTITY.md` 打包资源，加载器负责结构与预算校验；
- 默认用户档案没有正式投影；
- 项目台账较成熟，但与用户/会话/长期学习的分层还不完整；
- Skill 的检查与激活在审计时仍混合；本轮后续整改已分为 discover / inspect / activate，普通读取不再授权；
- 本轮后续整改已实现统一、不含正文的 `ContextManifest`，按 Lead 物理模型调用对账身份、上下文、工具、
  Skill 和 Token；
- DeerFlow 通用工作台、引用、摘要和能力协议仍需继续条件化。

准确表述为：**Harness 合格，项目事实层较强，默认产品身份已独立，其他上下文产品化仍不完整。**

### 正确架构不是再加一份大 Prompt

跨来源共同收敛为八层责任：系统权限、产品身份、用户档案、项目/账号事实、会话状态、方法与知识、工具与环境、
评测与学习。每层必须有独立所有者和作用域；SOUL 只能承担产品身份。

## 资料库落点

新建 `docs/agent-foundations/`，包含：

- 第一性原理；
- 跨框架参考架构；
- 上下文与文件模型；
- 第六版规范性工程标准；
- 第六版保留/修改/退役审计；
- Codex、Claude Code、Hermes 文件与子系统地图；
- 人类可读和机器可读的一手来源索引。

根 `AGENTS.md` 已新增入口。以后开发 Agent 修改身份、Prompt、上下文、SOUL、Memory、Skill、Tool/MCP、
Subagent、摘要、权限或 Agent Eval 前必须阅读该资料库。整库明确禁止注入产品 Lead。

## 对当前整改的影响

A143 的安全和首轮上下文减法仍然正确，不因本轮研究回滚。接下来必须按独立变更推进：

1. 先完成并提交 A143 已实现的外部 SystemMessage/bootstrap 防护和首轮上下文减法；
2. 已把现有短内核迁到独立产品身份资产，没有新增业务语义；
3. 已分离 Skill discover/inspect/activate，并完成权限、secret、Lead/嵌入式/子 Agent 回归；
4. 已完成 Shadow-only ContextManifest；
5. 最后再建立有来源、可纠正的 UserProfile 投影。

## 未完成边界

本轮建立了资料库和架构决策，并完成了其中的独立默认身份资产、显式 Skill 生命周期与 Shadow-only
ContextManifest；UserProfile 仍未完成。Claude Code 没有公开完整运行时源码，
因此其部分是官方文档审计，不是源码全量审计。Hermes 和 Codex 的文件地图覆盖 Agent 相关子系统，不包含图片、
翻译、普通 UI 资源和所有测试逐文件摘要。
