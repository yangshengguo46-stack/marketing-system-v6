---
id: A62
title: 单条内容表现形式决定谱系
status: implemented
date: 2026-08-17
---

# A62 单条内容表现形式决定谱系

## 边界

`FormatDecision` 位于已取证 `MessagePlan -> BaseDraft` 之后，只回答这一条内容用什么方式呈现。它与
`IncubationJudgment.account_presentation` 的账号级长期能力判断不同，也不把“历史故事、真实案例”
这类内容来源误当成口播、微短剧、图文等表现形式。

支持的首批形式为口头表达、微短剧、情景剧、图文、纯素材、访谈、纪录观察及可扩展自定义形式。
决定记录选择理由、已证实资源匹配、资源缺口、持续生产风险、替代形式、未知和可选叙事方法提示。
用户是否出镜、隐私、素材和产能未知时允许保持 `provisional`，不形成问卷硬门。

## 不可改写边界

- 草案没有标题、主体、具体事情、观点、正文或证据字段，因此不能借选择形式重写上游内容。
- 封存时重新读取精确 `message_plan + draft_version(stage=base)` 父产物，分别计算受保护内容、证据
  边界与基础稿正文哈希；基础稿必须由该 MessagePlan 直接派生。载荷只保留
  父产物身份、业务 ID 与哈希，不复制一份容易漂移的上游正文。
- 可选孵化判断和资源证据必须属于同一项目；被资源匹配实际引用的证据必须成为父产物。
- 叙事方法提示只允许用于微短剧或情景剧。非叙事形式不加载编剧方法。
- 合同没有平台、销售、发布、固定时长、固定镜头数、发布频率或其他数量配额。

## 验证

实现文件：

- `backend/packages/harness/deerflow/incubation/format_decision.py`
- `backend/packages/harness/deerflow/incubation/__init__.py`
- `backend/tests/test_incubation_format_decision.py`

最初的表现形式、孵化判断和内容纵切联合回归为 `39 passed`。A64 随后修正父级为
`MessagePlan + BaseDraft`，因此本文件描述的是修正后的合同；运行时验证见 A64。素材方案和 MediaKit
接线仍待完成，因此状态为 `implemented`，不是 `verified`。
