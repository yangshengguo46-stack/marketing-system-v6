# Agent Foundations 资料库

本目录是**给 Codex、Claude Code 和其他开发 Agent 使用的第六版工程手册**。它不进入产品 Agent 的运行时
Prompt，也不是给最终用户检索的营销知识库。它解决的是更上游的问题：

> 什么才算 Agent；模型、Harness、SOUL、用户档案、项目事实、Skill、Tool、Memory、权限和评测分别负责什么。

以后开发 Agent 修改 Lead、Prompt、Skill、Memory、MCP、子 Agent、会话摘要或业务状态前，必须先用本目录
判断变更属于哪一层，不得再把失败案例直接追加到核心提示词。

## 当前结论

第六版是一个真实 Agent 系统，不是套着聊天壳的固定工作流。它已经具有模型主导的 LangGraph 循环、动态工具
选择、MCP、Skill、子 Agent、状态恢复、持久账本和不可逆操作边界。

它已经完成四项基础整改：

- 默认产品身份已成为独立、只读、版本化的 `IDENTITY.md` 资产；
- Skill 已分离发现、检查和当前 Run 显式激活；
- 每次物理模型调用已有不含正文的 `ContextManifest`；
- 用户稳定事实已有显式来源、修订、纠正和删除的最小 `UserProfile`。

但它还不是产品化完成的“用户团队员工”：

- 项目事实、会话状态、长期学习和用户画像尚缺统一的产品检查界面；
- 通用工作台协议和长会话摘要仍可能占用与任务无关的注意力；
- UserProfile 已完成真实 GLM 新会话连续性验收，尚缺前端管理和跨模型一致性验收；

所以准确判断是：**Harness 合格，基础产品分层已建立，产品 Agent 化仍未完成。** 缺少 `SOUL.md` 不是唯一病根；
默认产品身份现由职责等价的 `IDENTITY.md` 承担。

## 阅读顺序

1. [第一性原理](01-first-principles.md)：Agent 到底是什么，各层为什么不能互相替代。
2. [参考架构](02-reference-architectures.md)：吴恩达、Harrison Chase、OpenAI、Anthropic、Codex、Claude Code、Hermes 的共同点与差异。
3. [上下文与文件模型](03-context-and-file-model.md)：SOUL、USER、项目台账、Memory、Skill、Tool 和 Policy 应放在哪里。
4. [第六版标准](04-v6-agent-standard.md)：后续代码和架构必须满足的工程标准。
5. [第六版符合性审计](05-v6-conformance-audit.md)：现役系统哪些保留、修改、退役。
6. [文件与子系统地图](06-file-and-subsystem-map.md)：Codex、Claude Code、Hermes 中真正影响 Agent 的文件族。
7. [来源索引](SOURCE_INDEX.md)：所有外部结论的一手来源与使用边界。

## 使用规则

- 本目录通过仓库根 `AGENTS.md` 约束开发过程；不得把整库或其中章节注入产品 Lead。
- 资料库记录的是架构不变量，不是新的营销母提示。
- `MUST` 只用于权限、事实归属、状态一致性、上下文来源和可验证性等工程边界。
- 营销判断、创意联想、内容根、账号方向和表现形式由模型结合项目事实与按需能力自主决定。
- 新框架或新课程只能在有一手来源、明确适用边界并通过本地评测后改变标准。
- 单个案例变好不能证明架构正确；单个案例失败也不能直接成为全局规则。
- 资料、决策、代码和评测必须能互相追溯。

## 一句话架构

```text
身份与目标
  + 当前用户和项目事实
  + 模型主导的观察、判断、行动、验证循环
  + 按需技能与工具
  + 确定性的权限、状态、回执和评测
= 能代表用户持续完成工作的 Agent
```
