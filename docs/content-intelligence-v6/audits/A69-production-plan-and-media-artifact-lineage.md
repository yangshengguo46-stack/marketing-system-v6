---
id: A69
status: implemented
date: 2026-08-18
---

# A69 素材方案与成片产物谱系

## 问题

初版候选让 ProductionPlan 直接消费 BaseDraft，绕过了已经选择的表现形式和适配稿；MediaArtifact
也允许未被方案批准的媒体观察或其他方案的中间成片作为输入。这会让制作层重新发明内容，并污染素材权利边界。

## 修正

- ProductionPlan 精确绑定 `AdaptedDraft + FormatDecision`，保存适配稿父级和适配正文哈希，不再直接
  消费 BaseDraft。
- 适配稿必须来自同一个精确 FormatDecision，且两者的形式、基础稿绑定和父级完全一致。
- 已有素材只接受同项目、角色为 `user_material` 的 `media_observation`，并且必须已经被精确
  FormatDecision 审阅；Topic/Benchmark 证据不能冒充生产资源。
- MediaArtifact 保存适配正文哈希、精确 ProductionPlan、输入集合哈希、MediaKit 执行回执、稳定
  `artifact://` 引用、实际媒体字节哈希和 QC。
- MediaObservation 输入必须在 ProductionPlan 明示批准；MediaArtifact 输入必须由同一个
  ProductionPlan 的前一步产生。方案 envelope 缺失任何已声明父级时拒绝。
- 产物合同不保存本机路径、临时 URL、Cookie、Token、API Key 或原始命令。

## 验证

素材方案和媒体产物合同回归 `29 passed`。当前完成的是封存与谱系，ProductionPlan 模型运行时、
MediaKit 动态 Schema 执行和真实输出物化尚未接入内容工具。

