# Codex、Claude Code、Hermes 文件与子系统地图

本页只列影响 Agent 行为的文件族：身份、上下文、循环、工具、技能、记忆、状态、权限、子 Agent、压缩和评测。
仓库中的 UI 图片、翻译、构建产物和普通业务测试不逐项抄录。Codex 与 Hermes 有官方源代码；Claude Code 没有
公开完整运行时源码，因此 Claude 部分只依据官方产品文档，不能假装做过源码级全量审计。

## Codex

固定审计版本：`openai/codex@422239eb4b1e0d0f85fac7256a079a1befe78472`。

| 文件族 | 责任 | 第六版应借鉴 |
|---|---|---|
| `codex-rs/core/gpt_5_2_prompt.md` | 基础身份、协作、自主执行、工具使用和交付 | 独立且模型无关的产品身份/协作内核 |
| `codex-rs/core/src/agents_md.rs`、`agents_md_manager.rs` | 查找、合并和作用域化项目指令 | 项目规则不混入身份或用户画像 |
| `codex-rs/core/src/context/*.rs` | 权限、环境、用户指令、插件、协作模式、时间等类型化片段 | 每个模型可见片段有名字、有所有者、有测试 |
| `codex-rs/core/src/context/world_state/*.rs` | 当前模型、权限、工具、环境、项目指令等可变化世界状态 | 区分稳定上下文与可更新状态 |
| `codex-rs/core/src/context_manager/` | 历史、规范化和上下文更新 | 更新动态状态时不匿名重写整段历史 |
| `codex-rs/core/src/compact*.rs`、`prompts/templates/compact/` | 压缩预算、远程/本地压缩与恢复 | 摘要是受控投影，不是第二项目台账 |
| `codex-rs/core/src/agent/`、`agents/` | Agent 控制、角色和委派 | 一个主 Agent，子任务有作用域 |
| `codex-rs/core/src/tools/`、MCP 管理模块 | Tool 注册、路由、执行生命周期和 MCP | 高层能力、延迟发现、确定性执行 |
| `codex-rs/skills/` | Skill 解析、发现、加载与样例 | 元数据常驻、正文按需、资源继续延迟 |
| sandbox/approval/network 相关模块 | 权限、审批和网络边界 | 安全由代码执行，不靠身份 Prompt |
| `core/tests/suite/` 与 snapshots | Prompt、上下文、压缩、AGENTS、工具等集成快照 | Agent 改动要验证完整请求与环境结果 |
| 根 `AGENTS.md` | 开发 Agent 的仓库规则 | 本资料库同样从第六版根 `AGENTS.md` 约束开发者 |

Codex 没有单独 `SOUL.md`，但 `gpt_5_2_prompt.md` 承担产品身份和协作内核；这证明职责比文件名重要。

## Claude Code

Claude Code 运行时源码未完整公开。官方文档可确认的扩展面如下：

| 产品资产/子系统 | 责任 | 第六版对应 |
|---|---|---|
| `CLAUDE.md` | 用户/团队维护的长期项目指令，支持目录作用域 | 仓库 `AGENTS.md` 与项目级运行规则 |
| Auto memory | Claude 自动沉淀、可查看/编辑的学习 | 经审查的用户/环境长期经验 |
| Skills | 按需加载的任务方法和知识 | 第六版产品/行业 Skill |
| MCP servers | 外部数据源和动作能力 | 抖音、浏览器、媒体等高层能力 |
| Subagents | 独立提示、上下文、工具和模型的有界工作者 | 研究/提取 sidecar，不是平级营销总脑 |
| Hooks | 生命周期上的确定性命令 | 权限、格式、审计等确定性策略 |
| Plugins | 打包 Skills、MCP、Hooks 和配置 | 可部署能力包，不是第二运行时 |
| Session JSONL/snapshots | 会话持续、恢复和回滚 | LangGraph checkpoint 与运行事件 |
| `/context`、`/memory`、`/skills`、`/agents`、`/hooks`、`/mcp`、`/permissions` | 面向用户/开发者的可观测入口 | 第六版 ContextManifest 与检查面 |

Claude Code 官方描述的运行循环是收集上下文、行动、验证、重复。其最重要的架构启示是把“建议模型如何做”与
“系统必须执行什么”分开：前者放项目指令/Skill，后者放 Hook、权限和工具实现。

## Hermes Agent

Hermes 官方 Architecture 页给出了完整的 Agent 相关目录图，核心链路如下：

```text
CLI / Gateway / ACP / Batch / API
-> AIAgent (run_agent.py)
-> prompt_builder + provider resolution + model_tools
-> model
-> tool calls -> registry/dispatch -> loop
-> session/state persistence
```

### 根入口与状态

| 文件 | 责任 |
|---|---|
| `run_agent.py` | `AIAgent` 核心对话/工具循环 |
| `cli.py` | 交互终端入口 |
| `model_tools.py` | Tool 发现、Schema 收集和分发 |
| `toolsets.py` | 工具分组和平台预设 |
| `hermes_state.py` | SQLite/FTS5 会话与状态 |
| `hermes_constants.py` | `HERMES_HOME` 和 profile 路径 |
| `batch_runner.py` | 批量 trajectory 生成 |

### Agent 内核

| 文件 | 责任 |
|---|---|
| `agent/prompt_builder.py` | 稳定、上下文、易变三层 Prompt 组装 |
| `agent/context_engine.py` | 可替换 Context Engine 接口 |
| `agent/context_compressor.py` | 超限时有损压缩 |
| `agent/prompt_caching.py` | Anthropic 前缀缓存 |
| `agent/auxiliary_client.py` | 视觉、摘要等辅助模型任务 |
| `agent/model_metadata.py`、`models_dev.py` | 上下文长度、Token 估算和模型目录 |
| `agent/anthropic_adapter.py` | Provider 消息格式转换 |
| `agent/skill_commands.py` | Skill 命令 |
| `agent/memory_manager.py`、`memory_provider.py` | Memory 编排与 Provider 接口 |
| `agent/trajectory.py` | 训练/审计轨迹保存 |

### CLI、Provider 与扩展

`hermes_cli/main.py`、`config.py`、`commands.py`、`auth.py`、`runtime_provider.py`、`models.py`、
`model_switch.py`、`setup.py`、`skills_config.py`、`skills_hub.py`、`tools_config.py`、`plugins.py`、
`callbacks.py` 和 `gateway.py` 分别承担命令、认证、模型选择、Skill/Tool 配置、插件、审批回调与 Gateway 管理。

### Tool 系统

| 文件/目录 | 责任 |
|---|---|
| `tools/registry.py` | 中央 Tool 注册表 |
| `tools/approval.py` | 危险命令识别和审批 |
| `terminal_tool.py`、`process_registry.py` | 终端与后台进程 |
| `file_tools.py`、`web_tools.py`、`browser_tool.py` | 文件、网页和浏览器能力 |
| `code_execution_tool.py` | 沙箱代码执行 |
| `delegate_tool.py` | 子 Agent 委派 |
| `mcp_tool.py` | MCP 客户端与动态 Tool |
| `credential_files.py`、`env_passthrough.py` | 受控凭据/环境传递 |
| `tools/environments/` | 本地、Docker、SSH、云沙箱等后端 |

### Gateway 与平台

`gateway/run.py`、`session.py`、`delivery.py`、`pairing.py`、`hooks.py`、`mirror.py`、`status.py` 负责消息分发、
会话、发送、用户授权、生命周期 Hook、镜像和进程状态；`gateway/platforms/` 与 `plugins/platforms/` 提供平台
适配。平台差异留在入口，核心 `AIAgent` 不为平台复制一套脑子。

### 长期上下文文件

| 文件 | 责任 |
|---|---|
| `SOUL.md` | 身份、人格、语气、价值取向 |
| `USER.md` | 用户稳定档案 |
| `MEMORY.md` | 环境、项目和工具学习 |
| `AGENTS.md` / `.hermes.md/HERMES.md` | 项目指令与作用域规则 |
| `skills/`、`optional-skills/` | 按需方法与知识 |

Hermes 还包含 `cron/`、`acp_adapter/`、`plugins/memory/`、`plugins/context_engine/`、`website/` 和大规模
`tests/`。这些证明它是完整 Harness，而不是“SOUL 加 Prompt”。第六版只借鉴职责分层与可观测性，不迁移运行时。

## 对第六版的直接结论

第六版当前对应关系：`lead_agent/IDENTITY.md` 承担默认产品身份，`identity.py` 承担加载、校验与内容版本，
`agent_core_contract.py` 只提供兼容导出，`prompt.py` 负责把名称和其他类型化上下文装配进模型请求。用户创建的
Agent/SOUL 属于另一配置作用域，不能覆盖默认产品身份。

三套系统共同证明：

1. 身份必须清楚，但不要求统一文件名；
2. 项目指令、用户档案、记忆和 Skill 必须分开；
3. Tool、权限、状态和验证属于 Harness；
4. 模型拥有开放判断，确定性代码拥有外部一致性；
5. 开发者必须能查看真实上下文与能力状态；
6. 第六版应整理现有 DeerFlow，不应再换底座或叠运行时。
