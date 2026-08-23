---
id: a140-a141-video-production-2026-08-22
date: 2026-08-22
scope:
  - A140
  - A141
status: focused_vertical_passed_full_repository_not_green
---

# A140/A141 起号制作桥与视频生产安全底座回执

## 仓库与边界

- 项目：`/Users/yangyucheng/Documents/ChatGPT/第六版营销系统`
- 分支：`codex/v6-comprehension-core`
- 本轮基线 HEAD：`d14ca51ffcc1f797c9ad01b7366a6d8d8c464736`
- 工作树：脏。其中同时存在用户原有 A137–A139 Prompt/认证/频道/扩展修改；本轮没有 reset、stash、覆盖或把它们冒充为 A140/A141 成果。
- 最终 `git status --porcelain=v1 --untracked-files=all | LC_ALL=C sort` SHA-256：`ab35710df2702135c53e8135a760806a754af0e5bb7d29117fe4aead74e63b44`
- 本轮没有运行 `arkcli +gen`，没有 MediaKit 云调用，没有产生供应商费用，也没有发布内容。

## 已验证的编排接缝

```text
AccountDirectionProposal -> confirmed AccountDirectionVersion
  -> optional proposed AccountLaunchPlan
  -> exact `确认起号计划 <proposal-id>`
  -> exact confirmed AccountLaunchPlan + exact seed_id
  -> evidence research -> TopicBrief -> MessagePlan -> BaseDraft
  -> explicit FormatDecision -> AdaptedDraft -> explicit ProductionPlan
  -> benchmark/source evidence + asset routing
  -> currently registered local media operation OR unregistered provider request
  -> future durable task/private materialization/QC -> MediaArtifact
```

主链不存在“起号计划直接到成片”的跳跃。计划 seed 只是研究入口，必须形成自己的证据、TopicBrief、消息计划和基础稿。
`ProductionPlan` 仍是资产/动作/装配的唯一真相；新 Skill 不拥有平行 JSON 台账或第二总控。

## 最终无 live 验证

### 合并后端纵切

命令覆盖：

- 账号方向/起号计划/确认工具/plan seed 到 TopicBrief；
- 对标视频证据、Ark 封闭请求与 CLI 模拟边界；
- MCP 持久任务、`at_most_once`、0016/0017 迁移；
- `ProductionPlan -> MediaArtifact`、MediaKit 本地/云端安全原语、批准与持久化；
- Skill 默认路由和 Agent 指导文件预算。

```bash
backend/.venv/bin/pytest -q \
  backend/tests/test_account_launch_plan.py \
  backend/tests/test_account_launch_plan_runtime.py \
  backend/tests/test_account_launch_plan_tool.py \
  backend/tests/test_account_direction.py \
  backend/tests/test_incubation_content_run.py \
  backend/tests/test_content_intelligence_tool.py \
  backend/tests/test_benchmark_video_evidence.py \
  backend/tests/test_incubation_ark_generation.py \
  backend/tests/test_ark_generation_cli.py \
  backend/tests/test_mcp_task_models.py \
  backend/tests/test_mcp_task_repository.py \
  backend/tests/test_mcp_task_service.py \
  backend/tests/test_migration_0016_mcp_task_submission_policy.py \
  backend/tests/test_migration_0017_account_launch_plan_unique.py \
  backend/tests/test_video_skill_routing_config.py \
  backend/tests/test_incubation_ledger.py \
  backend/tests/test_persistence_bootstrap.py \
  backend/tests/test_persistence_bootstrap_concurrency.py \
  backend/tests/test_persistence_bootstrap_regression.py \
  backend/tests/test_incubation_production_plan.py \
  backend/tests/test_incubation_media_artifact.py \
  backend/tests/test_incubation_approval_grants.py \
  backend/tests/test_mediakit_approval_request.py \
  backend/tests/test_mediakit_cloud_driver.py \
  backend/tests/test_mediakit_config.py \
  backend/tests/test_mediakit_enhance_video_preflight.py \
  backend/tests/test_mediakit_local_production.py \
  backend/tests/test_mediakit_quote_service.py \
  backend/tests/test_mediakit_router.py \
  backend/tests/test_mediakit_trusted_io.py \
  backend/tests/test_migration_0014_incubation_approval_grants.py \
  backend/tests/test_agent_guidance_check.py \
  -k 'not lead_does_not_bypass_an_explicit_shootable_topic_failure and not lead_keeps_current_surface_exclusions_out_of_the_entire_visible_answer and not lead_prompt_uses_a_thin_content_incubation_contract and not lead_owns_account_incubation_routing and not clarification_is_not_a_mandatory_business_workflow_gate'
```

结果：`404 passed, 5 deselected, 2 warnings in 149.63s (0:02:29)`。两个 warning 都是 Python 3.12 `aiosqlite` 默认 datetime adapter 弃用提示。

### 明确排除的 A139 Prompt 工作树冲突

五个用例已单独复验，当前完整结果为 `5 failed, 50 deselected in 5.55s`。断言仍期待旧的英文句子与
`<account_incubation>`，而用户并行工作树的当前 Prompt 是 `<agent_kernel>`。本轮不修改这五个 A139 所有权用例，也不把它们混入视频纵切成功结论。

### 其他最终回执

| 验证 | 结果 |
| --- | --- |
| `backend/.venv/bin/pytest -q tests/skills/test_video_generation.py` | `12 passed in 0.43s` |
| `quick_validate.py skills/public/marketing-video-production` | `Skill is valid!` |
| 项目 Skill Reviewer CLI | digest `sha256:ff5bcb5c8134ffd00bf478fa71f6814a486c24b0a12b68d0ee181e7a09a13b1d`；`0 blocker, 0 error, 0 warning`；无截断或未评估内容 |
| 当前变更 Python 文件 `ruff format --check` / `ruff check` | `68 files already formatted`; `All checks passed!` |
| `python3 ../scripts/pnpm.py check` in `frontend/` | `eslint . --ext .ts,.tsx && tsc --noEmit`，exit `0` |
| `.venv/bin/alembic -c packages/harness/deerflow/persistence/migrations/alembic.ini heads` | `0017_account_launch_plan_unique (head)` |
| `git diff --check` | exit `0` |

更早、最终收紧前曾跑一次后端非 live 全量：
`46 failed, 12530 passed, 75 skipped, 19 warnings in 682.50s`。失败集涉及同一脏工作树中的 A137/A139 Prompt、认证、频道与扩展修改，
且该回执早于最终收紧。因此当前证据是“A140/A141 聚焦纵切通过”，不是“当前整仓全绿”。

## GitHub 官方开源快照

快照时间：`2026-08-22T05:58:02Z`。来源是 GitHub 官方 REST `GET /repos/{owner}/{repo}`。stars 会变，下表只是该时点的证据。
GitHub 仓库元数据没有历史 star 序列；对 2026 新仓只能计算生命周期累计速度，不能证明最近 7/30 天加速。

| 仓库 | stars | created_at | pushed_at | GitHub license metadata | 第六版位置 |
| --- | ---: | --- | --- | --- | --- |
| [calesthio/OpenMontage](https://github.com/calesthio/OpenMontage) | 49,335 | 2026-03-29 | 2026-08-18 | AGPL-3.0 | 只洁净重写素材 connector、sample/费用审批门、contact sheet 和 QA；不接入全栈总控/台账 |
| [heygen-com/hyperframes](https://github.com/heygen-com/hyperframes) | 42,005 | 2026-03-10 | 2026-08-22 | Apache-2.0 | 确定性 HTML/GSAP renderer 候选；只消费封存计划并返回 RenderReceipt |
| [Vincentwei1021/video-shotcraft](https://github.com/Vincentwei1021/video-shotcraft) | 5,992 | 2026-07-19 | 2026-08-21 | Apache-2.0 | 镜头卡、motion recipe、storyboard/QA rubric 研究；模板与捆绑素材未迁移 |
| [FireRedTeam/FireRed-OpenStoryline](https://github.com/FireRedTeam/FireRed-OpenStoryline) | 3,242 | 2026-02-07 | 2026-07-31 | Apache-2.0 | 只作 typed edit-op compiler 的离线研究 |
| [bytedance/Bernini](https://github.com/bytedance/Bernini) | 1,273 | 2026-05-29 | 2026-08-13 | Apache-2.0 | 只研究本地生成/编辑 backend，不引入其语义规划器 |
| [oxbshw/watch-skill](https://github.com/oxbshw/watch-skill) | 304 | 2026-07-05 | 2026-08-21 | MIT | 带时间戳对标观察与成片 self-verification 候选 |
| [Shanyin-ai/shanyin-director-master](https://github.com/Shanyin-ai/shanyin-director-master) | 447 | 2026-04-05 | 2026-05-11 | MIT | 只已迁移冻结方法结构；不声称近期加速 |
| [volcengine/mediakit-cli](https://github.com/volcengine/mediakit-cli) | 189 | 2026-06-03 | 2026-07-16 | MIT | 火山官方证据/原子媒体层；注册必须强制显式 local/cloud |

成熟仓的当前关注度只作参考：Remotion 57,019★但使用自定义 Remotion License，不能简化成 OSI 开源；
MoneyPrinterTurbo 114,102★（MIT）、OpenCut 85,431★（MIT）、VideoLingo 18,224★（Apache-2.0）只分别作 adapter/smoke、人工精修 UI、字幕/翻译/配音候选。

## 第四/第五版与山音来源身份

- V4：`/Users/yangyucheng/Documents/第四版营销系统`，HEAD `58f4e0c900a2dc589fe4a23bdebbe8e3211b67b7`。
  `VIDEO_PIPELINE_MIGRATION_HISTORY.md` 受 Git 追踪，SHA-256
  `87212278bb0c36f0195295ddbe9410c6c16165cf00917176fca67ef78d2eaa90`；V-006 明确是 `local inspection done`，远程搜索/采集验收未完成。
  `video-pattern-learning` 四文件 manifest 为
  `b16a1dfa059c599a6d95ca1762f1b39efc0d3bb313bf50221d80b2d4a9ac6646`。
- V5：`/Users/yangyucheng/Documents/ChatGPT/第五版营销系统`，HEAD `3ee135f787354b36b85edc62404684fda37acdc0`。
  被参考的 `marketing-video-production` 与 `community/video_production` 15 个源文件全部未追踪，不属于该 HEAD；源文件 manifest 为
  `bd6462726ba4925642c7b738083afa1fc27293e74af4b879b5625540cf94ed3b`。
- 山音：冻结提交 `30f0daecaf0754e08cf88ece83fabf3a2372a016`，MIT `LICENSE` SHA-256
  `efc510fcf834152b44be1f2bba1b2f3b49525040ff2e5aee1184cae29e10e3fa`。具体上游文件到本地方法映射和逐文件哈希见 A141 审计与 Skill 第三方通知。

结论：V4 不能证明“全网找素材已成功”；V5 只是未追踪原型；山音与 `video-shotcraft` 是两个不同仓库。

## 本机版本回执

| 组件 | 版本 |
| --- | --- |
| ArkCLI | `1.0.11` |
| MediaKit CLI | `0.2.0` (build `2026-07-14T07:05:19Z`) |
| Node.js | `v26.4.0` |
| uv | `0.11.11` |
| pnpm（项目 runner） | `10.26.2` |
| Python | `3.12.13` |

## 尚不能注册 Ark 的硬门

1. 必须冻结 active profile 的 account/tenant/project/region、Endpoint 底层模型身份和当期价格证据。
2. 必须让注册层机械化强制 Ark 只能使用 `at_most_once`，不能走旧 remote-first submit。
3. 费用标记后的租约必须覆盖付费调用，并通过双 worker 超时 fencing 测试。
4. 持久错误必须是结构化脱敏合同，不能直接存任意异常文字。
5. 具体 runner 必须是 shell-free argv 执行且审计 ArkCLI/SDK 内部创建重试；“一次 CLI 进程”不等于“一次 HTTP mutation”。
6. 必须完成 Gateway 入口、精确报价/权利/云处理/费用批准、私有物化/QC，并保留一次用户明确批准的真实小额回执。

在这些条件完成前，新 Ark 合同和 CLI 适配器保持不可发现。“未注册”是专用 Tool/Gateway/driver 的发现边界，不是泛用 Bash 在主机层绝对无法执行的证明；正式启用前还须把 provider mutation 变成技术硬边界。

## 完整性摘要

- A140 审计 SHA-256：`705e7510272c8ab3d217f43b1d7361f206f00799774620aa747e36066e8088dd`
- A141 审计 SHA-256：`7b6313835a08d08293c04ae57b2191fbe9bd8309baae2298f4fa8bb4581c5709`
- `marketing-video-production` 包摘要：`ff5bcb5c8134ffd00bf478fa71f6814a486c24b0a12b68d0ee181e7a09a13b1d`
- 本回执不自引用自身哈希；台账只保存它的路径与上述外部完整性值。
