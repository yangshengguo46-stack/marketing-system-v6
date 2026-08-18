# ADR-027：保留薄合同单智能体方向，延期生产接入

## 状态

Deferred for production，Retained as preferred research direction，2026-08-19。

## 决定

保留“一个 Lead 拥有判断权，一个薄合同只召回根级候选”的架构方向。A92 不接入 Lead、Tool、Skill、MCP、
中间件、生产子智能体或现役内容根链路；核心提示词和现役运行时保持不变。

## 理由

- A92 合同成功 `12/12`，高于 A90 单工作者的 `8/12`，没有调用后路径绑定报废。
- 人工概念召回由 A90 的 `9/16` 提高到 `13/16`；人工完整案例由 `8/12` 提高到 `9/12`。
- 39/41 候选具备最终长期内容根资格，没有系统性滑入人物、事件、地点、作品、热点或具体选题。
- 三个词汇化对照的禁止标签均为零，没有把佛跳墙、叫花鸡和鱼香肉丝按字面误拆。
- 总 Token 从 A90 单工作者的 24,144 降到 11,689，且只需十二次初始请求。
- 但冻结门槛是 `14/16` 和 `10/12`；人工复核仍缺旅行、咖啡世界、佛跳墙或闽菜，不能生产晋级。
- A92 把房车案例的更大世界预标为“自驾旅行”，用户复核后判定该标注过窄。正确缺失跃迁是
  “房车旅行 -> 旅行”；原冻结标注保留为有争议的历史证据，详见 A94。

## 后果

- A92 十二题和唯一运行已消费，不得调参、改别名、改评分器或换模型后重跑。
- 不恢复双工作者，不向 A92 叠加词典、向量库、抖音证据、内容地图或更多提示层。
- 可复用薄候选合同、零至五候选、代码绑定 ID 与来源、输入预检、调用计数和原始回执机制。
- 任何后续实验必须使用新案例，只针对三个已知缺口：对象语义核心、大世界上探、产品邻接误判。
- 后续隐藏答案必须在冻结前经过用户复核，并允许多个有效根；评分器不能把载体、视角或开发者偏好冒充
  唯一业务答案。
- 在未来通过前，用户确认仍是内容根最终选择边界，搜索和内容地图只能接收已经确认的根。

## 证据

- `docs/content-intelligence-v6/audits/A92-thin-single-agent-content-root-preregistration.md`
- `docs/content-intelligence-v6/audits/A93-thin-single-agent-content-root-result.md`
- `docs/content-intelligence-v6/audits/A94-rv-travel-content-root-correction.md`
- `docs/content-intelligence-v6/evidence/thin-content-root-a92-2026-08-19.json`
