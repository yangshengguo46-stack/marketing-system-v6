# A46 项目绑定与重水化回执

## 范围

- 起始提交：`00561bb4`
- 分支：`codex/v6-comprehension-core`
- 日期：2026-08-17
- 目标：补齐 W01 的项目 API、线程绑定和运行时重水化，不修改内容脑。

## 失败基线

```text
ImportError: cannot import name 'incubation_projects' from 'app.gateway.routers'
```

## 自动测试

```text
PYTHONPATH=. uv run pytest \
  tests/test_incubation_projects_router.py \
  tests/test_incubation_ledger.py \
  tests/test_threads_router.py \
  tests/test_gateway_services.py -q

223 passed, 1 warning in 9.47s
```

覆盖项目列表用户隔离、响应 owner 隐藏、未知线程/项目拒绝、通用 metadata 防伪造、run context
防伪造、分支线程继承绑定，以及真实 `start_run` 对线程绑定的重水化。失效绑定在 Agent 执行前
返回 `409`。

完整离线后端套件：

```text
DEER_FLOW_AUTH_DISABLED=false make test

11750 passed, 76 skipped, 17 warnings in 468.31s
```

## 本机运行回执

运行中的 Gateway 热加载后：

```text
GET  http://127.0.0.1:8001/health                                      -> 200
GET  http://127.0.0.1:8001/api/incubation/projects                     -> 200
GET  http://127.0.0.1:2026/api/incubation/projects                     -> 200
POST http://127.0.0.1:8001/api/incubation/projects                     -> 201
POST http://127.0.0.1:8001/api/threads                                 -> 200
PUT  http://127.0.0.1:8001/api/incubation/threads/.../project          -> 200
GET  http://127.0.0.1:8001/api/incubation/threads/.../project          -> 200
```

项目 ID 为占位验收标识 `w01-live-20260817`，未记录用户身份、密钥或 Cookie。创建后再次读取返回
同一项目和时间戳，证明数据来自持久台账而非进程内缓存。

## 未完成

- 前端尚无项目选择器。
- 内容理解产物尚未在生产 Tool 中自动写入项目谱系。
- 本回执未调用模型、抖音或 MediaKit。
