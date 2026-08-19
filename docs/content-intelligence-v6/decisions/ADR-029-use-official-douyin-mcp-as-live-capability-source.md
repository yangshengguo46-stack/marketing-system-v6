# ADR-029：以抖音官方 MCP 作为动态能力源，保留领域合同

## 状态

Accepted，2026-08-19。连接器已接入；任何具体抖音能力仍需逐项真实验收。

## 决定

引入本地 `douyin-official-mcp` 桥连接抖音官方 SSE。它负责动态工具发现、稳定应用 Token 获取和协议转发，
解决静态 URL 泄露及两小时过期问题。官方 `tools/list` 作为“当前应用实际获得哪些 MCP 工具”的真相源。

不把官方 MCP 的出现解释为 119 个 OpenAPI 全部可用，也不立即删除现有 16 领域、Catalog 和已审计合同。
通用桥只允许明确只读的工具；写操作必须进入具体领域适配器，绑定业务对象和用户审批。应用级
`client_token` 与用户级 OAuth `access_token` 保持两条独立鉴权链。

应用级链统一调用官方 `stable_client_token` 端点。搜索适配器与官方 MCP 共用同一实现；同一进程共享
缓存，独立 MCP 进程依赖官方在有效期内幂等返回同一 Token，禁止各模块重新实现普通 Token 刷新。

## 理由

- 官方 SSE 已用真实应用身份完成初始化，证明协议和凭据链成立。
- 同一次真实 `tools/list` 返回零工具，证明文档目录、本地路由数量和实际授权数量必须分开。
- 静态把 token 写入 `extensions_config.json` 会泄露凭据，并在两小时后失效。
- 直接把未知数量的写工具交给 Lead 会绕过现有不可逆操作审批；动态发现不等于动态放权。
- 领域合同仍承担证据角色、Schema、输出边界和业务审批，官方 MCP 负责减少底层 HTTP 适配重复劳动。

## 后果

- 服务审批生效后，读能力可先通过官方桥验收，再决定替换对应手写 HTTP 适配器。
- MCP 工具为零时系统保持可运行，并明确报告授权为空，不回退为“已接通”。
- 需要用户授权的账号、粉丝、作品、发布和指标能力仍需账号级 OAuth 与凭据保险库。
- 对标证据、普通话题资料和自有账号数据继续使用不同证据角色，不能因来源同为抖音而混账。
- 只有完成真实 `登录/授权 -> tools/list -> 精确调用 -> 第一方回执` 的能力才能标记 adopted。
- 119 项能力的目录、合同、适配、授权和回执状态由 A104 的生成矩阵分别记录；鉴权基础设施成功不得计作
  业务能力成功，小程序、生活服务等独立产品线不得计作当前移动/网站应用已开通。
- 搜索产品页的“正式开放”文案不能覆盖现行接入文档的“实验能力，现不对外开放”和真实
  `28001018` 回执；搜索保持内测待批状态，详见 A105。

## 证据

- `docs/content-intelligence-v6/audits/A103-douyin-official-mcp-sse-live-audit.md`
- `docs/content-intelligence-v6/audits/A104-douyin-open-platform-capability-readiness.md`
- `docs/content-intelligence-v6/audits/A105-douyin-stable-token-and-search-access.md`
- `backend/tests/test_douyin_official_mcp_proxy.py`
- 抖音官方 MCP 服务广场接入文档
