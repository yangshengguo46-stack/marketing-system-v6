# ADR-023：拒绝 A84 ContentRootLab 进入运行时

## 状态

Rejected，2026-08-19。

## 背景

A83 建议比较“开放关系候选图 + 偏好选择”与现役顺序语义链。A84 在实现和真实输出前冻结
了四个新案例、隐藏别名、成本计量和验收阈值。实验代码先于唯一留出运行提交为
`82c273a8d6b94078e028e779247f1107167ec0d3`。

## 决定

拒绝将 A84 的关系候选图、语义成分召回或 DSPy 选择器注册到 Lead、Tool、Skill、MCP、中间件或任何
生产工作流。现役运行时保持不变。

## 理由

- 关系图候选召回为 3/4，最终选择为 2/4，未达预注册的 3/4。
- DSPy 仍为 2/4：它修复了一题，又破坏了一题，证明七条偏好还不足以稳定泛化。
- 关系图确实将调用从 24 降到 8，Token 从 57,601 降到 25,317，但成本改善不能代替语义验收。
- 失败同时来自候选召回与最终收敛，继续在同一提示上叠规则无法证明是哪个部分有效。

## 后果

- `backend/experiments/content_root_lab` 保持离线、只读性质，不是待启用功能。
- A84 四题已成为开发证据，不得再作为留出集。
- 可以沿用关系图的确定性 ID、证据状态、冻结候选绑定、隐藏答案隔离和成本回执作为下一个实验的测试基础。
- 后继只允许用新案例分别验证“词汇证据补候选”和“冻结候选偏好选择”，不在 A84 上叠加更多阶段。

## 证据

- `docs/content-intelligence-v6/audits/A84-content-root-lab-preregistration.md`
- `docs/content-intelligence-v6/audits/A85-content-root-lab-result.md`
- `docs/content-intelligence-v6/evidence/content-root-lab-a84-2026-08-18.json`
