---
id: A54
status: reviewed
traced_at: 2026-08-17
reviewed_at: 2026-08-17
decision: select_enhance_video_as_first_live_candidate_and_keep_disabled
sources:
  - /usr/local/bin/mediakit-cli@0.2.0
  - MediaKit source@279e5bb97e97c6875ae2c6891c2c3fa9a43f39c0, read-only
  - https://docs.volcengine.com/docs/6448/2279230
  - https://docs.volcengine.com/docs/6448/2279961
  - https://docs.volcengine.com/docs/6448/2278532
  - https://docs.volcengine.com/docs/6448/2486473
  - docs/content-intelligence-v6/audits/A53-mediakit-trusted-io.md
---

# A54 MediaKit 首个云能力选择审计

## 问题

A53 已经能安全暂存输入、恢复云任务并下载、哈希和质检视频结果，但尚未证明某一个真实 MediaKit
云能力同时具备可执行 Schema、可识别终态输出、可复算费用和能力专属物化策略。本审计只选择首个
真实验收候选，不发起云任务。

## 实时事实

2026-08-17 本机与 GitHub 官方仓库的 MediaKit 源码 HEAD 都是
`279e5bb97e97c6875ae2c6891c2c3fa9a43f39c0`，本机 CLI 为 `0.2.0`。

| 能力 | 当前 CLI Schema | 终态结果 | 结论 |
|---|---|---|---|
| `video/enhance-video` | 云端异步；输入视频、版本、场景、分辨率、帧率和码率档位 | 能力 Schema 明确声明 `video_url`、`duration`、`resolution` | 首个候选 |
| `video/asr-subtitles` | 云端异步 | `final_result` 只声明含糊的 `local_path` | 暂缓 |
| `video/video-ocr` | 云端异步 | `final_result` 只声明含糊的 `local_path` | 暂缓 |
| `video/segment-scenes` | 云端异步 | `final_result` 只声明含糊的 `local_path` | 暂缓 |

`shared/query-task` 的通用 Schema 只声明 `video_url`、`audio_url` 和状态等少数字段，而官方查询接口
说明真实 `result` 随 `task_type` 变化。当前 CLI 会把供应商 `result` 展开到顶层，但它没有为
ASR、OCR 和场景切分公开可验证的结构化终态合同。因此，不能因为第五版曾经跑出结果，就把三项能力
直接登记为第六版生产能力。

## Schema 与文档漂移

当前无 `_notice` 的规范化 Schema 摘要为：

```text
video/enhance-video 5573324d5727b5398b13ca89182a1e45c7953c9a8389bb12eec0b331eca46f00
shared/query-task    40758b327a1df82dbc63b0a0e9d792a24b0a69144529987309363810d59ff5c7
```

官方文档在 CLI 构建之后又增加了 `enhance_style`、`bitrate`、`bit_depth`、`8k` 等参数，并调整了
部分输入范围。第六版只能以执行时动态发现的 CLI Schema 为命令合同；文档用于价格、行为和风险证据，
不得把 CLI 尚未声明的参数塞进命令。任何 Schema 摘要变化都要使既有批准失效并重新审计。

## 当前费用证据

官方“视频工具计费”文档更新时间为 2026-08-06 21:38:50（北京时间）。标准版和专业版均按
**输出文件毫秒级时长 × 版本/短边分辨率/帧率系数 × 0.75 元/分钟**计费，采用后付费：

| 规格 | 标准版 | 专业版 |
|---|---:|---:|
| 720P 及以下，≤30fps | 0.75 元/分钟 | 7.5 元/分钟 |
| 1080P 及以下，≤30fps | 1.5 元/分钟 | 15 元/分钟 |
| 1080P 及以下，30-60fps | 3 元/分钟 | 30 元/分钟 |
| 4K 及以下，60-120fps | 24 元/分钟 | 240 元/分钟 |

首个验收候选限定为合成测试视频、标准版、720P 及以下、≤30fps。若输出恰为 1 秒，按当前公式估算
费用为 `0.0125 CNY`。这只是可复算估值：CLI 和提交 API 都没有供应商侧单任务金额上限参数，
本地 `ApprovalGrant.maximum_amount_micros` 不能阻止供应商在价格或输出规格异常时计费。

## 终态与恢复边界

- 官方画质增强文档说明默认结果是 MP4，临时下载链接有效 24 小时；A53 必须在终态后立即物化，不能
  把 URL 当持久产物。
- 官方查询文档宣布 2026-08-20 起只能查询 30 天内创建的任务；数据库任务和内部产物仍是业务真相，
  不能把供应商查询接口当长期档案。
- 官方终态还返回 `fps` 与 `tool_version`，而 CLI 能力 Schema 当前只声明 `duration`、`resolution`
  和 `video_url`。首轮验收必须保存原始回执摘要哈希，并检查实际字段，不能提前宣称合同完整。

## 决策

1. 选择 `video/enhance-video` 作为第一个真实云验收候选，因为它与 A53 的视频下载和本地质检合同吻合。
2. 首轮只允许 `standard`，且必须显式冻结输出分辨率和帧率；`professional` 不进入首轮批准入口。
3. 下一切片先实现能力专属 Schema 检查、价格证据快照和确定性费用报价。报价过期、规格不明确、
   Schema 漂移或用户金额不足时不得入队。
4. 因供应商没有单任务硬封顶，真实调用仍需一次新的、明确到能力、素材、规格、价格证据和金额的用户
   同意；本审计不构成该同意。
5. ASR、OCR、场景切分必须先取得并固定真实终态结构，再分别增加结构化物化策略，不能复用视频策略。

## 当前状态

状态为 `reviewed`，不是 `adopted` 或生产可用。本轮没有注册驱动、上传素材、调用云能力或产生费用。

