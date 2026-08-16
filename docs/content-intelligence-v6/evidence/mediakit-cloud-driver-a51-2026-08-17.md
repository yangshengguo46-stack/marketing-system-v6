# A51 MediaKit 云驱动模拟回执

## 审计证据

```text
mediakit-cli version:
0.2.0

mediakit-cli shared query-task --schema:
status description = processing, success, failed

archived source commit:
279e5bb97e97c6875ae2c6891c2c3fa9a43f39c0

archived source status set:
queued, running, completed, failed, canceled, cancelled
```

归档源码只读核对；没有执行供应商请求。驱动同时接受 Schema 描述与源码状态，随后归一为 DeerFlow
状态。每次查询命令都不含 `--poll-complete`。

## 失败基线

```text
initial contract collection:
ImportError: cannot import name 'MediaKitCloudAuthorizationContext'

first security review:
4 failed, 7 passed
```

四个失败分别证明授权异常、稳定引用、物化异常和产物引用尚有泄露或持久化缺口；修复前测试没有
放宽。

## 聚焦回归

```text
MediaKit cloud driver:
14 passed in 3.40s

MediaKit + durable tasks + incubation lineage:
78 passed, 1 warning in 7.58s

ruff format/check:
passed
```

第一次完整回归仅有 `backend/AGENTS.md` 超过仓库指导文件软预算这一项失败：
`11791 passed, 76 skipped, 1 failed`。将新增规则压缩到原预算内并单测后，最终完整离线回归为：

```text
DEER_FLOW_AUTH_DISABLED=0 full backend suite:
11792 passed, 76 skipped, 17 warnings in 417.45s
```

警告均为既有依赖弃用、测试密钥长度和模型参数提示；本切片没有新增警告类型。

## 已验证性质

- 授权发生在 Schema 发现、来源解析和远端提交之前；拒绝后调用次数为零。
- 提交使用持久本地任务 ID 作为 `client_token`；短命输入 URL 和原始 `request_id` 不进入
  `driver_data`。
- 队列、处理中、成功、失败和取消状态被确定性归一；一次轮询只发一次查询。
- 进程重启后重新发现的 `query-task` Schema 与持久哈希不一致时，在供应商查询前停止。
- 被篡改的哈希或稳定引用不能从恢复路径绕过合同。
- 完成回执先物化为内部 `artifact://` 引用和内容哈希；任务表不含供应商输出 URL。
- 授权、来源解析和物化异常只返回固定消息，不包含测试中的临时地址或令牌样例。

## 未发生

- 未注册 MediaKit 云驱动到 Gateway 或 Lead。
- 未上传、下载或处理真实用户素材。
- 未调用 MediaKit 云服务，未产生费用。
- 未声明 ASR、OCR、场景切分或其他具体云能力已经生产可用。
