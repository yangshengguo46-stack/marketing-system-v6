---
id: A43
status: reviewed
reviewed_at: 2026-08-17
decision: adopt_one_bounded_lead_tool_with_optional_project_persistence
sources:
  - docs/content-intelligence-v6/audits/A42-douyin-public-benchmark-candidate-aggregation.md
  - backend/packages/harness/deerflow/tools/builtins/douyin_benchmark_tool.py
  - backend/packages/harness/deerflow/runtime/user_context.py
  - backend/app/gateway/services.py
  - backend/tests/test_douyin_benchmark_tool.py
---

# A43 抖音对标候选 Lead 工具审计

## 问题

A42 已经能用官方搜索跨页聚合对标候选，但它只是库函数。如何让 DeerFlow Lead
真正使用它，同时不把低层 DomainRouter、密钥、用户身份、分页回执和数据库参数
暴露给模型。

## 发现

1. Lead 只需要三个业务参数：搜索语、目标作者显示名和最大作品数。
2. 认证用户、会话、运行和选中项目都是服务端运行时上下文，不应由模型填写。
3. 没有选中项目时，读取证据仍然有价值，不应成为硬门。
4. 有选中项目时，必须先用服务端认证用户复核项目所有权，再请求平台；
   客户端伪造 owner 字段不能进入运行上下文。
5. 平台已成功返回证据而台账写入失败时，该证据不应丢失。Lead 应收到有界证据和
   `persistence=failed`，而不是底层数据库异常。
6. 一个高层业务工具就足够；无需把搜索领域 Manifest 中的 Child 全部平铺给 Lead，
   也无需新增固定对标子 Agent。

## 决定

- 注册 `collect_douyin_benchmark_candidate` 为 DeerFlow 内置 Lead 工具。
- 模型可见 Schema 只包含 `query`、`actor_label`、`max_posts`；上限仍为 `24`。
- 工具复用 A42 的官方 v2 DomainRouter 和有界 Lead 投影，不再写搜索或分页逻辑。
- 无项目时返回只读证据和 `not_selected`；有项目时才按认证用户、会话和运行
  封存到孵化台账。
- 项目不存在或不属于当前用户时，在平台请求前拒绝。
- 平台异常和存储异常只记录异常类型，向 Lead 返回固定脱敏消息。
- 返回值仍是观察证据，不产生定位、受众、爆款原因或可复制结论。

## 验收边界

离线工具、路由、证据、台账与 Gateway 回归已通过。第六版本机仍未配置
`DOUYIN_CLIENT_KEY` 和 `DOUYIN_CLIENT_SECRET`，也尚无前端项目选择器。因此本条只标记
`implemented`，不标记真实抖音回执或产品端项目入库已验收。
