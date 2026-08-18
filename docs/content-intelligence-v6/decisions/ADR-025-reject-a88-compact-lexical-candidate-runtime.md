# ADR-025：拒绝 A88 紧凑词义候选方案进入运行时

## 状态

Rejected，2026-08-19。

## 决定

拒绝将 `experiments/compact_lexical_candidate_lab` 的紧凑 CC-CEDICT 投影接入 Lead、Tool、Skill、MCP、
中间件、子智能体或生产内容根链路。不因该问题建设现代汉语词典向量库。现役运行时保持不变。

## 理由

- 词典增强的透明词候选召回为 `4/7`，低于纯模型的 `6/7`，未达 `6/7` 最低线。
- 纯模型已达 `6/7`，词典臂不存在“至少多两题”的提升空间，预注册已指定这种情况为“未证明
  需要词库”。
- 词典臂从骑行、潜水和烘焙活动世界退化为配套商品或产出物列表，人工复核确认了证据诱导的产品邻接漂移。
- 证据臂多用 1,129 Token，没有产生质量增益。
- 两个模型臂都能避免麦克风和老婆饼的机械拆分，词典保护没有填补纯模型的缺口。
- 纯模型一题额外触发结构修复，唯一运行不完全满足严格请求数边界，不允许为改善结果重跑。

## 后果

- A88 十题已消费，不得调参、改分数器或换别名后重跑。
- A88 代码只作为可复核的失败实验，不得被正式代码导入。
- 可保留紧凑输入、确定性来源绑定、真实索引全量预检和请求计数的实验工程做法。
- 词典可以在用户明确要求查词时作为可选事实证据，但不作为内容根默认候选源。
- 后续应把模型开放召回的多个完整内容世界交给独立选择与用户校准，而不是继续向候选生成注入更多词义。

## 证据

- `docs/content-intelligence-v6/audits/A88-compact-lexical-candidate-preregistration.md`
- `docs/content-intelligence-v6/audits/A89-compact-lexical-candidate-result.md`
- `docs/content-intelligence-v6/evidence/compact-lexical-a88-2026-08-19.json`
