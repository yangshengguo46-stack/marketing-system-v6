# A40 对标账号快照实施回执

## 范围

本回执只验收第六版平台无关的对标账号观察合同、Lead 字节预算投影和业务台账封存。
没有注册抖音账号链接 Tool，没有调用真实平台，也没有产生账号定位、受众画像或成功归因。

## 来源谱系

- 第五版只读基线：`/Users/yangyucheng/Documents/ChatGPT/第五版营销系统@3ee135f7`。
- 重点源文件：`source_snapshot.py`、`account_link_collection.py`、
  `platform_account_reader.py`、`lead_projection.py` 及相应 E15 测试。
- 失败证据：A39 首次将抖音推荐流作品误当目标账号作品，后续以作者 ID 一致性拒绝该样本。
- 迁移决定：只重写合同，不迁移旧采集运行时和案例结论。详见
  `audits/A40-fifth-version-e15-benchmark-snapshot.md`。

## 新产物

- `BenchmarkProfileObservation`：稳定平台、外部账号 ID、规范公开链接、有界主页文本和公开指标。
- `BenchmarkPostObservation`：每条作品显式携带作者外部账号 ID，无法在后续偷偷混入另一账号。
- `BenchmarkCoverageReceipt`：单次最多 24 条，分开保留请求、返回、排除、`has_more`、采样依据和限制。
- `BenchmarkSnapshot`：快照时间、权利依据、用户请求链接、路由回执、主页、作品与覆盖的不可变组合。
- `seal_benchmark_snapshot`：封存为项目所有的 `benchmark_snapshot` / `benchmark_evidence`，不冒充用户自有账号。

## 自动验收

```text
uv run pytest tests/test_benchmark_snapshot.py -q
10 passed

uv run pytest tests/test_benchmark_snapshot.py tests/test_incubation_ledger.py \
  tests/test_douyin_evidence_snapshot.py tests/test_pnpm_script.py -q
35 passed

DEER_FLOW_AUTH_DISABLED=false make test
11709 passed, 76 skipped
```

自动验收覆盖：

- 作者不一致或缺失、重复作品 ID、覆盖数不一致和请求超过 24 条时失败。
- 负数、非有限指标或晚于快照的观察时间失败。
- Cookie、StorageState、原始 HTML、临时媒体地址和本地路径不属于返回合同。
- 24 条长文案在 4 KB 压力投影中仍保持字节预算，并显式报告省略作品数。
- 产物角色固定为 `benchmark_evidence`，不与 `topic_evidence` 或自有账号观察混用。

本地 `.env` 关闭鉴权会改变认证、CSRF 和所有者隔离测试的预期，因此全量回归显式恢复鉴权。
排查中发现并修复了既有 `content_intelligence_delivery` 内部标签的输入防伪造名单缺口；输入清洗
聚焦套件 `157 passed`，此前受环境影响的七组联合回归 `636 passed`。

## 剩余边界

- 抖音第三方账号的实际链接采集路由尚未接到第六版。
- 快照尚未由生产 Tool 根据当前用户/项目自动入库。
- 对标模式分析、反例、获客期定位、当前定位和不可复制条件是下一层引用产物，本切片没有伪造完成。
- 受众采集与 MediaKit 感知分别使用独立快照和覆盖回执，不追加到本快照中。
