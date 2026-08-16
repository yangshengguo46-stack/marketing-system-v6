---
id: A44
status: reviewed
reviewed_at: 2026-08-17
decision: adopt_strict_evidence_routes_and_ephemeral_mediakit_locators
sources:
  - backend/packages/harness/deerflow/content_intelligence/contracts.py
  - backend/packages/harness/deerflow/tools/builtins/content_intelligence_tool.py
  - backend/packages/harness/deerflow/incubation/media.py
  - backend/packages/harness/deerflow/community/mediakit/router.py
  - /usr/local/bin/mediakit-cli@0.2.0
  - /Users/yangyucheng/Documents/ChatGPT/第五版营销系统/backend/experiments/e15_account_evidence/mediakit.py
---

# A44 证据隔离与 MediaKit 媒体来源审计

## 问题

内容地图会同时搜索普通网页和抖音视频，对标链路也会搜抖音作品。
两者如果只按 URL 或平台名判断，对标候选就可能被重新包装为内容资料，
反过来一条选题视频也可能被误当成账号样本。同时，MediaKit 的
`video_url` 是否能直接接抖音分享页，必须以当前 CLI Schema 和源码实际行为判断。

## 发现

1. `content_intelligence.SourceItem` 曾经允许 `benchmark_account_candidate`。当前
   研究实现没有主动写入该角色，但合同层留下了错接入口。
2. 内容地图的抖音搜索适配会丢掉上游 `evidence_role`，然后不加区分地
   把所有搜索结果物化为 `topic_evidence`。这会把一个错配置的对标回执洗成选题证据。
3. 本机 `mediakit-cli 0.2.0` 的 ASR、OCR、场景切分和元信息 Schema 均接收
   `video_url`；描述要求公网可访问的 HTTP/HTTPS 媒体。
4. MediaKit CLI 会将 HTTP/HTTPS 字符串原样交给媒体能力；它不会将
   `v.douyin.com/...` 分享页解析成视频资源。本地文件输入则由 CLI 内部的媒体输入层处理。
5. 平台作品页是可持久化证据；解析后的 CDN 签名直链或本地文件路径是
   短命执行定位符，不能进入 Lead、前端、日志或业务台账。

## 决定

- 内容理解来源只允许 `user_material` 和 `topic_evidence`。
- 任何内容研究搜索源显式声明非 `topic_evidence` 角色时都整包丢弃。
- 内容地图调用抖音搜索时，还必须收到明确的 `topic_evidence`；
  `benchmark_account_candidate` 或缺失角色的抖音回执整包丢弃，不重标。
- 对标采集仍走 A42/A43 独立高层工具、账号候选和后续稳定身份链路。
- 新增 `EphemeralMediaSource`：只在执行内存中携带直链或本地路径，
  `repr` 脱敏；HTTP 直链还必须由解析器确认为 `video/*`。
- 新增 `MediaSourceReceipt`：只持久来源引用、权利引用、解析器、传输类型、
  定位符哈希、时间、过期信息和局限。
- 新增 `MediaKitCapabilityRouter`：从 `mediakit-cli <domain> <tool> --schema`
  动态读取 Schema，校验 `video_url` 能力、其他参数和客户端幂等令牌，
  生成不入账的脱敏预备调用。
- 内容资料与对标视频可以共用 MediaKit 能力，但机器感知产物必须继承其父证据角色。
  只有未来的用户孵化/适配判断产物可同时引用内容地图和对标诊断，上游不混料。

## 验收边界

离线证据隔离与 MediaKit 合同已实现，本机真实 CLI Schema 烟测已通过。
本轮没有解析真实抖音作品直链，没有提交付费云任务，也没有接通轮询、恢复、
ASR/OCR/场景切分输出或跨视频对标诊断。因此状态是 `implemented`，不是 MediaKit
感知链的 `verified`。
