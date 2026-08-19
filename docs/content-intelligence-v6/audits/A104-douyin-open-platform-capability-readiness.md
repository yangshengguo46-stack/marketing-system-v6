---
id: A104
status: reviewed
reviewed_at: 2026-08-19
decision: use_a_generated_readiness_matrix_and_activate_by_auth_surface
sources:
  - https://developer.open-douyin.com/docs/resource/zh-CN/dop/ability/mcp-service/mcp-service-desc
  - https://developer.open-douyin.com/docs/resource/zh-CN/dop/ability/opensdk/user-authorization/solution
  - https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/common-params
  - backend/packages/harness/deerflow/community/douyin_openapi/catalog_snapshot.json
  - backend/packages/harness/deerflow/community/douyin_openapi/readiness.py
  - docs/content-intelligence-v6/evidence/douyin-openapi-live-observation-2026-08-19.json
  - docs/content-intelligence-v6/evidence/douyin-openapi-readiness-2026-08-19.md
---

# A104 抖音开放平台全能力就绪审计

## 要解决的问题

过去把“官方目录存在”“本地 MCP 能列出领域”“本地声明了 Scope”“平台真实允许调用”混成了一个
“已接通”状态。结果是前脚说接好，后脚真实搜索又打开网页或收到权限错误。本轮不再逐接口口头判断，
而是把 119 项目录、代码适配、鉴权类型、应用产品线和真实回执合成一张可重复生成的状态矩阵。

## 五层状态

1. **目录层**：官方目录是否仍有该能力，只证明文档存在。
2. **合同层**：当前 URL、方法、Scope、应用类型和请求/响应 Schema 是否已追踪。
3. **代码层**：是否已有薄适配器、OAuth 驱动、Webhook 入口或官方 MCP 工具。
4. **授权层**：平台是否真的给当前应用或当前授权用户开通该 Scope/服务。
5. **回执层**：最小真实调用是否返回第一方成功结果。只有这一层通过才能写 `live_verified`。

## 当前应用真实状态

- 官方目录共 `119` 项，但其中 `75` 项属于小程序、生活服务、小程序推广、服务市场、分身技能或
  汽水音乐等独立产品/合作计划，不能因为当前移动/网站应用存在就算作已开通。
- 当前通用移动/网站应用候选面剩余 `44` 项：`12` 项旧合同需重查，`29` 项合同已定位但没有适配器，
  图文搜索 `1` 项适配器已写但未声明获批权限，视频搜索 `1` 项被平台以 `28001018` 拒绝。
- `client_token` 获取是真实通过的鉴权基础设施，因此全表有 `1` 项真实成功；它不是营销业务能力。
  当前真实业务能力通过数仍为 `0`。
- 官方 MCP 普通发现、stable token 发现和显式工具组 `28` 发现均为 `0` 个工具。协议初始化成功不等于
  服务已获批。

## 正确接入方式

### 应用级只读能力

搜索等能力使用 `client_token`。先在控制台完成对应能力或 MCP 服务审批，再将**实际获批** Scope 写入
本地未跟踪配置，最后用同一只读请求保存第一方回执。代码不能替平台授予权限；本地配置也不能冒充
控制台审批。

官方 MCP 的控制台路径是“移动/网站应用 → MCP 服务广场 → 选择服务 → 立即开通”。抖音官方服务需要
填写申请并等待审核，官方说明最长约五个工作日；通过后对应“能力管理”状态才会变为“已开通”。第三方
MCP 的自动开通规则不能套到抖音官方能力上。

### 用户授权账号能力

公开资料之外的自有/客户账号、粉丝、作品、指标和发布能力需要用户 OAuth：授权跳转、服务端回调换取
`access_token + open_id`、刷新、撤销和账号级令牌保险库。应用级 `client_token` 不能代替这一链路，
也不能用于读取竞争对手的私有粉丝画像。

OAuth 的平台前置是应用已创建并上线，而且相应 Scope 已在“能力管理”获批；之后仍要由具体用户确认
授权。调试台扫码拿到的用户令牌只能用于验收，不能代替产品中的账号绑定和服务端令牌生命周期。

### Webhook 能力

回调类能力必须进入服务端接收器，完成验签、幂等、重放防护、原始回执封存和业务对象映射。它们不是
Agent 主动调用的 Tool。

### 独立产品与合作计划

小程序、生活服务、推广计划、服务市场、分身技能和汽水音乐分别走自己的应用、资质或合作审核。它们
保留在总目录中，但不会自动暴露给当前 Agent，也不计入当前应用完成度。

## Agent 接线

Lead 继续只看 16 个业务领域，不直接接收 119 个静态 Schema。领域发现先查询就绪状态：官方 MCP 真正
出现只读工具时可减少 HTTP 适配；用户级能力走 OAuth 驱动；回调走 Webhook Inbox；写操作仍需领域适配、
所有权和不可逆审批。目录更新和真实回执由确定性代码生成，不能依靠聊天记忆。

## 下一步顺序

1. 在抖音控制台查清视频搜索和 MCP 服务的审批状态；平台通过后重跑同一验收，不能继续改本地搜索代码。
2. 第六版实现账号 OAuth、回调和令牌保险库，这是粉丝、作品、指标与发布真正可用的共同前置。
3. 官方 MCP `tools/list` 首次非空后，保存工具名、Schema 和安全注解快照，再映射进现有 16 个领域。
4. 只为业务需要且平台已授权的能力补薄适配器；禁止为了“119 全覆盖”实现不可用或不属于当前产品线的接口。

## 复现

```bash
backend/.venv/bin/python scripts/render_douyin_openapi_readiness.py
backend/.venv/bin/python scripts/render_douyin_openapi_readiness.py --check
```

生成物不包含 Client Key、Client Secret、token、Cookie 或带 token 的 SSE URL。
