---
id: A75
status: verified
date: 2026-08-18
decision: accept_first_local_production_vertical
---

# A75 MediaKit 制作方案本地执行纵切

## 目的

验证已经封存的 `ProductionPlan` 能否在不重做内容判断、不暴露本机路径的前提下，真正产生可追溯的
`MediaArtifact`。首条纵切只选择确定性、可逆且无需云费用的 `editing/trim-video`。

## 已实现

- 新增薄 `MediaKitLocalProductionOperation`，精确绑定 ProductionPlan 的动作、装配步骤、计划素材、
  动态 Schema 哈希、裁剪参数哈希、输出阶段和字节上限。
- 首版只接受 `start_time / end_time`；路径、URL、文件、回调、令牌和未知参数不能进入操作合同。
- 执行前重新核验项目所有权谱系、`user_material` 来源回执、素材字节哈希、ProductionPlan 状态和
  所引用的动作、步骤与素材，任何漂移都在 CLI 启动前失败。
- 服务端为每次尝试创建独立私有输出目录，并强制传给 MediaKit `--output-path`。结果只能来自该次
  目录中的普通文件，符号链接、目录逃逸、空文件和超限文件均拒绝。
- 输出经复制前后哈希、MediaKit 元信息质检和 MIME 校验后进入私有内容寻址存储；持久产物只保存
  `artifact://` 引用、字节哈希、大小、QC、执行回执和精确操作绑定，不保存命令、临时路径或授权值。
- 同一精确操作重复执行时，第一份封存回执获胜；临时目录变化或进程重试不会制造第二个业务结果。

## 验证

- MediaKit 本地生产、路由、可信 I/O 和 MediaArtifact 聚焦回归：`51 passed`。
- 真实使用本机 `mediakit-cli 0.2.0`，将仓库演示 MP4 裁剪为一份 1 秒视频；产物为
  `video/mp4`、346,615 字节，QC 通过，输出封存为 `artifact://`，执行后临时工作目录为零。
- 反向测试覆盖 Schema 漂移、未绑定方案节点、provisional 方案生成 final、输出目录逃逸、二级定位符、
  授权素材执行前被修改，以及重复执行复用。

## 仍未完成

- 当前是可调用的后端执行内核，尚未接入内容工具、Gateway 或用户审阅界面；普通用户还不能从已保存
  ProductionPlan 直接发起这次裁剪。
- ProductionPlan 是人类可审阅计划，不是媒体 DSL；首版不尝试从任意自然语言动作自动猜测时间码。
- 字幕、拼接、混音、合成等本地能力仍需各自的窄操作合同和真实验收，不能由动态 Schema 自动宣称支持。
- 云能力、费用批准、发布预演与平台发布不属于本切片。

## 判定

接受 `ProductionPlan -> reviewed local operation -> MediaKit -> MediaArtifact` 为首条真实制作纵切。
W04 已具备一个经过真实素材验收的执行能力，但在高层入口接线和更多能力逐项验收完成前，不能宣称
整个制作板块或发布前业务闭环已经完成。
