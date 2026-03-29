"""Tests for the remote center HTTP client."""

from __future__ import annotations

import io
import zipfile

from aiohttp import web
import pytest

from nanobot.web.remote_center import RemoteCenterClient


async def _start_remote_app(app: web.Application) -> tuple[web.AppRunner, str]:
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    sockets = site._server.sockets  # type: ignore[attr-defined]
    assert sockets
    port = sockets[0].getsockname()[1]
    return runner, f"http://127.0.0.1:{port}"


@pytest.mark.asyncio
async def test_upload_personal_artifacts_posts_multipart_payload() -> None:
    captured: dict[str, object] = {}

    async def sync_validation_data(request: web.Request) -> web.Response:
        form = await request.post()
        captured["project_name"] = form.get("project_name")
        captured["client_file_keys"] = form.getall("client_file_keys")
        uploads = form.getall("files")
        captured["filenames"] = [upload.filename for upload in uploads]
        captured["contents"] = [upload.file.read() for upload in uploads]
        return web.json_response(
            {
                "validation_data_files": [
                    {
                        "id": 9,
                        "original_filename": "report.txt",
                        "filename": "report.txt",
                    }
                ]
            }
        )

    app = web.Application()
    app.router.add_post("/api/validation-data/sync", sync_validation_data)
    runner, api_base = await _start_remote_app(app)

    try:
        client = RemoteCenterClient("http://frontend.example", api_base)
        client.token = "remote-token"
        items = await client.upload_personal_artifacts(
            files=[
                {
                    "filename": "report.txt",
                    "clientFileKey": "artifact-report",
                    "content": b"hello",
                    "contentType": "text/plain",
                }
            ],
            scope="project",
            project_id="project-a",
        )
    finally:
        await runner.cleanup()

    assert items == [
        {
            "id": "9",
            "kind": "personal-artifact",
            "filename": "report.txt",
            "scope": "project",
            "projectId": "project-a",
            "projectName": "project-a",
        }
    ]
    assert captured == {
        "project_name": "project-a",
        "client_file_keys": ["artifact-report"],
        "filenames": ["report.txt"],
        "contents": [b"hello"],
    }


@pytest.mark.asyncio
async def test_upload_personal_skill_sends_required_remote_fields() -> None:
    captured: dict[str, object] = {}

    async def sync_collected_skill(request: web.Request) -> web.Response:
        form = await request.post()
        for key in (
            "title",
            "business_type",
            "organization_name",
            "project_name",
            "base_skill_id",
            "base_skill_title",
            "uploader_id",
            "file",
        ):
            assert form.get(key) is not None, f"missing field: {key}"
        upload = form["file"]
        assert hasattr(upload, "file")
        archive = zipfile.ZipFile(io.BytesIO(upload.file.read()))
        assert archive.namelist() == ["SKILL.md", "_meta.json"]
        captured["business_type"] = form["business_type"]
        captured["organization_name"] = form["organization_name"]
        captured["project_name"] = form["project_name"]
        captured["base_skill_id"] = form["base_skill_id"]
        captured["base_skill_title"] = form["base_skill_title"]
        captured["uploader_id"] = form["uploader_id"]
        return web.json_response({"id": 11})

    app = web.Application()
    app.router.add_post("/api/skills/collected-sync", sync_collected_skill)
    runner, api_base = await _start_remote_app(app)

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("SKILL.md", "# Demo\n")
        zf.writestr("_meta.json", "{}")

    try:
        client = RemoteCenterClient("http://frontend.example", api_base)
        client.token = "remote-token"
        item = await client.upload_personal_skill(
            filename="demo-skill.zip",
            content=buffer.getvalue(),
            scope="project",
            project_id="project-a",
            user_id="u001",
        )
    finally:
        await runner.cleanup()

    assert item == {
        "id": "11",
        "kind": "personal-skill",
        "title": "demo-skill.zip",
        "scope": "project",
        "projectId": "project-a",
        "projectName": "project-a",
    }
    assert captured == {
        "business_type": "迁移调优",
        "organization_name": "project-a",
        "project_name": "project-a",
        "base_skill_id": "0",
        "base_skill_title": "原创",
        "uploader_id": "u001",
    }


@pytest.mark.asyncio
async def test_clone_org_skill_to_personal_uses_download_archive_and_required_fields() -> None:
    captured: dict[str, object] = {"download_calls": []}

    archive_buffer = io.BytesIO()
    with zipfile.ZipFile(archive_buffer, "w") as zf:
        zf.writestr("SKILL.md", "# Cloned\n")
        zf.writestr("_meta.json", "{}")
    archive_bytes = archive_buffer.getvalue()

    async def list_org_skills(request: web.Request) -> web.Response:
        assert request.query.get("ownership") == "organization"
        return web.json_response(
            {
                "skills": [
                    {
                        "id": 101,
                        "name": "report-gen",
                        "title": "工勘报告生成",
                        "description": "自动生成工勘报告",
                        "version": "1.0.0",
                        "organization_name": "交付中心",
                        "business_type": "迁移调优",
                        "update_time": "2026-03-28T10:00:00Z",
                        "uploader_id": "admin",
                        "tags": ["report"],
                    }
                ]
            }
        )

    async def download_org_skill(request: web.Request) -> web.Response:
        captured["download_calls"].append(dict(request.query))
        return web.Response(body=archive_bytes, content_type="application/zip")

    async def sync_collected_skill(request: web.Request) -> web.Response:
        form = await request.post()
        upload = form["file"]
        assert hasattr(upload, "file")
        zipfile.ZipFile(io.BytesIO(upload.file.read()))
        captured["business_type"] = form["business_type"]
        captured["organization_name"] = form["organization_name"]
        captured["project_name"] = form["project_name"]
        captured["base_skill_id"] = form["base_skill_id"]
        captured["base_skill_title"] = form["base_skill_title"]
        captured["uploader_id"] = form["uploader_id"]
        return web.json_response({"id": 12})

    app = web.Application()
    app.router.add_get("/api/skills", list_org_skills)
    app.router.add_get("/api/skills/{skill_id}/download", download_org_skill)
    app.router.add_post("/api/skills/collected-sync", sync_collected_skill)
    runner, api_base = await _start_remote_app(app)

    try:
        client = RemoteCenterClient("http://frontend.example", api_base)
        client.token = "remote-token"
        item = await client.clone_org_skill_to_personal(
            "101",
            scope="project",
            project_id="project-a",
            user_id="u001",
        )
    finally:
        await runner.cleanup()

    assert item == {
        "id": "12",
        "kind": "personal-skill",
        "title": "工勘报告生成",
        "scope": "project",
        "projectId": "project-a",
        "projectName": "project-a",
    }
    assert captured == {
        "download_calls": [{"target": "browser", "user_id": "u001"}],
        "business_type": "迁移调优",
        "organization_name": "交付中心",
        "project_name": "project-a",
        "base_skill_id": "101",
        "base_skill_title": "工勘报告生成",
        "uploader_id": "u001",
    }


@pytest.mark.asyncio
async def test_collect_skill_to_remote_posts_collected_sync_payload() -> None:
    captured: dict[str, object] = {}

    async def sync_collected_skill(request: web.Request) -> web.Response:
        form = await request.post()
        upload = form["file"]
        assert hasattr(upload, "file")
        zipfile.ZipFile(io.BytesIO(upload.file.read()))
        for key in (
            "title",
            "description",
            "tags",
            "business_type",
            "delivery_type",
            "organization_name",
            "project_name",
            "base_skill_id",
            "base_skill_title",
            "uploader_id",
            "version",
            "source_template_version",
            "local_last_modified_at",
        ):
            captured[key] = form[key]
        return web.json_response({"id": 21})

    app = web.Application()
    app.router.add_post("/api/skills/collected-sync", sync_collected_skill)
    runner, api_base = await _start_remote_app(app)

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("SKILL.md", "# Demo\n")
        zf.writestr("_meta.json", "{}")

    try:
        client = RemoteCenterClient("http://frontend.example", api_base)
        client.token = "remote-token"
        item = await client.collect_skill_to_remote(
            filename="report-gen.zip",
            content=buffer.getvalue(),
            title="工勘报告生成",
            description="回流技能",
            tags=["report", "remote"],
            business_type="迁移调优",
            delivery_type="标准交付",
            organization_name="交付中心",
            project_name="project-a",
            uploader_id="u001",
            version="1.1.0",
            source_template_version="1.0.0",
            local_last_modified_at="2026-03-29T10:00:00Z",
            base_skill_id=101,
            base_skill_title="工勘报告生成",
        )
    finally:
        await runner.cleanup()

    assert item == {
        "id": "21",
        "title": "工勘报告生成",
        "projectName": "project-a",
    }
    assert captured == {
        "title": "工勘报告生成",
        "description": "回流技能",
        "tags": '["report", "remote"]',
        "business_type": "迁移调优",
        "delivery_type": "标准交付",
        "organization_name": "交付中心",
        "project_name": "project-a",
        "base_skill_id": "101",
        "base_skill_title": "工勘报告生成",
        "uploader_id": "u001",
        "version": "1.1.0",
        "source_template_version": "1.0.0",
        "local_last_modified_at": "2026-03-29T10:00:00Z",
    }
