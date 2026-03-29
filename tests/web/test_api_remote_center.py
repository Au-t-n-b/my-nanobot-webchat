"""Tests for remote center session endpoints."""

from __future__ import annotations

from aiohttp.test_utils import TestClient, TestServer
import pytest

from nanobot.web.app import create_app
from nanobot.web.keys import REMOTE_CENTER_CLIENT_FACTORY_KEY


class FakeRemoteCenterClient:
    def __init__(self) -> None:
        self.login_calls: list[dict[str, str]] = []
        self.projects = [
            {"id": "project-a", "name": "项目A"},
            {"id": "project-b", "name": "项目B"},
        ]

    async def login(self, *, work_id: str, password: str) -> dict[str, object]:
        self.login_calls.append({"work_id": work_id, "password": password})
        return {
            "token": "remote-token",
            "user": {
                "workId": work_id,
                "name": "测试用户",
                "role": "user",
            },
            "projects": self.projects,
        }


class SingleProjectRemoteCenterClient(FakeRemoteCenterClient):
    def __init__(self) -> None:
        super().__init__()
        self.projects = [{"id": "project-a", "name": "项目A"}]


@pytest.mark.asyncio
async def test_remote_center_session_returns_disconnected_by_default() -> None:
    app = create_app()
    async with TestClient(TestServer(app)) as client:
        resp = await client.get("/api/remote-center/session")
        assert resp.status == 200
        assert await resp.json() == {
            "connected": False,
            "frontendBase": "",
            "apiBase": "",
            "user": None,
            "projects": [],
            "selectedProjectId": None,
            "selectedProjectName": None,
        }


@pytest.mark.asyncio
async def test_remote_center_login_returns_session_snapshot() -> None:
    app = create_app()
    fake_client = FakeRemoteCenterClient()
    app[REMOTE_CENTER_CLIENT_FACTORY_KEY] = lambda frontend_base, api_base: fake_client

    async with TestClient(TestServer(app)) as client:
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
        assert await resp.json() == {
            "connected": True,
            "frontendBase": "http://127.0.0.1:3000",
            "apiBase": "http://127.0.0.1:8000",
            "user": {
                "workId": "j00954996",
                "name": "测试用户",
                "role": "user",
            },
            "projects": [
                {"id": "project-a", "name": "项目A"},
                {"id": "project-b", "name": "项目B"},
            ],
            "selectedProjectId": None,
            "selectedProjectName": None,
        }
        assert fake_client.login_calls == [{"work_id": "j00954996", "password": "123456"}]


@pytest.mark.asyncio
async def test_remote_center_login_auto_selects_only_project() -> None:
    app = create_app()
    fake_client = SingleProjectRemoteCenterClient()
    app[REMOTE_CENTER_CLIENT_FACTORY_KEY] = lambda frontend_base, api_base: fake_client

    async with TestClient(TestServer(app)) as client:
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
        assert await resp.json() == {
            "connected": True,
            "frontendBase": "http://127.0.0.1:3000",
            "apiBase": "http://127.0.0.1:8000",
            "user": {
                "workId": "j00954996",
                "name": "测试用户",
                "role": "user",
            },
            "projects": [{"id": "project-a", "name": "项目A"}],
            "selectedProjectId": "project-a",
            "selectedProjectName": "项目A",
        }


@pytest.mark.asyncio
async def test_remote_center_project_switch_requires_existing_session() -> None:
    app = create_app()
    async with TestClient(TestServer(app)) as client:
        resp = await client.post("/api/remote-center/project", json={"projectId": "project-a"})
        assert resp.status == 400
        assert await resp.json() == {
            "error": {
                "code": "remote_not_connected",
                "message": "Remote center session not established",
            }
        }


@pytest.mark.asyncio
async def test_remote_center_logout_clears_session() -> None:
    app = create_app()
    fake_client = FakeRemoteCenterClient()
    app[REMOTE_CENTER_CLIENT_FACTORY_KEY] = lambda frontend_base, api_base: fake_client

    async with TestClient(TestServer(app)) as client:
        login_resp = await client.post(
            "/api/remote-center/login",
            json={
                "frontendBase": "http://127.0.0.1:3000",
                "apiBase": "http://127.0.0.1:8000",
                "workId": "j00954996",
                "password": "123456",
            },
        )
        assert login_resp.status == 200

        logout_resp = await client.post("/api/remote-center/logout")
        assert logout_resp.status == 200
        assert await logout_resp.json() == {"ok": True}

        session_resp = await client.get("/api/remote-center/session")
        assert session_resp.status == 200
        assert await session_resp.json() == {
            "connected": False,
            "frontendBase": "",
            "apiBase": "",
            "user": None,
            "projects": [],
            "selectedProjectId": None,
            "selectedProjectName": None,
        }
