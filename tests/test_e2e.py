"""
OpenCode Agent — Full E2E Test Suite.
No mocks. Real tools, real LLM, real SQLite.
"""
import os
os.environ["PYTHONIOENCODING"] = "utf-8"

import asyncio
import json
import time
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path("D:/AI_Agent")
API_KEY = PROJECT_ROOT.joinpath("LLM_key.txt").read_text().strip()
GLM_BASE_URL = "https://open.bigmodel.cn/api/paas/v4/"
GLM_MODEL = "glm-4-flash"

# ---------------------------------------------------------------------------
# Helper: create GLM provider
# ---------------------------------------------------------------------------

def _glm_provider(**overrides):
    from opencode_agent.provider.openai_provider import OpenAIProvider
    defaults = dict(model=GLM_MODEL, api_key=API_KEY, base_url=GLM_BASE_URL,
                    max_tokens=256, temperature=0.0)
    defaults.update(overrides)
    return OpenAIProvider(**defaults)


def _glm_provider_long(**overrides):
    from opencode_agent.provider.openai_provider import OpenAIProvider
    defaults = dict(model=GLM_MODEL, api_key=API_KEY, base_url=GLM_BASE_URL,
                    max_tokens=1024, temperature=0.0)
    defaults.update(overrides)
    return OpenAIProvider(**defaults)


async def _collect_events(stream):
    """Drain an async iterator of AgentEvents into a list."""
    events = []
    async for ev in stream:
        events.append(ev)
    return events


# ===================================================================
# T1: File Tools
# ===================================================================

class TestT1FileTools:
    """T1: File operation tools — real disk I/O."""

    async def _run_tool(self, tool, params: dict, working_dir: str = str(PROJECT_ROOT)):
        from opencode_agent.base_types import ToolCall
        from opencode_agent.tools.base import ToolContext
        ctx = ToolContext(working_dir=working_dir, permissions=None)
        tc = ToolCall(id="test-1", name=tool.info().name, input=json.dumps(params))
        return await tool.run(ctx, tc)

    @pytest.mark.asyncio
    async def test_t1_1_read_file_normal(self):
        """T1.1 read_file — normal read."""
        from opencode_agent.tools.file_tools import ReadFileTool, WriteFileTool
        # Setup: write a known file
        wf = WriteFileTool()
        td = str(PROJECT_ROOT / "tests" / "_tmp")
        (Path(td) / "test_read.txt").parent.mkdir(parents=True, exist_ok=True)
        await self._run_tool(wf, {"path": str(Path(td) / "test_read.txt"), "content": "line1\nline2\nline3"}, td)
        # Read back
        rf = ReadFileTool()
        res = await self._run_tool(rf, {"path": str(Path(td) / "test_read.txt")}, td)
        assert res.is_error is False, f"Unexpected error: {res.content}"
        assert "line1" in res.content
        assert "1: line1" in res.content  # line numbers
        print("  PASS")

    @pytest.mark.asyncio
    async def test_t1_2_read_file_pagination(self):
        """T1.2 read_file — offset + limit pagination."""
        from opencode_agent.tools.file_tools import ReadFileTool, WriteFileTool
        td = str(PROJECT_ROOT / "tests" / "_tmp")
        lines = "\n".join(f"line_{i}" for i in range(1, 21))
        await self._run_tool(WriteFileTool(), {"path": str(Path(td) / "paginate.txt"), "content": lines}, td)
        res = await self._run_tool(ReadFileTool(), {"path": str(Path(td) / "paginate.txt"), "offset": 5, "limit": 10}, td)
        assert res.is_error is False
        assert "5: line_5" in res.content
        assert "14: line_14" in res.content
        assert "15:" not in res.content  # beyond limit
        print("  PASS")

    @pytest.mark.asyncio
    async def test_t1_3_read_file_not_found(self):
        """T1.3 read_file — file not found."""
        from opencode_agent.tools.file_tools import ReadFileTool
        res = await self._run_tool(ReadFileTool(), {"path": "nonexistent_file_xyz.txt"})
        assert res.is_error is True
        assert "not found" in res.content.lower()
        print("  PASS")

    @pytest.mark.asyncio
    async def test_t1_4_write_file_creates_parents(self):
        """T1.4 write_file — creates parent directories."""
        from opencode_agent.tools.file_tools import WriteFileTool
        td = str(PROJECT_ROOT / "tests" / "_tmp")
        target = str(Path(td) / "nested" / "dir" / "file.txt")
        res = await self._run_tool(WriteFileTool(), {"path": target, "content": "hello"})
        assert res.is_error is False
        assert Path(target).exists()
        assert Path(target).read_text() == "hello"
        print("  PASS")

    @pytest.mark.asyncio
    async def test_t1_5_edit_file_exact_replace(self):
        """T1.5 edit_file — exact text replacement."""
        from opencode_agent.tools.file_tools import EditFileTool, WriteFileTool
        from opencode_agent.base_types import ToolCall
        from opencode_agent.tools.base import ToolContext
        td = str(PROJECT_ROOT / "tests" / "_tmp")
        target = str(Path(td) / "edit_me.txt")
        await self._run_tool(WriteFileTool(), {"path": target, "content": "hello world foo bar"})
        et = EditFileTool()
        ctx = ToolContext(working_dir=td, permissions=None)
        tc = ToolCall(id="t1-5", name="edit_file", input=json.dumps({
            "path": str(Path(td) / "edit_me.txt"), "find": "foo", "replace": "baz"
        }))
        res = await et.run(ctx, tc)
        assert res.is_error is False
        data = json.loads(res.content)
        assert data["occurrences"] == 1
        assert Path(target).read_text() == "hello world baz bar"
        print("  PASS")

    @pytest.mark.asyncio
    async def test_t1_6_glob_search_ls_combined(self):
        """T1.6 glob_pattern + search_files + list_directory."""
        from opencode_agent.tools.file_tools import GlobTool, GrepTool, ListDirectoryTool, WriteFileTool
        td = str(PROJECT_ROOT / "tests" / "_tmp" / "globtest")
        Path(td).mkdir(parents=True, exist_ok=True)
        for name in ["a.py", "b.py", "c.py"]:
            (Path(td) / name).write_text(f"# {name}\nimport os\nimport sys\n")
        for name in ["d.txt", "e.txt"]:
            (Path(td) / name).write_text("plain text")

        # glob
        gt = GlobTool()
        res = await self._run_tool(gt, {"pattern": "**/*.py", "path": td}, td)
        assert res.is_error is False
        assert "a.py" in res.content and "c.py" in res.content
        assert "d.txt" not in res.content

        # search
        st = GrepTool()
        res = await self._run_tool(st, {"pattern": "import", "path": td, "include": "*.py"}, td)
        assert res.is_error is False
        assert "a.py" in res.content

        # list_directory
        lt = ListDirectoryTool()
        res = await self._run_tool(lt, {"path": str(Path(td).parent)}, td)
        assert res.is_error is False
        assert "globtest" in res.content
        print("  PASS")


# ===================================================================
# T2: Bash Tool
# ===================================================================

class TestT2BashTool:
    """T2: Bash command execution — real processes."""

    @pytest.mark.asyncio
    async def test_t2_1_normal_execution(self):
        """T2.1 bash_command — normal execution."""
        from opencode_agent.tools.bash_tool import BashTool
        from opencode_agent.base_types import ToolCall
        from opencode_agent.tools.base import ToolContext
        import sys
        tool = BashTool()
        if sys.platform == "win32":
            cmd = "Write-Output 'hello'"
        else:
            cmd = "echo hello"
        ctx = ToolContext(working_dir=str(PROJECT_ROOT), permissions=None)
        tc = ToolCall(id="t2-1", name="bash_command", input=json.dumps({"command": cmd}))
        res = await tool.run(ctx, tc)
        assert res.is_error is False
        data = json.loads(res.content)
        assert data["exit_code"] == 0
        assert "hello" in data["stdout"]
        print("  PASS")

    @pytest.mark.asyncio
    async def test_t2_2_timeout(self):
        """T2.2 bash_command — command timeout."""
        from opencode_agent.tools.bash_tool import BashTool
        from opencode_agent.base_types import ToolCall
        from opencode_agent.tools.base import ToolContext
        import sys
        tool = BashTool()
        if sys.platform == "win32":
            cmd = "Start-Sleep -Seconds 10"
        else:
            cmd = "sleep 10"
        ctx = ToolContext(working_dir=str(PROJECT_ROOT), permissions=None)
        tc = ToolCall(id="t2-2", name="bash_command", input=json.dumps({"command": cmd, "timeout": 1000}))
        res = await tool.run(ctx, tc)
        assert res.is_error is True
        assert "timed out" in res.content.lower()
        print("  PASS")

    @pytest.mark.asyncio
    async def test_t2_3_dangerous_command_blocked(self):
        """T2.3 bash_command — dangerous command interception."""
        from opencode_agent.tools.bash_tool import BashTool
        from opencode_agent.base_types import ToolCall
        from opencode_agent.tools.base import ToolContext
        tool = BashTool()
        ctx = ToolContext(working_dir=str(PROJECT_ROOT), permissions=None)
        tc = ToolCall(id="t2-3", name="bash_command", input=json.dumps({"command": "rm -rf /"}))
        res = await tool.run(ctx, tc)
        assert res.is_error is True
        assert "DANGEROUS" in res.content
        print("  PASS")


# ===================================================================
# T3: Web Tools
# ===================================================================

class TestT3WebTools:
    """T3: Web fetch and search — real HTTP."""

    @pytest.mark.asyncio
    @pytest.mark.timeout(30)
    async def test_t3_1_web_fetch(self):
        """T3.1 web_fetch — fetch real URL."""
        from opencode_agent.tools.web_tools import WebFetchTool
        from opencode_agent.base_types import ToolCall
        from opencode_agent.tools.base import ToolContext
        tool = WebFetchTool()
        ctx = ToolContext(working_dir=str(PROJECT_ROOT), permissions=None)
        tc = ToolCall(id="t3-1", name="web_fetch", input=json.dumps({
            "url": "https://httpbin.org/get", "timeout": 15
        }))
        res = await tool.run(ctx, tc)
        assert res.is_error is False, f"Fetch failed: {res.content}"
        data = json.loads(res.content)
        assert data["success"] is True
        assert len(data["content"]) > 0
        print("  PASS")

    @pytest.mark.asyncio
    @pytest.mark.timeout(30)
    async def test_t3_2_web_search(self):
        """T3.2 web_search — best-effort."""
        from opencode_agent.tools.web_tools import WebSearchTool
        from opencode_agent.base_types import ToolCall
        from opencode_agent.tools.base import ToolContext
        tool = WebSearchTool()
        ctx = ToolContext(working_dir=str(PROJECT_ROOT), permissions=None)
        tc = ToolCall(id="t3-2", name="web_search", input=json.dumps({"query": "python"}))
        res = await tool.run(ctx, tc)
        # Either success or graceful failure
        if res.is_error:
            assert len(res.content) > 0  # meaningful error
        else:
            assert len(res.content) > 10
        print("  PASS" if not res.is_error else "  PASS (graceful degradation)")


# ===================================================================
# T4: Git Tools
# ===================================================================

class TestT4GitTools:
    """T4: Git operations — real git."""

    @pytest.mark.asyncio
    async def test_t4_1_non_repo_dir(self):
        """T4.1 git_status — non-repo directory returns error."""
        import tempfile
        from opencode_agent.tools.git_tools import GitStatusTool
        from opencode_agent.base_types import ToolCall
        from opencode_agent.tools.base import ToolContext
        tool = GitStatusTool()
        # Use system temp dir to ensure we are outside any git repo
        with tempfile.TemporaryDirectory() as tmp:
            ctx = ToolContext(working_dir=tmp, permissions=None)
            tc = ToolCall(id="t4-1", name="git_status", input="{}")
            res = await tool.run(ctx, tc)
            assert res.is_error is True
            print("  PASS")

    @pytest.mark.asyncio
    @pytest.mark.skipif(
        not Path(PROJECT_ROOT / ".git").is_dir(),
        reason="Not in a git repository"
    )
    async def test_t4_2_project_dir(self):
        """T4.2 git_status — project directory succeeds."""
        from opencode_agent.tools.git_tools import GitStatusTool
        from opencode_agent.base_types import ToolCall
        from opencode_agent.tools.base import ToolContext
        tool = GitStatusTool()
        ctx = ToolContext(working_dir=str(PROJECT_ROOT), permissions=None)
        tc = ToolCall(id="t4-2", name="git_status", input="{}")
        res = await tool.run(ctx, tc)
        assert res.is_error is False, f"git status failed: {res.content}"
        print("  PASS")


# ===================================================================
# T5: Provider — Real LLM Calls
# ===================================================================

class TestT5Provider:
    """T5: Provider layer — real GLM API calls."""

    @pytest.mark.asyncio
    @pytest.mark.timeout(60)
    async def test_t5_1_stream_text(self):
        """T5.1 OpenAI Provider — streaming text."""
        from opencode_agent.provider.base import ProviderMessage
        provider = _glm_provider(max_tokens=64)
        events = await _collect_events(provider.chat(
            messages=[ProviderMessage(role="user", content="Reply with exactly: TEST_OK")],
            stream=True,
        ))
        responses = [e for e in events if e.type.value == "response"]
        assert len(responses) > 0, "No RESPONSE events"
        full_text = "".join(e.content for e in responses)
        assert len(full_text) > 0, "Empty response text"
        dones = [e for e in events if e.type.value == "done"]
        assert len(dones) > 0, "No DONE event"
        print(f"  PASS (response: {full_text[:60]}...)")

    @pytest.mark.asyncio
    @pytest.mark.timeout(60)
    async def test_t5_2_stream_with_tools(self):
        """T5.2 OpenAI Provider — streaming with tool calls."""
        from opencode_agent.provider.base import ProviderMessage, ProviderTool
        provider = _glm_provider(max_tokens=256)
        tools = [ProviderTool(
            name="read_file",
            description="Read a file from disk",
            parameters={"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
        )]
        sys_prompt = "You must call the read_file tool with path 'config.py'. Do not explain, just call the tool."
        events = await _collect_events(provider.chat(
            messages=[ProviderMessage(role="user", content="Please read config.py")],
            tools=tools,
            system_prompt=sys_prompt,
            stream=True,
        ))
        tool_calls = [e for e in events if e.type.value == "tool_call"]
        # Tool calls may or may not appear depending on model behavior
        has_text = any(e.type.value == "response" for e in events)
        has_done = any(e.type.value == "done" for e in events)
        assert has_text or len(tool_calls) > 0, "No text or tool calls in response"
        assert has_done, "No DONE event"
        if tool_calls:
            assert tool_calls[0].tool_name == "read_file", f"Unexpected tool: {tool_calls[0].tool_name}"
        print(f"  PASS (tool_calls: {len(tool_calls)}, text: {has_text})")

    @pytest.mark.asyncio
    @pytest.mark.timeout(60)
    async def test_t5_3_non_stream(self):
        """T5.3 OpenAI Provider — non-streaming."""
        from opencode_agent.provider.base import ProviderMessage
        provider = _glm_provider(max_tokens=64)
        events = await _collect_events(provider.chat(
            messages=[ProviderMessage(role="user", content="Say OK")],
            stream=False,
        ))
        responses = [e for e in events if e.type.value == "response"]
        assert len(responses) > 0, "No RESPONSE events in non-stream mode"
        text = "".join(e.content for e in responses)
        assert len(text) > 0
        print(f"  PASS (response: {text[:40]})")


# ===================================================================
# T6: Prompt Engine
# ===================================================================

class TestT6PromptEngine:
    """T6: Prompt engine — SYSTEM_PROMPT.md loading and context injection."""

    @pytest.mark.asyncio
    async def test_t6_1_load_system_prompt(self):
        """T6.1 System prompt loads and has runtime context."""
        from opencode_agent.agent.prompt import get_agent_prompt
        from opencode_agent.config import AgentName, init_config
        init_config(working_dir=PROJECT_ROOT)
        prompt = get_agent_prompt(AgentName.CODER, tools_summary="- read_file: read stuff")
        assert len(prompt) > 5000, f"Prompt too short: {len(prompt)} chars"
        assert "Working directory" in prompt
        assert "Available Tools" in prompt
        assert "read_file" in prompt
        print(f"  PASS ({len(prompt)} chars)")

    @pytest.mark.asyncio
    async def test_t6_2_agent_type_different_prefixes(self):
        """T6.2 Different agent types produce different prefixes."""
        from opencode_agent.agent.prompt import get_agent_prompt
        from opencode_agent.config import AgentName, init_config
        init_config(working_dir=PROJECT_ROOT)
        coder = get_agent_prompt(AgentName.CODER)
        task = get_agent_prompt(AgentName.TASK)
        assert "read/write" in coder, "CODER prompt missing 'read/write'"
        assert "READ-ONLY" in task, "TASK prompt missing 'READ-ONLY'"
        print("  PASS")

    @pytest.mark.asyncio
    async def test_t6_3_tools_description_format(self):
        """T6.3 tools_description formats correctly."""
        from opencode_agent.agent.prompt import get_tools_description
        from opencode_agent.tools.file_tools import ReadFileTool
        desc = get_tools_description([ReadFileTool()])
        assert "read_file" in desc
        assert "Read" in desc  # from description
        assert "path" in desc   # from required params
        print("  PASS")


# ===================================================================
# T7: Agent Loop — Real End-to-End
# ===================================================================

class TestT7AgentLoop:
    """T7: Agent Loop — real LLM + real tools. The critical tests."""

    @pytest.mark.asyncio
    @pytest.mark.timeout(60)
    async def test_t7_1_simple_conversation(self):
        """T7.1 Simple conversation (no tool call expected)."""
        from opencode_agent.agent.loop import AgentLoop
        from opencode_agent.tools.file_tools import ReadFileTool
        from opencode_agent.config import AgentName
        loop = AgentLoop(
            provider=_glm_provider(max_tokens=128),
            tools=[ReadFileTool()],
            agent_name=AgentName.CODER,
        )
        events = await _collect_events(loop.run("Reply with exactly: LOOP_TEST_PASS"))
        responses = [e for e in events if e.type.value == "response"]
        assert len(responses) > 0, "No responses"
        full = "".join(e.content for e in responses)
        assert "LOOP_TEST_PASS" in full, f"Expected 'LOOP_TEST_PASS' in: {full[:200]}"
        dones = [e for e in events if e.type.value == "done"]
        assert len(dones) > 0
        assert len(loop.history) >= 2  # user + assistant
        print(f"  PASS (response: {full[:80]}...)")

    @pytest.mark.asyncio
    @pytest.mark.timeout(90)
    async def test_t7_2_tool_call_chain(self):
        """T7.2 Tool call chain — LLM calls read_file tool."""
        from opencode_agent.agent.loop import AgentLoop
        from opencode_agent.tools.file_tools import ReadFileTool
        from opencode_agent.config import AgentName
        loop = AgentLoop(
            provider=_glm_provider_long(max_tokens=512),
            tools=[ReadFileTool()],
            agent_name=AgentName.CODER,
        )
        events = await _collect_events(loop.run(
            "Please use the read_file tool to read the file SYSTEM_PROMPT.md (just the first 5 lines)."
        ))
        progress = [e for e in events if e.type.value == "progress"]
        tool_results = [e for e in events if e.type.value == "tool_result"]
        dones = [e for e in events if e.type.value == "done"]

        # Agent loop internally collects tool calls from the LLM and executes them.
        # Externally, it emits PROGRESS events before execution and TOOL_RESULT after.
        assert len(progress) > 0, "Expected PROGRESS event (tool dispatch)"
        assert progress[0].tool_name == "read_file", f"Unexpected tool in progress: {progress[0].tool_name}"
        assert len(tool_results) > 0, "Expected TOOL_RESULT event"
        assert tool_results[0].data.get("is_error") is not True, "Tool result should not be an error"
        assert len(dones) > 0, "Expected DONE event"
        assert dones[0].content is not None and len(dones[0].content) > 0, "Empty final response"
        assert len(loop.history) >= 3, f"Expected >= 3 history messages, got {len(loop.history)}"
        print(f"  PASS (progress: {len(progress)}, results: {len(tool_results)}, history: {len(loop.history)} msgs)")

    @pytest.mark.asyncio
    @pytest.mark.timeout(90)
    async def test_t7_3_multi_turn_memory(self):
        """T7.3 Multi-turn conversation — memory persists."""
        from opencode_agent.agent.loop import AgentLoop
        from opencode_agent.tools.file_tools import ReadFileTool
        from opencode_agent.config import AgentName
        loop = AgentLoop(
            provider=_glm_provider(max_tokens=128),
            tools=[ReadFileTool()],
            agent_name=AgentName.CODER,
        )
        # Turn 1
        events1 = await _collect_events(loop.run("My name is TestUser. Remember it. Reply only: OK"))
        assert any(e.type.value == "done" for e in events1)

        # Turn 2
        events2 = await _collect_events(loop.run("What name did I just tell you? Reply with only the name."))
        responses2 = [e for e in events2 if e.type.value == "response"]
        full2 = "".join(e.content for e in responses2)
        assert "TestUser" in full2, f"Memory failed. Response: {full2[:200]}"
        print(f"  PASS (response: {full2[:80]}...)")


# ===================================================================
# T8: Session Management — SQLite
# ===================================================================

class TestT8Session:
    """T8: Session management — real SQLite."""

    @pytest.mark.asyncio
    async def test_t8_1_crud_lifecycle(self):
        """T8.1 CRUD lifecycle."""
        from opencode_agent.agent.session import SessionManager
        db_path = PROJECT_ROOT / "tests" / "_tmp" / "test_session.db"
        if db_path.exists():
            db_path.unlink()
        sm = SessionManager(db_path)
        await sm.init()
        try:
            # Create
            s = await sm.create_session("test-crud")
            assert s.title == "test-crud"
            assert len(s.id) > 0

            # Get
            s2 = await sm.get_session(s.id)
            assert s2 is not None
            assert s2.title == "test-crud"

            # Update
            await sm.update_session(s.id, title="updated-title")
            s3 = await sm.get_session(s.id)
            assert s3.title == "updated-title"

            # Delete
            await sm.delete_session(s.id)
            s4 = await sm.get_session(s.id)
            assert s4 is None
            print("  PASS")
        finally:
            await sm.close()

    @pytest.mark.asyncio
    async def test_t8_2_message_persistence(self):
        """T8.2 Messages persist and restore correctly."""
        from opencode_agent.agent.session import SessionManager
        from opencode_agent.base_types import Message, MessageRole, TextContent, TokenUsage
        db_path = PROJECT_ROOT / "tests" / "_tmp" / "test_msg.db"
        if db_path.exists():
            db_path.unlink()
        sm = SessionManager(db_path)
        await sm.init()
        try:
            s = await sm.create_session("msg-test")
            msg = Message(
                role=MessageRole.USER,
                parts=[TextContent(text="Hello from test")],
                model="test-model",
            )
            msg_id = await sm.save_message(s.id, msg)
            assert len(msg_id) > 0

            msgs = await sm.get_messages(s.id)
            assert len(msgs) == 1
            assert msgs[0].role == MessageRole.USER
            assert msgs[0].text == "Hello from test"
            assert msgs[0].model == "test-model"
            print("  PASS")
        finally:
            await sm.close()

    @pytest.mark.asyncio
    async def test_t8_3_session_list_ordering(self):
        """T8.3 Session list ordered by updated_at DESC."""
        from opencode_agent.agent.session import SessionManager
        db_path = PROJECT_ROOT / "tests" / "_tmp" / "test_list.db"
        if db_path.exists():
            db_path.unlink()
        sm = SessionManager(db_path)
        await sm.init()
        try:
            s1 = await sm.create_session("first")
            await asyncio.sleep(0.02)
            s2 = await sm.create_session("second")
            await asyncio.sleep(0.02)
            s3 = await sm.create_session("third")

            sessions = await sm.list_sessions()
            assert len(sessions) >= 3
            # Most recently updated first
            times = [s.updated_at for s in sessions]
            assert times == sorted(times, reverse=True), "Sessions not ordered by updated_at DESC"
            print("  PASS")
        finally:
            await sm.close()

# ===================================================================
# T9: Ollama Provider
# ===================================================================

class TestT9OllamaProvider:
    """T9: Ollama provider — construction, config, and management APIs."""

    def test_t9_1_provider_construction(self):
        """T9.1 OllamaProvider construction with host/port."""
        from opencode_agent.provider.ollama_provider import OllamaProvider
        provider = OllamaProvider(host="192.168.1.100", port=11434, model="llama3")
        assert provider.model == "llama3"
        assert provider.api_key == "ollama"
        assert provider.base_url == "http://192.168.1.100:11434/v1"
        assert provider.ollama_base == "http://192.168.1.100:11434"
        print("  PASS")

    def test_t9_2_host_normalization(self):
        """T9.2 OllamaProvider normalizes various host formats."""
        from opencode_agent.provider.ollama_provider import OllamaProvider

        # With protocol prefix
        p1 = OllamaProvider(host="http://10.0.0.5", port=8080, model="qwen2")
        assert p1.base_url == "http://10.0.0.5:8080/v1"

        # Plain IP
        p2 = OllamaProvider(host="127.0.0.1", port=11434, model="llama3")
        assert p2.base_url == "http://127.0.0.1:11434/v1"

        # Hostname with path stripped
        p3 = OllamaProvider(host="myserver.local/v1", port=11434, model="mistral")
        assert p3.base_url == "http://myserver.local:11434/v1"

        # Explicit base_url takes precedence
        p4 = OllamaProvider(host="localhost", port=9999, model="llama3",
                            base_url="http://custom:7777/v1")
        assert p4.base_url == "http://custom:7777/v1"
        print("  PASS")

    def test_t9_3_config_enum(self):
        """T9.3 ModelProvider.OLLAMA exists and config has defaults."""
        from opencode_agent.config import ModelProvider, get_config, ProviderConfig
        assert ModelProvider.OLLAMA.value == "ollama"

        cfg = get_config()
        ollama_cfg = cfg.providers.get(ModelProvider.OLLAMA)
        assert ollama_cfg is not None
        assert ollama_cfg.host == "localhost"
        assert ollama_cfg.port == 11434
        assert ollama_cfg.base_url == "http://localhost:11434/v1"
        print("  PASS")

    def test_t9_4_factory_creates_ollama(self):
        """T9.4 create_provider returns OllamaProvider for OLLAMA."""
        from opencode_agent.config import ModelProvider, init_config, AgentName, AgentConfig
        from opencode_agent.provider import create_provider, OllamaProvider
        init_config(
            default_provider=ModelProvider.OLLAMA,
            agents={AgentName.CODER: AgentConfig(model="llama3", max_tokens=4096)},
        )
        provider = create_provider("coder")
        assert isinstance(provider, OllamaProvider)
        assert provider.model == "llama3"
        print("  PASS")

    def test_t9_5_health_check_unreachable(self):
        """T9.5 health_check raises ConnectionError for unreachable server."""
        import asyncio
        from opencode_agent.provider.ollama_provider import OllamaProvider

        async def _run():
            # Use a non-routable IP to guarantee failure
            provider = OllamaProvider(host="192.0.2.1", port=11434, model="llama3")
            try:
                await provider.health_check()
                assert False, "Should have raised ConnectionError"
            except (ConnectionError, Exception) as e:
                # ConnectTimeout maps to httpx.ConnectTimeout, which is a subclass of Exception
                assert "connect" in type(e).__name__.lower() or "Cannot connect" in str(e), f"Unexpected error: {e}"
                print("  PASS")

        asyncio.run(_run())

