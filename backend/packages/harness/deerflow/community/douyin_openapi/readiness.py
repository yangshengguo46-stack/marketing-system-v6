from __future__ import annotations

from collections import Counter
from typing import Any

from .catalog import OfficialCatalog
from .contracts import CapabilityEntry

_RECEIPT_STATES = frozenset({"live_verified", "provider_denied", "provider_error"})
_SEPARATE_PRODUCT_SECTIONS = frozenset(
    {
        "抖音生活服务接口",
        "小程序接口",
        "小程序推广计划",
        "服务市场开放能力",
        "分身技能数据",
        "汽水音乐",
    }
)

_STATE_LABELS = {
    "adapter_ready_permission_not_declared": "适配器已写，未声明获批权限",
    "configured_unverified": "本地已配置，尚无真实成功回执",
    "contract_needs_retrace": "目录存在，当前接口合同需重查",
    "documented_not_integrated": "接口已定位，尚未接入",
    "live_verified": "真实调用已通过",
    "provider_denied": "平台拒绝权限",
    "provider_error": "平台调用失败",
    "separate_product_surface": "属于独立产品或合作计划",
}

_AUTH_LABELS = {
    "app_credentials": "应用凭据",
    "client_token": "应用级 client_token",
    "documentation_review_required": "待核对官方合同",
    "local_utility": "本地工具",
    "oauth_exchange": "OAuth 换取/刷新令牌",
    "oauth_redirect": "用户 OAuth 跳转",
    "provider_program": "平台专项合作",
    "scope_review_required": "Scope 类型待核对",
    "user_oauth": "用户授权 access_token",
    "webhook": "回调验签",
}


def _authorization_mode(entry: CapabilityEntry) -> str:
    if entry.auth_mode:
        return entry.auth_mode
    if entry.interaction_direction == "inbound_webhook":
        return "webhook"
    if entry.interaction_direction == "provider_implemented":
        return "provider_program"
    if entry.interaction_direction == "local_utility":
        return "local_utility"
    if entry.interaction_direction == "auth":
        if entry.capability_id.endswith("client.token"):
            return "app_credentials"
        if entry.capability_id.endswith("douyin.get.permission.code"):
            return "oauth_redirect"
        return "oauth_exchange"
    permission = entry.permission_requirement_zh or ""
    if "需要用户授权" in permission or entry.domain in {"identity", "audience"}:
        return "user_oauth"
    if entry.scope:
        return "scope_review_required"
    return "documentation_review_required"


def _adapter_state(
    entry: CapabilityEntry,
    receipt: dict[str, Any] | None,
) -> str:
    return "adapter_ready" if entry.is_child_contract or receipt is not None else "not_integrated"


def _base_integration_state(
    entry: CapabilityEntry,
    *,
    declared_scopes: frozenset[str],
    configured_auth_modes: frozenset[str],
) -> str:
    if entry.section in _SEPARATE_PRODUCT_SECTIONS:
        return "separate_product_surface"
    if entry.documentation_status in {"stub_or_moved", "documentation_only"}:
        return "contract_needs_retrace"
    if not entry.is_child_contract:
        return "documented_not_integrated"

    required_scopes = set(entry.required_scopes)
    accepted_scopes = set(entry.required_scope_any_of)
    if entry.scope:
        required_scopes.add(entry.scope)
    has_scope = required_scopes <= declared_scopes
    if accepted_scopes:
        has_scope = bool(accepted_scopes & declared_scopes)
    if not has_scope:
        return "adapter_ready_permission_not_declared"
    if entry.auth_mode and entry.auth_mode not in configured_auth_modes:
        return "adapter_ready_permission_not_declared"
    return "configured_unverified"


def _next_action(entry: CapabilityEntry, state: str, authorization_mode: str) -> str:
    if state == "live_verified":
        if entry.interaction_direction == "auth":
            return "保留为鉴权基础设施回执，不计作业务能力"
        return "保留回执并接入对应业务模块"
    if state == "provider_denied":
        return "在平台完成该能力审批，再运行同一只读验收"
    if state == "provider_error":
        return "按脱敏回执核对参数、额度和平台状态"
    if state == "configured_unverified":
        return "运行一次最小只读调用并保存第一方回执"
    if state == "adapter_ready_permission_not_declared":
        return "先在控制台确认 Scope 已获批，再写入本地声明并实测"
    if state == "separate_product_surface":
        return "按对应产品或合作计划单独申请，不计作当前应用已开通"
    if state == "contract_needs_retrace":
        return "重查当前官方页面、应用类型、Scope 和请求合同"
    if authorization_mode == "user_oauth":
        return "先接账号 OAuth、回调与令牌保险库，再申请并验收 Scope"
    if authorization_mode == "webhook":
        return "配置回调地址、验签、去重与重放测试"
    if authorization_mode in {"oauth_redirect", "oauth_exchange", "app_credentials"}:
        return "接入鉴权基础设施并完成令牌生命周期测试"
    if entry.scope:
        return "核对 Scope 和应用资质，审计合同后增加薄适配器"
    return "先完成接口合同和应用适用性审计"


def _normalize_observation(observation: dict[str, Any]) -> dict[str, Any]:
    if observation.get("schema_version") != 1:
        raise ValueError("Unsupported Douyin readiness observation schema")
    configured_auth_modes = frozenset(str(value) for value in observation.get("configured_auth_modes", []))
    declared_scopes = frozenset(str(value) for value in observation.get("declared_scopes", []))
    official_mcp = observation.get("official_mcp")
    if not isinstance(official_mcp, dict):
        raise ValueError("Douyin readiness observation has no official_mcp object")
    tool_names = sorted({str(value) for value in official_mcp.get("tool_names", []) if isinstance(value, str) and value})
    if len(tool_names) > 256:
        raise ValueError("Douyin readiness observation has too many MCP tools")
    tested_groups = official_mcp.get("tested_tool_group_aids", [])
    if not isinstance(tested_groups, list):
        raise ValueError("Douyin readiness MCP groups must be a list")
    receipts = observation.get("direct_receipts", [])
    if not isinstance(receipts, list):
        raise ValueError("Douyin readiness receipts must be a list")
    return {
        "observed_at": str(observation.get("observed_at", "unknown")),
        "application_type": str(observation.get("application_type", "unknown")),
        "configured_auth_modes": configured_auth_modes,
        "declared_scopes": declared_scopes,
        "mcp_initialized": official_mcp.get("initialized") is True,
        "mcp_tool_names": tool_names,
        "mcp_tested_groups": tested_groups,
        "receipts": receipts,
    }


def build_capability_readiness(
    catalog: OfficialCatalog,
    observation: dict[str, Any],
) -> dict[str, Any]:
    """Merge official inventory, local contracts and credential-safe live receipts."""

    normalized = _normalize_observation(observation)
    catalog_ids = {entry.capability_id for entry in catalog.entries}
    receipts_by_id: dict[str, dict[str, Any]] = {}
    for receipt in normalized["receipts"]:
        if not isinstance(receipt, dict):
            raise ValueError("Douyin readiness receipt must be an object")
        capability_id = str(receipt.get("capability_id", ""))
        if capability_id not in catalog_ids:
            raise ValueError(f"Douyin receipt references unknown capability: {capability_id}")
        state = str(receipt.get("state", ""))
        if state not in _RECEIPT_STATES:
            raise ValueError(f"Douyin receipt has unsupported state: {state}")
        if capability_id in receipts_by_id:
            raise ValueError(f"Douyin receipt is duplicated: {capability_id}")
        receipts_by_id[capability_id] = receipt

    capabilities: list[dict[str, Any]] = []
    for entry in catalog.entries:
        authorization_mode = _authorization_mode(entry)
        state = _base_integration_state(
            entry,
            declared_scopes=normalized["declared_scopes"],
            configured_auth_modes=normalized["configured_auth_modes"],
        )
        provider_code: int | str | None = None
        receipt = receipts_by_id.get(entry.capability_id)
        if receipt is not None:
            state = str(receipt["state"])
            provider_code = receipt.get("provider_code")
        capabilities.append(
            {
                "capability_id": entry.capability_id,
                "section": entry.section,
                "domain": entry.domain,
                "name_zh": entry.name_zh,
                "interaction_direction": entry.interaction_direction,
                "documentation_url": entry.documentation_url,
                "documentation_status": entry.documentation_status,
                "scope": entry.scope,
                "authorization_mode": authorization_mode,
                "adapter_state": _adapter_state(entry, receipt),
                "integration_state": state,
                "provider_code": provider_code,
                "next_action": _next_action(entry, state, authorization_mode),
            }
        )

    state_counts = Counter(row["integration_state"] for row in capabilities)
    mcp_tool_names = normalized["mcp_tool_names"]
    if mcp_tool_names:
        mcp_state = "tools_discovered"
    elif normalized["mcp_initialized"]:
        mcp_state = "connected_no_tools"
    else:
        mcp_state = "connection_not_verified"

    return {
        "schema_version": 1,
        "observed_at": normalized["observed_at"],
        "catalog_version": catalog.catalog_version,
        "application_type": normalized["application_type"],
        "configured_auth_modes": sorted(normalized["configured_auth_modes"]),
        "declared_scopes": sorted(normalized["declared_scopes"]),
        "official_mcp": {
            "initialized": normalized["mcp_initialized"],
            "state": mcp_state,
            "tested_tool_group_aids": normalized["mcp_tested_groups"],
            "tool_count": len(mcp_tool_names),
            "tool_names": mcp_tool_names,
        },
        "summary": {
            "catalog_capabilities": len(capabilities),
            "adapter_ready_capabilities": sum(row["adapter_state"] == "adapter_ready" for row in capabilities),
            "live_verified_capabilities": state_counts["live_verified"],
            "live_verified_business_capabilities": sum(row["integration_state"] == "live_verified" and row["interaction_direction"] == "outbound" for row in capabilities),
            "state_counts": dict(sorted(state_counts.items())),
        },
        "capabilities": capabilities,
    }


def _escape(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def render_capability_readiness_markdown(report: dict[str, Any]) -> str:
    mcp = report["official_mcp"]
    mcp_label = {
        "connected_no_tools": "连接成功但无工具",
        "tools_discovered": "已发现可用工具",
        "connection_not_verified": "连接尚未验收",
    }[mcp["state"]]
    summary = report["summary"]
    lines = [
        "# 抖音开放平台能力就绪矩阵",
        "",
        f"- 观察时间：`{report['observed_at']}`",
        f"- 官方目录：`{summary['catalog_capabilities']}` 项",
        f"- 本地薄适配器：`{summary['adapter_ready_capabilities']}` 项",
        f"- 真实调用通过：`{summary['live_verified_capabilities']}` 项（其中业务能力 `{summary['live_verified_business_capabilities']}` 项）",
        f"- 官方 MCP：{mcp_label}（`{mcp['tool_count']}` 个工具）",
        "- 边界：目录存在、本地声明 Scope、代码已有适配器，都不等于平台已经授权。",
        "",
        "## 当前状态",
        "",
        "| 状态 | 数量 |",
        "| --- | ---: |",
    ]
    lines.extend(f"| {_STATE_LABELS[state]} | {count} |" for state, count in summary["state_counts"].items())
    lines.extend(
        [
            "",
            "## 全量能力",
            "",
            "| 板块 | 能力 | 鉴权 | 适配器 | 当前状态 | Scope | 下一步 | 官方文档 |",
            "| --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for row in report["capabilities"]:
        provider_suffix = f"（{row['provider_code']}）" if row.get("provider_code") is not None else ""
        lines.append(
            "| {section} | {name} | {auth} | {adapter} | {state}{provider} | {scope} | {action} | [docs]({url}) |".format(
                section=_escape(row["section"]),
                name=_escape(row["name_zh"]),
                auth=_AUTH_LABELS[row["authorization_mode"]],
                adapter="已写" if row["adapter_state"] == "adapter_ready" else "未写",
                state=_STATE_LABELS[row["integration_state"]],
                provider=provider_suffix,
                scope=_escape(row["scope"] or "-"),
                action=_escape(row["next_action"]),
                url=row["documentation_url"],
            )
        )
    lines.append("")
    return "\n".join(lines)
