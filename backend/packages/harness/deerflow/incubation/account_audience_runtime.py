from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from pydantic import ValidationError

from deerflow.incubation.account_audience import (
    AccountAudienceDecision,
    AccountAudienceProposalDraft,
    MarketingSubjectSnapshot,
    compile_account_audience_decision,
)

StructuredAudienceModel = Callable[
    [type[AccountAudienceProposalDraft], tuple[BaseMessage, ...]],
    Awaitable[Any],
]

MAX_ACCOUNT_AUDIENCE_INPUT_BYTES = 12_000


class AccountAudienceModelError(RuntimeError):
    pass


ACCOUNT_AUDIENCE_SYSTEM_PROMPT = """<account_audience>
你只负责在账号定位之前，判断这项业务首先需要影响哪些人。这个判断先于内容根、内容地图、账号人设、表现形式、选题和脚本。

先读清营销主体和交易或服务关系，再分别回答：
- 用户在业务中扮演什么角色；
- 账号在曝光之后要改变谁的什么行为，为这项业务完成什么结果；
- 谁付钱、签约或提供关键资源；
- 谁实际做决定；
- 谁使用产品、接受服务或最终受益；
- 账号为了业务结果真正需要影响谁、对方要完成什么任务或解决什么问题、希望其采取什么行动；
- 哪些人会愿意长期观看内容，他们持续关心的事情是什么；
- 用户明示的地区、语言、渠道或市场边界。

这里的“用户画像”是可修正的业务与内容受众假设，不是凭空编写年龄、性别、收入、性格或生活方式。没有用户事实或正式证据，不得添加人口统计特征。

路线规则：
- 如果用户原话或可信产品事实已经明确一条交易关系，只输出一条路线，material_choice_required=false。不要为了显得完整增加备选。
- 如果批发/零售、B 端/C 端、付款者/使用者、渠道客户/终端客户等差异会实质改变账号服务谁、讲什么和如何成交，输出两到三条真正不同的路线，material_choice_required=true，让用户先选。
- 不得用“所有人”“大众”“所有感兴趣的人”掩盖尚未解决的实质分歧。
- content_audience 可以比业务目标人群更宽，但必须说明他们为什么会持续关注；两者不能合并成一个模糊画像。
- agent_self 表示营销主体就是当前 Agent 产品。只能使用输入中的产品事实、能力、证据和边界，不得把它改写成一个身份未知的普通创业者。

边界：
- 不生成内容根、内容地图、定位、人设、表现形式、栏目、选题、脚本、发布计划或变现新业务。
- 不把业务身份自动当成能力、案例、资源或成绩。
- 不保证增长或成交，不用刻板印象替代未知。
- 信息不足时保留 unknowns；只有实质路线分歧才要求用户选择。

只返回符合 AccountAudienceProposalDraft 的结构化数据。
</account_audience>"""


def _render_account_audience_input(subject: MarketingSubjectSnapshot) -> str:
    payload = {
        "marketing_subject": subject.model_dump(mode="json"),
    }
    rendered = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    if len(rendered.encode("utf-8")) > MAX_ACCOUNT_AUDIENCE_INPUT_BYTES:
        raise ValueError("account audience input exceeds its byte budget")
    return "--- BEGIN ACCOUNT AUDIENCE INPUT ---\n" + rendered + "\n--- END ACCOUNT AUDIENCE INPUT ---"


async def generate_account_audience_decision(
    *,
    subject: MarketingSubjectSnapshot,
    structured_model: StructuredAudienceModel,
) -> AccountAudienceDecision:
    subject = MarketingSubjectSnapshot.model_validate(subject.model_dump(mode="python"))
    messages: tuple[BaseMessage, ...] = (
        SystemMessage(content=ACCOUNT_AUDIENCE_SYSTEM_PROMPT),
        HumanMessage(content=_render_account_audience_input(subject)),
    )
    try:
        model_result = await structured_model(AccountAudienceProposalDraft, messages)
        draft = AccountAudienceProposalDraft.model_validate(model_result)
        return compile_account_audience_decision(subject=subject, draft=draft)
    except (ValidationError, TypeError, ValueError) as error:
        raise AccountAudienceModelError("account audience model returned an invalid decision") from error
    except Exception as error:
        raise AccountAudienceModelError("account audience model call failed") from error


__all__ = [
    "ACCOUNT_AUDIENCE_SYSTEM_PROMPT",
    "AccountAudienceModelError",
    "MAX_ACCOUNT_AUDIENCE_INPUT_BYTES",
    "StructuredAudienceModel",
    "generate_account_audience_decision",
]
