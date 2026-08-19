---
id: A102
status: reviewed
reviewed_at: 2026-08-19
decision: repair_scope_drift_and_require_live_credential_preflight
sources:
  - https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/douyin-search-capability/aweme-dy-video-search
  - https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/account-permission/generate-stable-client-token
  - https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/account-permission/douyin-get-permission-code/
  - https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/account-permission/get-access-token/
  - logs/gateway.log
  - extensions_config.json
---

# A102 抖音 OpenAPI 真实接入断点审计

## 问题

第六版日志反复显示 `douyin-openapi-mcp` 成功加载 16 个领域，但 Agent 仍未产生真实
抖音搜索回执，后续甚至回退到网页搜索或视觉打开页面。需要区分本地 MCP 协议可用、
应用凭据可用、指定 Scope 可用和业务 API 真实通过。

## 证据

1. Gateway 日志证明 MCP 子进程可启动并列出 16 个领域工具；这只是 MCP
   `initialize/tools/list` 成功。
2. 第六版根 `.env` 和当前 Gateway 进程均不存在 `DOUYIN_CLIENT_KEY` 与
   `DOUYIN_CLIENT_SECRET`。`extensions_config.json` 仅保存 `$DOUYIN_*` 引用，解析后为空。
3. 官方当前搜索文档显示 `GET /dy_open_api/v1/search/video/` 与
   `aweme.dy.video_search`；A41 审计时曾显示 v2 与 `aweme.dy.video_search_v2`。
   v1/v2 URL 目前都会返回规范的无效令牌错误，但最终能否调用取决于当前应用真实获批 Scope。
4. 官方公开搜索使用应用级 `client_token`；需要账号授权的用户资料、粉丝、作品、
   发布等接口使用 OAuth `access_token + open_id`。二者不是同一条鉴权链。
5. 目前 119 条只是 Catalog 库存，16 个是渐进披露的领域入口，真正有适配器的 Child
   只有视频搜索与图文/经验搜索。

## 修复

- 视频搜索合同默认跟随官方当前 v1；如应用只声明已获批 v2 Scope，则保留 v2 兼容。
- 领域 Manifest 支持 Scope 别名中任一真实获批值，不再因文档版本变化隐藏搜索 Child。
- 现役未跟踪 `extensions_config.json` 原先把 v2 Scope 写死；现已改为
  `$DOUYIN_APPROVED_SCOPES`，与仓库模板一致，真实值只从本地环境解析。
- `make doctor` 新增抖音专项，分别检查 MCP 可执行文件、本地应用凭据和精确搜索合同，
  且不打印任何凭据值。
- 抖音相关 `129` 项与完整后端 `12201` 项非 live 测试通过；当前 `make doctor` 的两项错误为
  应用凭据缺失和真实 Scope 未声明。
- 本轮仍不标记 `live verified`；必须在 Client Key/Secret 进入本地 `.env`、重启 Gateway 后，
  真实取得 stable client token 并完成一次视频搜索回执。

## 当前结论

一直没接上的首要原因不是 MCP 架构，而是真实应用凭据从未进入第六版 Gateway。第二个
问题是 v1/v2 文档漂移，第三个问题是把 Catalog 和真正实现的适配器数量混为一谈。
