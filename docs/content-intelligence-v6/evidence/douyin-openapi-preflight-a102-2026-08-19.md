# A102 抖音 OpenAPI 本地预检回执

- 日期：2026-08-19
- 仓库：第六版营销系统
- MCP 可执行文件：`present`
- MCP 领域初始化：`16 tools loaded`
- `DOUYIN_CLIENT_KEY`：`absent`
- `DOUYIN_CLIENT_SECRET`：`absent`
- 发现时的声明搜索合同：硬编码 `v2 compatibility / aweme.dy.video_search_v2`
- 修复后的声明搜索合同：`absent`；现役 MCP 已改为从 `$DOUYIN_APPROVED_SCOPES` 解析，等待填写应用真实获批值
- 真实 stable client token：`not attempted; credentials absent`
- 真实视频搜索：`not attempted; credentials absent`
- 凭据扫描：本回执不含 Client Key、Client Secret、token、Cookie 或 open_id。

## 预检命令结果

```text
Douyin MCP executable: ok
Douyin application credentials: fail (missing Client Key or Client Secret)
Douyin video-search contract: fail (no approved video-search Scope declared)
```

该回执只证明本地状态，不证明抖音平台已接受请求。

## 回归回执

- 抖音、MCP 配置与 Doctor 定向回归：`129 passed`
- 完整后端非 live 回归：`12201 passed, 76 skipped`
- Ruff 检查与格式检查：通过
- Agent 指南检查：`24 AGENTS.md, 0 errors, 0 warnings`

`make doctor` 当前按设计返回两项失败：真实应用凭据缺失、真实获批 Scope 未声明。这两项失败是
阻止误报“已接通”的验收门，而不是代码回归。
