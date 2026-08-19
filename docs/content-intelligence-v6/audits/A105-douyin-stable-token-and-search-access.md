---
id: A105
status: reviewed
reviewed_at: 2026-08-19
decision: use_stable_client_token_and_wait_for_search_beta_approval
sources:
  - https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/account-permission/generate-stable-client-token
  - https://developer.open-douyin.com/docs/resource/zh-CN/dop/ability/mcp-service/mcp-service-desc
  - https://developer.open-douyin.com/docs/resource/zh-CN/dop/ability/search-management/item-search
  - https://developer.open-douyin.com/product/search
  - https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/app-mgmt/test
  - https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/app-mgmt/pub-app
  - backend/packages/harness/deerflow/community/douyin_openapi/client_token.py
---

# A105 抖音稳定应用凭证与搜索准入审计

## 图三究竟是什么

图三的 `client_token` 是应用级调用凭证，不需要某个抖音用户授权。Client Key 与 Client Secret 只能
保存在本地服务端配置中；业务模块不应保存或接收手工复制的 Token。

普通 `/oauth/client_token/` 有两小时有效期，但重复获取可能使旧 Token 失效。官方同时提供
`/oauth/stable_client_token/`：有效期同为两小时，有效期内重复请求会幂等返回同一枚 Token。这才是
多个本地模块或多个 MCP 进程避免“互刷”的正确合同。

## 第六版接法

新增一个共享实现 `douyin_openapi/client_token.py`：

1. 搜索适配器和官方 MCP 桥都只调用稳定端点。
2. 同一进程按 Client Key 与 Client Secret 的哈希指纹缓存，提前 60 秒进入刷新窗口，并用异步锁合并
   并发刷新。
3. 不同测试/生产凭据使用不同缓存项；原始凭据不作为日志、回执或模型输入。
4. 业务接口明确返回 Token 无效或过期时，只作废与失败请求完全相同的当前 Token，防止迟到响应误删
   新 Token。
5. 两个独立 MCP 进程不共享 Python 内存；跨进程一致性由官方稳定端点的幂等语义保证，不能把
   “共享代码”误写成“跨进程内存缓存”。

## 真实探测

使用本地未跟踪凭据完成以下只读探测，凭据、Token 和带 Token 的 SSE URL 均未进入输出：

- 稳定应用 Token 获取成功。
- 官方 MCP SSE 初始化成功，但省略工具组时 `tools/list` 仍返回 `0`。
- 直接视频搜索 v1 与保留的 v2 合同均返回 `28001018 应用未获得该能力`。
- 控制台显示当前 IPAgent 仍为测试应用，应用基础信息和移动端包信息尚未完成；测试应用本身允许先申请
  能力，但有按创建时间递减的每日 Scope 调用上限，上线转正后才解除。

因此认证链已经接通，当前失败不是 Client Secret、Token、MCP 协议、请求头或 v1/v2 选择造成的。

聚焦验证通过 94 项，其中新增稳定凭证合同测试 4 项；后端全量套件通过
`12218 passed, 76 skipped`，零失败。

## 平台准入矛盾

官方产品页写“抖音搜索能力正式开放”，入口却仍是“立即申请内测”；现行能力文档更明确写着
“该能力为实验能力，现不对外开放”。接口文档存在和 API 调试台可见都不等于应用获得了
`aweme.dy.video_search` 或 `aweme.dy.video_search_v2`。

官方 MCP 同样要在应用的 MCP 服务广场单独申请。只有审批生效后，`tools/list` 才会出现工具；当前返回
零工具是有效的授权状态，不是本地桥故障。

## 下一步

1. 从搜索能力产品页提交内测申请，真实描述 IPAgent 在用户发起营销研究时展示带抖音来源标识的搜索
   结果、跳回抖音消费内容的场景；提交属于对外申请，必须由用户最终确认。
2. 在 MCP 服务广场确认“抖音视频搜索/图文搜索”是已开通、审核中还是未申请。若未申请，按同一真实
   场景提交，等待平台审核。
3. 完成应用基础信息与包信息并上线转正，避免测试应用后续降为零调用额度。这不会自动授予搜索权限。
4. 收到平台审批后不再改搜索代码，只重跑固定验收：稳定 Token -> MCP `tools/list` -> 精确只读调用 ->
   v1/v2 中获批合同的真实视频结果。首个成功第一方回执出现前保持 `not_live_verified`。

## 结论

图三已经按官方推荐方式接入。当前搜索链路的直接外部阻塞是搜索内测/MCP 服务尚未对该应用生效；不存在还能靠
更换 Token、读取 Cookie 或继续修改请求代码绕过的本地方案。
