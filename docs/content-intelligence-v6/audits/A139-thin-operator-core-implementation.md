---
id: A139
status: reviewed
date: 2026-08-22
sources:
  - A137-model-neutral-agent-core-prompt-audit.md
  - A138-agent-core-contract-preregistration.md
  - ../evidence/a139-production-operator-core-2026-08-22.json
  - backend/packages/harness/deerflow/agents/lead_agent/agent_core_contract.py
  - backend/packages/harness/deerflow/agents/lead_agent/prompt.py
  - https://openai.com/business/guides-and-resources/a-practical-guide-to-building-ai-agents/
  - https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
  - https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/subsystems/system-prompt.md
---

# A139 薄运营执行者内核实施与真实验证

> 历史记录：本轮的三份生产合同随后被 A142/ADR-048 的极薄 Agent Kernel 替代；实验结果与失败证据继续有效。

## 目标

把 Lead 从“会做新媒体分析的外部顾问”校正为“在用户团队内接下当前任务的运营执行者”，同时不恢复
固定起号流程，不为 GLM、DeepSeek 或其他模型维护不同的营销母提示。

## 完整候选为什么被拒绝

A138 的完整候选把“主动完成”写得过强。它改善了问候和部分执行题，但也诱导模型为了显得负责而
过度搜索、扩张任务、补造竞品证据和起号数字。因此本轮没有把 `apply_agent_core_candidate` 注册为中间件，
也没有把它叠到正式 Prompt 之上。

## 正式采用的薄内核

现役 `SYSTEM_PROMPT_TEMPLATE` 直接组合三份模型无关合同：

1. `PRODUCTION_AGENT_CORE_CONTRACT`：内部同事关系、当前任务所有权、最小可用交付、工具和不可逆审批边界。
2. `PRODUCTION_ACCOUNT_INCUBATION_CHARTER`：首轮账号方向优先使用用户事实；只有用户明确要当前证据、对标，
   或名词确实陌生、近期、有歧义时才调研。临时工作判断不需要竞品证明，也不自动生成发布条数或启动序列。
3. `PRODUCTION_RESULT_REPORTING_CONTRACT`：放在整份系统提示最后。模型在可见回答前做一次短复核，删除虚构的用户事实、
   无来源的具体或量化断言、能力菜单和相邻计划；真有决策问题时先解释原因，再以该问题结束。

它们是 Prompt 的源码段，不是运行时覆盖、输出删改中间件或 Provider 分支。业务方法、行业知识、内容地图、
对标和执行工具仍然按需加载。静态母提示为 `8,981` UTF-8 字节，低于现役 `9,000` 字节预算。

新增的 `<work_ownership>` 和实验保留的 `<marketing_charter>` 都属于框架权威块，已同时加入共享输入清洗
denylist 和显式回归清单。用户消息、远程工具结果或 Skill 文本中的同名标签会被转义，不能冒充系统合同。

## 真实运行结果

| 轮次 | 结果 |
|---|---|
| GLM / DeepSeek Pro / DeepSeek Flash 问候 | 三者均 `0` 工具，约 `4.9k-5.2k` Token；前两者一句话，Flash 仍有一句短能力介绍 |
| 工业内窥镜首轮方向 | `1` 次模型、`0` 工具，直接给出“帮工厂看见看不见的隐患”方向 |
| 商用厨房油烟管清洗回归失败 | 收窄前曾达 `57` 工具、`159,506` Token，证明“有用就搜”仍会退化成完整性搜索 |
| 首轮搜索边界收窄后 | 冷库维修回归稳定为 `1` 次模型、`0` 工具、约 `6.0k-6.7k` Token |
| 最终新题：无损探伤 | `1` 次模型、`0` 工具、`6,718` Token；业务判断可用，但仍多问了一个问题并追加后续邀约 |

## 回归结果

- Prompt、实验器、孵化边界与内容智能相关测试：`108 passed`。
- 输入清洗安全文件：`197 passed`。
- 整仓离线回归前段通过 `5,261` 项后发现并修复上述新标签未入 denylist 的真实回归；修复后从该文件
  完整重跑，并续跑其余 341 个测试文件，后段为 `7,347 passed, 45 skipped`。
- 唯一未纳入通过结论的是 DeerFlow 原有
  `test_concurrent_checkpointer_getter_creates_one_instance`：八线程会在本机同时解析配置，超过测试写死的
  3 秒等待。相关 provider 与测试均未被本轮修改，隔离复现后作为既有环境时限问题保留，不为刷绿改底座。

## 当前判断

这次不是“完全解决”，而是一个有证据的部分晋级：

- **通过**：跨模型同一内核、问候短答、首轮不必搜索、临时工作判断、Prompt 预算、不可逆审批和结果优先。
- **未通过**：模型百分之百呈现员工本体感、百分之百遵守单问题和无邀约结尾。GLM 在新题上仍有顾问式泄漏。
- **不采用**：模型专属营销 Prompt、硬编辑最终回答、固定多 Agent 复审流程、恢复起号必经管道。

因此 ADR-045 只接受薄内核，并把“像员工”保留为真实会话行为验收，不用静态提示存在来宣称成功。
