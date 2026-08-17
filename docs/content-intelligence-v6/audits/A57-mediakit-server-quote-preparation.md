---
id: A57
status: reviewed
traced_at: 2026-08-17
reviewed_at: 2026-08-17
decision: adopt_default_off_server_quote_preparation_keep_cloud_execution_disabled
sources:
  - docs/content-intelligence-v6/audits/A54-mediakit-first-cloud-capability.md
  - docs/content-intelligence-v6/audits/A55-mediakit-enhance-video-preflight.md
  - docs/content-intelligence-v6/audits/A56-mediakit-exact-approval-api.md
  - backend/packages/harness/deerflow/community/mediakit/quote_service.py
  - backend/app/gateway/routers/incubation_projects.py
---

# A57 MediaKit 服务器报价生产入口审计

## 问题

A56 只能审阅和确认一个已经存在的服务器报价，却没有生产报价的 API。让客户端填写费率、价格证据、
来源定位符或操作摘要会重新打开盲签和篡改边界；直接把云驱动接到报价接口又会把“看价格”变成上传、
排队甚至扣费。同一操作在不同时间封存出两个内容寻址报价后，若凭证身份绑定报价产物 ID，还会产生
第二对有效批准。

## 已采用合同

1. `POST /api/incubation/projects/{project_id}/media/mediakit/enhance-video/quotes` 只接受当前用户、当前
   项目中已有的 `media_observation`，其角色必须是 `user_material`，并精确绑定同角色的
   `media_source_receipt` 父级。
2. 客户端只选择首轮已审阅的标准版、场景、720P 及以下分辨率、15-30fps、码率档位和金额上限。
   未声明字段一律拒绝；费率、价格证据、素材定位符、权利引用和操作摘要均由服务器持有。
3. 运营方价格证据从本地未跟踪 JSON 读取，最大 64 KiB，禁止未知字段；来源 URL、文档 ID、正文
   SHA-256、检查时间、有效期、硬封顶能力和结构化费率缺一不可。缺失、损坏、未来生效或过期均关闭
   报价。
4. 每次报价只通过 `MediaKitCapabilityRouter` 运行只读版本与 Schema 探测，并要求发现摘要等于审阅
   摘要。Schema 漂移时返回有界 503，不降级到硬编码参数表。
5. 报价沿用 A55 的确定性预检和 A56 的密封合同。批准产物及 API 响应不含 `source_ref`、
   `rights_ref`、URL、本机路径、Cookie、凭据或媒体字节。
6. 两类批准凭证的稳定 ID 由 `operation_sha256` 而非报价产物 ID 推导。同一精确操作的不同报价产物
   只能重放首对凭证；操作、金额、价格证据或规格变化仍形成不同身份。
7. 功能在 `config.yaml -> mediakit.quote_preparation_enabled` 下默认关闭。入口只封存可审阅报价，
   不创建或消费批准、不创建 `mcp_task`、不注册云驱动、不解析定位符、不上传素材、不调用供应商。

## 失败基线

```text
MediaKitEnhanceVideoQuoteService: missing
app.gateway.mediakit: missing
POST quote route: 404
disabled quote service: 404 instead of explicit 503
same operation in two quote artifacts: second approval pair returned 201
```

## 价格证据合同

```json
{
  "provider": "volcengine-mediakit",
  "capability_domain": "video",
  "capability_tool": "enhance-video",
  "currency": "CNY",
  "source_url": "https://docs.volcengine.com/docs/6448/2486473",
  "document_id": "2486473",
  "document_sha256": "<官方正文快照 SHA-256>",
  "document_updated_at": "<带时区时间>",
  "checked_at": "<带时区时间>",
  "valid_until": "<带时区时间>",
  "provider_hard_cap_supported": false,
  "rates": [
    {
      "tool_version": "standard",
      "resolution_tier": "720p",
      "maximum_fps": 30,
      "amount_micros_per_minute": 750000
    }
  ]
}
```

该文件是带时效的运营证据，不是永久内置价格表。更新价格必须重新取得官方页面证据、更新正文摘要和
检查时间；应用不会自动把网页内容或模型回答当成价格。

## 验收结果

- 聚焦报价、配置与 Gateway 回归：`20 passed, 1 warning`。
- MediaKit、孵化谱系与配置联合回归：`174 passed, 1 warning`。
- Gateway 启停与说明约束回归：`30 passed`。
- 阻塞 I/O 回归：`71 passed, 2 warnings`。
- 完整离线后端回归：`11864 passed, 76 skipped, 17 warnings in 426.03s`。

## 当前边界

状态仍为 `reviewed`。当前没有面向普通用户的素材观察创建/选择界面，也没有从批准凭证创建持久任务的
接线。供应商没有单任务费用硬封顶，云驱动保持未注册。任何真实 `enhance-video` 调用仍需能力专属
接线、一次全新的精确用户批准和独立真实回执。
