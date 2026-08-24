---
id: A148
status: reviewed
date: 2026-08-24
sources:
  - backend/packages/harness/deerflow/agents/lead_agent/IDENTITY.md
  - backend/packages/harness/deerflow/agents/middlewares/context_manifest_middleware.py
  - A112-tiktok-live-guild-clean-rerun.md
  - A143-effective-agent-context-and-deerflow-residue-audit.md
  - ../evidence/a148-tiktok-live-guild-thin-kernel-e2e-2026-08-24.json
---

# A148 TikTok 直播公会薄内核真实端到端

## 测试问题

在最新提交 `da6536f1`、真实 Gateway/Nginx、全新 Thread 中原样输入：

> 我是做 TikTok 直播公会的，主要地区为 MENA 和 CCA，我该怎么起号

使用 GLM 5.2 思考模式，关闭 Memory、Plan 和子 Agent，不向模型补充标准答案，不预先激活 Skill，完整走
`2026 -> Gateway -> Lead -> provider -> RunJournal -> UI history`。

## 结论

> 运行闭环通过，薄内核与上下文减负生效，但本轮业务验收失败。

Agent 用 1 次模型调用、4,616 Token 和约 56 秒完成回答，相比 A112 的 7 次调用、25,006 Token 和约
206 秒分别下降 6 次、81.5% 和约 74.6%。然而它没有把问题理解为“公会为了让潜在主播知道并选择自己，
这个对外账号应如何定位和生产内容”，而是写成了公会主体申请、主播招募、主播养号和九十天扩张的通用教程。

## 真实轨迹

ContextManifest 证明本轮没有旧会话和旧流程暗中干预：

- Memory、UserProfile、Active Skill、Durable Context、子 Agent 均为空；
- 首轮只暴露 `read_file`、`manage_user_profile`、`tool_search`、`describe_skill`、`activate_skill` 五个基础 Tool；
- 模型没有调用任何 Tool，没有搜索、对标、检查 Skill 或产出结构化孵化工件；
- 模型在 reasoning 中明确自行判断“无需搜索或数据分析，直接依据已有知识回答”。

因此，这次失败不能继续归因于历史记忆、强制工作流或多层提示叠加。它揭示的是薄内核后的另一面：模型拥有
行动权，但没有识别出这道专业、时效性问题需要先发现能力、查证业务和观察对标，便把“知道一些行业名词”误当成
“足以完成起号任务”。

## 业务复核

本轮保住了两个基础点：完整识别 `TikTok 直播公会`，保留 `MENA` 与 `CCA`。其余关键交付均未出现：

- 没有确定账号面对的是潜在主播、成熟主播、地区合作伙伴还是其他人群；
- 没有区分公会的业务对象和账号内容受众；
- 没有账号定位候选、推荐方向、人设、表现形式或长期内容世界；
- 没有对标账号或地区证据；
- 没有一个今天可以直接拍摄的具体选题，更没有脚本；
- 结尾仍以能力菜单和资质阶段追问收束，像顾问交付，不像员工先完成一版工作。

回答还在没有证据的情况下写入审核周期、分成比例、区域 ARPU、养号时长、开播时段、投流配额和主播规模等
大量具体数字。即使其中个别数字碰巧正确，本轮也没有可追溯来源，不能进入正式起号判断。

## 与 A112 的关系

A112 的旧孵化链虽然昂贵、含错误语义组件并编造用户资源，至少识别了潜在主播的需求和入会动作，并形成路线工件。
A148 清除了那套强制链后，成本和速度明显改善，却连不完美的业务目标投影也一起丢失。两者不是“旧版正确、
新版错误”的二选一，而是说明：

1. 不应恢复 A112 的固定语义、内容根和多工件流水线；
2. 也不能把极薄身份提示加裸模型，称为完整孵化 Agent；
3. 下一步要验证的是 Agent 如何在保留自主判断的同时，意识到自己缺少哪类事实与方法，并发现已有能力，而不是
   给每个行业再写一条强制搜索规则或答案硬门。

## 本轮边界

本轮只固定失败现场，没有修改母提示、工具路由、Skill 或孵化运行代码。不能用这一个案例决定恢复旧工作流，也不能
因成本下降宣称 Agent 已通过。后继实验必须继续使用全新案例，分别观察“无需外部证据的普通行业”和“专业且时效性强
的行业”，避免把直播公会特例写回主脑。
