---
id: A74
status: implemented_boundary
date: 2026-08-18
decision: observed_audience_enters_judgment_hllm_stays_intermediate
sources:
  - https://github.com/bytedance/HLLM
  - https://arxiv.org/abs/2409.12740
  - https://arxiv.org/abs/2508.18118
  - /Users/yangyucheng/Documents/ChatGPT/第五版营销系统/docs/mcn-incubation-v5/audits/A38-audience-intelligence-and-hllm.md
  - /Users/yangyucheng/Documents/第四版营销系统/third_party/bytedance/HLLM/HLLM_CREATOR_README.md
  - /Users/yangyucheng/Documents/第四版营销系统/third_party/bytedance/HLLM/code/HLLM_Creator_data_scripts/gpt_userinfo_open.py
---

# A74 受众观察与 HLLM 边界

## 目的

把字节 HLLM 放进第六版受众情报链，但不把它冒充成采集器、现成粉丝画像 API 或第二个
营销决策者。

## 上游能力核对

HLLM 上游研究提供层次化用户/物品表征。HLLM-Creator 的公开任务是基于最长 50 条用户历史进行
个性化创意生成，公开验证数据是 Amazon Books。仓库中的 `user_profile` 是训练输入字段；开源数据
准备脚本又使用了外部 Chat 模型生成画像文字。因此，`interests / needs / content_affinities`
不能被宣称为官方 HLLM-Creator 的现成输出合同。

## 第六版路由

```text
官方聚合画像
-> observed EvidenceSnapshot
-> A68
-> IncubationJudgment

授权受众交互
-> 项目/账号作用域 HMAC 伪名化
-> audience_behavior_snapshot
-> 单 actor 最近 50 条 HLLM 请求
-> user representation / cluster assignment
-> 多 actor 聚合、覆盖率与反例校验（待实现）
-> 独立画像解释器验收（待实现）
-> inferred audience evidence（未准入）
-> A68
```

## 已实现

- `ObservedAudienceProfile` 保留平台、账号关系、人群口径、来源权威、授权方式、覆盖和限制，
  可封存为正式 observed audience evidence。
- `followers / content_viewers / content_engagers / live_viewers / purchasers` 继续是五种不同人群，
  不因字段名相似而混合。
- 受众原始标识使用至少 32 字节密钥的 HMAC-SHA256，并绑定 owner、项目、平台和账号；
  原始 ID 和密钥不进入产物。
- `audience_behavior_snapshot` 与正式受众画像分开，不进入 A68，也不被计为伪造的正式候选。
- 评论、回复和直播聊天原文不写入模型可见产物；只保留“是否存在”与正文哈希。
- HLLM 请求只接受同一伪名 actor 的行为序列，最多取最新 50 条；聚合画像、达人作品史和
  账号聚合表现无法冒充输入。
- HLLM 请求不含交互原文、owner ID 或 project ID；回执只能声明
  `user_representation` 或 `cluster_assignment`。
- A68 现在要求 audience observation 的全部 item 都是 `observed`；本地派生、第三方估算和模型推断
  不能冒充观察。

## 未实现与准入条件

- 本机没有已验收的 HLLM 权重服务，本轮没有运行真实 HLLM 推理。
- 单 actor 的表征或分群归属不是整个账号的 cohort，不能进入 A68。
- 还需要多 actor 聚合合同、样本覆盖回执、分群稳定性/反例测试和独立画像解释器。
- 真实服务必须绑定精确 upstream commit、checkpoint ID/哈希、adapter version、输入/输出哈希和时间。
- 需要使用中文短视频受众数据做留出评测；Amazon Books 的公开结果不能直接证明对本业务有效。

## 判定

接受“观察证据立即辅助孵化，HLLM 作为后置的受众表征/个性化底座”。拒绝“单 actor 就是 cohort”、
“HLLM-Creator 原生输出自然语言粉丝画像”和“统计/估算/推断都是平台事实”。HLLM 当前不是冷启动硬门，
也不拥有孵化决策权。
