# A48 抖音 MCP 选题证据谱系审计

## 状态

`reviewed -> implemented offline; live credential acceptance blocked`

## 问题

A45 已恢复 `douyin-openapi-mcp` 的 16 个领域，A47 已把内容纵切写入项目，但两者仍未接上。
内容研究会寻找名为 `douyin_video_search` 的旧配置工具；第六版并未启用该项，因此实际运行只有
Web 搜索。即使重新启用，也会绕过已经建立的 MCP Manifest 边界。

## 发现

1. `douyin_search` MCP 领域已经提供 `video_search` Child，并区分 `topic_research` 与
   `benchmark_discovery`。
2. 当前本地 `extensions_config.json` 保存的是 `$DOUYIN_*` 环境引用，不是凭据值。解析后的
   Key、Secret 和 Device ID 为空，Scope 引用已配置。
3. 通过解析后配置启动真实 MCP 协议，可以得到 16 个领域；搜索 Manifest 返回
   `callable=false / auth_not_configured`，未发送平台搜索请求。
4. 搜索一次可能返回多条结果，但最终证据阅读只采用其中一部分。把所有检索候选都写进阅读父级
   会把探索噪声冒充最终依据。

## 决定

- 新增一个薄 `DouyinMcpTopicEvidenceSearch`，只负责从 `ToolRuntime.tools` 选择 MCP 标记的
  `douyin_search`、发现 Manifest、精确执行 `video_search` 和验证结构化回执。
- 内容研究不再读取旧 `douyin_video_search` 配置；Web 搜索继续作为并列资料源。
- Child 参数中的 `purpose` 固定为 `topic_research`。返回对标角色时整批拒绝，不能依靠模型纠正。
- Manifest 只在一次内容运行中发现一次；`stale_manifest` 最多重新发现并重试一次。
- 官方回执先转换为有覆盖、来源、限制和路由版本的 `EvidenceSnapshot`。只有快照中的公开 URL
  出现在最终 `ComprehensionRecord` 时才落盘，并成为 `content_reading` 父级。
- 长期 `content_world` 不引用单次平台搜索证据，避免热点和搜索排名静默改写账号定位。
- 缺少授权时该提供者返回空结果，Web 资料与内容地图仍可继续；禁止浏览器视觉兜底。

## 验收

- 失败测试先固定不存在 MCP 适配器、旧直连不得执行和对标角色不得混入。
- 聚焦 MCP、内容研究、证据合同和项目台账回归 `51 passed`；后端全量
  `11764 passed, 76 skipped`。
- Manifest 过期刷新和首次传输异常后的再次发现都有独立失败测试与通过回执。
- 本机运行探针确认 MCP 工具存在且无凭据时安全停在 Manifest 发现。
- 尚未取得真实 v2 搜索结果，所以本条不能标为 `live verified`。

完整命令与脱敏回执见
`evidence/douyin-mcp-topic-evidence-a48-2026-08-17.md`。
