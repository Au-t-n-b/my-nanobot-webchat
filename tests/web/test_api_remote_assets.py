"""Tests for remote asset proxy endpoints."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

from aiohttp import FormData
from aiohttp.test_utils import TestClient, TestServer
import pytest

from nanobot.web.app import create_app
from nanobot.web.keys import REMOTE_CENTER_CLIENT_FACTORY_KEY, REMOTE_CENTER_SESSION_STORE_KEY


class FakeRemoteAssetClient:
    def __init__(self) -> None:
        self.clone_calls: list[dict[str, str | None]] = []
        self.import_calls: list[str] = []
        self.skill_upload_calls: list[dict[str, object]] = []
        self.artifact_upload_calls: list[dict[str, object]] = []
        self.skill_collect_calls: list[dict[str, object]] = []

    async def login(self, *, work_id: str, password: str) -> dict[str, object]:
        return {
            "token": "remote-token",
            "user": {"workId": work_id, "name": "测试用户", "role": "user"},
            "projects": [{"id": "project-a", "name": "项目A"}],
        }

    async def list_org_skills(self) -> list[dict[str, object]]:
        return [
            {
                "id": "101",
                "name": "report-gen",
                "title": "工勘报告生成",
                "description": "自动生成工勘报告",
                "version": "1.0.0",
                "organizationName": "交付中心",
                "updatedAt": "2026-03-28T10:00:00Z",
            }
        ]

    async def get_org_skill(self, skill_id: str) -> dict[str, object]:
        assert skill_id == "101"
        return {
            "id": "101",
            "kind": "org-skill",
            "name": "report-gen",
            "title": "工勘报告生成",
            "description": "自动生成工勘报告",
            "version": "1.0.0",
            "organizationName": "交付中心",
            "uploaderId": "j00954996",
            "updatedAt": "2026-03-28T10:00:00Z",
            "tags": ["report"],
            "canImport": True,
            "canClone": True,
        }

    async def download_org_skill(self, skill_id: str, *, user_id: str) -> bytes:
        self.import_calls.append(f"{skill_id}:{user_id}")
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as zf:
            zf.writestr("SKILL.md", "# 工勘报告生成\n")
            zf.writestr("_meta.json", '{"version":"1.0.0"}')
        return buffer.getvalue()

    async def clone_org_skill_to_personal(
        self,
        skill_id: str,
        *,
        scope: str,
        project_id: str | None,
    ) -> dict[str, object]:
        self.clone_calls.append({"skill_id": skill_id, "scope": scope, "project_id": project_id})
        return {
            "id": "ps-2",
            "kind": "personal-skill",
            "title": "工勘报告生成",
            "scope": scope,
            "projectId": project_id,
            "projectName": "项目A" if project_id == "project-a" else None,
        }

    async def list_personal_skills(self, *, scope: str, project_id: str | None) -> list[dict[str, object]]:
        return [
            {
                "id": "ps-1",
                "kind": "personal-skill",
                "title": "我的报告生成",
                "scope": scope,
                "projectId": project_id,
                "projectName": "项目A" if project_id == "project-a" else None,
                "sourceType": "zip_file",
                "updatedAt": "2026-03-28T12:00:00Z",
            }
        ]

    async def upload_personal_skill(
        self,
        *,
        filename: str,
        content: bytes,
        scope: str,
        project_id: str | None,
        user_id: str = "",
    ) -> dict[str, object]:
        self.skill_upload_calls.append(
            {
                "filename": filename,
                "content": content,
                "scope": scope,
                "project_id": project_id,
                "user_id": user_id,
            }
        )
        return {
            "id": "ps-3",
            "kind": "personal-skill",
            "title": filename,
            "scope": scope,
            "projectId": project_id,
            "projectName": "项目A" if project_id == "project-a" else None,
        }

    async def list_personal_artifacts(self, *, scope: str, project_id: str | None) -> list[dict[str, object]]:
        return [
            {
                "id": "pa-1",
                "kind": "personal-artifact",
                "filename": "report.docx",
                "scope": scope,
                "projectId": project_id,
                "projectName": "项目A" if project_id == "project-a" else None,
                "sizeBytes": 102400,
                "sourceType": "session_output",
                "updatedAt": "2026-03-28T12:10:00Z",
            }
        ]

    async def upload_personal_artifacts(
        self,
        *,
        files: list[dict[str, object]],
        scope: str,
        project_id: str | None,
    ) -> list[dict[str, object]]:
        self.artifact_upload_calls.append(
            {
                "files": files,
                "scope": scope,
                "project_id": project_id,
            }
        )
        return [
            {
                "id": "pa-2",
                "kind": "personal-artifact",
                "filename": str(files[0]["filename"]),
                "scope": scope,
                "projectId": project_id,
                "projectName": "项目A" if project_id == "project-a" else None,
            }
        ]

    async def collect_skill_to_remote(
        self,
        *,
        filename: str,
        content: bytes,
        title: str,
        description: str,
        tags: list[str],
        business_type: str,
        delivery_type: str,
        organization_name: str,
        project_name: str | None,
        uploader_id: str,
        version: str,
        source_template_version: str,
        local_last_modified_at: str | None,
        base_skill_id: int,
        base_skill_title: str,
    ) -> dict[str, object]:
        self.skill_collect_calls.append(
            {
                "filename": filename,
                "content": content,
                "title": title,
                "description": description,
                "tags": tags,
                "business_type": business_type,
                "delivery_type": delivery_type,
                "organization_name": organization_name,
                "project_name": project_name,
                "uploader_id": uploader_id,
                "version": version,
                "source_template_version": source_template_version,
                "local_last_modified_at": local_last_modified_at,
                "base_skill_id": base_skill_id,
                "base_skill_title": base_skill_title,
            }
        )
        return {
            "id": "ps-remote-1",
            "title": title,
            "projectName": project_name,
        }


async def _login_remote(client: TestClient) -> None:
    resp = await client.post(
        "/api/remote-center/login",
        json={
            "frontendBase": "http://127.0.0.1:3000",
            "apiBase": "http://127.0.0.1:8000",
            "workId": "j00954996",
            "password": "123456",
        },
    )
    assert resp.status == 200


@pytest.mark.asyncio
async def test_get_org_skills_requires_remote_session() -> None:
    app = create_app()
    async with TestClient(TestServer(app)) as client:
        resp = await client.get("/api/remote-assets/org-skills")
        assert resp.status == 400
        assert await resp.json() == {
            "error": {
                "code": "remote_not_connected",
                "message": "Remote center session not established",
            }
        }


@pytest.mark.asyncio
async def test_get_org_skills_returns_mapped_items() -> None:
    app = create_app()
    fake_client = FakeRemoteAssetClient()
    app[REMOTE_CENTER_CLIENT_FACTORY_KEY] = lambda frontend_base, api_base: fake_client

    async with TestClient(TestServer(app)) as client:
        await _login_remote(client)
        resp = await client.get("/api/remote-assets/org-skills")
        assert resp.status == 200
        assert await resp.json() == {
            "items": [
                {
                    "id": "101",
                    "name": "report-gen",
                    "title": "工勘报告生成",
                    "description": "自动生成工勘报告",
                    "version": "1.0.0",
                    "organizationName": "交付中心",
                    "updatedAt": "2026-03-28T10:00:00Z",
                }
            ]
        }


@pytest.mark.asyncio
async def test_get_org_skill_detail_returns_can_import_and_can_clone() -> None:
    app = create_app()
    fake_client = FakeRemoteAssetClient()
    app[REMOTE_CENTER_CLIENT_FACTORY_KEY] = lambda frontend_base, api_base: fake_client

    async with TestClient(TestServer(app)) as client:
        await _login_remote(client)
        resp = await client.get("/api/remote-assets/org-skills/101")
        assert resp.status == 200
        assert await resp.json() == {
            "id": "101",
            "kind": "org-skill",
            "name": "report-gen",
            "title": "工勘报告生成",
            "description": "自动生成工勘报告",
            "version": "1.0.0",
            "organizationName": "交付中心",
            "uploaderId": "j00954996",
            "updatedAt": "2026-03-28T10:00:00Z",
            "tags": ["report"],
            "canImport": True,
            "canClone": True,
        }


@pytest.mark.asyncio
async def test_import_org_skill_returns_local_target(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NANOBOT_AGUI_SKILLS_ROOT", str(tmp_path / "skills"))
    app = create_app()
    fake_client = FakeRemoteAssetClient()
    app[REMOTE_CENTER_CLIENT_FACTORY_KEY] = lambda frontend_base, api_base: fake_client

    async with TestClient(TestServer(app)) as client:
        await _login_remote(client)
        resp = await client.post("/api/remote-assets/org-skills/101/import", json={"target": "workspace-skills"})
        assert resp.status == 200
        data = await resp.json()
        imported_path = Path(data["importedPath"])
        assert data["ok"] is True
        assert imported_path.is_dir()
        assert (imported_path / "SKILL.md").read_text(encoding="utf-8") == "# 工勘报告生成\n"
        assert (imported_path / ".nanobot-remote-skill.json").is_file()
        assert fake_client.import_calls == ["101:j00954996"]


@pytest.mark.asyncio
async def test_publish_local_skill_as_personal_asset(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "skills"
    local_skill = root / "local-skill"
    local_skill.mkdir(parents=True)
    (local_skill / "SKILL.md").write_text("---\ndescription: 本地技能\n---\n# local\n", encoding="utf-8")
    (local_skill / "_meta.json").write_text('{"version":"1.0.0"}', encoding="utf-8")
    monkeypatch.setenv("NANOBOT_AGUI_SKILLS_ROOT", str(root))

    app = create_app()
    fake_client = FakeRemoteAssetClient()
    app[REMOTE_CENTER_CLIENT_FACTORY_KEY] = lambda frontend_base, api_base: fake_client

    async with TestClient(TestServer(app)) as client:
        await _login_remote(client)
        resp = await client.post(
            "/api/skills/publish",
            json={"skillName": "local-skill", "target": "personal"},
        )
        assert resp.status == 200
        assert await resp.json() == {
            "ok": True,
            "target": "personal",
            "item": {
                "id": "ps-3",
                "kind": "personal-skill",
                "title": "local-skill.zip",
                "scope": "project",
                "projectId": "project-a",
                "projectName": "项目A",
            },
        }
        assert len(fake_client.skill_upload_calls) == 1
        call = fake_client.skill_upload_calls[0]
        assert call["filename"] == "local-skill.zip"
        assert call["scope"] == "project"
        assert call["project_id"] == "project-a"
        assert call["user_id"] == "j00954996"
        archive = zipfile.ZipFile(io.BytesIO(call["content"]))  # type: ignore[arg-type]
        assert sorted(archive.namelist()) == ["SKILL.md", "_meta.json"]


@pytest.mark.asyncio
async def test_publish_remote_imported_skill_as_collected_remote_asset(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "skills"
    imported = root / "report-gen"
    imported.mkdir(parents=True)
    (imported / "SKILL.md").write_text(
        "---\ndescription: 回流技能\nversion: 1.1.0\ntags: report,remote\n---\n# remote\n",
        encoding="utf-8",
    )
    (imported / "_meta.json").write_text('{"version":"1.0.0"}', encoding="utf-8")
    (imported / ".nanobot-remote-skill.json").write_text(
        (
            '{"source":"remote-imported","remoteSkillId":"101","remoteTitle":"工勘报告生成",'
            '"organizationName":"交付中心","businessType":"迁移调优","deliveryType":"标准交付",'
            '"sourceTemplateVersion":"1.0.0"}'
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("NANOBOT_AGUI_SKILLS_ROOT", str(root))

    app = create_app()
    fake_client = FakeRemoteAssetClient()
    app[REMOTE_CENTER_CLIENT_FACTORY_KEY] = lambda frontend_base, api_base: fake_client

    async with TestClient(TestServer(app)) as client:
        await _login_remote(client)
        resp = await client.post(
            "/api/skills/publish",
            json={"skillName": "report-gen", "target": "backflow"},
        )
        assert resp.status == 200
        assert await resp.json() == {
            "ok": True,
            "target": "backflow",
            "item": {
                "id": "ps-remote-1",
                "title": "工勘报告生成",
                "projectName": "project-a",
            },
        }
        assert len(fake_client.skill_collect_calls) == 1
        call = fake_client.skill_collect_calls[0]
        assert call["filename"] == "report-gen.zip"
        assert call["title"] == "工勘报告生成"
        assert call["description"] == "回流技能"
        assert call["tags"] == ["report", "remote"]
        assert call["business_type"] == "迁移调优"
        assert call["delivery_type"] == "标准交付"
        assert call["organization_name"] == "交付中心"
        assert call["project_name"] == "project-a"
        assert call["uploader_id"] == "j00954996"
        assert call["version"] == "1.1.0"
        assert call["source_template_version"] == "1.0.0"
        assert call["base_skill_id"] == 101
        assert call["base_skill_title"] == "工勘报告生成"
        archive = zipfile.ZipFile(io.BytesIO(call["content"]))  # type: ignore[arg-type]
        assert sorted(archive.namelist()) == ["SKILL.md", "_meta.json"]


@pytest.mark.asyncio
async def test_clone_org_skill_returns_personal_asset_payload() -> None:
    app = create_app()
    fake_client = FakeRemoteAssetClient()
    app[REMOTE_CENTER_CLIENT_FACTORY_KEY] = lambda frontend_base, api_base: fake_client

    async with TestClient(TestServer(app)) as client:
        await _login_remote(client)
        store = app[REMOTE_CENTER_SESSION_STORE_KEY]
        store.select_project("project-a")
        resp = await client.post(
            "/api/remote-assets/org-skills/101/clone-to-personal",
            json={"scope": "project", "projectId": "project-a"},
        )
        assert resp.status == 200
        assert await resp.json() == {
            "ok": True,
            "item": {
                "id": "ps-2",
                "kind": "personal-skill",
                "title": "工勘报告生成",
                "scope": "project",
                "projectId": "project-a",
                "projectName": "项目A",
            },
        }
        assert fake_client.clone_calls == [{"skill_id": "101", "scope": "project", "project_id": "project-a"}]


@pytest.mark.asyncio
async def test_get_personal_skills_returns_mapped_items() -> None:
    app = create_app()
    fake_client = FakeRemoteAssetClient()
    app[REMOTE_CENTER_CLIENT_FACTORY_KEY] = lambda frontend_base, api_base: fake_client

    async with TestClient(TestServer(app)) as client:
        await _login_remote(client)
        store = app[REMOTE_CENTER_SESSION_STORE_KEY]
        store.select_project("project-a")
        resp = await client.get("/api/remote-assets/personal-skills")
        assert resp.status == 200
        assert await resp.json() == {
            "items": [
                {
                    "id": "ps-1",
                    "kind": "personal-skill",
                    "title": "我的报告生成",
                    "scope": "project",
                    "projectId": "project-a",
                    "projectName": "项目A",
                    "sourceType": "zip_file",
                    "updatedAt": "2026-03-28T12:00:00Z",
                }
            ]
        }


@pytest.mark.asyncio
async def test_personal_skill_upload_accepts_zip_file() -> None:
    app = create_app()
    fake_client = FakeRemoteAssetClient()
    app[REMOTE_CENTER_CLIENT_FACTORY_KEY] = lambda frontend_base, api_base: fake_client

    async with TestClient(TestServer(app)) as client:
        await _login_remote(client)
        data = FormData()
        data.add_field("scope", "project")
        data.add_field("projectId", "project-a")
        data.add_field("sourceType", "zip_file")
        data.add_field("file", b"zip-content", filename="skill.zip", content_type="application/zip")
        resp = await client.post("/api/remote-assets/personal-skills/upload", data=data)
        assert resp.status == 200
        assert await resp.json() == {
            "ok": True,
            "item": {
                "id": "ps-3",
                "kind": "personal-skill",
                "title": "skill.zip",
                "scope": "project",
                "projectId": "project-a",
                "projectName": "项目A",
            },
        }
        assert fake_client.skill_upload_calls == [
            {
                "filename": "skill.zip",
                "content": b"zip-content",
                "scope": "project",
                "project_id": "project-a",
                "user_id": "",
            }
        ]


@pytest.mark.asyncio
async def test_personal_artifacts_upload_accepts_manual_files() -> None:
    app = create_app()
    fake_client = FakeRemoteAssetClient()
    app[REMOTE_CENTER_CLIENT_FACTORY_KEY] = lambda frontend_base, api_base: fake_client

    async with TestClient(TestServer(app)) as client:
        await _login_remote(client)
        data = FormData()
        data.add_field("scope", "project")
        data.add_field("projectId", "project-a")
        data.add_field("files", b"hello", filename="report.txt", content_type="text/plain")
        resp = await client.post("/api/remote-assets/personal-artifacts/upload", data=data)
        assert resp.status == 200
        assert await resp.json() == {
            "ok": True,
            "items": [
                {
                    "id": "pa-2",
                    "kind": "personal-artifact",
                    "filename": "report.txt",
                    "scope": "project",
                    "projectId": "project-a",
                    "projectName": "项目A",
                }
            ],
        }


@pytest.mark.asyncio
async def test_personal_artifacts_upload_from_session_rejects_workspace_escape(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    outside_file = outside / "report.txt"
    outside_file.write_text("hello", encoding="utf-8")
    monkeypatch.setenv("NANOBOT_AGUI_WORKSPACE_ROOT", str(workspace))
    app = create_app()
    fake_client = FakeRemoteAssetClient()
    app[REMOTE_CENTER_CLIENT_FACTORY_KEY] = lambda frontend_base, api_base: fake_client

    async with TestClient(TestServer(app)) as client:
        await _login_remote(client)
        resp = await client.post(
            "/api/remote-assets/personal-artifacts/upload-from-session",
            json={"scope": "project", "projectId": "project-a", "paths": [str(outside_file)]},
        )
        assert resp.status == 400
        assert await resp.json() == {
            "error": {
                "code": "invalid_upload_source",
                "message": "paths must stay within workspace",
            }
        }


@pytest.mark.asyncio
async def test_personal_artifacts_upload_from_session_reads_workspace_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "workspace"
    output = workspace / "output"
    output.mkdir(parents=True)
    report = output / "report.txt"
    report.write_text("hello", encoding="utf-8")
    monkeypatch.setenv("NANOBOT_AGUI_WORKSPACE_ROOT", str(workspace))
    app = create_app()
    fake_client = FakeRemoteAssetClient()
    app[REMOTE_CENTER_CLIENT_FACTORY_KEY] = lambda frontend_base, api_base: fake_client

    async with TestClient(TestServer(app)) as client:
        await _login_remote(client)
        resp = await client.post(
            "/api/remote-assets/personal-artifacts/upload-from-session",
            json={"scope": "project", "projectId": "project-a", "paths": [str(report)]},
        )
        assert resp.status == 200
        assert await resp.json() == {
            "ok": True,
            "items": [
                {
                    "id": "pa-2",
                    "kind": "personal-artifact",
                    "filename": "report.txt",
                    "scope": "project",
                    "projectId": "project-a",
                    "projectName": "项目A",
                }
            ],
        }
