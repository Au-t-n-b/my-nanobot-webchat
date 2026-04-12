"""Tests for ``GET /api/skills``."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from aiohttp.test_utils import TestClient, TestServer

from nanobot.web.app import create_app


@pytest.mark.asyncio
async def test_get_skills_auto_create_and_empty(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NANOBOT_AGUI_SKILLS_ROOT", str(tmp_path / "skills"))
    app = create_app()
    async with TestClient(TestServer(app)) as client:
        resp = await client.get("/api/skills")
        assert resp.status == 200
        data = await resp.json()
        assert data == {"items": []}
    assert (tmp_path / "skills").is_dir()


@pytest.mark.asyncio
async def test_get_skills_scans_skill_md_and_sorts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "skills"
    (root / "beta").mkdir(parents=True)
    (root / "Alpha").mkdir(parents=True)
    (root / "beta" / "SKILL.md").write_text("# beta", encoding="utf-8")
    (root / "Alpha" / "SKILL.md").write_text("# alpha", encoding="utf-8")
    monkeypatch.setenv("NANOBOT_AGUI_SKILLS_ROOT", str(root))

    app = create_app()
    async with TestClient(TestServer(app)) as client:
        resp = await client.get("/api/skills")
        assert resp.status == 200
        data = await resp.json()
        names = [it["name"] for it in data["items"]]
        assert names == ["Alpha", "beta"]
        assert all(Path(it["skillFile"]).is_absolute() for it in data["items"])
        assert all(it["source"] == "local" for it in data["items"])


@pytest.mark.asyncio
async def test_get_skills_marks_remote_imported_when_metadata_exists(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "skills"
    imported = root / "report-gen"
    imported.mkdir(parents=True)
    (imported / "SKILL.md").write_text("# report-gen", encoding="utf-8")
    (imported / ".nanobot-remote-skill.json").write_text(
        (
            '{"source":"remote-imported","remoteSkillId":"101","remoteTitle":"工勘报告生成",'
            '"organizationName":"交付中心"}'
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("NANOBOT_AGUI_SKILLS_ROOT", str(root))

    app = create_app()
    async with TestClient(TestServer(app)) as client:
        resp = await client.get("/api/skills")
        assert resp.status == 200
        assert await resp.json() == {
            "items": [
                {
                    "name": "report-gen",
                    "skillDir": str(imported.resolve()),
                    "skillFile": str((imported / "SKILL.md").resolve()),
                    "mtimeMs": int((imported / "SKILL.md").stat().st_mtime * 1000),
                    "source": "remote-imported",
                    "description": "",
                    "remoteSkillId": "101",
                    "remoteTitle": "工勘报告生成",
                    "organizationName": "交付中心",
                }
            ]
        }


@pytest.mark.asyncio
async def test_get_skills_error_payload_shape_on_internal_error() -> None:
    app = create_app()
    with patch("nanobot.web.routes.list_skills", side_effect=RuntimeError("boom")):
        async with TestClient(TestServer(app)) as client:
            resp = await client.get("/api/skills")
            assert resp.status == 500
            payload = await resp.json()
            assert "error" in payload
            assert payload["error"]["code"] == "internal_error"
            assert isinstance(payload["error"]["message"], str)


@pytest.mark.asyncio
async def test_get_modules_scans_module_json_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "skills"
    module_dir = root / "intelligent_analysis_workbench"
    module_dir.mkdir(parents=True)
    (module_dir / "module.json").write_text(
        """
        {
          "moduleId": "intelligent_analysis_workbench",
          "docId": "dashboard:intelligent-analysis-workbench",
          "dataFile": "skills/intelligent_analysis_workbench/data/dashboard.json",
          "flow": "intelligent_analysis_workbench",
          "taskProgress": {
            "moduleId": "intelligent_analysis_workbench",
            "moduleName": "智能分析工作台",
            "tasks": ["模块待启动", "分析目标已确认"]
          },
          "caseTemplate": {
            "moduleTitle": "智能分析工作台",
            "moduleGoal": "标准案例模块"
          }
        }
        """,
        encoding="utf-8",
    )
    monkeypatch.setenv("NANOBOT_AGUI_SKILLS_ROOT", str(root))

    app = create_app()
    async with TestClient(TestServer(app)) as client:
        resp = await client.get("/api/modules")
        assert resp.status == 200
        assert await resp.json() == {
            "items": [
                {
                    "moduleId": "intelligent_analysis_workbench",
                    "label": "智能分析工作台",
                    "description": "标准案例模块",
                    "taskProgress": {
                        "moduleId": "intelligent_analysis_workbench",
                        "moduleName": "智能分析工作台",
                        "tasks": ["模块待启动", "分析目标已确认"],
                    },
                    "dashboard": {
                        "docId": "dashboard:intelligent-analysis-workbench",
                        "dataFile": "skills/intelligent_analysis_workbench/data/dashboard.json",
                    },
                }
            ]
        }


@pytest.mark.asyncio
async def test_get_modules_skips_invalid_module_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "skills"
    valid_dir = root / "valid_module"
    valid_dir.mkdir(parents=True)
    (valid_dir / "module.json").write_text(
        """
        {
          "moduleId": "valid_module",
          "docId": "dashboard:valid-module",
          "dataFile": "skills/valid_module/data/dashboard.json",
          "flow": "valid_flow",
          "caseTemplate": {
            "moduleTitle": "有效模块",
            "moduleGoal": "可显示"
          }
        }
        """,
        encoding="utf-8",
    )
    invalid_dir = root / "broken_module"
    invalid_dir.mkdir(parents=True)
    (invalid_dir / "module.json").write_text("{not-json", encoding="utf-8")
    monkeypatch.setenv("NANOBOT_AGUI_SKILLS_ROOT", str(root))

    app = create_app()
    async with TestClient(TestServer(app)) as client:
        resp = await client.get("/api/modules")
        assert resp.status == 200
        assert await resp.json() == {
            "items": [
                {
                    "moduleId": "valid_module",
                    "label": "有效模块",
                    "description": "可显示",
                    "taskProgress": {
                        "moduleId": "valid_module",
                        "moduleName": "有效模块",
                        "tasks": [],
                    },
                    "dashboard": {
                        "docId": "dashboard:valid-module",
                        "dataFile": "skills/valid_module/data/dashboard.json",
                    },
                }
            ]
        }
