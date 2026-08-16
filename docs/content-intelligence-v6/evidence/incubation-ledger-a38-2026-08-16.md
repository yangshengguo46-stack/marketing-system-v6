# A38 W01 共享产物脊柱证据

## 范围

- 日期：2026-08-16
- 分支：`codex/v6-comprehension-core`
- 起始提交：`018ca4308c74800b613f97c43f018bd2aa8f9ad6`
- 目标：建立项目、账号、产物包装、内容哈希、父子谱系和证据角色，不修改内容脑方法或引入固定流程。

## 实现文件

- `backend/packages/harness/deerflow/incubation/contracts.py`
- `backend/packages/harness/deerflow/incubation/content_world.py`
- `backend/packages/harness/deerflow/persistence/incubation_ledger/model.py`
- `backend/packages/harness/deerflow/persistence/incubation_ledger/sql.py`
- `backend/packages/harness/deerflow/persistence/migrations/versions/0012_incubation_ledger.py`
- `backend/tests/test_incubation_ledger.py`
- `backend/tests/test_incubation_content_world.py`
- `backend/tests/test_migration_0012_incubation_ledger.py`

## 红灯记录

第一次运行 `tests/test_incubation_ledger.py` 在收集阶段以
`ModuleNotFoundError: deerflow.incubation` 失败。首次实现后，单独导入
`deerflow.persistence.models` 又暴露领域包与仓储包的循环导入；改为惰性导出后启动导入通过。

第二轮先增加长期地图适配和 payload 篡改测试。地图适配测试最初因
`seal_content_world_version` 不存在而在收集阶段失败；实现后转绿。仓储现在会在事务开始前重新
验证整个 `ArtifactEnvelope`，所以嵌套字典被修改后不会带着旧哈希写入数据库。

## 自动验证

```text
PYTHONPATH=. uv run pytest tests/test_incubation_ledger.py -q
10 passed

PYTHONPATH=. uv run pytest \
  tests/test_incubation_ledger.py \
  tests/test_migration_0012_incubation_ledger.py \
  tests/test_persistence_bootstrap.py \
  tests/test_persistence_bootstrap_regression.py \
  tests/test_persistence_bootstrap_concurrency.py -q
45 passed

PYTHONPATH=. uv run pytest \
  tests/test_persistence_autogen_script.py \
  tests/test_persistence_scaffold.py -q
57 passed

PYTHONPATH=. uv run pytest \
  tests/test_incubation_ledger.py \
  tests/test_incubation_content_world.py \
  tests/test_lead_agent_prompt.py -q
40 passed
```

聚焦 Ruff 检查、ORM 模型导入和 `git diff --check` 均通过。45 项与 57 项组成 102 项不同测试；
最后 40 项包含前面账本测试的扩展回归，因此不与 102 简单相加。

## 尚未验收

- Lead 与 API 还没有用户可见的项目选择、绑定和重水化入口。
- `ContentWorldView` 适配器尚未从生产 Tool 自动写入台账。
- 真实抖音账号、多进程 Postgres 和产品前端尚未验收。
- W02 的抖音搜索、对标账号、受众和 MediaKit 证据尚未迁入统一 `EvidenceSnapshot`。
