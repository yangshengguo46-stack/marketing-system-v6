---
id: A51
status: reviewed
reviewed_at: 2026-08-17
decision: adopt_isolated_mocked_cloud_driver_and_defer_live_registration
sources:
  - backend/packages/harness/deerflow/community/mediakit/driver.py
  - backend/packages/harness/deerflow/community/mediakit/router.py
  - backend/app/mcp_tasks/service.py
  - /usr/local/bin/mediakit-cli@0.2.0
  - fifth-version archived MediaKit source@279e5bb97e97c6875ae2c6891c2c3fa9a43f39c0, read-only
  - docs/content-intelligence-v6/audits/A49-mediakit-local-execution-and-cloud-recovery.md
  - docs/content-intelligence-v6/audits/A50-durable-task-submission-intent.md
---

# A51 MediaKit 云驱动无费用模拟验收

## 问题

A50 已经做到“先落提交意图，再调用远端”。本切片需要验证 MediaKit 云驱动能否在不把签名 URL、
本机路径、凭据或供应商原始输出写入任务表的前提下，完成幂等提交、单次查询、状态归一、重启恢复和
结果物化；同时不能为了测试而调用真实云任务或产生费用。

## 失败基线

测试先导入尚不存在的 `MediaKitCloudDriver` 与授权、查询、物化合同，收集期以 `ImportError` 失败。
首轮实现后，安全复核又固定四个失败：授权异常原文泄露、稳定引用可夹带签名 URL、物化异常泄露
临时下载地址、物化结果可把供应商 URL 当成持久产物引用。随后增加来源解析异常脱敏、恢复哈希篡改
和进程重启后查询 Schema 漂移测试。

## 审计发现

1. 本机 `mediakit-cli 0.2.0` 的 `shared query-task --schema` 将状态描述为
   `processing / success / failed`，但同一版本归档源码和错误码文档使用
   `queued / running / completed / failed / canceled / cancelled`。驱动必须在边界内兼容并归一，
   不能让供应商枚举成为业务状态机。
2. CLI 提供 `--poll-complete`，但它会让单个进程拥有整个轮询周期。第六版必须每次只查询一次，
   由 DeerFlow 租约工作进程决定下一次查询，才能在重启后恢复。
3. 云提交所需的 `video_url` 是短命执行数据。持久提交意图只能保存稳定 `source_ref` 和
   `rights_ref`，领取租约并通过授权后才解析 URL。
4. 供应商完成回执中的输出 URL 仍是执行数据。只有下载、哈希和质检后的内部
   `artifact://` 引用可以进入任务结果。

## 实现决定

- 云请求合同精确限定为稳定来源/权利引用、能力域与工具、非敏感能力参数、预期 Schema 哈希、
  云处理同意引用和费用授权引用；URL、路径、凭据字段和超预算参数在授权前拒绝。
- 驱动先调用受信授权器，再动态发现能力与 `query-task` Schema，随后解析一次短命来源。
  本地任务 ID 固定映射为 MediaKit `client_token`，使 A50 的提交重试保持同一幂等键。
- 持久恢复数据只含稳定引用、CLI/Schema/请求哈希和授权引用。供应商 `request_id` 只保存哈希；
  原始远端任务 ID 只存在内部任务表。
- 每次 `get_status()` 只执行一次 `query-task`，不使用 `--poll-complete`。供应商状态映射为 DeerFlow
  的 `submitted / working / completed / failed / cancelled`，未知状态确定性失败而不猜测。
- 完成结果交给受信物化器；物化器必须以本地任务 ID 幂等地下载、校验并返回内部
  `artifact://` 引用、内容 SHA-256、MIME 和字节数。原始供应商输出只在该调用内存中可见。
- 授权器、来源解析器和物化器的异常统一改写为固定错误信封，并用 `from None` 阻止异常链把临时
  URL 或供应商消息带入日志。恢复字段在查询前重新校验。
- MediaKit 没有已审计取消能力，驱动明确不伪造取消。本实现只能走 A50 `enqueue()` 路径。

## 当前边界

本切片通过的是隔离、无费用的模拟 CLI 生命周期，不是 MediaKit 云服务验收。驱动没有注册到
Gateway，也没有具体授权器、平台媒体解析器、下载物化器或能力专属输出质检。ASR、OCR、场景切分
等真实能力仍必须分别取得用户云处理同意和费用授权，并通过真实任务回执后才能标记可用。

## 结论

A50 的持久提交意图已能承接一个安全的 MediaKit 云驱动，W04 的“提交与恢复合同”通过模拟验收。
下一切片应实现本地受信依赖和一个明确能力的真实验收，不得直接把通用驱动注册成所有 MediaKit
能力已经可用，也不得回到 Agent 内长轮询。
