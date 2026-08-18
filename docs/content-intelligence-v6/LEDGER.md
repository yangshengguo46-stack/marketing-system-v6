# 第六版内容孵化内核台账

## 当前状态

- 台账日期：2026-08-18
- 第五版冻结提交：`3ee135f7`
- 第五版归档分支：`codex/archive-v5-final`
- 第五版归档标签：`marketing-v5-final-20260814`
- 第六版官方 DeerFlow 起点：`cd87968aea97b487380ea9586747d1ed8cdb5865`
- 第六版开发分支：`codex/v6-comprehension-core`
- 当前结论状态：`A98 existing modules minimally rewired on paper; runtime unchanged`

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

## A19 最大有效内容世界修正与创意收敛回归

A18 冻结后先写提示合同红测，再移除“对象能独立成立便优先保留对象”和“使用动作只是地图节点”的旧规则。新标准比较与原表达直接相连的最大有效内容世界，并明确完整商品或服务没有先验优先权。聚焦离线回归为：

```text
49 passed in 3.13s
```

随后再次删除唯一旧会话和记忆，以同一句输入运行页面真实链路：

```text
input: 我是做黄金礼品的，我要怎么起号？
model: deepseek-v4-pro
thread: 6051b448-196b-4ed0-bac3-9c82ff9d994b
run: a7694291-8720-4b7d-bc12-89f34a465519
elapsed: about 181s
tokens: 29,077 (input 22,197; output 6,880)
root selection: passed
rooted map: passed
fact-boundary abstention: passed
evidence-backed story: failed
overall end-to-end: failed
```

内容根选择器比较了黄金礼品物件、送礼动作和送礼关系世界，最终选择“中国人情往来与送礼关系世界”，正文也明确账号长期理解和讲述的是人情往来与送礼关系，而不是黄金工艺。这说明 A18 暴露的根选择问题在本次干净运行中得到修正，但单例通过不等于跨行业稳定。

下游没有讲出故事。命名召回生成了不存在于证据中的“溧阳等地张涛式天价彩礼事件”，有限搜索只找到宽泛评论、福清彩礼报道和一条谣言澄清。证据阅读正确指出人物、地点与事件均未得到支持，创意收敛随后弃权。地图中另有“十里红妆”等获得有限证据的分支，但当前合同绑定一个候选后不会自动改选，因此最终只交付了内容地图。

本轮据此修正模块定义：不新增独立编剧 Agent；地图后的 `TopicEditor` 只是从已取证路径形成选题的创意收敛动作，`NarrativeFrame` 是可选结果。真正写成微短剧或其他叙事作品属于后续表现形式适配。强行要求命名召回优先寻找行动链曾诱发虚构专名，该提示增量未被采用。下一轮应使用新留出材料比较候选先行检索与方向先行检索，不能继续在黄金案例上补关键词。

最终完整非 live 后端回归中，全部 `11600` 项功能测试通过；唯一失败是本轮补充说明使 `backend/AGENTS.md` 超出文档软预算。压缩导航说明、保留 ADR 细节后，文档预算定向测试通过：

```text
full run: 11600 passed, 76 skipped, 1 documentation-budget failure, 17 warnings
targeted documentation rerun: 1 passed
```

## A20 地图方向搜索与模型联想双路并行

A19 证明内容根和地图已经可以通过，但“模型先猜专名、搜索只核验该名字”的单路结构会被一个虚构候选锁死。此次没有继续用黄金礼品调提示词，而是先建立新的“共享用餐”留出测试。旧实现得到预期红灯：地图方向搜索没有启动，证据阅读合同也没有位置记录搜索独立发现的实体。

新结构保持“先冻结内容根”不变。冻结地图之后，第一条地图方向查询与模型命名联想同时启动；模型返回后，地图方向与联想候选的查询交替占用同一总量预算，并在统一来源回执中汇合。证据阅读可以选择地图搜索实际发现的实体；若选择模型联想路线，则不能在阅读阶段更换实体。`selected_entity_observation_refs` 将最终实体绑定到来源观察，避免只有名字、没有证据。

实现同时修正供应商结构化输出边界：单一合同收到多份工具调用时确定性失败并进入已有的一次修复，禁止像上一轮 DeepSeek 回执那样静默采用第一份。相同 URL 只保存一次内容，但保留它与多条研究路线的关联。

测试先后证明：

- 一个错误联想存在时，地图方向搜索发现的真实事件可以胜出。
- 模型没有召回任何专名时，地图搜索仍可独立形成 `TopicBrief`。
- 两路查询可同时执行，并受 `6` 次总查询、`3` 次并发、`8` 个唯一证据项的技术上限约束。
- 来源隔离、弱证据弃权、可选叙事和冻结根合同没有被放松。
- 多工具调用不会再因输出顺序决定答案。

聚焦回归结果：

```text
content-intelligence: 53 passed in 3.37s
research module: 15 passed in 2.20s
guidance soft budget: 1 passed in 2.06s
ruff check / format check: passed
```

该结果只批准进入真实端到端复验，不代表黄金礼品或跨行业已经验收。架构决策见 `ADR-006`。

## A21 获胜路线隔离、原文阅读与真实复验

新网关的第一次真实复验证明双路已经执行，但最终页面只显示内容地图。内部底稿定位出一个具体合同故障：证据阅读选中了 `map_direction_search`，却在观察列表中顺手记录了另一路的无关搜索噪声。该噪声没有被最终实体、关系或解释引用，但旧校验器仍将整份阅读作废。

修复先以真实回执写成红测试。确定性投影现在只保留获胜路线的观察、依赖这些观察的关系/状态变化/解释，以及实际被保留的来源。已知旁路噪声可以被比较后丢弃；伪造来源、用另一候选的证据绑定获胜实体，以及联想路线换名仍然硬失败。

修复后的真实运行仍然弃权。此时日志已能确认获胜路线和来源数，新病根不再是路线污染，而是所谓“联网证据”只有搜索引擎摘要，没有打开原文。选题总编对弱摘要弃权符合事实边界，因此没有通过放宽提示解决。

证据管道随后补上“打开原文”：去重后的公开 URL 优先由本地受控读取器处理，运营者配置的 `web_fetch` 只作后备。原 URL 在进入任一读取器前先做公网地址校验；本地读取器还会在每次跳转前重新校验，拒绝非文本响应，单页最多下载 2 MB，每个来源最多保留 6000 字符。两种读取都失败时仍保留搜索摘要，不中断冻结地图。本机配置的 Jina Reader 实测连续超时，本地读取器对一个公开政府网页成功抽取 1023 字正文，因此外部 Reader 不再是单点依赖。

最终真实回归：

```text
input: 我是做黄金礼品的，我要怎么起号？
model: deepseek-v4-pro
thread: 21ee1c7a-be39-45ef-a61f-2591bdfc2f46
run: d3fc503f-58ad-4fea-877d-03884283f71e
elapsed: about 169s
tokens: 41,204 (input 34,349; output 6,855)
llm calls: 7
unique search receipts: 8
opened public pages: 6
selected route: map-direction-1-2 (map_direction_search)
selected observations: 11
selected sources: 3
```

最终回答证明“冻结根 → 双路发现 → 原文阅读 → 路线收敛 → 选题”的技术链路已经连通，但不能据此判定黄金业务通过。内容根在搜索前已经被选成“婚嫁礼俗与人情往来中的赠受关系世界”，地图随后几乎全部展开彩礼、嫁妆、礼簿与婚嫁角色，搜索只是继续取证这个错误根。用户要求的是“黄金礼品 → 礼品 → 送礼 → 人情往来”，婚嫁只能是其中一个地图分支。因此本轮基础设施验收通过，黄金业务验收失败；此前“有条件通过”的判断由本条更正。

聚焦回归：

```text
content-intelligence: 60 passed in 3.35s
research + direct tool: 30 passed in 2.95s
full backend: 11,612 passed, 76 skipped, 17 warnings in 446.55s
ruff check / format check: passed
```

## A22 黄金婚嫁漂移尸检与候选裁决拆分

本轮先暂停搜索改造，逐条读取 A21 真实运行 `d3fc503f-58ad-4fea-877d-03884283f71e` 的 12 个持久化事件。首次漂移位置得到确定：

```text
语义阅读：黄金礼品 -> 词法主词“礼品” -> 赠送/收受/维系关系（基本正确）
根选择：把“婚嫁礼俗”窄场景与“人情往来”宽世界拼成一个候选并选中（首次失败）
冻结地图：只收到错误根，忠实展开婚嫁（后果）
联网搜索：只沿错误地图取证婚嫁（放大后果，不是首因）
```

旧根选择器在同一次模型调用中生成候选、命名候选、选择赢家并解释赢家。虽然提示文字已经禁止“窄对象与宽世界混合”，合同只校验索引存在，未在结构上区分根候选与示例分支。相同模型、相同输入、相同提示的三次无搜索隔离探针分别选择：

```text
婚嫁与人生礼仪的赠礼关系世界
黄金赠礼活动
送礼与表达心意、体面的人情往来
```

这证明 A19 的单次正确根不是稳定能力，病根也不是旧记忆或搜索质量，而是一个工作者对自己生成的候选进行自证式裁决。

修复先写红测试，再做职责拆分：候选召回只输出候选并标记 `root_candidate / example_branch`，独立裁决只在冻结的 root-candidate 子集中选择索引；代码层禁止 example-branch 成为内容根或观众领地。该拆分连续三次都把婚嫁降为分支，但其中两次仍停在“赠予”或“礼品/送礼”，说明还缺“多个场景共同发生了什么”的阅读跃迁。

随后建立一个不含行业示例的跨场景共同世界原型，只读取活动、参与者关系与具体场景。原型三次都得到“人情馈赠/人情馈赠礼俗”。第一次接入仍把完整商品名、材质和保值功能传给它，三次结果又残留“贵金属/贵重”，证明提示模型忽略高显著信息不如直接隔离信息。最终输入边界改为只提供：

```text
去修饰后的词法主词
参与活动
具体社会文化场景
```

它看不到完整商业对象、修饰语和商品价值功能；共同世界若成立，会确定性进入根候选，但仍由独立裁决与对象、活动等候选公平比较。系统提示与合同不包含黄金、婚嫁或任何回归行业答案。

同一 DeepSeek 模型的最终三次无搜索根探针为：

```text
以物系情、以礼定关的人生人情往来世界
郑重馈赠与关系维系
人情与关系往来的礼物世界
```

三次均将婚嫁、节庆、商务等保留为 `example_branch`，没有材质、保值或贵重限定。随后一次真实“到地图为止、禁用搜索”的完整运行得到：

```text
content_root: 人情往来的礼尚世界
audience_territory: 人情往来的礼尚世界
map: 随礼与还礼、礼的规则与分寸、人物关系、地域、历史变化、面子、人情债
婚嫁位置: “红白喜事中的随礼与还礼”分支
```

截至本条，黄金的语义跃迁、根选择和冻结地图通过；联网研究与具体选题尚未在新根上重新验收，不得借旧 A21 搜索结果宣称完整端到端通过。聚焦内容智能测试为 `62 passed`；在显式关闭本地开发用的鉴权旁路后，后端全量回归为 `11,614 passed, 76 skipped, 17 warnings`。架构决策见 `ADR-007`。

## A23 黄金根复验、共同世界审查与跨行业回归

A22 的三次短探针通过后，一次完整真实运行又选出“贵重赠予与价值传承的华人礼俗世界”。首次错误仍发生在搜索前：去修饰共同世界输入虽然看不到黄金，后续自由候选生成器却重新看到完整语义，并把黄金的保值与贵重价值拼回关系世界。仅收紧共同世界提示后又出现反向污染：海鲜被提升为待客世界，火锅底料被提升为聚餐涮菜。由此确认“同一黄金题多跑几次”不能证明通用能力，至少要让黄金、海鲜和火锅同时回归。

本轮先写失败测试，再做三项结构调整：

1. 语义合同增加去修饰后的活动、功能和场景，材质、地域、价格等被移除后不成立的价值与案例不得回流。
2. 新增独立共同世界反事实审查。把主词替换为大量无关对象后仍完整成立的普通使用、消费、制作、交易或聚会场景，不能成为共同世界。
3. 删除自由候选生成模型调用。代码从原语义值确定性装配候选并标明 `served_object / subject_activity / subject_function_or_use` 等来源；根裁决只接收对象角色及冻结的类型和名称。

第一次类型化裁决后，黄金和海鲜通过，火锅底料只走到“成品锅底”。语义阅读随后增加递归对象边界：中间实现物不能停在另一个中间产物，必须继续追到最终可独立识别、体验或参与的完整对象。最终同一默认 GLM 模型的并行真实回归为：

```text
黄金礼品 -> 人际馈赠与礼物交换
海鲜 -> 海鲜
重庆火锅底料 -> 火锅
```

黄金地图展开礼物种类、关系、仪式、历史、地域与文化；婚嫁不再成为内容根。海鲜没有被待客、烹饪或流通取代，火锅底料没有被聚餐或涮菜动作取代。聚焦测试为 `52 passed`，Ruff 通过。架构决策见 `ADR-008`。

## A24 搜索污染、供应商路由与证据角色审计

黄金根通过后才恢复搜索审计。代码发现 `_search_content_world_evidence` 虽声明使用当前搜索配置，实际硬编码 DuckDuckGo；同时每条地图方向查询机械追加“人物 事件 作品 记录”。真实查询的五条结果中，三条因此偏成作文素材与时间线工具。删除泛词后，结果回到礼物交换与人类学，但免费 DDG 中文结果仍混入低质页面，不能作为正式质量基线。

实现改为解析当前 `web_search` 配置，并兼容标准对象、列表及字节 `Result.WebResults` 回执。新增字节官方 Web Search 薄适配器，支持查询改写、时间范围和权威来源过滤；它只读取独立 `WEB_SEARCH_API_KEY`。本机只有 Ark 模型配置，没有搜索专用 Key；直接探测 Ark Responses 的内置 `web_search` 返回 `ToolNotOpen`，因此适配器只进入可选配置，没有擅自开通或产生费用。

官方资料进一步确认：基础 Web Search 返回网页/图片；豆包 Chat 中可见的抖音视频卡片属于联网问答 Agent 的另一能力，当前还要求移动端 SDK、企业与内容资质、售前评估和后台授权，不能从 Chat 客户端表现推断普通 API 已开放。

证据角色同时固定：普通搜索结果一律是 `topic_evidence`。搜索可以返回视频或账号页，但单条结果不能升级为对标账号分析；对标需要独立账号身份、多作品采集与覆盖回执。一次完整黄金搜索复验中，DDG 的六次查询均因外部连接失败而没有回执；内容根在搜索前后保持不变，来源与 `TopicBrief` 为空，证明“找不到就弃权”已经成立。架构决策见 `ADR-009`。

最终验证结果：

```text
content intelligence + search focused: 68 passed
repository guidance budgets: 12 passed
backend full non-live: 11,626 passed, 76 skipped, 17 warnings in 473.75s
ruff check / format check / git diff --check: passed
```

## A25 抖音 OpenAPI 全能力审计与 MCP 路由决策

2026-08-16 用户在抖音开放平台完成相关能力开通后，重新以当前官方移动/网站应用文档为准审计。结构化解析目录页面得到 13 张 API 表、119 个目录条目，主要覆盖个人资料、关系与粉丝画像、内容、搜索、私信群聊、数据开放、生活服务、素材工具、服务市场、小程序推广计划、分身技能数据和汽水音乐。此前按同站链接口径得到的 118 不是目录行数，现由结构化表格解析结果更正。119 也不代表 119 个可由 Agent 主动调用的 API：目录包含 OAuth、平台向商家发送的回调和要求接入方实现的接口，后续必须逐项标注交互方向。此前 A24 将“豆包 Chat 的视频结果”与普通 Web Search 区分是正确的，但“当前尚不能通过 OpenAPI 使用抖音视频搜索”的环境结论已经过时，由本条覆盖。

当前视频搜索正式合同为：

```text
GET https://open.douyin.com/dy_open_api/v1/search/video/
scope: aweme.dy.video_search
auth: application stable_client_token
required query: keyword, count, device_id
pagination: cursor + search_id + has_more
```

官方说明非字节内部租户的 `device_id` 可传随机数。稳定应用令牌有效期为 2 小时，有效期内重复获取返回同一令牌。官方 SDK 页面支持 Java、NodeJS 和 Go，Token 仍由调用方注入，并明确提示多实例若各自取 Token 会互刷。

第一条代码纵向切片已经按测试先行实现：新增官方视频搜索薄适配器，使用稳定令牌缓存，遇到无效或过期令牌最多刷新重试一次；返回仅保留视频 ID、标题、公开视频链接、高质量文本、作者昵称、发布时间和点赞观察值，不返回 Client Secret、Token、设备 ID、临时封面或头像 URL。现有内容研究同时调用网页搜索和可选抖音视频搜索，按来源交错占用同一证据预算；两者仍统一属于 `topic_evidence`，不能自动升级为对标账号。

聚焦红绿测试：

```text
red: ModuleNotFoundError: deerflow.community.douyin_search
green: 20 passed in 3.16s
```

全量能力不按 119 个 Lead 工具实现。采用版本化 Catalog/Manifest、鉴权代理、风险分级和领域 Child 调度器组成的独立 `douyin-openapi-mcp`；所有目录条目进入 Catalog，只有完成合同审阅、属于主动调用、当前应用已获 Scope、当前用户具备账号授权且符合任务风险的能力才成为可调用 Child。自有账号粉丝画像仍只用于该账号复盘，不能回答竞品粉丝画像。完整决策见 `ADR-010`。

## A26 Apache Doris MCP Server 1.0 升级复核

2026-08-16 按用户提示重新审阅 Apache 官方仓库当前 `master`、1.0.0 发布记录、架构、请求生命周期、能力可用性、安全、可靠性与核心实现。1.0.0 于 2026-08-01 发布，正式将旧版平铺工具替换为 8 个稳定只读领域和 55 个渐进披露 Child；发布快照记录 `1772 passed, 83 skipped`，另有 26 个真实 Doris 集群测试。当前 `master` 比 1.0.0 多 16 个提交，最新已到 2026-08-13 的 `#218`；其中 `#199` 专门修复推测性多领域发现：要求 Host 先选一个领域，领域说明明确职责和排除项，避免每轮携带多份 Manifest；`#204` 继续加固只读与 HTTP 安全边界。该版本不是概念图，仓库已包含 `domain_catalog.py`、`domain_manifest.py`、`domain_dispatcher.py`、`capability_detector.py`、Schema 校验、目录生成和对应测试。

与抖音 OpenAPI 网关直接相关的已验证设计如下：

```text
tools/list -> 稳定领域工具
domain {} -> 授权 Child + 精确 Schema + Availability + manifest_version
domain {child_tool, arguments, manifest_version}
  -> 重新鉴权
  -> 重新探测当前能力代际
  -> 拒绝过期 Manifest
  -> 输入 Schema 校验
  -> 精确 Handler
  -> 输出 Schema 校验
  -> data / warnings / metadata 或确定性错误
```

Doris 明确区分“公共目录能表示什么”和“当前身份、路由现在能安全调用什么”：未授权 Child 不披露，授权但不可用的 Child 以 `callable=false` 和稳定原因码保留；不使用概率式意图分类器猜工具。Manifest 版本是领域合同、Child 合同和能力代际的 SHA-256 派生值；代码还固定顶层 `tools/list` 24 KiB、Child 描述 800 字符、单个输入/输出 Schema 4 KiB、枚举 32 项等硬预算，并由同一能力目录生成文档、在 CI 检查漂移。

发布后经验进一步说明：渐进披露不是让 Agent 先把所有领域都打开一遍。顶层描述必须足够互斥，Host 只展开一个最匹配领域；用户下一轮改变问题时再切换。这是确定性编排纪律，不是 Server 端概率分类器，也不是把用户锁进固定工作流。

采用结论：更新 ADR-010，使抖音网关对齐这套分层发现和精确执行合同；借鉴协议与测试方法，不复制 Doris 专属探测器和数据库 Runtime。Doris 1.0 内置能力全部只读，不能覆盖抖音写操作的内容绑定审批、幂等、费用、未知状态对账和禁止盲重试，这部分继续由抖音网关独立承担。

官方证据：

- `https://github.com/apache/doris-mcp-server/releases/tag/1.0.0`
- `https://github.com/apache/doris-mcp-server/issues/189`
- `https://github.com/apache/doris-mcp-server/blob/master/docs/architecture/request-lifecycle.md`
- `https://github.com/apache/doris-mcp-server/blob/master/doris_mcp_server/tools/domain_manifest.py`
- `https://github.com/apache/doris-mcp-server/blob/master/doris_mcp_server/tools/domain_dispatcher.py`
- `https://github.com/apache/doris-mcp-server/commit/b7b66f5f80becdab7080d8b92a3bce17032752ca`

## A27 抖音 OpenAPI 目录快照、领域网关与真实 MCP 协议验收

2026-08-16 按 `ADR-010` 测试先行实现第一个可运行网关版本。失败基线为
`ModuleNotFoundError: deerflow.community.douyin_openapi`；随后建立内容寻址的官方目录快照、
16 个互斥领域、授权感知 Manifest、SHA-256 `manifest_version`、精确 Child 调度、
Draft 2020-12 输入/输出 Schema 校验和硬字节预算。顶层 `tools/list` 只暴露 16 个
`douyin_*` 领域，明确不存在与所有领域重叠的 `douyin_capabilities`。

结构化快照将 119 条分为：106 条 `outbound`、6 条 `provider_implemented`、5 条
`auth`、1 条 `inbound_webhook` 和 1 条 `local_utility`。文档追踪只在 45 条页面取到
可识别 HTTP 合同；68 条目录链接当前只返回空壳或迁移页，其余为回调、加密或无端点说明。
这些空壳记录保留在谱系和能力矩阵里，但没有根据名称反推 URL、参数或可用性。

首批采用两个同鉴权、公开只读的搜索 Child：

- `video_search` / `aweme.dy.video_search`：复用 A25 已验收的稳定令牌和视频证据投影。
- `experience_search` / `aweme.experience.search`：新增图文/经验搜索，最多 10 条，只保留稳定内容 ID、标题、作者、体裁和时长，丢弃临时封面 URL。

真实 MCP stdio 客户端已启动安装后的 `douyin-openapi-mcp` 子进程，完成
`initialize -> tools/list -> tools/call douyin_search {}`。回执为 16 个领域、无全局能力工具、
2 个搜索 Child 和 64 位 Manifest 版本。本机未配置抖音 Client Key/Secret，因此两个 Child
均正确显示 `callable=false / auth_not_configured`，未向平台发请求。这证明本地 MCP
协议链和失败边界通过，不代表真实抖音 Scope 验收。

快照与全量矩阵见
`evidence/douyin-openapi-catalog-2026-08-16.md`。授权账号令牌代理、粉丝画像、素材写入、发布、交易、
幂等、审批与未知结果对账仍未实现，不得标记为生产可用。

本轮最终验收如下：

```text
Douyin gateway + search focused: 34 passed in 3.14s
catalog report drift check: passed
ruff check / format check / git diff --check: passed
real MCP stdio: 16 domain tools; 2 scoped search Children; missing credentials -> auth_not_configured
wheel inspection: catalog_snapshot.json, server.py and search adapter present
backend full non-live: 11,640 passed, 76 skipped, 17 warnings in 397.01s
```

## A28 当前黄金起号链路真实端到端回执

2026-08-16 在全新聊天、无历史消息、`GLM-5.2 / Incubation candidate` 下运行用户原话
“我是做黄金礼品的，我要怎么起号？”。本次不是短探针，也没有隐藏标准答案；它从 Lead
真实调用现役 `explore_content_world`，依次经过语义阅读、内容根选择、冻结地图、资料发现、
证据阅读和选题编辑，再由 Lead 输出最终回答。

运行回执：

```text
thread: 114ac37d-0893-457b-90d9-e97ab7bd3ff5
run: 5f7d751f-53f4-4d7a-8fa3-24908bb1161c
status: success
elapsed: 6m04s
LLM calls: 7
input tokens: 32,827
output tokens: 10,026
total tokens: 42,853
```

语义与地图部分通过了这一个案例的核心检查：最终内容根为“以黄金礼品为媒介的馈赠关系与
人情往来”，明确把黄金当特异性锚点，把长期内容世界放在人们如何传心意、定关系、完成
仪式上；婚嫁只保留为人生节点之一。地图覆盖礼物选择、人情规则、人生节点、参与者、历史
地域、再流通、经济环境和禁忌边界，没有退回单纯讲材质、工艺和产品陈列。

但本次不能标记为完整起号通过：

- 用户问的是“怎么起号”，最终交付主要是一份约一万输出 Token 的百科式内容地图，没有
  收敛成可直接理解的账号主张、受众入口、表现形式选择及少量代表性栏目。
- 研究阶段按“公开证据最强”选择了金钱礼物社会学，而不是按账号长期价值与普通观众兴趣
  选择内容分支；最终具体选题因此过度学术化。
- 大地图中的地域差异、消费趋势、城乡差异、数字黄金等许多陈述没有逐项绑定本轮证据，
  只能视为待核验联想，不能和已取证事实混写。
- 七次模型调用、六分钟和 42,853 Token 对一次普通起号咨询不可接受。搜索与证据阅读应当
  服务选中的具体分支，不能迫使每次内容地图都完成论文级取证。
- 本轮 Gateway 日志显示 `MCP tools: 0`。它验证的是当前内容智能链，不是 A27 抖音
  OpenAPI MCP 的真实凭证、Scope 或平台回执闭环。

当前结论为 `reviewed -> partial pass`：内容根与地图方向通过，起号交付、事实边界、延迟与
成本未通过。制作板块继续暂停；下一步应先把“世界发现”和“面向用户的起号收敛”分开计费
与触发，保留宽地图，默认只输出短判断和代表性路径，联网取证仅在用户选择具体题目或明确
要求调研时启动。本条只冻结观测与诊断，不修改现役提示词或工作流。

> 2026-08-16 用户复核覆盖：A28 的“内容根与地图方向通过”判定不成立。
> “以黄金礼品为媒介的馈赠关系与人情往来”仍被黄金、礼品与馈赠锁定，
> 没有继续走到“礼”及人与人如何相处。A28 改判为 `reviewed -> failed`，
> 并由 A29 取代；技术运行成功不等于业务语义通过。

## A29 词法主词、语义核与内容根隔离验收

2026-08-16 根据用户对 A28 的纠错，先冻结失败条件：黄金礼品的最终地图不能继续是黄金、礼品、送礼、回礼与婚庆场景的展开；必须允许语义从词法主词“礼品”继续读取真子成分“礼”，再沿其实际语义家族进入人际规范、仪式、制度、秩序和历史变化。反例同时冻结：海鲜不能机械拆成“海”的哲学，火锅底料不能因“火锅”可联想多人共食就转成团圆饭或夜市，水果店不能被店务运营压过水果。

三次黄金真实无搜索运行将失败点逐步定位：

1. 第一次中，商业语义工作者没有输出意义核，共同世界回到“以物为媒介的人际馈赠与关系再生产”，地图全部是送礼和回礼，失败。
2. 第二次将语义家族隔离后，正确得到“礼”及礼尚往来、先礼后兵、克己复礼、礼崩乐坏、分庭抗礼和非礼勿视；但共同世界被命名为学术化的“礼治秩序下的人际规训与社会建构”，根裁决转而选择“赠予他人”，仍失败。
3. 第三次要求共同世界覆盖多个实质不同的语义分支，并用普通人可理解的生活问题命名。最终内容根为“人们如何用礼来组织人与人的相处”，根裁决明确将馈赠、礼物交换和心意表达降为该世界的平行分支。地图进入互惠回报、尊敬招纳、先协商后强制、秩序崩塌、自我约束、跨文化礼制、人际关系类型、历史文本和当代礼节，通过。

隔离词义工作者的真实对照探针表明：只给“礼品”时可以识别“礼”为社会关系或文化制度语义核；只给“海鲜”时，“海”只是来源对象，“鲜”只是品质；只给“火锅”时，“火”与“锅”分别是自然元素与器具，均不触发人文语义家族。真实并发反测曾暴露模型把“海”误标为文化制度、把“火锅”误标为人类活动并联想团圆饭的问题；最终边界因此排除自然来源与词内活动的跨域展开。

最终冻结真实回归为：

```text
黄金礼品 -> 礼 -> 人们如何组织人与人的相处
海鲜 -> 海鲜
水果店 -> 水果
重庆火锅底料 -> 火锅
```

重要限制：这是语义核与冻结地图的无搜索验收，不是完整起号交付。自由女神、国礼、埃文·凯尔、周公制礼作乐等具体题目需要在冻结根之后进入搜索、正文阅读与事实边界；本轮没有使用搜索，不得宣称这些选题已被系统取证。架构决策见 `ADR-011`。

本轮最终验证：

```text
content-intelligence focused: 55 passed
repository guidance budget: passed
backend full non-live: 11,645 passed, 76 skipped, 17 warnings in 466.91s
ruff check / format check / git diff --check: passed
```

第一次全量测试曾出现 37 个认证、CSRF 和渠道连锁失败。复核发现根目录本地 `.env` 为右侧开发页面配置了 `DEER_FLOW_AUTH_DISABLED=1`，而 `uv run` 会自动载入该文件；因此测试进程实际处于免登录模式。失败组在显式 `DEER_FLOW_AUTH_DISABLED=0` 后为 `479 passed`，完整套件也全部通过。该回执是测试环境边界，不修改本地产品运行配置，也不把配置误差记作语义架构回归。

## A30 词典、词义图与向量召回可行性审计

2026-08-16 根据用户提出的“为语义和内容根建立向量库并装入《现代汉语词典》”设想，审计结论为 `reviewed -> offline comparison required`：词汇知识可以补强 A29 的词义证据，但不应直接采用“整本词典切块 + 相似度检索”，也不应让词典或向量分数裁决内容根。

当前问题包含三个不同任务：复合词内部是否存在仍然承载含义的语素、该语素在当前上下文采用哪个义项、多个义项与固定表达是否能连续进入更大的内容世界。普通向量检索主要回答“哪些文本相似”；查询“礼品”时很可能继续召回礼物、赠品、礼盒等相邻表达，反而加强已经失败的馈赠世界。它也无法单独证明“礼品”可读取“礼”，同时“海鲜”不能据此机械拆为“海”和“鲜”。汉语复合词研究区分透明与不透明组合，词义不是语素义的简单相加；词义消歧研究也把上下文义项和词义库存作为独立问题。向量可用于发现候选关系，但不能代替可检查的构词关系和义项连续性。

建议候选是可插拔的 `LexicalEvidenceProvider`：

```text
词法主词
-> 整词精确查询
-> 真子成分/语素精确查询
-> 义项、词性、构词关系和固定表达图
-> 上下文义项审查与支持/反例
-> 现有隔离词义工作者
-> 现有共同世界与内容根裁决
```

首版以 SQLite 结构化索引和精确/前后缀/关系查询为主，记录 `lexeme / sense_id / pos / gloss / morpheme / typed_relation / example / source / license / version`。向量检索只作为可关闭的二级召回，用于在已经确认的义项附近寻找遗漏表达；不得直接选语义核、改写冻结内容根或把高余弦相似度当意义连续性的证据。现有根裁决继续比较最大有效内容世界，词典只提供词义证据。

数据许可边界：商务印书馆将《现代汉语词典》第 7 版 APP 标为官方正版并提供全量 69,000 字词内容，整本数字化内容不能在没有明确数据授权时抓取、复制或嵌入；中国著作权法也保护具有独创性选择或编排的汇编作品。OpenHowNet 提供义原、义项、词性和例句查询，方向比普通词典切块更贴近本任务，但代码与核心数据许可仍须分别形成 SBOM 记录。Chinese Wordnet 官方条款仅限学术研究、禁止商业使用，排除直接采用。CC-CEDICT 当前下载页采用 CC BY-SA 4.0，允许商业使用但要求署名和对数据改进遵守相同许可，可作为离线原型候选，不等于最终中文释义质量已经验收。

下一步只做新保留集上的四臂离线比较：现役 A29 基线、精确词典、精确词典加关系图、关系图加向量召回。比较语义核准确率、机械拆词误报、最终内容根、地图可用性、延迟和 Token；黄金礼品、海鲜、水果店、重庆火锅底料只作为开发回归，不再充当新架构的隐藏测试。比较通过前不增加运行时向量数据库、不导入《现代汉语词典》、不修改根裁决权。

主要证据：

- `https://www.cp.com.cn/Content/2020/11-20/1505014314.html`
- `https://www.npc.gov.cn/c2/c30834/202011/t20201119_308796.html`
- `https://github.com/thunlp/OpenHowNet/blob/master/README.md`
- `https://lope.linguistics.ntu.edu.tw/cwn2/licence/`
- `https://cc-cedict.org/editor/editor.php?handler=Download`
- `https://lope.linguistics.ntu.edu.tw/projects/chinese-wordnet/`
- `https://direct.mit.edu/coli/article/47/2/387/98520/Analysis-and-Evaluation-of-Language-Models-for`

### A30 实施结果：结构化词义证据采用，稠密向量暂缓

2026-08-16 完成测试先行的可插拔 `LexicalEvidenceProvider`。本地 CC-CEDICT 索引支持整词
精确义项、严格子成分、借词/音译提示、有类型前后缀与词内关系、义项均衡选择、专名过滤、
输入输出预算、来源摘要和只读查询。`explore_content_world` 在
`CONTENT_INTELLIGENCE_CEDICT_INDEX` 存在时启用；未配置时自动查找
`backend/.deer-flow/lexicons/cc-cedict.sqlite3`，缺失、损坏或查询失败均保留纯模型路径。
本地路径、整库内容和商业词典均不进入模型、前端、日志或 Git；只有有界词义投影进入隔离
词义工作者。

官方 2026-08-15 CC-CEDICT 发布包建立 124,751 条本地记录，99 条被有界解析器跳过；解压
内容摘要为 `ac0696d1fc870770b7368f6088c6d08fed1e443a7526e08dc31426e6e7d594bb`。
冻结八词三臂严格自动结果为 `4/8 -> 5/8 -> 6/8`；允许“婚礼”同时以“婚”作为有效真
子成分后的人工复核为 `5/8 -> 6/8 -> 7/8`，两套分数分开保存。新的完整链案例“婚戒”
最终进入“婚的社会关系如何缔结、确认、重复与被安排”，没有回到珠宝工艺或宗教戒律。

真实运行同时定位到两个非检索问题：共同世界名称会擦掉已接受的“礼”，以及根裁决会让
“送礼、伴手赠送”因离商品更近而压过其所属的大世界。因此本轮用通用合同补充“保留意义
核”和“显式比较候选包含关系”，没有加入黄金、礼品、海鲜、火锅等行业关键词。

稠密向量臂没有伪造完成。当前没有经许可且冻结的嵌入运行时，而近邻相似度会优先加强
礼物、礼盒、赠品等已知错误方向。决定为 `reviewed -> structured evidence adopted for local
canary; dense vector deferred`。详细决策见 `ADR-012`，逐项运行回执见
`evidence/lexical-evidence-a30-2026-08-16.md`。

## A31 构成语境所有权与词内已选义项

2026-08-16 在 A30 的陌生案例 canary 中发现两个下游信息损失。`宠物殡葬` 的语义阅读已
将“宠物”判为构成语境，共同世界却二次推翻并泛化为人类死亡；`老年旅行团` 的词典整词
义项正确，共同世界却只看到“团”而被“团拜”分支带到节庆问候。两者都不是增加向量召回
能解决的问题。

本轮冻结职责：语义阅读拥有 `world_scope_effect`，共同世界只能消费
`required_constitutive_contexts`；若下游漏掉已冻结语境，该泛化候选被代码撤下。隔离词义
工作者同时向下传递去除原词后的 `selected_meaning_in_head`，词族例子不得覆盖这个锚点。
集合、组织或群体名称也不再仅因包含多人就自动算社会关系。

黄金礼品和重庆火锅底料真实回归通过；婴儿辅食、云南咖啡豆首跑通过。宠物殡葬的首次
失败、两次开发修正均单独保留。亲子研学团首跑没有复现团拜漂移，最终地图可用，但“亲子”
仍被上游误标为分支限定，故结论为 `reviewed -> local canary adopted with modifier residual`，
不是生产验收。决策见 `ADR-013`，证据见
`evidence/constitutive-context-a31-2026-08-16.md`。

最终验证为：内容智能聚焦测试 `73 passed`，开发守则 `12 passed`，Ruff 与格式检查通过，
后端完整非 live 测试 `11,665 passed, 76 skipped, 17 warnings in 451.18s`。17 条 warning 为
现有依赖弃用和测试用短密钥提醒，本轮无失败。

## A32 词义选定后的稠密向量召回

2026-08-16 应用户要求恢复 A30 暂缓的真实向量实验。首个失败测试证明，在词义消歧之前把
“礼”的 gift、rite、etiquette 等全部释义拼成向量查询，会优先强化礼物邻近词，重演商品
世界错误。因此候选顺序冻结为：结构化词义先选定 `selected_meaning`，稠密向量随后只补该
义项附近的表达，再进入共同世界阅读；它不回流改写词义，也不拥有内容根裁决权。

本地真实底座为 FastEmbed 0.8.0、`BAAI/bge-small-zh-v1.5`、512 维与 sqlite-vec 0.1.9。
模型快照、91 MB 工件、词典源和索引均绑定 SHA-256；100 词条烟雾索引与七项边界测试通过，
124,751 词条、512 维、约 260 MB 的全量索引已经完成，SQLite 完整性检查为 `ok`。全新七案例四臂比较完成 28 次唯一冻结运行，27 次合同成功。向量真正产生候选的只有家谱修复和婚书定制，结果均比无向量的关系臂更差；其他五案没有向量候选，回答差异不能归因于向量。

结论为 `discovered -> traced -> reviewed -> rejected`：可归因改善 `0/2`、恶化 `2/2`，同时延迟与 Token 都上升。正式分析器已删除实验期间的 `semantic_recall_provider`、模型提示和运行合同。用户最终确认舍弃后，实验代码、脚本、测试、向量索引、模型缓存与原始本地回执均已删除，仅保留本台账、ADR-014 与
`evidence/dense-vector-a32-2026-08-16.md`。

## A33 从内容地图到可拍交付

2026-08-16 用户明确了一个长期被忽略的产品边界：学术性和百科性展开本身不是错误，它们是模型理解语义和探索内容方向的内部工作；错误是把这份地图直接当成最终交付。最小可拍单元应当显示“谁、在什么情境下、遇到什么具体事情，账号站在用户的真实位置输出什么观点”。

本轮测试先行新增 `MessagePlan` 和 `BaseDraft`。它们位于 `TopicBrief` 之后，不反向修改语义、内容根、地图或证据账本。具体主体、事情、用户立场和观点为必备字段；时间、地点和场景在真正影响这件事时才填写，不为形式完整强行补造。用户立场只来自原话，不冒充专家，也不允许基础文案在未请求时回到销售和成交。

首个嵌套 `MessagePlan + BaseDraft` 真实合同失败：GLM 原始请求与一次修复请求都没有返回可恢复的工具参数。本轮没有追加更多修复轮次或提示层，而是将合同替换为扁平 `MessagePlanDraft`，再由代码确定性组合 `opening + message_beats + closing` 为基础文案。扁平合同真实单调用通过，白酒完整端到端回归也首次直接返回“今日建议拍摄”，没有再生成长地图正文。

结论为 `discovered -> traced -> reviewed -> adopted for local canary`。这一结论只验收了从取证选题到具体交付的结构；白酒回归所依赖的个人文章和商业站点不足以让价位、品牌和礼数判断进入生产发布。编剧脑、口播、图文、纯素材和第四版营销 Skill 均尚未迁移，下一步只能在 `MessagePlan` 之后按需路由。详见 `ADR-015` 和 `evidence/shooting-delivery-a33-2026-08-16.md`。

## A34 第四版营销与编剧能力迁移审计

2026-08-16 对第四版 `codex/ip-agent-v1-final` 分支完成只读追踪。已提交来源固定为
`58f4e0c900a2dc589fe4a23bdebbe8e3211b67b7`；审计时未提交补丁摘要为
`b40c03fd97df59f3cda4559eeada9f8cddc8d065c001215b24596e0b757324dc`，共 27 条状态记录。
未提交 Writer Brain、Lead、SOUL 与合同修改只作为演进和失败证据，不作为迁移候选。

历史显示第四版后期已经连续移除编排硬门、业务语义硬门和旧语义层，并将 97 个公共 Skill
全部隔离。现有 1137 行 `writer_brain.py` 仍同时承担故事生成、关键词封锁、固定因果标记、
事实发布闸门、版本、幂等与事务提交；其“必须逐字出现但、转而、只能、代价是”和 Writer 必须
先绑定 Editorial Program 的结构不能迁移。可保留的是事实/推断/虚构分离，人物目标、阻力、
行动、反馈、换招、选择与结果的故事机制，以及不可变版本、哈希、幂等和回执经验。

结论为 `discovered -> traced -> reviewed -> selective rewrite approved; runtime migration pending`。
营销方法将来进入独立项目级孵化判断，只向下游提供有界主体立场和资源约束，不得改写语义、
内容根或地图；编剧方法只能在 `TopicBrief -> MessagePlan` 之后、表现形式明确选择叙事时按需
调用。说明、比较、历史梳理、知识答疑、口播、图文和纯素材不会被强制故事化。详细矩阵、目标
合同与迁移前失败测试见 `audits/A34-fourth-version-marketing-and-screenwriting.md`。

## A35 同题异讲与讲述策划

2026-08-16 用户指出，同样讲古巴雪茄、卡斯特罗和丘吉尔，有的人能让观众津津有味，有的人
只能讲成冷笑话；差别在于从哪里出发、以什么视角展开。UC 时代的“震惊体”则说明标题和开头
可以抢注意力，但空壳包装并不能替代内容兑现。

本轮先写失败测试，再在现有扁平 `MessagePlanDraft` 中增加 `entry_point`、`telling_lens`、
`audience_question`、`information_order` 和 `payoff`，没有增加新 Agent 或必经阶段。稳定计划身份
现在绑定完整讲述策划；同一 TopicBrief 和标题只要切入口或视角不同，就形成不同
`message_plan_id`。失败基线为 `5 failed, 1 passed`，实现后交付测试 `6 passed`、全部内容智能
回归 `93 passed`，Ruff 和 `git diff --check` 通过。

两次真实 `glm-5-2-260617` 雪茄探针均使用帝国战争博物馆和美国国会图书馆的有界证据。第一
次选中了“同一个视觉符号、不同人物意义”的有效视角，但把来源年代写成场景、正文偏资料汇报，
并将雪茄馆擅自塞进收束。通用边界修正后，第二次只从丘吉尔反复出现的雪茄切入，沿“视觉道具
如何变成人物标志”比较两人，场景保持空值，店铺不再进入正文，事实限制仍被保留。

结论为 `reviewed -> adopted for local canary; quality acceptance pending`。第二次成稿仍偏研究说明，
还没有达到“津津有味”；当前只验收讲述策划可检查且能转移模型注意力。下一候选是先冻结讲述
角度，再针对该角度补充真实场景、动作和语言证据后写稿，并与直接写稿做新保留集对照。详见
`ADR-016` 与 `evidence/telling-treatment-a35-2026-08-16.md`。

## A36 内容地图回归账号级编辑定位

2026-08-16 用户重新划清“做视频”和“做 IP”的边界：内容地图属于前期账号定位，负责长期
讲什么、用什么稳定方式观察世界；每天的具体选题与实时热点只能从地图上长出。原运行链虽然
口头称地图为长期内容世界，工程行为却是每次重建地图后立即搜题并优先返回“今日建议拍摄”，
因此一次搜索结果事实上可能抢走定位权。

本轮测试先行给 `ContentWorldView` 增加 `editorial_promise`、`recurring_lens` 与
`drift_boundaries`，不增加新 Agent 或新模型调用。地图以长期字段和疆域内容寻址；后续研究新增
命名候选不会改变版本。`TopicBrief` 必须绑定该版本，且路径第一步必须从冻结内容根出发。
宽泛起号请求现在先显示账号内容定位，再显示一个地图内的当日样例题。

“泰国老百姓为什么改稻为榴”被登记为优秀地图方向、未完全取证标题。现有研究只直接支持泰国
一个具体地区的受访果园从一般大田作物改种榴莲，不能推出全国性的水稻转换。上线题名前必须
继续核具体地区和原作物；在此之前使用“为什么泰国一些农民把传统大田作物改种榴莲”更严谨。

第一次真实端到端探针又暴露一个上游问题：根裁决把“顾客选购水果”当成了比“水果”更大的长期世界。
这不是地图丰富度问题，而是把“获得对象的交易步骤”误当成了“构成品类的完整参与活动”。新失败测试先锁定
这个区分，然后只改根裁决边界，没有增加水果关键词或新 Agent。

同一 `glm-5-2-260617`、同一干净问题在修正后选择“水果”，并明确生成果农选种与种植变化、产区演化、流通价格、
食用风味和历史文化等长期疆域。因此“为什么某地果农改种某种水果”已是地图内的自然路径。

结论为 `reviewed -> adopted for local canary; persistence pending`。五个内容智能聚焦文件共 `97 passed`。账号级持久化、用户确认、
版本切换和独立热点来源合同尚未实现。详见 `ADR-017` 与
`evidence/account-editorial-map-a36-2026-08-16.md`。

## A37 孵化运营全模块编排基线

2026-08-16 对第六版当前运行时、第五版 `3ee135f7` 隔离实验与第四版
`58f4e0c9` 生命周期代码完成重新对账。用户指出预演、发布回执、分析复盘、对标体系、
MediaKit 和抖音 OpenAPI 已分别存在，新问题不是继续造模块，而是建立共享业务谱系并重新接线。

本轮确认的事实：

- 第六版已有语义、账号级内容地图、联网取证、`TopicBrief`、`MessagePlan` 和基础文案纵切，
  但项目与账号持久化尚未实现。
- 第六版抖音 OpenAPI Catalog 收录 119 条目录记录并分入 16 个领域；当前采用的 Child 只有
  `video_search` 和 `experience_search`，目录存在不等于生产可用。
- 第五版 E15 保存账号链接采集、多平台搜索、受众证据、有界 Lead 投影和 MediaKit 任务回执。
  抖音“大能”和“田永成”案例通过过隔离真实采集与分析，但 E15 从未注册为第六版 Tool/MCP。
- 第五版 MediaKit 已真实运行元信息、ASR、OCR 和场景切分；OCR 误检也证明它只能作为
  机器观察，不能作为营销事实或孵化判断。
- 第四版有发布回执 repository/API、浏览器发布恢复、平台指标代码和预演/复盘历史表。
  预演与复盘表后来随旧语义层退役；因此只采用不可变、幂等、恢复、未知对账和预测对实绩方法，
  拒绝整个 `personal_ip` 包、旧 SOUL、必填阶段和硬门。

架构冻结为“一个总脑、三条循环、两个执行底座、一套事实台账”。每个业务模块产生一个内容寻址、
可追溯的产物；Lead 按用户当前目标补齐所需产物，不强制每个请求走完全流程。只有所有权、密钥、费用、
不可逆审批、幂等并发、未知结果对账和有来源的禁止规则可以硬拦截。

用户进一步确认，编排不能将 DeerFlow 退化为一个普通聊天壳。本轮因此对现有运行时再做一次能力对位：
LangGraph checkpoint 与 run ownership 承担恢复，受控工作者与 `task` 子 Agent 分别承担紧耹合和可并行认知工作，
MCP 与 `tool_search` 承担平台能力渐进发现，Skill 承担按需方法，Memory 只保存偏好和显式纠错，Sandbox 与
uploads 隔离媒体，Scheduler 复用正常 run lifecycle 执行定时发布和复盘，长耗时任务使用数据库租约恢复，
SSE/StreamBridge 和工具输出外部化承担可观测性与上下文保护。完整利用矩阵已加入实施计划。

分阶段工作包冻结为：

```text
W01 共享产物脊柱
-> W02 读取与证据中心
-> W03 孵化与单条内容谱系
-> W04 MediaKit 制作路由
-> W05 预演、审批与抖音发布
-> W06 指标、受众与复盘学习
-> W07 产品化与多平台扩展
```

这是实施依赖顺序，不是 Lead 面向用户的必经工作流。首个代码切片确定为 W01：只建项目、账号、
产物包装、父子谱系、内容哈希和证据角色的最小合同，不在同一切片继续修改内容脑提示词。

结论为 `reviewed -> orchestration baseline adopted; implementation starts at W01`。详见
`decisions/ADR-018-artifact-graph-orchestration.md` 与 `IMPLEMENTATION_PLAN.md`。

## A38 W01 共享产物脊柱实施

2026-08-16 按 A37 编排基线先写失败测试，再实现第六版首个共享业务边界。新增
`deerflow.incubation` 领域合同、`deerflow.persistence.incubation_ledger` SQL 仓储和
`0012_incubation_ledger` 迁移。三张表分别保存用户项目、项目内平台账号和内容寻址产物；
LangGraph checkpoint、聊天摘要和 Memory 均不替代这些表。

已验证的边界包括：两个用户可拥有同名项目且无法互读；账号必须与用户和项目一致；父产物必须
存在且类型、哈希、用户、项目全部匹配；证据角色参与产物身份，`topic_evidence` 与
`benchmark_evidence` 不会混查；相同产物重放幂等；API key、Token、Cookie、StorageState、
临时地址和本地路径类字段不得进入业务 payload。由于 Pydantic 冻结模型不会深冻结内部字典，
仓储会在事务前重新校验内容哈希，封存后篡改不能留下脏记录。

现有 `ContentWorldView` 新增的是可选适配器，而不是新的必经阶段。它只封存
`content_map_version_id` 所代表的长期内容根、受众疆域、编辑承诺、稳定观察方法、漂移边界和地图维度；
一次运行的 `record_id`、商业对象、候选根、命名搜索候选和未知项不会因每次取证变化而制造账号定位
新版本。Memory 工具说明同步移除“durable project context”，明确项目版本、审批、回执、指标与学习
状态必须从所有者隔离的业务台账重建。

计划原写“用内存仓储完成快速合同测试”。实际改为每个测试使用临时 SQLite 驱动同一 SQL 仓储，
原因是独立内存仓储会形成第二套持久化语义，与“业务数据库是唯一真相源”冲突。该偏差没有改变
验收目标，并增加了真实 Alembic 启动、旧库升级、并发引导和 ORM/迁移一致性覆盖。

结果为 `adopted -> implemented; Lead/API project hydration pending`。本轮相关测试共 102 项通过，
随后新增的长期地图适配与内层 payload 防篡改测试共 40 项聚焦回归通过；Ruff、Alembic autogen
一致性和 `git diff --check` 通过。完整命令与文件回执见
`evidence/incubation-ledger-a38-2026-08-16.md`。

## A39 W02 抖音选题证据第一切片

2026-08-16 开始将现有读取能力接入 A38 共享脊柱。先选择已经具备官方 Catalog、Manifest、
Schema 和权限上下文的抖音 `search.video_search`，没有先迁账号抓取或 MediaKit。新增通用
`EvidenceSnapshot`，显式区分 provider、collection method、evidence role、capture time、rights basis、
population scope、provenance、coverage、route receipt、warnings 和 limitations。

抖音平台适配器只接受经过 DomainRouter 的 `search.video_search` 成功回执，并白名单保留公开视频
ID、标题、公开链接、文本摘录、作者显示名、发布时间与点赞观察值。它固定生成
`topic_evidence`；错误路由、伪装成 `benchmark_evidence`、结果数量不一致或新增未审阅临时字段都会
失败。单条视频和一次搜索被明确限制为选题证据，不能证明对标账号定位、受众、成绩或可复制模式。

为控制 Token，完整快照只进入业务台账；`to_lead_projection()` 在 16 KB 默认预算内按完整证据项
装箱，返回快照哈希、路由回执哈希、覆盖、代表项、纳入数和省略数。它不会把字节流截成看似完整的
半条证据。4 KB 压力测试使用 20 条长文本，投影保持预算内并显式报告截断。

结论为 `reviewed -> implemented; production project ingestion pending`。适配器聚焦测试 `5 passed`；
与账本、内容地图、抖音 Router、视频搜索、体验搜索和 Lead Memory 边界的联合回归 `64 passed`。
本轮没有重新调用真实抖音 API，因此沿用旧搜索能力的 `verified` 结论，不把新项目入库链标成
`verified`。加入迁移、并发启动、Alembic autogen 和持久化脚手架后的最终相关套件为
`156 passed`。详见 `evidence/douyin-topic-evidence-a39-2026-08-16.md`。

## A40 W02 对标账号快照合同

2026-08-16 对第五版 `3ee135f7` 中 E15 的账号快照、链接采集、作者一致性和
Lead 投影完成逐文件审计。本轮确认可迁移的是工程合同，而不是第五版的采集运行时、
Playwright 选择器、本地 JSON 缓存或“大能”案例结论。详细来源、失败史和拒绝项已记入
`audits/A40-fifth-version-e15-benchmark-snapshot.md`。

第六版新增平台无关 `BenchmarkSnapshot`：主页与每条作品必须绑定同一稳定外部账号 ID；
作品 ID 必须唯一；单次请求最多 `24` 条；请求、返回、排除、`has_more`、采样依据和限制
分开保留。混入另一作者、虚假覆盖数、重复作品、负数/非有限公开指标和晚于快照的观察均
确定性拒绝。

快照封存为项目级 `benchmark_evidence`，不绑定用户自有的 `PlatformAccountRef`。完整快照留在
业务台账；Lead 投影默认上限 `16 KB`，超限时只能整条省略并显示数量，不将文案截成伪完整证据。
投影固定声明主页文本、文案和公开指标只是有界观察，不是账号定位、受众画像、成功原因或可复制公式。

本轮失败基线先在导入阶段失败，实现后 `BenchmarkSnapshot` 聚焦测试 `10 passed`，与产物台账、
抖音选题证据和 pnpm 工程回归的联合套件 `35 passed`。当前状态为
`reviewed -> implemented; production Douyin connector and live ledger ingestion pending`。

最终使用 `DEER_FLOW_AUTH_DISABLED=false make test` 运行完整后端离线套件，结果为
`11709 passed, 76 skipped`。首次按本地 `.env` 直接运行出现的认证、CSRF、渠道归属与扩展失败，
均由开发机设置 `DEER_FLOW_AUTH_DISABLED=true` 改变测试默认语义导致；显式恢复鉴权后只剩既有
`content_intelligence_delivery` 内部标签未进入用户输入防伪造名单。该缺口已加入 denylist，
对应输入清洗套件 `157 passed`，受影响的七组联合回归 `636 passed`。

## 工程环境：pnpm 版本锁定修复

2026-08-16 发现宿主全局 pnpm `11.19.0` 的 `pmOnFail=ignore` 绕过了
`frontend/package.json` 中的 `pnpm@10.26.2`。pnpm 11 因而将旧 `ignoredBuiltDependencies` 自动改成
三个 `set this to true or false` 占位值。失败测试固定后，共享运行器强制
`PNPM_CONFIG_PM_ON_FAIL=download`，真实调用恢复为 `10.26.2`；三项构建权限迁移为明确布尔 `false`。
`backend/tests/test_pnpm_script.py` 为 `9 passed`，不再允许占位字符串进入工作区。

## A41 W02 抖音官方优先证据路由

2026-08-16 复核当前抖音开放平台文档时发现，第六版仍在调用旧
`/dy_open_api/v1/search/video/` 和旧 Scope `aweme.dy.video_search`。先写失败测试后，运行时
合同、Domain Manifest 和薄适配器统一迁移至官方 v2 endpoint 与
`aweme.dy.video_search_v2`。

同一搜索能力新增两个本地目的：`topic_research` 保持 `topic_evidence`；
`benchmark_discovery` 生成 `benchmark_account_candidate`。该目的不会发送给抖音。候选快照明确
声明搜索作者名不是稳定账号身份，也不能证明定位、受众、成绩或可复制模式；只有后续官方账号路径
取得稳定账号 ID、作者一致多作品和覆盖回执，才可封存 A40 的 `BenchmarkSnapshot`。

本轮也正式冻结官方优先原则：第五版 E15 的身份一致和覆盖合同保留，Playwright 采集器不作为默认
路径迁移；自有/已授权账号走官方 API，第三方对标优先走官方搜索及星图/精选联盟等官方页面连接器。
聚焦测试从 `11 failed, 15 passed` 修复至 `26 passed`。真实查询在网络请求前返回
`DOUYIN_CLIENT_KEY and DOUYIN_CLIENT_SECRET are not configured`，说明第六版本地配置尚未迁入；
没有输出密钥，也不把本轮标记为 live verified。完整审计与回执见
`audits/A41-douyin-official-first-evidence-routing.md` 和
`evidence/douyin-video-search-v2-a41-2026-08-16.md`。

最终以 `DEER_FLOW_AUTH_DISABLED=false make test` 运行完整后端离线套件，结果为
`11713 passed, 76 skipped, 17 warnings in 466.09s`；Ruff、格式检查、AGENTS 文档约束和
`git diff --check` 均通过。

## A42 W02 抖音对标候选跨页聚合

2026-08-17 用户明确纠正路由：既然抖音开放平台已有公开视频搜索，先用官方 API
完成第三方对标内容样本，星图与百应往后排。本轮复核官方参数后进一步确认，
`open_id` 是授权用户唯一标识，不是目标竞品账号 ID；因此它只能作为查看者上下文，
不能用来伪造稳定竞品身份。

先写失败测试后，新增薄的 `BenchmarkCandidateRequest` 和官方搜索聚合层。它复用现有
DomainRouter、Manifest、v2 Schema 与 Token 路由，按 Unicode 归一后的作者显示名跨页精确筛选，
公开作品 ID 去重，并分别记录请求页、成功页、排除、重复、剩余页和停止原因。
后续页失败时保留已观察项并显式警告；首页失败不伪造空样本。

最多 24 条的完整候选快照可幂等写入现有项目台账，证据角色仍是
`benchmark_account_candidate`；Lead 仅接收固定字节预算投影。这已满足“官方 API
先看别人的公开内容样本”，但不宣称完整账号数据、粉丝画像或成功归因。只在出现稳定身份、
受众或商业字段缺口时，再启用星图或百应。

失败基线为新模块 `ModuleNotFoundError`；实现后聚焦套件 `34 passed`。本地仍缺抖音
Client Key/Secret，本轮没有生成真实平台回执，因此状态为
`reviewed -> implemented; live credential verification pending`。详见
`audits/A42-douyin-public-benchmark-candidate-aggregation.md` 与
`evidence/douyin-benchmark-candidate-a42-2026-08-17.md`。

最终以 `DEER_FLOW_AUTH_DISABLED=false make test` 复跑完整后端离线套件，结果为
`11721 passed, 76 skipped, 17 warnings in 424.47s`；Ruff、格式检查和
`git diff --check` 均通过。

## A43 W02 抖音对标候选接入 Lead

2026-08-17 在 A42 已完成官方搜索聚合后，继续以测试先行接入真实 DeerFlow
工具清单。失败基线为新工具模块 `ModuleNotFoundError`。实现后，Lead 只能看到
`query`、`actor_label` 和 `max_posts`；用户、会话、运行和项目身份都不在
模型 Schema 中。

未选项目时，工具直接返回 16 KB 以内的只读候选证据，不把项目或问卷变成硬门。
选中项目时，Gateway 只转发 `incubation_project_id`，不接受客户端 owner；工具用
服务端认证用户在平台请求前校验所有权，再用 `thread_id + run_id` 封存。
如果证据已收到但台账写入失败，Lead 仍收到证据和脱敏的 `persistence=failed`，
底层数据库内容不返回。

工具/Gateway 套件 `7 passed`，抖音路由、证据、台账与 Gateway 关联回归
`178 passed`，通用工具 Schema/运行时序列化回归 `38 passed`。本机仍缺抖音
Client Key/Secret，且前端尚无项目选择器，因此状态为
`reviewed -> implemented; live credential and product project selection acceptance pending`。
详见 `audits/A43-douyin-benchmark-lead-tool.md` 和
`evidence/douyin-benchmark-lead-tool-a43-2026-08-17.md`。

最终以 `DEER_FLOW_AUTH_DISABLED=false make test` 复跑完整后端离线套件，结果为
`11730 passed, 76 skipped, 17 warnings in 465.97s`。

## A44 W02 证据隔离与 MediaKit 来源边界

2026-08-17 在继续对标账号感知链之前，先复核内容地图查资料和对标采集是否会混料。
失败测试证明两个合同漏洞：`SourceItem` 仍允许 `benchmark_account_candidate`；
内容地图的抖音搜索适配会丢掉上游角色，并把错路由的对标回执重标成
`topic_evidence`。追加失败测试又证明普通网页搜索的显式对标角色也可流入；
现在领域类型与所有搜索适配均会按证据角色拒绝，不再按平台猜测。

同一切片完成 MediaKit 输入基础。本机 `mediakit-cli 0.2.0` 实际 Schema 确认
ASR、OCR、场景切分和元信息可直接接 `video_url`，但这必须是视频资源而不是
抖音分享 HTML 页。新合同只让解析器确认为 `video/*` 的短命直链或已存在的本地文件
进入预备调用；原始定位符不进 Lead 或台账，持久回执仅留哈希和权利谱系。

内容、抖音、台账与 MediaKit 联合聚焦回归 `174 passed`；本机真实 CLI Schema
预备调用返回版本 `0.2.0` 和稳定 Schema 哈希。本轮没有解析真实抖音媒体，
没有发起付费云任务，也没有实现轮询恢复和感知证据的父角色继承，因此状态为
`reviewed -> implemented; real resolver and execution pending`。详见
`audits/A44-evidence-isolation-and-mediakit-source-boundary.md` 与
`evidence/evidence-isolation-mediakit-a44-2026-08-17.md`。

追加普通网页搜索角色边界后，聚焦回归为 `60 passed in 4.27s`。
最终以 `DEER_FLOW_AUTH_DISABLED=false make test` 执行完整后端离线套件，结果为
`11742 passed, 76 skipped, 17 warnings in 463.85s`。
首次全量运行的 13 个网页读取失败未能在失败四组或完整套件复现；
详细回执保留了该非确定性现象，不把它冒充成稳定绿灯或本次功能回归。

## A45 抖音 MCP 运行配置恢复与状态纠偏

2026-08-17 按 A25-A27、A41-A43 和对应 Git 提交重新核账。既有实现已经包含
`douyin-openapi-mcp`、16 个领域 Manifest、官方 v2 视频搜索、对标候选跨页聚合和
Lead 高层工具；不得把运行配置缺失误判为功能未实现，也不得退回网页读取或重写采集器。

本机第六版缺少被 Git 忽略的 `extensions_config.json`，导致运行中的 Gateway 记录
`MCP tools: 0`。恢复现有 MCP 的本地启用配置并重载 Gateway 后，控制面显示
`douyin_openapi` 已注册且启用，真实 stdio 初始化列出 16 个领域工具，Agent 构建日志显示
`MCP tools: 16`。搜索领域只披露已声明获批的 `video_search` Child；由于本地进程仍未绑定
应用身份，其状态诚实保持 `callable=false / auth_not_configured`，本轮没有向抖音发请求。

这次只修复现有运行接线，没有修改业务代码、另建连接器或改变 A41-A43 的验收边界。
下一步是在 MCP 私有环境中绑定现有抖音应用身份后，执行一次官方 v2 视频搜索真实回执；
未取得回执前仍不得标记 `live verified`。详见
`audits/A45-douyin-mcp-runtime-recovery.md` 与
`evidence/douyin-mcp-runtime-recovery-a45-2026-08-17.md`。

## A46 W01 项目绑定与运行时重水化

2026-08-17 沿 A38 和 ADR-018 的未完成项继续测试先行接线。失败基线首先证明项目 API
不存在；进一步测试冻结了两个安全与连续性问题：普通线程 metadata 和 run context 均不能
写入 `incubation_project_id`，而已绑定线程每次 `start_run` 必须从服务端台账重水化同一项目。

实现新增 owner-scoped 项目创建、列表和读取，以及线程绑定、读取和解绑 API。绑定同时校验
线程与项目属于认证用户；响应不暴露 owner 身份。`incubation_project_id` 成为服务端保留元数据，
运行时会先清除请求中伪造的值，再验证线程绑定项目仍存在，最后同时注入
`ToolRuntime.context` 和兼容 `configurable`。失效绑定在 Agent 启动前返回 `409`。

聚焦回归为 `223 passed`；补充连续性边界后，分支线程继承项目绑定，失效绑定会在 Agent 执行前
返回 `409`。完整离线后端套件为 `11750 passed, 76 skipped`。运行中的本机 Gateway 经 `8001`
和 nginx `2026` 均返回新接口；
真实 SQLite 回执完成项目创建 `201`、线程创建 `200`、绑定 `200` 和重新读取 `200`。本轮没有
调用模型或抖音，也没有把前端选择器伪装成已完成。W01 服务端运行接线完成，前端交互归入 W07；
下一断点回到 W02 的内容/证据产物封存。详见
`audits/A46-incubation-project-runtime.md` 与
`evidence/incubation-project-runtime-a46-2026-08-17.md`。

## A47 内容纵切写入项目谱系

2026-08-17 继续完成 A46 留下的内容产物封存。新增确定性适配器，将同一次内容运行中的
`ComprehensionRecord`、长期 `ContentWorldView`、可选 `TopicBrief`、`MessagePlan` 和
`BaseDraft` 封存为项目级内容寻址产物。选题同时引用阅读记录与冻结地图，讲述策划引用选题，
基础成稿引用讲述策划；运行中的命名候选和搜索结果不会改变长期地图身份。

第一次真实黄金礼品运行虽然已经从黄金材质迁移到礼与关系秩序，但隐藏回执为
`persistence=not_selected`，数据库没有产物。项目绑定实际存在，根因是内容工具读取
`RunnableConfig.context`，而不是 DeerFlow 工具节点注入的 `ToolRuntime.context`。
失败测试固定后，工具改为与抖音证据工具相同的标准 `@tool + ToolRuntime` 接线，模型 Schema
仍只有用户原话，项目、用户、线程和运行身份均由服务端注入。

全新线程用同一句“我是做黄金礼品的，我要怎么起号？”复跑，长期内容根为：

```text
以礼待人：人们如何用礼节、礼物和礼制来维系彼此的关系与社会秩序
```

并收敛出“村里人随份子，为什么不是在‘送钱’而是在‘织网’”的具体选题。隐藏工具回执与
SQLite 同时确认五类产物各一条，父级和哈希匹配。聚焦测试 `25 passed`，内容、台账与 Gateway
关联回归 `175 passed`。完整离线后端套件最终为
`11757 passed, 76 skipped, 17 warnings in 436.86s`。

本轮不能记为全通过：运行耗时约 6 分 44 秒、13 次模型调用、70,323 Token；资料以二手来源为主，
成稿个别具体化说法仍需更强证据。结论为
`implemented; E2E-01 semantic migration and lineage passed; fact-boundary and performance follow-up required`。
详见 `audits/A47-content-run-artifact-lineage.md` 与
`evidence/content-run-artifact-lineage-a47-2026-08-17.md`。

## A48 抖音 MCP 选题证据接入内容谱系

2026-08-17 复核发现，内容纵切中的抖音资料源仍依赖 `config.yaml` 的旧
`douyin_video_search` 直连工具，而当前配置没有启用它；已经恢复的 16 域
`douyin-openapi-mcp` 因而没有进入内容研究。新增薄适配器后，内容研究从当前
`ToolRuntime.tools` 选择带 MCP 标记的 `douyin_search`，按
`空对象发现 Manifest -> 精确 video_search` 调用，业务用途固定为 `topic_research`。
旧直连配置即使存在也不会被调用。

官方结果继续与 Web 资料并列参与证据阅读。确定性代码只保留角色为 `topic_evidence` 的回执，
并在最终阅读确实保留其中公开 URL 时先封存 `evidence_snapshot`，再把它作为
`content_reading` 父级。对标候选、未采用结果和凭据字段都不能进入内容产物谱系；长期
`content_world` 仍不引用单次搜索证据。

聚焦回归为 `51 passed in 4.26s`，后端全量为
`11764 passed, 76 skipped, 17 warnings in 413.53s`。第一次未隔离本地免登录 `.env` 的全量
运行使 36 条认证、CSRF 与归属测试按 `default` 用户执行；命令级设置
`DEER_FLOW_AUTH_DISABLED=0` 后，相关 5 文件 `467 passed`，随后全量通过。这是测试环境回执，
没有修改用户本地登录配置。真实本机探针确认 16 个 MCP 工具与
`douyin_search` 均存在；解析后的本地 `CLIENT_KEY`、`CLIENT_SECRET`、`DEVICE_ID` 仍为空，
所以 `video_search` 正确为 `callable=false / auth_not_configured`，没有发出搜索请求。本条状态为
`implemented offline; live credential acceptance blocked`，不能记成抖音真实验收。详见
`audits/A48-douyin-mcp-topic-evidence-lineage.md` 与
`evidence/douyin-mcp-topic-evidence-a48-2026-08-17.md`。

## A49 W04 MediaKit 本地执行与云恢复边界

2026-08-17 沿 A44 继续接 MediaKit，先对照第五版 E15、本机 CLI 与 DeerFlow
`McpTaskService`。真实烟测发现 `mediakit-cli 0.2.0` 的元信息 Output Schema 描述云端
`task_id/request_id`，而本地模式实际返回容器、视频流和音频流元信息；只做 JSON Schema 校验会让
空对象也通过。第五版的云任务又把提交和 `--poll-complete` 绑在一个进程内，不能提供重启恢复。

本轮测试先行实现本地文件执行：命令前后双哈希固定输入内容，CLI 输出受 1 MB 预算约束，动态
Schema 之后再进入窄视频元信息合同。持久回执记录 CLI 版本、Schema、请求、源内容和输出哈希，
不记录命令、原始输出或路径；`media_observation` 自动继承 `media_source_receipt` 的证据角色。
本机生成的 1 秒、320×240 测试视频已通过真实 `--local probe-video-metadata` 执行，没有调用云端。

审计确认 DeerFlow 的租约轮询可复用，但现有提交顺序依赖远端取消来补偿落库失败，MediaKit CLI
没有已审计取消能力。云端 ASR/OCR/场景切分因此保持关闭，下一步先实现持久幂等提交意图，再绑定
原始任务句柄和后台轮询，不能回到 Agent 内长轮询。聚焦测试为 `11 passed`；完整回归最终为
`11771 passed, 76 skipped, 17 warnings in 420.58s`。详见
`audits/A49-mediakit-local-execution-and-cloud-recovery.md` 与
`evidence/mediakit-local-execution-a49-2026-08-17.md`。

## A50 W04 持久任务提交意图

2026-08-17 继续解决 A49 发现的“远端先提交、数据库后落库”恢复缺口。测试先要求一个可领取但不可
轮询的 `submission_pending` 状态，并固定三条性质：入队不能调用远端、后台提交后原子绑定句柄、
绑定失败后必须使用同一本地任务 ID 重试且不得取消远端。失败基线因
`CLAIMABLE_TASK_STATUSES` 尚不存在而在测试收集期失败。

实现新增 `enqueue()`、持久提交参数、提交意图租约领取和 `bind_submission()`。只有后台工作进程
持有有效租约时才能绑定远端句柄；绑定成功后提交参数清除。驱动异常会释放租约并延时重试，远端成功
但绑定落库异常则保留租约到期恢复窗口。原有同步 `submit()` 保持兼容，不把新路径强加给已有驱动。
迁移 `0013_mcp_task_submission_intent` 将 `remote_task_id` 改为可空并加入提交参数；真实旧
`0012` SQLite 表升级回归确认已有记录保持不变。

提交参数只允许稳定来源引用、能力名、Schema/授权引用和非敏感选项，禁止凭据、Cookie、临时 URL
和本机路径。MediaKit 云驱动尚未注册，本轮没有上传、供应商请求或费用。聚焦状态机测试为
`29 passed`，任务运行时与迁移启动回归为 `65 passed`；完整后端为
`11778 passed, 76 skipped, 17 warnings in 426.42s`。详见
`audits/A50-durable-task-submission-intent.md` 与
`evidence/durable-task-submission-intent-a50-2026-08-17.md`。

## A51 W04 MediaKit 云驱动无费用模拟验收

2026-08-17 在 A50 的持久提交意图之上新增隔离 `MediaKitCloudDriver`。失败测试先要求尚不存在的
云合同；首轮实现后安全复核又暴露授权异常原文、稳定引用夹带签名 URL、物化异常泄露临时输出地址和
外部 URL 冒充持久产物四个缺口。修复后，提交参数只接受稳定引用、能力名、Schema 哈希、授权引用
和非敏感选项，三个受信回调边界都只向任务运行时返回固定错误信封。

本机 `mediakit-cli 0.2.0` 的 `query-task --schema` 把状态描述为
`processing/success/failed`，同版本只读归档源码则使用
`queued/running/completed/failed/canceled/cancelled`。驱动兼容两组输入并归一为 DeerFlow 状态；
每次租约只查询一次，禁止 `--poll-complete`。本地任务 ID 固定作为 `client_token`，短命输入和输出
URL 只存在执行内存；完成任务必须物化为内部 `artifact://` 引用、内容哈希、MIME 和大小。

定向云驱动测试为 `14 passed`，MediaKit、持久任务和孵化谱系联合回归为
`78 passed, 1 warning`。第一次全量只因 `backend/AGENTS.md` 超指导文件软预算而失败；压缩规则并
单测后，最终完整离线后端为 `11792 passed, 76 skipped, 17 warnings in 417.45s`。本轮未注册驱动、
未调用云服务、未上传用户素材、未产生费用，也不代表 ASR/OCR/场景切分已经真实可用。详见
`audits/A51-mediakit-cloud-driver-mocked-acceptance.md` 与
`evidence/mediakit-cloud-driver-a51-2026-08-17.md`。

## A52 W04 MediaKit 精确批准账本

2026-08-17 继续审计 A51 的三个受信依赖时，先发现授权上下文缺少项目、本地任务、素材内容哈希、
完整操作摘要和费用上限，无法实现真正的一次性批准。对照第四版付费调用台账后，只迁移“服务端冻结
批准”和“执行任务原子消费”两条可靠性原则，没有迁移旧供应商、SKU 和制作状态机。

新增 `ApprovalGrant` 与迁移 `0014_incubation_approval_grants`。云处理同意和费用上限分别记录，
共同绑定 owner、项目、来源/权利引用、素材摘要、能力、参数、Schema、币种和金额上限形成的精确操作
摘要。首次执行用同一 SQL 事务将两条批准绑定到唯一 MCP 本地任务；并发输家、过期、撤销、跨项目、
换素材、换参数或换费用全部失败且不半绑定。同一任务在不确定提交后可幂等恢复，已绑定批准不能撤销。

驱动顺序同步修正为本地版本/Schema 校验后再消费批准，避免 CLI 漂移白白占用授权。聚焦测试为
`26 passed`，相关模块联合回归为 `125 passed, 1 warning`。首次全量唯一失败是仓库说明超软预算；
压缩摘要后，最终完整离线后端为 `11804 passed, 76 skipped, 17 warnings in 425.82s`。本轮仍未提供
批准 API、真实来源哈希复核或供应商费用封顶，也未注册驱动、上传素材、调用云服务或产生费用。详见
`audits/A52-mediakit-exact-approval-ledger.md` 与
`evidence/mediakit-exact-approval-a52-2026-08-17.md`。

## A53 W04 MediaKit 可信输入与结果物化

2026-08-17 继续补齐 A52 不能证明“云端实际读了哪些字节”的缺口。对照 MediaKit CLI `0.2.0`
和源码后确认：云能力可直接接收本地文件并由 CLI 上传，但其缓存身份只含路径、大小和修改时间，
不能替代内容哈希。第五版向 `query-task` 传 `--output-path` 的封装也不被当前 Schema 或实现消费，未形成可复用的
下载器。

失败测试先要求尚不存在的输出策略合同；安全复核又暴露两个真实问题：供应商返回任务号后再抛校验错会
丢失可对账句柄；只检查 `video/` 前缀会允许异常 MIME 进入回执。修正后，素材先进 owner/project 隔离的私有
内容寻址库，在批准前和提交后校验真实 SHA-256；后校验失败以固定错误和远端句柄入库。下载器对 HTTPS、
主机白名单、重定向、SSRF、大小和哈希逐层校验；只有能力登记的结果才可经专属质检原子封存为
`artifact://`，并发竞争只保留首份回执。

聚焦测试为 `36 passed`，MediaKit、长任务、批准与迁移联合回归为 `102 passed`，异步阻塞回归为
`71 passed, 2 warnings`；完整离线后端为 `11824 passed, 76 skipped, 17 warnings in 422.15s`。真实本机视频已通过
私有暂存、字节复核和 MediaKit 本地探测。本轮仍未注册云驱动、
上传素材、调用云能力或产生费用；费用供应商侧硬上限和逐能力真实回执仍未验收。详见
`audits/A53-mediakit-trusted-io.md` 与
`evidence/mediakit-trusted-io-a53-2026-08-17.md`。

## A54 W04 MediaKit 首个云能力选择

2026-08-17 对本机 `mediakit-cli 0.2.0`、官方仓库 HEAD、当前动态 Schema 和火山引擎四份实时文档
做交叉核对。`video/enhance-video` 的能力 Schema 明确声明终态 `video_url`、`duration` 与
`resolution`，可以接入 A53 的视频下载、哈希和本地质检；ASR、OCR、场景切分却仍只把终态声明为
`local_path`，而通用 `query-task` Schema 没有公开它们的结构化结果，因此不能把第五版的历史烟测
当作第六版输出合同。

本轮选择画质增强作为首个真实云候选，但保持关闭。首轮范围冻结为合成视频、标准版、720P 及以下、
30fps 及以下。官方 2026-08-06 计费正文显示该档按输出毫秒级时长计费，单价为 `0.75 CNY/分钟`；
一秒输出的公式估值是 `0.0125 CNY`。提交 API 与 CLI 均无供应商侧单任务金额上限，本地批准金额不能
冒充供应商硬封顶。官方查询接口还将在 2026-08-20 起只支持查询 30 天内任务，临时结果默认保留
24 小时。

因此 A54 状态是 `reviewed`：下一步先以失败测试实现能力专属 Schema 检查、带时效的价格证据和
确定性费用报价；真实任务仍需用户对当次素材、规格和金额重新明确同意。本轮没有注册驱动、上传素材、
调用云能力或产生费用。详见 `audits/A54-mediakit-first-cloud-capability.md` 与
`evidence/mediakit-first-cloud-capability-a54-2026-08-17.md`。

## A55 W04 MediaKit 画质增强费用预检与任务绑定

2026-08-17 按 A54 先写失败测试，再实现 `video/enhance-video` 专属离线预检。当前动态 Schema 必须
与审阅摘要一致，首轮只允许标准版、720P 及以下、15-30fps 和显式输出规格；缺规格、专业版、Schema
漂移、价格证据过期或用户金额不足均失败。官方价格正文被封装为带来源、正文哈希、检查时间和有效期的
证据，一秒合成视频按 `0.75 CNY/分钟` 得到 `0.0125 CNY` 确定性估值。

报价不再停留在调用内存：价格证据摘要、报价摘要、估值和有效期进入
`mediakit-cloud-operation-v2`，继而绑定云处理/费用批准、持久任务恢复数据和私有结果回执。报价在
到期瞬间失效，驱动会在素材解析和批准消费前停止；重启后若价格或报价字段被篡改，也会在供应商查询前
失败。本机只读探针确认 CLI `0.2.0` 的能力摘要仍为
`5573324d5727b5398b13ca89182a1e45c7953c9a8389bb12eec0b331eca46f00`，没有使用 `--cloud`。

聚焦回归为 `54 passed`，MediaKit、持久任务、批准、孵化谱系与迁移联合回归为 `132 passed`，
阻塞 I/O 回归为 `71 passed, 2 warnings`。完整离线后端回归为
`11842 passed, 76 skipped, 17 warnings in 427.66s`。
供应商没有单任务费用硬封顶，故状态仍为 `reviewed`：驱动未注册，没有批准 API，没有上传素材、
调用云能力或产生费用。详见 `audits/A55-mediakit-enhance-video-preflight.md` 与
`evidence/mediakit-enhance-video-preflight-a55-2026-08-17.md`。

## A56 W04 MediaKit 精确批准审阅与签发入口

2026-08-17 按 A55 后继缺口先写失败测试。最初仓储没有原子签发对，领域层没有可封存批准请求，
Gateway 的审阅与确认路径均为 404；补并发重放后还发现仅因 `issued_at` 相差一秒就会把同一报价误判
为冲突。实现据此只认服务器报价：`MediaKitCloudApprovalRequest` 重新核对项目、素材哈希、能力参数、
Schema、价格和报价字段，再封存为以 `user_material` 媒体观察为父级的内容寻址产物。对标素材不能进入
云处理批准，定位符、权利引用和本机路径不进入批准载荷或 API 响应。

`GET /api/incubation/projects/{project_id}/approvals/mediakit-cloud/{quote_artifact_id}` 只展示可审阅规格、
估值、金额上限、有效期和无供应商硬封顶警告。`POST .../mediakit-cloud` 必须回传原报价摘要、币种、
金额以及云处理、费用和无硬封顶三项明确确认。两张凭证使用报价内容推导的稳定 ID，在同一事务内
签发；双击和并发重试保留首个签发时间并返回同一对凭证。报价变化、过期、越权或半对冲突均失败。

聚焦回归为 `73 passed, 1 warning`，所有权、谱系、迁移、Gateway 与 MediaKit 联合回归为
`141 passed, 1 warning`，阻塞 I/O 回归为 `71 passed, 2 warnings`。完整离线后端回归为
`11849 passed, 76 skipped, 17 warnings in 428.20s`。本轮没有创建 `mcp_task`、注册 MediaKit 云驱动、
上传素材、调用供应商或产生费用。详见
`audits/A56-mediakit-exact-approval-api.md` 与
`evidence/mediakit-exact-approval-api-a56-2026-08-17.md`。

## A57 W04 MediaKit 服务器报价生产入口

2026-08-17 沿 A56 的真实缺口先写失败测试：报价路由为 404、关闭服务没有明确 503，且同一精确操作
只因生成了两个报价产物就能取得第二对批准。实现新增默认关闭的 `mediakit` 配置与 Gateway 报价服务。
它只从当前 owner/project 下已有的 `user_material` 元信息观察及其精确来源父级起步；客户端只能提交
已审阅输出规格和金额上限，不能提交费率、价格证据、来源定位符或操作摘要。

服务器每次读取最大 64 KiB、禁止未知字段、带来源正文哈希和有效期的运营方价格证据，并通过
`MediaKitCapabilityRouter` 重新发现本机 `video/enhance-video` Schema。缺失、损坏、过期、Schema
漂移、非用户素材或谱系不匹配均失败。封存载荷与审阅响应不含素材定位符、权利引用、本机路径和临时
URL。批准凭证身份改为精确操作摘要，使同一操作的重复报价、双击与网络重试收敛到同一对凭证。

聚焦报价回归为 `20 passed, 1 warning`，MediaKit、孵化谱系与配置联合回归为
`174 passed, 1 warning`，阻塞 I/O 回归为 `71 passed, 2 warnings`。完整离线后端回归为
`11864 passed, 76 skipped, 17 warnings in 426.03s`。本轮没有创建 `mcp_task`、注册 MediaKit 云驱动、
上传素材、调用供应商或产生费用；前端素材选择与真实云验收仍未开始。完整验证结果见
`evidence/mediakit-server-quote-preparation-a57-2026-08-17.md`。

## A58 有界并行语义工作者可用检查点

2026-08-17 将原六次串行的语义、词义、共同世界、复核、选根和地图链，收敛为两个首轮只读
结构化工作者并行、确定性合流、单一内容根裁决和一次冻结根地图。两个工作者只共享用户原表达，
互相看不到答案，也不是可使用工具或写状态的 DeerFlow `task` 子 Agent。词法主词相同或连续嵌套
时按可检查规则合流；无包含关系、无效意义路径和丢失构成语境的候选在地图前被拒绝。

并发屏障测试证明首轮真实重叠；清理旧串行提示词、七个死辅助函数和只覆盖死代码的测试后，七个
相关聚焦套件为 `120 passed in 5.03s`，Ruff 与 `git diff --check` 通过。真实“拳击手套”回归从
旧错误“搏击实战与对练”修正为精确内容根“拳击”，总耗时约 `101.44s`。一次黄金礼品回归只到
“礼赠”，没有到达人情世故，仍严格记失败。

用户决定将当前内核冻结为可用检查点，不再为追求最佳语义方案阻塞下游。此状态不代表全部语义
金标通过；下一主线转为从冻结地图和证据产出具体、可直接拍摄的 `TopicBrief`。详见
`audits/A58-bounded-parallel-semantic-workers.md`、
`decisions/ADR-019-bounded-parallel-semantic-workers.md` 与
`evidence/parallel-semantic-workers-a58-2026-08-17.md`。

## A59 冻结根地图延迟与重复召回

同一“拳击手套”回归显示地图调用约占 `61.84s`，输入只有冻结根，延迟主要来自一次生成长期承诺、
观察视角、漂移边界、不限方向、专名候选和未知项。地图专名召回又与下游研究模块重复，且当前没有
阶段级 Token、响应大小、Schema 修复和供应商重试回执，不能把 61 秒全部归因于模型生成。

审计决定不把地图按时间、人物和地域拆成多个子 Agent。后续采用“单次紧凑地图、确定性装配、
可检查性能回执”，先测量再决定 Token 预算；纯定位请求停在地图，需要今日选题时才进入研究，
有视频或对标账号时才调用抖音 OpenAPI 与 MediaKit。A59 目前为 `reviewed`，尚未实现性能改造，
不阻塞具体选题主线。详见 `audits/A59-frozen-map-latency-and-duplicate-recall.md`。

## A60 项目事实与孵化判断谱系

2026-08-17 沿 A37 的发布前链路补齐第一个缺失业务对象。新增 `IncubationBrief`，只接收用户明说或
授权观察得到的事实，分别保存业务、能力、资源、限制、目标、偏好和未知；信息不完整不会成为问卷
硬门。新增 `IncubationJudgment`，将定位、受众假设、人设、账号级表现形式和变现假设分开保存，
每项保留理由、置信度、未知和依据。

判断必须绑定同项目的 `incubation_brief + content_world`，并校验精确地图版本；对标和受众证据只能
作为额外父产物进入。账号级表现形式不代替单条 `FormatDecision`，变现也不回写内容地图或
TopicBrief。聚焦合同测试 `6 passed`，与项目台账、内容地图和内容纵切联合回归 `24 passed`。
本轮只完成合同和封存谱系，自动构造 Brief、真实模型判断、用户审阅和 TopicBrief 引用仍待接线，
不能宣称完整孵化脑完成。详见 `audits/A60-incubation-brief-and-judgment-lineage.md`。

## A61 可拍选题目标与精确地图路径

2026-08-17 修复“长期定位”和“今天具体拍什么”共用一个模糊出口的问题。普通起号请求现在默认
继续形成一条具体可拍选题，明确只问长期定位时才停在冻结地图；可拍选题置于回答首位，定位作为
依据。用户点名的热点、人物、作品、事件或问题只能以当前原话中的连续逐字片段进入研究，并明确标记为
未验证线索，不得自行成为证据。

研究候选现在必须绑定冻结地图中真实存在的 `dimension + map_path_id`，`TopicBrief` 保留从内容根
开始的全部中间路径，再接入公开证据支持的具体对象。用户题眼无证据、走错路线或无法回到冻结地图时
明确保留未知，不能静默换成另一个普通选题；研究或交付失败也只报告“定位完成但未形成可拍选题”，
不再用宽泛地图冒充成品。

聚焦回归为 `90 passed`，Ruff 与 `git diff --check` 通过。当前状态为 `implemented`：尚未完成真实
模型案例验收，也没有接入表现形式、素材方案或 MediaKit 制作。发布前主链范围仍以实施计划为准，
只从 `PreflightPrediction` 起延期。详见
`audits/A61-shootable-topic-goal-and-exact-map-path.md`。

## A62 单条内容表现形式决定谱系

2026-08-17 沿发布前主链新增薄 `FormatDecision`。A64 后续已把父级修正为精确
`MessagePlan -> BaseDraft`，再选择本条内容采用
口头表达、微短剧、情景剧、图文、纯素材、访谈、纪录观察或自定义形式，并记录资源匹配、缺口、持续
生产风险、替代形式和未知。账号级长期表现能力仍归 `IncubationJudgment`，历史故事和真实案例仍是
内容来源，不是表现形式。

草案没有标题、主体、具体事情、观点和证据字段；封存时从精确父产物重新计算受保护内容与证据边界
哈希，只保存身份和摘要哈希，不复制上游正文。资源依据必须作为同项目父产物进入，叙事方法提示只能
出现在微短剧或情景剧，合同中没有平台、销售、发布、固定时长、镜头数、条数或频率。

联合回归 `39 passed`，Ruff 与格式检查通过。当前状态为 `implemented`：模型生成、用户确认、
素材方案和 MediaKit 接线未完成。详见 `audits/A62-format-decision-lineage.md`。

## A63 孵化判断有界运行时

2026-08-17 为 A60 的孵化判断合同增加薄生成服务。它读取已封存 Brief、冻结地图和可选对标/受众
证据，通过注入式结构化模型生成判断，再交给确定性代码校验地图版本、依据父级和项目所有权。模型只
负责定位、受众假设、人设、账号级长期表现方式、变现假设、未知与备选，不要求固定模板、数字配额、
实验或发布操作，也不能改写内容根。

初版审查发现完整对标和受众快照会直接进入模型。补失败测试后改为复用现有
`to_lead_projection`，完整原始快照只留台账；冻结地图也只给孵化所需高层字段。整个模型输入限制为
16,000 UTF-8 字节，产物类型、证据角色或预算不符时在调用前失败，模型/合同失败不封存半份结果。

联合回归 `14 passed`，Ruff、格式及差异检查通过。当前状态仍是 `implemented`：Brief 构造、真实
模型、项目证据读取、持久化和起号回答接线待完成。详见
`audits/A63-incubation-judgment-runtime.md`。

## A64 表现形式运行时与基础稿绑定

2026-08-17 复核完整发布前链时发现 A62 只绑定 MessagePlan，与 ADR-018 的
`MessagePlan -> BaseDraft -> FormatDecision` 顺序冲突。失败测试先证明不相关基础稿仍会进入模型；修正后
决定同时锁定精确消息计划与其直接派生的 `draft_version(stage=base)`，保存基础稿身份、产物哈希和正文
哈希，并在模型调用前验证项目、类型、业务 ID、阶段和父级。

薄运行器输入限制为 32,000 UTF-8 字节，只允许最多八份同项目 `user_material` 媒体观察支撑“已有素材”；
对标证据不能冒充生产资源。模型失败、合同失败或谱系失败均不封存半份结果。合同与运行时回归
`41 passed`，Ruff、格式和差异检查通过。项目主链、形式适配稿、素材方案和 MediaArtifact 尚未接通，
因此仍不能宣称发布前链完成。详见
`audits/A64-format-decision-runtime-and-base-draft-binding.md`。

## A65 最小项目简报运行时

2026-08-17 新增确定性的 `build_minimal_incubation_brief`，把语义模块冻结的 `source_object` 与用户整句
原话逐字核对后，只记录一条 `user_stated` 业务事实。非连续片段、空值和改写均拒绝；能力、资源、限制、
目标、偏好、受众、变现和平台不被猜测，并保留显式未知。构造器不接模型、问卷、模板或检索。

最小简报、领域合同和孵化判断联合回归 `21 passed`。当前是可接线零件，尚未由内容工具调用、读取项目
证据或自动持久化。详见 `audits/A65-minimal-incubation-brief-runtime.md`。

## A66 孵化判断进入内容交付的边界

2026-08-18 将已封存的孵化判断接到 `MessagePlan` 生成边界。内容交付只读取定位、受众假设、人设、
账号级表达方向、未知与备选；变现假设明确不进入 TopicBrief 或 BaseDraft。判断只能校准账号立场与
解释重点，不能重选内容根、选题、事实或单条表现形式。

当判断实际参与交付时，`message_plan` 同时绑定精确 `topic_brief + incubation_judgment`；选题仍只
绑定阅读和冻结地图。不同项目、错误类型、不同地图版本或没有交付的判断均在封存前拒绝。聚焦回归
`25 passed`。内容工具自动构造、项目证据读取、持久化和表现形式主链接线仍在进行。详见
`audits/A66-incubation-judgment-to-delivery-lineage.md`。

## A67 表现形式适配稿

2026-08-18 在 `BaseDraft + FormatDecision` 之后新增独立 `AdaptedDraft`。每个表现单元必须引用基础稿
中的连续逐字片段并保存字符位置；适配层不能换题、补事实、改证据、加销售平台发布或固定数量。
图文和纯素材不强迫表演，微短剧和情景剧才允许高层场面与表演提示。

模型输入限制为 24,000 UTF-8 字节，父级、正文哈希、形式或输出合同失败均不封存。联合回归
`61 passed`。素材与拍摄方案尚需改为消费精确适配稿，内容工具自动编排仍未完成。详见
`audits/A67-format-adapted-draft.md`。

## A68 项目孵化证据选择

2026-08-18 新增无模型、无网络的正式项目证据选择器。对标只认已通过 `BenchmarkSnapshot` 合同的
`benchmark_evidence`；受众只认正式 owned/benchmark audience observation。选题资料、用户素材、
候选账号、浏览器原始内容和普通阅读记录不会混入孵化判断。

输入严格同项目，结果稳定去重、最新优先并限制为对标两份、受众两份；截断、近似但不合格候选与
缺失均留下限制说明。没有正式证据只标 missing，不阻断判断。选择器测试 `6 passed`，与判断运行时
联合回归 `14 passed`。内容工具读取与主链接线仍待完成。详见
`audits/A68-project-judgment-evidence-selection.md`。

## A69 素材方案与成片产物谱系

2026-08-18 修正制作层父级。ProductionPlan 现在消费精确 `AdaptedDraft + FormatDecision`，保存适配
正文哈希，不再越级从 BaseDraft 另写内容；已有素材必须是同项目、经精确形式决定审阅的
`user_material` 媒体观察。

MediaArtifact 绑定适配正文、精确方案、输入集合、MediaKit 回执、稳定内部引用、媒体字节哈希和 QC。
媒体观察必须由方案批准，中间媒体必须来自同一方案，声明父级缺失时拒绝。合同测试 `29 passed`。
模型生成 ProductionPlan、动态 Schema 执行与主链接线继续进行。详见
`audits/A69-production-plan-and-media-artifact-lineage.md`。

## A70 孵化判断主链接线

2026-08-18 将 A65 最小 Brief、A68 正式项目证据和 A63 判断运行时接入可拍选题工具。选中项目后，
本轮阅读、冻结地图与实际采用的选题证据先落账，再构造 Brief、读取正式对标/受众证据、生成并保存
IncubationJudgment，最后让其编辑投影参与 MessagePlan；变现仍不进入 TopicBrief 或 BaseDraft。

回答现在分栏展示定位、受众、人设、账号级表现方向、变现假设、未知和备选，且 MessagePlan 精确
绑定实际使用的判断。未选项目或判断准备失败不吞掉证据选题。联合回归 `79 passed`。单条
FormatDecision、适配稿、素材方案与 MediaKit 尚待继续接入本运行。详见
`audits/A70-incubation-runtime-orchestration.md`。

## A71 表现形式与适配稿主链接线

2026-08-18 将 A64 表现形式运行时和 A67 形式适配稿接到选中项目的有效 BaseDraft 之后。形式判断只
读取精确 MessagePlan、直接派生的 BaseDraft、可选孵化判断和最多八份同项目 `user_material`；适配稿
继续绑定精确形式决定，并让每个表现单元保留基础稿逐字锚点。

回答现在分栏展示本条表现形式与适配稿。内部 `_answer_appendix` 不进入前端持久化回执；后置模型失败
只降级这一段，不吞掉已经有效的选题和基础稿。联合回归 `103 passed`。详见
`audits/A71-format-adaptation-runtime-orchestration.md`。

## A72 素材与制作方案运行时

2026-08-18 新增 32 KB 有界 ProductionPlan 运行时。在模型调用前核验精确 AdaptedDraft、
FormatDecision、BaseDraft、MessagePlan 和最多八份已审阅 `user_material`；模型只负责素材需求、
拍摄/录音/排版动作和装配顺序，不能重开选题、改观点、补事实、编造资源或加入销售平台发布安排。

无素材时可形成带明确缺口的 `provisional` 方案；模型失败不封存半份结果。聚焦复核 `51 passed`。
主工具与 MediaKit 接线仍待完成。详见 `audits/A72-production-plan-runtime.md`。

## A73 制作方案主链接线

2026-08-18 将 A72 ProductionPlan 运行时接到选中项目的 FormatDecision 与 AdaptedDraft 之后，并把
状态、素材需求、拍摄/制作动作、装配顺序、资源缺口、未知和边界分栏展示。形式判断和制作方案复用
同一组已审阅 `user_material`，制作层不能另取对标或选题证据冒充素材。

后置制作失败不吞掉已经有效的内容产物。联合回归 `126 passed`。MediaKit 执行仍是下一独立断点。
详见 `audits/A73-production-plan-runtime-orchestration.md`。

## A74 受众观察与 HLLM 边界

2026-08-18 对照第五版 A38、第四版归档源码和字节 HLLM/HLLM-Creator 公开合同后，确认 HLLM
是受众行为之后的用户表征、分群和个性化创意底座，不是采集器或现成的自然语言粉丝画像 API。
公开仓库的 `user_profile` 是训练输入，数据准备中的画像文本又来自外部 Chat 模型，因此拒绝把
`interests / needs / content_affinities` 伪装成 HLLM-Creator 原生输出。

第六版现在可封存带明确人群口径的官方聚合画像并交给 A68。单 actor 交互序列改为
`audience_behavior_snapshot`：原始标识用 owner/项目/平台/账号作用域内的 HMAC-SHA256 伪名，评论、
回复和直播聊天原文不进入模型可见产物或 HLLM 请求。HLLM 输入只取同一 actor 最近 50 条经
证据匹配的行为，回执只能标明 `user_representation` 或 `cluster_assignment`。

审查期间曾实现“单 actor 直接封存为 cohort 画像”候选；静态复核证明它会夸大上游能力并误导孵化，
因此已在提交前删除，没有进入主线。A68 同时收紧为只接受全部 item 都是 `observed` 的受众快照，
本地派生、第三方估算和模型推断不能冒充平台观察。

当前为 `implemented boundary`：没有真实 HLLM 权重服务、多 actor 聚合、覆盖率回执或已验收画像解释器，
所以 HLLM 中间结果不进入 A68，也不是冷启动硬门。详见
`audits/A74-audience-observation-and-hllm-boundary.md`。

## A75 MediaKit 制作方案本地执行纵切

2026-08-18 在 A69/A73 的精确 ProductionPlan 谱系之后，新增首条真实
`ProductionPlan -> MediaKit -> MediaArtifact` 纵切。首版只允许本地 `editing/trim-video`，操作精确
绑定方案动作、装配步骤、计划素材、动态 Schema 和裁剪参数；输入必须来自同项目、已授权且字节未变的
`user_material`。

每次执行使用服务端创建的独立私有输出目录。只有目录内的普通文件可被物化，之后再经双哈希、
MediaKit 元信息质检、MIME 校验和内容寻址封存；命令、临时路径、权利引用和凭据不进入业务产物。
相同操作重放复用第一份封存回执。聚焦回归 `51 passed`。

真实烟测使用本机 `mediakit-cli 0.2.0` 将仓库演示 MP4 裁成一份 1 秒视频，得到 346,615 字节
`video/mp4`，QC 通过，保存为 `artifact://`，临时工作目录已清空。当前状态为 `verified local vertical`：
后端执行内核已通，但内容工具/Gateway/用户审阅入口、其他本地能力和云端真实验收仍待独立接线。详见
`audits/A75-mediakit-production-plan-local-execution.md`。

## A76 核心端到端、内容根与事实交付修复

2026-08-18 按用户要求暂停制作和素材，把真实验收终点收在 `AdaptedDraft`；表现形式与表达适配仍
属于孵化和内容认知，不等于制作。全新“宠物殡葬”留出题没有
从业务对象迁移到陪伴、失去、哀伤和告别世界，也没有形成 TopicBrief，严格记失败并转为开发证据。

雪茄馆回归又发现 A58 的采用实现把“雪茄品鉴”冻结成内容根并将人物、历史路线判为漂移。Git 追踪到
`c2ede5b6` 在并行提速之外同时替换了语义链，并把模型中间判断编译成候选硬门。本轮恢复其父提交的
顺序语义、词义家族、共同世界、独立复核、单根裁决和冻结地图；ADR-020 正式取代 ADR-019 的运行
决策。恢复后又通过通用反例修正“场馆 + 消费 + 社交”长场景冒充更大世界的问题，真实内容根最终为
“雪茄”。

完整研究随后形成 Cohiba 的政治特权、产区风土与工艺稀缺性选题。供应商未转义中文引号曾使完整
孵化和 MessagePlan 被解析器丢弃；统一结构化边界现在可将最多 16 KiB 畸形参数作为不可信数据做一次
纯协议修复。修复后的首稿又从模型记忆补入证据外人名并写出“全球最贵”，因此交付层新增一次有界
事实修复：证据外专名、数字、显式新名字和高风险绝对断言只能删除或泛化，仍越界则拒绝交付。

真实复跑得到标题“Cohiba：一支雪茄如何从政治特权走向全球溢价”，保留百科/零售商来源偏弱的
限制，并生成 MessagePlan 与 BaseDraft。真实续跑得到 `provisional` 的口头表达候选和八单元
AdaptedDraft，明确保留出镜、表达能力、平台和视觉资源未知；人工复核未见新增事实。最终台账有九类
认知与表达产物，不含 ProductionPlan 或 MediaArtifact。全部内容理解、孵化、形式、适配、制作合同与
导入边界回归为 `333 passed, 1 warning`。第一次完整回归发现七个新增内部提示标签尚未纳入共享防伪
净化名单；逐项归类并补回归后，相关净化测试 `180 passed`，第二次完整后端非 live 回归为
`12074 passed, 76 skipped, 17 warnings in 421.79s`。本轮没有运行 ProductionPlan、素材任务、MediaKit
或平台写操作。
一个雪茄案例通过不能覆盖宠物殡葬
失败，也不能宣称通用营销脑已经完成。详见
`audits/A76-core-e2e-root-and-delivery-recovery.md`、
`decisions/ADR-020-retire-parallel-root-gates-and-recover-evidence-delivery.md` 与
`evidence/core-e2e-a76-2026-08-18.md`。

## A77 Lead 固定上下文开销

2026-08-18 真实新会话只输入“你好”，没有工具或子 Agent，却产生 `14,695` 输入 Token。检查点实际
对话约 63 Token，病根是前端把未设置模式默认成 Pro、Tool Search 与 Skill 延迟发现关闭，以及每轮
同时注入 23 份 Skill 元数据、16 个抖音 MCP Schema、17 个常用工具 Schema 和冗长 Lead 手册。

本轮先写回归，再把未显式选择的思考模型默认改为 Thinking，启用 Skill/MCP 渐进发现，扩展
`tool_search.defer_tools` 以按需披露通用本地工具，并压缩 Lead 常驻提示。显式 Pro/Ultra、权限检查、
Skill 策略、孵化路由和事实边界均保留；提示模板新增 `9,000` UTF-8 字节上限。

同一问候的输入逐步从 `14,695 -> 9,606 -> 5,503 -> 3,879`，最终总计 `4,035` Token，固定输入下降
`73.6%`。没有增加问候短路。压缩后的黄金礼品真实回归虽未退回黄金知识，却停在“人际馈赠”并将
选题收敛到彩礼嫁妆；用户判定这仍是婚礼馈赠，不是“礼如何组织人与人相处”，所以业务回归失败。
固定入口优化结论仍成立；完整孵化运行的 `69.5K` Token、7 分 42 秒属于多节点认知管线成本，下一轮
必须独立测量和去重，不能再和固定入口浪费混算。详见
`audits/A77-lead-fixed-context-overhead.md` 与
`evidence/lead-context-overhead-a77-2026-08-18.md`。

## A78 语义入口与账号长期世界

2026-08-18 用户再次指出，把黄金礼品从“三金”改写为“婚礼馈赠”仍然失败：账号长期世界应进入
“礼如何影响人与人相处和社会秩序”，婚礼和馈赠只能是普通分支。追踪发现 `content_entry` 与耐久
`content_root` 曾被混为一个职责；即使拆开两者，共同世界合成者仍会被“礼在礼品中表示赠礼”提前
锚定。

本轮先以合同回归固定入口与长期根的分工：入口只进入阅读产物，地图、版本、搜索与选题只看经复核的
长期根。随后再隔离共同世界的两个注意力阶段：合成者只看独立意义成分及其语义家族，反事实复核者
之后才取得原复合词用途关系并检查回路。最终真实线程
`1b80470a-cd3c-4743-84cb-6cc3a9485ad3` 得到“人们以礼相待、依礼行事的世界”，地图主轴覆盖日常
相处、历史变化、失礼补救、权力资源、地域群体和跨文化礼节；婚礼、礼金与馈赠降为普通例子。

该运行 `15,888` 输入、`6,064` 输出、总计 `21,952` Token，7 次调用、162 秒。聚焦回归
`211 passed`，完整后端非 live 回归 `12080 passed, 76 skipped`，前端 `993 passed`。本地免登录配置
曾令 41 项认证测试被主动绕过；测试入口现固定 `DEER_FLOW_AUTH_DISABLED=0`，不改变产品运行设置。
这只是一条已标注案例的部分验收，且地图仍有一次“礼节博弈”的抽象措辞；不为此新增关键词硬门或
工作流。详见 `audits/A78-semantic-entry-and-account-world.md` 与
`evidence/golden-gift-entry-world-a78-2026-08-18.md`。

## A79 内容机会、对标证据与账号策略拆分

2026-08-18 用户指出账号定位是会随账号数据长期修订的业务对象，不应藏在语义与内容地图模块；
对标账号也不应与当前这一整条内容工具混成一坨。代码、Git 和台账复核确认这不是命名问题：原来的
`content_intelligence_tool.py` 同时负责候选内容机会、资料和对标证据、账号长期判断、单条选题、
成稿、形式与制作。更严重的是，每条具体选题先完成 TopicBrief，之后才临时创建
`IncubationJudgment`。定位没有指导选题，却会在交付阶段倒灌本条文案。

本轮按生命周期和决策权拆分：

- `ContentWorldView` 降为 `content_map_candidate`，只保存候选地图根、方向和边界。它不再宣称账号
  定位，也不决定受众、人设、账号级表现形式或变现。
- 根裁决显式分别选择语义入口与候选地图根。删除“已复核共同世界无条件覆盖模型选择”的隐藏改写；
  窄场景继续以 `example_branch` 约束，婚礼、购买、到店、宴请等不能因人物丰富就自动篡位。
- 新增独立 `develop_account_strategy`。只有它能读取项目事实、候选地图和正式对标/受众证据，形成
  定位、受众、人设、账号级表现方向和变现假设。
- `IncubationJudgment` 增加 `revision_number`、上一版产物 ID 和修改原因。相同父输入复用现有版本；
  变化必须生成紧邻后继版本并保留上一版，不能覆盖历史。
- 内容工具不再调用正式对标证据选择器，也不再生成孵化判断。具体选题只能读取与当前候选地图版本
  精确匹配的现有判断；没有就继续做内容机会和选题，不临时补造定位。
- `benchmark_account_candidate`、正式 `BenchmarkSnapshot` 和普通 `topic_evidence` 继续隔离。对标
  快照是只读观察，不拥有定位权，也不能进入语义或内容地图。

聚焦合同、账号策略、工具和架构边界回归为 `112 passed`。首次完整后端回归为
`12089 passed, 2 failed, 76 skipped`；两项失败均是旧测试仍要求“内容地图就是账号定位”。更新为新
合同后，聚焦交付回归 `8 passed`；格式与静态检查通过，最终完整后端非 live 回归为
`12091 passed, 76 skipped, 17 warnings in 439.41s`。

当前仍有两项明确未完成：线程只绑定项目，尚未绑定某个平台账号，所以默认解析的是项目级策略；
现役抖音对标采集只生成候选证据，正式 `BenchmarkSnapshot` 的稳定身份、多作品一致性与覆盖连接器
尚未生产接通。详见 `audits/A79-content-opportunity-account-strategy-boundary.md` 和
`decisions/ADR-021-separate-content-opportunity-account-strategy.md`。

## A80 账号路线提案与用户确认

2026-08-18 用户进一步明确，首次起号不应要求先登录平台账号，也不能由模型只给一条定位后默认
采用。它至少应展示几条把长期讲什么、受众、人设、真人出镜、无人素材、数字人、AI 情景剧、
AI 微电影或 MV 等表现形式、变现假设、资源和代价连成一体的路线；Agent 根据项目、产品和可选
对标证据推荐，用户确认后才能进入下一步。

本轮先以失败测试固定“推荐不等于确认、候选不得少于两条、未确认策略不得进入选题、无需
`PlatformAccountRef`、用户可选择非推荐路线”。实现中发现深嵌套持久化合同使真实 GLM 连续返回
畸形工具参数，因此改为扁平 `AccountStrategyProposalDraft`，再由代码编译为有父级、版本和哈希的
`IncubationJudgment`。模型合同没有版本号、确认状态或已选路线，不能自行替用户点头。

真实黄金礼品薄合同第一次虽技术通过，三条路线仍围着产品打转。继续追踪发现一个定位字段混合了
“账号长期讲什么”和“业务如何承接”。拆为 `content_subject` 与 `business_connection` 后，同一封存
内容根得到“礼的田野观察者”和“礼的场景档案馆”，黄金礼品只作为从业观察位置和后续承接。全新
“旧家具修复”完整链得到真人匠人纪实、无人素材影像志和 AI“家具前世今生”三条路线；系统推荐
真人纪实，但 `selected_option_id` 仍为空。

黄金拆字段后的路线调用为 `117.57s`；旧家具完整链语义/地图 `127.13s`、路线 `97.67s`，合计
`224.80s`。因此业务边界通过、交互速度未通过。平台账号绑定、正式对标连接器和可视化路线卡片
延期，不作为初步孵化硬门。聚焦回归 `85 passed`；首次全量回归只因根级 Agent 指南超过软预算
93 字节失败，压缩固定上下文后预算测试 `12 passed`，最终完整后端非 live 回归为
`12099 passed, 76 skipped, 17 warnings in 496.05s`。完整证据见
`audits/A80-account-route-proposal-and-confirmation.md`，决策由
`decisions/ADR-022-propose-account-routes-before-confirmation.md` 固定。

## A81 共同世界协议漂移与人情世故内容根

2026-08-18 以隐藏答案方式复测“我是做黄金礼品的，我要怎么起号？”。首轮真实完整链的共同世界
合成连续两次未通过结构校验，候选被降级撤下，最终内容根退化为“人际赠予与馈赠”；地图虽已出现
职场送礼与权力关系，仍没有越过赠予，严格记失败。旧日志只保存 `ValidationError` 类型，不能反推
具体字段。

本轮先写失败测试，将供应商 `null` 集合归一、构成语境筛选和世界/路径一致性从模型解析层移到
确定性归一化层。材质或样式被误填为构成语境时只清掉误填项，不再丢弃有效共同世界；真正改变人物、
共同事件、关系或生命周期的构成语境若遗漏或被世界名擦除，候选仍撤下。没有加入黄金、人情世故或
职场关键词。

同输入、同模型修复后真实复跑耗时 `158.65s`，最终内容根为“人们以礼来规范如何相处、如何做事的
共同秩序”，地图自行形成“礼在权力与资源不对等关系中的运作”“商业往来中的礼与利”“上下级越界
后果”等分支。内容根和地图因此取得一次恢复通过；小王与小张的完整反转仍是下游具体故事选题，不得
记成地图已经生成。首轮速度与多次稳定率仍未通过。详见
`audits/A81-shared-world-provider-drift-and-human-affairs-root.md` 与
`evidence/golden-gift-human-affairs-a81-2026-08-18.md`。聚焦分析器 `45 passed`，内容理解、研究、交付
与账号策略联合回归 `163 passed`，完整后端非 live 为
`12103 passed, 76 skipped, 17 warnings in 497.10s`。

## A82 首次项目自举、经营容器内容根与续写串线

2026-08-18 普通前端新会话直接输入“我是开水果店的，我要怎么起号”，首次回答却要求先创建或选择
项目。追踪确认 A80 的无平台账号验收预先注入了项目，而产品入口没有项目选择器。现改为在可信 owner
与 thread 下按确定性 ID 惰性创建隐式线程项目；显式失效项目仍拒绝，后续运行会把已存在的隐式项目
写回线程 metadata 并由服务端重水化。该修复只代办内部建档，不绕过所有权、项目谱系或用户路线确认。

自举后的第一轮又把“水果店”解析为经营容器、把“水果”识别为被服务对象，却让“人们聚在固定场所
买卖水果”赢得内容根。病根是共同世界复读了无修饰“店”的泛化经营动作，再把品类修饰语加回去，
形成一个看似更大的长标签。确定性候选构造现把这类经营容器交易回声降为被服务对象旁边的场景分支；
药店/药品留出回归通过，KTV 等没有独立被服务商品的活动场馆不受影响。

真实复跑的根裁决已经选择“水果”，地图展开品种、产地、季节、果农、流通、驯化与饮食文化，并生成
“阳光玫瑰价格变化”具体选题。但同一线程已有“季节周期记录者”确认版本，Lead 擅自把重复的起号问题
解释为继续生成第一条选题，继而跑到取证、文案和表现形式；整轮耗费 `103380` Token、`18` 次模型调用、
约 `12m39s`。因此项目自举与内容根修复可采用，首次起号/确认后续写/重新评估的意图与停止边界仍失败。
详见 `audits/A82-thread-project-bootstrap-and-container-root.md` 与
`evidence/fruit-store-bootstrap-root-a82-2026-08-18.md`。
聚焦联合回归 `230 passed`，开发手册与 Lead 提示预算 `40 passed`，完整后端非 live 回归为
`12108 passed, 76 skipped, 17 warnings in 499.11s`。

## A83 内容根泛化现成方案与采用边界

2026-08-18 针对“修一个案例、另一个案例又坏，是否需要逐条人工标注或建设向量知识库”完成大厂生产
系统、论文、中文语义资源、开源优化器、数据反馈工具和营销 Agent 的交叉审计。没有发现可直接安装的
“中文商业表达 -> 最大有效营销内容世界”成品；现有营销 Agent 普遍从既有商业背景、受众或内容支柱
开始，不能替代内容根判断。

最接近的成熟路线来自阿里 AliCoCo 和亚马逊 FolkScope/COSMO：商品类目和属性之上另建用户需求、
意图、功能、事件、受众和社会场景关系，由模型生成候选、人工判断合理性与典型性、模型再扩展判断。
后续研究又证明固定类别会产生类别僵化和属性歧义，因此第六版只借可空关系图和偏好数据，不把关系
枚举变成新的硬门。

下一阶段候选方案为隔离 `ContentRootLab`：开放候选生成，可选 OpenHowNet 中文词义证据，可审阅的
营销常识关系图，成对偏好与反例，再由 DSPy 离线优化选择器；只把通过冻结留出评测的提示/示例工件
导回现有 DeerFlow。LLooM 延后用于账号语料概念归纳，Distilabel/Argilla 只借数据合同，Agent Lightning
延后到真实奖励稳定之后。普通向量 RAG 只可检索案例与证据，不拥有根裁决权。本轮没有修改运行时、
提示词或测试，详见 `audits/A83-existing-content-root-generalization-solutions.md`。

## A84-A96 内容根实验回顾、用户纠错与自举边界

2026-08-19，A84 首次比较现役基线、开放关系候选图和 DSPy 偏好选择器。关系图降低调用与 Token，
但人工最终选择仅 `2/4`；七条开发偏好使 DSPy 修好羽毛球馆的同时弄坏儿童安全座椅。A90 后续双工作者
拆分又把候选下钻成具体路径，人工召回低于单工作者，因此多 Agent 和继续堆关系步骤均被拒绝。

A92 改用一次调用的薄候选合同，取得 `12/12` 合同成功和更低成本，但仍未过冻结门槛。更重要的是，
用户在 A94-A95 发现评测答案本身也有问题：房车租赁不应把“自驾旅行”当终点，缺失跃迁是“房车旅行
-> 旅行”；老年助听器不能只按听力健康和沟通计分，还应允许孝亲敬老、陪父母老去等关系世界，并允许
该品类不足以独立支撑 IP。A92 原人工聚合分数因此只保留为历史审计结果，不再冒充业务真值。

A96 据此把下一步从“再次自动改提示词”改为自举数据闭环：显式用户纠错保存为带条件、可争议的
`RootFeedbackRecord`；模型自动生成跨行业结构变体，确定性代码过滤合同和泄漏，多次独立评审只把分歧、
新关系、无强根和依赖未知条件的少数案例交给用户。抖音与网页证据只验证候选内容世界的真实容量，不拥有
语义裁决权。确认数据积累后才允许 DSPy 或小排序器离线优化，并必须通过全新、用户复核、允许多答案和
弱 IP 的冻结评测后版本化晋级。现役 Lead、提示和运行时均未修改。详见
`audits/A84-content-root-lab-preregistration.md`、`audits/A85-content-root-lab-result.md`、
`audits/A92-thin-single-agent-content-root-preregistration.md`、
`audits/A93-thin-single-agent-content-root-result.md`、
`audits/A94-rv-travel-content-root-correction.md`、
`audits/A95-senior-hearing-aid-root-and-ip-viability-correction.md` 与
`audits/A96-content-root-bootstrapping-loop.md`。

## A97 仓颉、创作者方法与平台证据的自进化编排

2026-08-19 复核第五版 E15、第四版仓颉适配 Skill、个人 IP 创作者方法图谱，以及第六版抖音
OpenAPI/MCP、MediaKit 和 HLLM 的真实状态。它们可以组成自进化系统，但不能作为多个拥有决策权的
Skill 同时常驻 Lead：抖音与 MediaKit 是观察层，仓颉式适配是证据编译层，金枪大叔、薛辉小清新、
亲爱的安先生和文案三把刀是提出可测试创意机制的方法卡，HLLM 只在真实逐受众行为和多 actor 聚合验收
后提供推断证据，Lead 仍是唯一营销判断者。

自进化被限定为追加式、可复核和可回滚的数据闭环：`RootFeedbackRecord / AccountEvidencePack ->
MechanismHypothesis -> PreflightPrediction -> PublicationReceipt / MetricSnapshot -> Retrospective /
LearningClaim -> 离线候选版本 -> 全新冻结评测`。禁止运行中自动修改核心提示、自动安装方法、把单条
爆款或模型自评分提升为规则。当前只是架构候选；仓颉与创作者图谱尚未迁入第六版运行时，抖音真实凭据、
MediaKit 广义感知与 HLLM 真实推理仍有未验收断点。详见
`audits/A97-skill-evidence-self-evolving-system.md`。

## A98 现有模块最小接线

2026-08-19 对第六版现役工具和领域合同逐项复核后，确认不需要新增总编排器、固定多 Agent、向量数据库
或第二套营销领域包。`develop_account_strategy` 已经串联项目自举、语义、候选内容地图、正式对标/受众
证据、路线提案和用户确认；内容工具也已串联网页/抖音选题证据、`TopicBrief`、`MessagePlan`、基础文案、
本条表现形式和适配稿。

最小缺口被压缩为三个薄连接件：`AccountPatternEvidence` 将抖音账号作品、MediaKit 时序观察与仓颉式
五层分析接入现有证据中心；`MechanismUseRecord` 保存本轮按需采用的金枪大叔、薛辉、亲爱的安先生或
文案三把刀方法及其可观察预测；反馈入口分别保存用户纠错 `RootFeedbackRecord` 和后续真实运营
`LearningClaim`。MediaKit 仅在有视频时启动，HLLM 仅在有合格逐受众行为和真实推理回执时启动，缺少
对标或平台账号均不阻断初步孵化。当前只完成接线审计，运行时未修改。详见
`audits/A98-existing-modules-minimal-wiring.md`。

## A99 对标优先孵化先导实验预注册与运行前修订

2026-08-19 在任何搜索证据和真实模型输出前冻结七个全新案例，并经两轮独立只读审查修订。A 只保留为
公开网页直接同行弱基线；B、C 都改为一次中间调用加一次公共方案调用。B 先冻结中性证据摘要，C 先冻结
一句长期主题和二至五个分支，最终盲审只看三组相同字段。实验因此只回答“显式冻结薄内容世界是否有
额外增益”，不能直接回答完整账号拆解能否替代内容根。

隐藏复核焦点已从运行案例拆到密封文件。公开证据使用实验专用 typed DDG 适配器，固定每次五条并区分
空结果和异常；同一规范 URL 可同时保留同行、需求和机制归属。证据 ID 绑定 provider、规范 URL 和标题/
摘要哈希，证据包重算哈希并绑定案例。模型输入预检包含消息、Schema 和修复文本；每个阶段/组共享修复
账本，最多两次。流程拆成“冻结证据 -> 自动覆盖 -> 人工相关性审核 -> B/C 中间结果 -> 真实输入预检 ->
A/B/C 公共路线 -> 盲审 -> 密封标签检查”，代码、提示、Schema 和数据哈希随回执保存。

本轮仍只使用 `public_web_benchmark_discovery`，不冒充抖音 OpenAPI、MediaKit 多作品拆解或稳定账号证据。
无论结果如何都保持离线，只有后续每行业至少两个稳定账号、每账号至少八条作者一致作品的真实复验才有资格
讨论架构替换。详见 `audits/A99-benchmark-first-incubation-preregistration.md`。

## A100 对标优先孵化先导实验止于证据门槛

2026-08-19 从干净提交 `c47ab1c4` 运行 A99 正式证据阶段。七题搜索规划合同均成功，21 次搜索在自动
数量检查中都返回同行、需求、机制各五条；但逐条人工复核后，只有宠物殡葬和老照片修复同时取得可区分
的三类证据。儿童摄影、工业防腐涂料和户外移动电源缺少合格可迁移机制，企业团建与夫妻肺片调料包连
同行或需求证据也被错页、空页和 SEO 噪声污染。夫妻肺片的查询规划没有误拆成婚姻或肺部健康，说明失败
发生在公开搜索召回而非该词义陷阱。

依照预注册的全七题人工证据门槛，本轮在任何 B/C 中间调用、A/B/C 起号路线和盲审前停止，不能将结果
解释为某种孵化架构失败。当前结论仅为：公开网页候选发现不能冒充完整对标拆解，也不足以验证“单靠对标
替代内容根/地图”。下一次只能用全新行业、稳定抖音账号、多作品 OpenAPI 回执和 MediaKit 时序证据重新
预注册；普通咨询资料与对标证据继续分账。详见 `audits/A100-benchmark-first-incubation-evidence-result.md`。
