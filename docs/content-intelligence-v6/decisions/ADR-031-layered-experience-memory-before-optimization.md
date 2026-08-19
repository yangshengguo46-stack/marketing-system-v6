# ADR-031：先建立分层经验记忆，再做检索与离线优化

## 状态

Accepted，2026-08-19。追加式内容根反馈合同已实现；在线检索、自动捕获和提示优化尚未启用。

## 背景

第六版已有事实台账、内容地图、对标证据、MediaKit、HLLM 和方法资料，但用户对内容根的纠错仍停留在聊天
与文档。继续改提示词、增加子 Agent 或安装向量库，都无法弥补“没有可复用确认经验”的缺口，并可能再次
造成第四版式的多套规则争权。

## 决定

- 在现有 incubation ledger 中分开事实/证据、确认案例和程序式方法三类记忆，不安装 LangMem、AutoGen、
  Agent Lightning 等第二运行时。
- 先使用 `RootFeedbackRecord` 保存一次完整纠错，并精确绑定被评价的 `content_map_candidate`。
- 反馈为追加式工件；争议、替代和退休均创建带父级的新版本，不更新旧记录。
- `best / acceptable / rejected / no_strong_root` 均为合法人工结论，多种可接受答案不得强行压成唯一金标。
- 线上 Lead 暂不自动读取反馈。检索必须先通过全新留出集，且同时返回适用案例、反例、条件和状态。
- 初期使用结构化过滤与小量模型比较，不预设向量数据库。嵌入检索只有证明提高最终判断后才可引入。
- DSPy、动态 cheatsheet、ACE 或微调只能在后台生成候选版本；不得在线修改核心提示词或 Skill。
- 多 Agent 只承担并行研究和有客观合同的复核，内容根仍由一个 Lead 与用户选择收敛。

## 未采用方案

- **直接把所有历史聊天塞进上下文**：Token 成本高，旧错误和新结论没有状态边界。
- **立刻建设词典或案例向量库**：相似不等于适用，会继续放大三金、水贝等邻近但错误的方向。
- **模型自我反思后直接写规则**：生成者、裁判和规则修改者是同一模型，缺少外部真值。
- **多个子 Agent 投票选根**：相关模型错误高度相关，多数票不能替代用户确认和独立证据。
- **用播放量训练内容根**：单条流量混合了分发、表现形式、账号基础和外部事件，不能证明长期内容世界正确。

## 后果

- 用户的纠错从聊天记忆升级为可查询、可版本化、可回滚的数据资产。
- 当前行为不会立即变聪明，因为本 ADR 刻意不允许未经评测的反馈注入现役 Lead。
- 下一项产品工作是最小确认入口与只读检索实验，不是再改内容根提示词。
- 未来的方法优化有清晰数据谱系，能定位召回、选择、IP 可行性或标签分歧，而不是笼统归因于模型。

## 证据

- `docs/content-intelligence-v6/audits/A96-content-root-bootstrapping-loop.md`
- `docs/content-intelligence-v6/audits/A108-agent-community-memory-and-evaluation-methods.md`
- `backend/packages/harness/deerflow/incubation/root_feedback.py`
- `backend/tests/test_incubation_root_feedback.py`
