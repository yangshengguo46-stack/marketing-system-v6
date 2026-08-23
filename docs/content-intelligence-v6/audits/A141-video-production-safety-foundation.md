---
id: A141
status: adopted
date: 2026-08-22
sources:
  - A75-mediakit-production-plan-local-execution.md
  - A50-durable-task-submission-intent.md
  - A140-account-direction-launch-plan-bridge.md
  - "/Users/yangyucheng/Documents/ChatGPT/第五版营销系统/skills/public/marketing-video-production/ (untracked worktree snapshot)"
  - "/Users/yangyucheng/Documents/ChatGPT/第五版营销系统/backend/packages/harness/deerflow/community/video_production/ (untracked worktree snapshot)"
  - "/Users/yangyucheng/Documents/第四版营销系统/docs/handoffs/VIDEO_PIPELINE_MIGRATION_HISTORY.md"
  - "/Users/yangyucheng/Documents/第四版营销系统/skills/public/video-pattern-learning/"
  - https://github.com/Shanyin-ai/shanyin-director-master/tree/30f0daecaf0754e08cf88ece83fabf3a2372a016
  - https://github.com/calesthio/OpenMontage
  - https://github.com/heygen-com/hyperframes
  - https://github.com/Vincentwei1021/video-shotcraft
  - https://github.com/FireRedTeam/FireRed-OpenStoryline
  - https://github.com/bytedance/Bernini
  - https://github.com/oxbshw/watch-skill
  - https://github.com/volcengine/mediakit-cli
  - https://github.com/remotion-dev/remotion/blob/main/LICENSE.md
  - https://github.com/harry0703/MoneyPrinterTurbo
  - https://github.com/OpenCut-app/OpenCut
  - https://github.com/Huanshere/VideoLingo
  - backend/packages/harness/deerflow/incubation/benchmark_video.py
  - backend/packages/harness/deerflow/incubation/ark_generation.py
  - backend/packages/harness/deerflow/community/ark_generation/client.py
  - backend/app/mcp_tasks/service.py
  - skills/public/marketing-video-production/SKILL.md
---

# A141 视频生产安全底座与项目原生 Skill

## 本轮目标

账号方向、具体选题、脚本和 `ProductionPlan` 已经属于第六版事实谱系，但“用户甩来对标视频 -> 拆解可迁移
结构 -> 用已有素材或火山生成补齐 -> 剪辑质检 -> 成片”的总入口仍缺失。第五版工作树里存在一套未合入
的原型，第四版存在素材搜索和视频模式方法，山音提供了镜头方法；它们不能以第二个总控、第二个计划 Schema
或第二本 JSON 台账直接搬回。

本轮采用现有第六版产物图，只建设一个不产生费用的安全底座：对标视频证据合同、Ark 文生视频单镜头内容寻址
请求合同、无默认执行器的 CLI 适配边界、最多提交一次的持久任务策略，以及一份项目原生视频生产 Skill。

## 采用的编排

```text
AccountDirectionVersion / optional AccountLaunchPlan
  -> evidence-backed TopicBrief -> MessagePlan -> BaseDraft
  -> explicit FormatDecision -> AdaptedDraft
  -> existing ProductionPlan
  -> benchmark/source evidence + asset routing
  -> validated content-addressed provider request or local-media operation
  -> durable task / private materialization / QC
  -> existing MediaArtifact
```

`marketing-video-production` 是下游路由知识，不拥有工件状态。山音的镜头目的、动作/反应、镜头组、
节奏变化和审阅表已按许可与边界缩成方法参考；`video-shotcraft` 是另一个 Apache-2.0 仓库，本轮只审计，未迁移其
模板、配方卡或捆绑素材。现有 `ProductionPlan` 仍是素材、动作和装配的唯一真相，Lead 仍是唯一对外
总脑。历史 `video-generation` Skill 已从项目示例配置和本机配置的默认发现中禁用，入口只保留迁移说明；其
脚本仍为兼容性文件，不能视为主机 Shell 层面的绝对执行禁令。第六版 Agent 的新视频请求只路由到项目原生
Skill，旧脚本不得代表用户执行。

## 对标视频证据合同

新增单视频 `benchmark_video_evidence`，只接受同项目、同证据角色且精确相连的
`media_source_receipt + media_observation`。它同时绑定来源、用户提供的权利声明或引用、定位符哈希、源内容哈希、两个父工件
ID 与内容哈希，并分开保存：

1. 机器观察：必须引用真实存在于精确媒体观察父级中的字段路径；
2. 编辑解释：显式为解释或创意假设，必须引用机器观察并保留不确定性；
3. 可迁移模式：同时引用观察和解释，只允许迁移抽象结构；
4. 不可迁移特征：至少明确创作者身份和品牌装潢；
5. 未知与限制。

合同把账号方向权固定为 `none`，把效果因果固定为 `not_established`，把复刻范围固定为
`abstract_structure_only`。Lead 投影最小预算 4 KB，按层轮转纳入条目并报告省略数量。当前没有注册
MediaKit ASR/OCR/镜头切分工具，也没有拿元数据冒充内容理解。权利字段是未经核验的用户声明/引用，不是授权、许可或法务审核回执。
对应边界值为 `rights_basis_status = declared_reference_not_verified`。

## Ark 文生视频 V1

首个窄纵切只允许一条 ready `ProductionPlan`，其中恰好包含：

- 一个 `to_create` 视频资产；
- 一个只绑定该资产的 `media_generation` 动作；
- 一个只绑定该资产的装配步骤；
- 精确 `AdaptedDraft + FormatDecision` 父级；
- 零用户参考素材。

当前 `prepare_ark_text_to_video_operation` 返回的只是一个经 Pydantic 验证、带确定性哈希的内容寻址请求值。它绑定精确计划父级、
动作/资产/装配 ID、提示、显式模型、画幅、分辨率、时长和封闭参数白名单；它尚未写入 `ArtifactEnvelope`、数据库或持久任务，也没有注册为 Tool/驱动。
合同拒绝网络/对象存储 URL、本机路径、引用文件、凭据及高熵秘密候选、callback、额外请求体、force、save-to 和任意扩展参数。V1 不等于未来只能
文生视频，而是先把无引用、无多镜头、无自由透传的最小风险面冻结。

`ArkCliTextToVideoClient` 只能注入 runner，没有默认 subprocess 执行器，也未注册为 Tool 或持久任务驱动。
模拟合同按 ArkCLI 顺序执行认证、视频资源解析、公共模型 `supported_params` 校验、一次异步 `+gen`，以及
独立 `gen get` 轮询。它只保留稳定任务 ID、选中模型、归一状态和原始响应哈希；临时 URL、本机路径、
stdout、stderr 与凭据不进入返回合同或异常。

本机只读检查确认 `arkcli 1.0.11` 与 `mediakit-cli 0.2.0` 可发现；本轮没有调用 `arkcli +gen`、没有调用
MediaKit 云能力，也没有产生供应商费用。

## 最多提交一次的持久任务

现有 MediaKit 提交使用可重试的持久 `client_token`，默认任务策略继续为 `idempotent_retry`。ArkCLI 当前
没有经过本项目审计的生成幂等键，不能复用这一假设。因此 MCP 长任务新增：

- `submission_policy = idempotent_retry | at_most_once`；
- `submission_started_at` 在进入供应商代码前持久化；
- `submission_unknown` 作为终态、注意态和不可领取状态；
- at-most-once 调用异常、进程恢复或远端已成功但本地绑定失败后不再提交；
- 未知态清除提交参数，保留对账提示。

迁移 `0016_mcp_task_submission_policy` 给旧任务回填 `idempotent_retry`，增加字段与检查约束；downgrade 会先把
仍为 `submission_pending` 的 `at_most_once` 行保守封成 `submission_unknown`，再移除新字段，避免旧 worker 重提。
这只提供通用安全原语；Ark 尚未接到该服务，不能把两个模块存在说成付费纵切已经闭环。

## 第四/第五版与开源方法的取舍

### GitHub 官方动态快照与编排选择

2026-08-22T05:58:02Z 直接读取 GitHub 官方 REST `GET /repos/{owner}/{repo}`。下表的 star 是该时点动态值；
“生命周期累计速度”只是 `当前 stars / 自 created_at 起天数` 的粗略关注度线索。GitHub 仓库元数据不提供历史
star 时间序列，因此不把该值写成“最近 7/30 天正在加速”，也不用 star 代替许可、安全、稳定性和业务验收。

| 官方仓库 | 许可 / 快照 | 生命周期累计速度 | 第六版取舍 |
| --- | --- | ---: | --- |
| [OpenMontage](https://github.com/calesthio/OpenMontage) | AGPL-3.0；49,335★；创建 2026-03-29；最近 push 2026-08-18 | 约 339★/天 | 最值得洁净重写开放素材 connector、生成前 sample/费用门、contact-sheet 审批和 QA；不搬 12 条 pipeline、100+ tools、自有 stage skills/provider registry/项目状态，否则会形成第二总控，并引入 AGPL 分发/服务边界。 |
| [HyperFrames](https://github.com/heygen-com/hyperframes) | Apache-2.0；42,005★；创建 2026-03-10；最近 push 2026-08-22 | 约 254★/天 | 候选确定性 HTML/GSAP 组版渲染器；只消费已封存 renderer spec/计划并返回 RenderReceipt，不采用其 intent interview、Media OS 或项目记忆做上层总控。 |
| [video-shotcraft](https://github.com/Vincentwei1021/video-shotcraft) | Apache-2.0；5,992★；创建 2026-07-19；最近 push 2026-08-21 | 约 178★/天 | 是“最新冒出”的明确样本；可只研究 shot cards、motion recipes、storyboard/QA rubric 和模板测试。不让它拥有 storyboard 状态；Remotion 特殊许可及捆绑素材还须逐项审核。 |
| [FireRed-OpenStoryline](https://github.com/FireRedTeam/FireRed-OpenStoryline) | Apache-2.0；3,242★；创建 2026-02-07；最近 push 2026-07-31 | 约 16.6★/天 | 只作“意图→可解释编辑操作”的离线研究；若后续采用，只能做输入既有 timeline/plan、输出 typed edit ops 的 compiler。 |
| [Bernini](https://github.com/bytedance/Bernini) | Apache-2.0；1,273★；创建 2026-05-29；最近 push 2026-08-13 | 约 15.0★/天 | 只作本地生成/编辑 backend 的离线研究；不引入它的 MLLM semantic planner 重新判断选题或镜头。 |
| [watch-skill](https://github.com/oxbshw/watch-skill) | MIT；304★；创建 2026-07-05；最近 push 2026-08-21 | 约 6.4★/天 | 可候选补“对标视频→带时间戳可搜证据”和成片 self-verification；只返 observations/coverage/QC receipt，不写方向。 |
| [Shanyin Director Master](https://github.com/Shanyin-ai/shanyin-director-master) | MIT；447★；创建 2026-04-05；最近 push 2026-05-11 | 约 3.2★/天 | 已只迁移方法结构并冻结提交/许可；五月后无 push，不声称近期加速，也不引入 Director Agent。 |
| [volcengine/mediakit-cli](https://github.com/volcengine/mediakit-cli) | MIT；189★；创建 2026-06-03；最近 push 2026-07-16 | 约 2.4★/天 | 是火山官方公开仓，继续作证据/原子媒体能力层。README 明说默认 cloud-first，所以注册必须机械化显式 `--local` 或 `--cloud`；云端仍走报价、批准、持久任务与私有物化。 |

成熟/高关注候选仍需分层：[Remotion](https://github.com/remotion-dev/remotion) 快照为 57,019★，但官方是自定义
Remotion License，只对个人、不超过 3 人的营利组织、非营利组织与非商业评估等给予免费资格，其他营利组织需 Company License；
它不能被粗略写成 OSI 开源依赖。[MoneyPrinterTurbo](https://github.com/harry0703/MoneyPrinterTurbo) 114,102★（MIT）、
[OpenCut](https://github.com/OpenCut-app/OpenCut) 85,431★（MIT）和 [VideoLingo](https://github.com/Huanshere/VideoLingo)
18,224★（Apache-2.0）只分别用于 adapter/端到端 smoke、未来人工精修 UI、字幕翻译/对齐/配音候选，不进主编排。
这三个老仓与 FFmpeg 都没有本轮可用的官方历史 star 序列，所以不声称“最近升星快”。

因此编排结论仍是：OpenMontage、MoneyPrinterTurbo、FireRed 只进方法/离线对比库；MediaKit/watch 只进证据与 QC；
山音/video-shotcraft 只进镜头方法与审阅投影；Ark/未来 Bernini 只进受批准的资产生成 lane；HyperFrames 或 Remotion
二选一做 renderer；FFmpeg + MediaKit/watch 只进 QA/DeliveryReceipt。方向、选题、脚本、计划与发布学习仍由第六版工件图拥有。

### 冻结方法（2026-08-22T13:29:44+08:00）

本节的“状态清单哈希”是对
`git status --porcelain=v1 --untracked-files=all | LC_ALL=C sort` 的字节做 SHA-256；“目录 manifest”是对按路径排序的
`<file_sha256>  <repo-relative-path>` 清单再做 SHA-256。前者只冻结 Git 状态与路径，后者才冻结目标文件字节；两者都不把未追踪文件冒充为提交内容。

### 第四版：受追踪的历史证据

- 仓库绝对路径：`/Users/yangyucheng/Documents/第四版营销系统`。快照 HEAD 为
  `58f4e0c900a2dc589fe4a23bdebbe8e3211b67b7`（`2026-08-06T02:29:30+08:00`）。全仓工作树是脏的，状态清单哈希为
  `5697d53fd39599d375bc70042b0b6de886f79ad07a9b068d632459b386b47229`；脏改动位于其他路径，下述两个目标路径的限定 `git status` 为空。
- 直接历史证据是
  `/Users/yangyucheng/Documents/第四版营销系统/docs/handoffs/VIDEO_PIPELINE_MIGRATION_HISTORY.md`；它受 Git 追踪，最后变更提交为
  `9a18fa1d7454c787f8495aff325098b837a951a9`，文件 SHA-256 为
  `87212278bb0c36f0195295ddbe9410c6c16165cf00917176fca67ef78d2eaa90`。该文档首段说明其状态只描述当时本地合同/测试/样例，不是当前客户可达性声明；
  V-006 的状态是 `local inspection done`，且验收栏明确把 owned/open remote search and acquisition 留为未完成项。这是“第四版未证明全网找素材成功”的直接证据。
- 模式学习目录是
  `/Users/yangyucheng/Documents/第四版营销系统/skills/public/video-pattern-learning/`；四个文件均受追踪，该目录最后变更提交为
  `ba03d9ba0513934863992d8ac64b13703a7ab2e3`，manifest 哈希为
  `b16a1dfa059c599a6d95ca1762f1b39efc0d3bb313bf50221d80b2d4a9ac6646`。文件 SHA-256 为：

| 第四版相对路径 | SHA-256 |
| --- | --- |
| `skills/public/video-pattern-learning/SKILL.md` | `b30a2f52afedeceb02854de7589d15a1fe422cbac51e42be3d5bb68ad85e00b1` |
| `skills/public/video-pattern-learning/agents/openai.yaml` | `9beaccf1b7abc05f8e697572b67d043b413f05813acbc7b0a2b3d7987bb1c2eb` |
| `skills/public/video-pattern-learning/references/parser-routing.md` | `f1cd25a7e7c8b579c729908dea88a5b6a9c96dbb2da03d28feb7007546593088` |
| `skills/public/video-pattern-learning/references/pattern-contract.md` | `1f904904997ba263d89e738c388a9f0a11c4ed5f8930e6fa46e004e8352836f7` |

这些证据只证明本地历史中存在视频模式学习方法和素材搜索的本地检查方向；它们不证明全网发现、远程采集、精确可用区间或权利许可已完成。

### 第五版：未追踪原型快照

- 仓库绝对路径：`/Users/yangyucheng/Documents/ChatGPT/第五版营销系统`。快照 HEAD 为
  `3ee135f787354b36b85edc62404684fda37acdc0`（`2026-08-14T22:36:34+08:00`），但它不包含下述原型。全仓工作树是脏的，状态清单哈希为
  `852b01726564deb682c623c9449dcc0c7991e0c72f0658add32298b17e845fde`。
- 被引用目录是
  `/Users/yangyucheng/Documents/ChatGPT/第五版营销系统/skills/public/marketing-video-production/` 与
  `/Users/yangyucheng/Documents/ChatGPT/第五版营销系统/backend/packages/harness/deerflow/community/video_production/`。限定 `git status` 对下列 15 个源文件全部返回 `??`，
  `git ls-files` 返回零个目标文件；因此这是未追踪的本地工作树快照，不是 HEAD `3ee135f…` 或任何提交态。
- 下列 15 个源文件的 manifest 哈希为
  `bd6462726ba4925642c7b738083afa1fc27293e74af4b879b5625540cf94ed3b`。目录中还存在 8 个生成的 `__pycache__/*.pyc`，它们未被当作迁移输入；若把这些缓存也纳入目录快照，23 文件的 manifest 哈希为
  `bfed825ab38ae5e6259bb29789860370a49dea17bd3df3a4957a31d1830073f2`。

| 第五版相对路径（全部未追踪） | SHA-256 |
| --- | --- |
| `backend/packages/harness/deerflow/community/video_production/__init__.py` | `21dffe1b58618daf74759f03ed7526e829232225144bc32a5c03642b390e4f27` |
| `backend/packages/harness/deerflow/community/video_production/ark.py` | `c3bcabf6138a3f66b3af09e7ff03825762a53eae07e5bb58dec5171842af58c6` |
| `backend/packages/harness/deerflow/community/video_production/content_lock.py` | `afcbe94af309704fbfc7848fff3a6e57a2d1cdb757395955d41ee6cb226da9b1` |
| `backend/packages/harness/deerflow/community/video_production/contracts.py` | `284b417d56c46089f9c5328b77f4d265ab796a45f75fffa247006a1ca9aa8ec0` |
| `backend/packages/harness/deerflow/community/video_production/ledger.py` | `651d2b5080a9e9590465adc0d6fff0c848cdcc55499d01b8f2e5642139c53836` |
| `backend/packages/harness/deerflow/community/video_production/mediakit.py` | `dc061ae2b0b6da13115fd07dfa907ad3a9fc51a24b33f1fa3a953d89e114be29` |
| `backend/packages/harness/deerflow/community/video_production/service.py` | `351c1ce411330ccefbaa5fd372ee81ff044b9a556583ce62ac536e5b544998d9` |
| `backend/packages/harness/deerflow/community/video_production/tools.py` | `c5af8ee6d7e8022109e66f88ea2f5e714febd0d24f95257a32f5653e73d2d689` |
| `skills/public/marketing-video-production/SKILL.md` | `3800ae7703e2ca7eb09ea46b6b8734c0ab2fa110f792ea20a769581274d3af9c` |
| `skills/public/marketing-video-production/references/director-craft.md` | `f259769b85cbdaf8096990a4ea5c56786475784a463884007f6a22a85a8d9097` |
| `skills/public/marketing-video-production/references/pipeline.md` | `1d252a4ef4814506a92eb99bc7eb17b94bdfc3599ba4d50d424d9afe45670e0c` |
| `skills/public/marketing-video-production/references/plan-contract.md` | `9088ba8b6b43202adbf95b780cdeabcd406b85caf7d8a025ab705cd539db85` |
| `skills/public/marketing-video-production/references/provider-routing.md` | `7ea57d90c1442dac1bd355ee8e2e596ca0ef040a2e7f9dd80d3efcb0636dd1f8` |
| `skills/public/marketing-video-production/references/roadmap.md` | `5cc744515257cf88b1e5b3dc2b4953851b52aabdc9efea69a32915fe55566f93` |
| `skills/public/marketing-video-production/references/third-party-notice-shanyin.md` | `1f37d3fb60e511987a16f78552a0e00d877ef1abc4423b5edf9b5c52bc9e0f61` |

这组哈希只让第五版原型可审计；不给它提交身份、不证明其已合入产品，也不会把其 JSON 台账、`ProductionPlan`、付费工具或“电影化”总模式迁入第六版。

### 山音许可冻结

- 山音来源以 `main` 在获取时的精确 HEAD
  `30f0daecaf0754e08cf88ece83fabf3a2372a016` 冻结，获取时间为 `2026-08-22T04:43:07Z`。上游
  `LICENSE` 是 MIT，1,064 原始字节的 SHA-256 为
  `efc510fcf834152b44be1f2bba1b2f3b49525040ff2e5aee1184cae29e10e3fa`。本项目只迁移叙事目的/删除
  测试、镜头组、动作/反应、节奏变化和九字段审阅的方法结构，精确文件与本地适配映射见
  [`third-party-notice-shanyin.md`](../../../skills/public/marketing-video-production/references/third-party-notice-shanyin.md)。

- 第四版素材搜索只证明本地范围与权利检查方向，未完成全网发现和可用素材采集。本轮只保留后续路线：发现
  与权利许可分开；浏览器、直链和下载器都不是版权判断器。
- 山音的镜头目的测试、镜头组、动作/反应和九列审阅思想按 MIT 许可归入 Skill 参考；它不拥有状态、Provider
  路由或内容判断，也不把创作者名称变成模仿提示。
- Remotion、HyperFrames、FFmpeg 等继续只是后续 renderer/finishing 选择，不成为新编排器。

## 明确未做

- 没有 Gateway 视频生产入口、前端任务卡、Ark 驱动注册、报价与 `ApprovalGrant` 原子绑定。
- 没有冻结 active profile 的 account/tenant/project/region、Endpoint 底层模型和价格解析回执；没有完成预检与
  费用标记的拆分、覆盖付费调用的租约/续租、双 worker 超时 fencing、结构化持久错误或 shell-free runner 审计。
- 没有真实 Ark 任务、付费回执、结果下载、私有物化或 `MediaArtifact` 封存。
- 没有 Ark 生图、图生视频、首尾帧、参考视频/音频、多镜头连续性或并行生成。
- 没有自动 ASR、OCR、场景切分、时间线装配、字幕、配音、音乐、响度与平台多规格交付。
- 没有恢复第四版全网素材采集，也没有把搜索 URL 标成可用素材。
- 没有发布、指标回收或从单条对标/生成结果自动修订账号方向。

## 验证回执

最终无 live 纵切将 A140 账号桥、对标/Ark 安全合同、MediaKit 已有生产纵切、持久任务/迁移、Skill 路由与
Agent 指导文件合并复验：`404 passed, 5 deselected, 2 warnings in 149.63s`。两个 warning 都是 Python 3.12
`aiosqlite` 默认 datetime adapter 弃用提示。五个 deselected 用例已单独确认为当前 A139 预存 Lead Prompt 断言与
`<agent_kernel>` 工作树不一致：`5 failed, 50 deselected in 5.55s`；本轮没有修改它们。

旧 `video-generation` 脚本回归 `12 passed in 0.43s`；前端 `eslint + tsc --noEmit` 退出码为 0；Alembic 唯一 head 为
`0017_account_launch_plan_unique`。新视频 Skill 通过 `quick_validate`，项目 Skill Reviewer 包摘要为
`sha256:ff5bcb5c8134ffd00bf478fa71f6814a486c24b0a12b68d0ee181e7a09a13b1d`，结果为
`0 blocker, 0 error, 0 warning`且无截断/未评估内容。

本轮更早、最终收紧前曾跑一次后端非 live 全量，结果为
`46 failed, 12530 passed, 75 skipped, 19 warnings in 682.50s`；失败集与同一脏工作树的 A137/A139 Prompt、认证、频道和扩展修改
相关，且那次时点早于最终代码，因此不声称当前整仓全绿。精确命令、源码快照、动态 GitHub 口径、哈希与未做事项见
`evidence/a140-a141-video-production-2026-08-22.md`。

## 回滚点

Ark 与对标合同当前未注册，最安全的运行时回滚就是保持它们不可发现；既有内容与 MediaKit 本地 trim 不受
影响。任务策略默认仍是 `idempotent_retry`，迁移可降级到 0015；降级前仍在提交边界的 at-most-once 行必须
保守终结，已经进入 `submission_unknown` 的任务不得因回滚被改回可领取。Skill 如需撤下，应从公开目录取消发现，但不得删除已经封存的业务工件或恢复第五版平行
台账。
