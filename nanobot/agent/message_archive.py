"""SQLite archive for compacted message storage and retrieval."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

from nanobot.config.schema import MessageArchiveConfig
from nanobot.utils.helpers import ensure_dir

_CREATE_TABLES = """
CREATE TABLE IF NOT EXISTS consolidated_ranges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL,
    start_idx INTEGER NOT NULL,
    end_idx INTEGER NOT NULL,
    summary_text TEXT,
    messages_count INTEGER,
    trigger_type TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS archived_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL,
    range_id INTEGER NOT NULL,
    msg_idx INTEGER NOT NULL,
    role TEXT NOT NULL,
    content TEXT,
    tool_calls TEXT,
    tool_call_id TEXT,
    name TEXT,
    timestamp TEXT,
    FOREIGN KEY (range_id) REFERENCES consolidated_ranges(id)
);

CREATE INDEX IF NOT EXISTS idx_archived_msg_conv ON archived_messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_archived_msg_range ON archived_messages(range_id);
"""


class MessageArchive:
    """Synchronous SQLite archive for compacted messages."""

    def __init__(self, workspace: Path, config: MessageArchiveConfig | None = None):
        self.config = config or MessageArchiveConfig()
        db_path = workspace / self.config.db_path
        ensure_dir(db_path.parent)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_CREATE_TABLES)
        self._conn.commit()

    def store_messages(
        self,
        conversation_id: str,
        messages: list[dict[str, Any]],
        summary_text: str = "(pending)",
        trigger_type: str = "auto",
        start_idx: int = 0,
    ) -> int:
        """Store a batch of messages. Returns the range_id."""
        now = datetime.now().isoformat()
        cursor = self._conn.execute(
            "INSERT INTO consolidated_ranges "
            "(conversation_id, start_idx, end_idx, summary_text, messages_count, trigger_type, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                conversation_id,
                start_idx,
                start_idx + len(messages) - 1,
                summary_text,
                len(messages),
                trigger_type,
                now,
            ),
        )
        range_id = cursor.lastrowid

        for i, msg in enumerate(messages):
            tool_calls = msg.get("tool_calls")
            self._conn.execute(
                "INSERT INTO archived_messages "
                "(conversation_id, range_id, msg_idx, role, content, tool_calls, tool_call_id, name, timestamp) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    conversation_id,
                    range_id,
                    start_idx + i,
                    msg.get("role", ""),
                    msg.get("content"),
                    json.dumps(tool_calls, ensure_ascii=False) if tool_calls else None,
                    msg.get("tool_call_id"),
                    msg.get("name"),
                    msg.get("timestamp"),
                ),
            )
        self._conn.commit()
        logger.debug("Archived {} messages as range #{}", len(messages), range_id)
        return range_id

    def update_summary(self, range_id: int, summary_text: str) -> None:
        self._conn.execute(
            "UPDATE consolidated_ranges SET summary_text = ? WHERE id = ?",
            (summary_text, range_id),
        )
        self._conn.commit()

    def search_by_keyword(
        self, conv_id: str, keyword: str, limit: int = 10
    ) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT range_id, msg_idx, role, substr(content, 1, 300) as preview "
            "FROM archived_messages "
            "WHERE conversation_id = ? AND content LIKE ? "
            "ORDER BY range_id DESC, msg_idx ASC LIMIT ?",
            (conv_id, f"%{keyword}%", limit),
        )
        return [dict(r) for r in rows]

    def get_range(self, range_id: int) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT id, conversation_id, start_idx, end_idx, summary_text, "
            "messages_count, trigger_type, created_at "
            "FROM consolidated_ranges WHERE id = ?",
            (range_id,),
        ).fetchone()
        if not row:
            return None
        msg_rows = self._conn.execute(
            "SELECT msg_idx, role, substr(content, 1, 100) as preview, name "
            "FROM archived_messages "
            "WHERE range_id = ? ORDER BY msg_idx ASC",
            (range_id,),
        ).fetchall()
        return {
            "summary": row["summary_text"],
            "trigger": row["trigger_type"],
            "messages_count": row["messages_count"],
            "created_at": row["created_at"],
            "messages": [dict(r) for r in msg_rows],
        }

    def close(self) -> None:
        self._conn.close()
