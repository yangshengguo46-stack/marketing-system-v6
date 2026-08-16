# A41 抖音视频搜索 v2 与候选证据回执

## 合同

```text
endpoint: GET https://open.douyin.com/dy_open_api/v2/search/video/
scope: aweme.dy.video_search_v2
auth: stable client token
local purposes:
  topic_research -> topic_evidence
  benchmark_discovery -> benchmark_account_candidate
```

`purpose` 不进入平台请求。两种输出都经过同一白名单、数量上限和临时字段清理；候选角色额外声明
作者显示名不是稳定身份，且当前结果不是 `BenchmarkSnapshot`。

## 测试先行

旧实现的失败基线为 `11 failed, 15 passed`：端点、Scope 和固定 `topic_evidence` 均不符合新合同。
实现后聚焦结果：

```text
26 passed in 3.12s
```

覆盖端点漂移、Manifest 权限、输入/输出 Schema、候选路由、本地参数不外传、证据人口口径和
`BenchmarkSnapshot` 边界。

完整后端离线回归：

```text
DEER_FLOW_AUTH_DISABLED=false make test
11713 passed, 76 skipped, 17 warnings in 466.09s
```

## 真实探测

```text
query: 大能 腕表
purpose: benchmark_discovery
result: local_configuration_missing
missing: DOUYIN_CLIENT_KEY, DOUYIN_CLIENT_SECRET
network_request_sent: false
credential_value_exposed: false
```

这是可恢复的本地配置缺口，不是平台拒绝或 v2 合同验收。配置未跟踪凭据后必须重跑真实权限与
回执测试，才能把本切片从 `implemented` 提升为 `verified`。
