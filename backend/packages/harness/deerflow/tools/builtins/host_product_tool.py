from __future__ import annotations

from langchain_core.tools import tool

from deerflow.incubation import current_host_product_profile


@tool("inspect_agent_product_profile", parse_docstring=True)
def inspect_agent_product_profile_tool() -> str:
    """Read verified product facts when the marketing subject is this Agent itself.

    Use only for explicit self-marketing or product-positioning questions about
    the current Agent. This read-only profile is not a user-business template
    and does not initiate an account workflow.
    """

    return current_host_product_profile().model_dump_json()


__all__ = ["inspect_agent_product_profile_tool"]
