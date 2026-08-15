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

## A12 根后阅读理解链恢复与 KTV 失败定位

第五版冻结前已经形成一条可用但未接入第六版的下游链：

```text
冻结内容根
-> 具体命名召回
-> 联网搜索回执
-> 证据阅读
-> TopicBrief
```

第六版最初只迁移到冻结地图和总编，因此能讲大类，却无法稳定从地图走到具体人物、作品或事件。本轮新增 `research.py`，把命名召回和证据阅读放在地图之后；搜索结果只进入白名单标题、URL 和摘要，研究失败必须原样保留地图。

第一次 KTV 新链实测仍失败。内容根选择为 `KTV门店`，地图被设备、供应链、合规与经营知识占据：

```text
thread: 818206dc-54bd-4b98-8ecd-aaa41ea585f8
run: 7e0ab6f1-de41-4de6-ad5c-e94206ab146e
result: failed; venue operations displaced singing and emotion
tokens: 43,553
elapsed: 488.7s
```

第二次虽召回卡拉 OK 发明史与《K歌之王》，Lead 却在同一动作中并行发起“怎么起号”的通用搜索，还把自己补写的抖音、小红书运营需求作为 `source_materials` 传入。隐藏直答随后与泛搜索一起进入第二次 Lead 合成，最终又出现业态分类、设备、同城获客、口播和“前 20 条”等内容：

```text
thread: 42b06989-2408-442e-976d-fa2c5551068d
run: 72214cdf-d68d-4166-acb5-8f23b90d52b6
result: failed; pre-map search and model-authored source contamination
tokens: 59,123
elapsed: 718.1s
```

由此落地三条边界：

- `explore_content_world` 的模型可见参数只保留用户原话，不能接模型改写来源。
- 调用直答内容世界工具时，不与 Lead 级 `web_search` 或 `web_fetch` 并行；搜索只在根冻结后发生。
- 对经营容器做构成性移除反事实时，判断去掉参与者活动后品类身份和用户进入理由是否仍成立，不能把空房间、设备或卖方流程仍存在视为品类仍成立。

GLM 修正版运行已经生成“卡拉 OK 发明、录像厅历史、NHK 歌唱节目”等根后查询，但在证据阅读处因账户欠费返回 403。运行表虽记为 `success`，业务工具实际失败，因此不得作为验收通过：

```text
thread: 0dc20842-f786-4bf4-95d4-da54d5aaaaf3
run: ebeb277a-572d-425e-8256-1a752d738e01
result: infrastructure failure; AccountOverdueError during evidence reading
tokens before failure: 41,122
elapsed: 581.0s
```

## A13 快速受控工作者与跨案例验收

DeepSeek V4 Pro 在页面思考模式下能让 Lead 正常选择工具，但内部结构化调用返回 `Thinking mode does not support this tool_choice`。这证明外层决策与内部工位不应无条件继承同一思考开关。现在外层 Lead 保留用户选择的思考模式，工具内受控工作者固定关闭供应商隐藏思考，以结构合同作为可检查的中间推理。

修复后 KTV 真实结果以“唱歌/K歌体验”为内容根，明确保留身体与心理、情绪宣泄、社交角色、歌曲与个人经历及媒介变迁，没有经营模板；根后取证落到井上大佑与卡拉 OK 发明史：

```text
thread: 5d459752-e499-4ec0-8df9-385617f76b2d
run: bdd187be-f98e-44d1-8e03-19a7327b3073
model: deepseek-v4-pro
result: semantic root, map, topic, and single delivery passed
tokens: 25,998
elapsed: 112.3s
```

首个陌生场馆题“陶艺体验馆”正确迁移到亲手做陶活动，但第一次地图混入定价、会员、获客、排班和交付，记为部分失败。增加“活动根面向参与者、不得改写成组织者运营”边界后，复跑只保留技法、触觉、失败、情绪、关系、历史、作品与跨手作比较，并召回《人鬼情未了》的拉坯场景：

```text
thread: 9c912050-10bc-4ef5-880b-0045365ecba1
run: f931e121-612d-4e67-a7f5-1ca6e241a9c7
result: root passed; map purity failed
tokens: 30,013
elapsed: 149.1s

thread: b962ac1e-dacc-4095-b5b1-5128f06b9977
run: b7f81cde-a005-4603-a3b7-ac5d15f67b4f
result: semantic and map passed; root label remained wider than ideal
tokens: 27,110
elapsed: 123.5s
```

真正留出的服务型题“婚礼主持”没有被用于调参。结果从使能角色迁移到 `婚礼仪式`，展开仪式动作、人物与家庭关系、文化差异、历史变化、人生过渡、复杂情绪及作品中的婚礼，没有主持行业运营。搜索召回过渡礼仪、日本三三九度和勃鲁盖尔画作，但证据阅读认为当前回执不足，最终保留地图而不强塞 TopicBrief，证明弱证据弃权生效：

```text
thread: 386ab461-8f3c-41ef-8485-8c32b9b8de7b
run: 7b3700c0-d934-4b0c-8dcf-1b4c0c8407f2
model: deepseek-v4-pro
result: held-out semantic root, participant map, abstention, and delivery passed
tokens: 26,050
elapsed: 114.3s
```

本轮可确认“语义识别、冻结地图、具体命名召回、可选证据选题”已经形成可用纵切，并在 KTV 与陌生服务题上达到约 80 分的内容判断。仍不能把它等同于完整营销 Agent：来源等级、全文抓取、表现形式、项目事实、账号证据、变现、发布和复盘尚未接入；陶艺根名也显示内容根与受众领地仍可能被模型合并，必须继续保留人工可见与版本评测。

## A14 冲突边界复盘与编剧脑拆分

婚礼页面结果再次出现“成员互动、让步甚至潜在冲突”，火锅结果也曾把关系差异写成博弈。这不是缺少一个更好的“冲突地图节点”，而是地图和编剧组织混在了一起。

本轮冻结定义：

```text
内容地图 = 围绕冻结根发散可研究的人、时间、地点、事件、种类、文化、作品和关系
编剧脑 = 在一条已取证路径上识别主体、目标、阻碍、行动、代价、结果变化
```

地图提示已移除“事件与冲突”和所有博弈式召回，改为可核验事件及实际关系；关系差异按差异、协商、角色互动或融合表达。证据阅读不再产出 TopicBrief。新增选题总编，先判断证据是否足以立题，再决定是否附带可选 `NarrativeFrame`。叙事六项必须完整且引用真实观察，说明型选题可以没有故事，弱证据可以完全弃权。

测试按红绿重构：第一次因 `TopicEditorialDecisionDraft` 不存在而在收集阶段失败；实现合同后，候选 ID 不一致测试抓到夹具错误；新增叙事完整性、显式弃权、证据引用、渲染、Lead 投影与框架标签净化回归，聚焦结果为：

```text
202 passed in 2.94s
```

## A15 真实模型反例、召回污染与珠峰行动链

婚礼主持反例使用 DeepSeek V4 Pro 运行。内容根为 `婚礼仪式`；网页搜索无结果后保留仪式形态、环节与象征、人物角色、地域、历史变化、比较及作品地图，没有 TopicBrief 或叙事骨架。它仍使用了一次“习俗冲突与融合”措辞，虽非剧情结构，但语义容易混淆，因此地图与正文总编进一步收紧为“差异、协商、角色互动或融合”，不升级为戏剧阻碍。

```text
embedded thread: live-conflict-wedding-v6
model: deepseek-v4-pro
result: root and map passed; research degraded safely; no forced story
```

陌生登山装备题选择登山/徒步活动并展开路线、季节、身体、同行、风险、地域、历史与作品。该次没有召回到已取证命名事件，正确没有生成故事：

```text
embedded thread: live-story-editor-mountaineering-v6
model: deepseek-v4-pro
result: divergent map passed; no named evidence and no forced story
```

随后使用 [英国皇家地理学会 1953 珠峰资料](https://www.rgs.org/our-collections/buy-and-license-images/limited-edition-platinum-prints/everest-1953-limited-edition-platinum-prints) 做受控证据测试，先后发现两层真实故障：

1. 命名召回猜测“两人背景差异、功绩归属争议”，证据仅支持首次突击折返、第二次冲顶、希拉里台阶和最终登顶。旧总编把召回理由误当必须兑现的选题合同，因此弃掉了已经完整的事件行动链。
2. 隔离召回假设后，总编开始形成 TopicBrief，但自然返回的选题级 `limitations` 不在合同内，严格 Schema 拒绝输出，修复重试仍失败。

修复方式不是追加行业案例。阅读与总编输入删除 `why_worth_reading`、`relation_to_root` 和 `search_queries`；最终路径理由与命名连接改由已取证 TopicBrief 机制生成；`TopicBrief.limitations` 正式进入合同、渲染与 Lead 投影。

最终受控运行生成：

```text
record: record-controlled-everest-3
model: deepseek-v4-pro
topic: 首次突击折返后，希拉里与丹增的第二次冲顶如何成功
narrative: protagonist + goal + obstacle + action + stakes + outcome all present
fact boundary: single-source limits and inferred stakes shown explicitly
result: passed
```

这证明当前“编剧脑”不是一个强迫每条内容制造戏剧的写作模板，而是证据后的可选组织能力。真正页面能否稳定召回足够好的全文资料仍取决于后续搜索与抓取质量，不能用这次受控证据通过冒充全链路来源能力已经完成。

## A16 全量回归与运行环境说明

第一次全仓回归在根 `AGENTS.md` 软预算与本地认证开关处失败。前者通过把根指南恢复为导航层解决；后者来自未跟踪 `.env` 中用于本地页面的 `DEER_FLOW_AUTH_DISABLED=1`，不是产品代码回归。测试子进程显式使用 `DEER_FLOW_AUTH_DISABLED=0`，同时保留 Gateway 的本地免登录运行方式。

最终完整离线后端套件：

```text
11601 passed, 76 skipped, 17 warnings
elapsed: 442.39s
NO_PROXY: 127.0.0.1,localhost
test auth mode: DEER_FLOW_AUTH_DISABLED=0
```

Gateway 已用当前源码重启在 `127.0.0.1:8003`，前端 `127.0.0.1:3001` 返回 200。未跟踪配置与 API Key 未进入测试输出、文档或提交候选。

## A17 提交前证据隔离审阅

全量回归前的逐文件审阅又发现三处不会改变架构、但会污染证据归属的实现缺口：

1. 证据阅读原本只能保证来源属于本轮搜索，却没有保证来源属于最终所选候选；候选 A 理论上可以借候选 B 的搜索回执立题。
2. 选题总编原本会看到所有候选的来源标题与 URL，即使规范化阅读只选择了其中一条路径。
3. `NarrativeFrame` 可以引用中心判断之外的额外观察，但这些观察原本不会自动进入 TopicBrief 的总证据引用和最终来源列表。

三条都先增加失败测试，再做最小修正：阅读观察必须绑定所选候选的来源；选题总编只接收阅读实际引用的来源回执；叙事专用观察并入选题证据并参与最终引用。另增加运行边界测试，确认任何根后研究异常都降级为已经冻结的地图，不让可选研究拖垮主要回答。

最终聚焦回归：

```text
220 passed in 3.95s
```

最终完整后端回归：

```text
11601 passed, 76 skipped, 17 warnings
elapsed: 442.39s
```

文档架构图同步更正：内容世界总编只写地图正文；可选的证据 TopicBrief 由确定性渲染器在模型调用后追加，因此正文模型看不到也不能改写已经绑定的事实、限制或叙事骨架。

## A18 清空会话与记忆后的黄金礼品端到端回归

为排除旧会话、长期记忆、检查点和运行残留对判断的影响，本轮先清空本地运行状态，再从唯一一条用户消息启动完整页面链路。清空后的基线为：

```text
threads: 0
memory facts: 0
memory summaries: 0
checkpoints: 0
writes: 0
```

测试输入、运行身份与结果：

```text
input: 我是做黄金礼品的，我要怎么起号？
model: deepseek-v4-pro
thread: 4f0735cd-edf6-40b3-b33c-3cdeeb8b38f1
run: 32b50cd7-6b75-4023-9351-6b8c025c1d3e
elapsed: about 120s
tokens: 26,042 (input 21,367; output 4,675)
llm calls: 7
infrastructure result: passed
business acceptance: failed
```

语义阅读并未失败。它正确拆出了 `黄金礼品` 的词汇中心是 `礼品`、`黄金` 是材质修饰，也召回了赠送、馈赠、婚嫁礼俗、节庆送礼、商务社交与人情往来等方向。根选择器同样生成了以下竞争候选：

```text
黄金礼品
赠送黄金礼品
作为情感与面子载体的送礼/回礼
中国人情往来的贵重礼物世界
```

第一处失败发生在收敛：根选择器仍选择 `黄金礼品`，并把“完整商品对象”误当成优先于“更大且仍能回到商品的有效内容世界”的理由。冻结地图因此同时展开黄金品类、工艺、金价、成色标准和产品比较；人情往来、婚嫁、满月、历史与文学虽然出现，却只是产品地图下的分支。最终正文标题仍为 `黄金礼品`，并明确声称最稳中心不是赠送动作，而是黄金礼品这个完整对象。

第二处失败在编剧脑：即使搜索已经找到潮汕婚嫁送聘、满月金锁等人情路径，当前总编仍只整理出一条礼俗说明题，更像证据选题编辑，而没有选择一个具体的人情事件，组织其中的人、关系目标、阻碍、处理和关系变化。对本案例，编剧应该编的是人情世故中的故事；黄金最多是事件中的礼物、道具或业务承接，不是故事主角。

本轮通过项包括：干净状态隔离、Lead 只调用内容世界工具、语义拆分、选根后搜索、来源限制、弱证据边界、非强制叙事和单次直接交付。它们不能抵消根选择失败。用户指定的目标链仍是：

```text
黄金礼品 -> 礼品 -> 送礼 -> 人情往来
```

因此，A11 中“黄金礼品已进入赠礼往来中的人际关系与仪式”的通过结论不再视为稳定验收；本条记录将其覆盖为一次可复现的干净环境回归失败。它同时证明问题不是旧记忆污染，而是候选已经被召回后，最终选择规则与模型收敛仍偏爱产品名词，且证据总编尚未真正承担编剧职责。该会话及结构化中间结果保留为下一版冻结回归证据，在提出新机制前不对本案例继续提示词调参。
