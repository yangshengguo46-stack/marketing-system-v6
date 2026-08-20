---
id: A113
status: adopted_for_local_experiment_production_license_pending
date: 2026-08-20
decision: pin_live_open_source_douyin_mcp_behind_bounded_read_only_facade
sources:
  - https://github.com/pazwusimple-netizen/douyin-mcp
  - https://github.com/Youhai020616/douyin
  - https://github.com/tamnd/douyin-cli
  - https://github.com/cmsjin/douyin
  - https://github.com/Johnserf-Seed/f2
  - https://github.com/NanmiCoder/MediaCrawler
---

# A113 免费开源抖音数据通道真实验收

## 问题

官方 OpenAPI 的认证基础设施已经打通，但当前应用没有视频搜索 Scope，官方 MCP 也返回零工具。用户明确
拒绝付费数据服务，并要求停止继续修补自研采集器，直接从开源仓库找到一个在当前机器上能取得真实抖音
搜索、账号、作品和评论的数据通道。

本轮验收标准不是 README、工具列表或 Mock，而是同一登录态下实际完成：

```text
关键词搜索 -> 视频详情 -> 稳定账号标识 -> 账号资料 -> 账号作品 -> 可见评论
```

任何需要付费 API Key、只有热榜、只读自有授权账号、返回空数组、触发 `verify_check` 后无可用回退，或
许可证明确禁止商业使用的候选，都不能成为现役通道。

## 候选实测

| 候选 | 当前机器真实结果 | 判定 |
| --- | --- | --- |
| `dy-cli 0.2.2` | 登录状态有效；视频搜索返回 `verify_check` 和空数据，却错误标记 `ok=true` | 拒绝 |
| `tamnd/douyin-cli 0.1.1` | 三组搜索均为 0；账号、作品、详情和评论均被风控；只有热榜可用 | 拒绝 |
| `cmsjin/douyin` | 复用同一登录态后搜索仍为 0，且搜索没有浏览器回退 | 拒绝 |
| `F2` 当前仓库 | 抖音搜索、评论等关键能力仍是待办或已移除 | 拒绝 |
| `MediaCrawler` | 功能覆盖接近，但项目明确限定非商业学习 | 不进入商业运行时 |
| TikHub/SocialDataX 等 | 能力目录完整，但真实调用需要付费 Key | 按用户要求排除 |
| `pazwusimple-netizen/douyin-mcp` | 搜索、详情、资料、作品、评论五项均返回真实数据 | 本地实验采用 |

采用候选固定在提交 `ab9eb3b36cd47e9091e520f9a5faabf72f1f16e4`，依赖继续使用上游锁文件。
搜索“`大能 腕表`”返回 5 条真实作品；随后成功取得作品详情、5 条评论、大能账号资料和 5 条近作。
“`黄金礼品 人情世故`”也返回真实抖音视频，不再经过普通网页搜索。

## 不需要 API Key

搜索、详情、账号、作品和评论只需要本机抖音登录态，不需要任何第三方 API Key。上游文档中的 Key 仅供
可选 ASR 使用；第六版已有 MediaKit，因此不启用上游的转写、下载、OCR、登录和退出工具。登录态从本机
Playwright StorageState 转换到权限为 `0600` 的未跟踪文件，值不进入仓库、日志、模型上下文、前端或
证据文件。

## 去除反检测逻辑

上游浏览器回退包含隐藏 `navigator.webdriver`、伪造 `window.chrome`、插件和语言的脚本，以及特殊
Chromium 参数。本轮分别关闭脚本、再改为普通 `chromium.launch(headless=True)` 与标准
`new_context(locale="zh-CN")`，两次都仍取得 5 条真实搜索结果。因此本地固定副本删除这些逻辑，只保留
正常 Playwright 页面访问、用户登录态和网络响应读取。

## 有界只读侧车

上游原始 MCP 虽然可用，但一次 5 条搜索约 `198,260` 字节，5 条账号作品约 `531,062` 字节，还包含
临时媒体地址、头像和大量页面字段，不能直接交给 Lead。固定副本外增加薄的 `readonly_server.py`：

- 只暴露搜索、详情、评论回复、账号资料、账号作品和分享链接解析 7 个读取工具。
- 不暴露登录、退出、推荐流、下载、OCR、转写和批量转写。
- 搜索最多 10 条、作品最多 12 条、评论最多 20 条；需要更多数据时显式分页。
- 删除 Cookie、原始页面、临时视频/封面/头像 URL 和供应商内部字段。
- 可见评论者身份只输出不可逆的批内伪名；明确标记 population scope 为
  `visible_commenters`，不能冒充粉丝或观看人群。
- 每次输出包含上游仓库、固定提交、采集方式、请求/返回数量和限制说明。

薄投影的 4 项测试先失败后通过。真实协议调用的结果体积为：搜索 `2,494`、详情 `836`、评论
`1,874`、账号资料 `679`、作品 `3,080` 字节，全部低于 16 KB Lead 投影预算。

## DeerFlow 接线

本机 `extensions_config.json` 已启用 `douyin_community_evidence`，使用固定路径启动标准 stdio MCP，
路由优先级为 100；未获批的 `douyin_openapi` 和零工具的 `douyin_official_mcp` 暂时停用。配置与登录态
均为 Git 忽略的本地运行状态。

DeerFlow 自身完成了第二层验收：成功发现带服务器前缀的 7 个工具，并经
`douyin_community_evidence_search_videos` 搜索“`黄金礼品 人情世故`”，得到 3 条真实抖音结果，完整
工具回包约 `1,850` 字节。由此可以确认链路为：

```text
DeerFlow Lead
  -> 本地只读 MCP
  -> 固定开源采集实现
  -> 登录态抖音公开页面
  -> 有界证据投影
```

## 许可证与当前边界

仓库根 `LICENSE` 是标准 MIT，明确允许使用、修改和分发；但 README 同时写有“仅供学习和研究、请勿用于
商业用途”。两者互相矛盾。当前只批准本机研发与真实账号验收，不能据此宣称生产商业许可已经清晰。
生产前须取得作者澄清，或对公开协议行为做独立的洁净实现并重新验收。

这个 MCP 只提供候选账号、作品和可见受众反应，不判断账号为什么成功，也不选择内容根或定位。正式
`BenchmarkSnapshot` 仍需稳定账号身份、作者一致的多作品窗口、MediaKit 内容观察和覆盖回执；咨询资料
继续记为 `topic_evidence`，不能与对标证据混账。

## 结论

抖音免费公开数据通道已经从“候选仓库”进入“本机真实可用”。下一步不再继续寻找或修补抖音搜索器，
而是在同一证据合同下把这 7 个工具接入对标采集编排，并用用户给过的真实账号完成
`候选 -> 账号 -> 多作品 -> 评论 -> MediaKit` 小闭环。跨平台仍逐个平台真实验收；抖音通过不代表
TikTok、小红书、Bilibili 或视频号已经可用。

## 后续状态

A114 已把本审计的只读 MCP 降为 `deerflow-capability-mcp` 内部 Child Runtime。A113 的真实数据与许可
结论保持有效，但其 `douyin_community_evidence` 平行 Host 注册方式已被 ADR-032 淘汰。
