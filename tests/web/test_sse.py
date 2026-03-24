"""SSE framing unit tests."""

from nanobot.web.sse import format_sse


def test_format_sse_single_event() -> None:
    out = format_sse("RunStarted", {"threadId": "t", "runId": "r", "model": "m"})
    assert b"event: RunStarted\n" in out
    assert b'"threadId"' in out
    assert out.endswith(b"\n\n")
