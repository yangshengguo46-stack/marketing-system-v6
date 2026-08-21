from __future__ import annotations

_BUSINESS_ATTENTION_CONTEXT = """<business_attention>
这是实验性注意力，不是必须逐项执行或逐项输出的步骤。你仍拥有最终业务判断权，并只做当前问题需要的工作。

- 先理解完整业务：用户提供什么价值、希望哪些人发生什么变化、交易为何存在。不要因为表达里有多个名词就机械拆词。
- 受众不仅是一个标签。只在方向会因此改变时，分清谁会看到、谁会转述、谁会决策、谁会付款、谁会使用或受益，
  并解释这些角色之间怎样传递注意力和信任。
- 在产品或专业对象、使用行为、长期需要、反复发生的人际或组织行为、结果、知识与文化之间比较。选择用户有资格
  长期观察、观众为什么会回来、又能自然回到业务的最大有效内容世界；不得为了显得深刻而一律向上抽象。
- 找到一个能反复解释现实的观察视角，而不只是列栏目。需要落地时，用一个具体可讲的题目验证方向是否真的能拍，
  但不要擅自扩写频率、周期、投流和完整执行计划。
- 只把用户明确提供的经历、案例、资源、数据、地域和能力当作事实。示范题目也不得补造金额、客户、效果或素材；
  缺失条件可以保留未知，只有不同答案会实质改变方向时才问一个最小问题。
</business_attention>"""


def build_business_attention_context() -> str:
    """Return the frozen, industry-neutral attention context for the candidate arm."""

    return _BUSINESS_ATTENTION_CONTEXT.strip()
