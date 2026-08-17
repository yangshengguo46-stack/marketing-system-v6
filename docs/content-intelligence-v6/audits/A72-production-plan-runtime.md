---
id: A72
status: implemented
date: 2026-08-18
---

# A72 素材与制作方案运行时

## 本轮实现

新增 `AdaptedDraft + FormatDecision -> ProductionPlan` 的有界结构化运行时。

- 模型调用前核验精确 AdaptedDraft、FormatDecision、BaseDraft、MessagePlan 和已审阅用户素材谱系。
- 总输入限制为 32,000 UTF-8 字节；适配单元、形式执行上下文和单份素材摘要分别限额。
- 最多接收八份同项目 `media_observation + user_material`，且每一份都必须已被精确 FormatDecision 审阅。
- 模型只生成素材需求、拍摄/录音/排版动作与装配顺序，不能换题、改观点、补事实或编造已有素材。
- 销售、平台、发布、投流、审批、固定时长、固定镜头数、频率和配额不属于 ProductionPlan。
- 图文与纯素材方案不能强迫表演或场面调度；只有微短剧和情景剧允许叙事执行提示。
- 素材不足时允许封存 `provisional` 方案并保留缺口；模型或合同失败不封存半份产物。

## 验证

父级合同和新运行时相关回归 `23 passed`；与 FormatDecision、AdaptedDraft 等上游联合回归在开发任务中
`101 passed`，主线复核的聚焦集合 `51 passed`。Ruff、格式和差异检查通过。运行时尚未接入
`explore_content_world`，MediaKit 也尚未消费该方案，因此不宣称制作链完成。
