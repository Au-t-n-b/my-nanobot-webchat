"""Server-Sent Events framing for AGUI."""

from __future__ import annotations

import json


def format_sse(event: str, data: dict) -> bytes:
    """One SSE message: event line + single-line JSON data + blank line."""
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event}\ndata: {payload}\n\n".encode("utf-8")
