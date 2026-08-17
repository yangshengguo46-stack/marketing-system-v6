# A53 MediaKit 可信 I/O 回执

## 失败基线

```text
tests/test_mediakit_trusted_io.py collection:
ImportError: cannot import name 'MediaKitCloudOutputPolicy'
```

实现后又先让两个安全回归失败，再修正代码：

```text
post-submit source mutation:
remote task handle was lost because submit() raised after the provider returned

malformed QC MIME:
"video/mp4\nx-private-path: /secret" was accepted as a durable content type
```

## 已验证性质

- 本地视频先复制到 owner/project 隔离的内容寻址目录；稳定来源引用同时绑定权利引用和 SHA-256。
- 解析只返回执行内 `EphemeralMediaSource`，私有路径不进任务数据、结果合同或 repr。
- 驱动在消费批准前校验真实字节；云提交后如果再校验失败，用固定错误和远端句柄封存为可对账失败。
- 下载只接受 HTTPS、明确主机白名单和公网地址；每次重定向重新校验，流式限制字节并计算哈希。
- 只有登记了确切 URL 字段、媒体类型和大小上限的能力可物化；视频还必须通过 MediaKit 本地元数据探测。
- 封存回执不含输出 URL、签名、远端任务原文或临时路径；并发物化只保留第一份原子回执。

## 自动验证

```text
MediaKit cloud driver + trusted I/O:
36 passed in 3.87s

MediaKit + durable tasks + approval ledger + migrations:
102 passed in 8.04s

blocking-I/O runtime suite:
71 passed, 2 warnings in 7.88s

static scan of trusted_io.py:
No static blocking IO event-loop risk findings in backend business code.

full offline backend with authentication enabled:
11824 passed, 76 skipped, 17 warnings in 422.15s
```

## 真实本机回执

生成一秒 `320x240` 黑场测试视频，走真实私有暂存、解析、字节校验和
`mediakit-cli --local video probe-video-metadata`：

```json
{"cli_version":"0.2.0","content_type":"video/mp4","size_bytes":2320,"source_content_sha256":"76efbefae98dc1292bb38ec33454c2892dd67c1c3831724870d1b6128c39623a","source_ref":"media-source:36fe441fd07e61ded5920bb2102a95117693fb951a5c0dbdbac17eba1d002063"}
```

## 未发生

- 未注册 MediaKit 云驱动或 Agent 工具。
- 未上传用户素材，未发起云任务，未产生费用。
- 未宣称 ASR、OCR、场景切分、增强或音频物化已真实可用。
- 未宣称供应商侧费用上限已可强制。
