---
id: A40
status: reviewed
reviewed_at: 2026-08-16
decision: rewrite_bounded_benchmark_snapshot_contract
sources:
  - /Users/yangyucheng/Documents/ChatGPT/第五版营销系统@3ee135f7
  - backend/experiments/e15_account_evidence/source_snapshot.py
  - backend/experiments/e15_account_evidence/account_link_collection.py
  - backend/experiments/e15_account_evidence/platform_account_reader.py
  - backend/experiments/e15_account_evidence/lead_projection.py
  - backend/tests/experiments/test_e15_account_source_snapshot.py
  - backend/tests/experiments/test_e15_account_link_collection.py
  - backend/tests/experiments/test_e15_platform_search.py
  - docs/mcn-incubation-v5/audits/A35-bounded-account-link-evidence.md
  - docs/mcn-incubation-v5/audits/A39-daneng-real-account-acceptance.md
---

# A40 第五版 E15 对标账号快照迁移审计

## 审计目标

第六版 W02 需要接收“用户给出一个对标账号链接”得到的结构化观察，但不能把第五版
隔离实验整包注册进新运行时。本轮只审计账号身份、多作品清单、覆盖回执和 Lead 投影，
不迁移媒体感知、受众交互或账号成功归因。

## 逐文件结论

| 第五版来源 | 有价值的边界 | 第六版决定 |
| --- | --- | --- |
| `source_snapshot.py` | 严格主页/作品白名单、时区时间、稳定公开链接、作品 ID 去重 | 用新 `BenchmarkSnapshot` 合同重写 |
| `account_link_collection.py` | 用户提供链接、显式权利依据、实际采样上限 `24` | 保留输入和覆盖语义，不迁移文件缓存 |
| `platform_account_reader.py` | 所有作品必须带稳定作者 ID 且与目标账号一致；冲突主页指标不猜值 | 保留确定性校验，平台页面选择器以后单独验收 |
| `lead_projection.py` | 完整快照不等于模型上下文；投影固定字节预算、显示省略数、保留源哈希和限制 | 保留，但首版只投影主页和作品观察，不投影未审阅模式 |
| A39 真实验收 | 推荐流不能冒充账号作品，公开零值哨兵不能冒充真实零播放 | 记为连接器验收基线，不由快照合同猜平台语义 |

## 新合同边界

- `BenchmarkSnapshot` 只表示一次有界的第三方账号公开观察，证据角色固定为
  `benchmark_evidence`。
- 主页身份和每条作品都带平台稳定 ID；任意作品作者不一致时整份快照拒绝封存。
- 覆盖回执区分请求数、返回数、排除数、`has_more` 和采样依据；单次请求上限为 `24`。
- 主页文本、作品文案和公开计数是不可信观察证据，不是指令、粉丝画像、成功原因或可复制公式。
- 快照不含原始 DOM/HTML、Cookie、StorageState、原始响应、临时媒体地址或本地路径。
  连接器可在本地使用凭证，但不得返回凭证值。
- 账号内容模式、反例、获客期定位、当前定位和不可复制条件属于后续分析产物，必须引用
  本快照，不得由采集器直接生成。

## 拒绝迁移

- 不迁移 E15 本地 JSON 缓存；第六版使用已有业务产物台账。
- 不迁移第五版平台枚举、Playwright 选择器和采集运行时；这些按平台逐个重新验收。
- 不将账号快照混成 `topic_evidence`、`owned_account_observation` 或受众证据。
- 不把 A39 的“大能”结论写成行业规则、Skill 或冷启动模板。

## 实施决定

状态从 `discovered -> traced -> reviewed -> adopted for bounded contract rewrite`。先实现平台无关的
`BenchmarkSnapshot`、字节预算投影与业务台账封存；再单独接入抖音账号读取路由。
本审计不授权 Lead Tool 注册，也不宣称已实现用户丢链接后的端到端解析。
