---
id: A143
status: reviewed
date: 2026-08-23
sources:
  - backend/packages/harness/deerflow/agents/lead_agent/agent_core_contract.py
  - backend/packages/harness/deerflow/agents/lead_agent/prompt.py
  - backend/packages/harness/deerflow/agents/lead_agent/agent.py
  - backend/packages/harness/deerflow/agents/middlewares/
  - backend/packages/harness/deerflow/skills/describe.py
  - backend/packages/harness/deerflow/tools/builtins/tool_search.py
  - backend/packages/harness/deerflow/config/agents_config.py
  - config.yaml
  - extensions_config.json
  - A142-employee-agent-kernel-and-gift-skill-v1-3.md
  - ../evidence/a143-effective-agent-context-2026-08-23.json
---

# A143 现役 Agent 完整上下文与 DeerFlow 残留审计

## 审计问题

用户指出，现役 Agent 仍然像普通 AI 顾问，缺少团队员工的本体感，并怀疑第六版只修改了核心提示词，
没有完成对 DeerFlow 默认超级助手的产品级改造。本轮从真实运行进程、SOUL、自定义 Agent、Memory、
母提示、Skill、Tool/MCP、中间件、子 Agent、前端模式和真实首轮请求反向排查。

## 结论

用户的怀疑成立，但不是一份隐藏 SOUL 在作怪。

> 第六版已经换了一颗较薄的“员工型心脏”，但默认 Agent 仍穿着 DeerFlow 通用超级助手的全套制服。

现役 `PRODUCTION_AGENT_KERNEL` 只占实际系统提示的小部分。默认聊天仍会同时看到 24 个全局
Skill 的路由摘要、41 个延迟 Tool 名称、17 份重复的抖音 MCP 强路由提示、沙箱文件工作流和
研究报告引用格式。这些上下文的总权重高于新内核，并且实际指向“研究、咨询、工作流、多工具”。

## 真实运行边界

### SOUL 与自定义 Agent

- 当前 Gateway 使用第六版 `backend/.deer-flow`。
- 该目录下没有默认 `SOUL.md`、`USER.md` 或用户 Agent 配置。
- `agents` 表为 `0` 行；最近默认聊天也没有有效 `agent_name`。
- `agents_api.enabled: false`，所以当前主聊天没有选中自定义 Agent。
- `load_agent_soul(None)` 的代码路径存在，但因文件不存在而返回空。

因此，新增一份更长的 SOUL 不是正确修复；它只会再叠一层人格文本。

### P0：当前没有 SOUL，但外部 Run 边界可以创建全局 SOUL

`agents_api.enabled: false` 只关闭 `/api/agents` 管理面，没有保护正常 Run 边界。现役 Gateway 把
`is_bootstrap` 和 `agent_name` 当作普通外部 context 白名单字段。`is_bootstrap=true` 会跳过普通 Lead 组装并
绑定 `setup_agent`；当请求没有 `agent_name` 时，`setup_agent` 会直接写全局 `${DEER_FLOW_HOME}/SOUL.md`。

现在还有两个叠加风险：

- 外部 `input.messages` 明确保留 `system/ai/tool` 角色，外部 `SystemMessage` 会被合并到生产系统提示并进入 checkpoint；
- 当前 `.env` 开启无认证模式，实际进程中 `8001` 和 `2026` 都在监听所有网卡。

这条路径尚未改写当前 Agent，所以不解释现有顾问腔；但它可以让未来一次外部请求永久改写默认人格，
必须作为独立安全边界修复，不得当作提示词问题处理。

### Memory

- `memory.enabled: false` 且 `memory.injection_enabled: false`。
- `users/default/memory.json` 只有空摘要，共 `561` 字节。
- 全新会话的首次失败在没有摘要、没有老聊天、没有工具调用时就出现。

因此，长期记忆不是当前首轮“顾问化”的根因。长会话摘要和已加载 Skill 可以放大问题，但不能解释新会话。

## 真实首轮模型请求

使用第六版实际 `config.yaml`、已启动的 `deerflow-capability-mcp`、默认用户和普通模式构造
生产 Lead，MCP 真实返回 17 个领域 Tool。完整帐单是：

| 项目 | 实际值 |
|---|---:|
| 原始 Tool | 42 |
| 延迟 Tool | 41 |
| 首轮可见 Tool Schema | 3：`read_file`、`tool_search`、`describe_skill` |
| 已启用 Skill | 24 |
| 完整静态系统提示 | **12,349 UTF-8 字节** |
| Agent Kernel 内容 | 1,079 字节 |
| Skill 系统与 24 个摘要 | 4,212 字节 |
| 41 个延迟 Tool 名称 | 771 字节 |
| 17 个 MCP 重复路由提示 | 3,779 字节 |

这还没有计入当日时间、用户消息、三份工具 Schema、模型自身计费方式和后续历史。
A142 中“静态 `SYSTEM_PROMPT_TEMPLATE` 为 3,560 字节”只计算了 Python 模板字面量，漏算了运行时动态注入；
它不能代表模型实际看到的系统提示。

## 残留来源

### P0：全量 Skill 摘要重新污染首轮注意力

`14c16195` 把核心提示改薄的同时，把延迟 Skill 索引从“只有名称”改为“名称 + 每项最多 120 字符
描述”。这个改动只用黄金礼品一个垂直 Skill 验收，却将全部 24 个 Skill 的用途永久注入每个请求。

其中：

- `deep-research` 摘要要求“ANY question requiring web research”以及“before content generation tasks”主动使用；
  正文又要求 `Always load`、多角度检索和禁止单次搜索。
- `consulting-analysis` 向模型暴露市场、消费者、品牌和竞品“咨询级报告”。
- `bootstrap` 暴露 SOUL 创建与多轮 onboarding；`surprise-me`、`claude-to-deerflow` 等与产品职责无关。
- 仅 `incubate-gift-human-relations` 与当时黄金礼品题直接相关。

这不是“方法正文没进母提示”就安全。路由描述本身就是高权重模型上下文。

### P0：MCP 服务器级路由被错误复制给每个 Child Tool

`extensions_config.json` 在 `deerflow_capabilities` 服务器上配置了一组泛关键词和 `priority=100`。
配置解析会把服务器路由继承到每个 Child，于是 17 个抖音 Tool 全部得到相同语义和相同优先级。

结果有两层污染：

1. 系统提示永久重复 17 次“遇到抖音/对标/评论区就 prefer 该工具”；
2. 运行时用子串命中，同优先级按工具名排序取前三，泛化的“抖音”容易先提升
   `douyin_assets`、`douyin_audience`、`douyin_clone_leads`，而不是当下最需要的搜索或公开证据。

MCP 本身已经可用，日志已多次记录持久会话创建，本轮也真实 `tools/list` 成功；问题是路由配置，
不是 MCP 没接上。

### P1：工具名在静态上下文里暗示了一条应用程序流程

虽然 41 个延迟 Tool 没有在首轮暴露 Schema，它们的名称仍被整体列入系统提示。`propose/confirm`、
`plan_account_launch`、`analyze_content_intelligence`、`explore_content_world`、两个对标采集名称同时出现，
会把“可选能力”视觉上重建成一条固定应用流程。

### P1：任意 `read_file(SKILL.md)` 会被升级为跨轮活跃 Skill

`DurableContextMiddleware` 把任意成功的 Skill 文件读取写入 `skill_context`，后续每轮要求“重读并应用”；
`SkillToolPolicyMiddleware` 还会按这些记录改变可见工具。因此，检查一份 Skill 和显式激活它没有分开。
这不解释全新会话的首轮失败，但会让已经读过 `deep-research` 或垂直行业 Skill 的长会话越来越僵化。

### P1：通用 DeerFlow 工作台协议仍全局常驻

无论当前任务是否需要文件、研究或报告，系统提示始终注入：

- `/mnt/user-data` 沙箱文件编辑流程；
- DeerFlow 专用 citation 形式与报告尾部 `Sources`；
- 通用能力发现和进度提醒。

这些不是首轮顾问化的第一根因，但会浪费注意力和 Token，并让所有请求都带上通用超级助手口音。

### P1：Pro/Ultra 会额外恢复强工作法

- Pro/Ultra 会启用 Todo 中间件，注入“三步以上即规划、始终一个 in-progress”等应用式规则。
- Ultra 还会注入长篇委派成本公式、六步子 Agent 工作流和固定输出结构。
- 子 Agent 默认再次继承全部启用 Skill 和 MCP 路由。

当前新会话默认为 thinking，不启用 Todo 或子 Agent，因此这也不是本次首轮失败的直接根因，但是
产品还没有完成改造的条件路径。

### P1：长会话摘要与提问工具会放大顾问惯性

- 32K 触发的默认摘要模板会持久保留 `NEXT STEPS`、被拒绝方案和后续任务，随后由 DurableContext
  每轮重新注入。长会话一旦形成咨询清单，摘要会延续这个形状。
- `ask_clarification` 虽然延迟，但它的 Schema 把“多个有效方案”和“建议需要批准”也当作提问理由，
  并支持最多 16 个字段。这比薄内核“只在真正阻塞时询问”更宽。
- Tool 一旦被 `tool_search` 提升，promotion 会跨轮保留；提问工具返回后又会直接终止当轮。

它们都不是全新会话首轮失败的根因，但能解释“对话越长，越像固定问卷”。

### P2：前端还在营造“继续问顾问”的产品体验

自动 follow-up suggestions 默认开启，每次回答后另起一次模型调用生成三个“帮助用户继续对话”的问题。
这些问题不写入 Lead checkpoint，因此不是主模型的顾问腔根因；但它会让用户面持续强化“再咨询一个问题”的产品感。

## 真实行为证据

全新线上线程中：

- `你好` 只发生 1 次模型调用、0 工具，却仍消耗约 4,840 输入 Token；
- `我是做 TikTok 直播公会的，中东和中亚地区，我该怎么起号` 只发生 1 次模型调用、0 工具，但给出多个
  类目、市场、团队问题，没有直接交付判断与可拍选题；
- 后续用户补充 `MENA 和 CCA` 后，Agent 仍重复追问类目。

这证明行为在任何 Tool/Skill 正文执行之前就已经被常驻上下文扭曲。不应继续把问题归因给模型或再增加答案硬门。

## 整改边界

本审计建议用“减法和产品组装”替代新规则：

1. 保留薄 Agent Kernel，不新增营销流程、答案模板或关键词硬门。
2. 默认产品 Agent 只静态显示产品原生的少量高信号 Skill；全量已安装 Skill 仍可由 `describe_skill`
   按任务搜索，不再把所有描述塞进首轮。
3. 取消 MCP 服务器级泛路由。使用自然语义 `tool_search` 或逐 Tool 精确路由，不让“抖音”同时提升
   三个按字母排序的无关 Tool。
4. 延迟 Tool 保留在搜索目录，但不把整张内部工作流名单常驻注入模型。
5. 分离 `inspected_skill` 和显式 `activated_skill`；普通读取不得跨轮改变工具权限。
6. 文件工作台、报告引用、Todo 和子 Agent 方法只在相应能力真正激活时出现。
7. 增加“完整首轮模型可见请求”预算和快照测试，不再只检查 Python 模板常量。
8. 将 `is_bootstrap` 移出外部 Run context，禁止 bootstrap 写全局默认 SOUL，外部 Run 不得注入持久
   `SystemMessage`；本地无认证调试服务只能监听回环地址。

整改成功的验收不是“禁止某句话”，而是：同一模型、全新会话、相同用户请求下，首轮能以更少常驻
上下文直接做出判断和可用交付，同时仍能在真正需要时发现 Skill、MCP 和 DeerFlow 执行能力。

## 本轮边界

本文是根因审计，不宣称整改已验收。在生产改动前，必须先用失败测试固定完整首轮上下文边界，再用黄金
礼品、TikTok 公会和一个全新行业做真实 A/B；不得只用黄金礼品一题证明泛化。

## 后续整改回执（2026-08-23）

本审计第 5 项已经由 A145 / ADR-050 落地，历史诊断不回写删除：

- `describe_skill` 只返回检查结果和精确激活入口；
- `activate_skill(exact_name)` 才能建立当前 Run 的 Agent 激活来源；
- 普通读取 `SKILL.md` 只进入兼容性的“曾检查”投影，不改变工具权限、不绑定 secret；
- 用户显式 `/skill` 激活优先，Agent 无权在同一 Run 覆盖；
- 激活结果按启用清单、真实路径和正文 SHA-256 再校验，不能伪造 ToolMessage 激活；
- Lead、嵌入式客户端、子 Agent、权限和 secret 相关回归为 `602 passed`。

这项整改没有把 Skill 做成必经工作流，也没有往核心 Prompt 添加行业规则。A143 的其他未完成项继续由
ContextManifest 和后续 UserProfile 独立处理。
