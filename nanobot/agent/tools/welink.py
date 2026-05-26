"""WeLINK XiaoLuban messaging tool."""

from __future__ import annotations

import os
import time
from collections import deque
from datetime import date
from typing import Any

from loguru import logger

from nanobot.agent.tools.base import Tool
from nanobot.config.schema import WelinkToolConfig

try:
    import requests
except ImportError:
    requests = None  # type: ignore[assignment]

try:
    from prettytable import PrettyTable
except ImportError:
    PrettyTable = None  # type: ignore[assignment,misc]


def _build_plain_table(headers: list[str], rows: list[list[str]]) -> str:
    """Simple fallback table when prettytable is not installed."""
    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            if i < len(col_widths):
                col_widths[i] = max(col_widths[i], len(str(cell)))
    sep = "+" + "+".join("-" * (w + 2) for w in col_widths) + "+"
    def fmt_row(cells: list[str]) -> str:
        parts = []
        for i, c in enumerate(cells):
            w = col_widths[i] if i < len(col_widths) else len(str(c))
            parts.append(f" {str(c).ljust(w)} ")
        return "|" + "|".join(parts) + "|"
    lines = [sep, fmt_row(headers), sep]
    for row in rows:
        lines.append(fmt_row([str(c) for c in row]))
    lines.append(sep)
    return "\n".join(lines)


def format_table(headers: list[str], rows: list[list[str]]) -> str:
    """Format table data with Consolas font wrapper for WeLINK rendering."""
    if PrettyTable is not None:
        tbl = PrettyTable(headers)
        for row in rows:
            tbl.add_row(row)
        raw = str(tbl)
    else:
        raw = _build_plain_table(headers, rows)
    return f'<span style="font-family:Consolas;font-weight:bold;">{raw}</span>'


class SendWelinkTool(Tool):
    """Agent tool: send message to WeLINK via XiaoLuban HTTP API."""

    def __init__(self, config: WelinkToolConfig):
        self._config = config
        self._send_timestamps: deque[float] = deque()
        self._daily_count: int = 0
        self._daily_date: date | None = None

    @property
    def name(self) -> str:
        return "send_welink"

    @property
    def description(self) -> str:
        return (
            "Send a message to WeLINK (XiaoLuban). "
            "Supports rich text via HTML span tags in content: "
            'color <span style="color:green;">green</span>, '
            'bold <span style="font-weight:bold;">bold</span>, '
            'combined <span style="color:red;font-weight:bold;">red bold</span>, '
            "and emoji (copy from https://emojixd.com/). "
            "Set format='table' with table_data to send a formatted table. "
            "Receiver can be a group ID or employee number. "
            "Avoid sending at peak hours (6:00, 9:00, 17:30) as message queues may be congested."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": (
                        "Message text. Supports HTML span tags for styling: "
                        'e.g. <span style="color:green;font-weight:bold;">PASS</span>'
                    ),
                },
                "receiver": {
                    "type": "string",
                    "description": "Receiver ID: WeLINK group ID or employee number",
                },
                "format": {
                    "type": "string",
                    "enum": ["text", "table"],
                    "description": "Message format. 'table' renders table_data as a formatted table.",
                },
                "table_data": {
                    "type": "object",
                    "description": (
                        "Table data when format='table'. "
                        "Object with 'headers' (array of strings) and 'rows' (array of arrays)."
                    ),
                    "properties": {
                        "headers": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "rows": {
                            "type": "array",
                            "items": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                        },
                    },
                    "required": ["headers", "rows"],
                },
            },
            "required": ["receiver"],
        }

    def _resolve_auth(self) -> str | None:
        env = (
            os.environ.get("XIAOLUBAN_AUTH")
            or os.environ.get("WELINK_XLB_AUTH")
            or ""
        ).strip()
        if env:
            return env
        return self._config.xiaoluban_auth.strip() or None

    def _check_rate_limit(self) -> tuple[bool, str]:
        now = time.monotonic()
        window = 60.0
        while self._send_timestamps and now - self._send_timestamps[0] > window:
            self._send_timestamps.popleft()
        if len(self._send_timestamps) >= self._config.rate_limit_per_minute:
            return False, (
                f"rate limit exceeded ({self._config.rate_limit_per_minute}/min). "
                "Please wait before sending again."
            )

        today = date.today()
        if self._daily_date != today:
            self._daily_date = today
            self._daily_count = 0
        if self._daily_count >= self._config.rate_limit_per_day:
            return False, (
                f"daily rate limit exceeded ({self._config.rate_limit_per_day}/day). "
                "Try again tomorrow."
            )

        return True, ""

    def _record_send(self) -> None:
        self._send_timestamps.append(time.monotonic())
        self._daily_count += 1

    async def execute(self, **kwargs: Any) -> str:
        content: str = kwargs.get("content", "").strip()
        receiver: str = kwargs.get("receiver", "").strip()
        fmt: str = kwargs.get("format", "text")
        table_data: dict | None = kwargs.get("table_data")

        if not receiver:
            return "Error: receiver is required."

        if fmt == "table":
            if not table_data or "headers" not in table_data or "rows" not in table_data:
                return "Error: table_data with 'headers' and 'rows' is required when format='table'."
            table_str = format_table(table_data["headers"], table_data["rows"])
            content = f"{content}\n{table_str}" if content else table_str
        elif not content:
            return "Error: message content is empty."

        if requests is None:
            return "Error: 'requests' package not installed. Run: pip install requests"

        auth = self._resolve_auth()
        if not auth:
            return (
                "Error: WeLINK auth not configured. "
                "Set environment variable XIAOLUBAN_AUTH or configure "
                "tools.welink.xiaolubanAuth in config.json."
            )

        ok, reason = self._check_rate_limit()
        if not ok:
            return f"Error: {reason}"

        url = self._config.xiaoluban_url.rstrip("/") + "/"
        data: dict[str, str] = {
            "content": content,
            "receiver": receiver,
            "auth": auth,
        }
        sender = (
            self._config.xiaoluban_sender.strip()
            or os.environ.get("XIAOLUBAN_SENDER", "").strip()
        )
        if sender:
            data["sender"] = sender

        try:
            resp = requests.post(url=url, json=data, timeout=30.0)
        except Exception as e:
            logger.error("send_welink request failed: {}", e)
            return f"Error: WeLINK request failed: {e}"

        if not resp.ok:
            logger.warning("send_welink HTTP {}: {}", resp.status_code, resp.text[:200])
            return f"Error: WeLINK returned HTTP {resp.status_code}: {resp.text[:200]}"

        self._record_send()
        table_note = " (with table)" if fmt == "table" else ""
        return f"Message sent to WeLINK receiver '{receiver}'{table_note}."
