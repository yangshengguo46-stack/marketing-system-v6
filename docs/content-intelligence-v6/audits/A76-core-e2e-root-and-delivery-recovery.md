---
id: A76
status: implemented_real_partial
reviewed_at: 2026-08-18
decision: retire_a58_runtime_restore_sequential_rooting_and_bound_delivery_facts
sources:
  - backend/packages/harness/deerflow/content_intelligence/analyzer.py
  - backend/packages/harness/deerflow/content_intelligence/research.py
  - backend/packages/harness/deerflow/content_intelligence/delivery.py
  - backend/packages/harness/deerflow/tools/builtins/content_intelligence_tool.py
  - backend/packages/harness/deerflow/agents/middlewares/input_sanitization_middleware.py
  - backend/tests/test_content_intelligence_analyzer.py
  - backend/tests/test_content_intelligence_delivery.py
  - backend/tests/test_content_intelligence_research.py
  - backend/tests/test_content_intelligence_tool.py
  - backend/tests/test_input_sanitization_middleware.py
  - docs/content-intelligence-v6/decisions/ADR-020-retire-parallel-root-gates-and-recover-evidence-delivery.md
  - docs/content-intelligence-v6/evidence/core-e2e-a76-2026-08-18.md
---

# A76 核心端到端、内容根回归与事实交付修复

## 本轮范围

用户要求真实运行“我是做什么的”到具体选题和可表达成稿，同时明确暂停制作与素材。验收终点因此
冻结为：

```text
用户原话
-> 语义阅读
-> 内容根
-> 账号级内容地图
-> 公开资料与 TopicBrief
-> 孵化判断（定位 / 受众 / 人设 / 账号级表现形式 / 变现假设）
-> MessagePlan
-> BaseDraft
-> FormatDecision（允许 provisional）
-> AdaptedDraft
```

`ProductionPlan`、素材任务、MediaKit 和平台写操作均不是本轮完成条件。表现形式属于孵化与表达判断，
不是制作；信息不足时必须保留未知与备选，不得把暂定形式冒充成用户已确认。已有制作代码不删除，
但运行上下文必须在 `AdaptedDraft` 后停止，模型工具参数中没有暴露该内部开关。

## 全新留出题失败

全新输入“我是做宠物殡葬的，该怎么起号？”预先登记的目标跃迁是宠物殡葬进入人与宠物的陪伴、
失去、哀伤和告别世界。真实 GLM 运行仍把内容根留在“宠物殡葬”，研究也没有形成 TopicBrief。
该案例严格记失败，并从此转为开发证据；不能在修正后继续冒充留出题。

## A58 回归定位

雪茄馆回归首先把内容根选成“雪茄品鉴”，并将人物与历史方向写进漂移边界。Git 追踪发现提交
`c2ede5b6` 名义上是并行提速，实际同时替换了词义/共同世界链，并把 `required_contexts` 等模型
中间判断编译成确定性硬约束。A58 自己已经记录黄金礼品只到“礼赠”而未到人情世界，却仍被采用为
运行检查点。

本轮机械恢复 `c2ede5b6^` 的顺序认知链：语义阅读、语义家族、共同世界、独立复核、单一内容根
裁决、冻结根地图。旧 A58 文档和提交保留为失败证据；ADR-020 取代其运行决策。

恢复后雪茄第一次仍被选成长名称“人们在雪茄馆里到店品鉴雪茄并驻留社交的生活世界”。这证明
A58 不是唯一病根：根裁决器把“场所 + 对象 + 消费动作 + 社交结果”的长场景误当成了更大世界。
新增通用反例后，裁决器必须比较候选在该场景之外的外延容量；若对象还能独立展开历史、人物、事件、
地域和作品，该消费场景只是对象地图的一条路径。使用失败运行中完全相同的候选重放后，根改为
“雪茄”；从用户原话完整复跑也再次得到“雪茄”。

## 真实选题与结构化故障

根修复后的真实研究形成具体选题：

> Cohiba 如何从卡斯特罗的私人外交礼物变成全球高端雪茄品牌？这一转变中，政治特权、产区风土
> 与工艺稀缺性各自扮演了什么角色？

这证明 `雪茄 -> 具体人物/品牌/历史 -> 取证问题` 可以运行，但本次来源只有百科摘要和零售商文章，
权威性不足，TopicBrief 已显式保留该限制。

随后孵化判断和 MessagePlan 首轮都因供应商结构化 JSON 中未转义的中文双引号失败。原始 AIMessage
其实包含完整答案，但 LangChain 将它放入 `invalid_tool_calls`，旧解析器直接丢弃。统一结构化调用器
现在最多执行一次修复：将不超过 16 KiB 的畸形参数作为不可信数据交回模型，只允许修引号、转义、
括号和 Schema，不允许加入新事实。孵化、交付、形式和适配运行器共用同一边界。

修复后真实后半程成功生成孵化判断、MessagePlan、BaseDraft、FormatDecision 和 AdaptedDraft，且未
生成 ProductionPlan。但人工复核发现 BaseDraft 从模型记忆补入证据中不存在的名字
`Eduardo Rivera`，并把标题写成“全球最贵”。因此“技术链路跑通”不能等同“内容合格”。

## 交付事实边界

交付层新增一次有界语义修复，只针对高信号证据泄漏：

- 正文中新出现、事实账本没有的拉丁专名；
- 正文中新出现、事实账本没有的数字；
- “名叫/名为”等显式引入但证据账本没有的人名；
- 证据没有的“全球最贵、唯一、总是、只属于”等绝对断言。

修复只能删除或泛化列出的细节，不能换另一个名字、数字、排名或模型记忆事实；一次修复后仍越界
则拒绝交付。它是高信号护栏，不冒充完整的语义事实核验器。真实复跑删除了不存在的人名和“全球
最贵”，保留来源局限，形成标题“Cohiba：一支雪茄如何从政治特权走向全球溢价”。

修复稿随后再次进入真实形式与适配运行。`FormatDecision` 因没有用户素材、出镜意愿、表达能力和
平台信息而正确保持 `provisional`，给出口头表达候选及图文、情景表达备选；`AdaptedDraft` 只改写
表达节奏，八个单元均绑定 BaseDraft 原文锚点。人工复核没有发现新增人名、数字或绝对断言。最终
台账包含九类认知与表达产物，没有 `ProductionPlan` 或 `MediaArtifact`。

## 当前结论

- 自动合同与聚焦回归通过，内容主链可在 AdaptedDraft 后明确停止。
- 七个新增内部提示标签已纳入共享防伪净化；完整后端非 live 回归为
  `12074 passed, 76 skipped, 17 warnings`，无失败。
- 雪茄真实案例通过内容根、具体选题、孵化判断、基础稿、暂定形式与表达适配链路。
- 宠物殡葬全新留出题失败，因此不能宣称通用营销脑完成或达到 80 分。
- 雪茄资料源偏弱，成稿只能作为链路验收稿，不是可直接发布的事实终稿。
- 顺序链质量恢复但延迟高；提速必须在新留出质量不下降后单独比较，不能重新叠硬门。
- ProductionPlan、素材、MediaKit、发布、回执和复盘本轮均未启动。
