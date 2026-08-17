---
id: A52
status: reviewed
reviewed_at: 2026-08-17
decision: adopt_exact_two_grant_ledger_and_keep_live_cloud_disabled
sources:
  - backend/packages/harness/deerflow/incubation/approvals.py
  - backend/packages/harness/deerflow/persistence/incubation_ledger
  - backend/packages/harness/deerflow/community/mediakit/authorization.py
  - backend/packages/harness/deerflow/community/mediakit/driver.py
  - docs/content-intelligence-v6/audits/A51-mediakit-cloud-driver-mocked-acceptance.md
  - fourth-version paid-call ledger and history, read-only
---

# A52 MediaKit 精确批准账本

## 问题

A51 的云驱动只有一个受信授权回调。回调当时看不到项目、本地任务、完整操作摘要、素材内容摘要或
费用上限，因此任何具体实现都无法证明用户批准的正是即将执行的那一次操作。继续接真实云端会让
一项批准被换素材、换参数、换能力或换任务复用。

## 旧版教训

第四版曾允许调用方把 `paid_calls_require_explicit_approval` 关闭，也曾把批准绑定到发起 run，导致
后续执行 run 无法安全消费。修复后虽然形成了大型 paid-call 状态机，但还混入供应商、SKU、预算预留、
加密任务恢复等大量产品特定字段。第六版不迁移这套系统，只采用两个已证实的原则：批准内容由服务端
冻结；执行时原子绑定唯一幂等任务，同一任务可以恢复，另一任务不能抢占。

## 失败基线

测试先导入不存在的 `ApprovalGrant`，收集期以 `ImportError` 失败。随后冻结以下行为：

- 云处理同意与费用上限是两条不同批准，缺一不可；
- 批准必须匹配 owner、项目、素材摘要、权利引用、能力、参数、Schema、币种和金额上限；
- 过期、撤销、跨用户、跨项目、参数变化和费用变化均不能消费；
- 两个并发任务竞争同一批准对时只能一个成功；
- 同一本地任务在提交不确定或进程重启后可以幂等重试；
- 任一校验失败时两条批准都不能出现半绑定。

## 合同与持久化

新增 `ApprovalGrant`，类型固定为 `cloud_processing` 或 `fee_authorization`。两者共享同一个
`mediakit-cloud-operation-v1` 摘要；费用批准额外保存 ISO 三字母币种和正整数微单位上限。
操作摘要包含：

```text
project_id
source_ref + rights_ref + source_content_sha256
capability_domain + capability_tool + capability_arguments
expected_schema_sha256
currency + maximum_amount_micros
```

批准引用和本地任务 ID 不进入操作摘要：前者只是指向批准记录，后者在真正执行时由 SQL 原子绑定。
迁移 `0014_incubation_approval_grants` 新增 owner/project 外键、费用形状、绑定、撤销和过期约束。

首次绑定要求两条批准都未撤销、未过期、未绑定且精确匹配。两个条件更新位于同一事务，第二条失败会
回滚第一条；并发输家得到固定拒绝。绑定后批准视为已经准入，不能撤销或改绑；同一任务即使跨过原
批准有效期仍可恢复相同幂等提交，避免远端结果不确定时制造第二次调用。

## 云驱动接线

`MediaKitCloudApprovalAuthorizer` 将 A51 授权上下文映射到批准账本。云请求现在必须携带项目、预期
素材 SHA-256、币种和最高微单位金额；这些字段与能力参数共同形成操作摘要。驱动先执行本地版本和
Schema 校验，确认没有漂移后才绑定批准；随后才解析短命媒体源并调用云端。授权异常仍被 A51 的固定
错误信封脱敏。

## 当前边界

本切片没有提供前端或 Gateway 批准接口，外部调用方不能自行铸造批准；也没有注册云驱动。请求中的
`source_content_sha256` 已进入批准摘要，但真实解析器尚未把它与下载后的字节重新核对。费用上限只是
用户批准合同，尚没有可核验 MediaKit 单次报价或供应商侧强制上限，不能宣称成本已经封顶。

因此下一切片只能实现受信素材解析、内容哈希复核和结果下载物化。取得可审计价格依据并再次获得用户
明确同意前，不得调用真实 MediaKit 云任务。

## 结论

A52 将 A51 的空授权回调替换为可恢复、可审计的本地批准底座，同时没有把审批变成 Agent 推理阶段。
这是云执行真实性硬门，不评价内容，也不改变孵化、语义或选题判断。
