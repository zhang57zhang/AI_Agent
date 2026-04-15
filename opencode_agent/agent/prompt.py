"""Prompt engine — builds system prompts for different agent types.

Loads SYSTEM_PROMPT.md and injects dynamic context:
- Current working directory
- Git branch/status
- Available tools
- Model information
- Skill content (loaded from .md files)
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from opencode_agent.config import AgentName, get_config

logger = logging.getLogger("opencode_agent.agent.prompt")

# Cache for loaded prompt content
_prompt_cache: dict[str, str] = {}
_prompt_mtime: float = 0


def _load_system_prompt() -> str:
    """Load SYSTEM_PROMPT.md from disk (with caching)."""
    global _prompt_cache, _prompt_mtime

    cfg = get_config()
    prompt_path = cfg.system_prompt_path

    if not prompt_path.is_absolute():
        prompt_path = Path.cwd() / prompt_path

    try:
        mtime = prompt_path.stat().st_mtime
        if prompt_path in _prompt_cache and mtime == _prompt_mtime:
            return _prompt_cache[prompt_path]

        content = prompt_path.read_text(encoding="utf-8")
        _prompt_cache[str(prompt_path)] = content
        _prompt_mtime = mtime
        logger.info("Loaded system prompt from %s (%d chars)", prompt_path, len(content))
        return content
    except FileNotFoundError:
        logger.warning("SYSTEM_PROMPT.md not found at %s", prompt_path)
        return _default_system_prompt()
    except Exception as e:
        logger.warning("Error loading system prompt: %s", e)
        return _default_system_prompt()


def _default_system_prompt() -> str:
    """Fallback system prompt when SYSTEM_PROMPT.md is not found."""
    return """You are an AI coding assistant with access to various tools for file operations,
command execution, web browsing, and git operations. You help developers write, debug,
and maintain code efficiently.

Key principles:
- Follow existing project patterns and style
- Make minimal, focused changes
- Verify changes with tests when possible
- Ask for clarification when requirements are ambiguous
- Always explain what you're doing and why
"""


def _get_git_context() -> str:
    """Get current git branch and status for prompt injection."""
    import subprocess

    try:
        cfg = get_config()
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, timeout=5,
            cwd=str(cfg.working_dir),
        )
        if result.returncode == 0 and result.stdout.strip():
            return f"Git branch: {result.stdout.strip()}"
    except Exception:
        pass
    return ""


def _load_skills(skills_dir: Path | None = None) -> str:
    """Load all skill .md files and format them for injection."""
    if skills_dir is None:
        cfg = get_config()
        skills_dir = cfg.skills_dir

    if not skills_dir or not skills_dir.exists():
        return ""

    skill_sections: list[str] = []
    for skill_file in sorted(skills_dir.glob("**/*.md")):
        try:
            content = skill_file.read_text(encoding="utf-8").strip()
            rel_path = skill_file.relative_to(skills_dir)
            skill_sections.append(f"### Skill: {rel_path}\n\n{content}")
        except Exception as e:
            logger.warning("Failed to load skill %s: %s", skill_file, e)

    if not skill_sections:
        return ""

    return "\n\n## Active Skills\n\n" + "\n\n---\n\n".join(skill_sections)


def get_agent_prompt(
    agent_name: AgentName = AgentName.CODER,
    model_name: str = "",
    tools_summary: str = "",
) -> str:
    """Build the full system prompt for an agent.

    Args:
        agent_name: Which agent type (coder, task, summarizer, title).
        model_name: The model being used (injected for context).
        tools_summary: Optional summary of available tools.

    Returns:
        Complete system prompt string ready for the LLM.
    """
    base_prompt = _load_system_prompt()

    # Agent-specific prefixes
    agent_prefixes = {
        AgentName.CODER: (
            "You are an AI coding assistant with full read/write access to the codebase. "
            "You can edit files, run commands, search code, and manage git operations. "
            "Always follow the workflow: Understand -> Plan -> Execute -> Verify.\n\n"
        ),
        AgentName.TASK: (
            "You are a code exploration and analysis agent. You have READ-ONLY access "
            "to the codebase. Use Glob, Grep, and ReadFile to explore and analyze code. "
            "Provide thorough analysis but do not modify any files.\n\n"
        ),
        AgentName.SUMMARIZER: (
            "You are a summarization agent. Your job is to condense information into "
            "clear, concise summaries. Focus on key points, decisions, and action items.\n\n"
        ),
        AgentName.TITLE: (
            "You are a title generation agent. Generate a short, descriptive title "
            "(max 80 characters) that captures the essence of a conversation or task.\n\n"
        ),
    }

    prefix = agent_prefixes.get(agent_name, "")
    cfg = get_config()

    # Build context block
    context_parts: list[str] = []

    # Working directory
    context_parts.append(f"Working directory: {cfg.working_dir}")

    # Model info
    if model_name:
        context_parts.append(f"Model: {model_name}")

    # Git context
    git_ctx = _get_git_context()
    if git_ctx:
        context_parts.append(git_ctx)

    # Timestamp
    context_parts.append(f"Current time: {time.strftime('%Y-%m-%d %H:%M:%S')}")

    context_block = "\n".join(context_parts)

    # Tools summary
    tools_block = ""
    if tools_summary:
        tools_block = f"\n\n## Available Tools\n\n{tools_summary}"

    # Skills
    skills_block = _load_skills()

    # Assemble final prompt
    parts = [
        prefix,
        base_prompt,
        f"\n\n---\n## Runtime Context\n\n{context_block}",
        tools_block,
        skills_block,
    ]

    return "\n".join(part for part in parts if part)


def get_tools_description(tools: list[Any]) -> str:
    """Generate a human-readable summary of available tools.

    This is injected into the system prompt to help the LLM understand
    what tools it has access to.
    """
    lines: list[str] = []
    for tool in tools:
        info = tool.info()
        lines.append(f"- **{info.name}**: {info.description}")
        if info.required:
            lines.append(f"  Required params: {', '.join(info.required)}")
    return "\n".join(lines)