---
id: A145
status: reviewed
date: 2026-08-23
sources:
  - A143-effective-agent-context-and-deerflow-residue-audit.md
  - A144-agent-foundations-reference-library-and-v6-conformance.md
  - ../decisions/ADR-049-agent-foundation-and-context-layering-standard.md
  - ../decisions/ADR-050-explicit-run-scoped-skill-activation.md
  - backend/packages/harness/deerflow/agents/lead_agent/IDENTITY.md
  - backend/packages/harness/deerflow/agents/lead_agent/identity.py
  - backend/packages/harness/deerflow/skills/describe.py
  - backend/packages/harness/deerflow/agents/middlewares/skill_activation_middleware.py
  - backend/packages/harness/deerflow/agents/middlewares/skill_tool_policy_middleware.py
  - backend/packages/harness/deerflow/runtime/secret_context.py
---

# A145 产品身份资产与显式 Skill 生命周期整改

## 问题

A143-A144 已确认两个产品装配缺口：默认员工身份只存在于 Python 字符串；任意读取 Skill 文件会被耐久上下文
误当成激活，并进一步改变工具权限和 secret 绑定。前者无法独立版本化，后者把“看看方法”错误升级成“本任务
必须采用并获得其能力”。

## 产品身份整改

默认身份正文已迁入打包资源 `IDENTITY.md`。加载器要求正文不超过 1,600 UTF-8 字节，只允许一个产品身份标签
和一个名称占位符，并以正文 SHA-256 形成不可变版本。`agent_core_contract.py` 只负责装配，不再保留第二份身份
正文。源码和 wheel 测试同时验证资源存在，避免本地可用、安装包丢失。

该资产只描述“是谁、长期目标、如何承担任务、事实与不可逆动作边界”，没有加入固定孵化流程、平台规则、
行业答案或用户资料。

## Skill 生命周期整改

现役生命周期明确分为：

```text
discover -> inspect -> activate -> use within this run
```

- `tool_search` / Skill 索引负责发现；
- `describe_skill` 负责只读检查，返回摘要和精确激活入口；
- `activate_skill(exact_name)` 负责显式激活；
- Agent 激活来源只存当前 Run 的受保护 runtime context，不跨 Run 持久化；
- 用户 `/skill` 是显式用户指令，优先于 Agent 自选，不能在同一 Run 被覆盖；
- 旧 checkpoint 的 `skill_context` 字段保留兼容，但只显示“曾检查”，不再拥有工具或 secret 权限；
- 激活中间件复核 Tool 来源、精确名称、启用清单、真实路径与正文哈希，伪造 ToolMessage 不能获得激活状态；
- `secrets-autonomous: false` 只阻止 Agent 自选 Skill 绑定 secret，不阻止用户明确 `/skill`。

Skill 正文通过隐藏的当前 Run 上下文持续提供给模型，并在压缩后重新投影；它不是项目事实账本，也不能修改
产品身份。

## 验收

- 产品身份、Prompt 与账号方向聚焦回归：`53 passed`；
- Skill 生命周期、耐久上下文、权限、secret、Lead、嵌入式客户端和子 Agent 回归：`602 passed`；
- Ruff 检查通过，相关文件已格式化；
- wheel 内容检查确认三份身份资源均被打包。

本轮没有改变账号孵化业务方法、内容根、内容地图、制作、发布或复盘链路。下一项是只读
`ContextManifest`：先观察模型实际收到的身份、消息、Skill、Tool Schema 与预算，再决定是否继续瘦身。
