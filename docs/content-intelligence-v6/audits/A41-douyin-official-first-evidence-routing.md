---
id: A41
status: reviewed
reviewed_at: 2026-08-16
decision: adopt_official_first_v2_search_and_candidate_boundary
sources:
  - https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/douyin-search-capability/aweme-dy-video-search
  - https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/account-permission/get-account-open-info
  - https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/video-management/posting-task/video-basic-info
  - docs/content-intelligence-v6/audits/A40-fifth-version-e15-benchmark-snapshot.md
---

# A41 抖音官方优先证据路由审计

## 问题

W02 已有官方抖音搜索、第五版 E15 采集证据和第六版 `BenchmarkSnapshot`，但必须明确对标账号
到底先走哪条路径，以及公开搜索结果何时可以升级成正式账号快照。

## 发现

1. 当前官方视频搜索合同已是 `GET /dy_open_api/v2/search/video/`，Scope 为
   `aweme.dy.video_search_v2`。第六版运行时仍保留旧 v1 合同，存在真实版本漂移。
2. 官方视频搜索适合发现话题、作品和候选作者，但返回的作者显示名不是稳定账号身份，也不提供
   一个任意第三方账号的作者一致完整作品列表。
3. 官方用户信息和视频基础信息能力受目标用户授权及相应 Scope 约束，不能把“应用已开通能力”
   等同于“可读取任意竞品账号全部数据”。
4. 第五版 E15 的身份一致、覆盖和有界投影合同仍有价值；其 Playwright 选择器、平台运行时和
   本地 JSON 缓存不是第六版默认实现。

## 决定

- 抖音读取统一采用 `official-first`，不再默认调用第五版采集器。
- `topic_research` 生成 `topic_evidence`；`benchmark_discovery` 生成
  `benchmark_account_candidate`。`purpose` 只控制本地证据角色，不发送给平台。
- 候选证据只用于找到“可能值得分析的账号”。它必须经过稳定账号 ID、作者一致多作品和真实覆盖
  回执，才能由独立连接器封存为 `BenchmarkSnapshot`。
- 自有/已授权账号使用官方授权 API；第三方对标优先使用抖音官方可用能力及星图/精选联盟等
  官方页面的受控浏览器连接器。只有逐项证明官方缺口后，才审议补充采集器。
- 原始 Catalog 快照保留当时目录证据，不篡改来源摘要；当前经审阅的 v2 合同由运行时 override
  与 A41 回执覆盖。下一次全目录刷新再生成新的内容寻址快照。

## 状态边界

代码和离线测试已经实现。第六版本地尚未配置 `DOUYIN_CLIENT_KEY` 与
`DOUYIN_CLIENT_SECRET`，真实探测没有向抖音发出请求，因此本轮不能标记 live verified。
