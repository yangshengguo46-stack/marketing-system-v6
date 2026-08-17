# A56 MediaKit 精确批准入口回执

## 红灯

```text
2 failed: repository has no issue_approval_pair
collection error: MediaKitCloudApprovalRequest is unavailable
2 failed: review and confirmation routes return 404
1 failed: same quote with a later issued_at is treated as a conflict
```

测试文件插入位置和导入归属各有一次夹具修正，均在正式产品红灯外单独处理。

## 已验证性质

- 客户端不能凭自造操作摘要签发批准；批准对象来自服务器报价和真实元信息父级。
- 对标素材角色被拒绝，批准载荷与审阅响应不泄露执行定位符、权利引用、本机路径或临时 URL。
- 审阅接口只返回用户作决定所需的能力、规格、价格、上限、有效期和硬封顶状态。
- 确认值变化、过期、跨项目、缺少明确确认或半对冲突均不会留下凭证。
- 两张凭证同事务写入；同报价双击、串行重试和并发重放收敛到首个签发结果。
- API 不创建持久任务，不注册或调用 MediaKit 云驱动。

## 自动验证

```text
focused approval + MediaKit:
73 passed, 1 warning in 6.59s

ownership + lineage + migrations + Gateway + MediaKit:
141 passed, 1 warning in 14.00s

blocking-I/O runtime suite:
71 passed, 2 warnings in 7.94s

full offline backend:
11849 passed, 76 skipped, 17 warnings in 428.20s
```

## 未发生

- 未生成生产报价或开放前端按钮。
- 未创建、排队或执行 `mcp_task`。
- 未上传素材、调用供应商或产生费用。
- 未宣称 `enhance-video` 已生产可用。
