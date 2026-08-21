from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from deerflow.incubation.account_audience import MarketingSubjectSnapshot
from deerflow.incubation.contracts import (
    ArtifactEnvelope,
    IncubationContract,
    LogicalAccountRef,
    NonEmptyStr,
    ProjectRef,
)


class HostProductProfile(IncubationContract):
    """Bounded product truth used only when the user refers to the Agent itself."""

    schema_version: Literal["v6-host-product-profile-v1"] = "v6-host-product-profile-v1"
    profile_version: int = Field(ge=1)
    product_name: NonEmptyStr = Field(max_length=120)
    subject_expression: NonEmptyStr = Field(max_length=500)
    category: NonEmptyStr = Field(max_length=500)
    target_segments: tuple[NonEmptyStr, ...] = Field(min_length=1, max_length=8)
    business_facts: tuple[NonEmptyStr, ...] = Field(min_length=1, max_length=12)
    capabilities: tuple[NonEmptyStr, ...] = Field(min_length=1, max_length=16)
    accepted_evidence: tuple[NonEmptyStr, ...] = Field(default=(), max_length=12)
    constraints: tuple[NonEmptyStr, ...] = Field(min_length=1, max_length=16)


def current_host_product_profile() -> HostProductProfile:
    """Return the reviewed facts for the current customized DeerFlow product."""

    return HostProductProfile(
        profile_version=1,
        product_name="DeerFlow",
        subject_expression="DeerFlow 内容孵化与新媒体运营 Agent",
        category="以账号孵化为核心、连接研究证据与内容执行的新媒体运营 Agent 系统",
        target_segments=(
            "知道自己做什么，但不知道账号应该影响谁、长期讲什么和第一条拍什么的经营者",
            "需要把个人专业、品牌或产品转成可持续内容账号的个人与团队",
        ),
        business_facts=(
            "这是一个以账号孵化为核心的内容孵化与新媒体运营 Agent 产品。",
            "产品承接的是从业务理解、目标人群、账号策略到具体内容交付的判断工作。",
        ),
        capabilities=(
            "能把用户的业务表达解析为可检查的商业主体、候选内容世界和内容地图。",
            "能生成并版本化账号策略路线，覆盖业务目标、受众、人设、账号级表现形式和变现假设。",
            "能沿已确认的账号方向研究证据并产出具体可拍选题、信息计划和基础草稿。",
            "能在已验收连接器和权限范围内读取有界公开证据、对标观察与项目事实。",
        ),
        accepted_evidence=(
            "账号策略提案、用户确认、逻辑账号隔离和版本化台账已有自动化回归。",
            "语义理解、内容根、内容地图、具体选题与草稿之间已有内容寻址工件。",
            "平台证据、对标证据和用户事实在合同中保持不同来源角色。",
        ),
        constraints=(
            "不能保证涨粉、播放、线索或成交结果。",
            "不能把未验收的平台、媒体或发布能力宣传为已经可用。",
            "不能编造用户能力、客户案例、素材、供应链、历史成绩或对标结论。",
            "平台登录、数据、制作和发布能力取决于实际连接器、账号权限及对应验收状态。",
        ),
    )


def seal_host_product_profile(
    *,
    project: ProjectRef,
    logical_account: LogicalAccountRef,
    profile: HostProductProfile,
    created_at: datetime,
    source_thread_id: str,
    source_run_id: str,
) -> ArtifactEnvelope:
    profile = HostProductProfile.model_validate(profile.model_dump(mode="python"))
    return ArtifactEnvelope.seal(
        project=project,
        artifact_type="host_product_profile",
        version=profile.profile_version,
        payload=profile.model_dump(mode="json"),
        logical_account=logical_account,
        created_at=created_at,
        source_thread_id=source_thread_id,
        source_run_id=source_run_id,
    )


def build_agent_self_subject(
    *,
    user_request: str,
    profile_artifact: ArtifactEnvelope,
) -> MarketingSubjectSnapshot:
    if profile_artifact.artifact_type != "host_product_profile":
        raise ValueError("agent self subject requires a host product profile")
    profile = HostProductProfile.model_validate(profile_artifact.payload)
    return MarketingSubjectSnapshot(
        subject_kind="agent_self",
        subject_expression=profile.subject_expression,
        source_user_request=user_request,
        business_facts=profile.business_facts,
        capabilities=profile.capabilities,
        resources=profile.accepted_evidence,
        constraints=profile.constraints,
        goals=("让目标用户通过公开可检查的真实操盘过程理解产品能解决什么问题。",),
        basis_artifact_ids=(profile_artifact.artifact_id,),
    )


__all__ = [
    "HostProductProfile",
    "build_agent_self_subject",
    "current_host_product_profile",
    "seal_host_product_profile",
]
