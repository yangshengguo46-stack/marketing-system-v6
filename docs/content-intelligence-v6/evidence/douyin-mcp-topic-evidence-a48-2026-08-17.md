# A48 抖音 MCP 选题证据回执

## 范围

- 起始提交：`d7e2bbf9`
- 分支：`codex/v6-comprehension-core`
- 日期：2026-08-17
- 目标：让内容研究通过现有抖音 MCP 取得选题资料，并将最终采用证据接入项目谱系。

## 失败基线

新测试首先引用尚不存在的 MCP 选题适配器，得到：

```text
ModuleNotFoundError: No module named
'deerflow.tools.builtins.douyin_topic_evidence'
```

代码复核同时确认，原 `_search_content_world_evidence` 只从 `config.yaml` 查找
`web_search` 和 `douyin_video_search`；当前后者未配置，运行中的 MCP 工具不参与内容研究。

## 实现回执

```text
content map query
-> runtime MCP tool: douyin_search
-> discover current search Manifest
-> execute exact child: video_search
-> purpose: topic_research
-> validate official EvidenceSnapshot
-> interleave with Web topic evidence
-> final evidence reading
-> seal only snapshots whose URL survived reading
-> evidence_snapshot -> content_reading
```

旧 `config.yaml` 直连项即使存在也不会执行。`benchmark_account_candidate` 回执会被拒绝，
未被最终阅读采用的公开视频结果不会写入项目。

## 本机 MCP 与凭据状态

所有检查只输出字段状态，不输出值：

```text
MCP tools: 16
douyin_search: present
raw private config: $DOUYIN_* references
resolved DOUYIN_CLIENT_KEY: absent
resolved DOUYIN_CLIENT_SECRET: absent
resolved DOUYIN_DEVICE_ID: absent
approved scope: aweme.dy.video_search_v2
video_search callable: false
unavailable_reason: auth_not_configured
network search request sent: false
```

一次将原始 `$VAR` 字符串误当真实值的诊断请求被官方令牌端点判为
`error_code=10003 / 配置无效`；该请求没有取得令牌或搜索数据，也没有写入代码、台账或工件。
随后所有验收均改用 DeerFlow 解析后的运行配置，上述 `auth_not_configured` 才是当前真实状态。

## 自动测试

聚焦测试：

```text
PYTHONPATH=. uv run pytest \
  tests/test_content_intelligence_tool.py \
  tests/test_incubation_content_run.py \
  tests/test_douyin_topic_evidence_mcp.py \
  tests/test_douyin_evidence_snapshot.py \
  tests/test_incubation_ledger.py -q

51 passed in 4.26s
```

适配器新增两条恢复回归：过期 Manifest 只重新发现并重试一次；首次 MCP 传输异常不会把失败
发现永久缓存，后续查询可以重新发现。

后端全量：

```text
DEER_FLOW_AUTH_DISABLED=0 PYTHONPATH=. uv run pytest -q

11764 passed, 76 skipped, 17 warnings in 413.53s
```

第一次直接运行全量时，本地 `.env` 的免登录设置被配置模块载入，36 条认证、CSRF 与账号归属
测试因此以 `default` 用户运行并失败。没有修改该本地设置；命令级覆盖后，涉及的 5 个文件先得到
`467 passed`，随后全量通过。该诊断与 A48 代码无交叉。

## 未完成

- 本地进程还需要真实 `DOUYIN_CLIENT_KEY`、`DOUYIN_CLIENT_SECRET` 和 `DOUYIN_DEVICE_ID`。
- 取得凭据后必须重新发现 Manifest，再跑一次真实 v2 搜索与项目 SQLite 父级核验。
- 本回执不等于真实平台搜索通过，也不允许网页视觉采集替代。
