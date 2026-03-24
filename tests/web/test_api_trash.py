"""Tests for ``POST /api/trash-files``."""

from __future__ import annotations

from pathlib import Path

import pytest
from aiohttp.test_utils import TestClient, TestServer

from nanobot.web.app import create_app


@pytest.mark.asyncio
async def test_trash_files_rejects_empty_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NANOBOT_AGUI_WORKSPACE_ROOT", str(tmp_path / "workspace"))
    app = create_app()
    async with TestClient(TestServer(app)) as client:
        r = await client.post("/api/trash-files", json={"paths": []})
        assert r.status == 400
        j = await r.json()
        assert j["error"]["code"] == "bad_request"


@pytest.mark.asyncio
async def test_trash_files_rejects_any_escape_all_or_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ws = tmp_path / "workspace"
    ws.mkdir()
    inside = ws / "a.txt"
    inside.write_text("x", encoding="utf-8")
    outside = tmp_path / "outside.txt"
    outside.write_text("x", encoding="utf-8")
    monkeypatch.setenv("NANOBOT_AGUI_WORKSPACE_ROOT", str(ws))
    app = create_app()
    async with TestClient(TestServer(app)) as client:
        r = await client.post("/api/trash-files", json={"paths": [str(inside), str(outside)]})
        assert r.status == 400
        assert inside.exists()  # zero side effects when escape exists


@pytest.mark.asyncio
async def test_trash_files_dedupes_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ws = tmp_path / "workspace"
    ws.mkdir()
    f = ws / "dup.txt"
    f.write_text("x", encoding="utf-8")
    monkeypatch.setenv("NANOBOT_AGUI_WORKSPACE_ROOT", str(ws))
    app = create_app()
    async with TestClient(TestServer(app)) as client:
        r = await client.post("/api/trash-files", json={"paths": [str(f), str(f)]})
        assert r.status == 200
        j = await r.json()
        assert len(j["deleted"]) == 1


@pytest.mark.asyncio
async def test_trash_files_accepts_directory_target(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ws = tmp_path / "workspace"
    d = ws / "folder"
    d.mkdir(parents=True)
    (d / "x.txt").write_text("x", encoding="utf-8")
    monkeypatch.setenv("NANOBOT_AGUI_WORKSPACE_ROOT", str(ws))
    app = create_app()
    async with TestClient(TestServer(app)) as client:
        r = await client.post("/api/trash-files", json={"paths": [str(d)]})
        assert r.status == 200
        j = await r.json()
        assert j["ok"] is True
        assert str(d.resolve()) in j["deleted"]


@pytest.mark.asyncio
async def test_trash_files_partial_success_returns_deleted_and_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ws = tmp_path / "workspace"
    ws.mkdir()
    good = ws / "ok.txt"
    good.write_text("x", encoding="utf-8")
    missing = ws / "missing.txt"
    monkeypatch.setenv("NANOBOT_AGUI_WORKSPACE_ROOT", str(ws))
    app = create_app()
    async with TestClient(TestServer(app)) as client:
        r = await client.post("/api/trash-files", json={"paths": [str(good), str(missing)]})
        assert r.status == 200
        j = await r.json()
        assert j["ok"] is False
        assert str(good.resolve()) in j["deleted"]
        assert any(item["path"] == str(missing.resolve()) for item in j["failed"])


@pytest.mark.asyncio
async def test_trash_files_rejects_symlink_escape(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ws = tmp_path / "workspace"
    ws.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "x.txt").write_text("x", encoding="utf-8")
    link = ws / "link-outside"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError as e:
        if "1314" in str(e):
            pytest.skip("symlink privilege unavailable on this Windows environment")
        raise
    monkeypatch.setenv("NANOBOT_AGUI_WORKSPACE_ROOT", str(ws))
    app = create_app()
    async with TestClient(TestServer(app)) as client:
        r = await client.post("/api/trash-files", json={"paths": [str(link / "x.txt")]})
        assert r.status == 400
        j = await r.json()
        assert j["error"]["code"] == "bad_request"


@pytest.mark.asyncio
async def test_trash_files_error_payload_shape(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ws = tmp_path / "workspace"
    ws.mkdir()
    monkeypatch.setenv("NANOBOT_AGUI_WORKSPACE_ROOT", str(ws))
    app = create_app()
    async with TestClient(TestServer(app)) as client:
        r = await client.post("/api/trash-files", json={"paths": []})
        assert r.status == 400
        j = await r.json()
        assert "error" in j
        assert "code" in j["error"]
        assert "message" in j["error"]
