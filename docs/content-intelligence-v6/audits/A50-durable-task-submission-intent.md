---
id: A50
status: reviewed
reviewed_at: 2026-08-17
decision: adopt_durable_submission_intent_before_mediakit_cloud_driver
sources:
  - backend/app/mcp_tasks/service.py
  - backend/packages/harness/deerflow/mcp/tasks
  - backend/packages/harness/deerflow/persistence/mcp_tasks
  - backend/packages/harness/deerflow/persistence/migrations/versions/0013_mcp_task_submission_intent.py
  - docs/content-intelligence-v6/audits/A49-mediakit-local-execution-and-cloud-recovery.md
---

# A50 持久任务提交意图审计

## 问题

A49 证明 DeerFlow 已有的租约轮询器可以承接云媒体任务，但旧 `submit()` 会先调用远端、再保存
任务句柄。若数据库写入失败，只能依赖驱动取消远端任务；MediaKit CLI 没有已审计的取消能力，不能
沿用这条路径。

## 失败基线

测试先要求一个尚不存在的 `submission_pending` 状态和 `CLAIMABLE_TASK_STATUSES`，因此在收集期
以 `ImportError` 失败。随后测试固定三条恢复性质：入队不得调用远端、后台提交后原子绑定句柄、
绑定落库失败后以同一本地任务 ID 重试且不得调用取消。

## 实现

1. 新增 `submission_pending`。它可被后台租约领取，但不是远端可轮询状态，也不会被
   `TaskSnapshot.is_pollable` 误判。
2. `enqueue()` 只写入本地任务 ID、稳定提交参数和下一处理时间，不调用驱动。
3. 后台领取提交意图后构造 `TaskSubmitRequest`，把已经落库的本地任务 ID 交给驱动；支持这条路径
   的驱动必须把它映射到供应商幂等键，例如 MediaKit `client_token`。
4. 远端返回后，`bind_submission()` 在租约仍属于当前工作进程且未过期时，原子写入远端任务 ID、
   初始状态和驱动恢复数据，并清除提交参数。
5. 远端调用失败会释放租约并延迟重试；远端已成功但绑定抛错时不取消任务，租约过期后以相同幂等键
   重新提交并对账。
6. 迁移 `0013_mcp_task_submission_intent` 保留旧任务，将 `remote_task_id` 改为可空并增加
   `submit_arguments`。真实旧 `0012` SQLite 表升级测试确认记录不丢。
7. 旧 `submit()` 保持原行为，避免改变已有支持取消补偿的驱动；MediaKit 云驱动只能使用新路径。

## 安全边界

- `submit_arguments` 是内部恢复数据，不是模型、前端或业务产物。不得保存 API Key、Cookie、
  StorageState、临时签名 URL 或本机路径。
- MediaKit 后续只保存稳定 `source_ref`、能力名、Schema 版本、授权引用和非敏感选项；执行时再在
  所有权边界内解析短命上传地址。
- 原始远端任务 ID 只存在内部任务表；项目事实台账保存其哈希和业务回执，不将句柄放进 Lead 上下文。
- 只有明确支持幂等提交的驱动可以调用 `enqueue()`。本切片没有注册 MediaKit 云驱动，也没有发起
  云端请求或产生费用。

## 结论

“先落意图、后调远端、再绑定句柄”的恢复窗口已经闭合，A49 的架构阻塞解除。W04 仍未完成：下一
切片需要实现 MediaKit 云驱动、动态 Schema 参数适配、费用与云处理授权、状态查询、输出下载和
哈希质检，并用无费用模拟回执先验收。
