# 抖音开放平台能力就绪矩阵

- 观察时间：`2026-08-19T08:50:03+08:00`
- 官方目录：`119` 项
- 本地薄适配器：`3` 项
- 真实调用通过：`1` 项（其中业务能力 `0` 项）
- 官方 MCP：连接成功但无工具（`0` 个工具）
- 边界：目录存在、本地声明 Scope、代码已有适配器，都不等于平台已经授权。

## 当前状态

| 状态 | 数量 |
| --- | ---: |
| 适配器已写，未声明获批权限 | 1 |
| 目录存在，当前接口合同需重查 | 12 |
| 接口已定位，尚未接入 | 29 |
| 真实调用已通过 | 1 |
| 平台拒绝权限 | 1 |
| 属于独立产品或合作计划 | 75 |

## 全量能力

| 板块 | 能力 | 鉴权 | 适配器 | 当前状态 | Scope | 下一步 | 官方文档 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 个人资料 | 抖音获取授权码 | 用户 OAuth 跳转 | 未写 | 接口已定位，尚未接入 | - | 接入鉴权基础设施并完成令牌生命周期测试 | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/account-permission/douyin-get-permission-code) |
| 个人资料 | 获取 access_token | OAuth 换取/刷新令牌 | 未写 | 接口已定位，尚未接入 | - | 接入鉴权基础设施并完成令牌生命周期测试 | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/account-permission/get-access-token) |
| 个人资料 | 刷新 refresh_token | OAuth 换取/刷新令牌 | 未写 | 接口已定位，尚未接入 | - | 接入鉴权基础设施并完成令牌生命周期测试 | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/account-permission/refresh-token) |
| 个人资料 | 生成 client_token | 应用凭据 | 已写 | 真实调用已通过（0） | - | 保留为鉴权基础设施回执，不计作业务能力 | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/account-permission/client-token) |
| 个人资料 | 刷新 access_token | OAuth 换取/刷新令牌 | 未写 | 接口已定位，尚未接入 | - | 接入鉴权基础设施并完成令牌生命周期测试 | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/account-permission/refresh-access-token) |
| 个人资料 | 获取用户公开信息 | 用户授权 access_token | 未写 | 目录存在，当前接口合同需重查 | - | 重查当前官方页面、应用类型、Scope 和请求合同 | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/account-management/get-account-open-info) |
| 关系能力 | 获取粉丝列表 | 用户授权 access_token | 未写 | 接口已定位，尚未接入 | - | 先接账号 OAuth、回调与令牌保险库，再申请并验收 Scope | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/account-management/user-data/get-fans-list) |
| 关系能力 | 获取用户的关注列表 | 用户授权 access_token | 未写 | 接口已定位，尚未接入 | following.list | 先接账号 OAuth、回调与令牌保险库，再申请并验收 Scope | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/account-management/user-data/get-user-follow-list) |
| 关系能力 | 获取用户的双向关注列表数据 | 用户授权 access_token | 未写 | 接口已定位，尚未接入 | friend.list | 先接账号 OAuth、回调与令牌保险库，再申请并验收 Scope | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/account-management/user-data/get-friend-list) |
| 关系能力 | 获取用户粉丝数据 | 用户授权 access_token | 未写 | 接口已定位，尚未接入 | fans.data.bind | 先接账号 OAuth、回调与令牌保险库，再申请并验收 Scope | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/account-management/fans-portrait-data/get-user-fans-data) |
| 关系能力 | 获取用户粉丝来源 | 用户授权 access_token | 未写 | 接口已定位，尚未接入 | data.external.fans_source | 先接账号 OAuth、回调与令牌保险库，再申请并验收 Scope | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/account-management/fans-portrait-data/get-user-fans-origin) |
| 关系能力 | 获取用户粉丝喜好数据 | 用户授权 access_token | 未写 | 接口已定位，尚未接入 | data.external.fans_favourite | 先接账号 OAuth、回调与令牌保险库，再申请并验收 Scope | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/account-management/fans-portrait-data/get-user-fans-like) |
| 关系能力 | 获取用户粉丝热评 | 用户授权 access_token | 未写 | 接口已定位，尚未接入 | data.external.fans_favourite | 先接账号 OAuth、回调与令牌保险库，再申请并验收 Scope | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/account-management/fans-portrait-data/get-user-fans-hot-comment) |
| 内容能力 | 查询视频分享结果及数据 | Scope 类型待核对 | 未写 | 接口已定位，尚未接入 | aweme.forward | 核对 Scope 和应用资质，审计合同后增加薄适配器 | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/video-management/douyin/search-video/video-share-result) |
| 内容能力 | 查询视频携带的地点信息 | Scope 类型待核对 | 未写 | 接口已定位，尚未接入 | poi.search | 核对 Scope 和应用资质，审计合同后增加薄适配器 | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/video-management/douyin/search-video/video-poi) |
| 内容能力 | 通过videoid获取IFrame代码 | 待核对官方合同 | 未写 | 目录存在，当前接口合同需重查 | - | 重查当前官方页面、应用类型、Scope 和请求合同 | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/video-management/douyin/iframe-player/get-iframe-by-video) |
| 内容能力 | 通过 ItemID 获取 iFrame 代码 | 待核对官方合同 | 未写 | 目录存在，当前接口合同需重查 | - | 重查当前官方页面、应用类型、Scope 和请求合同 | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/video-management/douyin/iframe-player/get-iframe-by-item) |
| 内容能力 | 创建投稿任务 | Scope 类型待核对 | 未写 | 接口已定位，尚未接入 | task.posting.create | 核对 Scope 和应用资质，审计合同后增加薄适配器 | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/video-management/posting-task/create-posting-task) |
| 内容能力 | 绑定视频 | Scope 类型待核对 | 未写 | 接口已定位，尚未接入 | posting.behavior | 核对 Scope 和应用资质，审计合同后增加薄适配器 | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/video-management/posting-task/bind-video) |
| 内容能力 | 核销投稿任务 | Scope 类型待核对 | 未写 | 接口已定位，尚未接入 | task.posting.user_verification | 核对 Scope 和应用资质，审计合同后增加薄适配器 | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/video-management/posting-task/verify-posting-task) |
| 内容能力 | 查询视频基础信息 | Scope 类型待核对 | 未写 | 接口已定位，尚未接入 | posting.behavior | 核对 Scope 和应用资质，审计合同后增加薄适配器 | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/video-management/posting-task/video-basic-info) |
| 搜索能力 | 抖音视频搜索 | 应用级 client_token | 已写 | 平台拒绝权限（28001018） | aweme.dy.video_search | 在平台完成该能力审批，再运行同一只读验收 | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/douyin-search-capability/aweme-dy-video-search) |
| 搜索能力 | 抖音图文搜索 | 应用级 client_token | 已写 | 适配器已写，未声明获批权限 | aweme.experience.search | 先在控制台确认 Scope 已获批，再写入本地声明并实测 | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/douyin-search-capability/aweme-experience-search) |
| 私信群聊 | 创建/更新留资卡片 | 待核对官方合同 | 未写 | 目录存在，当前接口合同需重查 | - | 重查当前官方页面、应用类型、Scope 和请求合同 | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/interaction-management/business-tool/retain-consult-card/create-retain-consult-card) |
| 私信群聊 | 查询留资卡片 | 待核对官方合同 | 未写 | 目录存在，当前接口合同需重查 | - | 重查当前官方页面、应用类型、Scope 和请求合同 | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/interaction-management/business-tool/retain-consult-card/query-retain-consult-card) |
| 私信群聊 | 删除留资卡片 | 待核对官方合同 | 未写 | 目录存在，当前接口合同需重查 | - | 重查当前官方页面、应用类型、Scope 和请求合同 | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/interaction-management/business-tool/retain-consult-card/delete-retain-consult-card) |
| 私信群聊 | 创建/更新小程序引导卡片模板 | 待核对官方合同 | 未写 | 目录存在，当前接口合同需重查 | - | 重查当前官方页面、应用类型、Scope 和请求合同 | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/interaction-management/business-tool/micro-app-card/create-template) |
| 私信群聊 | 查询小程序引导卡片模板 | 待核对官方合同 | 未写 | 目录存在，当前接口合同需重查 | - | 重查当前官方页面、应用类型、Scope 和请求合同 | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/interaction-management/business-tool/micro-app-card/query-template) |
| 私信群聊 | 删除小程序引导卡片模板 | 待核对官方合同 | 未写 | 目录存在，当前接口合同需重查 | - | 重查当前官方页面、应用类型、Scope 和请求合同 | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/interaction-management/business-tool/micro-app-card/delete-template) |
| 私信群聊 | 图片上传 | 待核对官方合同 | 未写 | 目录存在，当前接口合同需重查 | - | 重查当前官方页面、应用类型、Scope 和请求合同 | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/interaction-management/business-tool/image-upload) |
| 数据开放服务 | 三方活动数据同步 | Scope 类型待核对 | 未写 | 接口已定位，尚未接入 | interest.activity.sync | 核对 Scope 和应用资质，审计合同后增加薄适配器 | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/data-open-service/douyin-interest/third-party-data-sync) |
| 数据开放服务 | 三方活动状态同步 | 用户授权 access_token | 未写 | 接口已定位，尚未接入 | interest.activity.sync | 先接账号 OAuth、回调与令牌保险库，再申请并验收 Scope | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/data-open-service/douyin-interest/tp-activity-status-sync) |
| 数据开放服务 | 三方活动报名数据同步 | Scope 类型待核对 | 未写 | 接口已定位，尚未接入 | interest.activity.sync | 核对 Scope 和应用资质，审计合同后增加薄适配器 | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/data-open-service/douyin-interest/tp-activity-signup-sync) |
| 数据开放服务 | 三方活动报名状态同步 | 用户授权 access_token | 未写 | 接口已定位，尚未接入 | interest.activity.sync | 先接账号 OAuth、回调与令牌保险库，再申请并验收 Scope | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/data-open-service/douyin-interest/tp-signup-status-sync) |
| 数据开放服务 | 三方活动图片上传 | Scope 类型待核对 | 未写 | 接口已定位，尚未接入 | interest.activity.sync | 核对 Scope 和应用资质，审计合同后增加薄适配器 | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/data-open-service/douyin-interest/third-party-image-upload) |
| 数据开放服务 | 三方活动审核结果回调Webhook | 回调验签 | 未写 | 接口已定位，尚未接入 | - | 配置回调地址、验签、去重与重放测试 | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/data-open-service/douyin-interest/tp-activity-review-callback) |
| 数据开放服务 | 三方敏感信息加密 | 本地工具 | 未写 | 接口已定位，尚未接入 | - | 先完成接口合同和应用适用性审计 | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/data-open-service/douyin-interest/third-party-encryption) |
| 抖音生活服务接口 | 门店信息查询 | 待核对官方合同 | 未写 | 属于独立产品或合作计划 | - | 按对应产品或合作计划单独申请，不计作当前应用已开通 | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/life.capacity/life.capacity.shop/shop.query) |
| 抖音生活服务接口 | 验券准备 | 待核对官方合同 | 未写 | 属于独立产品或合作计划 | - | 按对应产品或合作计划单独申请，不计作当前应用已开通 | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/life.capacity/life.capacity.fulfilment/certificate.prepare) |
| 抖音生活服务接口 | 验券 | 待核对官方合同 | 未写 | 属于独立产品或合作计划 | - | 按对应产品或合作计划单独申请，不计作当前应用已开通 | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/life.capacity/life.capacity.fulfilment/certificate.verify) |
| 抖音生活服务接口 | 撤销核销 | 待核对官方合同 | 未写 | 属于独立产品或合作计划 | - | 按对应产品或合作计划单独申请，不计作当前应用已开通 | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/life.capacity/life.capacity.fulfilment/certificate.cancel) |
| 抖音生活服务接口 | 券状态查询 | 待核对官方合同 | 未写 | 属于独立产品或合作计划 | - | 按对应产品或合作计划单独申请，不计作当前应用已开通 | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/life.capacity/life.capacity.fulfilment/certificate.get) |
| 抖音生活服务接口 | 券状态批量查询 | 待核对官方合同 | 未写 | 属于独立产品或合作计划 | - | 按对应产品或合作计划单独申请，不计作当前应用已开通 | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/life.capacity/life.capacity.fulfilment/certificate.query) |
| 抖音生活服务接口 | 验券历史查询 | 待核对官方合同 | 未写 | 属于独立产品或合作计划 | - | 按对应产品或合作计划单独申请，不计作当前应用已开通 | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/life.capacity/life.capacity.billing/certificate.verifyrecord.query) |
| 抖音生活服务接口 | 分账明细查询 | 待核对官方合同 | 未写 | 属于独立产品或合作计划 | - | 按对应产品或合作计划单独申请，不计作当前应用已开通 | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/life.capacity/life.capacity.billing/ledger.query-record-by-cert) |
| 抖音生活服务接口 | 会员数据更新 | 待核对官方合同 | 未写 | 属于独立产品或合作计划 | - | 按对应产品或合作计划单独申请，不计作当前应用已开通 | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/life.capacity/member/update.info) |
| 抖音生活服务接口 | 会员入会&退会 | 平台专项合作 | 未写 | 属于独立产品或合作计划 | - | 按对应产品或合作计划单独申请，不计作当前应用已开通 | [docs](https://partner.open-douyin.com/docs/resource/zh-CN/local-life/develop/OpenAPI/member/member.join.new) |
| 抖音生活服务接口 | 订单查询 | 待核对官方合同 | 未写 | 属于独立产品或合作计划 | - | 按对应产品或合作计划单独申请，不计作当前应用已开通 | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/life.capacity/order.query/query) |
| 抖音生活服务接口 | 下单确认 | 平台专项合作 | 未写 | 属于独立产品或合作计划 | - | 按对应产品或合作计划单独申请，不计作当前应用已开通 | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/life.capacity/tripartite.code/can) |
| 抖音生活服务接口 | 发券 | 平台专项合作 | 未写 | 属于独立产品或合作计划 | - | 按对应产品或合作计划单独申请，不计作当前应用已开通 | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/life.capacity/tripartite.code/create) |
| 抖音生活服务接口 | 发券回调 | 待核对官方合同 | 未写 | 属于独立产品或合作计划 | - | 按对应产品或合作计划单独申请，不计作当前应用已开通 | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/life.capacity/tripartite.code/callback) |
| 抖音生活服务接口 | 退款 | 平台专项合作 | 未写 | 属于独立产品或合作计划 | - | 按对应产品或合作计划单独申请，不计作当前应用已开通 | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/life.capacity/tripartite.code/refund.apply) |
| 抖音生活服务接口 | 审核回调 | 待核对官方合同 | 未写 | 属于独立产品或合作计划 | - | 按对应产品或合作计划单独申请，不计作当前应用已开通 | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/life.capacity/tripartite.code/refund.audit) |
| 抖音生活服务接口 | 信息同步 | 平台专项合作 | 未写 | 属于独立产品或合作计划 | - | 按对应产品或合作计划单独申请，不计作当前应用已开通 | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/life.capacity/tripartite.code/refund.notice) |
| 抖音生活服务接口 | 创建/修改团购活动 | 待核对官方合同 | 未写 | 属于独立产品或合作计划 | - | 按对应产品或合作计划单独申请，不计作当前应用已开通 | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/life.capacity/goods/save) |
| 抖音生活服务接口 | 免审修改商品 | 待核对官方合同 | 未写 | 属于独立产品或合作计划 | - | 按对应产品或合作计划单独申请，不计作当前应用已开通 | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/life.capacity/goods/free.audit) |
| 抖音生活服务接口 | 上下架商品 | 待核对官方合同 | 未写 | 属于独立产品或合作计划 | - | 按对应产品或合作计划单独申请，不计作当前应用已开通 | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/life.capacity/goods/operate) |
| 抖音生活服务接口 | 同步库存 | 待核对官方合同 | 未写 | 属于独立产品或合作计划 | - | 按对应产品或合作计划单独申请，不计作当前应用已开通 | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/life.capacity/goods/batch.save) |
| 抖音生活服务接口 | 查询商品模板 | 待核对官方合同 | 未写 | 属于独立产品或合作计划 | - | 按对应产品或合作计划单独申请，不计作当前应用已开通 | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/life.capacity/goods/template.get) |
| 抖音生活服务接口 | 查询商品草稿数据 | 待核对官方合同 | 未写 | 属于独立产品或合作计划 | - | 按对应产品或合作计划单独申请，不计作当前应用已开通 | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/life.capacity/goods/draft.get) |
| 抖音生活服务接口 | 查询商品草稿数据列表 | 待核对官方合同 | 未写 | 属于独立产品或合作计划 | - | 按对应产品或合作计划单独申请，不计作当前应用已开通 | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/life.capacity/goods/query) |
| 抖音生活服务接口 | 查询商品线上数据 | 待核对官方合同 | 未写 | 属于独立产品或合作计划 | - | 按对应产品或合作计划单独申请，不计作当前应用已开通 | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/life.capacity/goods/online.get) |
| 抖音生活服务接口 | 查询商品线上数据列表 | 待核对官方合同 | 未写 | 属于独立产品或合作计划 | - | 按对应产品或合作计划单独申请，不计作当前应用已开通 | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/life.capacity/goods/online.query) |
| 抖音生活服务接口 | 创建/更新多SKU商品的SKU列表 | 待核对官方合同 | 未写 | 属于独立产品或合作计划 | - | 按对应产品或合作计划单独申请，不计作当前应用已开通 | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/life.capacity/goods/goods.batch.save) |
| 小程序接口 | 商铺同步 | 待核对官方合同 | 未写 | 属于独立产品或合作计划 | - | 按对应产品或合作计划单独申请，不计作当前应用已开通 | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/micro-app/shop/synchronism) |
| 小程序接口 | 查询店铺 | 待核对官方合同 | 未写 | 属于独立产品或合作计划 | - | 按对应产品或合作计划单独申请，不计作当前应用已开通 | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/micro-app/shop/search) |
| 小程序接口 | 获取抖音POI ID | 待核对官方合同 | 未写 | 属于独立产品或合作计划 | - | 按对应产品或合作计划单独申请，不计作当前应用已开通 | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/micro-app/shop/get-douyin-poi-id) |
| 小程序接口 | 店铺匹配任务结果查询 | 待核对官方合同 | 未写 | 属于独立产品或合作计划 | - | 按对应产品或合作计划单独申请，不计作当前应用已开通 | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/micro-app/shop/task-query) |
| 小程序接口 | 店铺匹配状态查询 | 待核对官方合同 | 未写 | 属于独立产品或合作计划 | - | 按对应产品或合作计划单独申请，不计作当前应用已开通 | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/micro-app/shop/status-query) |
| 小程序接口 | 发起店铺匹配POI同步任务 | 待核对官方合同 | 未写 | 属于独立产品或合作计划 | - | 按对应产品或合作计划单独申请，不计作当前应用已开通 | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/micro-app/shop/poi-sync-task) |
| 小程序接口 | 查询全部店铺信息接口(天级别请求5次) | 待核对官方合同 | 未写 | 属于独立产品或合作计划 | - | 按对应产品或合作计划单独申请，不计作当前应用已开通 | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/micro-app/shop/query-all-shop-info) |
| 小程序接口 | 查询店铺全部信息任务返回内容 | 待核对官方合同 | 未写 | 属于独立产品或合作计划 | - | 按对应产品或合作计划单独申请，不计作当前应用已开通 | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/micro-app/shop/query-shop-all-tasks) |
| 小程序接口 | SKU同步 | 待核对官方合同 | 未写 | 属于独立产品或合作计划 | - | 按对应产品或合作计划单独申请，不计作当前应用已开通 | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/micro-app/goods-repo/sku-sync) |
| 小程序接口 | sku拉取(该接口由接入方实现) | 平台专项合作 | 未写 | 属于独立产品或合作计划 | - | 按对应产品或合作计划单独申请，不计作当前应用已开通 | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/micro-app/goods-repo/sku-pull) |
| 小程序接口 | 多门店SPU同步 | 待核对官方合同 | 未写 | 属于独立产品或合作计划 | - | 按对应产品或合作计划单独申请，不计作当前应用已开通 | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/micro-app/goods-repo/spu-sync) |
| 小程序接口 | 多门店SPU状态同步 | 待核对官方合同 | 未写 | 属于独立产品或合作计划 | - | 按对应产品或合作计划单独申请，不计作当前应用已开通 | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/micro-app/goods-repo/spu-status-sync) |
| 小程序接口 | 多门店SPU库存同步 | 待核对官方合同 | 未写 | 属于独立产品或合作计划 | - | 按对应产品或合作计划单独申请，不计作当前应用已开通 | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/micro-app/goods-repo/spu-repo-sync) |
| 小程序接口 | 多门店SPU信息查询 | 待核对官方合同 | 未写 | 属于独立产品或合作计划 | - | 按对应产品或合作计划单独申请，不计作当前应用已开通 | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/micro-app/goods-repo/spu-info-query) |
| 小程序接口 | 商品达人分佣配置 | 待核对官方合同 | 未写 | 属于独立产品或合作计划 | - | 按对应产品或合作计划单独申请，不计作当前应用已开通 | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/micro-app/goods-repo/take-rate) |
| 小程序接口 | 订单同步 | 待核对官方合同 | 未写 | 属于独立产品或合作计划 | - | 按对应产品或合作计划单独申请，不计作当前应用已开通 | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/micro-app/client-message-sync/order-sync) |
| 小程序接口 | 获取POI基础数据 | 待核对官方合同 | 未写 | 属于独立产品或合作计划 | - | 按对应产品或合作计划单独申请，不计作当前应用已开通 | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/micro-app/poi-data/get-poi-data) |
| 小程序接口 | POI用户数据 | 待核对官方合同 | 未写 | 属于独立产品或合作计划 | - | 按对应产品或合作计划单独申请，不计作当前应用已开通 | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/micro-app/poi-data/poi-user-data) |
| 小程序接口 | POI服务基础数据 | 待核对官方合同 | 未写 | 属于独立产品或合作计划 | - | 按对应产品或合作计划单独申请，不计作当前应用已开通 | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/micro-app/poi-data/poi-service-data) |
| 小程序接口 | POI服务成交用户数据 | 待核对官方合同 | 未写 | 属于独立产品或合作计划 | - | 按对应产品或合作计划单独申请，不计作当前应用已开通 | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/micro-app/poi-data/poi-service-user-data) |
| 小程序接口 | POI热度榜 | 待核对官方合同 | 未写 | 属于独立产品或合作计划 | - | 按对应产品或合作计划单独申请，不计作当前应用已开通 | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/micro-app/poi-data/poi-service-hot-list) |
| 小程序接口 | POI认领列表 | 待核对官方合同 | 未写 | 属于独立产品或合作计划 | - | 按对应产品或合作计划单独申请，不计作当前应用已开通 | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/micro-app/poi-data/poi-claim-list) |
| 小程序接口 | 优惠券同步 | 待核对官方合同 | 未写 | 属于独立产品或合作计划 | - | 按对应产品或合作计划单独申请，不计作当前应用已开通 | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/micro-app/coupon/coupon-sync) |
| 小程序接口 | 优惠券更新 | 待核对官方合同 | 未写 | 属于独立产品或合作计划 | - | 按对应产品或合作计划单独申请，不计作当前应用已开通 | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/micro-app/coupon/coupon-update) |
| 小程序接口 | 通用佣金计划查询带货数据 | 待核对官方合同 | 未写 | 属于独立产品或合作计划 | - | 按对应产品或合作计划单独申请，不计作当前应用已开通 | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/micro-app/cps/common-plan-detail) |
| 小程序接口 | 通用佣金计划查询达人带货数据 | 待核对官方合同 | 未写 | 属于独立产品或合作计划 | - | 按对应产品或合作计划单独申请，不计作当前应用已开通 | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/micro-app/cps/common-plan-talent-detail) |
| 小程序接口 | 通用佣金计划查询带货达人列表 | 待核对官方合同 | 未写 | 属于独立产品或合作计划 | - | 按对应产品或合作计划单独申请，不计作当前应用已开通 | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/micro-app/cps/common-plan-talent-list) |
| 小程序接口 | 通用佣金计划查询达人带货详情 | 待核对官方合同 | 未写 | 属于独立产品或合作计划 | - | 按对应产品或合作计划单独申请，不计作当前应用已开通 | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/micro-app/cps/common-plan-talent-media-list) |
| 小程序接口 | 查询通用佣金计划 | 待核对官方合同 | 未写 | 属于独立产品或合作计划 | - | 按对应产品或合作计划单独申请，不计作当前应用已开通 | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/micro-app/cps/plan-list) |
| 小程序接口 | 发布/修改通用佣金计划 | 待核对官方合同 | 未写 | 属于独立产品或合作计划 | - | 按对应产品或合作计划单独申请，不计作当前应用已开通 | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/micro-app/cps/save-common-plan) |
| 小程序接口 | 修改通用佣金计划状态 | 待核对官方合同 | 未写 | 属于独立产品或合作计划 | - | 按对应产品或合作计划单独申请，不计作当前应用已开通 | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/micro-app/cps/update-common-plan-status) |
| 工具能力 | 上传素材接口 | 待核对官方合同 | 未写 | 目录存在，当前接口合同需重查 | - | 重查当前官方页面、应用类型、Scope 和请求合同 | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/tools-ability/material-management/upload-material-interface) |
| 工具能力 | 上传临时素材接口 | Scope 类型待核对 | 未写 | 接口已定位，尚未接入 | enterprise.im | 核对 Scope 和应用资质，审计合同后增加薄适配器 | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/tools-ability/material-management/upload-temp-material-interface) |
| 工具能力 | 获取素材列表接口 | 用户授权 access_token | 未写 | 接口已定位，尚未接入 | im | 先接账号 OAuth、回调与令牌保险库，再申请并验收 Scope | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/tools-ability/material-management/material-list-interface) |
| 工具能力 | 删除素材接口 | 待核对官方合同 | 未写 | 目录存在，当前接口合同需重查 | - | 重查当前官方页面、应用类型、Scope 和请求合同 | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/tools-ability/material-management/delete-material-interface) |
| 工具能力 | 小程序接口能力 | 用户授权 access_token | 未写 | 接口已定位，尚未接入 | micapp.is_legal | 先接账号 OAuth、回调与令牌保险库，再申请并验收 Scope | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/tools-ability/mini-app-interface) |
| 工具能力 | 模拟webhook事件 | 用户授权 access_token | 未写 | 接口已定位，尚未接入 | aweme.webhook | 先接账号 OAuth、回调与令牌保险库，再申请并验收 Scope | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/tools-ability/sandbox-management/mock-webhook-event) |
| 工具能力 | 获取 jsb_ticket | Scope 类型待核对 | 未写 | 接口已定位，尚未接入 | js.ticket | 核对 Scope 和应用资质，审计合同后增加薄适配器 | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/tools-ability/jsb-management/get-jsticket) |
| 服务市场开放能力 | 查询用户的服务购买信息 | 待核对官方合同 | 未写 | 属于独立产品或合作计划 | - | 按对应产品或合作计划单独申请，不计作当前应用已开通 | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/service-market/service-relationship/GetUserServicePurchaseList) |
| 服务市场开放能力 | 扣除用户服务的剩余使用次数/条数 | 待核对官方合同 | 未写 | 属于独立产品或合作计划 | - | 按对应产品或合作计划单独申请，不计作当前应用已开通 | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/service-market/service-relationship/DecrProductUserRemainTimes) |
| 服务市场开放能力 | 导入外部订购数据 | 用户授权 access_token | 未写 | 属于独立产品或合作计划 | market.service.user | 按对应产品或合作计划单独申请，不计作当前应用已开通 | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/service-market/service-relationship/InsertPurchaseInfo) |
| 服务市场开放能力 | 删除导入的外部订购数据 | 用户授权 access_token | 未写 | 属于独立产品或合作计划 | market.service.user | 按对应产品或合作计划单独申请，不计作当前应用已开通 | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/service-market/service-relationship/DeletePurchaseInfo) |
| 小程序推广计划 | 中介查询违规达人列表 | Scope 类型待核对 | 未写 | 属于独立产品或合作计划 | taskbox.agent.admin | 按对应产品或合作计划单独申请，不计作当前应用已开通 | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/taskbox/query-violate-talent-list) |
| 小程序推广计划 | 查询推广计划视频数据下载链接 | 用户授权 access_token | 未写 | 属于独立产品或合作计划 | taskbox.agent.admin | 按对应产品或合作计划单独申请，不计作当前应用已开通 | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/taskbox/agency-query-bill-link) |
| 小程序推广计划 | 查询视频任务相关实时汇总数据 | 用户授权 access_token | 未写 | 属于独立产品或合作计划 | taskbox.agent.admin | 按对应产品或合作计划单独申请，不计作当前应用已开通 | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/taskbox/agency-query-video-sum) |
| 小程序推广计划 | 获取合作链接 | 用户授权 access_token | 未写 | 属于独立产品或合作计划 | taskbox.agent.admin | 按对应产品或合作计划单独申请，不计作当前应用已开通 | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/taskbox/gen-agent-link) |
| 小程序推广计划 | 换绑团长 | 用户授权 access_token | 未写 | 属于独立产品或合作计划 | taskbox.agent.admin | 按对应产品或合作计划单独申请，不计作当前应用已开通 | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/taskbox/change-user-bind-agent) |
| 小程序推广计划 | 查询绑定关系 | 用户授权 access_token | 未写 | 属于独立产品或合作计划 | taskbox.agent.admin | 按对应产品或合作计划单独申请，不计作当前应用已开通 | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/taskbox/get-agency-user-bind-record) |
| 小程序推广计划 | 创建团长 | 用户授权 access_token | 未写 | 属于独立产品或合作计划 | taskbox.agent.admin | 按对应产品或合作计划单独申请，不计作当前应用已开通 | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/taskbox/save-agent) |
| 小程序推广计划 | 查询任务详情 | 用户授权 access_token | 未写 | 属于独立产品或合作计划 | taskbox.agent.admin | 按对应产品或合作计划单独申请，不计作当前应用已开通 | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/taskbox/agency-query-task-info) |
| 小程序推广计划 | 查询小程序任务台任务ID | 用户授权 access_token | 未写 | 属于独立产品或合作计划 | taskbox.agent.admin | 按对应产品或合作计划单独申请，不计作当前应用已开通 | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/taskbox/agency-query-app-task) |
| 小程序推广计划 | 查询视频状态-v2 | 用户授权 access_token | 未写 | 属于独立产品或合作计划 | taskbox.agent.admin | 按对应产品或合作计划单独申请，不计作当前应用已开通 | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/taskbox/query-task-video-status-v2) |
| 分身技能数据 | 技能开发者获取分身留资数据 | Scope 类型待核对 | 未写 | 属于独立产品或合作计划 | open.skill.data.collect | 按对应产品或合作计划单独申请，不计作当前应用已开通 | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/clone-skill-data/skill-dev-avatar-data) |
| 汽水音乐 | 首页推荐 | Scope 类型待核对 | 未写 | 属于独立产品或合作计划 | luna.openapi.platform.play_core | 按对应产品或合作计划单独申请，不计作当前应用已开通 | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/qishui-music/feed-song-tab) |
| 汽水音乐 | 相关歌曲推荐 | Scope 类型待核对 | 未写 | 属于独立产品或合作计划 | luna.openapi.platform.play_core | 按对应产品或合作计划单独申请，不计作当前应用已开通 | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/qishui-music/related-media) |
