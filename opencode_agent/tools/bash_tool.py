"""Bash/command execution tool."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

from opencode_agent.base_types import ToolCall, ToolInfo, ToolResponse
from opencode_agent.config import get_config
from opencode_agent.tools.base import BaseTool, ToolContext


class BashTool(BaseTool):
    """Execute shell commands with timeout and working directory support."""

    def info(self) -> ToolInfo:
        return ToolInfo(
            name="bash_command",
            description=(
                "Execute a shell command and return stdout, stderr, and exit code.\n"
                "Supports both bash and PowerShell commands depending on platform.\n"
                "Commands run in the project working directory by default.\n"
                "Use the workdir parameter to change directories (prefer over cd).\n"
                "IMPORTANT: For file operations, prefer dedicated file tools over bash.\n"
                "AVOID using bash for: reading files, writing files, searching code.\n"
                "Use bash for: git, npm, pip, docker, build tools, and other CLI operations."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Shell command to execute."},
                    "timeout": {
                        "type": "integer",
                        "description": "Timeout in milliseconds. Default: 120000 (2 min).",
                        "default": 120000,
                    },
                    "workdir": {
                        "type": "string",
                        "description": "Working directory for the command. Defaults to project root.",
                    },
                },
                "required": ["command"],
            },
            required=["command"],
        )

    async def run(self, ctx: ToolContext, params: ToolCall) -> ToolResponse:
        try:
            data = json.loads(params.input) if isinstance(params.input, str) else params.input
        except (json.JSONDecodeError, TypeError):
            return ToolResponse.error(f"Invalid JSON parameters: {params.input}")

        command = data.get("command", "")
        timeout_ms = int(data.get("timeout", 120000))
        workdir = data.get("workdir", ctx.working_dir)

        if not command.strip():
            return ToolResponse.error("Empty command")

        # Safety check for dangerous commands
        config = get_config()
        for dangerous in config.dangerous_commands:
            if dangerous.lower() in command.lower():
                return ToolResponse.error(
                    f"DANGEROUS COMMAND DETECTED: '{dangerous}' found in command. "
                    "This operation may cause irreversible damage. If you genuinely need "
                    "to run this, the user must approve it manually."
                )

        # Check permission
        if ctx.permissions:
            from opencode_agent.base_types import PermissionAction, PermissionRequest
            granted = await ctx.permissions.request(
                PermissionRequest(
                    tool_name="bash_command",
                    action=PermissionAction.BASH,
                    params={"command": command},
                    description=f"Execute: {command[:200]}",
                ),
                session_id=ctx.session_id,
            )
            if not granted:
                return ToolResponse.error("Permission denied for bash command")

        # Determine shell
        is_windows = sys.platform == "win32"
        if is_windows:
            shell = ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command"]
        else:
            shell = ["/bin/bash", "-c"]

        try:
            proc = await asyncio.create_subprocess_exec(
                *shell,
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=workdir,
                env={**os.environ, "CI": "true"},
            )

            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_ms / 1000)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                return ToolResponse.error(
                    f"Command timed out after {timeout_ms}ms.\n"
                    "Consider increasing timeout or breaking the command into smaller steps."
                )

            stdout_text = stdout.decode("utf-8", errors="replace")
            stderr_text = stderr.decode("utf-8", errors="replace")
            exit_code = proc.returncode or 0

            # Truncate very large output
            max_output = 50000
            if len(stdout_text) > max_output:
                stdout_text = stdout_text[:max_output] + f"\n\n... (truncated, {len(stdout_text)} total chars)"

            if exit_code == 0:
                return ToolResponse.json_response({
                    "exit_code": exit_code,
                    "stdout": stdout_text,
                    "stderr": stderr_text,
                })
            else:
                return ToolResponse.error(
                    f"Exit code: {exit_code}\nstdout: {stdout_text}\nstderr: {stderr_text}"
                )

        except FileNotFoundError:
            return ToolResponse.error(f"Shell not found: {shell[0]}")
        except PermissionError:
            return ToolResponse.error(f"Permission denied executing: {command[:100]}")
        except OSError as e:
            return ToolResponse.error(f"OS error: {e}")