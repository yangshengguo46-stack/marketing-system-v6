"""Deferred Skill discovery, inspection, and explicit activation.

``describe_skill`` returns metadata without changing Agent behavior.
``activate_skill`` loads one exact SKILL.md and emits an authenticated-by-origin
activation marker that runtime middleware validates before changing task-scoped
authority. Ordinary file reads are inspection only.

Mirrors ``build_tool_search_tool`` from ``tool_search.py``: same query syntax,
same ``Command`` + ``ToolMessage`` return shape, same fail-safe degradation.
"""

from __future__ import annotations

import hashlib
import html
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from fnmatch import fnmatchcase
from typing import TYPE_CHECKING, Annotated

from langchain_core.messages import ToolMessage
from langchain_core.tools import InjectedToolCallId, tool
from langgraph.types import Command

if TYPE_CHECKING:
    from langchain.tools import BaseTool

from deerflow.constants import DEFAULT_SKILLS_CONTAINER_PATH
from deerflow.skills.catalog import SkillCatalog
from deerflow.skills.types import SKILL_MD_FILE, Skill, SkillCategory

logger = logging.getLogger(__name__)

_SKILL_INDEX_DESCRIPTION_MAX_CHARS = 120
SKILL_ACTIVATION_ENTRY_KEY = "skill_activation_entry"


# ── Setup ────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class SkillSearchSetup:
    """Result of assembling skill search for one agent build.

    Mirrors ``DeferredToolSetup`` from ``tool_search.py``.

    - **Empty** ``(None, None, frozenset())``: no skills available or skill search
      disabled.  The agent falls back to the legacy full-metadata prompt.
    - **Populated**: inspection and activation tools are appended to the agent's
      tools, while ``skill_names`` are rendered in ``<skill_index>`` instead of
      full metadata.
    """

    describe_skill_tool: BaseTool | None
    activate_skill_tool: BaseTool | None
    skill_names: frozenset[str]


def build_describe_skill_tool(
    catalog: SkillCatalog,
    *,
    container_base_path: str = DEFAULT_SKILLS_CONTAINER_PATH,
) -> BaseTool:
    """Build the ``describe_skill`` tool as a closure over *catalog*.

    The returned tool is a plain ``@tool``-decorated function that searches the
    catalog and returns a ``Command`` wrapping a ``ToolMessage``.  No graph state
    mutation is needed (unlike ``tool_search`` which promotes deferred tools).
    """

    @tool
    def describe_skill(
        name: str,
        tool_call_id: Annotated[str, InjectedToolCallId],
    ) -> Command:
        """Fetch usage metadata for installed skills so you can decide whether to load them.

        Skills appear with short routing summaries in <skill_index> in the
        system prompt. This tool matches a query against installed skills and
        returns their full metadata — description, allowed tools, and file
        location — without activating them. If one fits the current task, call
        activate_skill with that exact Skill name.

        Query forms:
          - "select:data-analysis,deep-research" -- fetch these exact skills (no cap)
          - "chart visualization" -- keyword search, best matches (up to 5)
          - "+podcast gen" -- require "podcast" in the name, rank by remaining terms (up to 5)
        """
        matched = catalog.search(name)
        if not matched:
            content = f"No skills matched: {name}"
        else:
            content = _render_skill_metadata(matched, container_base_path)

        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=content,
                        tool_call_id=tool_call_id,
                        name="describe_skill",
                    )
                ],
            }
        )

    return describe_skill


def _exact_skill(catalog: SkillCatalog, name: str) -> Skill | None:
    normalized = name.strip()
    if not normalized or normalized != name or any(skill.name == normalized for skill in catalog.skills) is False:
        return None
    return next(skill for skill in catalog.skills if skill.name == normalized)


def build_activate_skill_tool(
    catalog: SkillCatalog,
    *,
    container_base_path: str = DEFAULT_SKILLS_CONTAINER_PATH,
) -> BaseTool:
    """Build the exact-name, task-scoped ``activate_skill`` tool."""

    @tool
    def activate_skill(
        name: str,
        tool_call_id: Annotated[str, InjectedToolCallId],
    ) -> Command:
        """Activate one installed Skill for the current task using its exact name.

        Inspect candidates with describe_skill first. Activation loads the
        selected SKILL.md, returns its full guidance, and lets the runtime apply
        its tool and secret policy for this run. A later activation may replace
        an Agent-selected Skill, but cannot override a Skill explicitly selected
        by the user with /skill-name.
        """
        skill = _exact_skill(catalog, name)
        if skill is None:
            message = ToolMessage(
                content=f"Error: '{name}' is not one exact installed Skill name. Inspect candidates with describe_skill first.",
                tool_call_id=tool_call_id,
                name="activate_skill",
                status="error",
            )
            return Command(update={"messages": [message]})

        try:
            if skill.skill_file.name != SKILL_MD_FILE:
                raise ValueError(f"expected {SKILL_MD_FILE}")
            content = skill.skill_file.read_text(encoding="utf-8")
        except (OSError, UnicodeError, ValueError) as exc:
            logger.warning("Failed to load Skill %s for activation: %s", skill.name, exc)
            message = ToolMessage(
                content=f"Error: Skill '{skill.name}' could not be loaded safely.",
                tool_call_id=tool_call_id,
                name="activate_skill",
                status="error",
            )
            return Command(update={"messages": [message]})

        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        path = skill.get_container_file_path(container_base_path)
        escaped_name = html.escape(skill.name, quote=True)
        escaped_path = html.escape(path, quote=True)
        escaped_hash = html.escape(content_hash, quote=True)
        escaped_content = html.escape(content, quote=False)
        message = ToolMessage(
            content=(
                f'<skill_activation name="{escaped_name}" path="{escaped_path}" sha256="{escaped_hash}">\n'
                "This Skill is active for the current task. Apply it with judgment; user facts and higher-level boundaries still govern.\n"
                '<skill_content encoding="xml-escaped">\n'
                f"{escaped_content}\n"
                "</skill_content>\n"
                "</skill_activation>"
            ),
            tool_call_id=tool_call_id,
            name="activate_skill",
            additional_kwargs={
                SKILL_ACTIVATION_ENTRY_KEY: {
                    "name": skill.name,
                    "path": path,
                    "description": " ".join((skill.description or "").split()),
                    "sha256": content_hash,
                }
            },
        )
        return Command(update={"messages": [message]})

    return activate_skill


def build_skill_search_setup(
    skills: list,
    *,
    enabled: bool,
    container_base_path: str = DEFAULT_SKILLS_CONTAINER_PATH,
    prompt_index_patterns: list[str] | None = None,
) -> SkillSearchSetup:
    """Build the skill search setup from a filtered skill list.

    Mirrors ``build_deferred_tool_setup`` from ``tool_search.py``.

    Returns an empty setup when *enabled* is ``False`` or *skills* is empty.
    """
    if not enabled or not skills:
        return SkillSearchSetup(None, None, frozenset())

    catalog = SkillCatalog(tuple(skills))
    prompt_names = catalog.names
    if isinstance(prompt_index_patterns, (list, tuple)):
        patterns = tuple(pattern.strip() for pattern in prompt_index_patterns if pattern.strip())
        prompt_names = frozenset(name for name in catalog.names if any(fnmatchcase(name, pattern) for pattern in patterns))
    return SkillSearchSetup(
        describe_skill_tool=build_describe_skill_tool(
            catalog,
            container_base_path=container_base_path,
        ),
        activate_skill_tool=build_activate_skill_tool(
            catalog,
            container_base_path=container_base_path,
        ),
        skill_names=prompt_names,
    )


# ── Rendering ────────────────────────────────────────────────────────────────


def _render_skill_metadata(skills: list, container_base_path: str) -> str:
    """Render structured metadata for a list of matched skills."""
    blocks: list[str] = []
    for s in skills:
        mutability = "[custom, editable]" if s.category == SkillCategory.CUSTOM else "[built-in]"
        tools_line = ", ".join(s.allowed_tools) if s.allowed_tools else "(all)"
        location = s.get_container_file_path(container_base_path)
        # name/description/allowed-tools come from untrusted ``.skill`` frontmatter;
        # escape so a value cannot forge a framework tag in the describe_skill output.
        name = html.escape(s.name, quote=False)
        description = html.escape(s.description, quote=False)
        tools = html.escape(tools_line, quote=False)
        loc = html.escape(location, quote=False)
        blocks.append(f"## Skill: {name}\n- Description: {description} {mutability}\n- Allowed tools: {tools}\n- Location: {loc}")
    return "\n\n".join(blocks)


# ── Prompt rendering ─────────────────────────────────────────────────────────


def get_skill_index_prompt_section(
    *,
    skill_names: frozenset[str] = frozenset(),
    skill_descriptions: Mapping[str, str] | None = None,
    container_base_path: str = DEFAULT_SKILLS_CONTAINER_PATH,
    skill_evolution_section: str = "",
) -> str:
    """Generate ``<skill_system>`` with a compact ``<skill_index>``.

    A name and bounded usage summary are level-one routing metadata. The agent
    can use ``describe_skill`` to inspect full metadata and ``activate_skill``
    to load one exact method for the current task. Skill method bodies remain
    out of the base prompt.

    Returns empty string when there are no skills.
    """
    if not skill_names:
        return ""

    descriptions = skill_descriptions or {}
    index_lines: list[str] = []
    for raw_name in sorted(skill_names):
        name = html.escape(raw_name, quote=False)
        description = " ".join(str(descriptions.get(raw_name, "")).split())
        if len(description) > _SKILL_INDEX_DESCRIPTION_MAX_CHARS:
            description = f"{description[: _SKILL_INDEX_DESCRIPTION_MAX_CHARS - 3]}..."
        suffix = f": {html.escape(description, quote=False)}" if description else ""
        index_lines.append(f"- {name}{suffix}")
    index = "\n".join(index_lines)
    evolution = f"\n{skill_evolution_section}" if skill_evolution_section else ""

    return f"""<skill_system>
You have access to skills that provide optimized workflows for specific tasks.

**On-Demand Skill Discovery:**
1. Treat listed Skills as optional capabilities, not mandatory stages
2. When a Skill may materially improve the task, call describe_skill(name) to inspect metadata only
3. If its capability fits, call activate_skill(exact_name) to activate it for this task
4. A read_file call, including a direct read of SKILL.md, is inspection only and never activates a Skill
5. Apply activated guidance with judgment; user facts, goals, and higher-level boundaries still govern

**Explicit Slash Skill Activation:**
- If the user starts a request with `/<skill-name>`, that skill was explicitly requested.
- The runtime injects the activated skill content; do not call `read_file` for that SKILL.md again unless the injected skill references supporting resources you need.
{evolution}
<skill_index>
{index}
</skill_index>

Skills are located at: {container_base_path}
</skill_system>"""
