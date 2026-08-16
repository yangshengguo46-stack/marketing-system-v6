# A47 内容纵切项目谱系回执

## 范围

- 起始提交：`0f482301`
- 分支：`codex/v6-comprehension-core`
- 日期：2026-08-17
- 目标：把现有内容理解纵切封存到线程已绑定的项目，不修改内容脑提示词。

## 失败证据

第一次真实运行：

```text
thread: a47-golden-gift-20260817
run: d4ca6c0f-47ef-427a-aa47-a7530fc825a1
status: success
persistence: not_selected
database artifacts: 0
```

该线程的 metadata 已含正确项目绑定，因此不是用户漏选项目。失败测试将持久化入口改为生产实际
使用的运行时身份后，旧实现得到预期红灯：

```text
TypeError: _persist_content_run() got an unexpected keyword argument 'runtime'
```

## 修复与自动测试

`explore_content_world` 改用标准 DeerFlow `ToolRuntime` 注入；模型可见 Schema 仍只有
`user_request`。项目、所有者、线程和运行 ID 均不接受模型参数。

聚焦测试：

```text
PYTHONPATH=. uv run pytest \
  tests/test_content_intelligence_tool.py \
  tests/test_incubation_content_run.py -q

25 passed in 3.55s
```

内容、台账与 Gateway 关联回归：

```text
PYTHONPATH=. uv run pytest \
  tests/test_incubation_content_run.py \
  tests/test_incubation_content_world.py \
  tests/test_incubation_ledger.py \
  tests/test_content_intelligence_tool.py \
  tests/test_content_intelligence_delivery.py \
  tests/test_gateway_services.py -q

175 passed in 5.61s
```

## 真实黄金礼品回执

```text
project: a47-golden-gift-20260817
thread: a47-golden-gift-runtime-fix-20260817
run: 9b72b351-c501-45d1-9a1b-e5c72013aec0
model: glm-5-2-260617
status: success
elapsed: 6m44s
llm calls: 13
input tokens: 55,621
output tokens: 14,702
total tokens: 70,323
persistence: stored
```

SQLite 中五类产物各一条：

```text
content_reading  1
content_world    1
topic_brief      1
message_plan     1
draft_version    1
```

哈希摘要和父级数量：

| 产物 | SHA-256 前 12 位 | 父级数 |
| --- | --- | ---: |
| `content_reading` | `e01360751a7f` | 0 |
| `content_world` | `0882a2a9dacd` | 0 |
| `topic_brief` | `d0d5f51f4cd9` | 2 |
| `message_plan` | `cf2fd926d9aa` | 1 |
| `draft_version` | `43aefc5a0f3d` | 1 |

业务摘要：

```text
content root:
以礼待人：人们如何用礼节、礼物和礼制来维系彼此的关系与社会秩序

topic:
村里人随份子，为什么不是在“送钱”而是在“织网”——
阎云翔在下岬村看到的人情秩序
```

输出已经从“黄金”迁移到“礼与关系秩序”，并形成具体主体、事情、立场和基础稿；未注入黄金标准
答案，也没有通过浏览器或对标账号证据改写内容地图。

## 诚实边界

- 当前资料以二手来源为主，草稿中个别具体化说法仍需原著或权威材料复核。
- 本轮没有调用抖音对标工具、MediaKit、表现形式、发布或复盘。

完整离线后端套件：

```text
DEER_FLOW_AUTH_DISABLED=false make test

11757 passed, 76 skipped, 17 warnings in 436.86s
```

第一次完整运行仅因新增说明使 `AGENTS.md` 超过仓库软字节预算而失败；细节按仓库分层规则下沉到
`backend/packages/harness/deerflow/tools/AGENTS.md` 后，指导文件检查 `12 passed`，上述第二次完整
运行一次通过。功能测试在两次运行中均未失败。
