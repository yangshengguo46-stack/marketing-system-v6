---
id: A103
status: reviewed
reviewed_at: 2026-08-19
decision: connect_official_sse_but_do_not_claim_capability_until_tools_exist
sources:
  - https://developer.open-douyin.com/docs/resource/zh-CN/dop/ability/mcp-service/mcp-service-desc
  - https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/account-permission/client-token/
  - https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/account-permission/generate-stable-client-token
  - backend/packages/harness/deerflow/community/douyin_openapi/official_mcp.py
  - extensions_config.json
---

# A103 抖音官方 MCP SSE 真实握手审计

## 问题

应用控制台给出了 `https://open.douyin.com/sse`、Client Key 和 Client Secret。需要确认这是不是
另一把 API Key、如何接入 DeerFlow，以及它能否替代当前手写 OpenAPI 适配器。

## 官方合同

- SSE 地址固定为 `https://open.douyin.com/sse`。
- 必填查询参数 `token` 可使用应用级 `client_token`；涉及授权用户的 MCP 使用 OAuth
  `access_token`。
- 可选 `tool_group_aid` 接收已开通工具组 ID，省略时应返回该应用已开通的全部工具。
- 官方 MCP 服务需要在服务广场单独申请；官方说明审批最长可到五个工作日。服务通过后，对应
  能力管理状态才变为已开通。

## 2026-08-19 真实结果

使用本地未跟踪凭据分别完成两次只读握手，凭据、token 和带 token URL 均未进入输出、日志或文档：

1. 普通 `client_token` 获取成功，官方返回有效期 `7200` 秒。
2. MCP `initialize` 成功，服务端标识为 `mcp server gateway` 版本 `1.0.0`。
3. 省略 `tool_group_aid` 的 `tools/list` 返回 `0` 个工具。
4. 使用现有 stable client token 再测，结果同样为 `0` 个工具，排除 token 类型误用。
5. 对控制台页面路径中的候选工具组 `28` 显式传入 `tool_group_aid`，结果仍为 `0` 个工具，排除遗漏
   工具组筛选参数。
6. DeerFlow 自身加载链成功同时启动 16 个本地抖音领域入口和官方桥；官方桥贡献工具数仍为 `0`。
7. 同一应用的直接 v1/v2 视频搜索均收到官方错误 `28001018 应用未获得该能力`。因此不能把能力目录、
   MCP 握手或本地 16 个领域入口记为视频搜索已接通。

## 实现

- 新增 `douyin-official-mcp` 本地 stdio 桥。A105 后续将其与直接 OpenAPI 搜索统一到
  `stable_client_token` 实现；各进程在两小时有效期内本地缓存，而官方稳定端点保证跨进程重复获取
  幂等返回同一 Token，避免普通 Token 互刷。
- token 只在内存中拼入官方 SSE URL；异常统一脱敏，不打印该 URL。
- 动态读取全部分页工具；可用 `DOUYIN_MCP_TOOL_GROUP_AIDS` 缩小到控制台给出的精确工具组。
- 通用桥只执行官方明确标为只读的工具。写工具或缺少安全标注的工具必须另建经过审计的领域适配器，
  并保留账号、内容、费用和不可逆操作审批。
- 原 119 行目录与两个手写搜索适配器暂不删除；官方 MCP 真实工具尚未出现，当前不存在可做的等价验收。

## 验收余项

1. 控制台 MCP 服务状态必须显示已开通，而非申请中或仅拥有 OpenAPI 目录入口。
2. 不指定工具组时，真实 `tools/list` 至少返回一个工具，并保存不含凭据的名称、Schema 与注解快照。
3. 选择一个只读工具完成真实调用，保存官方回执和错误边界。
4. 视频搜索只有在返回真实作品结果后，才替换现有失败的直连适配器并进入选题/对标证据链。
5. 需要账号授权的作品、粉丝、发布和指标能力另走 OAuth，不得拿应用 token 冒充用户授权。

稳定 Token 的最终实现与搜索内测准入断点见 A105。

## 结论

这条 SSE 是正确且更省维护的官方 MCP 通道，不是另一把独立 API Key。代码接线已经通过，但应用当前
有效工具数为零，阻塞点在抖音侧能力开通状态。现阶段状态是“连接已建立、能力未授权”，不是“抖音生态
已经全部接通”。
