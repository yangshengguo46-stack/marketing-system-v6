---
id: ADR-036
status: proposed
date: 2026-08-21
supersedes: []
related:
  - A123-short-video-launch-planning-audit.md
  - ADR-018-artifact-graph-orchestration.md
  - ADR-021-separate-content-opportunity-account-strategy.md
  - ADR-022-propose-account-routes-before-confirmation.md
  - A124-account-brain-memory-and-skill-architecture.md
  - ADR-037-logical-account-scoped-account-brain.md
---

# ADR-036 版本化账号起号计划

## 决定

在已确认账号战略与日常内容生产之间增加一个可选的 `AccountLaunchPlan` 工件：

```text
confirmed IncubationJudgment + matching ContentWorldVersion
    -> proposed AccountLaunchPlan
    -> user confirmation or revision
    -> one planned topic seed
    -> evidence research
    -> TopicBrief -> MessagePlan -> BaseDraft
```

该工件默认表达 30 天计划，并明确第 1-7 天为第一轮验证期。7 天和 30 天是用户要求的计划视窗，
不是平台规律、成功期限或发布数量。

## 所有权

- 已确认 `IncubationJudgment` 继续独占定位、受众、人设、账号级表现形式和变现假设。
- `ContentWorldView` 继续提供可探索方向和路径，不决定发布日历。
- `AccountLaunchPlan` 只负责栏目组合、计划题眼、行动节奏、观察问题与调整条件。
- `TopicBrief` 继续独占单个已取证选题的事实与论证合同。
- 发布、回执和复盘仍由后续独立工件负责。

## 约束

1. 没有已确认路线不得生成计划；无需绑定或登录平台账号。
2. 每个栏目必须绑定当前内容地图中的真实 `path_id`。
3. 每个题眼必须写清具体主体、发生/要追问的事以及账号准备表达的立场。
4. 命名人物、历史事件、作品、数字和实时事实只能标记为待研究，不能在计划阶段伪装成事实。
5. 发布日来自明确产能或标记为暂定的产能假设；非发布日是合法的一等行动。
6. 不写固定粉丝、播放、转化阈值，不承诺爆款或 30 天起号成功。
7. 第 7 天和第 30 天检查点必须存在，但只要求回答观察问题，不作为阻止继续创作的硬门。
8. 用户确认、修改或新结果可以产生新版本；历史版本不可覆盖。

## 账号 Skill 与事实台账

一个用户的一个逻辑账号对应一个独立 `AccountBrain` 作用域；私有账号 Skill 只是其中的程序性投影。
Skill、台账和资料不能混成一个长文本：

- 私有账号 Skill 是账号脑的轻量入口，保存已确认且相对稳定的定位、受众、人设、表现形式、内容边界、
  栏目原则和当前运营方法；Lead 进入该账号时按需加载它，不污染其他账号。
- `AccountLaunchPlan`、定位、地图、发布结果和复盘继续保存在结构化事实台账。Skill 是可重建投影，
  不能成为真相源，也不能覆盖历史版本。
- 用户案例、对标拆解、公开证据、旧稿、评论和受众资料进入账号资料库。首版优先结构化过滤；只有数据量
  和评测证明有必要时才增加向量检索。
- 一次结果只进入待验证学习。反复验证且保留适用条件和反例后，才能更新私有账号 Skill。

计划包含稳定的父级绑定、版本、路径引用和时间覆盖，仍须由领域合同与代码校验。账号 Skill 负责方法，
模型负责提出栏目和题眼，输出必须落入合同。把整套日历写入全局 Lead 提示词会增加所有对话成本，也会
重现旧版固定流程和多层控制冲突。

## 后果

- 首次孵化可以在用户确认路线后交付一个真正可执行的 7/30 天运营版本。
- 同一用户的多个账号分别加载自己的私有账号 Skill 与资料空间，不共享未经批准的账号经验。
- 日常创作复用既有定位和地图，不再重复整条冷启动链。
- 批量计划不会绕过事实研究；每个真正要拍的题仍单独形成 `TopicBrief`。
- 后续调度器可以消费已确认的计划，但本 ADR 不授权自动制作或发布。

## 前置条件

本 ADR 由 `ADR-037` 的逻辑账号隔离决定约束。在双账号隔离、线程账号切换和 Skill 投影重建测试通过前，
`AccountLaunchPlan` 保持隔离实验，不能注册为 Lead 工具或默认流程。
