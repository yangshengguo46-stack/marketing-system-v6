# 第六版内容孵化内核台账

## 当前状态

- 台账日期：2026-08-15
- 第五版冻结提交：`3ee135f7`
- 第五版归档分支：`codex/archive-v5-final`
- 第五版归档标签：`marketing-v5-final-20260814`
- 第六版官方 DeerFlow 起点：`cd87968aea97b487380ea9586747d1ed8cdb5865`
- 第六版开发分支：`codex/v6-comprehension-core`
- 当前结论状态：`reviewed -> adopted as first vertical slice`

## A01 第五版与第六版边界

第五版保留为失败证据、评测历史和业务纠错样本，不作为第六版源码模板。第六版从官方 DeerFlow 独立目录开始，只迁移经过审阅的结论：

- Lead 保留最终孵化与新媒体判断权。
- 观察、解释、假设、反证和未知必须分层。
- 语义理解、内容地图和选题是同一阅读理解记录的不同投影，不是三个互相争权的流程 Agent。
- 内容地图回答长期讲什么；表现形式回答怎么呈现；变现和发布属于更后业务层。
- 对象本身已经构成完整内容世界时，不为追求抽象而强行向上跳。
- 类别地图与命名人物、作品、事件候选分开；无来源联想只能作为待验证假设。

未迁移内容包括第五版累积提示词、现役语义/地图工具源码、E28-E40 未通过实现、行业标准答案、固定数量、固定步骤和评测运行产物。

## A02 官方基线

第一次 GitHub HTTPS 克隆在约 15 MB 后因 HTTP/2 连接中断。为避免把失败网络传输误当成版本问题，第六版使用第五版对象库中刚从官方 `origin/main` 验证过的 `cd87968a` 建立独立工作树，再将远端 URL 指向官方仓库。新分支创建时：

- `HEAD == cd87968a`
- `git diff origin/main..HEAD` 为空
- 工作树为空
- 第五版未跟踪文件、缓存、字节码和评测产物均未进入第六版

官方后端完整离线基线结果为 `11543 passed, 76 skipped, 1 failed`。唯一失败是本机 HTTP 代理截获测试内部的 `127.0.0.1` OpenViking MCP 请求并返回 502；使用 `NO_PROXY=127.0.0.1,localhost` 单独复跑后通过。该问题记录为环境基线，不归因于第六版代码。

## A03 测试先行证据

第一组测试先引用不存在的 `deerflow.content_intelligence`，得到预期红灯：

```text
ModuleNotFoundError: No module named 'deerflow.content_intelligence'
```

实现最小合同后，记录与投影测试 `10 passed`。第二组测试先引用不存在的分析器和内置工具，再分别得到导入红灯；接入后聚焦测试为 `18 passed`，官方 Lead 提示词、模型选择、Skill、MCP 与子 Agent 路由回归为 `114 passed`。

完整回归首次发现新增的 `<content_intelligence>` 与 `<content_intelligence_method>` 尚未进入 DeerFlow 的输入净化名单。先保留失败，再把两个框架标签纳入原有统一防伪边界；用户输入和远程工具结果的显式回归随后通过。

提交前合同复核又发现 `Observation` 与 `GroundedStatement` 允许空引用。新增两条测试后先得到 `2 failed, 10 passed`，再收紧观察、实体、角色、反证及已落地投影的证据字段。最终内容智能与输入净化定向测试为 `176 passed`。

## A04 首个垂直切片

当前运行链路为：

```text
SourceItem
-> one optional structured comprehension call
-> ComprehensionRecord
-> BusinessSemanticView / ContentWorldView / TopicBrief
-> Lead final judgment
```

确定性代码只负责来源 ID、记录 ID、引用完整性、类型一致性和投影绑定。模型负责开放世界理解；无来源常识只能标记为假设并显示限制或验证问题。列表允许为空，缺失信息不会成为语义硬门。

## 未验收事项

- 尚未用真实模型跑第五版四个已标注训练案例和全新留出案例。
- 尚未证明当前单次结构化调用优于模型直答、Skill 或受控多 Agent 方案。
- 尚未接入项目事实账本持久化、外部搜索证据桥、账号采集、受众情报、表现形式、变现、发布或复盘。
- 尚未授权把用户纠错自动提升为跨用户通用规则。

因此当前只能称为“第六版可运行的第一候选内核”，不能称为营销脑已经达到 80 分。

## A05 GLM 真实结构化调用

使用本机未跟踪配置中的 `glm-5-2-260617`，以“我是做咖啡设备维修的，这个账号可以讲什么？”做第一次真实冒烟。首次调用暴露供应商兼容问题：GLM 将 `business_semantics`、`content_world` 和 `topic_brief` 三个嵌套对象作为 JSON 字符串放进工具参数，LangChain 的 Pydantic 解析器在进入领域合同前失败。

该故障先被加入 `test_analyzer_decodes_provider_stringified_projection_objects_without_retry`，确认红灯后才实现兼容层。兼容层要求 `include_raw`，仅从同一次工具调用的原始参数中解码预期容器字段，不追加模型调用、不读取或记录模型隐藏思考，也不放宽来源与引用校验。

同一案例复跑通过，摘要为：

```text
record_id: ci-68a6d285c46290cb7144
observations: 1
interpretations: 2
commercial_object: 咖啡设备维修服务
content_root: 咖啡设备维修
topic_brief: null
unknowns: 3
```

技术合同通过，但业务质量尚未验收：当前内容根仍可能过窄，且本请求没有形成 TopicBrief。该结果不得被描述为新内核已经解决内容地图或达到 80 分，只证明 GLM 与第六版结构化链路可以完成一次真实、无重试的往返。

## A06 工程验收

- 后端静态检查：`ruff check` 通过，`1137` 个 Python 文件满足格式检查。
- 后端完整非 live 套件：`11571 passed, 76 skipped, 17 warnings`，耗时 `358.89s`。
- 完整套件使用 `DEER_FLOW_AUTH_DISABLED=0` 验证原有认证测试，并以 `NO_PROXY=127.0.0.1,localhost` 排除已登记的本机代理干扰。
- 前端 `lint + type check` 通过；本切片没有修改前端运行代码。
- 本地 API Key 和运行配置仍在 Git 忽略文件中，不进入源码、台账、日志或测试夹具。

## A07 黄金礼品真实业务评测（失败基线）

2026-08-15 使用本机未跟踪配置中的 `glm-5-2-260617`，对同一个冻结输入运行两层真实评测：

```text
我是做黄金礼品的，我要怎么起号？
```

第一层直接调用 `analyze_content_intelligence` 的 `combined` 投影。商业语义部分正确识别：

```text
commercial_object: 黄金礼品
lexical_head: 礼品
modifier: 黄金 -> 材质/价值限定
```

但内容地图未通过。模型将 `content_root` 收敛为“黄金礼品业务”，只展开产品、礼赠场景和起号方法三个相邻维度，没有完成已标注参考中的核心跃迁：

```text
黄金礼品 -> 礼品 -> 送礼 -> 人情来往
```

第二层通过第六版完整 Lead 运行。Lead 确实主动调用了 `analyze_content_intelligence`，证明运行接线有效；最终回答却重新收敛为“送礼场景种草、黄金知识科普、产品工艺视觉大片”三条通用品类路径，并泄漏到平台选择、养号、私域和发布节奏。回答还在没有业务证据的情况下生成了“第 1-3 天”“第 4-14 天”“每天 1-2 条”“前 30 条 90%”等具体数字。

本次完整运行可见指标：

```text
model: glm-5-2-260617
tool called: analyze_content_intelligence
input tokens: 29.7K
output tokens: 9,868
total tokens: 39.6K
elapsed: 3m26s
thread: 85034bd6-ae2d-4d11-ab85-5f9d6265f736
```

评测结论为 **failed**，不能因词法主语识别正确而判定内容孵化通过。当前候选同时存在四个问题：

- 语义拆分已经能看见“黄金是材质、礼品是主语”，但没有把该中间表示转化为内容根。
- `combined` 一次请求商业语义、内容地图和选题，可能诱发“交付完整方案”的注意力偏移。
- Lead 在读取结构化结果后仍可回到模型先验中的通用起号模板，说明工具输出尚未形成有效的最终判断约束。
- 单次回答的延迟与 Token 成本过高，且新增计算没有换来参考跃迁。

这次结果作为第六版第一个真实失败基线保留。后续修正必须先增加冻结评测，再改认知链路；不得直接按“黄金礼品”行业词写标准答案，也不得通过增加固定 MCN 流程掩盖失败。

## A08 单次大合同到受控多专家

黄金礼品后续评测显示，将语义、内容根、地图和起号回答放在同一次模型任务中，会让“交付一份完整起号方案”的注意力压过语义跃迁。将职责分为四个独立上下文：

```text
语义阅读
-> 内容根选择
-> 只看冻结根的地图展开
-> 只读已有地图的总编表达
```

地图专家的实际输入只有 `primary_content_center`，不包含商品、语义草稿、用户原话、候选根和销售目标。总编结果经 `return_direct` 退出模型循环后再提升为正式回答，避免通用 Lead 重新写回品类号。

这是受控的多专家链，不是可自由使用工具或修改状态的 DeerFlow `task` 子 Agent。具体决策见 `ADR-002`。

## A09 商业回桥根因与删除

“商业回桥”不是 DeerFlow 或模型的原生概念，是工程层将用户早期“不卖而卖”的表达抽象成了 `object_anchor` 和 `return_path`。旧内容世界提示词又无条件要求“保留回到商业对象的路径”，因此通用 Lead 持续将人情世界缩回黄金产品。

Git 谱系已经确认了它从业务目标变成运行时硬约束的过程：

1. 2026-08-11 的第五版提交 `c948ccac` 仍把它写成账号尺度的“商业归因/商业回路”：内容先建立“懂送礼与关系表达”的记忆，再由主页、咨询和交付承接。这个目标本身成立。
2. 2026-08-13 的提交 `425d1e26` 将目标提前编译进选根器，要求根世界和每个主要内容轴都能回到商品，并用非空 `return_path` 参与 `branch_lens`、`promote_to_root` 等决定。此时商业承接开始反向控制语义与地图。
3. 2026-08-14 的多个离线评测又把 `return_path` / `business_return_path` 变成候选必填字段，错误约束由提示词扩散成测试口径。
4. 第六版初始提交 `ebc60fbd` 虽重建了阅读理解合同，仍在 `ContentWorldView` 中继承 `return_path`，所以新底座没有自动消除旧注意力。

现在已从 `ContentWorldDraft`、`ContentWorldView`、投影引用校验、Lead 投影和内容世界提示中删除商品锚点与回桥。地图专家只收到冻结内容根；运行时提示也不再用“不要回桥”这种仍会激活相关注意力的否定表述。测试直接验证字段和相关提示词都不存在，而不只是要求模型“尽量不用”。商业承接留给地图之后的独立模块，当前未实现。

## A10 真实模型业务回归

### 黄金礼品

首次总编仍使用结构化长文合同，GLM 在中文正文中输出未转义引号，两次 JSON 均无法解析。系统正确拒绝了伪造结果，但用户只收到结构失败提示。

```text
thread: 80123565-1611-4fe9-bec0-8683a19c5fd6
result: failed at prose JSON protocol
```

失败测试落地后，前三个专家仍使用结构化合同，总编改为 Markdown 正文。真实复跑的内容根为“礼品馈赠活动”，正文展开社会契约、婚丧仪式、人情债、外交赠礼、数字红包、文学叙事与馈赠禁忌。黄金只在语义跃迁段作为起点，不再是地图主转轴。

```text
thread: 0f7ed210-f48d-4f86-86a3-b5c4796a1e5f
model: glm-5-2-260617
result: business judgment passed
tokens: 32.7K
elapsed: 6m39s
```

删除商业回桥字段与运行时注意力词后，再用最终消息交付机制复跑。内容根为“赠礼往来中的人际关系与仪式”，正文展开互惠、面子、权力位差、人情债、婚丧礼金、跨文化赠礼、《礼物》与《麦琪的礼物》。黄金仅在首段作为语义起点，没有品类方案、商品展示或第二次 Lead 改写。

```text
thread: dce7b980-91fd-40b9-bd62-934d2e43f15b
run: 52a6a7c2-e209-44b5-8fa4-cb78bc45099c
model: glm-5-2-260617
result: business and delivery passed after bridge removal
tokens: 24.6K
elapsed: 5m31s
visible H1: 赠礼往来中的人际关系与仪式
second Lead rewrite: absent
```

### 重庆火锅底料

第一次异质复跑没有复读黄金逻辑，但内容根为“火锅聚餐——多人围炉涮煮共食的社交餐饮活动”，过度抽象到社交活动，未达到用户标注的“火锅”。因此只能记为方向改善，不能记通过。

```text
thread: 0d645c03-e6f5-45d1-9c59-fc9f13d54ea8
model: glm-5-2-260617
result: partial failure; root over-socialized
tokens: 29.1K
elapsed: 5m07s
```

增加“社会功能必须是构成性的而非仅仅常见场景”后，第二次选成“制作火锅”，又把完整对象降成了动作；第三次拆开 `served_objects` 与 `served_activities` 后，内容根终于精确为“火锅”，但页面只显示内部结构，没有正式正文。

```text
thread: ca8b14ee-898f-477b-a44d-244a006faafa
result: partial failure; action root

thread: 538129b7-818e-4b0a-8206-a352176fd9e1
result: business judgment passed; final answer invisible
```

首次加入可见 `AIMessage` 后，业务正文正确，但将 AI 消息直接放进工具节点破坏了 LangChain 的 `return_direct` 路由判断。Lead 随后又运行一次，补出“聚焦重庆火锅底料”的第二份方案。这个任务作为消息路由失败证据保留。

```text
thread: 7d133678-0d2b-42c6-82d6-6aee98d1b2ae
result: business judgment passed; delivery failed with a second Lead rewrite
```

最终实现只在工具节点写入带 `deerflow_direct_response` 标记的隐藏 `ToolMessage`。原生 `return_direct` 先结束模型循环，`TerminalResponseMiddleware.after_agent` 再提升为唯一可见 AI 回答。真实页面刷新后正文仍存在，只有一个一级标题“火锅”，没有工具回执和第二份品类方案。地图展开种类、历史、地域、人物行为、事件冲突、生活习惯及公共表达。

```text
thread: b073ee8a-5bc9-425a-af01-3c1a28477933
run: b0af00d5-dd18-40c2-891e-8fa316c2b88a
model: glm-5-2-260617
result: business and delivery passed
tokens: 21.3K
elapsed: 3m09s
refresh persistence: passed
visible H1 count: 1
second Lead rewrite: absent
```

## A11 当前验收边界

已通过的是两个业务与交付判断：黄金礼品进入赠礼往来中的人际关系与仪式，重庆火锅底料进入“火锅”世界；两者均由最终消息机制单次交付，没有第二次 Lead 品类改写。这证明拆开语义、选根、地图和表达比单次大合同稳定，也证明删除商业回桥有必要。

当前不可宣称 80 分营销脑已完成：海鲜、水果和全新留出题尚未用最终架构完成真实回归。当前单次仍需 3 至 5.5 分钟和 21K 至 25K Token，产品延迟与成本仍待优化。
