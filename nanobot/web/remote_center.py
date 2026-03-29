"""Remote delivery center client and in-memory session store."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import json
from typing import Any

import httpx


def _normalize_base_url(value: str) -> str:
    return str(value or "").strip().rstrip("/")


def _response_error_detail(resp: httpx.Response) -> str:
    try:
        payload = resp.json()
    except Exception:
        payload = None
    if isinstance(payload, dict):
        detail = payload.get("detail")
        if isinstance(detail, str) and detail.strip():
            return detail.strip()
        if isinstance(detail, list) and detail:
            return json.dumps(detail, ensure_ascii=False)
        message = payload.get("message")
        if isinstance(message, str) and message.strip():
            return message.strip()
    text = resp.text.strip()
    return text[:500] if text else ""


def _raise_for_status(resp: httpx.Response, *, fallback_message: str) -> None:
    try:
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        detail = _response_error_detail(resp)
        raise ValueError(detail or fallback_message or str(exc)) from exc


def _map_user(raw_user: Any) -> dict[str, str] | None:
    if not isinstance(raw_user, dict):
        return None
    work_id = str(raw_user.get("workId") or raw_user.get("work_id") or "").strip()
    if not work_id:
        return None
    return {
        "workId": work_id,
        "name": str(raw_user.get("name") or work_id),
        "role": str(raw_user.get("role") or "user"),
    }


def _map_projects(raw_projects: Any) -> list[dict[str, str]]:
    projects: list[dict[str, str]] = []
    if not isinstance(raw_projects, list):
        return projects
    for item in raw_projects:
        if isinstance(item, dict):
            project_name = str(item.get("name") or item.get("organization_name") or "").strip()
            project_id = str(item.get("id") or item.get("project_id") or project_name).strip()
        else:
            project_name = str(item or "").strip()
            project_id = project_name
        if not project_name:
            continue
        projects.append({"id": project_id or project_name, "name": project_name})
    return projects


class RemoteCenterClient:
    """Thin HTTP client for the remote delivery center."""

    def __init__(self, frontend_base: str, api_base: str, *, timeout_s: float = 20.0) -> None:
        self.frontend_base = _normalize_base_url(frontend_base)
        self.api_base = _normalize_base_url(api_base)
        self.timeout = timeout_s
        self.token = ""

    async def _post_multipart_json(
        self,
        path: str,
        *,
        data: dict[str, Any] | list[tuple[str, str]],
        files: dict[str, tuple[str, bytes, str]] | list[tuple[str, tuple[str, bytes, str]]],
        token: str = "",
        fallback_message: str,
    ) -> dict[str, Any]:
        auth_token = token or self.token

        def _send() -> dict[str, Any]:
            headers = {"Authorization": f"Bearer {auth_token}"} if auth_token else {}
            form_data: dict[str, str | list[str]]
            if isinstance(data, list):
                form_data = {}
                for key, value in data:
                    current = form_data.get(key)
                    if current is None:
                        form_data[key] = value
                    elif isinstance(current, list):
                        current.append(value)
                    else:
                        form_data[key] = [current, value]
            else:
                form_data = data
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(
                    f"{self.api_base}{path}",
                    data=form_data,
                    files=files,
                    headers=headers,
                )
                _raise_for_status(resp, fallback_message=fallback_message)
                payload = resp.json()
                return payload if isinstance(payload, dict) else {}

        return await asyncio.to_thread(_send)

    async def login(self, *, work_id: str, password: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            login_resp = await client.post(
                f"{self.api_base}/api/auth/login",
                json={"work_id": work_id, "password": password},
            )
            _raise_for_status(login_resp, fallback_message="Remote login failed")
            login_data = login_resp.json()
            token = str(login_data.get("token") or "").strip()
            if not token:
                raise ValueError("Remote login response missing token")
            self.token = token
            user = _map_user(login_data.get("user"))
            projects_resp = await client.get(
                f"{self.api_base}/api/auth/projects",
                headers={"Authorization": f"Bearer {token}"},
            )
            _raise_for_status(projects_resp, fallback_message="Remote projects query failed")
            projects_data = projects_resp.json()
            projects = _map_projects(projects_data.get("organizations") or [])
            return {
                "token": token,
                "user": user,
                "projects": projects,
            }

    async def list_org_skills(self, *, token: str = "") -> list[dict[str, Any]]:
        auth_token = token or self.token
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(
                f"{self.api_base}/api/skills",
                params={"ownership": "organization"},
                headers={"Authorization": f"Bearer {auth_token}"},
            )
            _raise_for_status(resp, fallback_message="Remote organization skills query failed")
            payload = resp.json()
        skills = payload.get("skills") if isinstance(payload, dict) else []
        items: list[dict[str, Any]] = []
        if not isinstance(skills, list):
            return items
        for raw in skills:
            if not isinstance(raw, dict):
                continue
            skill_id = str(raw.get("id") or "").strip()
            if not skill_id:
                continue
            items.append(
                {
                    "id": skill_id,
                    "name": str(raw.get("name") or raw.get("title") or skill_id),
                    "title": str(raw.get("title") or raw.get("name") or skill_id),
                    "description": str(raw.get("description") or ""),
                    "version": str(raw.get("version") or ""),
                    "businessType": str(raw.get("business_type") or raw.get("businessType") or ""),
                    "deliveryType": str(raw.get("delivery_type") or raw.get("deliveryType") or ""),
                    "organizationName": str(raw.get("organization_name") or raw.get("organizationName") or ""),
                    "updatedAt": str(raw.get("update_time") or raw.get("updatedAt") or raw.get("upload_time") or ""),
                    "_raw": raw,
                }
            )
        return items

    async def get_org_skill(self, skill_id: str, *, token: str = "") -> dict[str, Any]:
        items = await self.list_org_skills(token=token)
        for item in items:
            if str(item.get("id")) == str(skill_id):
                raw = item.get("_raw") if isinstance(item.get("_raw"), dict) else {}
                return {
                    "id": str(item["id"]),
                    "kind": "org-skill",
                    "name": str(item["name"]),
                    "title": str(item["title"]),
                    "description": str(item["description"]),
                    "version": str(item["version"]),
                    "businessType": str(item.get("businessType") or raw.get("business_type") or ""),
                    "deliveryType": str(item.get("deliveryType") or raw.get("delivery_type") or ""),
                    "organizationName": str(item["organizationName"]),
                    "uploaderId": str(raw.get("uploader_id") or raw.get("uploaderId") or ""),
                    "updatedAt": str(item["updatedAt"]),
                    "tags": raw.get("tags") if isinstance(raw.get("tags"), list) else [],
                    "canImport": True,
                    "canClone": True,
                }
        raise KeyError(skill_id)

    async def download_org_skill(self, skill_id: str, *, token: str = "", user_id: str) -> bytes:
        auth_token = token or self.token
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(
                f"{self.api_base}/api/skills/{skill_id}/download",
                params={"target": "browser", "user_id": user_id},
                headers={"Authorization": f"Bearer {auth_token}"},
            )
            _raise_for_status(resp, fallback_message="Remote skill download failed")
            return resp.content

    async def clone_org_skill_to_personal(
        self,
        skill_id: str,
        *,
        token: str = "",
        user_id: str = "",
        scope: str,
        project_id: str | None,
    ) -> dict[str, Any]:
        detail = await self.get_org_skill(skill_id, token=token)
        archive = await self.download_org_skill(skill_id, token=token, user_id=user_id)
        project_name = project_id or ""
        data = {
            "title": str(detail["title"]),
            "description": str(detail["description"]),
            "tags": "[]",
            "business_type": str(detail.get("businessType") or "迁移调优"),
            "base_skill_id": str(detail["id"]),
            "base_skill_title": str(detail["title"]),
            "project_name": project_name,
            "uploader_id": user_id,
            "version": str(detail.get("version") or "1.0.0"),
            "source_template_version": str(detail.get("version") or "1.0.0"),
            "organization_name": str(detail.get("organizationName") or project_name or "个人空间"),
        }
        files = {"file": (f"{detail['name']}.zip", archive, "application/zip")}
        payload = await self._post_multipart_json(
            "/api/skills/collected-sync",
            data=data,
            files=files,
            token=token,
            fallback_message="Remote personal skill clone failed",
        )
        return {
            "id": str(payload.get("id") or ""),
            "kind": "personal-skill",
            "title": str(detail["title"]),
            "scope": scope,
            "projectId": project_id,
            "projectName": project_id,
        }

    async def list_personal_skills(
        self,
        *,
        token: str = "",
        scope: str,
        project_id: str | None,
        user_id: str = "",
    ) -> list[dict[str, Any]]:
        auth_token = token or self.token
        params: dict[str, str] = {"ownership": "personal"}
        if project_id:
            params["project_name"] = project_id
        if user_id:
            params["uploader_id"] = user_id
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(
                f"{self.api_base}/api/skills",
                params=params,
                headers={"Authorization": f"Bearer {auth_token}"},
            )
            _raise_for_status(resp, fallback_message="Remote personal skills query failed")
            payload = resp.json()
        skills = payload.get("skills") if isinstance(payload, dict) else []
        items: list[dict[str, Any]] = []
        if not isinstance(skills, list):
            return items
        for raw in skills:
            if not isinstance(raw, dict):
                continue
            items.append(
                {
                    "id": str(raw.get("id") or ""),
                    "kind": "personal-skill",
                    "title": str(raw.get("title") or raw.get("name") or ""),
                    "scope": scope,
                    "projectId": project_id,
                    "projectName": project_id,
                    "sourceType": "zip_file",
                    "updatedAt": str(raw.get("update_time") or raw.get("updatedAt") or ""),
                }
            )
        return items

    async def upload_personal_skill(
        self,
        *,
        token: str = "",
        filename: str,
        content: bytes,
        scope: str,
        project_id: str | None,
        user_id: str = "",
    ) -> dict[str, Any]:
        auth_token = token or self.token
        project_name = project_id or ""
        data = {
            "title": filename,
            "description": "",
            "tags": "[]",
            "business_type": "迁移调优",
            "organization_name": project_name or "个人空间",
            "project_name": project_name,
            "base_skill_id": "0",
            "base_skill_title": "原创",
            "uploader_id": user_id,
            "version": "1.0.0",
            "source_template_version": "1.0.0",
        }
        files = {"file": (filename, content, "application/zip")}
        payload = await self._post_multipart_json(
            "/api/skills/collected-sync",
            data=data,
            files=files,
            token=auth_token,
            fallback_message="Remote personal skill upload failed",
        )
        return {
            "id": str(payload.get("id") or ""),
            "kind": "personal-skill",
            "title": filename,
            "scope": scope,
            "projectId": project_id,
            "projectName": project_id,
        }

    async def list_personal_artifacts(
        self,
        *,
        token: str = "",
        scope: str,
        project_id: str | None,
        user_id: str = "",
    ) -> list[dict[str, Any]]:
        auth_token = token or self.token
        params: dict[str, str] = {}
        if project_id:
            params["project_name"] = project_id
        if user_id:
            params["uploader_id"] = user_id
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(
                f"{self.api_base}/api/validation-data",
                params=params,
                headers={"Authorization": f"Bearer {auth_token}"},
            )
            _raise_for_status(resp, fallback_message="Remote personal artifacts query failed")
            payload = resp.json()
        files = payload.get("validation_data_files") if isinstance(payload, dict) else []
        items: list[dict[str, Any]] = []
        if not isinstance(files, list):
            return items
        for raw in files:
            if not isinstance(raw, dict):
                continue
            items.append(
                {
                    "id": str(raw.get("id") or ""),
                    "kind": "personal-artifact",
                    "filename": str(raw.get("original_filename") or raw.get("filename") or ""),
                    "scope": scope,
                    "projectId": project_id,
                    "projectName": project_id,
                    "sizeBytes": int(raw.get("file_size") or 0),
                    "sourceType": "session_output",
                    "updatedAt": str(raw.get("update_time") or raw.get("updatedAt") or raw.get("upload_time") or ""),
                }
            )
        return items

    async def upload_personal_artifacts(
        self,
        *,
        token: str = "",
        files: list[dict[str, Any]],
        scope: str,
        project_id: str | None,
    ) -> list[dict[str, Any]]:
        auth_token = token or self.token
        data: list[tuple[str, str]] = [("project_name", project_id or "")]
        request_files = []
        for item in files:
            filename = str(item.get("filename") or "file.bin")
            client_file_key = str(item.get("clientFileKey") or filename)
            content = bytes(item.get("content") or b"")
            content_type = str(item.get("contentType") or "application/octet-stream")
            data.append(("client_file_keys", client_file_key))
            request_files.append(("files", (filename, content, content_type)))
        payload = await self._post_multipart_json(
            "/api/validation-data/sync",
            data=data,
            files=request_files,
            token=auth_token,
            fallback_message="Remote personal artifacts upload failed",
        )
        uploaded = payload.get("validation_data_files") if isinstance(payload, dict) else []
        result: list[dict[str, Any]] = []
        if not isinstance(uploaded, list):
            return result
        for raw in uploaded:
            if not isinstance(raw, dict):
                continue
            result.append(
                {
                    "id": str(raw.get("id") or ""),
                    "kind": "personal-artifact",
                    "filename": str(raw.get("original_filename") or raw.get("filename") or ""),
                    "scope": scope,
                    "projectId": project_id,
                    "projectName": project_id,
                }
            )
        return result

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
        token: str = "",
    ) -> dict[str, Any]:
        data: dict[str, Any] = {
            "title": title,
            "description": description,
            "tags": json.dumps(tags, ensure_ascii=False),
            "business_type": business_type,
            "delivery_type": delivery_type,
            "organization_name": organization_name,
            "project_name": project_name or "",
            "base_skill_id": str(base_skill_id),
            "base_skill_title": base_skill_title,
            "uploader_id": uploader_id,
            "version": version,
            "source_template_version": source_template_version,
        }
        if local_last_modified_at:
            data["local_last_modified_at"] = local_last_modified_at
        files = {"file": (filename, content, "application/zip")}
        payload = await self._post_multipart_json(
            "/api/skills/collected-sync",
            data=data,
            files=files,
            token=token,
            fallback_message="Remote skill collect failed",
        )
        return {
            "id": str(payload.get("id") or ""),
            "title": title,
            "projectName": str(project_name or ""),
        }


@dataclass
class RemoteCenterSession:
    connected: bool = False
    frontend_base: str = ""
    api_base: str = ""
    token: str = ""
    user: dict[str, str] | None = None
    projects: list[dict[str, str]] = field(default_factory=list)
    selected_project_id: str | None = None
    selected_project_name: str | None = None
    client: Any = None

    def snapshot(self) -> dict[str, Any]:
        return {
            "connected": self.connected,
            "frontendBase": self.frontend_base,
            "apiBase": self.api_base,
            "user": self.user,
            "projects": self.projects,
            "selectedProjectId": self.selected_project_id,
            "selectedProjectName": self.selected_project_name,
        }


class RemoteCenterSessionStore:
    """Process-local remote session holder for desktop AGUI."""

    def __init__(self) -> None:
        self._session = RemoteCenterSession()

    def snapshot(self) -> dict[str, Any]:
        return self._session.snapshot()

    def is_connected(self) -> bool:
        return self._session.connected

    def token(self) -> str:
        return self._session.token

    def user(self) -> dict[str, str] | None:
        return self._session.user

    def selected_project(self) -> tuple[str | None, str | None]:
        return self._session.selected_project_id, self._session.selected_project_name

    def client(self) -> Any:
        return self._session.client

    def set_session(
        self,
        *,
        frontend_base: str,
        api_base: str,
        token: str,
        user: dict[str, str] | None,
        projects: list[dict[str, str]],
        client: Any,
    ) -> dict[str, Any]:
        self._session = RemoteCenterSession(
            connected=True,
            frontend_base=_normalize_base_url(frontend_base),
            api_base=_normalize_base_url(api_base),
            token=token,
            user=user,
            projects=projects,
            selected_project_id=projects[0]["id"] if len(projects) == 1 else None,
            selected_project_name=projects[0]["name"] if len(projects) == 1 else None,
            client=client,
        )
        return self.snapshot()

    async def clear(self) -> dict[str, Any]:
        close = getattr(self._session.client, "aclose", None)
        if callable(close):
            await close()
        self._session = RemoteCenterSession()
        return {"ok": True}

    def select_project(self, project_id: str) -> dict[str, Any]:
        target = str(project_id or "").strip()
        for item in self._session.projects:
            if item["id"] == target:
                self._session.selected_project_id = item["id"]
                self._session.selected_project_name = item["name"]
                return {
                    "selectedProjectId": item["id"],
                    "selectedProjectName": item["name"],
                }
        raise KeyError(project_id)
