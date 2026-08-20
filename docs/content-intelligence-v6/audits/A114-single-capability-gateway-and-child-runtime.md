---
id: A114
status: adopted_for_local_runtime
date: 2026-08-20
decision: merge_parallel_douyin_mcp_surfaces_into_one_manifest_gateway
sources:
  - https://github.com/apache/doris-mcp-server
  - https://ossie.apache.org/
  - https://github.com/pazwusimple-netizen/douyin-mcp
---

# A114 单一能力网关与 Child Runtime 验收

## 目标

把 A113 已跑通的抖音搜索、详情、评论、回复、创作者资料、创作者作品和分享链接解析，迁入此前按
Doris/Ossie 思路建立的 Manifest/领域路由 MCP。系统不再让 Agent 同时面对官方 OpenAPI、官方 MCP 和
社区 MCP 三套入口。

## 测试先行

新增测试先固定以下边界，再写实现：

- 官方 119 项库存必须原样保留，七个公开证据 Child 另行登记。
- 顶层只能出现领域 Tool，不能出现七个原始采集动作。
- Child 必须绑定最新 Manifest 并通过双向 Schema；不合格回包不能把未知字段或凭证值带回。
- 第一方发行包只能保留 `deerflow-capability-mcp` 一个 console entrypoint。
- 示例配置只能保留 `deerflow_capabilities` 一个产品能力 MCP 注册项。
- Child 只能调用审阅白名单，并复用 DeerFlow 的长驻 MCP 会话池。

最终聚焦网关、抖音 Provider、会话池、缓存与 doctor 的回归为 `166 passed`；全量抖音测试并带上本轮
TikTok 对标回归为 `94 passed`。格式化与 Ruff 检查均通过。

后端全套非 live 回归完成 `12278 passed / 75 skipped`，唯一失败是新增说明让原本只剩 2 字节余量的
`backend/AGENTS.md` 超过软预算；压缩说明后对应 12 项指导文件测试全部通过，没有功能测试失败。

## 接线结果

`deerflow-capability-mcp` 当前列出 17 个领域 Tool。`douyin_public_evidence` 的 Manifest 精确披露七个
只读 Child，其输入输出均有字段、数量和字节上限。Child 调度器启动 A113 的固定本地只读运行时，原始
MCP 不再单独注册给 DeerFlow Host。

本机 `extensions_config.json` 已机械迁移：旧三项被删除，只启用 `deerflow_capabilities`；密钥值只在本地
结构化搬运，未打印、未写入 Git。MCP cache 重置成功，Host 实测只发现 17 个领域，未发现任何旧社区
前缀或裸 Child。

## 真实验收

通过统一 Router 跑完：5 条搜索、视频详情、5 条评论、创作者资料、5 条作品、分享链接解析和评论回复，
七项均无错误。改为长驻 Child 会话后，搜索、详情和三条账号作品只启动一次子进程，整链约 7.44 秒。

最终再从 DeerFlow Host 执行：

```text
tools/list
  -> douyin_public_evidence
  -> discover Manifest
  -> search_videos("黄金礼品 人情世故")
  -> 3 条真实抖音结果
```

返回元数据明确绑定 `public_evidence` 领域。原始 Cookie、页面、临时媒体地址和大回包没有进入 Host 输出。
最终 `make doctor` 状态为 `Ready`，同时识别官方 API Provider 与公开证据 Child；本机启用配置只含
`deerflow_capabilities` 一个 MCP Server。

## 保留边界

一个 MCP 入口不等于一个巨型业务模块。对标分析、内容根、账号定位、受众、形式与复盘继续保留自己的
业务对象；网关只提供事实采集与执行能力。通用 GitHub、Postgres 等 DeerFlow 示例可以保持默认关闭，
但第六版产品本机运行时只启用统一能力网关。

A113 上游仓库的 LICENSE/README 仍有冲突，因此当前 Child 只批准本机研发。下一步可以在相同 Child
合同下逐项替换成洁净浏览器实现；替换 Provider 不得改变 Agent 工具面或业务台账。
