---
id: ADR-047
status: accepted
date: 2026-08-22
related:
  - A141-video-production-safety-foundation.md
  - ADR-018-artifact-graph-orchestration.md
  - A50-durable-task-submission-intent.md
---

# ADR-047 Ark 生成采用最多提交一次边界

## 决定

对未提供或未审计稳定生成幂等键的付费 Provider，持久任务必须使用 `at_most_once`，并在进入外部提交代码前
持久化 `submission_started_at`。一旦这个边界存在但没有稳定远端任务 ID，状态只能进入
`submission_unknown` 并等待对账，不能自动重新提交。

Ark 视频首个候选进一步限定为精确 `ProductionPlan` 下的单资产、单动作、单装配、纯文生视频 V1。模型、
显式画幅/分辨率/时长、其余白名单参数和提示全部进入内容哈希；参考资产、对象存储/网络 URL、本机路径、
凭据、callback、任意 extra body 和供应商 escape hatch 不进入合同。该对象目前只是内容寻址 Pydantic 请求，
不是已持久化 `ArtifactEnvelope`。ArkCLI 适配器必须先验证认证与资源，再验证公共模型声明的参数，视频只
异步提交并独立轮询。

## 与可重试任务的区别

默认 `idempotent_retry` 保持现有行为，只能用于已经证明同一本地任务键会在 Provider 端收敛到同一远端
任务的驱动。不能因为 DeerFlow 有本地任务 ID，就假设任意供应商调用是幂等的。

```text
idempotent_retry:
  持久意图 -> 可用同一供应商幂等键恢复提交 -> 绑定远端句柄

at_most_once:
  持久意图 -> 写 submission_started_at -> 只调用一次
  -> 有句柄则轮询
  -> 无法判定则 submission_unknown，永不自动重提
```

## 注册门

合同、CLI 适配器和任务策略通过自动测试后仍不注册。生产接线至少还须同时满足：

1. Gateway 只从认证 owner/project 和精确 `ProductionPlan` 生成并持久化请求；
2. 冻结 profile/account/tenant/project/region、公共模型或 Endpoint 解析出的底层模型身份、显式有效参数与
   当前价格证据，形成未过期报价；
3. 权利、云处理和费用批准精确绑定同一操作哈希与任务；
4. Ark 驱动只能以 `at_most_once` 入队，不能调用旧的先提交后落库入口；
5. 结果进入私有物化、媒体类型/大小/哈希/QC 后才形成 `MediaArtifact`；
6. 重试安全的认证/资源/参数预检在费用标记前完成；费用标记后的租约覆盖或安全续租整个付费提交，双 worker
   超时测试证明不能产生第二次 `+gen` 或丢失唯一任务 ID；
7. 注册层只接受结构化脱敏错误和经过审计的 shell-free argv runner，并核实 ArkCLI/SDK 内部不会对创建请求
   做未受控重试；
8. 一次全新、用户明确批准的真实小额任务完成并保留回执。

## 拒绝

- 拒绝在 Lead、Skill 或 shell 中直接运行付费 `arkcli +gen`。
- 拒绝把“异常”一律当作未提交成功。
- 拒绝清除 `submission_unknown` 标记后静默重试。
- 拒绝把第五版项目 JSON 台账或自有视频计划作为恢复真相。
- 拒绝用一个对标视频、一个生成结果或供应商原始输出改写账号方向与事实主张。
- 拒绝把“未注册到 Tool/Gateway”表述为主机层绝对不可执行；Lead 仍有通用 Bash，正式启用前必须把供应商
  mutation 约束成技术边界，而非只依赖 Skill 文案。

## 后果

供应商短时故障下，at-most-once 可能比自动重试更保守，并需要人工对账；这是避免重复扣费的有意取舍。
后续若 Ark 提供并经真实验收稳定幂等键，可以新建 ADR 将特定操作切到 `idempotent_retry`，不能仅凭文档字段
名或本地任务 ID 推断。
