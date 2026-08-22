---
id: A137
status: reviewed
date: 2026-08-22
sources:
  - backend/packages/harness/deerflow/agents/lead_agent/prompt.py
  - backend/packages/harness/deerflow/agents/lead_agent/agent.py
  - backend/tests/test_lead_agent_prompt.py
  - backend/tests/test_incubation_architecture_boundaries.py
  - backend/tests/test_content_intelligence_tool.py
  - A129-deepseek-codex-harness-reference.md
  - A133-a132-full-harness-business-review.md
  - A136-confirmed-direction-topic-e2e.md
  - https://openai.com/business/guides-and-resources/a-practical-guide-to-building-ai-agents/
  - https://github.com/openai/codex/blob/main/codex-rs/core/gpt_5_1_prompt.md
  - https://github.com/openai/codex/blob/main/codex-rs/skills/src/assets/samples/openai-docs/references/prompting-guide.md
  - https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
  - https://www.anthropic.com/engineering/building-effective-agents
  - https://langchain-ai.github.io/langgraph/prebuilt/
  - https://langchain-ai.github.io/langgraph/tutorials/multi_agent/multi-agent-collaboration/
  - https://github.com/google-gemini/gemini-cli/blob/main/docs/cli/system-prompt.md
  - https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/subsystems/system-prompt.md
  - https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/core/system-prompt/README.md
  - https://docs.bigmodel.cn/cn/guide/platform/prompt
---

# A137 跨模型 Agent 核心提示词审计

## 用户指出的问题

现役 Agent 即使完成了业务分析，交流体验仍像外部顾问或老师：解释方法、列出建议、把下一步交还给用户，
而不像一个已经进入公司、接下任务、使用工具、形成判断并汇报结果的运营同事。

这不是某一条 TikTok 公会会话的问题，也不应通过给 GLM、DeepSeek 或其他模型分别定制营销提示来修复。
本审计研究的是一份所有模型共用的 **Agent 工作合同**。

## 结论

现役核心提示词确有结构性缺陷。它已经定义了业务领域、事实边界、工具路由和大量禁止事项，却没有完整定义：

1. Agent 与用户是什么工作关系；
2. 哪类请求意味着 Agent 已经接下任务；
3. Agent 在返回前应完成哪些允许的工作；
4. 什么状态才算当前任务完成；
5. 什么事情由 Agent 继续推进，什么事情必须交回用户；
6. 最终应像员工汇报结果，还是像顾问讲授方法。

因此，`You own the final judgment` 只解决了“谁做营销判断”，没有解决“谁对任务结果负责”。当前系统本质上仍是
一份业务能力较强的咨询型聊天提示，运行在具备工具的 Agent Harness 中。

正确方向不是再增加“像员工一样说话”或某个行业示例，而是**替换核心协作合同，同时把业务方法和工具细节
移回各自所有者**。

## 外部资料的共同收敛

| 来源 | 关键原则 | 对第六版的含义 |
|---|---|---|
| OpenAI Agent 指南 | Agent 代表用户独立完成任务，管理工作流，识别完成状态并在失败时纠正 | 核心 Prompt 必须定义任务所有权和退出条件 |
| OpenAI Codex Prompt | 在允许范围内持续工作到任务端到端完成，使用工具验证，再像同事一样交付 | 不能停在建议、教程或“你可以继续” |
| OpenAI Prompt 指南 | 目标、成功标准、停止条件优先；人格控制语气，协作方式控制主动性、澄清和检查 | 当前只有简陋语气规则，缺少协作方式 |
| Anthropic Context Engineering | 使用最小的高信号上下文，提示处在“具体但不硬编码流程”的合适高度 | 不能继续把失败案例变成常驻禁令 |
| LangGraph | Agent 是模型、Prompt、工具与 Harness 组成的反馈循环，直到任务完成 | DeerFlow 已有循环，缺的是完成合同，不是再造工作流 |
| Gemini CLI | 稳定 firmware 只放安全、审批和工具协议；persona、目标、方法与项目语境分层 | 核心合同与营销方法应分离 |
| DeepSeek Harness | Prompt 由有名字、有顺序、有所有者的 Section 组装，工具 Schema 也是模型可见合同的一部分 | 每条指令应能回答“谁拥有、何时出现” |
| GLM 官方 Prompt 指南 | System Prompt 应明确角色、风格、任务模式和具体行为；复杂知识可用参考资料和子任务 | GLM 不需要另一套营销母提示，只需要同一份明确合同 |

这些来源对模型措辞各有偏好，但 Agent 架构结论一致：**核心定义责任、权限、完成和交付；知识与方法按需进入；
模型供应商只负责协议适配。**

## 现役提示词证据

### 1. 只有职位名称，没有工作关系

现役 `<role>` 只有：

```text
You are {agent_name}, a content incubation and new-media operations agent built on DeerFlow.
```

它告诉模型“属于什么类别”，没有告诉模型“在用户团队里承担什么责任”。普通 Chat 产品同样可以使用这句话。

### 2. 一句所有权被后文抵消

`<account_incubation>` 写了 `You own the final judgment`，但随后又要求：

```text
offer a few coherent routes ...; recommend one without adopting it
```

“给选项、给建议、但不采用”保护了用户确认权，却同时把 Agent 推回外部顾问位置。真正需要区分的是：

- Agent 可以形成并据此工作的**临时工作判断**；
- 只有用户明确确认后，它才能成为**持久账号决策**。

当前 Prompt 把这两者一起否掉了。

### 3. 没有按请求类型定义授权

现役 Prompt 详细规定何时问一个问题，却没有统一区分：

- 问答、解释和研究：调查后直接报告；
- 策略和创作：交付可使用的工作产物；
- 修改和执行：在范围内直接做并验证；
- 发布、付费、删除和身份操作：准备完成后等待确认。

结果是模型即使拥有工具，也容易把每一类请求都退化为“我建议你怎么做”。

### 4. 没有完成标准

核心 Prompt 没有一条通用规则说明“返回前，当前请求的可完成部分已经完成”。`A broad account-starting question
asks for a strategic direction` 只限制不要扩张到 7/30 天计划，并没有定义一个合格的账号方向产物应达到什么状态。

没有完成标准时，模型最安全的语言模式就是讲框架、给清单、留下后续入口。

### 5. 语气规则代替不了协作规则

`<response_style>` 只有清晰、自然、范围对齐。这些规则能改变文字表面，不能决定 Agent 是否主动调查、是否
执行、何时向用户提问、是否检查结果、以及谁承担下一步。

OpenAI 的 Prompt 指南明确区分：personality 决定语气，collaboration style 决定提问、假设、主动性、权衡、
检查和不确定性处理。现役 Prompt 只有前者的弱版本。

### 6. 常驻内容的注意力分配失衡

当前静态模板为 `8,873` UTF-8 字节。按当前配置真实渲染：

| 模式 | 渲染 Prompt | 近似字符分词 Token | 备注 |
|---|---:|---:|---|
| 普通 | `10,006` 字符 | 约 `2,502` | 24 个 Skill 只注入索引 |
| Ultra/子 Agent | `16,385` 字符 | 约 `4,096` | 仍未计算工具 Schema、记忆和聊天历史 |

长度本身不是罪；Codex 的公开 Prompt 也不短。问题在于高成本区域主要描述工具路由、子 Agent 成本和历史
业务修补，而任务所有权、完成标准与协作关系几乎为空。简单“你好”的完整输入仍会叠加工具 Schema，因而
可能超过一万 Token。

### 7. 测试锁住了句子，不等于锁住行为

至少三个测试文件包含 33 处对 `SYSTEM_PROMPT_TEMPLATE` 或 `prompt.py` 的引用。大量测试断言某句英文必须
存在或某个禁词不得出现。这能保护架构边界，却不能证明模型表现得像执行者，也会鼓励以后继续追加句子来修
回归。

第六版自启动后八天内有 14 个提交修改过母提示。虽然总字节曾下降，这种高频业务纠错仍说明核心 Prompt
承担了过多本应属于工具合同、Skill、状态投影或行为评测的责任。

## 根因排序

1. **缺失协作合同**：没有定义“内部执行者”与用户的责任关系。
2. **缺失完成合同**：没有用户可见成果、成功标准和停止条件。
3. **确认权与工作判断混淆**：为避免替用户确认，连 Agent 自己的临时工作判断也不敢采用。
4. **常驻 Prompt 越权**：营销方法、工具路由、历史修补和宿主协议挤在同一个注意力平面。
5. **验证目标错误**：静态字符串测试多，跨请求的真实协作行为评测少。
6. **上下文成本未完整归账**：只限制静态模板 9 KB，没有限制完整渲染 Prompt 加工具 Schema 的首轮成本。

## 建议的跨模型核心架构

### 第一层：Agent Kernel，所有模型完全相同

只保留五项稳定合同：

```text
身份与工作关系
任务所有权与完成标准
自主行动与审批边界
事实、证据与不确定性边界
结果汇报方式
```

其行为语义应是：

- 你是用户团队里的新媒体运营执行者，不是外部教师或只给建议的顾问；
- 把明确请求当作交付任务，在允许范围内调查、判断、创作、调用工具和验证；
- 返回前完成当前范围内可以完成的工作，或明确唯一真实阻塞；
- 只有不可逆外部动作、付费、发布、账号身份和实质扩张范围需要确认；
- 不编造已经做过的动作、回执、数据或用户资源；
- 汇报“做了什么、得出什么、依据与未知、下一项由谁承担”，不默认讲课。

这是一份候选合同的语义骨架，不是本轮直接写入生产的最终文案。

### 第二层：营销职责章程，所有模型完全相同

只定义长期目标：帮助用户把业务或能力变成受众愿意持续关注、能积累信任并服务真实业务目标的 IP。保留
事实、受众、长期内容价值和可持续生产等少量业务不变量，不放行业答案、固定起号流程或工具名。

### 第三层：按需方法与能力

- 起号、账号定位、内容地图、选题、对标、脚本、制作和复盘分别由延迟 Tool/Skill 提供；
- 行业知识只进入垂直 Skill；
- 工具的参数、失败语义和回执由工具 Schema 拥有；
- 子 Agent 规则仅在该模式启用时出现，并应压缩为可执行合同，不常驻一篇成本分析。

### 第四层：项目与账号事实

用户事实、已确认方向、账号历史、证据和结果从业务台账按任务投影。它们不是核心 Prompt，也不能由模型记忆
冒充。

### 第五层：模型适配器

不同供应商只处理：

- Tool Call / Structured Output 协议；
- thinking 开关与推理参数；
- 上下文、缓存和最大输出限制；
- 流式事件和错误归一化。

禁止在这里维护“GLM 营销 Prompt”“DeepSeek 营销 Prompt”或模型专属行业规则。同一候选核心 Prompt 必须
原样通过跨模型评测。

## 当前内容应搬到哪里

| 现役内容 | 新所有者 |
|---|---|
| 角色名、责任、事实边界、审批边界、完成与汇报 | Agent Kernel |
| 孵化的业务目标与少量长期不变量 | 营销职责章程 |
| `analyze_content_intelligence`、`explore_content_world` 的具体路由 | 延迟工具描述或任务能力卡 |
| 行业假设与案例 | 垂直 Skill |
| 已确认账号方向与用户事实 | 业务台账动态投影 |
| 文件路径、输出图片、编辑工具协议 | Harness/工具固件 |
| 子 Agent 成本计算、并发限制和角色目录 | 子 Agent 能力提供者，仅启用时注入 |
| 模型参数和 Tool Call 差异 | Provider Adapter，不能进入营销 Prompt |

## 后续 A/B 必须怎样做

下一步先预注册，不直接替换现役 Prompt：

1. **同一候选 Prompt 跨模型运行**：至少覆盖当前可用的三种文本模型；不得出现模型名分支。
2. **同 Harness 公平比较**：工具、Skill、记忆、历史、thinking、递归预算和用户输入完全一致。
3. **覆盖六类请求**：问候、解释研究、起号判断、具体选题/脚本、执行型任务、不可逆发布请求。
4. **隐藏行业题**：既有黄金礼品和 TikTok 公会只作诊断；晋级使用未参与写 Prompt 的新行业。
5. **行为指标优先**：任务所有权、实际调查/执行、工作产物完整度、事实边界、审批正确性、阻塞真实性。
6. **顾问泄漏指标**：无必要的“你应该、你可以、建议你”、通用课程框架、把可完成工作重新分配给用户。
7. **成本指标**：首轮基础 Prompt、工具 Schema、动态上下文、总输入 Token、工具轮数和耗时分别归账。
8. **人工复核必需**：模型裁判不能单独决定“像不像一个负责的员工”。

候选只有在多数模型和多数 held-out 任务上同时改善，而且不牺牲事实边界与审批安全时，才允许替换生产
Prompt。单一模型或单一黄金礼品案例变好，不构成通过。

## 本轮不做什么

- 不修改生产 Prompt；
- 不给任何模型单独定制营销提示；
- 不增加“你要像员工”这一句表面人设；
- 不把更多 MCN 知识、行业案例或工作流塞回核心；
- 不以静态字符串测试代替真实行为评测；
- 不因“本体感”问题引入第二运行时或固定多 Agent 流程。

## 最终判断

用户的诊断是正确的：核心提示的问题比某条业务回答更上游。现役系统已经拥有工具、Skill、业务台账和
LangGraph 循环，但母提示把 Agent 定义成“会做新媒体分析的 AI”，没有定义成“对这项新媒体工作负责的
执行者”。

下一步应做一次**删除优先、结果优先、跨模型一致**的 Prompt 重构实验：先建立短的 Agent Kernel，再让
现有业务能力按需长回来。不是给每个模型写不同提示，也不是继续往当前母提示上叠补丁。
