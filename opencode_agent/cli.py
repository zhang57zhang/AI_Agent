"""CLI entry point — argument parsing and app startup."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from opencode_agent.config import AgentName, ModelProvider, init_config
from opencode_agent.permissions import PermissionService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="opencode-agent",
        description="OpenCode-like AI Coding Agent — Terminal TUI with MCP, LSP, and multi-agent orchestration",
    )
    parser.add_argument(
        "--model", "-m",
        default=None,
        help="Model to use (e.g., gpt-4o, claude-sonnet-4-20250514, llama3)",
    )
    parser.add_argument(
        "--provider", "-p",
        choices=[p.value for p in ModelProvider],
        default=None,
        help="LLM provider (openai, anthropic, local, openrouter)",
    )
    parser.add_argument(
        "--agent", "-a",
        choices=[a.value for a in AgentName],
        default="coder",
        help="Agent type (coder, task, summarizer, title)",
    )
    parser.add_argument(
        "--working-dir", "-w",
        default=None,
        help="Working directory (default: current directory)",
    )
    parser.add_argument(
        "--prompt", "-P",
        default=None,
        help="Path to SYSTEM_PROMPT.md",
    )
    parser.add_argument(
        "--skills-dir", "-s",
        default=None,
        help="Directory containing skill .md files",
    )
    parser.add_argument(
        "--no-mcp",
        action="store_true",
        help="Disable MCP tool discovery",
    )
    parser.add_argument(
        "--no-lsp",
        action="store_true",
        help="Disable LSP integration",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
    )
    parser.add_argument(
        "--version", "-v",
        action="version",
        version="opencode-agent 0.1.0",
    )
    return parser.parse_args()


def setup_logging(debug: bool = False) -> None:
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stderr,
    )
    # Suppress noisy loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("textual").setLevel(logging.WARNING)


def main() -> None:
    """Main entry point."""
    args = parse_args()
    setup_logging(debug=args.debug)

    # Build config overrides
    overrides: dict = {}

    if args.model:
        overrides.setdefault("agents", {})[AgentName.CODER] = {"model": args.model}
    if args.provider:
        overrides["default_provider"] = ModelProvider(args.provider)
    if args.working_dir:
        overrides["working_dir"] = Path(args.working_dir).resolve()
    if args.prompt:
        overrides["system_prompt_path"] = Path(args.prompt).resolve()
    if args.skills_dir:
        overrides["skills_dir"] = Path(args.skills_dir).resolve()
    if args.no_mcp:
        overrides["enable_mcp"] = False
    if args.no_lsp:
        overrides["enable_lsp"] = False

    # Initialize configuration
    config = init_config(**overrides)

    # Start the TUI
    from opencode_agent.tui.app import OpenCodeAgentApp

    app = OpenCodeAgentApp()
    app.run()


if __name__ == "__main__":
    main()