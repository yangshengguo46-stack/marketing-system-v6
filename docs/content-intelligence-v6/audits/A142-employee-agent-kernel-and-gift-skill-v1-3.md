---
id: A142
status: reviewed
date: 2026-08-22
sources:
  - A137-model-neutral-agent-core-prompt-audit.md
  - A139-thin-operator-core-implementation.md
  - ../decisions/ADR-048-minimal-agent-kernel-and-bounded-skill-routing.md
  - ../evidence/a142-agent-kernel-and-skill-routing-2026-08-22.json
  - backend/packages/harness/deerflow/agents/lead_agent/agent_core_contract.py
  - backend/packages/harness/deerflow/skills/describe.py
  - skills/public/incubate-gift-human-relations/SKILL.md
---

# A142 员工型 Agent 内核与礼赠 Skill v1.3

## 要解决的问题

第六版虽然已有工具、Skill、内容地图和事实台账，Lead 的可见行为仍像一个外部顾问：解释方法、列能力、
不断提问，却没有稳定呈现“这是我的工作，我先做起来”的本体感。病根不是缺少另一条营销规则，而是把
Agent 当成了预先编排的应用程序。

本轮采用的第一性定义是：Agent 在目标和当前状态下，自主选择下一步行动，执行后观察结果，再修正行动，
直到交付结果或遇到真正需要用户决定的阻塞。Harness 提供模型、上下文、工具、Skill、状态和恢复能力，
不替模型写死业务路线。

## 正式内核

正式 `PRODUCTION_AGENT_KERNEL` 只保留五件事：

1. 身份：用户团队内的新媒体孵化与运营员工，不是外部顾问或老师。
2. 目标：帮助用户获得关注、被理解、被记住和被信任，建立可持续 IP，并从真实结果中改进。
3. 自主性：自行判断、创作、研究、调用能力、执行、验证和修正；没有必经能力或工作流。
4. 事实边界：事实必须真实，判断可以大胆；事实、推断、假设与创意保持可区分。
5. 行动边界：只有发布、付款、删除、账号身份和权利承诺等不可逆外部动作需要明确批准。

内核为 `1,108` UTF-8 字节，静态 `SYSTEM_PROMPT_TEMPLATE` 为 `3,560` 字节。A139 中首轮方向、搜索时机、
单问题、交付复核等业务合同不再常驻母提示；对应能力仍可由 Agent、Skill、工具和事实台账按当前任务使用。
这次是替换，不是继续叠加。

## Skill 渐进披露对比

本轮用同一 GLM、同一完整 DeerFlow Harness 和同一黄金礼品问题比较两种路由投影。

| 方案 | “你好” | 黄金礼品 | 结论 |
|---|---:|---:|---|
| 只列 Skill 名称 | `3,182` Token，0 工具 | `65,208` Token；没有加载礼赠 Skill，转去抖音/网页/内容地图并重新落入婚礼题材 | 拒绝 |
| 名称 + 最多 120 字符用途摘要 | `3,768` Token，0 工具 | `18,272` Token；`describe_skill` 两次、`read_file` 一次，明确选择人情世故并给出三个完全脱离商品的题目 | 接受 |

名称-only 省下的首次上下文不足以抵偿能力错路。120 字符摘要只是路由元数据，不包含 Skill 方法正文；
模型仍须主动调用 `describe_skill` 和 `read_file`，并可拒绝该 Skill。行业方法没有回到主脑。

## 真实业务复核

接受版的黄金礼品回答明确判断“讲人情世故，黄金只是手段”，并给出“还错人情”“抢买单改变关系定义”
“关系一般的人突然示好”等可直接拍摄题目。它没有把婚礼、彩礼或三金当默认入口，也没有调用内容地图。
这满足当前最关键的语义跃迁和具体选题要求。

仍未宣称完全成功：问候仍会短暂列举能力；黄金答案末尾仍追加一次顾问式追问，并出现“黄金最不会出错”
这类未经证据支持的绝对判断。它们属于真实模型行为缺口，不能再通过扩张母提示、关键词删句或固定复审
Agent 来遮盖。

## 回归与边界

- Agent 内核实验、Prompt、Skill、工具发现、账号方向、MCP 取消和输入清洗聚焦回归：`365 passed`。
- 名称-only 的失败运行与接受版运行均保留线程 ID、工具名和 Token 回执，不保存工具参数、搜索正文或密钥。
- MCP Child 初始化取消现已区分子会话失败与调用方取消；前者成为可恢复工具错误，后者仍取消整次运行。
- 本轮没有新增固定孵化工作流、输出改写中间件、Provider 专属营销 Prompt 或强制多 Agent 路线。

## 当前判断

第六版现役结构应描述为：**一个极薄的员工型总脑，加有界能力路由，再按需打开行业 Skill 和执行工具。**
总脑拥有最终判断，Skill 提供可拒绝的方法，工具提供行动能力，事实台账提供连续性。下一阶段应通过新的
真实行业题继续检查泛化和本体感，而不是再给核心提示词添加历史失败禁令。
