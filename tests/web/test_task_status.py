"""Tests for ``GET /api/task-status``."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from aiohttp.test_utils import TestClient, TestServer

from nanobot.web.app import create_app


@pytest.mark.asyncio
async def test_task_status_returns_default_when_file_missing(tmp_path: Path) -> None:
    cfg = MagicMock()
    cfg.workspace_path = tmp_path
    app = create_app(config=cfg)

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
async def test_task_status_returns_file_payload_when_valid(tmp_path: Path) -> None:
    payload = {
        "updatedAt": "2026-03-27T10:00:00Z",
        "overall": {"doneCount": 1, "totalCount": 2},
        "modules": [
            {"id": "m1", "name": "需求分析", "status": "completed", "steps": []},
            {"id": "m2", "name": "方案设计", "status": "running", "steps": [{"id": "s1", "name": "拆分任务", "done": False}]},
        ],
    }
    (tmp_path / "task_progress.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    cfg = MagicMock()
    cfg.workspace_path = tmp_path
    app = create_app(config=cfg)

    async with TestClient(TestServer(app)) as client:
        r = await client.get("/api/task-status")
        assert r.status == 200
        got = await r.json()

    assert got == payload


@pytest.mark.asyncio
async def test_task_status_returns_500_when_invalid_json(tmp_path: Path) -> None:
    (tmp_path / "task_progress.json").write_text("{invalid json", encoding="utf-8")
    cfg = MagicMock()
    cfg.workspace_path = tmp_path
    app = create_app(config=cfg)

    async with TestClient(TestServer(app)) as client:
        r = await client.get("/api/task-status")
        assert r.status == 500
        body = await r.json()

    assert "detail" in body
