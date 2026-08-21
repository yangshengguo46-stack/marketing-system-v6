from __future__ import annotations

from typing import Annotated

from langchain_core.tools import tool
from pydantic import Field

from deerflow.content_intelligence import TermResolution
from deerflow.tools.builtins.incubation_tool_support import search_term_evidence


@tool("verify_business_term", parse_docstring=True)
async def verify_business_term_tool(
    term_expression: Annotated[str, Field(min_length=1, max_length=240)],
) -> str:
    """Verify one unfamiliar or recent business expression with one bounded search.

    This capability only checks what a term or abbreviation means. It is not
    market research, benchmark evidence, a content map, or an account strategy.
    Search summaries remain term evidence and cannot support market-size,
    performance, policy, or operating claims.

    Args:
        term_expression: The exact unfamiliar expression copied from the user's current message.
    """

    query = term_expression.strip()
    try:
        results = await search_term_evidence(query, 3)
    except Exception:
        results = ()
    if results:
        resolution = TermResolution.from_search_results(
            query=query,
            checked_terms=(query,),
            unknown_terms=(query,),
            results=results,
        )
    else:
        resolution = TermResolution.unresolved(
            query=query,
            checked_terms=(query,),
            unknown_terms=(query,),
            limitation="词项核实没有取得可用公开证据，当前具体含义保持未知。",
        )
    return resolution.model_dump_json(exclude_none=True)


__all__ = ["verify_business_term_tool"]
