# A54 MediaKit 首个云能力证据

## 本机与源码

```text
mediakit-cli 0.2.0
local source HEAD:  279e5bb97e97c6875ae2c6891c2c3fa9a43f39c0
GitHub remote HEAD: 279e5bb97e97c6875ae2c6891c2c3fa9a43f39c0
```

动态 Schema 去掉提示字段后规范化哈希：

```text
video/enhance-video 5573324d5727b5398b13ca89182a1e45c7953c9a8389bb12eec0b331eca46f00
shared/query-task    40758b327a1df82dbc63b0a0e9d792a24b0a69144529987309363810d59ff5c7
```

## 官方文档快照

| 文档 | 更新时间（UTC） | 正文 SHA-256 |
|---|---|---|
| `2279230` 提交画质增强任务 API | `2026-08-07T06:16:55Z` | `3fc020433a5f1dc60eef25070c9ea54126433b8cc4bb059bfb6d26a96fe85c64` |
| `2279961` 画质增强开发指南 | `2026-08-06T13:37:22Z` | `a04081345615297d5aece3facbf8194acbba8f97d02a1fc4a2650fceb3d8b792` |
| `2278532` 查询任务信息 API | `2026-08-12T09:26:25Z` | `b1ea8f3cf7b85707e87d7e20e6e3b87141c6e337cb2502e409b99f59912dd750` |
| `2486473` 视频工具计费 | `2026-08-06T13:38:50Z` | `41e6833f4ca2ae1946e241d2e273b3fea833815dc4ccd129abf4b25115789ad6` |

官方来源：

- https://docs.volcengine.com/docs/6448/2279230
- https://docs.volcengine.com/docs/6448/2279961
- https://docs.volcengine.com/docs/6448/2278532
- https://docs.volcengine.com/docs/6448/2486473

## 选择回执

```text
selected candidate: video/enhance-video
first-run version: standard only
first-run output: <=720P, <=30fps, synthetic video only
current rate: 0.75 CNY/output minute
one-second formula estimate: 0.0125 CNY
provider-side per-task hard cap: not found in CLI schema or official submit API
live execution: disabled
```

ASR、OCR 和场景切分的能力 Schema 当前只把终态描述为 `local_path`，通用查询 Schema 也未声明其
结构化结果。它们保留为后续逐能力验收对象，没有被错误登记成视频文件输出。

## 未发生

- 未调用 `mediakit-cli --cloud`。
- 未上传用户素材或合成测试素材。
- 未消费云处理批准或费用批准。
- 未注册 Gateway、Lead、MCP 或后台驱动。

