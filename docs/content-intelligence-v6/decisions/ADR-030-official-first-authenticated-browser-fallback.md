# ADR-030：官方优先，本地已登录浏览器承担抖音只读对标回退

## 状态

Accepted，2026-08-19。候选搜索和指定账号主页已完成一个真实账号竖切验收。

## 背景

抖音官方应用凭证、稳定 Token 和 MCP SSE 均已连通，但视频搜索 Scope 和 MCP 工具尚未
对当前应用开放。等待审批不能阻断本地产品的对标研究，但通用网络搜索和视觉逐页阅读又
无法稳定地绑定账号、作品和公开指标。

## 决定

- 保留 ADR-029 的官方 OpenAPI/MCP 优先级。只有官方候选采集明确不可用时，高层对标工具
  才进入本地浏览器回退。
- 回退使用正常可见的 Playwright Chromium 和用户手动登录后的本地 StorageState。不实现反检测、
  验证码绕过、指纹伪装或账号池。
- 浏览器是本地认证和请求执行器，不是模型的视觉工具。只有白名单结构化网络响应可进入解析器；
  Cookie、StorageState、DOM、HTML、截图、临时媒体 URL 和本地路径均不进入业务合同。
- 成功是事件驱动的：真实搜索 URL 和已解析结果响应缺一不可。搜索建议、热榜或单纯页面跳转
  不能触发成功。
- Lead 只看见两个有界工具：候选账号搜索和指定账号快照。底层页面交互、接口名、凭证和
  分页不暴露给模型。
- 候选搜索仍是 `benchmark_account_candidate`；只有指定账号主页上的稳定身份与作者一致多作品
  才能生成 `BenchmarkSnapshot`。

## 未采用的替代方案

- **无限期等官方审批**：保留为最终首选路由，但不能作为当前唯一数据源。
- **普通网页搜索**：可以提供话题证据，不能伪装成账号主页覆盖和作者一致回执。
- **视觉读整页**：Token 消耗高、容易漏项，也难以校验作品 ID 与指标。
- **在业务代码中复制抖音签名与 Cookie 调用**：扩大凭证暴露和维护面，且不比本地真实页面会话更可验收。

## 后果

- 对标搜索在官方权限待批时仍可用，并且不再需要模型逐页看网页。
- 本地运行时需要 Playwright Chromium、可见浏览器和未跟踪的登录态文件；登录失效时需要用户再次手动登录。
- 页面合同变化会产生明确的 unavailable，而不是空数据成功。端点白名单、长度前缀 JSON 解码和
  完成事件都有回归测试。
- 这个回退只增加证据获取能力，不修改语义理解、内容根、内容地图、账号定位或 Lead 的营销决策权。

## 证据

- `docs/content-intelligence-v6/audits/A105-douyin-stable-token-and-search-access.md`
- `docs/content-intelligence-v6/audits/A106-douyin-authenticated-browser-fallback.md`
- `backend/tests/test_douyin_browser_fallback.py`
- `backend/tests/test_douyin_benchmark_tool.py`
