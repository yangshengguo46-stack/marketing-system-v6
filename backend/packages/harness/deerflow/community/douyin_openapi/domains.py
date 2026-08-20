from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DomainDefinition:
    domain_id: str
    tool_name: str
    description: str
    includes: str
    excludes: str


_DEFINITIONS = (
    DomainDefinition(
        "identity",
        "douyin_identity",
        "Authorized Douyin account identity and public profile operations. Excludes audience lists, content, search, and OAuth credential exchange.",
        "authorized account profile and identity",
        "audience, content, search, OAuth secrets",
    ),
    DomainDefinition(
        "audience",
        "douyin_audience",
        "Authorized-account followers, follows, mutual follows, and first-party fan portrait data. Excludes competitor audience claims and content search.",
        "own or client-authorized relationship and fan data",
        "competitor inference, public search, post analytics",
    ),
    DomainDefinition(
        "content",
        "douyin_content",
        "Douyin video metadata, sharing results, iframe lookup, and posting-task operations. Excludes public discovery, asset storage, and publishing approval policy.",
        "video metadata, embeds, posting tasks",
        "public search, material repository, approval decisions",
    ),
    DomainDefinition(
        "search",
        "douyin_search",
        "Public Douyin video and image-text discovery for topic evidence. Excludes account authorization, competitor-account analysis, and audience portraits.",
        "public video and image-text search",
        "account analysis, fan portraits, publishing",
    ),
    DomainDefinition(
        "public_evidence",
        "douyin_public_evidence",
        "Authenticated public-page evidence for Douyin videos, creators, posts, visible comments, and share links. Excludes own-account analytics, raw credentials, and marketing judgment.",
        "bounded public video, creator, post, and visible-audience observations",
        "own-account analytics, credentials, raw pages, positioning decisions",
    ),
    DomainDefinition(
        "messaging",
        "douyin_messaging",
        "Private-message business cards, mini-app guide-card templates, and message image upload. Excludes ordinary content publishing and CRM decisions.",
        "message cards, templates, message images",
        "feed publishing, audience inference, CRM judgment",
    ),
    DomainDefinition(
        "interest_events",
        "douyin_interest_events",
        "Third-party activity synchronization for Douyin Interest plus its callback and encryption contracts. Excludes local-life orders and content events.",
        "activity, signup, status, callback, encryption contracts",
        "local-life fulfilment, content analytics",
    ),
    DomainDefinition(
        "local_shops",
        "douyin_local_shops",
        "Local-life shop, store, and POI matching operations. Excludes goods, vouchers, orders, member analytics, and affiliate plans.",
        "shops, stores, POI matching",
        "goods, fulfilment, audience data, affiliate plans",
    ),
    DomainDefinition(
        "local_fulfilment",
        "douyin_local_fulfilment",
        "Local-life vouchers, verification, orders, refunds, settlement, coupon synchronization, and fulfilment callbacks. Excludes goods authoring and shop matching.",
        "vouchers, orders, refunds, settlement, coupons",
        "goods authoring, store matching, audience analytics",
    ),
    DomainDefinition(
        "local_goods",
        "douyin_local_goods",
        "Local-life group-buy and mini-app goods, SKU, SPU, inventory, and commission configuration. Excludes order fulfilment and affiliate reporting.",
        "goods, SKU, SPU, inventory",
        "orders, vouchers, affiliate reports",
    ),
    DomainDefinition(
        "local_audience",
        "douyin_local_audience",
        "Local-life membership and POI audience or service-performance datasets. Excludes general fan portraits, shop matching, and transaction execution.",
        "membership and POI audience datasets",
        "general fans, shop matching, transaction writes",
    ),
    DomainDefinition(
        "local_affiliate",
        "douyin_local_affiliate",
        "Mini-app general commission plans and creator commerce reporting. Excludes promotion-plan agency management and ordinary goods inventory.",
        "commission plans and creator commerce data",
        "agency taskbox, goods inventory, order fulfilment",
    ),
    DomainDefinition(
        "assets",
        "douyin_assets",
        "Douyin material repository, temporary assets, mini-app capability checks, webhook simulation, and JSB tickets. Excludes MediaKit local media processing.",
        "platform materials and developer utilities",
        "local editing, MediaKit, content strategy",
    ),
    DomainDefinition(
        "service_market",
        "douyin_service_market",
        "Douyin service-market purchase verification, usage deduction, and external subscription synchronization. Excludes local-life orders and product sales.",
        "service purchases and usage entitlements",
        "local-life orders, ordinary commerce",
    ),
    DomainDefinition(
        "creator_partnerships",
        "douyin_creator_partnerships",
        "Douyin mini-app promotion-plan agencies, creators, leaders, tasks, billing links, and video status. Excludes TikTok talent contracting and fan portraits.",
        "Douyin promotion-plan partnerships and taskbox",
        "TikTok contracting, fan portraits, feed publishing",
    ),
    DomainDefinition(
        "clone_leads",
        "douyin_clone_leads",
        "Lead data explicitly collected through an authorized Douyin AI-clone skill. Excludes ordinary private messages and inferred audience data.",
        "authorized AI-clone skill lead receipts",
        "private messages, inferred identities, fan portraits",
    ),
    DomainDefinition(
        "music",
        "douyin_music",
        "Qishui Music home-feed and related-song recommendations. Excludes Douyin video search, music licensing judgment, and audio production.",
        "Qishui Music recommendations",
        "video search, licensing decisions, audio editing",
    ),
)

DOMAIN_DEFINITIONS = {definition.domain_id: definition for definition in _DEFINITIONS}
