---
id: ADR-049
status: accepted
date: 2026-08-23
related:
  - ../audits/A144-agent-foundations-reference-library-and-v6-conformance.md
  - ../../agent-foundations/README.md
  - ../../agent-foundations/04-v6-agent-standard.md
  - ADR-048-minimal-agent-kernel-and-bounded-skill-routing.md
---

# ADR-049 采用开发 Agent 资料库与八层上下文标准

## 决定

采用 `docs/agent-foundations/` 作为第六版 Agent 架构的开发权威资料库，并从根 `AGENTS.md` 强制所有开发 Agent
在修改 Lead 身份/Prompt、上下文组装、SOUL、用户/项目记忆、Skills、Tool/MCP、子 Agent、压缩、权限或评测前
读取该资料库。

产品 Agent 的上下文分为：系统权限、产品身份、用户档案、项目/账号事实、会话状态、方法与知识、工具与环境、
评测与学习。各层必须有独立所有者、作用域与版本语义，不能互相冒充。

资料库只约束开发和架构审查，禁止整体或逐章注入产品 Lead。产品 Lead 继续采用 ADR-048 的极薄、模型无关内核，
营销方法按需加载，业务判断不变成固定流程。

## 依据

- OpenAI 与 Anthropic 都将 Agent 的核心定义为模型主导的决策/工具循环，而不是预定业务路径。
- Codex 证明 SOUL 文件名并非必要；其价值在于独立身份与类型化上下文。
- Hermes 清楚分离 SOUL、USER、MEMORY、项目指令和 Skill，说明第六版当前代码字符串身份仍需产品化。
- Claude Code 将项目指令、Skill、MCP、Subagent、Hook 和 Memory 分开，支持将确定性边界留在代码。
- A143 已证明只修改薄核心不足以控制行为，完整模型上下文才是实际作用面。

## 后果

- 以后不允许因一个失败案例直接往核心 Prompt 添加禁止句或行业答案。
- 任何问题先归属身份、用户、项目、会话、方法、工具、权限或评测层，再修改对应所有者。
- 第六版保留 DeerFlow/LangGraph 唯一运行时，不迁移到 Codex、Claude Code 或 Hermes。
- 下一批代码变更按顺序处理独立身份资产、Skill 生命周期、ContextManifest 和 UserProfile，不打包成一次大改。

## 不采用

- 不把资料库做成产品 RAG 或长系统提示；
- 不因缺少 `SOUL.md` 就替换 DeerFlow；
- 不照抄 Hermes 的文件名和存储形式；
- 不建立固定多 Agent 部门流水线；
- 不让普通对话自动修改默认产品身份；
- 不用模型专属营销 Prompt 弥补架构分层问题。
