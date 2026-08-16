# A44 证据隔离与 MediaKit 来源合同回执

## 失败基线

```text
content-intelligence SourceItem accepted benchmark_account_candidate
content-world Douyin search accepted and relabeled a benchmark_account_candidate receipt
content-world web search accepted an explicitly labeled benchmark_evidence receipt
ModuleNotFoundError: No module named 'deerflow.community.mediakit'
```

## 实现回执

- `content_intelligence.EvidenceRole` 缩小为 `user_material | topic_evidence`。
- 任何搜索源显式声明的对标角色都会被拒绝；抖音内容研究路由还要求
  上游回执显式为 `topic_evidence`，缺失角色也不会被重标。
- HTTP 媒体只有在解析器确认 `video/*` 后才能形成 `EphemeralMediaSource`。
- 平台页面、过期直链、携带凭证的 URL、不存在的本地文件和不支持
  `video_url` 的 MediaKit 能力不能进入预备调用。
- 可持久回执不含 URL 和本地路径，并可通过 `ArtifactEnvelope` 脱敏完整性校验。
- Router 读取 CLI 版本与当前工具 Schema，不在业务代码中复制完整参数表。

## 自动回归

```text
content intelligence + Douyin + ledger + MediaKit focused suite:
174 passed in 7.63s

MediaKit unit suite:
5 passed

final focused boundary suite:
60 passed in 4.27s

backend full non-live final run:
11742 passed, 76 skipped, 17 warnings in 463.85s
```

第一次全量运行曾出现 13 个浏览器/Browserless/Crawl4AI 网页读取失败。
这些失败不在 MediaKit 路径上；失败四组隔离复跑为
`126 passed, 1 skipped`，包含完整测试收集的首错复跑随后全量通过；
追加普通网页搜索角色边界后，仓库标准 `make test` 也再次全量通过。
本轮未将该非确定性现象误记为产品回归，也未隐去首次失败。

## 本机真实 CLI Schema 烟测

```text
mediakit-cli version
-> mediakit-cli 0.2.0
-> build date: 2026-07-14T07:05:19Z

video/asr-subtitles capability discovery and prepared direct-link call
-> cli_version: 0.2.0
-> capability: asr_subtitles
-> schema_sha256: 6efaa9887ef00b7ae902dbafa69a5d8efc7ababe9fb1ea0fca468b744dcdb782
-> raw URL omitted; locator_sha256 retained
```

CLI 同时返回一条本机 MediaKit Skills 未与 `0.2.0` 同步的 notice。Router 会保留
有界 notice，但本轮没有自动执行全局 `mediakit-cli update --force`。

## 未验收

- 抖音作品页到经授权临时直链/本地文件的真实解析器。
- 真实云端 ASR、OCR、场景切分提交、费用同意、幂等、轮询和重启恢复。
- 媒体感知回执继承 `topic_evidence` 或 `benchmark_evidence` 父证据角色的持久化实现。
- 一个真实对标账号的多作品视听观察、评论/受众观察与人工诊断对齐。
