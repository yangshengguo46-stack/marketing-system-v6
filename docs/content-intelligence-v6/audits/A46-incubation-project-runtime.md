# A46 W01 项目绑定与运行时重水化审计

## 状态

`reviewed -> implemented; backend live receipt passed; frontend selector deferred to W07`

## 问题

A38 已有项目、账号与产物 SQL 台账，但没有产品运行入口。A43 为对标工具临时允许
`incubation_project_id` 从普通 run context 进入，这会同时造成两类问题：客户端可以伪造项目选择，
线程重开或换客户端时又可能丢失选择。

## 决策

- 项目是用户级业务真相，不是聊天参数。
- 线程只保存服务端控制的项目引用；项目实体仍以 incubation ledger 为准。
- 只有专用绑定 API 能修改该引用，并同时校验线程所有权与项目所有权。
- `start_run` 清除 `body.config` 和 `body.context` 中的同名值，只接受线程已保存的绑定。
- 绑定项目不存在时 fail closed 为 `409`，不让 Agent 在错误项目或无项目状态下继续写证据。
- 前端选择器不塞进本切片；后端 API 已为 W07 提供稳定合同。

## 实现

- `IncubationLedgerRepository.list_projects` 提供 owner-scoped 分页读取。
- `/api/incubation/projects` 提供创建与列表；`/projects/{project_id}` 提供读取。
- `/api/incubation/threads/{thread_id}/project` 提供绑定、读取与解绑。
- 通用线程 metadata 入参将 `incubation_project_id` 作为服务端保留键清除。
- `start_run` 在 Agent admission 前读取线程、复核项目并双写运行上下文。
- Gateway 生命周期复用同一数据库 session factory 构造项目台账仓储。

## 验收边界

通过了仓储、路由、线程保留键、运行上下文和真实本机 SQLite/Gateway 回执。尚未实现前端项目选择器，
也尚未让内容纵切自动封存 `ContentWorldVersion -> TopicBrief -> MessagePlan -> DraftVersion`。
