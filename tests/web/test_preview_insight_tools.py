"""Capped filesystem tools for preview file insight."""

from __future__ import annotations

from pathlib import Path

import pytest

from nanobot.agent.tools.filesystem import ReadFileHeadTool, ReadFileTailTool, ReadHexDumpTool


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    (tmp_path / "a.txt").write_text("line1\nline2\nline3\n", encoding="utf-8")
    (tmp_path / "big.bin").write_bytes(b"\x00\x01\x02" * 300)
    return tmp_path


@pytest.mark.asyncio
async def test_read_file_head_clamps_lines(workspace: Path) -> None:
    t = ReadFileHeadTool(workspace=workspace, allowed_dir=workspace, extra_allowed_dirs=None)
    out = await t.execute("a.txt", lines=9999)
    assert "1|" in out and "line1" in out
    assert "(capped read:" in out


@pytest.mark.asyncio
async def test_read_file_tail_reads_end(workspace: Path) -> None:
    t = ReadFileTailTool(workspace=workspace, allowed_dir=workspace, extra_allowed_dirs=None)
    out = await t.execute("a.txt", lines=2)
    assert "line2" in out
    assert "line3" in out


@pytest.mark.asyncio
async def test_read_hex_dump_clamps_byte_limit(workspace: Path) -> None:
    t = ReadHexDumpTool(workspace=workspace, allowed_dir=workspace, extra_allowed_dirs=None)
    out = await t.execute("big.bin", byteLimit=9999)
    # schema max 512 — execute clamps
    assert "512 byte" in out or "byte(s)" in out
    lines = [ln for ln in out.splitlines() if ln.strip() and not ln.startswith("(")]
    raw_hex_lines = [ln for ln in lines if "|" in ln and "  " in ln]
    joined = "\n".join(raw_hex_lines)
    # 512 bytes => 32 lines of 16 bytes
    assert len(raw_hex_lines) <= 40


@pytest.mark.asyncio
async def test_read_hex_dump_accepts_bytes_kwarg(workspace: Path) -> None:
    t = ReadHexDumpTool(workspace=workspace, allowed_dir=workspace, extra_allowed_dirs=None)
    out = await t.execute("big.bin", bytes=64)
    assert "00000000" in out
