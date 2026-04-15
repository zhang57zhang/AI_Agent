"""File operation tools: read, write, edit, glob, grep, ls."""

from __future__ import annotations

import fnmatch
import json
import os
import re
from pathlib import Path
from typing import Any

from opencode_agent.base_types import ToolCall, ToolInfo, ToolResponse
from opencode_agent.tools.base import BaseTool, ToolContext


class ReadFileTool(BaseTool):
    """Read file contents with optional line range."""

    def info(self) -> ToolInfo:
        return ToolInfo(
            name="read_file",
            description=(
                "Read a file from the local filesystem. Returns content with line numbers.\n"
                "Use offset and limit parameters to read specific sections of large files.\n"
                "Combine with Glob to find files first, then Read to examine them."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Absolute or relative path to the file to read.",
                    },
                    "offset": {
                        "type": "integer",
                        "description": "Line number to start reading from (1-indexed). Default: 1.",
                        "default": 1,
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of lines to read. Default: 2000.",
                        "default": 2000,
                    },
                    "encoding": {
                        "type": "string",
                        "description": "File encoding. Default: utf-8.",
                        "default": "utf-8",
                    },
                },
                "required": ["path"],
            },
            required=["path"],
        )

    async def run(self, ctx: ToolContext, params: ToolCall) -> ToolResponse:
        try:
            data = json.loads(params.input) if isinstance(params.input, str) else params.input
        except (json.JSONDecodeError, TypeError):
            return ToolResponse.error(f"Invalid JSON parameters: {params.input}")

        file_path = Path(data.get("path", ""))
        if not file_path.is_absolute():
            file_path = Path(ctx.working_dir) / file_path

        offset = max(1, int(data.get("offset", 1)))
        limit = int(data.get("limit", 2000))
        encoding = data.get("encoding", "utf-8")

        try:
            content = file_path.read_text(encoding=encoding)
        except FileNotFoundError:
            return ToolResponse.error(f"File not found: {file_path}")
        except PermissionError:
            return ToolResponse.error(f"Permission denied: {file_path}")
        except UnicodeDecodeError:
            return ToolResponse.error(f"Cannot decode file with encoding '{encoding}': {file_path}")

        lines = content.splitlines(keepends=True)
        total_lines = len(lines)

        # Apply offset (1-indexed)
        start = max(0, offset - 1)
        end = min(total_lines, start + limit)
        selected = lines[start:end]

        # Format with line numbers
        numbered = "".join(f"{i + start + 1}: {line}" for i, line in enumerate(selected))

        truncated = end < total_lines
        suffix = f"\n\n(Showing lines {start + 1}-{end} of {total_lines})" if truncated else ""
        suffix += f"\n(End of file - total {total_lines} lines)" if not truncated else ""

        return ToolResponse.text(numbered + suffix)


class WriteFileTool(BaseTool):
    """Create or overwrite a file."""

    def info(self) -> ToolInfo:
        return ToolInfo(
            name="write_file",
            description=(
                "Write content to a file. Creates parent directories if needed.\n"
                "Use the LS tool to verify the correct location when creating new files.\n"
                "Combine with Glob and Grep tools to find and modify multiple files.\n"
                "Always include descriptive comments when making changes to existing code."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path to write."},
                    "content": {"type": "string", "description": "Content to write."},
                    "encoding": {"type": "string", "description": "Encoding. Default: utf-8.", "default": "utf-8"},
                },
                "required": ["path", "content"],
            },
            required=["path", "content"],
        )

    async def run(self, ctx: ToolContext, params: ToolCall) -> ToolResponse:
        try:
            data = json.loads(params.input) if isinstance(params.input, str) else params.input
        except (json.JSONDecodeError, TypeError):
            return ToolResponse.error(f"Invalid JSON parameters: {params.input}")

        file_path = Path(data.get("path", ""))
        if not file_path.is_absolute():
            file_path = Path(ctx.working_dir) / file_path

        content = data.get("content", "")
        encoding = data.get("encoding", "utf-8")

        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content, encoding=encoding)
            written = len(content.encode(encoding))
            return ToolResponse.json_response({
                "success": True,
                "path": str(file_path),
                "written_bytes": written,
            })
        except PermissionError:
            return ToolResponse.error(f"Permission denied: {file_path}")
        except OSError as e:
            return ToolResponse.error(f"Write error: {e}")


class EditFileTool(BaseTool):
    """Search-and-replace within a file."""

    def info(self) -> ToolInfo:
        return ToolInfo(
            name="edit_file",
            description=(
                "Edit a file by replacing an exact text match with new content.\n"
                "The find string must match exactly (including whitespace).\n"
                "For regex replacement, set use_regex to true."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path to edit."},
                    "find": {"type": "string", "description": "Text to find (exact match or regex)."},
                    "replace": {"type": "string", "description": "Replacement text."},
                    "use_regex": {
                        "type": "boolean",
                        "description": "Treat find as regex pattern. Default: false.",
                        "default": False,
                    },
                },
                "required": ["path", "find", "replace"],
            },
            required=["path", "find", "replace"],
        )

    async def run(self, ctx: ToolContext, params: ToolCall) -> ToolResponse:
        try:
            data = json.loads(params.input) if isinstance(params.input, str) else params.input
        except (json.JSONDecodeError, TypeError):
            return ToolResponse.error(f"Invalid JSON parameters: {params.input}")

        file_path = Path(data.get("path", ""))
        if not file_path.is_absolute():
            file_path = Path(ctx.working_dir) / file_path

        find_text = data.get("find", "")
        replace_text = data.get("replace", "")
        use_regex = data.get("use_regex", False)

        try:
            content = file_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return ToolResponse.error(f"File not found: {file_path}")

        if use_regex:
            new_content, count = re.subn(find_text, replace_text, content)
            if count == 0:
                return ToolResponse.error(f"Regex pattern not found in {file_path}")
        else:
            count = content.count(find_text)
            if count == 0:
                return ToolResponse.error(
                    f"Text not found in {file_path}. "
                    "Ensure exact match including whitespace and line endings."
                )
            new_content = content.replace(find_text, replace_text)

        file_path.write_text(new_content, encoding="utf-8")
        return ToolResponse.json_response({
            "success": True,
            "path": str(file_path),
            "occurrences": count,
        })


class GlobTool(BaseTool):
    """Find files by glob pattern."""

    def info(self) -> ToolInfo:
        return ToolInfo(
            name="glob_pattern",
            description=(
                "Fast file pattern matching. Returns matching file paths.\n"
                "Supports glob patterns like **/*.py, src/**/*.ts, etc.\n"
                "Use this to discover project structure before reading files."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Glob pattern to match."},
                    "path": {
                        "type": "string",
                        "description": "Directory to search in. Default: working directory.",
                        "default": ".",
                    },
                },
                "required": ["pattern"],
            },
            required=["pattern"],
        )

    async def run(self, ctx: ToolContext, params: ToolCall) -> ToolResponse:
        try:
            data = json.loads(params.input) if isinstance(params.input, str) else params.input
        except (json.JSONDecodeError, TypeError):
            return ToolResponse.error(f"Invalid JSON parameters: {params.input}")

        pattern = data.get("pattern", "*")
        base_path = Path(data.get("path", ctx.working_dir))
        if not base_path.is_absolute():
            base_path = Path(ctx.working_dir) / base_path

        matches = sorted(str(p.relative_to(base_path)) for p in base_path.glob(pattern) if p.is_file())

        if len(matches) > 100:
            matches = matches[:100]
            suffix = f"\n\n(Showing first 100 of {len(matches)} matches)"
        else:
            suffix = f"\n(Total: {len(matches)} matches)"

        return ToolResponse.text("\n".join(matches) + suffix if matches else "No matches found.")


class GrepTool(BaseTool):
    """Search file contents using regex or literal text."""

    def info(self) -> ToolInfo:
        return ToolInfo(
            name="search_files",
            description=(
                "Search file contents using regex or literal text match.\n"
                "Returns matching lines with file paths and line numbers.\n"
                "For iterative exploration, consider using the Agent tool instead.\n"
                "Set literal=true when searching for exact text with special characters."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Regex or literal pattern to search."},
                    "path": {"type": "string", "description": "Directory to search. Default: working dir."},
                    "include": {
                        "type": "string",
                        "description": "File filter (glob), e.g., '*.py', '*.{ts,tsx}'",
                    },
                    "literal": {
                        "type": "boolean",
                        "description": "Use literal text instead of regex. Default: false.",
                        "default": False,
                    },
                },
                "required": ["pattern"],
            },
            required=["pattern"],
        )

    async def run(self, ctx: ToolContext, params: ToolCall) -> ToolResponse:
        try:
            data = json.loads(params.input) if isinstance(params.input, str) else params.input
        except (json.JSONDecodeError, TypeError):
            return ToolResponse.error(f"Invalid JSON parameters: {params.input}")

        pattern = data.get("pattern", "")
        search_path = Path(data.get("path", ctx.working_dir))
        if not search_path.is_absolute():
            search_path = Path(ctx.working_dir) / search_path
        include = data.get("include", "")
        literal = data.get("literal", False)

        regex = re.compile(pattern, re.IGNORECASE) if not literal else None

        results: list[str] = []
        max_results = 200
        count = 0

        for root, dirs, files in os.walk(search_path):
            # Skip hidden and common ignored dirs
            dirs[:] = [d for d in dirs if not d.startswith((".", "__pycache__", "node_modules", ".git"))]

            for fname in files:
                if include and not fnmatch.fnmatch(fname, include):
                    continue
                if not include and fname.startswith("."):
                    continue

                fpath = Path(root) / fname
                try:
                    content = fpath.read_text(encoding="utf-8", errors="ignore")
                except (PermissionError, OSError):
                    continue

                for line_num, line in enumerate(content.splitlines(), 1):
                    match = (pattern in line) if literal else (regex.search(line) if regex else False)
                    if match:
                        rel = fpath.relative_to(search_path)
                        results.append(f"{rel}:{line_num}: {line.strip()}")
                        count += 1
                        if count >= max_results:
                            break
                if count >= max_results:
                    break
            if count >= max_results:
                break

        suffix = f"\n\n(Showing {len(results)} results)" if len(results) >= max_results else f"\n(Total: {len(results)} results)"
        return ToolResponse.text("\n".join(results) + suffix if results else "No matches found.")


class ListDirectoryTool(BaseTool):
    """List directory contents."""

    def info(self) -> ToolInfo:
        return ToolInfo(
            name="list_directory",
            description=(
                "List files and subdirectories in a given path.\n"
                "Use Glob for pattern-based file finding.\n"
                "Use Grep for searching file contents."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directory path. Default: working dir."},
                },
            },
        )

    async def run(self, ctx: ToolContext, params: ToolCall) -> ToolResponse:
        try:
            data = json.loads(params.input) if isinstance(params.input, str) else params.input
        except (json.JSONDecodeError, TypeError):
            return ToolResponse.error(f"Invalid JSON parameters: {params.input}")

        dir_path = Path(data.get("path", ctx.working_dir))
        if not dir_path.is_absolute():
            dir_path = Path(ctx.working_dir) / dir_path

        if not dir_path.exists():
            return ToolResponse.error(f"Directory not found: {dir_path}")
        if not dir_path.is_dir():
            return ToolResponse.error(f"Not a directory: {dir_path}")

        entries: list[str] = []
        try:
            for item in sorted(dir_path.iterdir()):
                suffix = "/" if item.is_dir() else ""
                entries.append(f"  {item.name}{suffix}")
        except PermissionError:
            return ToolResponse.error(f"Permission denied: {dir_path}")

        return ToolResponse.text(f"{dir_path}/\n" + "\n".join(entries))


def get_file_tools() -> list[BaseTool]:
    """Return all file operation tools."""
    return [
        ReadFileTool(),
        WriteFileTool(),
        EditFileTool(),
        GlobTool(),
        GrepTool(),
        ListDirectoryTool(),
    ]