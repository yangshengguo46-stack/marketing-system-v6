from __future__ import annotations

import hashlib
import json
from typing import Annotated, Any

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import Field, model_validator

from deerflow.content_intelligence.analyzer import _invoke_structured
from deerflow.content_intelligence.contracts import (
    BasisRef,
    ContentIntelligenceBundle,
    ContractModel,
    NonEmptyStr,
)

MessageBeats = Annotated[tuple[NonEmptyStr, ...], Field(min_length=1)]


class MessagePlanDraft(ContractModel):
    topic_title: NonEmptyStr
    focal_subject: NonEmptyStr
    context: NonEmptyStr | None = None
    concrete_event_or_question: NonEmptyStr
    account_position: NonEmptyStr
    point_of_view: NonEmptyStr
    entry_point: NonEmptyStr
    telling_lens: NonEmptyStr
    audience_question: NonEmptyStr
    information_order: NonEmptyStr
    payoff: NonEmptyStr
    opening: NonEmptyStr
    message_beats: MessageBeats
    closing: NonEmptyStr
    limitations: tuple[NonEmptyStr, ...] = ()
    unknowns: tuple[NonEmptyStr, ...] = ()

    def bind(
        self,
        *,
        bundle: ContentIntelligenceBundle,
        account_position_basis: str,
    ) -> ShootingDelivery:
        return _bind_message_plan_draft(
            self,
            bundle=bundle,
            account_position_basis=account_position_basis,
        )


class MessagePlan(ContractModel):
    message_plan_id: NonEmptyStr
    record_id: NonEmptyStr
    topic_title: NonEmptyStr
    focal_subject: NonEmptyStr
    context: NonEmptyStr | None = None
    concrete_event_or_question: NonEmptyStr
    account_position: NonEmptyStr
    account_position_basis: NonEmptyStr
    point_of_view: NonEmptyStr
    entry_point: NonEmptyStr
    telling_lens: NonEmptyStr
    audience_question: NonEmptyStr
    information_order: NonEmptyStr
    payoff: NonEmptyStr
    opening: NonEmptyStr
    message_beats: MessageBeats
    closing: NonEmptyStr
    evidence_refs: tuple[BasisRef, ...] = ()
    limitations: tuple[NonEmptyStr, ...] = ()
    unknown_refs: tuple[NonEmptyStr, ...] = ()
    research_needed: tuple[NonEmptyStr, ...] = ()


class BaseDraft(ContractModel):
    draft_id: NonEmptyStr
    message_plan_id: NonEmptyStr
    text: NonEmptyStr


class ShootingDelivery(ContractModel):
    message_plan: MessagePlan
    base_draft: BaseDraft

    @model_validator(mode="after")
    def bind_base_draft_to_plan(self) -> ShootingDelivery:
        if self.base_draft.message_plan_id != self.message_plan.message_plan_id:
            raise ValueError("base draft must bind to the same message plan")
        return self


def _bind_message_plan_draft(
    draft: MessagePlanDraft,
    *,
    bundle: ContentIntelligenceBundle,
    account_position_basis: str,
) -> ShootingDelivery:
    topic = bundle.topic_brief
    if topic is None:
        raise ValueError("shooting delivery requires an evidence-bound topic brief")
    treatment_fingerprint = json.dumps(
        draft.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    message_plan_id = _stable_id(
        "message-plan",
        bundle.record.record_id,
        topic.path.path_id,
        treatment_fingerprint,
    )
    message_plan = MessagePlan(
        message_plan_id=message_plan_id,
        record_id=bundle.record.record_id,
        **draft.model_dump(exclude={"limitations", "unknowns"}),
        account_position_basis=account_position_basis,
        evidence_refs=topic.evidence_refs,
        limitations=tuple(dict.fromkeys((*topic.limitations, *draft.limitations))),
        unknown_refs=topic.unknown_refs,
        research_needed=topic.research_needed,
    )
    base_text = "\n\n".join((draft.opening, *draft.message_beats, draft.closing))
    return ShootingDelivery(
        message_plan=message_plan,
        base_draft=BaseDraft(
            draft_id=_stable_id("base-draft", message_plan_id, base_text),
            message_plan_id=message_plan_id,
            text=base_text,
        ),
    )


SHOOTING_DELIVERY_SYSTEM_PROMPT = """<content_intelligence_delivery>
你是 TopicBrief 之后的内容交付编辑。语义理解和账号内容地图已经完成；地图给出长期讲什么和稳定怎么看，TopicBrief 才是今天从地图中选出的具体一题。

- 不得重新选择内容根、更换 TopicBrief 的具体问题，也不得把地图重新扩写成百科全书。
- 讲述方案必须兑现账号长期承诺并服从稳定观察方法，但不得把这两句话生硬复述进正文。当前热点只能增加这条内容的当日入口，不能让成稿脱离地图路径。
- 你的任务是将已经选定并取证的一条内容，收敛成今天可以继续制作的具体方案。
- message_plan 必须说清：谁在什么情境下遇到了什么具体事情或问题，账号从用户的真实立场给出什么明确观点。
- focal_subject 是这条内容中真正被讲述的人、群体或具体对象；不得用“某些人”、“相关人群”等空话代替。
- context 描述内容世界里的时间、地点、场合或处境，只在它真正影响这件事时填写；不得填写来源名称、资料年代、检索过程，也不得为了对称强行补齐。
- concrete_event_or_question 必须是一件可讲清的事、一个可回答的具体问题或一个可观察的行为，不得使用“品类与文化”、“某物的多元价值”一类宽泛方向。
- account_position 只能由用户原话支持。可以使用从业者、经营者或当事人的观察视角，但不得补造年限、客户案例、业绩、资质或专业能力，不得冒充用户没有声明的身份。
- 用户身份只决定观察角度，不要求把用户的店铺、职业或商品写进正文；不得冒充医生、律师、历史学者或其他身份。
- point_of_view 必须是一句可被辩认的明确判断，但不得超出 TopicBrief 的中心判断、机制、反面边界和已读证据。用户立场只决定观察角度，不能替代事实证据。
- entry_point 必须说明从哪个具体事实、人物、物件、场面或问题切入；选择一个主入口，让观众立刻进入这条内容，不要把多个来源和背景资料并列成目录。
- telling_lens 必须选定一个连贯的讲述视角，例如跟着某个人、某件物、某段关系、一次变化或一组对照观察整件事。视角可以重新组织证据，不能发明证据或更换选题。
- audience_question 是观众在听完之前真正想追下去的问题。它可以形成诚实的信息差，但不能制造虚假悬念，也不能承诺输入证据无法兑现的答案。
- information_order 必须说明信息按什么顺序揭示，以及前一层理解如何引出后一层；不要把资料按百科目录平铺。
- payoff 必须回答 audience_question，并把观众带回 TopicBrief 的中心判断，形成一个比开头更多的新理解。
- topic_title 和 opening 可以有吸引力，但标题包装不能替代切入点、视角、证据推进和最终兑现。不得用“震惊、惊呆、不看后悔”等空壳词冒充内容强度。
- 来源名称本身不是内容。除非来源身份就是事件的一部分或某个断言必须就地归因，否则让证据约束事实并保留在参考资料中，不要把正文写成资料汇报。
- opening、message_beats 和 closing 共同构成表现形式之前的基础文案。都要写成可直接连起来表达的句子，不要写成“讲背景”、“分析原因”一类操作标签。不设固定段数、时长、镜头数、信息点数或发布配额。
- opening、message_beats 和 closing 只能改写输入的具体问题、中心判断、作用机制、反面边界和已读观察。输入没有的人名、角色名称、仪式步骤、历史原因、数字或因果不得由常识补入；需要时写入 unknowns。
- 基础文案先把话说清，不预设用户必须口播、演短剧、出镜或拥有某种素材。
- 对医疗、法律、金融、健康或其他高风险事实，只能沿已给证据表达；证据不足时保留为问题或未知，不得写成确定建议。
- 不补造数据、历史细节、具体人名、用户经历、拍摄素材或经营结果。未请求时不加销售话术、商业回桥、发布节奏或投流方案。
- 不得因为用户从事商业经营，就把 closing 写成购买、成交、市场、客户或“消费者为什么买单”。立场负责观察，收束只回到这条内容的判断。

只返回结构化合同。
</content_intelligence_delivery>"""


async def synthesize_shooting_delivery(
    bundle: ContentIntelligenceBundle,
    *,
    user_request: str,
    model: Any,
    runnable_config: dict[str, Any] | None = None,
) -> ShootingDelivery | None:
    """Translate one evidence-bound topic into a concrete, format-neutral delivery."""

    topic = bundle.topic_brief
    world = bundle.content_world
    if topic is None or world is None or world.content_root is None:
        return None

    draft = await _invoke_structured(
        model,
        MessagePlanDraft,
        (
            SystemMessage(content=SHOOTING_DELIVERY_SYSTEM_PROMPT),
            HumanMessage(content=_render_delivery_input(bundle, user_request=user_request)),
        ),
        runnable_config=runnable_config,
        include_raw=True,
        container_fields={"message_beats", "limitations", "unknowns"},
    )
    return draft.bind(bundle=bundle, account_position_basis=user_request)


def _render_delivery_input(bundle: ContentIntelligenceBundle, *, user_request: str) -> str:
    topic = bundle.topic_brief
    world = bundle.content_world
    assert topic is not None and world is not None and world.content_root is not None

    observations_by_id = {item.observation_id: item for item in bundle.record.observations}
    sources_by_id = {item.source_id: item for item in bundle.record.sources}
    evidence_observations = []
    source_ids: list[str] = []
    for evidence_ref in topic.evidence_refs:
        if evidence_ref.kind != "observation":
            continue
        observation = observations_by_id.get(evidence_ref.ref_id)
        if observation is None:
            continue
        evidence_observations.append(
            {
                "observation_id": observation.observation_id,
                "claim": observation.claim,
                "source_refs": observation.source_refs,
            }
        )
        for source_ref in observation.source_refs:
            if source_ref not in source_ids:
                source_ids.append(source_ref)

    payload = {
        "用户原话": user_request,
        "已冻结内容根": world.content_root,
        "账号长期承诺": world.editorial_promise,
        "持续观察方法": world.recurring_lens,
        "内容地图版本": world.content_map_version_id(),
        "已取证选题": {
            "具体问题": topic.question,
            "中心判断": topic.central_claim,
            "作用机制": topic.mechanism,
            "反面与边界": topic.counterpoint,
            "内容路径": [
                {
                    "from": step.from_label,
                    "relation": step.relation,
                    "to": step.to_label,
                }
                for step in topic.path.steps
            ],
            "证据限制": topic.limitations,
            "待研究": topic.research_needed,
        },
        "已读观察": evidence_observations,
        "来源回执": [
            source.model_dump(
                mode="json",
                include={"source_id", "kind", "evidence_role", "title", "uri"},
                exclude_none=True,
            )
            for source_id in source_ids
            if (source := sources_by_id.get(source_id)) is not None
        ],
    }
    return "--- BEGIN SHOOTING DELIVERY INPUT ---\n" + json.dumps(payload, ensure_ascii=False, indent=2) + "\n--- END SHOOTING DELIVERY INPUT ---"


def render_shooting_delivery(
    bundle: ContentIntelligenceBundle,
    delivery: ShootingDelivery,
) -> str:
    topic = bundle.topic_brief
    world = bundle.content_world
    if topic is None or world is None or world.content_root is None:
        raise ValueError("shooting delivery is not bound to an evidence topic and content root")
    plan = delivery.message_plan
    if plan.record_id != bundle.record.record_id:
        raise ValueError("shooting delivery record does not match the content bundle")

    lines = [
        "# 账号内容定位",
        "",
        f"**长期讲什么：** {world.content_root}",
    ]
    if world.editorial_promise is not None:
        lines.extend(("", f"**关注理由：** {world.editorial_promise}"))
    if world.recurring_lens is not None:
        lines.extend(("", f"**稳定观察方法：** {world.recurring_lens}"))
    if world.dimensions:
        lines.extend(("", "## 长期内容疆域", ""))
        lines.extend(f"- **{dimension.name}：** {dimension.rationale}" for dimension in world.dimensions)
    lines.extend(
        (
            "",
            "# 今日建议拍摄",
            "",
            f"## {plan.topic_title}",
            "",
            f"**谁：** {plan.focal_subject}",
        )
    )
    if plan.context is not None:
        lines.extend(("", f"**时间 / 场景：** {plan.context}"))
    lines.extend(
        (
            "",
            f"**发生什么：** {plan.concrete_event_or_question}",
            "",
            f"**你的立场：** {plan.account_position}",
            "",
            f"**核心观点：** {plan.point_of_view}",
            "",
            f"**从哪里讲起：** {plan.entry_point}",
            "",
            f"**讲述视角：** {plan.telling_lens}",
            "",
            f"**观众一路想知道：** {plan.audience_question}",
            "",
            f"**信息怎么揭开：** {plan.information_order}",
            "",
            f"**最后得到什么：** {plan.payoff}",
            "",
            "## 内容推进",
            "",
            f"**开头：** {plan.opening}",
            "",
        )
    )
    lines.extend(f"{index}. {beat}" for index, beat in enumerate(plan.message_beats, start=1))
    lines.extend(
        (
            "",
            f"**收束：** {plan.closing}",
            "",
            "## 基础文案",
            "",
            delivery.base_draft.text,
            "",
            "## 内容路径",
            "",
            " → ".join(
                dict.fromkeys(
                    (
                        world.content_root,
                        *(label for step in topic.path.steps for label in (step.from_label, step.to_label)),
                    )
                )
            ),
        )
    )

    boundary_items = tuple(dict.fromkeys((*plan.limitations, *plan.research_needed)))
    if boundary_items:
        lines.extend(("", "## 证据边界", ""))
        lines.extend(f"- {item}" for item in boundary_items)

    unknowns_by_id = {item.unknown_id: item.question for item in bundle.record.unknowns}
    unknown_items = tuple(unknowns_by_id[ref] for ref in plan.unknown_refs if ref in unknowns_by_id)
    if unknown_items:
        lines.extend(("", "## 待确认", ""))
        lines.extend(f"- {item}" for item in unknown_items)

    citations = _topic_citations(bundle)
    if citations:
        lines.extend(("", "## 参考资料", ""))
        lines.extend(f"- [{title}]({uri})" for title, uri in citations)
    return "\n".join(lines).strip()


def _topic_citations(bundle: ContentIntelligenceBundle) -> tuple[tuple[str, str], ...]:
    topic = bundle.topic_brief
    if topic is None:
        return ()
    observations = {item.observation_id: item for item in bundle.record.observations}
    sources = {item.source_id: item for item in bundle.record.sources}
    citations: list[tuple[str, str]] = []
    seen: set[str] = set()
    for evidence_ref in topic.evidence_refs:
        if evidence_ref.kind != "observation":
            continue
        observation = observations.get(evidence_ref.ref_id)
        if observation is None:
            continue
        for source_ref in observation.source_refs:
            source = sources.get(source_ref)
            if source is None or source.uri is None or source.uri in seen:
                continue
            seen.add(source.uri)
            citations.append((source.title or source.uri, source.uri))
    return tuple(citations)


def _stable_id(prefix: str, *parts: str) -> str:
    payload = "\x1f".join(parts).encode("utf-8")
    return f"{prefix}-{hashlib.sha256(payload).hexdigest()[:16]}"
