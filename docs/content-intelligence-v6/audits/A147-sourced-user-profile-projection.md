---
id: A147
status: reviewed
date: 2026-08-23
sources:
  - A144-agent-foundations-reference-library-and-v6-conformance.md
  - A146-shadow-context-manifest.md
  - ../decisions/ADR-049-agent-foundation-and-context-layering-standard.md
  - ../decisions/ADR-052-sourced-user-profile-projection.md
  - backend/packages/harness/deerflow/agents/user_profile.py
  - backend/packages/harness/deerflow/agents/middlewares/user_profile_middleware.py
  - backend/packages/harness/deerflow/tools/builtins/user_profile_tool.py
  - backend/tests/test_user_profile.py
  - backend/tests/test_user_profile_middleware.py
  - backend/tests/test_user_profile_tool.py
  - ../evidence/a147-user-profile-live-acceptance-2026-08-23.md
---

# A147 有来源、可纠正的最小 UserProfile

## 问题

第六版已有版本化产品身份和项目业务台账，但缺少一层很小的跨项目用户档案。结果是新任务中的 Lead 知道自己是
用户团队里的员工，却不稳定地知道老板长期偏好中文、希望先给结论或不熟悉代码。直接恢复全量自动 Memory 又会把
项目、账号、临时要求和模型推断混成永久事实。

## 实现

新增用户级 `UserProfile`，只允许四类稳定信息：背景事实、沟通偏好、协作偏好和稳定限制。Lead 通过一个可逆
`manage_user_profile` Tool 执行 `remember / replace / forget`。每次写入必须引用当前最后一条可见用户消息中的精确
原文片段，并保存消息、片段、Thread、Run 和时间的来源哈希。

存储采用用户隔离的追加式修订：每版包含前版哈希、内容哈希、变更来源和最多 16 个当前条目。写入使用乐观版本和
原子文件提交；并发同版写显式冲突，篡改修订加载失败。删除不改写历史文件。

Lead 每次物理模型调用前读取当前修订，投影为最多 2,400 UTF-8 字节的隐藏 `HumanMessage`。条目做 HTML 转义，当前
用户消息仍位于其后，并在投影正文中明确拥有更高优先级。项目、账号、品牌、产品、受众、临时任务、模型推断和
操作授权不属于该档案。画像不能授权 Tool 或外部动作。

子 Agent 不获得画像修改 Tool，也不自动继承整份画像。Lead 只在委派确有需要时把相关事实写进有界任务描述。

## 可观测与隐私

`ContextManifest` 只记录画像是否存在、版本、内容哈希、总条目数、实际投影数和省略数。画像正文、存储路径和
中间件 owner token 不进入 RunEvent。owner token 只存在于被统一脱敏的 runtime context；伪造上下文不能让
Manifest 把画像标记为可信。

## 验收

- 修订、纠正、删除、幂等、并发、条目上限、篡改失败和用户隔离通过；
- 隐藏、有界、转义、当前消息优先、空档案清残留、同步/异步投影通过；
- Tool 精确引用和模型推断拒绝、Lead 可见/子 Agent 不可修改通过；
- Manifest 同版哈希、内容不泄漏、owner token 认证和事件契约通过；
- A147、Manifest、输入权限和 Lead 装配聚焦回归 `285 passed`；共享 Lead、Client、Skill、子 Agent、授权、输入清洗、RunEvent 与
  RunJournal 邻接回归 `1439 passed, 1 skipped`，只有一条第三方弃用告警；
- 真实 `glm-5-2-260617` 使用隔离用户和全新 Thread 验收通过：输出为中文、结论优先、主动员工口吻，未出现
  老师/顾问措辞；真实用量为 `1789` 输入、`40` 输出、`1829` 总 Token。

本轮没有把 Agent Foundations 资料库注入产品 Lead，没有修改产品身份、营销方法、内容根、内容地图、制作或发布
流程。尚未完成的是面向用户的画像查看/编辑界面，以及跨全部供应商模型的表达一致性验收。
