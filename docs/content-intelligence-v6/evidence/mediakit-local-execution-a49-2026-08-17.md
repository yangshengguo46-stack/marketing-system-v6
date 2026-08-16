# A49 MediaKit 本地执行回执

## 失败基线

```text
ImportError: cannot import name 'MediaKitExecutionReceipt'
source mutation test: DID NOT RAISE MediaKitCommandError
```

测试先固定了本地执行、输入内容哈希、输出预算、严格元信息适配、角色继承和不持久化路径；
随后再实现执行器与合同。

## 本机真实执行

输入是一段本机生成的 1 秒测试视频，不包含用户素材。执行命令使用
`mediakit-cli --local video probe-video-metadata`，未调用云端能力、未产生费用。

```text
cli_version: 0.2.0
schema_sha256: 9f14f6e2ba82038254f935e4d89ba4e44ff25cc17525ca6567575c8b3a9e06aa
source_content_sha256: 821e748ac1f2240cde48855842c28bd92f9a350cca3ed1bee56e71869d9d013e
output_sha256: 37cf9e196e0ca9264ff582c6d871f091da9a90f00f5fac306a8bf5d04e21b805
duration: 1.0
frame: 320 x 240
```

原始本地路径、命令参数和 CLI JSON 未写入本回执。CLI 报告本机 Skills 尚未同步到 `0.2.0`；
本轮没有自动执行全局更新。

## 自动回归

```text
MediaKit focused suite:
11 passed in 1.86s

MediaKit, incubation ledger, task runtime, architecture and guidance suite:
68 passed in 7.49s

full backend suite:
11771 passed, 76 skipped, 17 warnings in 420.58s
```

## 未验收

- 云端 ASR、OCR、场景切分的费用授权、持久提交意图、轮询、重启恢复和结果文件质检。
- 抖音作品页到授权直链或本地文件的真实解析器。
- 一个真实账号的多视频观察与人工内容诊断对齐。
- 本地剪辑、字幕、裁剪、拼接、混音和合成的 `MediaArtifact`。
