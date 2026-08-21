---
id: ADR-041
status: accepted
date: 2026-08-22
related:
  - A129-deepseek-codex-harness-reference.md
  - ADR-040-agent-owned-incubation-routing.md
---

# ADR-041 选择性吸收外部 Harness 设计

## 决定

第六版继续以 DeerFlow Harness 为唯一 Agent Runtime，不迁移到 DeepSeek Harness，也不嵌入 Codex App Server
作为第二运行时。

选择性吸收以下设计原则：

1. 采用 Codex 的极简 Agent Loop、渐进披露、稳定上下文前缀、延迟能力发现和有界工具输出原则。
2. 采用 DeepSeek 的 Definition / Provider / Consumer 能力接缝，以及“模型可见内容必须可重建”的审计原则。
3. 新增搜索、对标、媒体理解或平台能力时，只有确实存在可替换 Provider 才建立 seam；Lead 只看稳定的
   高层 Tool 合同。
4. 先实施无行为变化的 `PromptManifest` 影子观测，再评估命名 Prompt Section 或统一 Turn/Event 投影。
5. Agent 运行事件和孵化业务台账保持分离：前者解释一次运行，后者保存账号长期事实和决策。

## 约束

- `PromptManifest` 不得改变模型输入、工具目录、回答、工具轨迹或业务状态。
- Manifest 只保存来源、类别、顺序、哈希、字节数、估算 Token 和业务工件引用；密钥、Cookie、完整隐私、
  大段原始工具输出不得进入观测记录。
- 中间件不得新增营销判断、行业规则、固定孵化阶段或输出覆盖。
- 子 Agent 仅承担独立 sidecar 任务，不能形成多个拥有最终营销决策权的平级 Agent。
- 任何 Prompt、Skill 或规则优化仍须经过冻结评测、台账和 Git 审核，禁止运行时自我修改。
- checkpoint 和 `RunEventStore` 的统一只从只读投影开始；在恢复、分叉、压缩和回放验收前不得替换
  LangGraph persistence。

## 理由

DeerFlow 已经提供恢复、沙箱、授权、MCP、Skill、子 Agent、前端和测试体系，替换底座不能直接提升营销
判断，反而会引入一次高风险重写。当前真实痛点是上下文和规则来源不可一眼解释，而不是缺少另一套循环。

Codex 的运行纪律可以先解决 Token 与上下文透明度；DeepSeek 的能力接缝可以减少重复 Provider 和工具暴露。
两者都能通过小型影子实验验证，无需先破坏现役链路。

## 未采用

- DeepSeek 的 Cordis 插件树和事件溯源不整包迁入。
- Codex 的代码领域 Prompt、工具和 App Server 协议不替代 DeerFlow Gateway。
- 不将所有模块为架构整齐而重写成插件。
- 不将 Agent 会话日志与账号策略、内容、发布、指标和学习事实合并成一个万能账本。
