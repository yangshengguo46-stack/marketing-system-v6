---
id: A59
status: reviewed
reviewed_at: 2026-08-17
decision: measure_then_compact_single_map_call
sources:
  - backend/packages/harness/deerflow/content_intelligence/analyzer.py
  - backend/packages/harness/deerflow/content_intelligence/research.py
  - backend/packages/harness/deerflow/tools/builtins/content_intelligence_tool.py
  - docs/content-intelligence-v6/evidence/parallel-semantic-workers-a58-2026-08-17.md
---

# A59 冻结根地图延迟与重复召回审计

## 触发

修正后的“拳击手套”真实回归总耗时约 `101.44s`，其中冻结根地图调用约 `61.84s`。
业务语义和词义世界已经并行，地图成为当前最大单段延迟。

## 发现

1. 地图输入很小，只包含冻结内容根；延迟不来自长上文或联网搜索。
2. 一次地图调用同时生成长期承诺、稳定观察视角、漂移边界、不限数量的地图方向、专名候选、
   验证查询和未知项。拳击案例实际生成九个方向，开放式输出工作量较大。
3. 地图中的 `named_candidates` 与后续研究模块对人物、事件、作品和制度的命名召回重复。
4. 当前结构化调用没有阶段级性能回执，无法区分长输出、首次 Schema 失败后的修复调用、
   供应商网络重试或排队波动。
5. 当前没有地图专属输出预算。直接先设硬 `max_tokens` 可能截断 JSON，反而触发修复调用。
6. 完整高层工具还会继续研究、搜索、证据阅读、选题和表达。纯长期定位请求若无条件进入下游，
   会把地图性能问题与未请求工作混在一起。

## 决定

- 不把地图按时间、地域、人物等轴拆成多个模型工作者。它必须围绕一个冻结根形成统一疆域，
  并行拆写会增加调用、总 Token、重复和合并冲突。
- 先增加每阶段耗时、输出 Token、响应大小、Schema 修复次数和供应商重试的可检查回执。
- 保留模型判断长期承诺、稳定视角、适用方向、根特有漂移边界和知识缺口。
- 路径 ID、根节点绑定、去重、验证状态、内部方法信息过滤等交给确定性代码。
- 将专名候选从地图和研究的重复职责中移出一处；在修改合同前先用测试证明研究仍能从全部
  地图方向召回人物、事件和作品。
- 取得真实输出分布后，才比较紧凑合同和地图专属 Token 预算；不先拍脑袋设固定方向数量。
- 后续高层意图按需停止：长期讲什么可停在地图，今天拍什么才进入研究与选题，用户给视频或
  对标账号时才调用抖音 OpenAPI 与 MediaKit。

## MediaKit 边界

MediaKit 没有冻结。它继续用于对标视频、自有素材和制作任务；纯内容根地图没有媒体输入时，
不应为了“用上 MediaKit”而增加一次无意义调用。

## 下一验收

1. 正常地图只有一次模型尝试；若发生修复必须可见计数。
2. 紧凑合同前后地图节点覆盖、具体性和漂移率不下降。
3. 比较全新盲测案例的输出 Token、P50/P95 和阶段耗时。
4. 相同根的任何缓存必须绑定模型、提示词和 Schema 哈希，任一变化即失效。

