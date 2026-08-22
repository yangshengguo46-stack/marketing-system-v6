---
id: ADR-045
status: superseded
date: 2026-08-22
superseded_by: ADR-048-minimal-agent-kernel-and-bounded-skill-routing.md
related:
  - A137-model-neutral-agent-core-prompt-audit.md
  - A138-agent-core-contract-preregistration.md
  - A139-thin-operator-core-implementation.md
---

# ADR-045 采用薄的模型无关运营执行者内核

> 该决定的模型无关、员工身份和不可逆审批原则保留；三份生产业务合同及 9,000 字节预算已由 ADR-048
> 的极薄 Agent Kernel 替代。

## 决定

正式 Lead 使用一份跨模型共用的薄工作合同：它是用户团队内的新媒体运营执行者，明确请求是当前任务，
交付最小可用结果；只在工具能实质改变结果时使用工具，不为显得主动而调研；不可逆外部动作仍须明确审批。

首轮账号方向以用户事实形成临时工作判断。只有用户要求当前证据或对标，或名词需要有界核实时才搜索。临时判断可用于
当前回答；只有用户接受精确提案和选项才成为持久账号方向。

结果合同位于母提示最后，要求可见回答前做一次短复核。静态 `SYSTEM_PROMPT_TEMPLATE` 继续受 `9,000` UTF-8 字节上限约束。

## 实现边界

- 三份合同由 `prompt.py` 直接组合，不使用运行时 Prompt 覆盖中间件。
- 新合同使用的框架权威标签必须进入共享输入清洗 denylist，用户或工具证据不能伪造同名块。
- Provider 适配器只处理工具协议、thinking、上下文限制、流式事件和错误归一；禁止出现 GLM/DeepSeek/豆包专属营销 Prompt。
- 行业答案归垂直 Skill，工具用法归 Tool Schema，账号事实归业务台账，不再回填母提示。
- 不修改模型输出，不用关键词删句，不建固定复审子 Agent 管道。

## 拒绝

- 拒绝 A138 的完整强执行候选：它会过度搜索并扩张任务。
- 拒绝通过放宽 Prompt 预算来继续追加历史失败禁令。
- 拒绝用一个模型或一道行业题的提升宣称跨模型完成。

## 残留风险

真实 GLM 新题已从 `57` 工具调用收敛到 `0`，但仍会偶发多一个问题或顾问式后续邀约。这项不通过状态必须向用户透明，
后续以新会话的人工偏好和业务交付验收，不再用冷库维修题调参。
