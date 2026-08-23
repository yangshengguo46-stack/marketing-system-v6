---
id: ADR-050
status: accepted
date: 2026-08-23
related:
  - ../audits/A143-effective-agent-context-and-deerflow-residue-audit.md
  - ../audits/A145-product-identity-and-explicit-skill-lifecycle.md
  - ADR-034-domain-skill-layering-and-lifecycle.md
  - ADR-049-agent-foundation-and-context-layering-standard.md
---

# ADR-050 Skill 检查与 Run 级显式激活分离

## 决定

第六版统一采用 `discover -> inspect -> activate -> use` 的 Skill 生命周期。发现和检查没有执行授权；只有用户
显式 `/skill` 或 Agent 成功调用 `activate_skill(exact_name)` 才建立激活来源。

Agent 自选激活只对当前 Run 生效，不写入 checkpoint。用户 `/skill` 激活在同一 Run 中拥有优先级，Agent 不能
覆盖。任何普通 `read_file(SKILL.md)`、历史 `skill_context` 或伪造 ToolMessage 都不能改变工具可见性、secret
绑定或活跃 Skill 正文。

## 依据

- 阅读可能只是比较或审计，不能等同于采用；
- A143 证明“读取即激活”会让长会话越来越僵化，并产生隐形权限变化；
- Run 级激活保留模型自主选择方法的能力，又避免一次选择永久污染账号或用户；
- 用户明确选择应高于 Agent 的自主路由；
- 启用清单、路径和内容哈希复核能把模型意图与真实安装资产绑定。

## 后果

- `describe_skill` 成为只读检查接口；
- `activate_skill` 在 Lead、嵌入式客户端和子 Agent 中作为框架能力存在；
- 工具策略和 secret 中间件只读取受保护的激活来源；
- 旧 `skill_context` 保留 checkpoint 兼容和“曾检查”展示，不再拥有行为权威；
- 后续 ContextManifest 必须分别展示 inspected 与 activated，不能再只写“有 Skill”。

## 不采用

- 不继续使用“读取即应用”；
- 不把 Agent 自选激活跨 Run 持久化；
- 不让 Skill 修改产品身份或项目事实；
- 不用行业关键词硬门强制激活；
- 不因为激活 Skill 就固定模型的工具轨迹或输出模板。
