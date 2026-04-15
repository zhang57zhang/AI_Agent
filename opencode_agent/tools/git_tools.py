"""Git operation tools."""

from __future__ import annotations

import asyncio
import json
import subprocess
from typing import Any

from opencode_agent.base_types import ToolCall, ToolInfo, ToolResponse
from opencode_agent.tools.base import BaseTool, ToolContext


async def _run_git(args: list[str], cwd: str, timeout: int = 30000) -> tuple[int, str, str]:
    """Run a git command and return (exit_code, stdout, stderr)."""
    proc = await asyncio.create_subprocess_exec(
        "git", *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout / 1000)
    return (
        proc.returncode or 0,
        stdout.decode("utf-8", errors="replace"),
        stderr.decode("utf-8", errors="replace"),
    )


class GitStatusTool(BaseTool):
    def info(self) -> ToolInfo:
        return ToolInfo(
            name="git_status",
            description="Show working tree status — modified, untracked, staged files.",
            parameters={"type": "object", "properties": {}},
        )

    async def run(self, ctx: ToolContext, params: ToolCall) -> ToolResponse:
        code, stdout, stderr = await _run_git(["status", "--short", "-b"], ctx.working_dir)
        if code != 0:
            return ToolResponse.error(f"git status failed: {stderr}")
        return ToolResponse.text(stdout if stdout else "Clean working tree.") if code == 0 else ToolResponse.error(stderr)


class GitDiffTool(BaseTool):
    def info(self) -> ToolInfo:
        return ToolInfo(
            name="git_diff",
            description="Show unstaged and staged changes.",
            parameters={
                "type": "object",
                "properties": {
                    "staged": {"type": "boolean", "description": "Show only staged changes. Default: false."},
                },
            },
        )

    async def run(self, ctx: ToolContext, params: ToolCall) -> ToolResponse:
        data = json.loads(params.input) if isinstance(params.input, str) else {}
        args = ["diff", "--color=never"]
        if data.get("staged"):
            args.append("--staged")
        code, stdout, stderr = await _run_git(args, ctx.working_dir)
        if code != 0:
            return ToolResponse.error(stderr)
        return ToolResponse.text(stdout if stdout else "No changes.") if code == 0 else ToolResponse.error(stderr)


class GitLogTool(BaseTool):
    def info(self) -> ToolInfo:
        return ToolInfo(
            name="git_log",
            description="Show commit history.",
            parameters={
                "type": "object",
                "properties": {
                    "options": {"type": "string", "description": "Extra git log options, e.g. '--oneline -n 10'"},
                },
            },
        )

    async def run(self, ctx: ToolContext, params: ToolCall) -> ToolResponse:
        data = json.loads(params.input) if isinstance(params.input, str) else {}
        extra = data.get("options", "").split()
        args = ["log", "--color=never"] + extra
        code, stdout, stderr = await _run_git(args, ctx.working_dir)
        if code != 0:
            return ToolResponse.error(stderr)
        return ToolResponse.text(stdout) if code == 0 else ToolResponse.error(stderr)


class GitCommitTool(BaseTool):
    def info(self) -> ToolInfo:
        return ToolInfo(
            name="git_commit",
            description=(
                "Create a git commit. Only call when explicitly requested.\n"
                "NEVER commit without user's explicit request.\n"
                "NEVER update git config.\n"
                "NEVER force push."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "message": {"type": "string", "description": "Commit message."},
                    "all": {"type": "boolean", "description": "Stage all changes before commit."},
                },
                "required": ["message"],
            },
            required=["message"],
        )

    async def run(self, ctx: ToolContext, params: ToolCall) -> ToolResponse:
        data = json.loads(params.input) if isinstance(params.input, str) else {}
        message = data.get("message", "")
        if not message:
            return ToolResponse.error("Commit message is required")

        if data.get("all"):
            await _run_git(["add", "-A"], ctx.working_dir)

        code, stdout, stderr = await _run_git(["commit", "-m", message], ctx.working_dir)
        if code != 0:
            return ToolResponse.error(f"Commit failed: {stderr}")

        # Get the SHA
        _, sha_out, _ = await _run_git(["rev-parse", "HEAD"], ctx.working_dir)
        return ToolResponse.json_response({"success": True, "sha": sha_out.strip(), "message": message})


class GitBranchTool(BaseTool):
    def info(self) -> ToolInfo:
        return ToolInfo(
            name="git_branch",
            description="List, create, or delete branches.",
            parameters={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Branch name (for create/delete)."},
                    "action": {"type": "string", "enum": ["list", "create", "delete"], "default": "list"},
                },
            },
        )

    async def run(self, ctx: ToolContext, params: ToolCall) -> ToolResponse:
        data = json.loads(params.input) if isinstance(params.input, str) else {}
        action = data.get("action", "list")

        if action == "list":
            code, stdout, stderr = await _run_git(
                ["branch", "--color=never", "--all"], ctx.working_dir
            )
        elif action == "create" and data.get("name"):
            code, stdout, stderr = await _run_git(
                ["checkout", "-b", data["name"]], ctx.working_dir
            )
        elif action == "delete" and data.get("name"):
            code, stdout, stderr = await _run_git(
                ["branch", "-D", data["name"]], ctx.working_dir
            )
        else:
            return ToolResponse.error("Invalid action or missing branch name")

        if code != 0:
            return ToolResponse.error(stderr)
        return ToolResponse.text(stdout) if code == 0 else ToolResponse.error(stderr)


class GitCheckoutTool(BaseTool):
    def info(self) -> ToolInfo:
        return ToolInfo(
            name="git_checkout",
            description="Switch branches or restore working tree files.",
            parameters={
                "type": "object",
                "properties": {
                    "ref": {"type": "string", "description": "Branch name, tag, or commit to checkout."},
                },
                "required": ["ref"],
            },
            required=["ref"],
        )

    async def run(self, ctx: ToolContext, params: ToolCall) -> ToolResponse:
        data = json.loads(params.input) if isinstance(params.input, str) else {}
        ref = data.get("ref", "")
        if not ref:
            return ToolResponse.error("Ref is required")
        code, stdout, stderr = await _run_git(["checkout", ref], ctx.working_dir)
        if code != 0:
            return ToolResponse.error(stderr)
        return ToolResponse.text(f"Checked out: {ref}") if code == 0 else ToolResponse.error(stderr)


def get_git_tools() -> list[BaseTool]:
    return [
        GitStatusTool(),
        GitDiffTool(),
        GitLogTool(),
        GitCommitTool(),
        GitBranchTool(),
        GitCheckoutTool(),
    ]