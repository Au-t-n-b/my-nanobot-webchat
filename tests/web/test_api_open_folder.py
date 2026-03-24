"""Tests for ``POST /api/open-folder``."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from aiohttp.test_utils import TestClient, TestServer

from nanobot.web.app import create_app


@pytest.mark.asyncio
async def test_open_folder_directory_ok(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ws = tmp_path / "workspace"
    target = ws / "skills" / "abc"
    target.mkdir(parents=True)
    monkeypatch.setenv("NANOBOT_AGUI_WORKSPACE_ROOT", str(ws))
    app = create_app()
    with patch("nanobot.web.routes.open_in_os") as m_open:
        async with TestClient(TestServer(app)) as client:
            r = await client.post("/api/open-folder", json={"target": str(target)})
            assert r.status == 200
            assert await r.json() == {"ok": True}
    m_open.assert_called_once()


def test_open_file_windows_selects_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from nanobot.web.fs_ops import open_in_os

    f = tmp_path / "a.txt"
    f.write_text("x", encoding="utf-8")
    monkeypatch.setattr("platform.system", lambda: "Windows")
    with patch("subprocess.Popen") as popen:
        open_in_os(f)
    popen.assert_called_once()
    args = popen.call_args[0][0]
    assert args[0].lower() == "explorer"
    assert any(str(f) in str(x) for x in args)


def test_open_file_non_windows_opens_parent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from nanobot.web.fs_ops import open_in_os

    f = tmp_path / "a.txt"
    f.write_text("x", encoding="utf-8")
    monkeypatch.setattr("platform.system", lambda: "Linux")
    with patch("subprocess.Popen") as popen:
        open_in_os(f)
    popen.assert_called_once()
    args = popen.call_args[0][0]
    assert args[0] == "xdg-open"
    assert str(f.parent) == str(args[1])


@pytest.mark.asyncio
async def test_open_folder_rejects_escape(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ws = tmp_path / "workspace"
    ws.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    monkeypatch.setenv("NANOBOT_AGUI_WORKSPACE_ROOT", str(ws))
    app = create_app()
    async with TestClient(TestServer(app)) as client:
        r = await client.post("/api/open-folder", json={"target": str(outside)})
        assert r.status == 400
        j = await r.json()
        assert j["error"]["code"] == "bad_request"


@pytest.mark.asyncio
async def test_open_folder_rejects_symlink_escape(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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
        r = await client.post("/api/open-folder", json={"target": str(link / 'x.txt')})
        assert r.status == 400
        j = await r.json()
        assert j["error"]["code"] == "bad_request"


@pytest.mark.asyncio
async def test_open_folder_not_found_returns_404_with_error_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ws = tmp_path / "workspace"
    ws.mkdir()
    target = ws / "nope.txt"
    monkeypatch.setenv("NANOBOT_AGUI_WORKSPACE_ROOT", str(ws))
    app = create_app()
    async with TestClient(TestServer(app)) as client:
        r = await client.post("/api/open-folder", json={"target": str(target)})
        assert r.status == 404
        j = await r.json()
        assert j["error"]["code"] == "not_found"
        assert isinstance(j["error"]["message"], str)
