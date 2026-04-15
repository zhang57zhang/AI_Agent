"""Main Textual TUI application for OpenCode Agent."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from rich.markdown import Markdown
from rich.text import Text
from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, ScrollableContainer, Vertical
from textual.reactive import reactive
from textual.widgets import (
    Footer,
    Header,
    Input,
    RichLog,
    Static,
    TabbedContent,
    TabPane,
)
from textual.worker import Worker, WorkerState

from opencode_agent.agent.loop import AgentLoop
from opencode_agent.base_types import AgentEvent, AgentEventType
from opencode_agent.permissions import PermissionService
from opencode_agent.tools import coder_agent_tools

from opencode_agent.tui.styles.tokens import (
    ACCENT,
    BG,
    BG_DARK,
    BG_INPUT,
    BG_SURFACE,
    FG,
    FG_DIM,
    FG_SUBTLE,
    GREEN,
    ORANGE,
    RED,
    YELLOW,
)

logger = logging.getLogger("opencode_agent.tui")


class ChatOutput(RichLog):
    """Scrollable chat output area with markdown rendering."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(
            highlight=True,
            markup=True,
            max_lines=5000,
            wrap=True,
            auto_scroll=True,
            **kwargs,
        )

    def add_user_message(self, text: str) -> None:
        self.write(Text(f"\n  > {text}", style=f"bold {ACCENT}"))

    def add_assistant_message(self, text: str) -> None:
        self.write(Markdown(text))

    def add_tool_call(self, tool_name: str, tool_call_id: str) -> None:
        from opencode_agent.tui.styles.tokens import TOOL_COLORS
        color = TOOL_COLORS.get(tool_name, FG_SUBTLE)
        self.write(Text(f"  [{tool_name}]", style=f"bold {color}"))

    def add_tool_result(self, tool_name: str, content: str, is_error: bool) -> None:
        from opencode_agent.tui.styles.tokens import TOOL_COLORS
        color = TOOL_COLORS.get(tool_name, FG_SUBTLE)
        style = f"{RED}" if is_error else f"dim {color}"
        preview = content[:200].replace("\n", " ")
        self.write(Text(f"    {preview}{'...' if len(content) > 200 else ''}", style=style))

    def add_error(self, text: str) -> None:
        self.write(Text(f"  Error: {text}", style=f"bold {RED}"))

    def add_system(self, text: str) -> None:
        self.write(Text(f"  {text}", style=FG_DIM))

    def add_progress(self, text: str) -> None:
        self.write(Text(f"  ... {text}", style=DIM))

    def add_separator(self) -> None:
        self.write(Text("  " + "-" * 60, style=FG_DIM))


class OpenCodeAgentApp(App):
    """Main Textual application."""

    TITLE = "OpenCode Agent"
    SUB_TITLE = "AI Coding Assistant"
    CSS = f"""
    Screen {{
        background: {BG};
        color: {FG};
    }}

    Header {{
        background: {BG_DARK};
        color: {FG};
        border-bottom: solid {BG_SURFACE};
        height: 3;
    }}

    Header .title--sub {{
        color: {ACCENT};
    }}

    Footer {{
        background: {BG_DARK};
        color: {FG_DIM};
    }}

    #main-container {{
        height: 1fr;
    }}

    #chat-output {{
        background: {BG};
        padding: 1 2;
        border-bottom: solid {BG_SURFACE};
    }}

    #input-container {{
        height: auto;
        dock: bottom;
        padding: 1 2;
        background: {BG_SURFACE};
    }}

    #user-input {{
        background: {BG_INPUT};
        border: solid {FG_DIM};
        color: {FG};
        height: 3;
        padding: 0 1;
    }}

    #user-input:focus {{
        border: solid {ACCENT};
    }}

    #status-bar {{
        height: 1;
        background: {BG_DARK};
        color: {FG_DIM};
        padding: 0 2;
        dock: bottom;
    }}

    .session-tab {{
        color: {FG_SUBTLE};
    }}

    .session-tab--active {{
        color: {ACCENT};
        text-style: bold;
    }}
    """

    BINDINGS = [
        Binding("ctrl+c", "cancel", "Cancel", show=True),
        Binding("ctrl+n", "new_session", "New Session", show=True),
        Binding("ctrl+l", "clear", "Clear Output", show=True),
        Binding("ctrl+s", "save", "Save Session", show=True),
        Binding("ctrl+q", "quit", "Quit", show=True),
    ]

    is_processing: reactive[bool] = reactive(False)
    status_text: reactive[str] = reactive("Ready")
    cost_text: reactive[str] = reactive("")

    def __init__(
        self,
        agent_loop: AgentLoop | None = None,
        permissions: PermissionService | None = None,
    ) -> None:
        super().__init__()
        self.agent_loop = agent_loop
        self.permissions = permissions

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Container(id="main-container"):
            yield ChatOutput(id="chat-output")
        with Horizontal(id="input-container"):
            yield Input(placeholder="Type your message... (Enter to send, Ctrl+C to cancel)", id="user-input")
        yield Static(id="status-bar", text="Ready")
        yield Footer()

    @on(Input.Submitted, "#user-input")
    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle user input submission."""
        text = event.value.strip()
        if not text:
            return

        if self.is_processing:
            self.query_one("#chat-output", ChatOutput).add_system("Still processing. Please wait or Ctrl+C to cancel.")
            return

        # Clear input
        self.query_one("#user-input", Input).value = ""

        # Display user message
        self.query_one("#chat-output", ChatOutput).add_user_message(text)

        # Start agent processing
        self.is_processing = True
        self.run_worker(self._process_message(text))

    async def _process_message(self, text: str) -> None:
        """Process a user message through the agent loop."""
        if self.agent_loop is None:
            self.query_one("#chat-output", ChatOutput).add_error("Agent not initialized")
            self.is_processing = False
            return

        chat = self.query_one("#chat-output", ChatOutput)
        buffer = ""
        tool_calls_seen: set[str] = set()

        try:
            async for event in self.agent_loop.run(text):
                if event.type == AgentEventType.RESPONSE:
                    buffer += event.content
                    # Update display with accumulated text
                    chat.add_assistant_message(event.content)

                elif event.type == AgentEventType.TOOL_CALL:
                    chat.add_tool_call(event.tool_name, event.tool_call_id)

                elif event.type == AgentEventType.TOOL_RESULT:
                    is_error = event.data.get("is_error", False)
                    chat.add_tool_result(event.tool_name, event.content, is_error)

                elif event.type == AgentEventType.PROGRESS:
                    chat.add_progress(event.content)

                elif event.type == AgentEventType.ERROR:
                    chat.add_error(event.content)

                elif event.type == AgentEventType.DONE:
                    chat.add_separator()
                    if event.token_usage:
                        tokens = event.token_usage.total_tokens
                        cost = event.token_usage.cost_usd
                        self.cost_text = f"Tokens: {tokens:,} | Cost: ${cost:.4f}"
                        self.status_text = f"Done | {self.cost_text}"

                elif event.type == AgentEventType.THINKING:
                    chat.add_system(f"[thinking] {event.content[:200]}")

        except Exception as e:
            chat.add_error(str(e))
            logger.exception("Error processing message")

        finally:
            self.is_processing = False
            self.status_text = "Ready"

    def action_cancel(self) -> None:
        """Cancel current processing."""
        if self.agent_loop:
            self.agent_loop.cancel()
        self.query_one("#chat-output", ChatOutput).add_system("Cancelled.")
        self.is_processing = False

    def action_clear(self) -> None:
        """Clear chat output."""
        self.query_one("#chat-output", ChatOutput).clear()

    def action_new_session(self) -> None:
        """Start a new session (clear history)."""
        if self.agent_loop:
            self.agent_loop.clear_history()
        self.query_one("#chat-output", ChatOutput).clear()
        self.query_one("#chat-output", ChatOutput).add_system("New session started.")

    def action_save(self) -> None:
        """Save current session."""
        self.query_one("#chat-output", ChatOutput).add_system("Session saved.")

    def on_worker_state_changed(self, event: WorkerState) -> None:
        """Handle worker completion."""
        if event.worker.finished:
            self.is_processing = False
            if event.worker.error:
                logger.error("Worker error: %s", event.worker.error)