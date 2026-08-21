---
id: A128
status: reviewed_with_live_e2e
date: 2026-08-21
sources:
  - A121-soft-domain-skill-implementation-and-live-eval.md
  - A126-audience-first-subject-and-product-truth.md
  - A127-pre-audience-term-verification.md
  - backend/packages/harness/deerflow/agents/lead_agent/prompt.py
  - backend/packages/harness/deerflow/tools/builtins/content_intelligence_tool.py
  - skills/public/incubate-gift-human-relations/SKILL.md
  - ADR-040-agent-owned-incubation-routing.md
---

# A128 Agent 自主孵化路由

## 触发问题

用户复核真实对话后指出：系统已经知道业务和受众，却仍无条件进入拆词、受众决策、内容根、地图、对标和
路线工具。代码虽然由 Agent 调用，营销判断实际上仍被应用程序式工作流拥有。它会重复提问、增加 Token，
并把一次起号咨询变成必须走完的状态机。

审计确认病根不是“步骤太多”这一表象，而是三个权责错误：

1. Lead 提示词要求 `develop_account_strategy` 成为起号请求的第一个动作。
2. 工具同时拥有受众、内容根、地图、对标、路线和停止点，Lead 只能转述。
3. 行业 Skill 仍引用旧工具和旧 Profile，导致已退休流程通过另一条入口重新出现。

## 本轮实现

- `develop_account_strategy` 保留为历史兼容与离线验收实现，但从默认 Lead 工具目录移除。
- Lead 直接拥有最终判断。它可以直接回答，也可以按当前不确定性选择一次澄清、行业 Skill、词项核实、
  语义分析、内容地图、对标证据或子任务；没有固定第一步。
- 受众不是强制表单。只有付款者、决策者、使用者或内容受众的差异会实质改变路线时，才问一个选择题。
- `verify_business_term` 只对陌生、近期或歧义词做一次最多三条摘要的核实；熟悉词不搜索。
- `inspect_agent_product_profile` 只在 Agent 自营销时读取服务端事实，修复“你自己”被当成用户业务。
- 内容地图结果改为隐藏的有界工作材料，返回 Lead 后由 Lead 收敛；同一用户轮次最多调用一次。模型误传
  改写后的主体时，工具回退到用户逐字请求，不再触发重算循环。
- 行业 Skill 只提供领域注意力。礼赠 Skill 不再要求旧路线工具，也不在普通对话读取带旧分支提示的
  Profile；长期方向比较产品、行为和关系三个编辑距离，并将未提供的资源保持为条件。
- `read_file` 不再延迟发现。加载 Skill 从 `describe -> tool_search -> read` 缩为 `describe -> read`。
- 完整 Lead 中间件会把少量合法工具放大为很多 LangGraph super-step，因此三个入口统一将默认预算从
  `100` 调到 `180`；重复调用仍由循环检测、单轮地图上限和服务端 `1000` 上限约束。

## 真实运行

所有运行使用全新线程、`glm-5-2-260617`、thinking 开启；未复用聊天记忆。

| 案例 | 工具轨迹 | Token | 结果 |
|---|---|---:|---|
| TikTok 公会，MENA/CCA | 无工具 | 5,243 | 正确识别三类账号目的，只问一个会改变路线的问题 |
| Agent 卖自己 | 产品事实工具 | 16,399 | 主体绑定为当前 Agent，不再虚构普通人身份 |
| 黄金礼品，B2C+B2B 已知 | Skill 两段读取 | 26,990 | 比较产品、送礼行为、人情关系，推荐“人情关系观察者”；无婚嫁分支 |
| 企业客户答谢礼，修复前 | Skill 三段读取 | 26,967 | 方向正确，但先断言用户“一定有案例”后再表示不确定，失败 |
| 企业客户答谢礼，修复后 | Skill 两段读取 | 21,242 | 先识别行政采购受众，推荐其职场关系世界；资源只作条件，事实边界通过 |

`read_file` 常驻后，最后一组同题总 Token 从 `26,967` 降为 `21,242`，约减少 21%。黄金礼品没有调用
内容地图，证明行业 Skill 和 Lead 可以在证据足够时直接判断；内容地图仍可在真正需要跨文本发散时按需调用。

## 自动验证

- Lead 系统提示词由超出架构预算的 `10,662` 字节压缩到 `7,907` 字节；保留自主路由、事实边界、
  单轮一次内容地图、陌生词核实、自营销事实档案和行业 Skill 按需加载等行为锚点。
- 内容智能、业务词项、产品档案、孵化边界、输入净化、工具搜索和 Gateway 聚焦回归：`517 passed`。
- 正式认证配置下完整后端非 live 回归：`12,438 passed, 75 skipped, 17 warnings`，退出码 `0`。
- `make format` 与提示词、指导文件体积门均通过。

## 未通过与边界

- 一个信息完整的实体水果店案例虽零工具完成，但 GLM 仍给出同质化计划、主观半径、发布时间和宝妈刻板
  画像。自主路由解决的是决策权与无效流程，不等于基础模型营销质量自动达到 80 分。
- 黄金礼品已到达人情关系世界，但具体示例仍偏礼赠行为；本轮按“可用而非完美”通过，不宣称任意行业泛化。
- 动态 Lead 的首轮方向目前仍是聊天输出，尚未替代旧 `IncubationJudgment` 的版本化持久化合同。旧合同
  绑定地图优先流程，不能原样接回；后续应设计薄的追加式 `AccountDirectionProposal`。
- 递归预算增加不是质量增益。Token 预算、模型服从性和 Skill 加载成本仍需独立优化。

结论：第六版默认孵化入口已从“Agent 外壳包固定应用流程”改为“Lead 按不确定性选方法”。旧工作流仍可供
历史回放，但不再拥有默认营销判断权。
