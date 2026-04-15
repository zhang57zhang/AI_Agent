"""Session management with SQLite persistence."""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from opencode_agent.base_types import Message, MessageRole, Session

logger = logging.getLogger("opencode_agent.agent.session")

_CREATE_SESSIONS_TABLE = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL DEFAULT '',
    parent_id TEXT DEFAULT '',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    total_cost REAL DEFAULT 0,
    message_count INTEGER DEFAULT 0
);
"""

_CREATE_MESSAGES_TABLE = """
CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,
    parts_json TEXT NOT NULL DEFAULT '[]',
    model TEXT DEFAULT '',
    timestamp REAL NOT NULL,
    token_usage_json TEXT DEFAULT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);
"""


class SessionManager:
    """Manages conversation sessions with SQLite persistence."""

    def __init__(self, db_path: Path | str | None = None) -> None:
        self._db_path = Path(db_path) if db_path else None
        self._connection = None

    async def init(self) -> None:
        """Initialize the database and create tables."""
        if self._db_path is None:
            from opencode_agent.config import get_config
            cfg = get_config()
            self._db_path = cfg.sessions_db

        self._db_path.parent.mkdir(parents=True, exist_ok=True)

        import aiosqlite

        self._connection = await aiosqlite.connect(str(self._db_path))
        self._connection.row_factory = aiosqlite.Row

        await self._connection.executescript(_CREATE_SESSIONS_TABLE)
        await self._connection.executescript(_CREATE_MESSAGES_TABLE)
        await self._connection.commit()
        logger.info("Session database initialized: %s", self._db_path)

    async def close(self) -> None:
        if self._connection:
            await self._connection.close()
            self._connection = None

    def _ensure_connection(self) -> Any:
        if self._connection is None:
            raise RuntimeError("SessionManager not initialized. Call init() first.")
        return self._connection

    # --- Session CRUD ---

    async def create_session(self, title: str = "", parent_id: str = "") -> Session:
        session = Session(
            id=str(uuid.uuid4())[:12],
            title=title or "New Session",
            parent_id=parent_id,
            created_at=time.time(),
            updated_at=time.time(),
        )
        db = self._ensure_connection()
        await db.execute(
            "INSERT INTO sessions (id, title, parent_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (session.id, session.title, session.parent_id, session.created_at, session.updated_at),
        )
        await db.commit()
        return session

    async def get_session(self, session_id: str) -> Session | None:
        db = self._ensure_connection()
        cursor = await db.execute("SELECT * FROM sessions WHERE id = ?", (session_id,))
        row = await cursor.fetchone()
        if row is None:
            return None
        return Session(
            id=row["id"],
            title=row["title"],
            parent_id=row["parent_id"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            total_cost=row["total_cost"],
            message_count=row["message_count"],
        )

    async def list_sessions(self, limit: int = 50) -> list[Session]:
        db = self._ensure_connection()
        cursor = await db.execute(
            "SELECT * FROM sessions ORDER BY updated_at DESC LIMIT ?", (limit,)
        )
        rows = await cursor.fetchall()
        return [
            Session(
                id=row["id"],
                title=row["title"],
                parent_id=row["parent_id"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                total_cost=row["total_cost"],
                message_count=row["message_count"],
            )
            for row in rows
        ]

    async def update_session(self, session_id: str, **fields: Any) -> None:
        db = self._ensure_connection()
        valid = {"title", "total_cost", "message_count", "updated_at"}
        updates = {k: v for k, v in fields.items() if k in valid}
        if not updates:
            return
        updates["updated_at"] = time.time()
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [session_id]
        await db.execute(f"UPDATE sessions SET {set_clause} WHERE id = ?", values)
        await db.commit()

    async def delete_session(self, session_id: str) -> None:
        db = self._ensure_connection()
        await db.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
        await db.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        await db.commit()

    # --- Message persistence ---

    async def save_message(self, session_id: str, message: Message) -> str:
        msg_id = str(uuid.uuid4())[:12]
        parts_data = []

        for part in message.parts:
            if hasattr(part, "text"):
                parts_data.append({"type": "text", "text": part.text})
            elif hasattr(part, "tool_call"):
                tc = part.tool_call
                parts_data.append({
                    "type": "tool_call",
                    "id": tc.id,
                    "name": tc.name,
                    "input": tc.input,
                })

        usage_json = None
        if message.token_usage:
            usage_json = json.dumps(asdict(message.token_usage))

        db = self._ensure_connection()
        await db.execute(
            "INSERT INTO messages (id, session_id, role, parts_json, model, timestamp, token_usage_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (msg_id, session_id, message.role.value, json.dumps(parts_data),
             message.model, message.timestamp, usage_json),
        )
        await db.commit()

        # Update session stats
        await self.update_session(session_id, message_count=await self._count_messages(session_id))
        return msg_id

    async def get_messages(self, session_id: str, limit: int = 100) -> list[Message]:
        db = self._ensure_connection()
        cursor = await db.execute(
            "SELECT * FROM messages WHERE session_id = ? ORDER BY timestamp ASC LIMIT ?",
            (session_id, limit),
        )
        rows = await cursor.fetchall()

        messages: list[Message] = []
        for row in rows:
            parts = []
            for p in json.loads(row["parts_json"]):
                from opencode_agent.base_types import TextContent, ToolCall, ToolCallContent
                if p["type"] == "text":
                    parts.append(TextContent(text=p["text"]))
                elif p["type"] == "tool_call":
                    parts.append(ToolCallContent(tool_call=ToolCall(
                        id=p["id"], name=p["name"], input=p["input"]
                    )))

            usage = None
            if row["token_usage_json"]:
                data = json.loads(row["token_usage_json"])
                from opencode_agent.base_types import TokenUsage
                usage = TokenUsage(**data)

            messages.append(Message(
                role=MessageRole(row["role"]),
                parts=parts,
                model=row["model"],
                timestamp=row["timestamp"],
                token_usage=usage,
            ))
        return messages

    async def _count_messages(self, session_id: str) -> int:
        db = self._ensure_connection()
        cursor = await db.execute(
            "SELECT COUNT(*) as cnt FROM messages WHERE session_id = ?", (session_id,)
        )
        row = await cursor.fetchone()
        return row["cnt"] if row else 0