# 第六版内容孵化内核台账

## 当前状态

- 台账日期：2026-08-14
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
