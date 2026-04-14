"""Tests for ``GET /api/file``."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from aiohttp.test_utils import TestClient, TestServer

from nanobot.web.app import create_app
from nanobot.web.paths import normalize_file_query, resolve_file_target


def test_normalize_file_query() -> None:
    assert normalize_file_query("a\\b\\c") == "a/b/c"
    assert normalize_file_query("x\r\ny") == "xy"
    assert normalize_file_query("") == ""


def test_resolve_relative_stays_in_workspace(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    ws.mkdir()
    inner = ws / "inner" / "f.txt"
    inner.parent.mkdir(parents=True)
    inner.write_text("hi", encoding="utf-8")
    got = resolve_file_target("inner/f.txt", ws)
    assert got == inner.resolve()


def test_resolve_relative_workspace_prefix_stays_in_workspace(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    ws.mkdir()
    inner = ws / "skills" / "gongkan_skill" / "ProjectData" / "Input" / "BOQ.xlsx"
    inner.parent.mkdir(parents=True)
    inner.write_text("hi", encoding="utf-8")
    got = resolve_file_target("workspace/skills/gongkan_skill/ProjectData/Input/BOQ.xlsx", ws)
    assert got == inner.resolve()


def test_resolve_relative_escape_raises(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    ws.mkdir()
    with pytest.raises(ValueError, match="escapes"):
        resolve_file_target("../outside.txt", ws)


@pytest.mark.asyncio
async def test_get_file_requires_path() -> None:
    app = create_app()
    async with TestClient(TestServer(app)) as client:
        r = await client.get("/api/file")
        assert r.status == 400


@pytest.mark.asyncio
async def test_get_file_absolute(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    f = tmp_path / "readme.txt"
    f.write_bytes(b"hello file")
    app = create_app()
    async with TestClient(TestServer(app)) as client:
        r = await client.get("/api/file", params={"path": str(f)})
        assert r.status == 200
        assert await r.read() == b"hello file"
        assert "text/plain" in (r.headers.get("Content-Type") or "")


@pytest.mark.asyncio
async def test_get_file_relative_workspace(tmp_path: Path) -> None:
    ws = tmp_path / "w"
    ws.mkdir()
    (ws / "a.md").write_text("# x", encoding="utf-8")
    cfg = MagicMock()
    cfg.workspace_path = ws
    app = create_app(config=cfg)
    async with TestClient(TestServer(app)) as client:
        r = await client.get("/api/file", params={"path": "a.md"})
        assert r.status == 200
        assert (await r.text()) == "# x"


@pytest.mark.asyncio
async def test_get_file_relative_workspace_prefix(tmp_path: Path) -> None:
    ws = tmp_path / "w"
    ws.mkdir()
    target = ws / "skills" / "gongkan_skill" / "ProjectData" / "Input" / "BOQ.xlsx"
    target.parent.mkdir(parents=True)
    target.write_text("xlsx-bytes", encoding="utf-8")
    cfg = MagicMock()
    cfg.workspace_path = ws
    app = create_app(config=cfg)
    async with TestClient(TestServer(app)) as client:
        r = await client.get("/api/file", params={"path": "workspace/skills/gongkan_skill/ProjectData/Input/BOQ.xlsx"})
        assert r.status == 200
        assert await r.text() == "xlsx-bytes"


@pytest.mark.asyncio
async def test_get_file_escape_returns_400(tmp_path: Path) -> None:
    ws = tmp_path / "w"
    ws.mkdir()
    cfg = MagicMock()
    cfg.workspace_path = ws
    app = create_app(config=cfg)
    async with TestClient(TestServer(app)) as client:
        r = await client.get("/api/file", params={"path": "../secret"})
        assert r.status == 400


@pytest.mark.asyncio
async def test_get_file_missing_returns_404(tmp_path: Path) -> None:
    cfg = MagicMock()
    cfg.workspace_path = tmp_path
    app = create_app(config=cfg)
    async with TestClient(TestServer(app)) as client:
        r = await client.get("/api/file", params={"path": "nope.txt"})
        assert r.status == 404
