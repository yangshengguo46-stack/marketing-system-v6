---
id: A53
status: reviewed
traced_at: 2026-08-17
reviewed_at: 2026-08-17
decision: adopt_isolated_trusted_io_and_keep_live_cloud_disabled
sources:
  - /usr/local/bin/mediakit-cli@0.2.0
  - MediaKit source@279e5bb97e97c6875ae2c6891c2c3fa9a43f39c0, read-only
  - backend/packages/harness/deerflow/community/mediakit/driver.py
  - backend/packages/harness/deerflow/community/mediakit/router.py
  - docs/content-intelligence-v6/audits/A51-mediakit-cloud-driver-mocked-acceptance.md
  - docs/content-intelligence-v6/audits/A52-mediakit-exact-approval-ledger.md
---

# A53 MediaKit 可信输入与结果物化审计

## 当前缺口

A52 已把一次云操作绑定到 owner、项目、素材摘要、能力参数、Schema 和费用上限，但请求中的素材
SHA 仍只是声明值。A51 的模拟来源可以返回任意签名 URL，模拟物化器也可以直接声称已经下载和质检。
在这两个受信依赖落地前，精确批准仍不能证明云端实际读取了哪一份字节，任务结果也不能成为制作产物。

## 已追踪事实

1. MediaKit CLI `0.2.0` 允许云任务直接接收本地文件。CLI 会申请上传地址并上传文件，再把
   `mediakit://` file ID 交给能力接口；因此第六版不需要自行制造公网素材 URL。
2. CLI 上传缓存的本地身份由路径、大小和修改时间组成，不含内容哈希。第六版必须先把输入复制到
   私有内容寻址路径，并在提交前后自行复核 SHA-256，不能把该缓存当作内容完整性证明。
3. README 明确云端结果以 URL 返回。`shared query-task --schema` 当前只公开 `video_url` 和
   `audio_url`，而不同能力的最终文件类型并不相同；不能把所有 URL 都按视频处理。
4. 第五版 E15 向 `query-task` 传入 `--output-path`，但当前 query-task 输入 Schema 和云执行源码均
   不消费该字段。那段代码没有形成通用的下载、哈希或质检实现，不迁移。
5. 供应商 URL 可能带短命签名。URL、响应正文、临时路径和下载异常原文都必须停留在执行边界；持久
   回执只保留内部引用、内容哈希、MIME、字节数和操作谱系。

## 已采用合同

- `MediaKitTrustedSourceStore` 将受信本地视频复制到 owner/project 隔离的内容寻址目录，生成由
  owner、项目、权利引用和内容 SHA 共同决定的稳定 `source_ref`。
- 云驱动在消费批准前解析并复核真实字节，提交后再次复核；只有该私有本地来源可以进入当前云驱动。
- `MediaKitSafeHttpDownloader` 只接受 HTTPS、显式允许的供应商主机和公开地址，逐跳检查重定向，
  流式执行字节上限并计算 SHA-256。
- `MediaKitCloudResultMaterializer` 只处理已经登记的能力输出策略。下载完成后必须通过注入的能力专属
  质检器，再原子写入内容寻址产物和无 URL 的任务回执；同一任务恢复时复用首个已封存结果。
- 首片只实现视频文件质检边界，不把 ASR/OCR/场景切分的结构化结果伪装成视频文件。每项能力仍需
  单独策略和真实回执。

## 失败测试与修正

首个失败基线在测试收集期因 `MediaKitCloudOutputPolicy` 不存在而失败。实现后的安全复核又用
失败测试固定了三个易被忽略的情形：

- 真实字节校验必须先于批准消费和云端调用；
- 供应商已返回任务号后才发现素材变化时，返回固定失败状态并保留远端句柄供对账，不能抛错丢失句柄；
- 并发物化同一任务时只有第一份原子封存回执生效，败者复用胜出结果并清理自己的孤立产物。

## 验收结果

- MediaKit 与可信 I/O 聚焦测试：`36 passed`。
- 媒体、长任务、批准账本和迁移联合回归：`102 passed`。
- 异步阻塞 I/O 回归：`71 passed, 2 warnings`；新实现静态扫描无发现。
- 真实本机烟测使用 CLI `0.2.0` 完成私有暂存、双哈希校验和本地视频探测，结果为
  `video/mp4`、`2320` 字节，未返回本机路径。
- 完整离线后端回归：`11824 passed, 76 skipped, 17 warnings in 422.15s`。

## 当前边界

代码仍未注册到 Gateway、Lead 或 MCP 工具集。也未配置真实供应商输出主机白名单，未开放产物读取
API，未为 ASR、OCR、场景切分或音频结果登记专属物化策略。用户批准的金额也仍只是本地合同，供应商侧
尚无已验证的硬封顶。因此本切片只标记 `reviewed`；没有上传用户素材、调用 MediaKit 云端或产生费用。
