# A52 MediaKit 精确批准回执

## 失败基线

```text
tests/test_incubation_approval_grants.py collection:
ImportError: cannot import name 'ApprovalGrant' from 'deerflow.incubation'
```

测试没有通过 mock 放宽，而是新增批准合同、SQL 表、迁移和实际仓储接线。

## 已验证性质

- `cloud_processing` 不携带金额，`fee_authorization` 必须携带币种和正数微单位上限。
- 两条批准同时绑定同一 owner、项目和 `mediakit-cloud-operation-v1` 摘要。
- 摘要随素材内容 SHA、能力 Schema、能力参数或费用上限变化；只更换批准记录引用不会改变操作本身。
- 过期、撤销、跨用户、跨项目、操作变化和费用变化均失败关闭，且不会半消费批准。
- 两个任务并发竞争时只有一个成功；已绑定任务可在过期后恢复，其他任务不能复用。
- 本地 CLI/Schema 漂移在批准绑定前停止；授权失败后不解析媒体源、不发云请求。
- 迁移 `0014_incubation_approval_grants` 可从 `0013` 的版本化数据库升级。

## 聚焦回归

```text
approval ledger + 0014 migration + MediaKit cloud driver:
26 passed in 4.72s

MediaKit + durable tasks + incubation ledger + migrations:
125 passed, 1 warning in 14.88s

first full backend run:
1 failed, 11803 passed, 76 skipped
only failure: backend/AGENTS.md was 178 bytes over its soft budget

guidance budget regression after compaction:
1 passed in 1.71s

final full offline backend run:
11804 passed, 76 skipped, 17 warnings in 425.82s
```

第一次全量失败没有运行时或业务失败。压缩仓库级摘要、保留完整 A52 专项审计后，预算测试和第二次
全量均通过。

## 未发生

- 未创建 Gateway 或前端批准入口。
- 未把批准记录放入模型上下文或聊天记忆。
- 未注册 MediaKit 云驱动。
- 未解析或上传真实用户素材。
- 未调用云服务，未产生费用。
- 未证明请求中的预期素材哈希已经与实际字节相同。
- 未证明 MediaKit 费用可被供应商侧限制在批准上限内。
