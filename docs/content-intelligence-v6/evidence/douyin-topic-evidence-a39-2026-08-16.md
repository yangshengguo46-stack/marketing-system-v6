# A39 抖音选题证据第一切片

## 输入边界

- 来源：抖音 OpenAPI `search.video_search` DomainRouter 成功回执。
- 角色：固定为 `topic_evidence`。
- 采集方式：`official_openapi`。
- 不是：对标账号快照、受众画像、自有账号指标或发布实绩。

## 白名单字段

每条公开视频只保留 `item_id`、标题、公开作品链接、官方回执中的文本、作者显示名、发布时间和
点赞观察值。Manifest 版本、Catalog 版本和搜索会话 ID 进入路由回执；Lead 只看路由回执哈希。
封面、头像、临时地址、Token、Cookie、StorageState 和原始提供商响应均不进入证据快照。

## 预算投影

`EvidenceSnapshot.to_lead_projection()` 默认上限 16 KB。它先保留身份、角色、时间、覆盖、限制和
哈希，再逐条加入完整的有界代表项。下一条会越界时停止，并返回 `total_items`、`included_items`、
`omitted_items` 和 `truncated`，不以字符串截断伪装全量证据。

## 自动验证

```text
PYTHONPATH=. uv run pytest tests/test_douyin_evidence_snapshot.py -q
5 passed

PYTHONPATH=. uv run pytest \
  tests/test_incubation_ledger.py \
  tests/test_incubation_content_world.py \
  tests/test_douyin_evidence_snapshot.py \
  tests/test_douyin_openapi_router.py \
  tests/test_douyin_search_tools.py \
  tests/test_douyin_experience_search_adapter.py \
  tests/test_lead_agent_prompt.py -q
64 passed

上述联合回归再加入 `0012` 迁移、空库/旧库/并发启动、Alembic autogen 与持久化脚手架：
156 passed
```

## 尚未完成

- 生产 Tool 还没有接收选中项目上下文并自动调用 `put_artifact()`。
- 体验搜索尚未有独立 EvidenceSnapshot 适配器。
- 对标账号必须使用账号身份加多作品覆盖合同，不能复用本适配器。
- 本切片没有新跑真实抖音 API，不构成新的 live acceptance。
