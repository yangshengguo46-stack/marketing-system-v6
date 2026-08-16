---
id: A49
status: reviewed
reviewed_at: 2026-08-17
decision: adopt_local_execution_and_defer_cloud_submission_until_durable_intent
sources:
  - backend/packages/harness/deerflow/community/mediakit/router.py
  - backend/packages/harness/deerflow/incubation/media.py
  - backend/app/mcp_tasks/service.py
  - backend/packages/harness/deerflow/persistence/mcp_tasks
  - /usr/local/bin/mediakit-cli@0.2.0
  - fifth-version E15 MediaKit experiment, read-only
---

# A49 MediaKit 本地执行与云任务恢复审计

## 问题

A44 只完成动态 Schema 和短命媒体来源边界。W04 继续执行时，需要同时回答：本地任务如何形成
可信输入输出回执，云端异步任务能否直接接入 DeerFlow 的持久轮询器，以及第五版实现是否可以迁移。

## 发现

1. 本机 `mediakit-cli 0.2.0` 的 `probe-video-metadata` Schema 描述云端提交结果
   `task_id/request_id`，但 `--local` 真实返回 `format_meta`、`video_stream_meta` 和
   `audio_stream_meta`。其 Output Schema 没有必填字段且允许额外字段，真实本地结果与空对象都会通过
   纯 JSON Schema 校验。
2. 第五版 E15 已真实运行元信息、ASR、OCR 和场景切分，但云任务通过单个同步函数提交并
   `--poll-complete`。进程中断后没有持久任务所有者，不能作为第六版恢复实现迁移。
3. DeerFlow 已有租约、并发轮询、错误重试和过期租约恢复的 `McpTaskService`。其内部模型实际是
   协议中立的，但当前提交顺序是“远端提交成功后再落库”；落库失败时要求驱动取消远端任务。
4. MediaKit CLI 只有提交与 `shared query-task`，没有已审计的取消能力。因此直接注册驱动会在
   提交后落库失败时留下未知云任务。`client_token` 幂等有帮助，但不能替代持久提交意图和对账。
5. `mcp_tasks` 当前没有对外 REST 路由，适合保存恢复所需的内部原始任务句柄；业务产物仍只应保存
   任务 ID 哈希、输入输出哈希、授权和版本回执。

## 决定

- 先实现无云费用的本地文件执行。命令输入和原始输出仅存在执行内存，错误不包含参数或供应商响应。
- 本地源文件在执行前后各计算一次 SHA-256；内容变化即失败，不能给变化后的文件补写成功回执。
- 动态 Output Schema 继续作为第一层兼容检查；每一种可持久观察另有窄语义合同。首个合同只接受
  真实视频元信息，拒绝把云端 `task_id` 或空对象冒充成本地元信息。
- `MediaSourceReceipt` 在产物层带证据角色，`MediaObservationSnapshot` 自动继承该角色；
  `topic_evidence` 与 `benchmark_evidence` 不会因共用 MediaKit 而混料。
- 云端 ASR/OCR/场景切分暂不注册。下一切片必须先增加“落库提交意图 -> 幂等远端提交 -> 绑定句柄”
  或证明等价恢复机制，再复用 DeerFlow 租约轮询；不得实现无效取消或回到 Agent 内长轮询。

## 当前边界

本地 `probe-video-metadata` 已真实执行并形成内容寻址回执。它只证明媒体执行谱系与机器元信息，
不证明视频讲了什么、账号为何成功或当前用户应当复制什么。制作能力、云端感知、输出文件质检、
真实抖音媒体解析器和跨视频分析仍未验收。
