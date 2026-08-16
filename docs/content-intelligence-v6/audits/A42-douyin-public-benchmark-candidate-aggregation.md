---
id: A42
status: reviewed
reviewed_at: 2026-08-17
decision: adopt_official_public_search_aggregation_defer_xingtu_buyin
sources:
  - https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/douyin-search-capability/aweme-dy-video-search
  - https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/common-params
  - docs/content-intelligence-v6/audits/A40-fifth-version-e15-benchmark-snapshot.md
  - docs/content-intelligence-v6/audits/A41-douyin-official-first-evidence-routing.md
  - /Users/yangyucheng/Documents/ChatGPT/第五版营销系统/backend/experiments/e15_account_evidence/platform_account_reader.py
  - /Users/yangyucheng/Documents/ChatGPT/第五版营销系统/backend/experiments/e15_account_evidence/lead_projection.py
---

# A42 抖音公开对标候选聚合审计

## 问题

用户已开通抖音开放平台能力，第三方对标账号是否还需要先建星图、百应连接器。

## 发现

1. 官方 `search.video_search` 已能返回公开作品 ID、标题、高质量文本、作者显示名、
   发布时间、点赞观察值和作品链接，并支持 `cursor + search_id` 翻页。
2. 搜索返回的是关键词排名样本，不是某账号的完整作品列表；作者字段也只是显示名，
   不能伪装成稳定外部账号 ID。
3. 官方通用参数将 `open_id` 定义为授权用户的唯一标识。视频搜索中的可选
   `open_id` 只能当作授权查看者上下文，不能当作目标竞品的身份过滤器。
4. 第五版 E15 值得复用的是同一作者、作品去重、覆盖回执和有界 Lead 投影；
   Playwright 选择器、本地 JSON 缓存和旧平台运行时不需要迁移。
5. 因此官方公开搜索已足以完成第一层“找到并观察对标候选”。星图和百应应在
   真实需要稳定账号身份、更完整的账号/受众/商业字段时再启用。

## 决定

- 新增一个薄的官方搜索聚合层，不新增 Agent 或第二运行时。
- 聚合层使用同一 Domain Manifest 跨页调用 `video_search`，按 Unicode 归一后的
  作者显示名精确筛选，作品 ID 去重，最多保留 `24` 条。
- 覆盖回执分别记录请求、成功页、非目标作者排除、重复作品、剩余页与停止原因。
  后续页失败时保留早先观察并标记部分结果；首页失败不伪造空样本。
- 完整 `EvidenceSnapshot` 可幂等封存到项目台账，角色固定为
  `benchmark_account_candidate`；Lead 只接收固定字节预算投影。
- 该产物仍不是 `BenchmarkSnapshot`。取得稳定目标账号 ID 和作者一致作品列表后，
  才能升级为正式 `benchmark_evidence`。
- 星图与百应状态为 `deferred`，不是 `rejected`。不在官方公开搜索已满足的字段上
  重复造连接器。

## 验证边界

离线聚焦测试已通过；第六版本地仍没有 `DOUYIN_CLIENT_KEY` 和
`DOUYIN_CLIENT_SECRET`，因此本轮没有生成真实抖音回执，不标记 `live verified`。
