---
id: A56
status: reviewed
traced_at: 2026-08-17
reviewed_at: 2026-08-17
decision: adopt_exact_review_and_atomic_grant_issuance_keep_execution_disabled
sources:
  - docs/content-intelligence-v6/audits/A55-mediakit-enhance-video-preflight.md
  - backend/packages/harness/deerflow/community/mediakit/approval_request.py
  - backend/packages/harness/deerflow/persistence/incubation_ledger/sql.py
  - backend/app/gateway/routers/incubation_projects.py
---

# A56 MediaKit 精确批准 API 审计

## 问题

A55 能生成确定性报价，但报价没有成为用户可审阅、可明确确认的业务对象。直接让客户端提交
`operation_sha256` 会形成盲签：客户端声称批准的摘要可能不是服务器将执行的素材、参数和金额。
逐张写入两类凭证还可能只成功一张；随机凭证 ID 则会让双击和网络重试生成重复批准。

## 已采用合同

1. 只有服务器生成的 `MediaKitFeeQuote` 能构造批准请求。构造时重新核对项目、素材内容哈希、能力、
   参数摘要、Schema、价格证据、报价摘要、估值、币种、金额上限和有效期。
2. 批准请求封存为内容寻址的 `mediakit_cloud_approval_request`。父级必须是同项目、角色为
   `user_material`、并带 `media_source_receipt` 谱系的 `media_observation`；对标证据不能借此取得
   云处理授权。
3. 批准载荷和审阅响应不含 `source_ref`、`rights_ref`、临时 URL、本机路径、凭据或原始媒体。
4. GET 审阅接口展示能力、Schema、版本、素材时长、输出分辨率/帧率、费率、估值、用户上限、
   有效期和供应商硬封顶状态。它不签发凭证。
5. POST 确认必须精确回传报价摘要、币种和金额，并分别确认云处理、费用授权和“供应商无单任务
   硬封顶”。任何字段变化、过期、项目越权或错误产物类型均失败。
6. 云处理与费用凭证使用报价产物推导的稳定 ID，由一个数据库事务同时创建。重试身份忽略后来请求的
   `issued_at`，保留首个成功签发时间；操作、币种、金额或到期时间不同仍冲突。
7. 本入口只产生未绑定批准，不创建 `mcp_task`、不消费批准、不注册驱动、不上传或调用云能力。

## 失败基线

```text
IncubationLedgerRepository.issue_approval_pair: missing
MediaKitCloudApprovalRequest: missing
GET approval review: 404
POST exact approval: 404
same quote with later issued_at: ApprovalGrantConflictError
```

## 验收结果

- 聚焦批准与 MediaKit 回归：`73 passed, 1 warning`。
- 所有权、谱系、迁移、Gateway 与 MediaKit 联合回归：`141 passed, 1 warning`。
- 阻塞 I/O 回归：`71 passed, 2 warnings`。
- 完整离线后端回归：`11849 passed, 76 skipped, 17 warnings in 428.20s`。

## 当前边界

批准请求的生产生成入口和前端确认界面尚未接线，云驱动也仍未注册。供应商没有单任务费用硬封顶，
所以签发凭证不代表可以执行；真实云验收仍需新的明确用户指令和独立回执。本轮没有外部调用或费用。
