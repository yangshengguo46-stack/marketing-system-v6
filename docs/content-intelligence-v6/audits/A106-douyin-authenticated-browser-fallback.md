---
id: A106
status: reviewed
reviewed_at: 2026-08-19
decision: adopt_official_first_authenticated_browser_fallback
sources:
  - docs/content-intelligence-v6/audits/A105-douyin-stable-token-and-search-access.md
  - backend/packages/harness/deerflow/community/douyin_browser.py
  - backend/packages/harness/deerflow/tools/builtins/douyin_benchmark_tool.py
  - backend/tests/test_douyin_browser_fallback.py
  - backend/tests/test_douyin_benchmark_tool.py
---

# A106 抖音本地登录浏览器回退审计

## 问题

A105 已证明稳定 `client_token` 和官方 MCP 握手正常，但当前应用未获得视频搜索
Scope，官方 MCP `tools/list` 也为空。继续改 Token 或重写 HTTP 签名不能解决外部审批
阻塞，而通用网页搜索又不能产生账号身份绑定的多作品对标证据。

## 已采用路线

高层工具保持“官方优先”：

1. `collect_douyin_benchmark_candidate` 先调用官方 OpenAPI 路由。
2. 只有官方候选采集明确报不可用时，才转到用户本地、可见、已登录的 Playwright
   会话。未知程序错误不会被回退掩盖。
3. 浏览器通过页面原生搜索交互发起请求，但采集器只保留
   `/general/search/single/` 或 `/general/search/stream/` 的结构化 JSON 结果。搜索建议、热榜、
   首页推荐、DOM、HTML 和截图均不是证据输出。
4. 候选采集使用 Unicode 归一化后的显示名精确匹配；此时仍只是候选证据。
5. 用户提供或选定账号链接后，`collect_douyin_benchmark_account` 直接采集账号主页，
   只保留同一稳定作者标识的作品，生成正式 `BenchmarkSnapshot` 和覆盖回执。

登录态只从 `DOUYIN_BROWSER_STORAGE_STATE_PATH` 指向的本地未跟踪文件读取，并再次过滤为
抖音域 Cookie 和 StorageState。密钥、Cookie 值、本地路径和原始响应不进入模型、前端、
日志或业务台账。

## 本轮故障与修正

首个实现用固定的 1.5 秒等待，页面尚未进入真实搜索页就会关闭。第二个实现虽然
等待响应，但把搜索建议和热榜接口误当成视频结果，仍会提前结束。

现在的完成条件为：

- 页面必须真正进入 `/search/` 结果 URL。
- 必须观察到首屏结果或长度前缀流，并完成 JSON 解析。
- 20 秒内没有结果响应时明确返回 `search_response_not_observed`，不将页面跳转当成成功。
- 已开始但仍未结束的流式读取在收尾阶段有时限，避免浏览器反向永久不关闭。

## 真实验收

2026-08-19 使用用户本地已登录会话执行只读验收：

- 搜索词：`大能 腕表`；目标显示名：`大能`。
- 候选采集完成真实搜索页跳转，解析 9 条作者精确匹配作品，无候选告警。
- 使用搜索结果中的稳定账号标识采集主页，返回 12 条作者一致作品。
- 主页同次可见观察为 572 条作品、9,456,925 粉丝；这些是时点值，不是受众画像或
  成功原因。
- 浏览器、对标工具、工具 Schema 和去重的聚焦回归测试 60 项通过。
- 后端全量离线套件通过 `12,233 passed, 75 skipped`，零失败；Ruff 检查与格式检查通过。

## 边界

- 这是抖音公开账号对标证据的本地回退，不替代官方 API；Scope 获批后仍优先官方路由。
- 不绕过验证码、登录失效、访问限制或平台规则。出现中间页时失败并由用户手动恢复。
- 页面和网络合同可能变化；产品可用性由真实回执和回归测试决定，不由代码中的平台枚举决定。
- 对标观察不能自动决定内容根、账号定位、受众画像、爆火因果或可复制性。
