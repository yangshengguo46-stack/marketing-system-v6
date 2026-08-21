---
id: A134
status: reviewed
date: 2026-08-22
sources:
  - A114-single-capability-gateway-and-child-runtime.md
  - A128-agent-owned-incubation-routing.md
  - A129-deepseek-codex-harness-reference.md
  - A133-a132-full-harness-business-review.md
  - ADR-018-artifact-graph-orchestration.md
  - ADR-040-agent-owned-incubation-routing.md
  - backend/packages/harness/deerflow/agents/lead_agent/prompt.py
  - backend/packages/harness/deerflow/tools/tools.py
  - backend/packages/harness/deerflow/tools/builtins/account_incubation_tool.py
  - backend/packages/harness/deerflow/tools/builtins/content_intelligence_tool.py
---

# A134 当前架构、台账与三循环对账

## 审计范围

本轮从当前 Git HEAD、现役 Lead Prompt、默认工具目录、孵化工件、内容工具、Gateway 项目重水化、统一能力
MCP、实施计划和 A01-A133 台账反向核对。目标不是再评价某个行业答案，而是回答：当前系统到底有哪些真实
可达能力，三条循环是否连通，历史决策是否仍与运行时代码一致。

审计时分支为 `codex/v6-comprehension-core@02c3bacb`，工作区干净；官方 DeerFlow 起点
`cd87968a` 是当前 HEAD 的祖先，分支领先 `origin/main` 105 个提交。该分支没有远端跟踪分支，属于本机
备份风险，不是代码正确性问题。本轮聚焦架构、账号工具、内容工具和 Gateway 的 204 项测试全部通过；
这些测试没有覆盖下述动态方向持久化断点。

## 真实架构

设计原则仍然成立：一个 Lead、三条按需循环、两个执行底座、一套业务台账。真实实现状态却不是完整闭环：

| 区域 | 当前真实状态 | 判断 |
| --- | --- | --- |
| Lead 判断 | A128 后可直接回答、澄清或按需调用 Skill、词项、地图、对标 | 现役且方向正确 |
| 孵化循环 | 首轮方向只存在于聊天；旧地图绑定提案器已退出默认工具 | 入口断链 |
| 内容循环 | 独立请求可从语义、候选地图、取证走到 TopicBrief、MessagePlan、BaseDraft，可选到 AdaptedDraft | 部分可用 |
| 学习循环 | 发布前预演、回执、指标、复盘与 LearningClaim 没有现役 Agent 入口 | 尚未实现，且当前延期 |
| MediaKit | 本地感知、可信 I/O 和首个 trim 纵切已验收 | 制作执行暂停；对标视频感知仍保留在后续主线 |
| 平台证据 | 单一 MCP 网关已在本机真实调用抖音只读 Child；官方搜索仍受 Scope 阻塞 | 研发可用，非商业生产 |

## 主要问题

### P1 动态账号方向没有业务工件

A128 取消 `develop_account_strategy` 固定流程后，Lead 的判断变成自由聊天输出。旧
`IncubationJudgment` 又强制要求 `incubation_brief + content_map_candidate` 父级和精确地图版本，不能
原样承接自由判断。结果是账号方向可以答对，却不能可靠完成：

```text
方向提案 -> 用户选择 -> 确认版本 -> 后续内容复用 -> 新证据修订
```

这不是模型能力问题，而是缺少一枚薄的追加式业务对象。

### P1 新入口与内容循环没有连续性

`explore_content_world` 只能复用旧式、精确绑定候选地图的 confirmed `IncubationJudgment`。新的动态方向
没有地图父级，也没有可读取工件；因此后续“按刚才方向给一条选题”只能依赖聊天记忆，压缩、重开线程或
跨日运营后无法从业务台账重建。

### P1 隐式项目创建仍藏在退休工具里

旧 `develop_account_strategy` 会在首次请求时创建确定性的隐式项目和逻辑账号。Gateway 只会绑定已经存在
的隐式对象，不会创建它们。Lead 直接回答时没有触发持久化，因此首次账号方向连项目作用域都可能不存在。
项目不应为普通聊天自动创建，但任何正式方向落账必须通过一个共用、幂等的作用域创建器。

### P1 对标 Provider 尚未完全收口

A114 已建立 `deerflow-capability-mcp` 单入口，七个公开抖音 Child 也完成真实验收；但现役
`douyin_benchmark_tool.py` 仍直接构造官方 Router，并直接回退 `douyin_browser`，账号 URL 采集更是只走
旧浏览器采集器。统一网关的决策和高层工具实际路径不一致。下一切片应在同一个网关合同下完成
`候选 -> 稳定账号 -> 多作品 -> 评论/互动 -> BenchmarkSnapshot`，再接 MediaKit 观察；不能再保留第二套
业务可见 Provider 编排。

### P2 文档和工具面仍保留旧流程口径

`ARCHITECTURE.md`、`IMPLEMENTATION_PLAN.md` 和 `tools/AGENTS.md` 仍把
`develop_account_strategy -> confirm_account_strategy` 写成当前主路径。默认工具目录却只有旧确认器和旧
起号计划，没有新方向提案生产者。A132 实测因此在首轮暴露了三个暂时不可达的旧 Schema。本轮将它们改为
延迟发现；没有删除旧工件或历史兼容实现。

### P2 内容工具成本与职责过大

`explore_content_world` 是一个高层业务能力，不是对外固定工作流；但其 `one_shootable_topic` 实现内部仍
同时承担语义、根候选、地图、并行搜索、证据阅读、选题和成稿，文件约 1392 行。这个组合能工作，也符合
“用户要一条可拍选题”的结果合同，但冷启动成本和故障归因都偏高。后续优化应按产物缓存和可重用边界拆分，
不能再叠 Prompt、关键词门或平级营销 Agent。

### P2 仍有三处注意力与输入重复风险

- Lead 可显式调用 `verify_business_term`，内容工具内部又创建 `TermResolver`，旧账号工具还有同一辅助路径；
  当前没有一个可复用的词项解析工件，可能在同轮重复搜索或得到不同解释。
- `explore_content_world` 未收到 `subject_expression` 时会把完整 `user_request` 回退为营销主体。对“我是做
  黄金礼品的，该怎么起号”这类问句，问题动作可能再次混入主体语义。该处应先做新留出测试，不能直接再加
  关键词清洗。
- Lead 同时收到“没有工具或方法是必经第一步”“行业内容问题先检查匹配 Skill”和全局 `Skill First`。
  A133 的黄金礼品成功又确实依赖渐进加载 Skill，因此这是待观测的注意力张力，不应在没有真实 A/B 前删掉
  任意一边。

### P2 运行可观测性与验收回执不完整

ADR-041 的生产 `PromptManifest` 尚未实现；目前只有实验清单。A126/A128 的真实运行也没有独立机器回执，
只能从审计表格复核。两项都不阻断当前主线，但在再次优化 Token、Skill 或 Prompt 前应补齐。

### P2 平台与 Git 的运营边界

- 官方抖音稳定应用 Token 已真实可用；官方搜索业务仍因应用 Scope/内测准入失败，不是缺 Key。
- 本机公开证据 Child 真实可用，但上游 MIT 与 README 非商用文字冲突，生产前需澄清或洁净重写。
- 当前第六版分支没有远端跟踪分支，机器故障时 105 个本地提交缺少远端副本；推送属于外部操作，未在本轮执行。

## 没有判为问题的部分

- 保留一个 Lead 是正确的；不恢复固定受众表、固定地图、固定对标或固定子 Agent 阵容。
- 内容根方法可以在一次可选调用中冻结候选地图根；Lead 决定是否采用它，不需要把所有内部候选再交给
  多个平级 Agent 争夺最终权力。
- 用户已明确暂停素材、制作、预演、发布和复盘，因此学习循环未完成是当前范围状态，不是假装已闭环。
- A130/A132 等已拒绝实验仍隔离在 `backend/experiments`，没有偷偷注册进生产运行时。

## 当前主线顺序

1. 实现 `AccountDirectionProposal -> AccountDirectionVersion` 薄桥：由 Lead 填写判断，确定性代码只做
   所有权、原话绑定、版本、父级、哈希和用户确认；不要求先有地图、对标或完整受众工件。
2. 让确认方向作为内容循环的可选编辑上下文；内容地图在真正需要选题时按需生成，不能反向改写方向。
3. 迁移或只读兼容旧 `IncubationJudgment`，再移除孤儿确认工具和退休的大型策略工具。
4. 将两个抖音对标高层工具统一到单一能力网关，封存正式对标快照并补 MediaKit/受众反应。
5. 实现无行为影响的生产 `PromptManifest`，再做成本优化。
6. 继续保持制作、发布和学习循环暂停，直到用户重新打开该范围。

本轮只接受上述接线修复，不再增加行业规则、全局业务卡、向量库、固定流程或第二 Agent Runtime。

## 本轮验证回执

- 延迟发现配置先由测试新增三个旧工具断言，修改配置前按预期失败，修改后定向用例通过。
- 工具发现、延迟装配、孵化边界、旧账号孵化兼容、内容主链和 Gateway 联合回归：`224 passed`。
- AGENTS 指导预算与 GitHub Agent 配置：`24 passed`；`backend/AGENTS.md` 从 25,537 字节压缩到
  22,954 字节，重新低于 24,576 字节软上限。
- 后端非实时全量：`12452 passed, 75 skipped, 1 failed`。唯一失败为
  `TestSyncSingletonThreadSafety::test_concurrent_checkpointer_getter_creates_one_instance` 在全量负载下等待
  后台线程 3 秒超时；脱离全量负载精确复跑为 `1 passed in 3.21s`。它不在本轮改动路径，但全量结果仍按
  原样记录，不冒充一次性全绿。
