# ADR-024：拒绝 A86 词汇候选实验进入运行时

## 状态

Rejected，2026-08-19。

## 决定

拒绝将 `experiments/lexical_candidate_lab` 的词典裸候选、模型来源自报合同或关系词族投影接入 Lead、
Tool、Skill、MCP、中间件、子智能体或生产内容根链路。现役运行时保持不变。

## 理由

- 词典裸候选召回 7/7，同时在马桶上产生马和桶，不能安全自动并入。
- 纯模型仅 7/10 合同成功，证明让模型自报证据来源造成无谓合同失败。
- 证据臂八题在调用前超出输入预算，只有两题真实运行，不具备比较效力。
- 沙发案例出现真实但不合当前语境的网络义项，证明相关词族会制造注意力漂移。

## 后果

- A86 十题已消费，不得调大预算或修改提示后重跑为留出实验。
- 可以保留其隐藏答案隔离、三臂回执、调用与 Token 计量方式。
- 后继只能用新题测试紧凑精确词义投影，并把候选生成与证据来源绑定分开。
- 本结论不否定 CC-CEDICT 作为可选证据源，也不支持建设向量知识库。

## 证据

- `docs/content-intelligence-v6/audits/A86-lexical-candidate-recall-preregistration.md`
- `docs/content-intelligence-v6/audits/A87-lexical-candidate-recall-result.md`
- `docs/content-intelligence-v6/evidence/lexical-candidate-a86-2026-08-19.json`
