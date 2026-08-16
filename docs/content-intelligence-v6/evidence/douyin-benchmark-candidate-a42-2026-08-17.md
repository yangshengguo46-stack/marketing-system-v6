# A42 抖音对标候选聚合回执

## 代码边界

- 新增 `BenchmarkCandidateRequest` 与 `collect_benchmark_account_candidate`。
- 继续使用现有 `DomainRouter -> search.video_search`，没有复制 Token 、HTTP 或 Schema 逻辑。
- 按作者显示名精确筛选、作品 ID 去重，记录跨页、排除、重复和停止原因。
- `viewer_open_id` 只发送给官方搜索，不进入快照、台账或 Lead 投影。
- 完整候选快照作为 `benchmark_account_candidate` 幂等写入既有业务台账；
  4 KB 压力投影保持完整证据项边界并显式报告省略数。

## 失败基线

```text
ModuleNotFoundError:
deerflow.community.douyin_openapi.benchmark_candidates
```

## 聚焦验证

```bash
cd backend
uv run pytest \
  tests/test_douyin_benchmark_candidate_collection.py \
  tests/test_douyin_search_tools.py \
  tests/test_douyin_openapi_router.py \
  tests/test_douyin_evidence_snapshot.py -q
```

结果：`34 passed`。

完整后端离线回归：

```bash
cd backend
DEER_FLOW_AUTH_DISABLED=false make test
```

结果：`11721 passed, 76 skipped, 17 warnings in 424.47s`。Ruff、格式检查和
`git diff --check` 同步通过。

## 未验证项

- 本地未配置抖音 Client Key/Secret，未调用真实 v2 搜索。
- 显示名候选不是稳定账号身份，未升级为 `BenchmarkSnapshot`。
- 星图和百应延期到官方公开搜索出现明确字段缺口之后。
