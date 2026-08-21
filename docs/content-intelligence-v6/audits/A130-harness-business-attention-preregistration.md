---
id: A130
status: preregistered
date: 2026-08-22
sources:
  - A129-deepseek-codex-harness-reference.md
  - ADR-041-selective-harness-reference-adoption.md
  - backend/experiments/harness_business_attention_lab
---

# A130 Harness 业务注意力对比预注册

## 研究问题

外部 Harness 的设计原则能否提升第六版的实际业务判断，而不仅是降低 Token 或让架构更整齐。首轮只验证
上下文架构：当前完整 Lead Prompt 是否稀释业务注意力，以及一张不含行业答案的薄注意力卡是否改善起号
方向判断。

## 三个冻结实验臂

1. `current_full`：运行时函数生成的现役完整 Lead 系统 Prompt。
2. `minimal_host`：只保留 Lead 权责、事实边界、最小澄清和直接作答原则，不提供孵化方法。
3. `focused_business`：在 `minimal_host` 上追加一张可自由移动的业务注意力卡，不规定工具、阶段、题量、
   平台或行业答案。

三臂使用同一个 `glm-5-2-260617`、thinking 开启、temperature 0、无联网、无工具、每题每臂一次主调用。
这是一项注意力隔离实验，不等同于完整 DeerFlow Agent 验收。

## 数据与防泄漏

- 黄金礼品、水果店和 TikTok 公会是已多次使用的 `diagnostic`，只能帮助解释行为，不能决定晋级。
- 六个 `held_out` 覆盖工业服务、社区改造、银发培训、情感服务、企业培训和消费产品。
- 数据集只保存用户原话，不保存行业标准答案、内容根、目标路线或示例选题。
- Prompt 不得出现任何测试行业名，也不得出现固定步骤、固定数量或平台模板。

## 业务能力评分

盲评只看业务理解、受众关系、长期内容世界、差异化视角、业务回路和事实边界六项，每项 0 至 2 分。
不奖励标题、排版、字数、术语和自信语气。`current_full` 与 `focused_business` 的答案按 case ID 稳定换位为
A/B，裁判看不到实验臂名称。

## 晋级门槛

`focused_business` 必须同时满足：

- 至少六个 held-out 全部完成；
- 至少 62.5% 的 held-out 获得盲评偏好；
- held-out 平均总分比 `current_full` 高至少 1.5 分；
- 不得出现现役通过而候选失败的事实边界回归；
- 任一 held-out 不得比现役低超过 2 分。

即使通过，也只允许把注意力卡带入下一轮完整 DeerFlow E2E；不能直接注册中间件、Skill 或新工作流。
若 `minimal_host` 已与 `focused_business` 相当，则优先判定为去噪收益，不为业务方法卡虚增 Prompt。
