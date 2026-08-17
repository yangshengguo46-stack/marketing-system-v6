# A55 MediaKit 画质增强预检回执

## 失败基线

```text
AttributeError: MediaKitFeeQuote has no as_operation_fields
Failed: pricing evidence at valid_until did not raise
TypeError: MediaKitCloudDriver got unexpected keyword argument 'clock'
ValueError: durable cloud request has an invalid contract
```

测试夹具中一次时间类型漏导入已先修正；它未被当作实现失败证据。

## 真实本机只读探针

探针只执行 `mediakit-cli version` 与 `video enhance-video --schema`，随后在本地计算报价；没有
`--cloud`、上传或供应商任务。

```json
{"cli_version":"0.2.0","currency":"CNY","estimated_amount_micros":12500,"fee_quote_sha256":"8d299712ceb66ba8a3c41abc72d189c99f01a601a44b1e67628307f81c97bf9c","fee_quote_valid_until":"2026-08-18T10:00:00+00:00","maximum_amount_micros":20000,"pricing_evidence_sha256":"1dafcaf8ae519932d2d7e3805f7e5e0601f85248e522a7a92b3a4463a1df9b7c","provider_hard_cap_supported":false,"schema_sha256":"5573324d5727b5398b13ca89182a1e45c7953c9a8389bb12eec0b331eca46f00"}
```

## 已验证性质

- 缺少显式版本、分辨率或帧率，超出首轮规格，Schema 漂移，价格过期或金额不足均不能生成报价。
- 报价到期瞬间即失效，并在素材解析、批准消费和远端提交前停止。
- 操作摘要同时绑定素材、能力参数、Schema、价格证据、报价、估值、币种、用户上限和有效期。
- 授权上下文、任务恢复和私有结果回执携带同一报价身份；篡改在供应商查询前失败。
- 持久任务和结果不包含价格正文、凭据、临时 URL、本机路径或供应商响应原文。

## 自动验证

```text
focused preflight + cloud driver + trusted I/O:
54 passed in 4.12s

MediaKit + durable tasks + approvals + lineage + migrations:
132 passed in 9.00s

blocking-I/O runtime suite:
71 passed, 2 warnings in 8.08s

full offline backend:
`11842 passed, 76 skipped, 17 warnings in 427.66s`
```

## 未发生

- 未注册 MediaKit 云驱动或 Agent 工具。
- 未上传素材、发起云任务或产生费用。
- 未把本地金额上限描述为供应商硬封顶。
- 未宣称 `enhance-video` 已生产可用，也未顺带放开 ASR、OCR 或场景切分。
