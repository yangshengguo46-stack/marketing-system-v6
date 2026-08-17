# A57 MediaKit 服务器报价生产入口回执

## 红灯

```text
collection error: MediaKitEnhanceVideoQuoteService is unavailable
collection error: app.gateway.mediakit is unavailable
3 failed, 5 passed:
- quote preparation route returned 404
- disabled service returned 404 instead of bounded 503
- two quote artifacts for one operation issued two approval pairs
```

测试夹具曾从聚合包导入两个未导出的媒体元信息类型，已改为从其真实所属模块导入；这项测试装配修正
与正式产品红灯分开记录。

## 本机只读能力证据

```text
mediakit-cli version: 0.2.0
video/enhance-video schema_sha256:
5573324d5727b5398b13ca89182a1e45c7953c9a8389bb12eec0b331eca46f00
```

本次只执行版本与 `--schema` 探测，没有使用 `--cloud`，没有上传或提交任务。

## 已验证性质

- 服务器只能从当前用户、当前项目、`user_material` 角色的元信息观察和精确父级生成报价。
- 客户端额外提交费率、证据或未声明字段会在请求模型处被拒绝。
- 价格文件缺失、超限、未知字段、格式错误、失效或动态 Schema 漂移均失败关闭。
- 报价载荷与审阅响应不泄露来源定位符、权利引用、URL、本机路径或凭据。
- 报价请求只发现能力、计算估值并封存产物，不创建任务或触发云执行。
- 同一精确操作即使有多个内容寻址报价产物，也只会签发并重放同一对批准凭证。
- 旧配置对象没有 `mediakit` 字段时按关闭处理；配置示例和 Helm 配置版本同步到 34。

## 自动验证

```text
focused quote + config + Gateway:
20 passed, 1 warning in 4.11s

MediaKit + incubation lineage + config:
174 passed, 1 warning in 9.83s

Gateway startup + guidance:
30 passed in 19.87s

blocking-I/O runtime suite:
71 passed, 2 warnings in 7.81s

full offline backend:
11864 passed, 76 skipped, 17 warnings in 426.03s
```

## 未发生

- 未创建、排队或执行 `mcp_task`。
- 未注册或调用 MediaKit 云驱动。
- 未读取执行定位符、上传素材或产生费用。
- 未开放前端按钮，未宣称 `enhance-video` 已生产可用。
