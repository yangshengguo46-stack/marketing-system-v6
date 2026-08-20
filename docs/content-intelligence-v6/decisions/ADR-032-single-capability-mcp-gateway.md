---
id: ADR-032
status: accepted
date: 2026-08-20
decision: expose_one_manifest_gateway_and_keep_providers_internal
supersedes:
  - ADR-010
  - ADR-029
---

# ADR-032 单一能力 MCP 网关

## 决策

第六版产品运行时只注册一个第一方 MCP：`deerflow-capability-mcp`。Agent 只看到边界互斥的领域
Tool；空调用发现版本化 Child Manifest，精确调用携带 `manifest_version` 并再次校验授权、风险、输入
Schema、输出 Schema 和结果大小。

官方 OpenAPI、官方 SSE、登录态公开页面、浏览器和未来 MediaKit 都是网关内部 Provider。Provider
可以是模块、长驻子进程或远端服务，但不能作为平行 MCP 再注册给 Host。高层的内容根、对标分析、账号
定位、受众判断和复盘仍是业务工具；它们调用网关，不进入网关替代营销决策。

## 原因

并行注册 `douyin_openapi`、`douyin_official_mcp` 和 `douyin_community_evidence` 会产生重复工具、重复
鉴权、重复路由和相互冲突的可用性判断。Doris/Ossie 式 Manifest、能力探测、Child 调度和领域运行时正好
解决这个问题：统一的是协议入口和能力合同，不是把所有实现揉成一个文件。

## 当前实现

- 顶层为 17 个领域 Tool；七项登录态公开页面能力只作为 `douyin_public_evidence` 的 Child。
- 官方 119 项目录继续作为可追溯能力库存，不等于 119 个可调用接口。
- Child 运行时使用 DeerFlow 现有 `MCPSessionPool` 长驻复用，一次网关进程只启动一个对应子会话。
- 旧 `douyin-openapi-mcp`、`douyin-official-mcp` console entrypoint 和三个并列本机注册项已退出。
- 官方 SSE 桥模块保留为内部 Provider 候选；返回零工具时仍不可用。
- 登录态公开页面 Provider 当前只批准本机研发，生产许可问题由 A113 继续约束。

## 晋级规则

新能力先成为内部 Provider，再提供有界 Child 合同，最后通过真实调用验收。未通过的 Provider 不得新增
平行 MCP 绕开网关。MediaKit、发布、指标和账号授权在对应主线恢复前只保留内部实现，不为“目录完整”
提前暴露 Child。

