# A107 字节 Web Search 视频能力真实审计

- 日期：2026-08-19
- 状态：reviewed
- 对象：现有 `deerflow.community.byted_search` 适配器与用户提供的独立搜索凭证
- 凭证边界：只存根目录 Git 忽略的 `.env`；本文、测试、日志和回执均不记录值

## 问题

验证豆包搜索的 API Key 是否不仅能搜索网页，还能直接搜索视频，尤其是返回可供对标采集使用的抖音作品。

## 真实调用

1. 以 `Authorization: Bearer <local secret>` 调用现有官方地址
   `https://open.feedcoopapi.com/search_api/web_search`，鉴权成功，无供应商错误。
2. 查询 `抖音 大能 腕表 视频` 返回 10 条 `WebResults`，抖音作品直链 0 条。
3. 查询 `site:douyin.com/video 大能 腕表` 返回 10 条 `WebResults`，抖音作品直链 0 条；供应商没有严格执行域名限定。
4. 查询可召回爱奇艺和 Bilibili 视频页面，但这些条目仍标为普通 `WebResults`，`ContentFormats` 为 `text`。
5. 原始 `Result` 只有 `WebResults`、`ImageResults`、`CardResults` 等字段，没有 `VideoResults`；本轮 `ImageResults` 与 `CardResults` 均为空。
6. 将请求显式改为 `SearchType=video` 后，供应商返回 `10402 invalid search type`。

## 结论

- **可用**：凭证有效，现有字节网页搜索适配器可以直接使用它取得普通公开网页证据。
- **有限可用**：网页结果可能碰巧链接到爱奇艺、Bilibili 等视频页，但没有统一的视频作者、作品 ID、播放指标或媒体类型合同。
- **不可用**：该接口不能作为抖音视频搜索、对标账号发现或多作品账号采集接口。
- **不等价**：豆包 Chat 或联网问答 Agent Pro 展示抖音视频卡片，不代表基础 Web Search API 具有相同权限。官方快速入门仍要求抖音视频另行联系售前接入并配置相应能力。

## 路由决定

- 字节 Web Search 只进入 `topic_evidence`，用于内容地图后的事实查证和外部资料召回。
- 抖音作品与对标账号继续走官方 OpenAPI（获批后）或当前已验收的本地登录态结构化浏览器采集。
- 不把“URL 指向视频站”升级成 `video_evidence`；只有平台作品标识、作者绑定和覆盖回执齐全时才能进入对标链路。

## 官方依据

- [联网问答 Agent 更新记录](https://www.volcengine.com/docs/85508/1510771)
- [联网问答 Agent 快速入门](https://www.volcengine.com/docs/85508/1544858)

## 证据

见 `evidence/byted-web-search-video-a107-2026-08-19.md`。本审计未保存密钥、完整响应正文或供应商请求头。
