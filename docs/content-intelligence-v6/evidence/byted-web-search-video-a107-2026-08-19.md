# A107 字节 Web Search 视频探测回执

| 探测 | HTTP/供应商结果 | 返回集合 | 抖音作品直链 | 判断 |
|---|---|---|---:|---|
| `抖音 大能 腕表 视频`，`SearchType=web` | 成功 | 10 条 `WebResults` | 0 | 普通网页检索 |
| `site:douyin.com/video 大能 腕表`，`SearchType=web` | 成功 | 10 条 `WebResults` | 0 | 域名限定未形成抖音作品召回 |
| `抖音 卡斯特罗 丘吉尔 雪茄 视频`，`SearchType=web` | 成功 | 5 条 `WebResults` | 0 | 含爱奇艺/Bilibili 页面，但仍为文本网页合同 |
| `卡斯特罗 丘吉尔 雪茄`，`SearchType=video` | `10402 invalid search type` | 无 | 0 | 当前接口不接受视频搜索类型 |

原始成功响应的 `Result` 字段为：`WebResults`、`ImageResults`、`CardResults`、
`Choices`、`SearchContext`、`ResultCount`、`TimeCost`、`Usage` 与 `LogId`。本轮没有
`VideoResults`；`ImageResults`、`CardResults` 和 `Choices` 均为空。

密钥只存在本地 Git 忽略配置中，未写入此回执。完整网页摘要未保存，避免把第三方正文与临时结果沉淀为
稳定业务事实。
