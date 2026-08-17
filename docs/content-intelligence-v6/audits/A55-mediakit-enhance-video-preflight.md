---
id: A55
status: reviewed
traced_at: 2026-08-17
reviewed_at: 2026-08-17
decision: adopt_offline_quote_binding_and_keep_live_cloud_disabled
sources:
  - /usr/local/bin/mediakit-cli@0.2.0
  - https://docs.volcengine.com/docs/6448/2486473
  - docs/content-intelligence-v6/audits/A54-mediakit-first-cloud-capability.md
  - backend/packages/harness/deerflow/community/mediakit/enhance_video.py
  - backend/packages/harness/deerflow/community/mediakit/driver.py
---

# A55 MediaKit 画质增强费用预检审计

## 问题

A54 已选择 `video/enhance-video`，但价格、输出规格和有效期尚未进入持久任务合同。若只在调用前临时
算一次金额，排队、重启或批准绑定后都可能失去当时依据；若报价已过期仍解析素材或消费一次性批准，
还会制造不必要的副作用。本切片只实现离线预检和持久绑定，不发起真实云任务。

## 已采用合同

1. 执行时发现的 CLI Schema 必须与审阅摘要一致；文档新增但 CLI 未声明的参数不能进入命令。
2. 首轮只允许 `standard`、720P 及以下、15-30fps，并要求显式版本、分辨率和帧率。专业版、回调参数
   和未审阅字段全部拒绝。
3. 价格证据保存供应商、能力、币种、来源 URL、文档 ID/哈希/更新时间、检查时间、有效期、是否存在
   供应商硬封顶和结构化费率。费率按版本、输出分辨率档位和帧率匹配。
4. 预检使用本地元数据中的正视频时长，向上取整到毫秒，再用整数微元计算估值。它明确标记为估值，
   不冒充供应商最终账单或硬封顶。
5. `MediaKitFeeQuote` 绑定 Schema、能力参数、价格证据、时长、输出规格、费率、估值、用户上限、
   有效期和输出物化策略，并只投影四个持久字段：价格证据摘要、报价摘要、估值和到期时间。
6. `mediakit-cloud-operation-v2` 将这四项与项目、素材、权利、能力、参数、Schema、币种和用户上限
   一起哈希。批准引用本身仍不进入操作摘要，避免同一精确操作换批准 ID 时改变内容身份。
7. 云驱动在本地 Schema 校验后、素材解析和批准消费前检查报价；`now >= valid_until` 即失效。
8. 报价字段继续进入授权上下文、持久 `driver_data`、重启恢复合同和私有结果回执身份。数据库字段
   被篡改或同一任务换报价时，在供应商查询或结果复用前失败。

## 失败测试

首个红灯固定了四处真实缺口：

```text
MediaKitFeeQuote.as_operation_fields: missing
pricing evidence at valid_until: did not expire
MediaKitCloudDriver(clock=...): unsupported
durable request with quote fields: invalid contract
```

随后增加恢复期反例，覆盖价格证据摘要、报价摘要、估值和到期时间被篡改，以及同一本地任务尝试复用
另一报价的私有结果回执。

## 验收结果

- 预检、云驱动和可信 I/O 聚焦回归：`54 passed`。
- MediaKit、持久任务、批准、孵化谱系和迁移联合回归：`132 passed`。
- 阻塞 I/O 回归：`71 passed, 2 warnings`。
- 本机只读探针：CLI `0.2.0`，`enhance-video` Schema 摘要仍为
  `5573324d5727b5398b13ca89182a1e45c7953c9a8389bb12eec0b331eca46f00`；一秒标准版 720P/25fps
  估值 `12500` 微元，用户测试上限 `20000` 微元。
- 完整离线后端回归：`11842 passed, 76 skipped, 17 warnings in 427.66s`。

## 当前边界

供应商提交接口仍没有单任务金额硬上限。当前估值以输入时长为保守、可复算的预检依据，实际输出规格
与账单仍需真实回执验收。驱动没有注册到 Gateway、Lead 或 MCP 工具集，也没有批准 API、真实输出
主机配置或生产能力声明。状态是 `reviewed`，不是 `adopted`；本轮没有上传素材、调用云能力或产生费用。
