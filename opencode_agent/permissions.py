"""Permission system for tool execution.

Implements a grant/deny model with optional persistent grants.
Tools check permissions before executing sensitive operations.
The TUI (or CLI) layer handles the actual user prompt.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from opencode_agent.base_types import (
    PermissionAction,
    PermissionDecision,
    PermissionRequest,
)
from opencode_agent.pubsub import Broker, get_broker

logger = logging.getLogger("opencode_agent.permissions")


class PermissionService:
    """Manages tool execution permissions.

    Supports:
    - Per-session persistent grants (remember user's choice)
    - Auto-approve list from config (for safe tools like read/glob/ls)
    - Event-based approval flow (publishes request → UI prompts user → receives decision)
    """

    def __init__(self, auto_approve: set[str] | None = None) -> None:
        self._auto_approve: set[str] = auto_approve or set()
        self._persistent_grants: dict[str, set[str]] = {}  # session_id -> {tool_action_key}
        self._pending: dict[str, asyncio.Future[PermissionDecision]] = {}
        self._broker: Broker[PermissionRequest] = get_broker()  # type: ignore[assignment]

    def is_auto_approved(self, tool_name: str, action: PermissionAction) -> bool:
        """Check if this tool/action is in the auto-approve allowlist."""
        key = f"{tool_name}:{action.value}"
        return key in self._auto_approve or tool_name in self._auto_approve

    def is_persistently_granted(self, session_id: str, tool_name: str, action: PermissionAction) -> bool:
        """Check if the user has already granted this permission persistently."""
        key = f"{tool_name}:{action.value}"
        return session_id in self._persistent_grants and key in self._persistent_grants[session_id]

    async def request(
        self,
        req: PermissionRequest,
        session_id: str = "",
    ) -> bool:
        """Request permission from the user.

        Returns True if granted, False if denied.
        If auto-approved or persistently granted, returns immediately.
        Otherwise publishes a PermissionRequest event and waits for a response.
        """
        # Fast path: auto-approve
        if self.is_auto_approved(req.tool_name, req.action):
            logger.debug("Auto-approved: %s:%s", req.tool_name, req.action)
            return True

        # Fast path: persistent grant
        if session_id and self.is_persistently_granted(session_id, req.tool_name, req.action):
            logger.debug("Persistent grant: %s:%s (session=%s)", req.tool_name, req.action, session_id)
            return True

        # Publish request and wait for response
        future: asyncio.Future[PermissionDecision] = asyncio.get_event_loop().create_future()
        request_id = f"{session_id}:{req.tool_name}:{req.action.value}:{id(req)}"
        self._pending[request_id] = future

        try:
            await self._broker.publish(req)

            # Wait for decision with timeout (default 5 minutes)
            decision = await asyncio.wait_for(future, timeout=300.0)
            if decision == PermissionDecision.GRANT_PERSISTENT:
                self._add_persistent_grant(session_id, req.tool_name, req.action)
            return decision != PermissionDecision.DENY
        except asyncio.TimeoutError:
            logger.warning("Permission request timed out: %s", req.tool_name)
            return False
        finally:
            self._pending.pop(request_id, None)

    def grant(self, request_id: str, decision: PermissionDecision) -> bool:
        """Called by the UI layer to respond to a pending permission request."""
        future = self._pending.get(request_id)
        if future is None or future.done():
            return False
        future.set_result(decision)
        return True

    def grant_persistent(self, req: PermissionRequest, session_id: str = "") -> None:
        """Persistently grant a permission (without user prompt)."""
        self._add_persistent_grant(session_id, req.tool_name, req.action)

    def deny(self, req: PermissionRequest) -> None:
        """Deny a specific permission request."""
        # Find and reject any matching pending request
        for rid, future in list(self._pending.items()):
            if not future.done():
                # Simple match by tool name + action
                if req.tool_name in rid and req.action.value in rid:
                    future.set_result(PermissionDecision.DENY)

    def clear_session(self, session_id: str) -> None:
        """Clear all persistent grants for a session."""
        self._persistent_grants.pop(session_id, None)

    def _add_persistent_grant(self, session_id: str, tool_name: str, action: PermissionAction) -> None:
        if session_id not in self._persistent_grants:
            self._persistent_grants[session_id] = set()
        self._persistent_grants[session_id].add(f"{tool_name}:{action.value}")