# 第六版孵化运营系统实施计划

## 文档状态

- 日期：2026-08-16
- 状态：`active implementation plan`
- 第六版开发分支：`codex/v6-comprehension-core`
- 第六版当前基线检查点：`f752d3a1`（后续实施事实以 `LEDGER.md` 和独立提交为准）
- 第五版只读来源：`/Users/yangyucheng/Documents/ChatGPT/第五版营销系统@3ee135f7`
- 第四版只读来源：`/Users/yangyucheng/Documents/第四版营销系统@58f4e0c9`
- 架构决策：`decisions/ADR-018-artifact-graph-orchestration.md`

这份文档是实施顺序和验收基线；`LEDGER.md` 只记录已经发生的事实。计划变更时必须记录原因，
不得倒改旧验收结论。

## 目标与非目标

目标是把已有的孵化判断、账号证据、内容创作、MediaKit 制作、抖音观察与发布、预演、
回执、指标与复盘能力组装成一个可追溯的运营闭环。

首轮非目标：

- 不同时开发六个平台的发布写路径；先用抖音真实测试账号打通一条。
- 不将抖音 119 个目录项一次性全部启用；按领域和风险逐项验收。
- 不迁移第四版的固定流程、SOUL、语义硬门、Writer Brain 单体和旧中间件。
- 不开发电影化 IP 或导演工作台。
- TikTok 达人签约只保留为延期业务模块，不进入当前主线。

## 当前主线断点

2026-08-17 用户确认语义理解、内容根与内容地图按 A58 当前可用版本冻结，不再为追求最优解阻塞
后续产品。`TopicBrief` 是下一个具体开发模块，但系统目标没有缩成选题工具。

发布回执之前仍必须完成的主链为：

```text
项目事实
-> 语义理解 / 内容根 / 账号级内容地图
-> 对标与受众证据
-> 孵化判断：定位 / 受众 / 人设 / 表现形式 / 变现
-> 具体 TopicBrief
-> MessagePlan / BaseDraft / FormatDecision
-> 素材方案 / MediaKit 感知与制作 / MediaArtifact
```

当前暂缓点从 `PreflightPrediction` 开始，包括不可逆发布审批、平台写操作、发布回执、指标与复盘。
前面已经实现的 A41-A57 证据、项目谱系、抖音 MCP 与 MediaKit 基础必须继续复用，不能因开发
`TopicBrief` 而另起一条孤立链路。

## 状态语义

| 状态 | 含义 |
| --- | --- |
| `discovered` | 发现代码、文档或能力线索 |
| `traced` | 已追到来源仓库、分支、提交和未提交快照 |
| `reviewed` | 已理解输入、输出、失败史和权限边界 |
| `adopted` | 已决定在第六版以新合同实现 |
| `rejected` | 已明确不迁移，只保留证据 |
| `implemented` | 第六版已有代码与自动测试 |
| `verified` | 已在真实模型、真实素材或真实平台回执上通过指定验收 |
| `production` | 所有权、密钥、恢复、可观测性和真实账号验收全部通过 |

## 模块迁移矩阵

| 模块 | 当前来源 | 真实状态 | 第六版决定 | 下一验收 |
| --- | --- | --- | --- | --- |
| DeerFlow Lead | 第六版 | `implemented` | 保留唯一对外判断权 | 工具路由不要求固定轨迹 |
| 项目与账号事实台账 | 第六版 `deerflow.incubation` | `implemented; server runtime and content lineage verified` | 保留最小产物图合同、SQL 持久化、owner-scoped API 与线程重水化 | 前端选择器、产物查询与真实多账号验收 |
| 语义、内容根与账号地图 | 第六版 `content_intelligence` | `implemented; two-reader overlap and context binding verified offline` | 保留现有运行时和项目版本谱系 | 新保留集真实质量/延迟、用户确认与版本切换 |
| 选题证据与洞察 | 第六版联网阅读 | `implemented; goal and exact-path contracts verified offline` | 洞察收敛保留在 `TopicBrief` 前，不新建自由 Agent | 真实模型热点、跨事件和象征联系回执 |
| 抖音 OpenAPI Catalog/MCP | 第六版 | `implemented` | 保留 Manifest 渐进披露 | 逐项真实权限与回执验收 |
| 抖音公开视频/体验搜索 | 第六版 | `v2/MCP content route and project evidence lineage implemented; live credentials pending` | 选题经 MCP 为 `topic_evidence`，对标发现可跨页聚合为候选证据 | 绑定三项本地应用凭据后做 v2 真实回执与项目入库复核 |
| 对标账号采集 | 官方抖音能力 + 第六版 `BenchmarkSnapshot` | `author-label candidate aggregation implemented; stable identity connector pending` | 官方搜索先按作者显示名聚合候选；稳定身份、作者一致多作品与覆盖回执后才升级快照 | 先验收官方公开搜索；星图/百应延期为字段缺口补充；第五版采集器不默认迁移 |
| 对标模式分析 | 第五版 A39/A41 | `reviewed` | 重写为只读证据分析，不直接定位当前用户 | 支持样本、反例、时期迁移与不可复制条件 |
| 受众情报 | 第五版 E15/A38/A40 | `reviewed; partial verification` | 区分粉丝、观众、互动者、直播观众和购买者 | 自有账号官方数据与对标可见证据分路验收 |
| MediaKit 感知 | 第五版 E15 + 第六版薄路由 | `local metadata + trusted private I/O verified; live cloud disabled` | 保留动态 Schema、窄结果合同、脱敏回执和哈希；云驱动使用持久意图、精确批准、私有来源与受控物化 | 逐项登记结果策略并验收 ASR/OCR/场景切分与人工核对 |
| `MessagePlan` 与基础文案 | 第六版 | `implemented` | 继续作为形式无关交付 | 新保留集上的观点、视角与证据边界 |
| 表现形式选择 | 第四版方法审计 | `contract + bounded runtime implemented; orchestration pending` | 薄 `FormatDecision` 绑定精确 MessagePlan 与 BaseDraft，不改写选题或正文 | 项目运行接线、真实模型资源匹配与素材方案 |
| 编剧与成稿方法 | 第四版 Skill | `reviewed` | 只在选定叙事形式时加载小方法 | 非叙事内容不被强制编故事 |
| MediaKit 制作 | MediaKit CLI 与旧版可靠性证据 | `local foundation + exact approval + trusted I/O implemented; production pending` | 经统一路由执行已批准制作任务 | 本地编辑产物、批准入口、可核验云费用上限与首个真实云能力 |
| 发布前预演 | 第四版旧表与 `ip-content-calibration` | `reviewed; old schema retired` | 只吸收不可变预测和反事实方法 | 预测绑定精确成稿和媒体哈希 |
| 审批与发布状态机 | 第四版发布可靠性代码 | `reviewed` | 薄迁移幂等、恢复和未知对账 | 错账号、审批过期、内容变更、崩溃与重放 |
| 发布回执 | 第四版 repository/API | `reviewed; old implementation exists` | 重写最小不可变回执，不迁旧领域包 | 第一方作品 ID、公开链接和未知结果 |
| 指标快照 | 第四版 `platform_metrics` | `reviewed` | 确定性采集和聚合 | 时间窗口、来源、覆盖和缺失值 |
| 复盘与学习 | 第四版旧表、Skill 与全局方法 | `reviewed; old schema retired` | 重写为 `LearningClaim` 候选，禁止自动改 Skill | 预演对实绩、反例与修改原因 |
| 商业路径与变现 | 第四版方法审计 | `reviewed; deferred` | 项目级独立判断，不进语义或内容地图 | 内容信任、行动触发、承接与实际业务结果 |
| 调度与恢复 | DeerFlow 宿主运行时 | `implemented by host` | 复用正常 run lifecycle 与 scheduler | 非交互任务、重启与租约冲突 |

## DeerFlow 原生能力利用矩阵

| DeerFlow 能力 | 在孵化系统中的职责 | 接入时点 | 不应承担 |
| --- | --- | --- | --- |
| Lead Agent | 理解用户当前目标、选择高层能力、最终收敛并对用户负责 | 已使用 | 自己记住全部业务事实或绕过审批 |
| LangGraph/checkpoint | 交互运行、中断恢复、状态转移与重放 | W01 起 | 代替项目、回执和指标数据库 |
| 受控内部工作者 | 业务语义与词义世界首轮并发；证据阅读、候选与收敛等紧耹合结构化分工 | 已使用；首轮并发离线验收 | 变成可修改状态的自由 Agent |
| `task` 子 Agent | 可并行的大样本对标研究、独立反证和长报告 | W02/W06 | 固定每次启动的子 Agent 阵容 |
| MCP 持久会话 | 抖音、浏览器和后续平台连接器 | W02/W05 | 将低层 API 平铺给 Lead |
| `tool_search` | 延迟装载 MCP Schema，只提升当前需要的领域能力 | W02 启用验收 | 概率猜测权限或未审阅 Child |
| Skills 延迟发现 | 按需加载对标、表现形式、成稿和复盘方法 | W02/W03/W06 | 孵化总脑、固定流程或自动改写自身 |
| Memory | 用户偏好、显式纠错与长期交互习惯 | W01 分类策略 | 项目事实、账号令牌、审批、回执、指标或跨用户案例库 |
| Summarization | 长对话压缩和 Skill 引用持久提醒 | 已使用；W01 项目重水化已接线 | 在压缩摘要中维护唯一业务真相 |
| Sandbox/uploads | 用户素材隔离、广义文档读取、MediaKit 输入输出和中间工件 | W02/W04 | 无所有权的跨用户文件路径 |
| Vision | 关键帧、素材和成片人机质检 | W02/W04 | 将整账号视频原文全部塞入 Lead 上下文 |
| Tool output budget | 大账号包、MediaKit 回执和平台原始结果外部化，只投影摘要 | W02 扩展 | 无限截断导致来源、哈希或限制丢失 |
| Durable MCP tasks | 长耗时平台或云媒体任务的租约、轮询、重启恢复与快照 | W04/W05 | 在 Agent 循环内持续轮询远程任务 |
| Scheduler | 定时发布、指标回收、未知对账和定期复盘 | W05/W06 | 另建一套背景 Agent 运行时 |
| Run events/SSE/StreamBridge | 子任务、媒体、发布和复盘的可见进度、恢复与成本观测 | W02 起 | 将大原始工件作为 SSE 消息传输 |
| Authorization/guardrails | 账号、路由、工具和不可逆操作授权 | W01/W05 | 基于内容评分拦截创作 |
| Tool progress/loop detection | 发现重复搜索、无新信息调用和不可恢复配置问题 | W02 起 | 将正常多路取证误判为死循环 |
| Circuit breaker/LLM concurrency | 供应商故障降级、并发和 Token/成本保护 | Lead 已有；结构化工作者固定两路，进程级共用保护待压测 | 用重试风暴填补证据缺失 |
| Plan/Todo | 长任务的用户可见执行计划与进度 | W02 起按需 | 固化所有用户的业务阶段 |

矩阵的原则是“把 DeerFlow 原生能力用到它擅长的边界”，不是追求一次请求同时触发所有功能。

## 实施工作包

### W01 共享产物脊柱

状态：`implemented; server project selection, hydration, and content-run lineage verified; frontend selector deferred to W07`

目标：在不修改 Lead 核心提示词的前提下，建立项目、账号、产物包装、父子谱系、内容哈希和
证据角色的最小合同。

先写的失败测试：

- 两个用户的同名项目和同平台账号不能串联。
- 父产物不存在、属于另一用户或哈希不匹配时不能建立谱系。
- `topic_evidence`、`benchmark_evidence`、`owned_account_observation` 和 `published_outcome`
  不能互换。
- 用户可以从任意业务产物进入，不被上游空值硬拦截。

退出条件：合同、内存仓储验证和数据库迁移都通过；未向 Lead 暴露低层表和密钥。

### W02 读取与证据中心

状态：`in progress; Douyin MCP topic lineage, MediaKit local metadata lineage, and isolated cloud lifecycle implemented; live platform and cloud media acceptance pending`

目标：将抖音公开搜索、对标账号、自有账号、受众和 MediaKit 感知输出统一投影为有角色的
`EvidenceSnapshot`，但保持采集路径和权限语义不同。

实施顺序：

1. 抖音 v2 公共视频搜索按目的进入 `topic_evidence` 或 `benchmark_account_candidate`。
2. 用官方账号能力或审阅后的官方页面连接器补齐稳定账号身份、作者一致多作品清单和覆盖回执。
3. 迁移 MediaKit 感知回执，再接窄语义提取与确定性跨视频聚合。
4. 最后接自有账号授权数据和受众快照。

退出条件：Lead 只看见有界证据包；原始页面、Cookie、Token、临时 URL 和本地路径不越界。

2026-08-16 第一切片回执：新增通用 `EvidenceSnapshot`、覆盖回执、观察来源类型和固定字节预算
Lead 投影；抖音 `search.video_search` 的 DomainRouter 回执经白名单适配后可封存为
`topic_evidence`。投影只含快照/路由哈希、覆盖、限制和预算内代表项，并显示省略数量；完整证据留在
业务台账。当前适配器尚未由生产 Tool 自动写入选中项目，W02 继续进行。证据见
`evidence/douyin-topic-evidence-a39-2026-08-16.md`。

2026-08-16 第二切片回执：完成第五版 E15 逐文件审计，在第六版重写平台无关
`BenchmarkSnapshot`。快照将稳定外部账号 ID 与最多 `24` 条作者一致作品绑定，保留请求、
返回、排除、`has_more` 和采样限制，并封存为项目级 `benchmark_evidence`。Lead 投影只含有界
主页/作品观察和哈希，不输出账号定位、受众、成功原因或可复制公式。抖音账号链接连接器
尚未注册或真实入库验收。审计见 `audits/A40-fifth-version-e15-benchmark-snapshot.md`，回执见
`evidence/benchmark-snapshot-a40-2026-08-16.md`。

2026-08-16 第三切片回执：官方文档复核发现视频搜索已从旧 `v1`/`aweme.dy.video_search`
迁移到 `v2`/`aweme.dy.video_search_v2`。运行时合同、权限清单和薄适配器已经同步；调用参数新增
本地 `purpose`，但不会发送给平台。`topic_research` 保持选题证据，`benchmark_discovery` 只生成
对标账号候选证据。当前第六版本地尚未配置 Client Key/Secret，真实探测在发出网络请求前以
`auth_not_configured` 失败，因此代码状态为 `implemented`，不冒充 `verified`。详见
`audits/A41-douyin-official-first-evidence-routing.md` 与
`evidence/douyin-video-search-v2-a41-2026-08-16.md`。

2026-08-17 第四切片回执：现有 DomainRouter 之上新增薄的对标候选聚合层。它使用
同一 Manifest 跨页调用官方视频搜索，按 Unicode 归一后的作者显示名精确筛选、作品 ID
去重，并记录排除、重复、跨页和停止回执。最多 24 条的完整候选快照可幂等封存到
现有项目台账，Lead 仍只看固定字节预算投影。`open_id` 只作为授权查看者上下文，
不写入产物，也不冒充目标账号身份。星图与百应延期到出现明确字段缺口之后。详见
`audits/A42-douyin-public-benchmark-candidate-aggregation.md` 与
`evidence/douyin-benchmark-candidate-a42-2026-08-17.md`。

2026-08-17 第五切片回执：将 A42 聚合器注册为单个高层 Lead 工具
`collect_douyin_benchmark_candidate`。模型只提供搜索语、目标作者显示名和最大作品数；
认证用户、会话、运行和可选孵化项目由服务端注入。无项目不阻断只读证据；
有项目时先校验认证所有权，再请求平台和封存证据。写入失败不丢弃已取得证据，
且所有异常都以固定脱敏消息返回。本机真实抖音凭据和前端项目选择器仍待验收。
详见 `audits/A43-douyin-benchmark-lead-tool.md` 与
`evidence/douyin-benchmark-lead-tool-a43-2026-08-17.md`。

2026-08-17 第六切片回执：修复内容地图的证据洗标漏洞。内容理解来源
只允许 `user_material | topic_evidence`；抖音研究回执必须显式为
`topic_evidence`，任何搜索源显式声明的对标回执都不再被重新包装。
同时新增 MediaKit 的薄输入边界：
平台页先经解析，只有确认为 `video/*` 的临时直链或现有本地文件才可进入
动态 Schema Router；台账只留定位符哈希。本机 `mediakit-cli 0.2.0` Schema 预备调用
已通过，实际解析、云端执行和恢复仍待接通。详见
`audits/A44-evidence-isolation-and-mediakit-source-boundary.md` 与
`evidence/evidence-isolation-mediakit-a44-2026-08-17.md`。

2026-08-17 第七切片回执：内容纵切不再读取未启用的旧 `douyin_video_search` 直连配置，而是从
当前 DeerFlow 运行时选择带 MCP 标记的 `douyin_search`，执行
`Manifest discovery -> video_search(topic_research)`。最终阅读实际采用的官方 URL 才会触发
`evidence_snapshot -> content_reading` 父级，未采用结果和对标角色会被丢弃。聚焦回归
`51 passed`，后端全量 `11764 passed, 76 skipped`。当前忽略配置只保存 `$DOUYIN_*` 引用，
Gateway 环境中的 Key、Secret 和 Device ID
均为空，所以真实 Manifest 正确返回 `auth_not_configured` 且没有发送搜索请求。详见
`audits/A48-douyin-mcp-topic-evidence-lineage.md`。

### W03 孵化与单条内容产物谱系

状态：`in progress; bounded judgment runtime and format-decision contract implemented; orchestration and production wiring pending`

目标：将现有 `ContentWorldView -> TopicBrief -> MessagePlan -> BaseDraft` 绑定到项目与
地图版本，然后增加薄 `FormatDecision` 与 `DraftVersion`。

退出条件：

- 内容地图不因热点、表现形式、发布或复盘被静默改写。
- 同一 `TopicBrief` 可以产生不同表现形式，但事情、观点和证据边界保持一致。
- 非叙事选题不调用编剧方法。
- 成稿不擅自补造素材、客户案例、数量、周期、成功率或预算。

2026-08-17 第一切片回执：一次内容纵切现在可自动封存
`content_reading + content_world -> topic_brief -> message_plan -> draft_version`。身份只从线程绑定后
注入的 `ToolRuntime.context` 取得；没有项目时回答仍可用，落盘失败也不会吞掉内容。黄金礼品真实
运行已经迁移到“礼与关系秩序”并留下五类 SQLite 产物，但单次耗时约 6 分 44 秒、70,323 Token，
且二手资料支撑的草稿仍有具体化风险。W03 因此没有完成，下一切片需做确认版本复用、事实边界和
`FormatDecision`，详见 `audits/A47-content-run-artifact-lineage.md`。

2026-08-17 第二切片回执：新增可不完整的 `IncubationBrief` 与版本化 `IncubationJudgment`。用户事实、
授权观察和未知与定位、受众、人设、账号级表现形式、变现假设保持分层；判断强制绑定 Brief、冻结地图
和实际引用证据。当前仅完成领域合同与封存，运行时生成、用户审阅、选题引用和单条
`FormatDecision` 仍待实现。详见 `audits/A60-incubation-brief-and-judgment-lineage.md`。

2026-08-17 第三切片回执：内容工具明确区分长期定位与单条可拍选题，普通起号默认继续到选题和基础
文案。用户题眼只能以原话逐字线索进入研究，命名候选绑定冻结地图的精确路径，最终 TopicBrief 保留
全部中间节点；无证据或错路线时明确弃权，不再静默换题或把地图冒充成品。聚焦回归 `90 passed`，
真实模型验收与后续 `FormatDecision` 仍待完成。详见
`audits/A61-shootable-topic-goal-and-exact-map-path.md`。

2026-08-17 第四切片回执：新增薄 `FormatDecision`，精确绑定 MessagePlan 的受保护内容与证据边界
哈希，并可引用同项目孵化判断和用户素材证据。它只选择本条呈现形式，不能改写选题、加入平台销售发布或
固定数量；资源未知允许 provisional，非叙事形式不能携带编剧提示。联合回归 `39 passed`。真实模型
生成、用户确认与素材方案仍待接线。详见 `audits/A62-format-decision-lineage.md`。

2026-08-17 第五切片回执：孵化判断增加注入式结构化模型运行时，严格绑定 Brief、冻结地图和可选
对标/受众父产物。完整证据不进模型，统一使用现有有界投影，整个输入限制为 16,000 UTF-8 字节；
错误产物类型、角色、项目或模型输出均不产生半份判断。联合回归 `14 passed`。Brief 构造、真实模型、
项目证据读取与回答接线仍待完成。详见 `audits/A63-incubation-judgment-runtime.md`。

2026-08-17 第六切片回执：修正 A62 与 ADR-018 的父级漂移。`FormatDecision` 现在同时绑定精确
MessagePlan 和由它直接派生的 BaseDraft，并在模型调用前校验项目、类型、业务 ID、阶段和谱系；薄运行器
输入限制为 32,000 UTF-8 字节，只允许 `user_material` 媒体观察支撑“已有素材”。聚焦回归
`41 passed`。项目主链接线、形式适配稿和素材方案仍待完成。详见
`audits/A64-format-decision-runtime-and-base-draft-binding.md`。

### W04 MediaKit 制作路由

目标：以动态 Schema 建立统一媒体能力路由，将已批准的制作请求执行为内容寻址的
`MediaArtifact`。

前置合同已实现：`MediaKitCapabilityRouter` 动态读取版本和 Schema，
`EphemeralMediaSource` 与 `MediaSourceReceipt` 分离执行定位符和持久回执。
本地执行、模拟云生命周期、精确批准、私有来源和视频结果物化已经接通，但这不等于 W04 已具备生产制作能力；
生产任务接线、非视频结果策略和真实云回执仍待验收；供应商本身不提供单任务费用硬上限。

2026-08-17 第一执行切片：本地文件现可通过动态能力路由真实执行
`probe-video-metadata`。执行前后双哈希防止输入替换，CLI 原始 JSON 先经 Output Schema 再经
窄视频元信息合同，最终封存只含版本、Schema、请求、源内容和输出哈希。媒体观察自动继承
`MediaSourceReceipt` 的证据角色，路径与临时 URL 不入账。审计同时确认现有 DeerFlow 租约轮询
可以复用，但 MediaKit 没有取消能力，不能照搬“先提交后落库”的 MCP 提交流程；云任务必须先补
持久提交意图。详见 `audits/A49-mediakit-local-execution-and-cloud-recovery.md`。

2026-08-17 第二执行切片：通用长任务运行时已增加 `submission_pending` 和 `enqueue()`。
提交意图先落库，后台租约工作进程再以稳定本地任务 ID 调用远端并原子绑定句柄；绑定失败不取消
远端，而是在租约过期后使用同一幂等键恢复。`0013_mcp_task_submission_intent` 已覆盖旧数据库升级。
本切片没有注册 MediaKit 云驱动；下一步先用模拟 CLI 验证提交、查询、恢复、授权和输出质检，再决定
是否执行真实付费验收。详见 `audits/A50-durable-task-submission-intent.md`。

2026-08-17 第三执行切片：新增隔离的 `MediaKitCloudDriver`，严格限定无凭据持久参数，先校验本地
版本和 Schema，再校验云处理与费用授权、解析短命媒体地址，并将持久本地任务 ID 用作 `client_token`。后台每次只调用一次
`query-task`，兼容并归一 CLI Schema 与归档源码中不一致的状态枚举；完成回执必须经幂等物化器转成
内部 `artifact://` 引用和内容哈希。授权、来源解析、物化和恢复数据异常均使用固定脱敏错误。
模拟生命周期已经通过，但驱动未注册，来源解析器、下载质检和云费用验收仍未完成。
详见 `audits/A51-mediakit-cloud-driver-mocked-acceptance.md`。

2026-08-17 第四执行切片：新增两类 `ApprovalGrant` 和 `0014_incubation_approval_grants`。云处理
同意与费用上限共同绑定 owner、项目、素材内容哈希、能力参数、Schema、币种和金额形成的操作摘要，
再原子绑定唯一 MCP 本地任务；同任务可恢复，另一任务不能复用。授权器已经接入隔离云驱动，但没有
批准 API，预期素材哈希尚未与解析后的真实字节复核，供应商费用也没有可核验强制上限，因此仍不注册
或执行真实云能力。详见 `audits/A52-mediakit-exact-approval-ledger.md`。

2026-08-17 第五执行切片：新增 owner/project 隔离的私有内容寻址来源库，云驱动在批准前和
提交后核对实际字节；一旦已取得远端任务号，后校验失败也必须保留句柄供对账。能力级物化策略限定
输出字段、媒体类型和大小，下载经主机白名单、SSRF、哈希和 MediaKit 本地质检后只封存首份
`artifact://` 结果。已通过真实本地视频烟测，但未注册云驱动或产生费用。详见
`audits/A53-mediakit-trusted-io.md`。

2026-08-17 第六审计切片：对照本机 CLI、官方仓库 HEAD、最新提交/查询文档与视频工具计费页，
选择 `video/enhance-video` 作为首个真实云验收候选。它的终态明确包含视频 URL、时长和分辨率，
可复用 A53 视频物化边界；ASR、OCR 和场景切分的当前终态 Schema 仍只有含糊的 `local_path`，暂缓。
首轮候选限定合成视频、标准版、720P 及以下、30fps 及以下，当前计费公式估值为每输出分钟
`0.75 CNY`。供应商提交接口没有单任务金额硬上限，故本轮仍不注册、不上传、不调用；下一切片先把
价格证据、明确规格和费用报价绑定进预检合同。详见
`audits/A54-mediakit-first-cloud-capability.md`。

2026-08-17 第七执行切片：新增 `video/enhance-video` 专属离线预检。它以执行时动态 Schema 为
命令合同，只允许首轮审阅范围内的标准版、显式分辨率和帧率；价格表作为带来源、正文哈希、检查时间
和有效期的证据，按毫秒向上取整生成可复算估值。报价的价格证据摘要、报价摘要、估值和到期时间已
进入 `mediakit-cloud-operation-v2`、两类批准的授权上下文、持久任务恢复数据和私有结果回执。
报价到期或估值超过用户上限时，在素材解析、批准消费和云提交前失败。供应商仍没有单任务金额硬上限，
因此本切片保持驱动未注册，未上传或调用云能力。详见
`audits/A55-mediakit-enhance-video-preflight.md`。

2026-08-17 第八执行切片：将服务器生成的报价封存为项目内不可变
`mediakit_cloud_approval_request`。报价必须以用户授权素材的元信息观察为父级，客户端不能提交自造
操作摘要。Gateway 新增只读审阅和精确确认入口；确认报价摘要、币种或金额变化、报价过期、项目越权
或缺少“供应商无硬封顶”确认时均不签发。两类 `ApprovalGrant` 由同一数据库事务原子创建，确定性 ID
使双击和重试收敛到首个成功决定。接口不会排队、注册驱动或调用云端。详见
`audits/A56-mediakit-exact-approval-api.md`。

2026-08-17 第九执行切片：新增默认关闭的服务器报价生产入口。Gateway 只接受同 owner/project 下
已有的 `user_material` 元信息观察，追溯其精确来源回执；客户端不能提交费率、价格证据、来源定位符
或操作摘要。运营方价格 JSON 受大小、严格字段、来源哈希和有效期约束，服务在每次报价时重新读取
MediaKit 版本与 `enhance-video` Schema，漂移即失败。报价只封存可审阅对象，不创建长任务。批准凭证
改按精确操作摘要确定身份，使同一操作的多个报价产物也只会签发一对凭证。默认配置、Helm 示例和
配置版本已同步；前端素材选择、任务创建和真实云验收继续暂停。详见
`audits/A57-mediakit-server-quote-preparation.md`。

首批验收：

- 本地剪辑、字幕、裁剪、拼接、混音、合成和元信息。
- 云端 ASR、OCR、场景切分和增强能力的授权、费用、幂等与恢复。
- Schema 漂移、上传中断、异步任务重启、输出缺失、输出哈希和错误脱敏。

退出条件：MediaKit 不读孵化方法，不重选选题，不直接发布。

### W05 预演、审批与抖音发布

目标：对精确 `DraftVersion + MediaArtifact + PlatformAccount` 封存预演和审批，再通过抖音
OpenAPI 或受控浏览器发布，产生不可变 `PublicationReceipt`。

发布状态：

```text
draft -> prepared -> approved -> executing
-> succeeded / failed / unknown -> reconciled
```

退出条件：

- 内容、媒体、账号或审批有一项改变就必须重新确认。
- 页面跳转不等于发布成功；没有第一方作品 ID 或公开链接时进入 `unknown`。
- `unknown` 不自动重发，先对账。
- 幂等重放不产生第二条作品。

### W06 指标、受众与复盘学习

目标：从 `PublicationReceipt` 出发，按平台适用时间窗口采集 `MetricSnapshot` 和
`AudienceSnapshot`，对比预演形成 `Retrospective` 与 `LearningClaim`。

退出条件：

- 缺失指标不变成零，不同人群口径不混合。
- 观测相关性不写成平台或用户心理因果。
- 一次复盘不自动更新通用规则。
- `LearningClaim` 支持 `active / contested / superseded / retired`，且检索时同时显示支持样本与反例。

### W07 产品化与多平台扩展

在抖音闭环通过后，再实现项目、账号、证据、内容、素材、日历发布与增长复盘工作区，
并将平台合同扩展到小红书、视频号、快手、Bilibili 和 TikTok。

多平台枚举覆盖不等于平台支持。每个平台必须完成真实测试账号的“登录或授权、观察、准备、
用户确认、发布、第一方回执、指标回收”才可进入 `production`。

## 端到端验收场景

| ID | 场景 | 必须证明 |
| --- | --- | --- |
| E2E-01 | 用户说“我是做黄金礼品的” | 语义可进入“礼、人与人相处”的长期地图，不被发布或商品目录倒灌 |
| E2E-02 | 用户给一个抖音对标链接 | 账号身份、多作品、MediaKit 证据、覆盖和反例进入 `BenchmarkSnapshot` |
| E2E-03 | 从账号地图生成当日内容 | 热点或取证路径不改写内容根，输出具体可拍 `TopicBrief` 与 `MessagePlan` |
| E2E-04 | 将已批准成稿制作为视频 | MediaKit 回执、费用授权、恢复和输出哈希完整，并通过质检 |
| E2E-05 | 在抖音真实测试账号发布 | 审批绑定、幂等、崩溃恢复、第一方回执与 `unknown` 对账 |
| E2E-06 | 到指定观察窗口后复盘 | 实绩与预演精确绑定，缺失与反例保留，学习不自动改写规则 |
| E2E-07 | 两用户各自连接抖音账号 | 项目、令牌、素材、审批、回执、指标和学习结论全部隔离 |

## 横切测试矩阵

- 架构：禁止内容、媒体、平台或复盘模块修改 Lead 核心提示词、强制工具选择或覆盖模型结果。
- 所有权：两用户、多项目、同平台多账号、错账号、越权父产物与越权回执。
- 证据：角色不可互换、引用必须解析、大工件有界投影、原页面文本作为不可信证据。
- 模型：测试最终业务结果与证据边界，不要求固定工具轨迹、子 Agent 数量、提问轮数或脚本路线。
- MediaKit：Schema 漂移、本地/云端路由、云处理同意、费用、幂等、中断恢复、哈希、质检与错误脱敏。
- 平台：Manifest 漂移、权限、登录失效、租约冲突、幂等重放、执行崩溃、未知结果和人工对账。
- 学习：盲预演不可修改、指标时间窗口、反例、过时经验、候选规则状态和跨用户学习默认关闭。
- 密钥：本地未跟踪配置外不出现真值；文档、数据库、日志、截图、工具回执和测试夹具全部使用占位符。

## 首个开发切片

首个代码切片是 W01，不是继续改内容脑提示词。原因是后续每个模块都需要共享的所有权、产物谱系、
哈希和证据角色；没有这根脊柱，直接迁 MediaKit、发布或复盘只会再形成三套各自的真相。

W01 实施步骤：

1. 阅读 `backend/AGENTS.md` 中持久化与迁移约定，先写合同失败测试。
2. 新增小型 `deerflow.incubation` 领域包，只保存业务产物包装、所有权和谱系，不包含 Agent 提示词。
3. 实现内容寻址 ID 和父产物校验，用隔离 SQLite 运行同一 SQL 仓储完成快速合同测试。
4. 按第六版现有数据库规范增加最小持久化和迁移测试。
5. 只为现有 `ContentWorldView` 增加可选项目谱系适配；不同时改语义、选题或 Lead 路由。

W01 同时必须完成 Memory 与业务台账的分界测试：用户偏好和显式纠错可以进入 Memory，所有权、
内容版本、审批、回执、指标和学习状态必须从业务台账重建。对话压缩或线程切换不得改变这些状态。

2026-08-16 实施回执：已新增不可变合同、项目/账号/产物三表、`0012_incubation_ledger` 迁移、
所有权/敏感字段/证据角色/血缘/幂等校验，以及 `ContentWorldView` 的可选长期地图适配器。封存后
篡改 payload 会在事务前重新验签并拒绝。DeerFlow Memory 指南已明确排除项目版本、审批、发布回执、
指标和学习状态。计划中的独立内存仓储被同一 SQL 仓储的临时 SQLite 测试替代，避免维护第二套真相
实现。2026-08-17 又补齐 owner-scoped 项目 API、线程绑定和 `start_run` 服务端重水化：普通运行请求不能
直接注入项目 ID，绑定只能经所有权校验后的专用接口修改，重开线程时由台账重新注入。W01 服务端接线
至此完成；前端项目选择器归入 W07 产品化，不再阻塞 W02-W06。证据见
`evidence/incubation-ledger-a38-2026-08-16.md` 与
`evidence/incubation-project-runtime-a46-2026-08-17.md`。

下一验收断点仍是 W02 的官方 v2 真实回执，需要本地绑定三项抖音应用凭据；W04 的持久提交意图与
隔离云驱动、精确批准账本、受信来源与幂等物化已通过无费用验收。下一切片先对照实时能力 Schema、
输出类型和计费证据，只为一个明确 MediaKit 云能力登记策略；取得用户对精确费用上限的新批准后才能做真实
回执验收。不得用网页视觉采集伪装 W02 已通过，也不得在 Agent 循环内
长轮询云任务。
