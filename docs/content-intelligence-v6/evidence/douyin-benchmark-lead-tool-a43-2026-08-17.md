# A43 抖音对标候选 Lead 工具回执

## 范围

- 高层工具：`collect_douyin_benchmark_candidate`
- 模型可见参数：`query`、`actor_label`、`max_posts`
- 服务端注入：认证用户、`thread_id`、`run_id`、可选 `incubation_project_id`
- 产物：最多 16 KB 的 `benchmark_account_candidate` Lead 投影，以及可选项目台账封存

## 失败基线

```text
ModuleNotFoundError: No module named 'deerflow.tools.builtins.douyin_benchmark_tool'
```

## 离线回归

```text
Lead tool + Gateway context: 7 passed
Douyin router/evidence/ledger/Gateway related suite: 178 passed
Tool schema and runtime serialization suite: 38 passed
Full backend offline suite: 11730 passed, 76 skipped, 17 warnings in 465.97s
```

覆盖以下边界：

- 工具已进入 `BUILTIN_TOOLS`，且模型 Schema 不包含运行时、所有者、密钥、Token、
  Cookie、分页游标和 `search_id`。
- 未选项目时直接返回只读证据，不调用项目仓储。
- 选中项目时先检查认证用户所有权，再调用平台，并保存会话/运行归属。
- 伪造的 owner 上下文不会被 Gateway 转发。
- 平台失败不返回底层异常；台账失败仍保留已取得证据，并返回脱敏的
  `persistence=failed`。

## 未验收

- 本机未配置抖音 Client Key/Secret，本轮没有请求真实官方 v2 接口。
- 前端尚无孵化项目创建/选择器，所以本轮没有产品界面上的真实项目入库回执。
- 官方搜索仍只能生成显示名候选，不能证明稳定竞品账号身份。
