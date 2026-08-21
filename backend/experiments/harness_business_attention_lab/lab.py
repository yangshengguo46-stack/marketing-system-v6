from __future__ import annotations

import hashlib

from experiments.harness_business_attention_lab.contracts import BlindPair, PromptManifest

_MINIMAL_HOST_PROMPT = """<role>
你是 DeerFlow 的内容孵化 Lead，负责回答当前用户的起号与业务传播问题。
</role>

你拥有最终业务判断权。方法、工具和资料只能辅助，不能替你决定答案。直接回答当前问题，不为完整感追加
用户没有要求的流程、周期、频率、投流或执行清单。

只把用户明确提供的内容当作事实。区分已知、推断、条件与未知；不得编造用户的经历、案例、资源、资质、
受众数据、渠道或制作能力。缺失信息不妨碍有用判断时，保留未知并继续；只有不同答案会实质改变方向时，
才问一个最小问题。

不要输出内部推理过程。使用与用户相同的语言，清楚、简洁地给出实际答案。
"""


_BUSINESS_ATTENTION = """<business_attention>
下面是可自由移动的注意力，不是待办清单，也不要求逐项输出。

- 先理解完整业务表达：它提供什么价值，涉及哪些人，用户最终希望谁发生什么变化。不要为了拆词而拆词。
- 只有付款者、决策者、使用者与内容观众的差异会改变方向时，才把受众关系单独展开。
- 寻找这个业务有资格长期观察的最大有效长期内容世界。它可以是产品或专业对象本身，也可以是使用行为、长期
  需求、反复发生的关系、结果、知识或文化；哪一个更强取决于当前业务，禁止一律向上抽象。
- 账号不是行业百科。判断观众为什么会回来、这个主体凭什么持续讲、什么观察视角能形成辨识度，以及兴趣
  和信任怎样合理返回用户的业务。
- 人设与表现形式服从真实能力和内容世界。用户没有提供出镜、案例、场地、团队或专业背书时，只能给条件化
  选项，不能替用户补齐。

回答前在内部比较几个真正不同的方向，选择当前事实下最有解释力的一条；只有备选会帮助用户决策时才展示。
需要让方向落地时，可以给一两个具体题目作示范，但不要擅自扩写成发布计划。
</business_attention>
"""


def build_minimal_host_prompt() -> str:
    return _MINIMAL_HOST_PROMPT.strip()


def build_business_attention_section() -> str:
    return _BUSINESS_ATTENTION.strip()


def build_focused_business_prompt() -> str:
    return f"{build_minimal_host_prompt()}\n\n{build_business_attention_section()}"


def build_prompt_manifest(
    *,
    arm: str,
    sections: tuple[tuple[str, str], ...],
    user_prompt: str,
) -> PromptManifest:
    all_sections = (*sections, ("user_prompt", user_prompt))
    section_bytes = {name: len(text.encode("utf-8")) for name, text in all_sections}
    section_hashes = {name: hashlib.sha256(text.encode("utf-8")).hexdigest() for name, text in all_sections}
    total_bytes = sum(section_bytes.values())
    return PromptManifest(
        arm=arm,
        section_bytes=section_bytes,
        section_hashes=section_hashes,
        total_bytes=total_bytes,
        estimated_tokens=max(1, (total_bytes + 3) // 4),
    )


def build_blind_pair(
    *,
    case_id: str,
    left_arm: str,
    left_text: str,
    right_arm: str,
    right_text: str,
) -> BlindPair:
    swap = int(hashlib.sha256(case_id.encode("utf-8")).hexdigest()[-1], 16) % 2 == 1
    if swap:
        answer_a, answer_b = right_text, left_text
        arm_by_label = {"A": right_arm, "B": left_arm}
    else:
        answer_a, answer_b = left_text, right_text
        arm_by_label = {"A": left_arm, "B": right_arm}
    judge_payload = f"<answer_a>\n{answer_a}\n</answer_a>\n\n<answer_b>\n{answer_b}\n</answer_b>"
    return BlindPair(
        case_id=case_id,
        answer_a=answer_a,
        answer_b=answer_b,
        arm_by_label=arm_by_label,
        judge_payload=judge_payload,
    )
