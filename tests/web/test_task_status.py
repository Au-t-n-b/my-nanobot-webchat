"""Tests for ``GET /api/task-status``."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from aiohttp.test_utils import TestClient, TestServer

from nanobot.config import loader as config_loader
from nanobot.web.app import create_app


def _set_nanobot_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Point config/data lookups at a temp ``~/.nanobot`` directory."""
    config_path = tmp_path / ".nanobot" / "config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(config_loader, "_current_config_path", config_path)
    return config_path.parent


@pytest.mark.asyncio
async def test_task_status_returns_default_when_file_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_nanobot_home(monkeypatch=monkeypatch, tmp_path=tmp_path)
    app = create_app(config=None)

    async with TestClient(TestServer(app)) as client:
        r = await client.get("/api/task-status")
        assert r.status == 200
        body = await r.json()

    modules = body.get("modules")
    assert isinstance(modules, list)
    assert len(modules) == 6
    assert body["overall"]["totalCount"] == len(modules)
    assert body["overall"]["doneCount"] == sum(1 for m in modules if m.get("status") == "completed")
    for module in modules:
        assert module.get("status") in {"pending", "running", "completed"}
        assert isinstance(module.get("steps"), list)


@pytest.mark.asyncio
async def test_task_status_returns_file_payload_when_valid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    nanobot_home = _set_nanobot_home(monkeypatch, tmp_path)
    payload = {
        "schemaVersion": 1,
        "updatedAt": 1774659000,
        "progress": [
            {
                "moduleId": "m_1",
                "moduleName": "机房准备",
                "updatedAt": 1774659000,
                "tasks": [
                    {"name": "提资", "completed": True},
                    {"name": "工勘数据采集与处理", "completed": True},
                ],
            },
            {
                "moduleId": "m_2",
                "moduleName": "机房工勘",
                "updatedAt": 1774659000,
                "tasks": [
                    {"name": "数据解析/架构/空间设", "completed": True},
                    {"name": "数据智能提取", "completed": False},
                ],
            },
        ],
    }
    (nanobot_home / "task_progress.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    app = create_app(config=None)

    async with TestClient(TestServer(app)) as client:
        r = await client.get("/api/task-status")
        assert r.status == 200
        got = await r.json()

    assert got["updatedAt"] == 1774659000
    assert got["overall"] == {"doneCount": 1, "totalCount": 2}
    assert got["modules"] == [
        {
            "id": "m_1",
            "name": "机房准备",
            "status": "completed",
            "steps": [
                {"id": "m_1_s_1", "name": "提资", "done": True},
                {"id": "m_1_s_2", "name": "工勘数据采集与处理", "done": True},
            ],
        },
        {
            "id": "m_2",
            "name": "机房工勘",
            "status": "running",
            "steps": [
                {"id": "m_2_s_1", "name": "数据解析/架构/空间设", "done": True},
                {"id": "m_2_s_2", "name": "数据智能提取", "done": False},
            ],
        },
    ]


@pytest.mark.asyncio
async def test_task_status_returns_500_when_invalid_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    nanobot_home = _set_nanobot_home(monkeypatch, tmp_path)
    (nanobot_home / "task_progress.json").write_text("{invalid json", encoding="utf-8")
    app = create_app(config=None)

    async with TestClient(TestServer(app)) as client:
        r = await client.get("/api/task-status")
        assert r.status == 500
        body = await r.json()

    assert "detail" in body
