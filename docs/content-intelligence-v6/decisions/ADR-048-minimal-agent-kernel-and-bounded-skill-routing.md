---
id: ADR-048
status: accepted
date: 2026-08-22
related:
  - ../audits/A137-model-neutral-agent-core-prompt-audit.md
  - ../audits/A139-thin-operator-core-implementation.md
  - ../audits/A142-employee-agent-kernel-and-gift-skill-v1-3.md
---

# ADR-048 采用极薄 Agent 内核与有界 Skill 路由

## 决定

正式 Lead 只用一份模型无关的 `PRODUCTION_AGENT_KERNEL` 定义员工身份、长期目标、自主行动、事实边界和
不可逆审批。行业方法、平台规则、固定起号步骤、评分、搜索顺序、问题数量和交付模板不得进入该内核。

启用 Skill 使用两级渐进披露：首轮只暴露 Skill 名称和最多 120 字符的用途摘要；完整元数据通过
`describe_skill` 获取，方法正文通过 `read_file` 加载。摘要只帮助模型发现能力，不自动激活 Skill、改变
工具权限、选择内容根或强制工作流。

## 依据

- 名称-only 首次问候减少 `586` Token，但黄金礼品真实运行没有加载礼赠 Skill，最终消耗 `65,208`
  Token 并重新落入婚礼和商品题材。
- 120 字符摘要版问候为 `3,768` Token；黄金礼品运行以三个成功工具调用在 `18,272` Token 内到达
  “人与人之间的相处与人情世故”，且交付可直接拍摄的题目。
- 极薄内核为 `1,108` 字节，完整静态模板为 `3,560` 字节，能够跨模型共用且没有恢复第四版硬门。

## 替代与拒绝

- 拒绝恢复 A139 的三份业务母合同；其正确意图由 Agent 自主性、业务 Skill、工具和事实对象分别承担。
- 拒绝名称-only Skill 索引作为现役默认；真实业务召回失败已经超过其上下文收益。
- 暂不增加自动行业分类器、向量库或第二个路由模型。只有新行业评测证明 120 字符摘要无法泛化时再比较。
- 拒绝用输出后处理删除顾问语气，也拒绝为 GLM、DeepSeek、豆包分别维护营销 Prompt。

## 约束

- `PRODUCTION_AGENT_KERNEL <= 1,600` UTF-8 字节。
- `SYSTEM_PROMPT_TEMPLATE <= 5,000` UTF-8 字节。
- Skill 路由摘要单项不超过 `120` 字符，并在进入 Prompt 前转义。
- Skill 方法正文不得出现在常驻索引；只有模型实际加载后才进入当前上下文。
- 行业题验收必须记录真实工具轨迹、Token、最终业务判断和残留问题，不能以测试绿灯替代业务复核。

## 后果

Agent 获得更清晰的目标与自主权，同时仍能发现专业方法。首轮问候比名称-only 多约 `586` Token，但换回了
黄金礼品这一核心业务题的稳定路由。剩余的能力菜单和顾问式结尾作为行为缺口继续观测，不再污染核心内核。
