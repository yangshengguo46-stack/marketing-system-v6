# A50 持久任务提交意图回执

## 失败基线

```text
ImportError: cannot import name 'CLAIMABLE_TASK_STATUSES'
```

测试在实现前即要求 `submission_pending` 可领取但不可轮询，并要求入队、后台绑定、失败恢复和迁移
行为。

## 聚焦回归

```text
task model/service/repository:
29 passed in 4.42s

task runtime + migration/bootstrap:
65 passed in 10.61s

ruff format/check:
passed
```

## 已验证性质

- `enqueue()` 返回前只存在本地提交意图，驱动调用次数为零。
- 后台工作进程使用已持久化的本地任务 ID 调用驱动并绑定远端句柄。
- 绑定落库失败后再次提交仍使用同一 ID，且取消调用次数为零。
- 过期租约不能覆盖任务；提交参数在成功绑定后清除。
- 从真实 `0012` 表结构升级后，旧远端句柄保持不变，新增列为空，迁移 head 为
  `0013_mcp_task_submission_intent`。

## 未发生

- 未注册或调用 MediaKit 云驱动。
- 未上传素材、未调用供应商 API、未产生费用。
- 未把 API Key、Cookie、临时 URL 或本机路径写入测试、日志或台账。

## 全量回归

```text
DEER_FLOW_AUTH_DISABLED=0 full backend suite:
11778 passed, 76 skipped, 17 warnings in 426.42s
```

警告均为既有依赖弃用、测试密钥长度和模型参数提示；本切片没有新增失败或警告类型。
