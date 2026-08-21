---
id: A124
status: reviewed
date: 2026-08-21
sources:
  - https://docs.langchain.com/oss/python/concepts/memory
  - https://docs.langchain.com/oss/python/langchain/long-term-memory
  - https://docs.langchain.com/oss/python/deepagents/memory
  - https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills
  - https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
  - https://arxiv.org/abs/2309.02427
  - https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/memory-usage
  - https://support.google.com/youtube/answer/13616340?hl=en
  - backend/packages/harness/deerflow/skills/storage/user_scoped_skill_storage.py
  - backend/packages/harness/deerflow/agents/middlewares/skill_activation_middleware.py
  - backend/packages/harness/deerflow/agents/thread_state.py
  - backend/packages/harness/deerflow/incubation/contracts.py
  - backend/packages/harness/deerflow/persistence/incubation_ledger/model.py
  - backend/packages/harness/deerflow/persistence/migrations/versions/0015_incubation_logical_accounts.py
  - backend/app/gateway/routers/incubation_projects.py
---

# A124 账号脑、账号 Skill 与长期记忆架构审计

## 问题

用户确认定位后，账号会持续产生计划、选题、脚本、发布结果、评论、受众变化和复盘结论。需要判断：

> 是否应该让一个用户的一个账号对应一个 Skill 或知识库？

这不是二选一。Skill、长期事实、历史经历和当前任务上下文承担不同职责，把它们混成一个长文件会导致
陈旧信息、跨账号串用、上下文膨胀，并让一次偶然结果污染长期方法。

## 外部依据

1. LangGraph 将长期记忆区分为语义记忆、情景记忆和程序记忆，并允许使用任意自定义 namespace 隔离；
   thread 只适合短期对话状态。
2. CoALA 使用同样的语义、情景、程序记忆分工描述语言 Agent。该分类不是某一家产品的偶然实现。
3. Anthropic 将 Agent Skill 定义为可按需发现和加载的说明、脚本和资源包，核心原则是渐进披露。Skill
   更接近“怎么做”的程序性知识，不适合充当不断变化的交易数据库。
4. Microsoft Foundry 明确用稳定 scope 隔离不同用户或实体的长期记忆，并建议由可信代码决定 scope，
   不能让模型自行选择隔离边界。
5. 官方创作者资料建议按系列、形式、受众、主题寿命和制作成本分组，再从真实表现中寻找重复规律；
   这支持账号计划持续修订，不支持把首月日历永久写死在 Skill 中。

## 第六版结论

采用“一个逻辑账号一个 `AccountBrain` 作用域”，而不是“一个账号等于一个可写大 Skill”。

```text
AccountBrain(owner_user_id, logical_account_id)
├── Semantic Profile       已确认定位、受众、人设、形式、内容世界、产能与限制
├── Episodic Library       对标、用户案例、题稿、发布、指标、评论、受众与复盘
├── Procedural Projection  当前账号已采用的做法和边界，以只读 Account Skill 投影
└── Working Projection     本次任务按需组装的有界上下文
```

### 语义层：账号现在是什么

结构化事实台账保存已确认状态和版本关系，是唯一业务真相源。这里包括：

- 当前账号战略及其替代方案；
- 内容根和内容地图版本；
- 受众假设、人物身份、表现形式与变现路径；
- 已确认产能、资源、隐私和制作限制；
- 当前 `AccountLaunchPlan` 及修订原因。

这些对象必须支持版本、父级 ID、来源、状态和回滚，不能只存在聊天或 Markdown 中。

### 情景层：账号经历过什么

账号资料库保存带来源的经历和证据：用户材料、公开研究、对标快照、旧稿、发布回执、指标窗口、评论、
受众观察和复盘。一次爆款或失败先成为情景记录，不能直接成为长期规则。

首版使用账号 ID、类型、时间、来源、状态和标签做结构化过滤。只有资料规模与冻结评测证明语义检索
显著提升召回时，才增加向量索引；“语义记忆”不等于必须使用向量数据库。

### 程序层：这个账号已经学会怎么做

每个逻辑账号可以生成一个私有 `Account Skill`，但它只是事实台账的轻量、只读、可重建投影，包含：

- 当前稳定的内容承诺和表达边界；
- 已被多次结果支持的栏目原则、表现方法和禁用做法；
- 何时读取哪些账号工件和证据；
- 源工件 ID、版本和内容哈希。

通用的 7/30 天规划方法、内容地图方法、写作方法和复盘方法继续留在共享 Skill。账号 Skill 不保存全部
历史、完整日历、密钥、Cookie、Token、原始评论或实时计数，也不允许模型凭一次结果自行改写。

### 工作层：这一轮真正需要什么

Lead 每次只获得当前任务所需的有界投影。例如写一条视频时加载当前定位、相关地图路径、一个
`TopicBrief`、必要证据和少数反例，不加载账号全部历史。这样利用 DeerFlow 的按需 Skill 和工具能力，
同时避免“一个你好消耗一万 Token”的上下文污染。

## 逻辑账号先于平台账号

用户说“我是做黄金礼品的”时就可以创建逻辑账号，不要求先登录抖音。正式身份应为：

```text
LogicalAccountRef(owner_user_id, project_id, logical_account_id)
    -> zero or many PlatformAccountRef
```

同一个 IP 可以随后绑定抖音、小红书或 TikTok；平台授权只是执行与数据连接，不重新定义此前账号资产。
线程中的 `logical_account_id` 必须由服务端可信上下文注入，不能由模型或前端任意伪造。

## DeerFlow 实施状态与缺口

现有 DeerFlow 已具备：

- `users/{owner_user_id}/skills/custom/` 用户级私有 Skill；
- Skill 校验、写入、发现、激活、历史和回滚；
- 线程状态、工件台账与项目级查询。

2026-08-21 已完成：

- 未绑定平台时创建正式 `LogicalAccountRef`；
- 账号策略、内容、形式、适配、制作和起号计划工件的 `logical_account_id` 隔离；
- Gateway 从可信线程元数据注入账号，剥离调用方伪造字段；
- 同一线程可在同项目内切换账号，解绑项目时同步清理账号；
- 旧平台账号稳定回填至 legacy 逻辑账号，旧工件保持原 ID 与父引用。

仍缺：

- 按可信账号 ID 确定性生成和加载唯一只读 Account Skill 投影；
- 账号 Skill 与源工件版本/hash 不一致时的重建；
- 真实模型完成未登录双账号的“定位 -> 地图 -> 计划 -> TopicBrief”全链验收。

因此仍不能直接把账号资料写进现有用户级 Skill。下一切片只允许现有私有 Skill 存储承载确定性命名、
可从台账重建的 `account-{logical_account_id}` 只读投影。

## 学习提升规则

```text
真实发布结果
-> 情景记录
-> 带适用条件、反例和置信度的 LearningClaim
-> 多次或对照结果支持，且用户确认
-> adopted account rule
-> 重新生成 Account Skill 投影
```

不满足提升条件时，学习只影响下一轮候选，不修改账号稳定方法。这样系统可以越用越聪明，同时不会
把噪声自动写进主脑。

## 对 7/30 天计划的影响

`AccountLaunchPlan` 属于语义层的版本化运营状态，不属于 Skill 正文。Skill 只说明如何读取、执行和复盘
计划。计划中的每个真正拍摄题仍须生成独立 `TopicBrief`，发布结果再进入情景层。

`LogicalAccountRef`、账号隔离和可信线程绑定已完成，因此起号计划可以作为明确请求才调用的可选 Lead
能力接入。它不是默认阶段，不阻断单条选题；账号 Skill 投影完成前，它仍只从结构化台账读取父工件。

## 验收

1. 同一用户建立两个未登录账号，定位、地图、计划和资料不能互相召回。
2. 一个账号绑定多个平台后，账号战略保持同源，平台数据保留各自来源和人口范围。
3. 新对话选择账号后只加载该账号投影；切换账号时旧 Skill 和旧工件不残留。
4. 一次发布异常不能自动改写账号 Skill；经过确认的规则可追溯至结果、反例和版本。
5. 删除并重建 Account Skill 后，内容哈希应与事实台账投影一致。
6. 不启用向量检索时仍可完成账号日常任务；启用须有冻结对比证据。

## 最终判断

“一账号一脑”有充分依据；“一账号一大 Skill”没有。第六版应使用账号级作用域，把事实、经历、方法和
工作上下文分开。Skill 是账号脑的按需入口，不是账号脑本身。
