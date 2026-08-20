# A117 开源领域 Skill 架构审计

- 日期：2026-08-20
- 状态：reviewed
- 触发问题：行业经验从通用主脑拆出后，是否存在 Superpowers 一类可复用方案，以及行业 Skill 应如何组织才不会再次污染主脑。

## 结论

拆分方向成立，而且比继续修改通用提示词更容易调节。开源社区已经验证了三件事：

1. 领域知识可以按 Skill 渐进加载，不必常驻系统提示词。
2. 大型领域 Skill 库可以存在，但必须有清晰边界、检索、版本、评测和许可治理。
3. Skill 本身也必须测试；不能因为它是 Markdown 就把一次看似成功的回答当成通过。

开源方案没有直接提供“商业表达 -> 语义主体 -> 最大有效内容世界 -> 起号路线”这一营销孵化内核。
现成营销 Skill 主要覆盖 SEO、文案、投放、日历、平台运营和分析。它们可以补充下游工种，不能替代本项目
已经验证的“黄金礼品 -> 人情往来 -> 人与人之间的相处与人情世故”判断。因此开源可以提供架构和生产纪律，
行业语义跃迁、真实对标、结果反馈和用户纠错仍是本系统的核心资产。

## 本地底座核对

第六版 DeerFlow 已有完成这条路线所需的大部分基础设施：

- `SkillCatalog` 只把名称索引放进启动上下文，支持精确选择和有界搜索。
- `describe_skill` 延迟返回描述、权限和路径，正文与引用文件由 Agent 按需读取。
- `allowed-tools`、只读公开 Skill、用户 Skill 存储和 Skill 审查器已经存在。
- `skill-creator` 已包含有 Skill/无 Skill 对照、并行评测、人工查看、聚合指标、方差分析和描述优化脚本。
- A116 已实现 `incubate-*` 精确加载、有界 Profile、一次最多一个行业 Skill 及完整下游边界传播。

这意味着不需要安装第二套 Skill 运行时，也不需要把 Deep Agents 或 Superpowers 嵌入生产 Agent。缺口位于
行业 Skill 的分类、生命周期、触发评测、行为评测、版本元数据和组合冲突治理。

## 开源方案对照

### Agent Skills 开放规范

[Agent Skills Specification](https://agentskills.io/specification) 规定 `SKILL.md` 的名称、描述、许可、兼容性、
元数据和可选工具权限，并推荐三级渐进披露：启动时只读元数据，激活后读取正文，资源按需读取。当前 DeerFlow
实现与该模型一致；`incubation-profile.json` 可以继续作为本项目的有界领域引用文件，而不是另建向量库。

可直接采用：

- `metadata.version`、作者、来源与许可证字段。
- 简短触发描述、短正文、领域细节进入 `references/`。
- 脚本、参考资料和资产分离，避免 Skill 正文膨胀。

### LangChain Deep Agents

[Deep Agents Skills](https://docs.langchain.com/oss/python/deepagents/skills) 将 Skill、Memory 和 Tool 明确分开：Skill 是
按需能力，Memory 是持续上下文，Tool 是程序化行动；还支持多来源覆盖、动态列表、命名空间和子 Agent 的独立
Skill 范围。它证明“同一个 Agent 按任务加载不同领域能力”是 LangGraph 生态的标准做法。

本项目只吸收这个分层概念。DeerFlow 已经是 LangGraph 底座并已有对应能力，引入 Deep Agents 作为第二运行时
只会增加状态、权限和调试路径。

### Superpowers

[Superpowers](https://github.com/obra/superpowers) 是面向编程 Agent 的组合式 Skill 方法论。最有价值的是其
[writing-skills](https://github.com/obra/superpowers/blob/main/skills/writing-skills/SKILL.md)：先在没有 Skill 时观察真实失败，
再写最小 Skill，通过多次有/无 Skill 对照发现漏洞，最后收紧规则；它还明确把运行方差视为指标，并主张可由
代码校验的机械约束不要写成提示词。

采用：

- Skill 的 RED -> GREEN -> REFACTOR 测试纪律。
- 触发准确率与执行效果分开评测。
- 至少多次独立运行，人工阅读异常样本，禁止以单次命中宣布成功。
- 一次只新增或修改一个行业 Skill，完成验收再继续下一类。

拒绝：

- “任何回答前都必须调用 Skill”的全局强制规则。
- 把固定 brainstorming、planning、subagent、review 流程搬进营销判断。
- 安装 Superpowers 作为营销运行时或用它控制 Lead 的决策轨迹。

这些强制规则适合规范代码开发，但用于开放营销判断会重新制造第四版的硬门冲突。Superpowers 在本项目中是
开发手册，不是业务大脑。

### 现成营销与社媒 Skill

[Marketing Skills](https://github.com/coreyhaines31/marketingskills) 提供 CRO、SEO、文案、分析和增长 Skill，
并用一份共享 product-marketing 文档承载产品、受众、定位和版本变化。可参考其版本化项目上下文和横向工种拆分；
但“所有 Skill 先读 foundation”以及固定内容支柱、评分表不进入孵化内核。

[Social Media Skills](https://github.com/social-media-skills/skills) 提供大量品牌、声音、平台内容、发布和分析 Skill。
它可作为后续平台表现形式、日历和运营检查表的候选来源，但其品牌基础链和通用内容支柱不能解决内容根判断，
也不得整包安装。大量全局 Skill 会增加误触发、上下文和冲突面。

这两类仓库中的单个 Skill 只有在来源、许可、更新频率、触发边界和真实评测都完成后，才可安全重写或吸收；
不整包复制源码。

### 大型领域 Skill 库

[Scientific Agent Skills](https://github.com/K-Dense-AI/scientific-agent-skills) 展示了大量科学领域能力可以围绕稳定数据库、
工具和研究任务分包；[SecuritySkills](https://github.com/UnitOneAI/SecuritySkills) 展示了领域层级、Schema、测试 fixture、
角色、阶段、框架、版本和工具权限等治理字段。它们证明“大型行业 Skill 库”可行，但成功前提不是 Skill 数量多，
而是每个 Skill 围绕稳定责任边界并可独立验证。

本项目应借用 SecuritySkills 式治理元数据和回归 fixture，不照搬科学或安全领域内容。

## 推荐四层架构

```text
L0 通用孵化内核
  精确用户事实、语义候选、内容根/地图合同、事实边界、最终收敛

L1 行业孵化 Skill（incubate-*，一次最多一个）
  可复用语义路径、长期内容世界候选、局部分支、不可假设项、证据查询建议

L2 横向创作与运营 Skill（按任务读取，可组合）
  对标分析、受众研究、定位备选、选题、观点、脚本、表现形式、变现、发布与复盘

L3 确定性证据与执行工具
  抖音 MCP、MediaKit、HLLM、指标计算、持久化、审批和发布
```

Lead 仍是唯一最终营销判断者。L1 不能决定人设、表现形式或变现；L2 不能重新选择内容根；L3 只返回证据、
计算或执行结果，不能拥有营销结论。

## 行业 Skill 的正确粒度

不能给每个 SKU 建一个 Skill。Skill 应围绕可跨多个商业对象复用的“语义与内容世界机制”形成。下一批候选簇为：

| 候选簇 | 可覆盖示例 | 需要验证的共同机制 |
| --- | --- | --- |
| 礼赠与人情关系 | 黄金礼品、商务礼品、伴手礼 | 物品进入送、收、回、拒绝与关系秩序 |
| 食材与饮食世界 | 水果、海鲜、火锅底料 | 品类、饮食行为、地域、历史与文化世界 |
| 物件、身份与收藏 | 腕表、宝石、雪茄 | 物件进入人物、身份、审美、技术和历史 |
| 专业服务与变化 | 医美、咨询、教育 | 专业能力服务于人的变化、风险与判断 |
| 移动、生活方式与自由 | 房车、旅行、户外 | 工具进入移动方式、空间选择和生活价值 |
| 组织、招募与生态 | TikTok 公会、服务平台 | 组织连接供需双方、规则、成长和区域生态 |

这些只是待评测分类，不是现役规则。若同一 Skill 无法在至少多个不同商业对象上稳定迁移，就继续拆分；若两个
Skill 的触发长期重叠，则合并或增加反例，不允许同时注入后让模型自行处理冲突。

## 推荐包结构

```text
skills/public/incubate-<domain>/
├── SKILL.md
├── references/
│   ├── incubation-profile.json
│   ├── evidence-queries.json        # 可选：对标与资料检索方向，不是结论
│   └── accepted-cases.jsonl         # 可选：只收录有真实结果和适用边界的案例
└── evals/
    ├── trigger-cases.json           # 应触发与不应触发
    ├── behavior-cases.json          # 有 Skill/无 Skill 对照
    └── held-out-cases.json          # 冻结后不再调参
```

`SKILL.md` 只说明何时使用、何时不用及职责边界。具体行业路径留在结构化 Profile；外部证据与用户事实分开存储。
成功案例不能自动成为通用规则，必须同时记录适用条件、失败反例和真实结果。

## 生命周期与验收

```text
discovered -> candidate -> shadow -> active
                         -> rejected
active -> contested -> superseded / retired
```

- `candidate`：来源、许可、边界和最小失败样本已经登记。
- `shadow`：不影响正式回答，只进行有/无 Skill 对照和触发测试。
- `active`：留出案例、反触发、事实边界、真实端到端和成本均达到预注册标准。
- `contested`：新反例出现，保留旧版本和证据但停止扩散经验。
- `superseded/retired`：由新版本替代或证明不再适用。

每次修改 Skill 必须生成新版本，不覆盖旧评测。至少分别检查：触发准确、根与地图业务正确性、局部分支污染、
无依据事实、与无 Skill 基线的增益、多次运行方差、Token/耗时。单个黄金礼品案例通过，只批准当前 Skill 在该
边界继续使用，不证明所有礼品或所有行业已经解决。

## 迁移建议

第四、第五版的仓颉、薛辉、金枪大叔、文案三把刀、亲爱的安先生等材料应逐一审计为 L2 横向 Skill 候选，
不能进入 L0 或 L1。每项标记 `直接采用 / 薄适配 / 仅提取方法 / 拒绝`，并用新案例对照验证。抖音 MCP、
MediaKit 和 HLLM 保持 L3，不写成行业 Skill，也不能自动校准内容根；它们提供真实证据，学习循环再决定是否
修改候选经验。

## 决策

采用现有 DeerFlow Skill 运行时和 Agent Skills 渐进披露结构，吸收 Superpowers 的 Skill TDD 与
SecuritySkills 的治理思路。拒绝整包安装 Superpowers、Deep Agents 或任何大规模营销 Skill 库。下一步先为
`incubate-gift-human-relations` 补齐标准元数据、触发/反触发与多次运行评测，再用“食材与饮食世界”作为第二个
跨对象 Skill 候选；二者通过后才扩展更多行业。

架构约束见 `decisions/ADR-034-domain-skill-layering-and-lifecycle.md`。
