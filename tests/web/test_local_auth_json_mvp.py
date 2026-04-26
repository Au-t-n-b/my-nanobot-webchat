from __future__ import annotations

from pathlib import Path

import pytest
from aiohttp.test_utils import TestClient, TestServer

from nanobot.web.app import create_app
from nanobot.web.local_json_store import ensure_seed_users, read_users, registry_dir


@pytest.fixture(autouse=True)
def _isolated_registry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    reg = tmp_path / "registry"
    reg.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("NANOBOT_REGISTRY_DIR", str(reg))
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)


def test_seed_admin_created(tmp_path: Path) -> None:
    reg = tmp_path / "registry"
    reg.mkdir(parents=True, exist_ok=True)
    ensure_seed_users(reg)
    users = read_users(reg)
    assert any(u.get("employeeNo") == "test" and u.get("roleCode") == "ADMIN" for u in users if isinstance(u, dict))


@pytest.mark.asyncio
async def test_login_then_me() -> None:
    app = create_app()
    async with TestClient(TestServer(app)) as client:
        r = await client.post("/api/auth/login", json={"workId": "test", "password": "test"})
        assert r.status == 200
        body = await r.json()
        token = body.get("token")
        assert isinstance(token, str) and token
        # last login snapshot file should be refreshed on successful login
        p = registry_dir() / "current_login.json"
        assert p.is_file()
        snap = p.read_text(encoding="utf-8")
        assert "test" in snap
        r2 = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert r2.status == 200
        me = await r2.json()
        assert "user" in me


@pytest.mark.asyncio
async def test_me_requires_bearer() -> None:
    app = create_app()
    async with TestClient(TestServer(app)) as client:
        r = await client.get("/api/auth/me")
        assert r.status == 401


@pytest.mark.asyncio
async def test_admin_register_pd_then_login() -> None:
    app = create_app()
    async with TestClient(TestServer(app)) as client:
        lr = await client.post("/api/auth/login", json={"workId": "test", "password": "test"})
        token = (await lr.json())["token"]
        rr = await client.post(
            "/api/auth/register",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "workId": "pd001",
                "realName": "PD One",
                "password": "password123",
                "passwordConfirm": "password123",
                "roleCode": "PD",
            },
        )
        assert rr.status == 201
        lr2 = await client.post("/api/auth/login", json={"workId": "pd001", "password": "password123"})
        assert lr2.status == 200


@pytest.mark.asyncio
async def test_pd_register_member_requires_project_and_stages() -> None:
    app = create_app()
    async with TestClient(TestServer(app)) as client:
        # create PD via admin
        lr = await client.post("/api/auth/login", json={"workId": "test", "password": "test"})
        admin_token = (await lr.json())["token"]
        await client.post(
            "/api/auth/register",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "workId": "pd002",
                "realName": "PD Two",
                "password": "password123",
                "passwordConfirm": "password123",
                "roleCode": "PD",
            },
        )
        lrpd = await client.post("/api/auth/login", json={"workId": "pd002", "password": "password123"})
        pd_token = (await lrpd.json())["token"]

        bad = await client.post(
            "/api/auth/register",
            headers={"Authorization": f"Bearer {pd_token}"},
            json={
                "workId": "m001",
                "realName": "Member",
                "password": "password123",
                "passwordConfirm": "password123",
            },
        )
        assert bad.status == 400


@pytest.mark.asyncio
async def test_pd_register_member_and_list_by_project() -> None:
    app = create_app()
    async with TestClient(TestServer(app)) as client:
        lr = await client.post("/api/auth/login", json={"workId": "test", "password": "test"})
        admin_token = (await lr.json())["token"]
        await client.post(
            "/api/auth/register",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "workId": "pd003",
                "realName": "PD Three",
                "password": "password123",
                "passwordConfirm": "password123",
                "roleCode": "PD",
            },
        )
        lrpd = await client.post("/api/auth/login", json={"workId": "pd003", "password": "password123"})
        pd_token = (await lrpd.json())["token"]

        cr = await client.post(
            "/api/auth/register",
            headers={"Authorization": f"Bearer {pd_token}"},
            json={
                "workId": "m002",
                "realName": "Member2",
                "password": "password123",
                "passwordConfirm": "password123",
                "projectId": "p1",
                "stages": ["设备安装"],
            },
        )
        assert cr.status == 201

        lst = await client.get("/api/admin/members", headers={"Authorization": f"Bearer {pd_token}"}, params={"projectId": "p1"})
        assert lst.status == 200
        body = await lst.json()
        assert body["projectId"] == "p1"
        assert any(m.get("workId") == "m002" for m in body.get("members", []))


@pytest.mark.asyncio
async def test_pd_projects_create_and_list_and_members_scope() -> None:
    """PD can create projects, list only own projects, and members list without projectId is scoped."""
    app = create_app()
    async with TestClient(TestServer(app)) as client:
        # create PD via admin
        lr = await client.post("/api/auth/login", json={"workId": "test", "password": "test"})
        admin_token = (await lr.json())["token"]
        await client.post(
            "/api/auth/register",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "workId": "pd_scope",
                "realName": "PD Scope",
                "password": "password123",
                "passwordConfirm": "password123",
                "roleCode": "PD",
            },
        )
        lrpd = await client.post("/api/auth/login", json={"workId": "pd_scope", "password": "password123"})
        pd_token = (await lrpd.json())["token"]

        # PD creates project
        pr = await client.post(
            "/api/projects",
            headers={"Authorization": f"Bearer {pd_token}"},
            json={"name": "项目A"},
        )
        assert pr.status == 201
        proj = (await pr.json()).get("project") or {}
        pid = proj.get("projectId")
        assert isinstance(pid, str) and pid

        # PD lists projects (should include only own)
        pl = await client.get("/api/projects", headers={"Authorization": f"Bearer {pd_token}"})
        assert pl.status == 200
        projects = (await pl.json()).get("projects") or []
        assert any(p.get("projectId") == pid for p in projects if isinstance(p, dict))

        # PD creates member under that project
        cr = await client.post(
            "/api/auth/register",
            headers={"Authorization": f"Bearer {pd_token}"},
            json={
                "workId": "m_scope",
                "realName": "Member Scope",
                "password": "password123",
                "passwordConfirm": "password123",
                "projectId": pid,
                "stages": ["设备安装"],
            },
        )
        assert cr.status == 201

        # PD list members without projectId: should include the member
        ml = await client.get("/api/admin/members", headers={"Authorization": f"Bearer {pd_token}"})
        assert ml.status == 200
        body = await ml.json()
        assert body.get("projectId") in (None, "")
        assert any(m.get("workId") == "m_scope" for m in body.get("members", []))

