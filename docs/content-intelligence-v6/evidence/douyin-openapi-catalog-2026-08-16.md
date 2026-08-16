# Douyin OpenAPI Catalog Evidence

- Captured: `2026-08-16`
- Official index: https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/list
- Catalog rows: `119`
- Source SHA-256: `d5fe5ea32b1ef7c425cc4a4bbc12e9679074cd082655f20145aaa0522924632b`
- Entries SHA-256: `db15faab677f3ec3e374d5f4e5fe7be3cdbd937679db54e54516f4e986f5a8d9`
- Boundary: a catalog row is not a claim that the current app can call it.

## Official Sections

| Value | Count |
| --- | ---: |
| 个人资料 | 6 |
| 关系能力 | 7 |
| 内容能力 | 8 |
| 分身技能数据 | 1 |
| 小程序接口 | 31 |
| 小程序推广计划 | 10 |
| 工具能力 | 7 |
| 抖音生活服务接口 | 27 |
| 搜索能力 | 2 |
| 数据开放服务 | 7 |
| 服务市场开放能力 | 4 |
| 汽水音乐 | 2 |
| 私信群聊 | 7 |

## Gateway Domains

| Value | Count |
| --- | ---: |
| assets | 7 |
| audience | 7 |
| clone_leads | 1 |
| content | 8 |
| creator_partnerships | 10 |
| identity | 6 |
| interest_events | 7 |
| local_affiliate | 7 |
| local_audience | 8 |
| local_fulfilment | 18 |
| local_goods | 17 |
| local_shops | 8 |
| messaging | 7 |
| music | 2 |
| search | 2 |
| service_market | 4 |

## Interaction Directions

| Value | Count |
| --- | ---: |
| auth | 5 |
| inbound_webhook | 1 |
| local_utility | 1 |
| outbound | 106 |
| provider_implemented | 6 |

## Documentation Status

| Value | Count |
| --- | ---: |
| documentation_only | 4 |
| endpoint_documented | 45 |
| local_utility_documented | 1 |
| stub_or_moved | 68 |
| webhook_documented | 1 |

## Review Status

| Value | Count |
| --- | ---: |
| adopted | 2 |
| discovered | 74 |
| reviewed | 1 |
| traced | 42 |

## Full Inventory

| Domain | Capability | Direction | Review | Docs | Method | Scope | Official page |
| --- | --- | --- | --- | --- | --- | --- | --- |
| identity | 抖音获取授权码 | auth | traced | endpoint_documented | GET | - | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/account-permission/douyin-get-permission-code) |
| identity | 获取 access_token | auth | traced | endpoint_documented | POST | - | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/account-permission/get-access-token) |
| identity | 刷新 refresh_token | auth | traced | endpoint_documented | POST | - | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/account-permission/refresh-token) |
| identity | 生成 client_token | auth | traced | endpoint_documented | POST | - | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/account-permission/client-token) |
| identity | 刷新 access_token | auth | traced | endpoint_documented | POST | - | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/account-permission/refresh-access-token) |
| identity | 获取用户公开信息 | outbound | discovered | stub_or_moved | - | - | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/account-management/get-account-open-info) |
| audience | 获取粉丝列表 | outbound | traced | endpoint_documented | GET | - | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/account-management/user-data/get-fans-list) |
| audience | 获取用户的关注列表 | outbound | traced | endpoint_documented | GET | following.list | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/account-management/user-data/get-user-follow-list) |
| audience | 获取用户的双向关注列表数据 | outbound | traced | endpoint_documented | GET | friend.list | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/account-management/user-data/get-friend-list) |
| audience | 获取用户粉丝数据 | outbound | traced | endpoint_documented | GET | fans.data.bind | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/account-management/fans-portrait-data/get-user-fans-data) |
| audience | 获取用户粉丝来源 | outbound | traced | endpoint_documented | GET | data.external.fans_source | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/account-management/fans-portrait-data/get-user-fans-origin) |
| audience | 获取用户粉丝喜好数据 | outbound | traced | endpoint_documented | GET | data.external.fans_favourite | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/account-management/fans-portrait-data/get-user-fans-like) |
| audience | 获取用户粉丝热评 | outbound | traced | endpoint_documented | GET | data.external.fans_favourite | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/account-management/fans-portrait-data/get-user-fans-hot-comment) |
| content | 查询视频分享结果及数据 | outbound | traced | endpoint_documented | POST | aweme.forward | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/video-management/douyin/search-video/video-share-result) |
| content | 查询视频携带的地点信息 | outbound | traced | endpoint_documented | POST | poi.search | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/video-management/douyin/search-video/video-poi) |
| content | 通过videoid获取IFrame代码 | outbound | discovered | documentation_only | - | - | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/video-management/douyin/iframe-player/get-iframe-by-video) |
| content | 通过 ItemID 获取 iFrame 代码 | outbound | discovered | documentation_only | - | - | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/video-management/douyin/iframe-player/get-iframe-by-item) |
| content | 创建投稿任务 | outbound | traced | endpoint_documented | POST | task.posting.create | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/video-management/posting-task/create-posting-task) |
| content | 绑定视频 | outbound | traced | endpoint_documented | POST | posting.behavior | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/video-management/posting-task/bind-video) |
| content | 核销投稿任务 | outbound | traced | endpoint_documented | POST | task.posting.user_verification | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/video-management/posting-task/verify-posting-task) |
| content | 查询视频基础信息 | outbound | traced | endpoint_documented | POST | posting.behavior | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/video-management/posting-task/video-basic-info) |
| search | 抖音视频搜索 | outbound | adopted | endpoint_documented | GET | aweme.dy.video_search | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/douyin-search-capability/aweme-dy-video-search) |
| search | 抖音图文搜索 | outbound | adopted | endpoint_documented | GET | aweme.experience.search | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/douyin-search-capability/aweme-experience-search) |
| messaging | 创建/更新留资卡片 | outbound | discovered | stub_or_moved | - | - | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/interaction-management/business-tool/retain-consult-card/create-retain-consult-card) |
| messaging | 查询留资卡片 | outbound | discovered | stub_or_moved | - | - | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/interaction-management/business-tool/retain-consult-card/query-retain-consult-card) |
| messaging | 删除留资卡片 | outbound | discovered | stub_or_moved | - | - | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/interaction-management/business-tool/retain-consult-card/delete-retain-consult-card) |
| messaging | 创建/更新小程序引导卡片模板 | outbound | discovered | stub_or_moved | - | - | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/interaction-management/business-tool/micro-app-card/create-template) |
| messaging | 查询小程序引导卡片模板 | outbound | discovered | stub_or_moved | - | - | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/interaction-management/business-tool/micro-app-card/query-template) |
| messaging | 删除小程序引导卡片模板 | outbound | discovered | stub_or_moved | - | - | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/interaction-management/business-tool/micro-app-card/delete-template) |
| messaging | 图片上传 | outbound | discovered | stub_or_moved | - | - | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/interaction-management/business-tool/image-upload) |
| interest_events | 三方活动数据同步 | outbound | traced | endpoint_documented | POST | interest.activity.sync | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/data-open-service/douyin-interest/third-party-data-sync) |
| interest_events | 三方活动状态同步 | outbound | traced | endpoint_documented | POST | interest.activity.sync | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/data-open-service/douyin-interest/tp-activity-status-sync) |
| interest_events | 三方活动报名数据同步 | outbound | traced | endpoint_documented | POST | interest.activity.sync | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/data-open-service/douyin-interest/tp-activity-signup-sync) |
| interest_events | 三方活动报名状态同步 | outbound | traced | endpoint_documented | POST | interest.activity.sync | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/data-open-service/douyin-interest/tp-signup-status-sync) |
| interest_events | 三方活动图片上传 | outbound | traced | endpoint_documented | POST | interest.activity.sync | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/data-open-service/douyin-interest/third-party-image-upload) |
| interest_events | 三方活动审核结果回调Webhook | inbound_webhook | discovered | webhook_documented | - | - | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/data-open-service/douyin-interest/tp-activity-review-callback) |
| interest_events | 三方敏感信息加密 | local_utility | discovered | local_utility_documented | - | - | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/data-open-service/douyin-interest/third-party-encryption) |
| local_fulfilment | 门店信息查询 | outbound | discovered | stub_or_moved | - | - | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/life.capacity/life.capacity.shop/shop.query) |
| local_fulfilment | 验券准备 | outbound | discovered | stub_or_moved | - | - | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/life.capacity/life.capacity.fulfilment/certificate.prepare) |
| local_fulfilment | 验券 | outbound | discovered | stub_or_moved | - | - | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/life.capacity/life.capacity.fulfilment/certificate.verify) |
| local_fulfilment | 撤销核销 | outbound | discovered | stub_or_moved | - | - | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/life.capacity/life.capacity.fulfilment/certificate.cancel) |
| local_fulfilment | 券状态查询 | outbound | discovered | stub_or_moved | - | - | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/life.capacity/life.capacity.fulfilment/certificate.get) |
| local_fulfilment | 券状态批量查询 | outbound | discovered | stub_or_moved | - | - | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/life.capacity/life.capacity.fulfilment/certificate.query) |
| local_fulfilment | 验券历史查询 | outbound | discovered | stub_or_moved | - | - | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/life.capacity/life.capacity.billing/certificate.verifyrecord.query) |
| local_fulfilment | 分账明细查询 | outbound | discovered | stub_or_moved | - | - | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/life.capacity/life.capacity.billing/ledger.query-record-by-cert) |
| local_audience | 会员数据更新 | outbound | discovered | stub_or_moved | - | - | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/life.capacity/member/update.info) |
| local_audience | 会员入会&退会 | provider_implemented | discovered | stub_or_moved | - | - | [docs](https://partner.open-douyin.com/docs/resource/zh-CN/local-life/develop/OpenAPI/member/member.join.new) |
| local_fulfilment | 订单查询 | outbound | discovered | stub_or_moved | - | - | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/life.capacity/order.query/query) |
| local_fulfilment | 下单确认 | provider_implemented | discovered | stub_or_moved | - | - | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/life.capacity/tripartite.code/can) |
| local_fulfilment | 发券 | provider_implemented | discovered | stub_or_moved | - | - | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/life.capacity/tripartite.code/create) |
| local_fulfilment | 发券回调 | outbound | discovered | stub_or_moved | - | - | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/life.capacity/tripartite.code/callback) |
| local_fulfilment | 退款 | provider_implemented | discovered | stub_or_moved | - | - | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/life.capacity/tripartite.code/refund.apply) |
| local_fulfilment | 审核回调 | outbound | discovered | stub_or_moved | - | - | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/life.capacity/tripartite.code/refund.audit) |
| local_fulfilment | 信息同步 | provider_implemented | discovered | stub_or_moved | - | - | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/life.capacity/tripartite.code/refund.notice) |
| local_goods | 创建/修改团购活动 | outbound | discovered | stub_or_moved | - | - | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/life.capacity/goods/save) |
| local_goods | 免审修改商品 | outbound | discovered | stub_or_moved | - | - | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/life.capacity/goods/free.audit) |
| local_goods | 上下架商品 | outbound | discovered | stub_or_moved | - | - | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/life.capacity/goods/operate) |
| local_goods | 同步库存 | outbound | discovered | stub_or_moved | - | - | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/life.capacity/goods/batch.save) |
| local_goods | 查询商品模板 | outbound | discovered | stub_or_moved | - | - | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/life.capacity/goods/template.get) |
| local_goods | 查询商品草稿数据 | outbound | discovered | stub_or_moved | - | - | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/life.capacity/goods/draft.get) |
| local_goods | 查询商品草稿数据列表 | outbound | discovered | stub_or_moved | - | - | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/life.capacity/goods/query) |
| local_goods | 查询商品线上数据 | outbound | discovered | stub_or_moved | - | - | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/life.capacity/goods/online.get) |
| local_goods | 查询商品线上数据列表 | outbound | discovered | stub_or_moved | - | - | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/life.capacity/goods/online.query) |
| local_goods | 创建/更新多SKU商品的SKU列表 | outbound | discovered | stub_or_moved | - | - | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/life.capacity/goods/goods.batch.save) |
| local_shops | 商铺同步 | outbound | discovered | stub_or_moved | - | - | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/micro-app/shop/synchronism) |
| local_shops | 查询店铺 | outbound | discovered | stub_or_moved | - | - | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/micro-app/shop/search) |
| local_shops | 获取抖音POI ID | outbound | discovered | stub_or_moved | - | - | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/micro-app/shop/get-douyin-poi-id) |
| local_shops | 店铺匹配任务结果查询 | outbound | discovered | stub_or_moved | - | - | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/micro-app/shop/task-query) |
| local_shops | 店铺匹配状态查询 | outbound | discovered | stub_or_moved | - | - | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/micro-app/shop/status-query) |
| local_shops | 发起店铺匹配POI同步任务 | outbound | discovered | stub_or_moved | - | - | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/micro-app/shop/poi-sync-task) |
| local_shops | 查询全部店铺信息接口(天级别请求5次) | outbound | discovered | stub_or_moved | - | - | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/micro-app/shop/query-all-shop-info) |
| local_shops | 查询店铺全部信息任务返回内容 | outbound | discovered | stub_or_moved | - | - | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/micro-app/shop/query-shop-all-tasks) |
| local_goods | SKU同步 | outbound | discovered | stub_or_moved | - | - | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/micro-app/goods-repo/sku-sync) |
| local_goods | sku拉取(该接口由接入方实现) | provider_implemented | discovered | stub_or_moved | - | - | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/micro-app/goods-repo/sku-pull) |
| local_goods | 多门店SPU同步 | outbound | discovered | stub_or_moved | - | - | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/micro-app/goods-repo/spu-sync) |
| local_goods | 多门店SPU状态同步 | outbound | discovered | stub_or_moved | - | - | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/micro-app/goods-repo/spu-status-sync) |
| local_goods | 多门店SPU库存同步 | outbound | discovered | stub_or_moved | - | - | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/micro-app/goods-repo/spu-repo-sync) |
| local_goods | 多门店SPU信息查询 | outbound | discovered | stub_or_moved | - | - | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/micro-app/goods-repo/spu-info-query) |
| local_goods | 商品达人分佣配置 | outbound | discovered | stub_or_moved | - | - | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/micro-app/goods-repo/take-rate) |
| local_fulfilment | 订单同步 | outbound | discovered | stub_or_moved | - | - | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/micro-app/client-message-sync/order-sync) |
| local_audience | 获取POI基础数据 | outbound | discovered | stub_or_moved | - | - | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/micro-app/poi-data/get-poi-data) |
| local_audience | POI用户数据 | outbound | discovered | stub_or_moved | - | - | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/micro-app/poi-data/poi-user-data) |
| local_audience | POI服务基础数据 | outbound | discovered | stub_or_moved | - | - | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/micro-app/poi-data/poi-service-data) |
| local_audience | POI服务成交用户数据 | outbound | discovered | stub_or_moved | - | - | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/micro-app/poi-data/poi-service-user-data) |
| local_audience | POI热度榜 | outbound | discovered | stub_or_moved | - | - | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/micro-app/poi-data/poi-service-hot-list) |
| local_audience | POI认领列表 | outbound | discovered | stub_or_moved | - | - | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/micro-app/poi-data/poi-claim-list) |
| local_fulfilment | 优惠券同步 | outbound | discovered | stub_or_moved | - | - | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/micro-app/coupon/coupon-sync) |
| local_fulfilment | 优惠券更新 | outbound | discovered | stub_or_moved | - | - | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/micro-app/coupon/coupon-update) |
| local_affiliate | 通用佣金计划查询带货数据 | outbound | discovered | stub_or_moved | - | - | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/micro-app/cps/common-plan-detail) |
| local_affiliate | 通用佣金计划查询达人带货数据 | outbound | discovered | stub_or_moved | - | - | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/micro-app/cps/common-plan-talent-detail) |
| local_affiliate | 通用佣金计划查询带货达人列表 | outbound | discovered | stub_or_moved | - | - | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/micro-app/cps/common-plan-talent-list) |
| local_affiliate | 通用佣金计划查询达人带货详情 | outbound | discovered | stub_or_moved | - | - | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/micro-app/cps/common-plan-talent-media-list) |
| local_affiliate | 查询通用佣金计划 | outbound | discovered | stub_or_moved | - | - | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/micro-app/cps/plan-list) |
| local_affiliate | 发布/修改通用佣金计划 | outbound | discovered | stub_or_moved | - | - | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/micro-app/cps/save-common-plan) |
| local_affiliate | 修改通用佣金计划状态 | outbound | discovered | stub_or_moved | - | - | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/life-service-open-ability/micro-app/cps/update-common-plan-status) |
| assets | 上传素材接口 | outbound | discovered | documentation_only | - | - | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/tools-ability/material-management/upload-material-interface) |
| assets | 上传临时素材接口 | outbound | traced | endpoint_documented | POST | enterprise.im | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/tools-ability/material-management/upload-temp-material-interface) |
| assets | 获取素材列表接口 | outbound | reviewed | endpoint_documented | GET | im | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/tools-ability/material-management/material-list-interface) |
| assets | 删除素材接口 | outbound | discovered | documentation_only | - | - | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/tools-ability/material-management/delete-material-interface) |
| assets | 小程序接口能力 | outbound | traced | endpoint_documented | GET | micapp.is_legal | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/tools-ability/mini-app-interface) |
| assets | 模拟webhook事件 | outbound | traced | endpoint_documented | POST | aweme.webhook | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/tools-ability/sandbox-management/mock-webhook-event) |
| assets | 获取 jsb_ticket | outbound | traced | endpoint_documented | GET | js.ticket | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/tools-ability/jsb-management/get-jsticket) |
| service_market | 查询用户的服务购买信息 | outbound | discovered | stub_or_moved | - | - | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/service-market/service-relationship/GetUserServicePurchaseList) |
| service_market | 扣除用户服务的剩余使用次数/条数 | outbound | discovered | stub_or_moved | - | - | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/service-market/service-relationship/DecrProductUserRemainTimes) |
| service_market | 导入外部订购数据 | outbound | traced | endpoint_documented | POST | market.service.user | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/service-market/service-relationship/InsertPurchaseInfo) |
| service_market | 删除导入的外部订购数据 | outbound | traced | endpoint_documented | POST | market.service.user | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/service-market/service-relationship/DeletePurchaseInfo) |
| creator_partnerships | 中介查询违规达人列表 | outbound | traced | endpoint_documented | POST | taskbox.agent.admin | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/taskbox/query-violate-talent-list) |
| creator_partnerships | 查询推广计划视频数据下载链接 | outbound | traced | endpoint_documented | POST | taskbox.agent.admin | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/taskbox/agency-query-bill-link) |
| creator_partnerships | 查询视频任务相关实时汇总数据 | outbound | traced | endpoint_documented | POST | taskbox.agent.admin | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/taskbox/agency-query-video-sum) |
| creator_partnerships | 获取合作链接 | outbound | traced | endpoint_documented | POST | taskbox.agent.admin | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/taskbox/gen-agent-link) |
| creator_partnerships | 换绑团长 | outbound | traced | endpoint_documented | POST | taskbox.agent.admin | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/taskbox/change-user-bind-agent) |
| creator_partnerships | 查询绑定关系 | outbound | traced | endpoint_documented | POST | taskbox.agent.admin | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/taskbox/get-agency-user-bind-record) |
| creator_partnerships | 创建团长 | outbound | traced | endpoint_documented | POST | taskbox.agent.admin | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/taskbox/save-agent) |
| creator_partnerships | 查询任务详情 | outbound | traced | endpoint_documented | POST | taskbox.agent.admin | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/taskbox/agency-query-task-info) |
| creator_partnerships | 查询小程序任务台任务ID | outbound | traced | endpoint_documented | POST | taskbox.agent.admin | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/taskbox/agency-query-app-task) |
| creator_partnerships | 查询视频状态-v2 | outbound | traced | endpoint_documented | POST | taskbox.agent.admin | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/taskbox/query-task-video-status-v2) |
| clone_leads | 技能开发者获取分身留资数据 | outbound | traced | endpoint_documented | POST | open.skill.data.collect | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/clone-skill-data/skill-dev-avatar-data) |
| music | 首页推荐 | outbound | traced | endpoint_documented | POST | luna.openapi.platform.play_core | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/qishui-music/feed-song-tab) |
| music | 相关歌曲推荐 | outbound | traced | endpoint_documented | POST | luna.openapi.platform.play_core | [docs](https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/openapi/qishui-music/related-media) |
