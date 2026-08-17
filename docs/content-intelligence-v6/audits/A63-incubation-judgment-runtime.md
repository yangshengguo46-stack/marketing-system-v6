---
id: A63
title: 孵化判断有界运行时
status: implemented
date: 2026-08-17
---

# A63 孵化判断有界运行时

## 实现

新增薄 `generate_incubation_judgment` 服务。它接收已封存的 `IncubationBrief`、冻结
`content_world`、可选 `BenchmarkSnapshot` 和受众 `EvidenceSnapshot`，调用一个注入式结构化模型
回调，再使用 A60 的确定性封存函数建立精确父级谱系。它没有注册成新的 Lead 工具，也没有建立第二套
Agent 运行时。

提示只要求定位、受众假设、人设、账号级长期表现方式、变现假设、依据、未知和备选方案。信息不足
允许返回未知或空判断；不要求固定模板、数字配额、实验、发布日程或平台操作。模型必须原样使用冻结
地图版本，不能重选内容根，变现只能留在孵化判断中。

## 上下文与证据边界

首次审查发现候选实现会把整份对标和受众快照放进模型输入，绕过已有的有界 Lead 投影。失败测试后
改为：

- `BenchmarkSnapshot` 与 `EvidenceSnapshot` 必须同时通过项目、产物类型、证据角色和自身合同校验。
- 完整快照继续保留在业务台账；模型只读取各自的 `to_lead_projection`。
- 冻结地图只投影版本、内容根、受众疆域、长期承诺、观察方法和防漂移边界，不复制全地图。
- 一次孵化判断的完整模型输入硬限制为 16,000 UTF-8 字节；证据过多或元数据无法在预算内表达时，
  在模型调用前明确失败，不做无声截断。
- 模型失败或结构合同失败不会封存半份判断。

## 验证与剩余工作

实现与测试：

- `backend/packages/harness/deerflow/incubation/judgment_runtime.py`
- `backend/tests/test_incubation_judgment_runtime.py`

运行时与 A60 领域合同联合回归 `14 passed`，Ruff、格式及差异检查通过。当前状态为
`implemented`：还需从用户原话构造/更新 Brief、在选定项目中读取可用证据、调用真实模型、保存产物并
把判断投影接入起号回答。未经这些接线不能称为完整孵化脑已运行。
