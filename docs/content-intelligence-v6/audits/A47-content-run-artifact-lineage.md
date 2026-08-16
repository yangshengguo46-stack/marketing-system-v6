# A47 内容纵切项目谱系审计

## 状态

`reviewed -> implemented; E2E-01 semantic migration and five-artifact persistence passed; fact-boundary and performance follow-up required`

## 问题

A46 已能把项目绑定重水化到每次运行，但内容工具仍只返回聊天答案。语义阅读、长期地图、
具体选题、讲述策划和基础成稿没有进入项目事实台账，线程切换、压缩或后续制作都无法可靠引用
同一版本。

第一轮真实黄金礼品验收还发现一条运行时接线错误：线程和项目绑定均存在，工具却从
`RunnableConfig.context` 读取身份，实际回执为 `incubation_persistence.status=not_selected`。
这证明单元测试直接构造的配置没有覆盖 LangGraph 生产工具注入方式。

## 决策

- 内容工具采用 DeerFlow 现有的 `@tool + ToolRuntime` 约定，与抖音官方证据工具一致。
- 项目、用户、线程和运行身份只读取服务端注入的 `ToolRuntime.context`；模型 Schema 仍只有
  `user_request`。
- 一次成功内容纵切最多封存五类产物：`content_reading`、`content_world`、`topic_brief`、
  `message_plan`、`draft_version`。
- 长期 `content_world` 继续复用既有内容寻址适配器；一次搜索发现的命名候选、热点和运行记录
  不参与地图版本身份。
- `topic_brief` 同时引用阅读记录与冻结地图；讲述策划引用选题；基础成稿引用讲述策划。
- 未选项目时继续正常回答；台账失败时保留答案并只返回固定脱敏状态，不能把持久化变成创作硬门。

## 真实业务验收

冻结输入为：

```text
我是做黄金礼品的，我要怎么起号？
```

第一次真实运行的长期判断已经脱离黄金材质，进入“礼作为人与人关系秩序的实践”，但因上述
运行时读取错误没有落盘。修复后使用全新线程、同一模型和同一句输入复跑，结果为：

```text
长期内容根：以礼待人：人们如何用礼节、礼物和礼制来维系彼此的关系与社会秩序
具体选题：村里人随份子，为什么不是在“送钱”而是在“织网”
```

数据库与隐藏工具回执同时确认五类产物各一条，并形成：

```text
content_reading + content_world
                -> topic_brief
                -> message_plan
                -> draft_version
```

因此 E2E-01 的两个核心条件已经通过：内容根没有停留在黄金商品目录，且一条地图内的具体可拍
选题可以进入可追溯项目谱系。

## 保留问题

- 本轮选题主要依赖豆瓣、知乎和维基百科等二手材料。成稿中的部分具体化表述，例如随礼参与规则，
  超出了当前来源能够稳妥证明的颗粒度；这条草稿不能直接标记为事实终稿。
- 单次运行耗时约 6 分 44 秒，13 次模型调用，共 70,323 Token。每次从头重建已确认地图不适合
  持续运营；后续应从项目台账读取确认版本，仅对新增选题路径做取证和收敛。
- 尚无用户确认、地图版本切换、产物列表 API、前端项目选择器、`FormatDecision` 和制作调用。
- 本轮只通过黄金礼品纵切，不能据此宣称营销脑整体达到 80 分。

完整命令、运行 ID、哈希摘要和测试回执见
`evidence/content-run-artifact-lineage-a47-2026-08-17.md`。
