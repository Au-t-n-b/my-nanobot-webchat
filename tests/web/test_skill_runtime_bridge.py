"""Tests for standardized skill runtime event bridging."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from uuid import uuid4

import pytest
from aiohttp.test_utils import TestClient, TestServer

from nanobot.config import loader as config_loader
from nanobot.web.app import create_app
from nanobot.web.mission_control import ChatCardHandle


def _set_nanobot_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    config_path = tmp_path / ".nanobot" / "config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(config_loader, "_current_config_path", config_path)
    return config_path.parent


@pytest.fixture()
def local_tmp_dir() -> Path:
    root = Path(__file__).resolve().parents[2] / ".tmp" / "pytest-skill-runtime-bridge"
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"case-{uuid4().hex}"
    path.mkdir(parents=True)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def _first_sse_data(body: str, event_name: str) -> dict | None:
    blocks = body.split("\n\n")
    for block in blocks:
        lines = [ln.strip() for ln in block.strip().split("\n") if ln.strip()]
        ev = None
        data_line = None
        for ln in lines:
            if ln.startswith("event:"):
                ev = ln[len("event:") :].strip()
            elif ln.startswith("data:"):
                data_line = ln[len("data:") :].strip()
        if ev == event_name and data_line:
            return json.loads(data_line)
    return None


@pytest.mark.asyncio
async def test_emit_guidance_event_uses_mission_control(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    async def fake_emit_guidance(self, context, actions, **kwargs):
        captured["context"] = context
        captured["actions"] = actions
        captured.update(kwargs)
        return ChatCardHandle(card_id="guide-card", doc_id="chat:t-runtime")

    monkeypatch.setattr(
        "nanobot.web.mission_control.MissionControlManager.emit_guidance",
        fake_emit_guidance,
    )

    from nanobot.web.skill_runtime_bridge import emit_skill_runtime_event

    result = await emit_skill_runtime_event(
        envelope={
            "event": "chat.guidance",
            "payload": {
                "context": "准备进入下一步",
                "actions": [{"label": "继续", "verb": "proceed"}],
                "cardId": "guide:runtime",
            },
        },
        thread_id="t-runtime",
        docman=None,
    )

    assert result["ok"] is True
    assert result["event"] == "chat.guidance"
    assert captured["context"] == "准备进入下一步"
    assert captured["actions"] == [{"label": "继续", "verb": "proceed"}]
    assert captured["card_id"] == "guide:runtime"


@pytest.mark.asyncio
async def test_emit_file_request_event_uses_mission_control(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    async def fake_ask_for_file(self, **kwargs):
        captured.update(kwargs)
        return ChatCardHandle(card_id="upload-card", doc_id="chat:t-runtime")

    monkeypatch.setattr(
        "nanobot.web.mission_control.MissionControlManager.ask_for_file",
        fake_ask_for_file,
    )

    from nanobot.web.skill_runtime_bridge import emit_skill_runtime_event

    result = await emit_skill_runtime_event(
        envelope={
            "event": "hitl.file_request",
            "payload": {
                "purpose": "smart-survey-input",
                "title": "请上传输入件",
                "accept": ".xlsx,.zip",
                "multiple": True,
                "saveRelativeDir": "skills/gongkan_skill/input",
                "resumeAction": "run_step1",
                "requestId": "req-upload-bridge-1",
                "cardId": "upload:runtime",
                "skillName": "gongkan_skill",
                "stateNamespace": "gongkan_skill",
                "stepId": "prepare_inputs",
            },
        },
        thread_id="t-runtime",
        docman=None,
    )

    assert result["ok"] is True
    assert result["event"] == "hitl.file_request"
    assert captured["purpose"] == "smart-survey-input"
    assert captured["title"] == "请上传输入件"
    assert captured["accept"] == ".xlsx,.zip"
    assert captured["multiple"] is True
    assert captured["save_relative_dir"] == "skills/gongkan_skill/input"
    assert captured["next_action"] == "run_step1"
    assert captured["card_id"] == "upload:runtime"
    assert captured["skill_name"] == "gongkan_skill"
    assert captured["state_namespace"] == "gongkan_skill"
    assert captured["step_id"] == "prepare_inputs"
    assert captured.get("hitl_request_id") == "req-upload-bridge-1"


@pytest.mark.asyncio
async def test_emit_file_request_persists_pending_hitl_before_rendering(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    async def fake_ask_for_file(self, **kwargs):
        captured.update(kwargs)
        return ChatCardHandle(card_id="upload-card", doc_id="chat:t-runtime")

    monkeypatch.setattr(
        "nanobot.web.mission_control.MissionControlManager.ask_for_file",
        fake_ask_for_file,
    )

    from nanobot.web.pending_hitl_store import PendingHitlStore
    from nanobot.web.skill_runtime_bridge import dispatch_skill_runtime_intent

    store = PendingHitlStore(tmp_path / "hitl.db")
    await store.init()

    intent = {
        "type": "chat_card_intent",
        "verb": "skill_runtime_event",
        "payload": {
            "event": "hitl.file_request",
            "threadId": "t-runtime",
            "skillName": "gongkan_skill",
            "skillRunId": "run-1",
            "payload": {
                "requestId": "req-file-1",
                "purpose": "smart-survey-input",
                "title": "请上传输入件",
                "accept": ".xlsx,.zip",
                "multiple": True,
                "saveRelativeDir": "skills/gongkan_skill/input",
                "resumeAction": "run_step1",
                "onCancelAction": "cancel_step1_upload",
                "cardId": "upload:runtime",
                "skillName": "gongkan_skill",
                "stateNamespace": "gongkan_skill",
                "stepId": "prepare_inputs",
                "expiresAt": int(1e15),
            },
        },
    }

    handled, message = await dispatch_skill_runtime_intent(
        intent,
        thread_id="t-runtime",
        docman=None,
        pending_hitl_store=store,
    )
    assert handled is True
    assert "请上传输入件" in message
    assert captured["card_id"] == "upload:runtime"
    assert captured.get("hitl_request_id") == "req-file-1"

    pending = await store.get_pending_request("req-file-1")
    assert pending is not None
    assert pending["request_id"] == "req-file-1"
    assert pending["status"] == "pending"
    assert pending["thread_id"] == "t-runtime"
    assert pending["skill_name"] == "gongkan_skill"
    assert pending["resume_action"] == "run_step1"


@pytest.mark.asyncio
async def test_emit_choice_request_persists_pending_hitl_before_rendering(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    async def fake_emit_choices(self, title, options, **kwargs):
        captured["title"] = title
        captured["options"] = options
        captured.update(kwargs)
        return ChatCardHandle(card_id="choice-card", doc_id="chat:t-runtime")

    monkeypatch.setattr(
        "nanobot.web.mission_control.MissionControlManager.emit_choices",
        fake_emit_choices,
    )

    from nanobot.web.pending_hitl_store import PendingHitlStore
    from nanobot.web.skill_runtime_bridge import dispatch_skill_runtime_intent

    store = PendingHitlStore(tmp_path / "hitl.db")
    await store.init()

    intent = {
        "type": "chat_card_intent",
        "verb": "skill_runtime_event",
        "payload": {
            "event": "hitl.choice_request",
            "threadId": "t-runtime",
            "skillName": "gongkan_skill",
            "skillRunId": "run-1",
            "payload": {
                "requestId": "req-choice-1",
                "cardId": "choice:runtime",
                "title": "请选择本次建模目标",
                "options": [{"id": "md", "label": "生成 Markdown"}],
                "resumeAction": "after_choice",
                "onCancelAction": "cancel_choice",
                "skillName": "gongkan_skill",
                "stateNamespace": "gongkan_skill",
                "stepId": "choose_goal",
                "expiresAt": int(1e15),
            },
        },
    }

    handled, msg = await dispatch_skill_runtime_intent(
        intent,
        thread_id="t-runtime",
        docman=None,
        pending_hitl_store=store,
    )
    assert handled is True
    assert "请选择本次建模目标" in msg
    assert captured["card_id"] == "choice:runtime"
    assert captured.get("hitl_request_id") == "req-choice-1"

    pending = await store.get_pending_request("req-choice-1")
    assert pending is not None
    assert pending["status"] == "pending"
    assert pending["resume_action"] == "after_choice"


@pytest.mark.asyncio
async def test_emit_confirm_request_persists_pending_hitl_before_rendering(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    async def fake_emit_confirm(self, title, *, confirm_label, cancel_label, **kwargs):
        captured["title"] = title
        captured["confirm_label"] = confirm_label
        captured["cancel_label"] = cancel_label
        captured.update(kwargs)
        return ChatCardHandle(card_id="confirm-card", doc_id="chat:t-runtime")

    monkeypatch.setattr(
        "nanobot.web.mission_control.MissionControlManager.emit_confirm",
        fake_emit_confirm,
    )

    from nanobot.web.pending_hitl_store import PendingHitlStore
    from nanobot.web.skill_runtime_bridge import dispatch_skill_runtime_intent

    store = PendingHitlStore(tmp_path / "hitl.db")
    await store.init()

    intent = {
        "type": "chat_card_intent",
        "verb": "skill_runtime_event",
        "payload": {
            "event": "hitl.confirm_request",
            "threadId": "t-runtime",
            "skillName": "gongkan_skill",
            "skillRunId": "run-1",
            "payload": {
                "requestId": "req-confirm-1",
                "cardId": "confirm:runtime",
                "title": "审批通过后是否继续？",
                "confirmLabel": "继续",
                "cancelLabel": "稍后处理",
                "resumeAction": "approval_pass",
                "onCancelAction": "approval_defer",
                "skillName": "gongkan_skill",
                "stateNamespace": "gongkan_skill",
                "stepId": "approve",
                "expiresAt": int(1e15),
            },
        },
    }

    handled, msg = await dispatch_skill_runtime_intent(
        intent,
        thread_id="t-runtime",
        docman=None,
        pending_hitl_store=store,
    )
    assert handled is True
    assert "审批通过后是否继续" in msg
    assert captured["card_id"] == "confirm:runtime"
    assert captured.get("hitl_request_id") == "req-confirm-1"
    assert captured["confirm_label"] == "继续"
    assert captured["cancel_label"] == "稍后处理"

    pending = await store.get_pending_request("req-confirm-1")
    assert pending is not None
    assert pending["status"] == "pending"
    assert pending["resume_action"] == "approval_pass"


@pytest.mark.asyncio
async def test_emit_dashboard_patch_uses_skill_ui_patch_channel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[dict] = []

    async def capture(payload: dict) -> None:
        captured.append(payload)

    monkeypatch.setattr("nanobot.agent.loop.emit_skill_ui_data_patch_event", capture)

    from nanobot.web.skill_runtime_bridge import emit_skill_runtime_event

    result = await emit_skill_runtime_event(
        envelope={
            "event": "dashboard.patch",
            "payload": {
                "syntheticPath": "skill-ui://SduiView?dataFile=skills/gongkan_skill/data/dashboard.json",
                "docId": "dashboard:gongkan",
                "ops": [
                    {
                        "op": "merge",
                        "target": {"by": "id", "nodeId": "summary-text"},
                        "value": {"type": "Text", "content": "已完成准备"},
                    }
                ],
            },
        },
        thread_id="t-runtime",
        docman=None,
    )

    assert result["ok"] is True
    assert result["event"] == "dashboard.patch"
    assert len(captured) == 1
    payload = captured[0]
    assert payload["syntheticPath"] == "skill-ui://SduiView?dataFile=skills/gongkan_skill/data/dashboard.json"
    patch = payload["patch"]
    assert patch["docId"] == "dashboard:gongkan"
    assert patch["type"] == "SduiPatch"
    assert patch["ops"][0]["target"]["nodeId"] == "summary-text"


@pytest.mark.asyncio
async def test_emit_dashboard_bootstrap_uses_bootstrap_channel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[dict] = []

    async def capture(payload: dict) -> None:
        captured.append(payload)

    monkeypatch.setattr("nanobot.agent.loop.emit_skill_ui_bootstrap_event", capture)

    from nanobot.web.skill_runtime_bridge import emit_skill_runtime_event

    document = {
        "schemaVersion": 1,
        "type": "SduiDocument",
        "root": {"type": "Text", "id": "summary-text", "content": "hello"},
    }
    result = await emit_skill_runtime_event(
        envelope={
            "event": "dashboard.bootstrap",
            "payload": {
                "syntheticPath": "skill-ui://SduiView?dataFile=skills/gongkan_skill/data/dashboard.json",
                "docId": "dashboard:gongkan",
                "document": document,
            },
        },
        thread_id="t-runtime",
        docman=None,
    )

    assert result["ok"] is True
    assert result["event"] == "dashboard.bootstrap"
    assert captured == [
        {
            "syntheticPath": "skill-ui://SduiView?dataFile=skills/gongkan_skill/data/dashboard.json",
            "document": document,
            "docId": "dashboard:gongkan",
        }
    ]


@pytest.mark.asyncio
async def test_emit_artifact_publish_appends_all_items(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []

    # Keep signature aligned with MissionControlManager.add_artifact(doc_id, *, synthetic_path, ...)
    async def fake_add_artifact(self, doc_id, *, synthetic_path, **kwargs):
        calls.append({"synthetic_path": synthetic_path, "doc_id": doc_id, **kwargs})

    monkeypatch.setattr(
        "nanobot.web.mission_control.MissionControlManager.add_artifact",
        fake_add_artifact,
    )

    from nanobot.web.skill_runtime_bridge import emit_skill_runtime_event

    result = await emit_skill_runtime_event(
        envelope={
            "event": "artifact.publish",
            "payload": {
                "syntheticPath": "skill-ui://SduiView?dataFile=skills/gongkan_skill/data/dashboard.json",
                "docId": "dashboard:gongkan",
                "artifactsNodeId": "uploaded-files",
                "items": [
                    {
                        "artifactId": "a1",
                        "label": "输入资料.zip",
                        "path": "workspace/skills/gongkan_skill/input/输入资料.zip",
                        "kind": "archive",
                        "status": "ready",
                    },
                    {
                        "artifactId": "a2",
                        "label": "工勘报告.docx",
                        "path": "workspace/skills/gongkan_skill/output/工勘报告.docx",
                        "kind": "doc",
                        "status": "ready",
                    },
                ],
            },
        },
        thread_id="t-runtime",
        docman=None,
    )

    assert result["ok"] is True
    assert result["event"] == "artifact.publish"
    assert len(calls) == 2
    assert calls[0]["doc_id"] == "dashboard:gongkan"
    assert calls[0]["artifacts_node_id"] == "uploaded-files"
    assert calls[1]["label"] == "工勘报告.docx"


@pytest.mark.asyncio
async def test_emit_task_progress_sync_normalizes_and_emits_status(
    local_tmp_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_nanobot_home(monkeypatch, local_tmp_dir)
    captured: list[dict] = []

    async def capture(payload: dict) -> None:
        captured.append(payload)

    monkeypatch.setattr("nanobot.agent.loop.emit_task_status_event", capture)

    from nanobot.web.skill_runtime_bridge import emit_skill_runtime_event

    result = await emit_skill_runtime_event(
        envelope={
            "event": "task_progress.sync",
            "payload": {
                "updatedAt": 1774659000,
                "progress": [
                    {
                        "moduleId": "m_gk",
                        "moduleName": "智慧工勘",
                        "tasks": [
                            {"name": "输入准备", "completed": True},
                            {"name": "报告生成", "completed": False},
                        ],
                    }
                ],
            },
        },
        thread_id="t-runtime",
        docman=None,
    )

    assert result["ok"] is True
    assert result["event"] == "task_progress.sync"
    assert len(captured) == 1
    assert captured[0]["overall"] == {"doneCount": 0, "totalCount": 1}
    assert captured[0]["summary"]["activeCount"] == 1
    assert captured[0]["modules"][0]["name"] == "智慧工勘"


@pytest.mark.asyncio
async def test_emit_unsupported_event_raises_value_error() -> None:
    from nanobot.web.skill_runtime_bridge import emit_skill_runtime_event

    with pytest.raises(ValueError, match="unsupported skill runtime event"):
        await emit_skill_runtime_event(
            envelope={"event": "hitl.unknown_request", "payload": {}},
            thread_id="t-runtime",
            docman=None,
        )


@pytest.mark.asyncio
async def test_dispatch_skill_runtime_intent_executes_bridge(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[dict] = []

    async def fake_emit_skill_runtime_event(**kwargs):
        captured.append(kwargs)
        return {"ok": True, "summary": "runtime bridge ok", "event": "chat.guidance"}

    monkeypatch.setattr(
        "nanobot.web.skill_runtime_bridge.emit_skill_runtime_event",
        fake_emit_skill_runtime_event,
    )

    from nanobot.web.skill_runtime_bridge import dispatch_skill_runtime_intent

    handled, message = await dispatch_skill_runtime_intent(
        {
            "type": "chat_card_intent",
            "verb": "skill_runtime_event",
            "payload": {
                "event": "chat.guidance",
                "payload": {"context": "继续", "actions": []},
            },
        },
        thread_id="t-runtime",
        docman=None,
    )

    assert handled is True
    assert message == "runtime bridge ok"
    assert len(captured) == 1
    assert captured[0]["thread_id"] == "t-runtime"
    assert captured[0]["envelope"]["event"] == "chat.guidance"


@pytest.mark.asyncio
async def test_dispatch_skill_runtime_start_invokes_resume_runner_once() -> None:
    from nanobot.web.skill_runtime_bridge import dispatch_skill_runtime_intent

    resumed: list[dict] = []

    async def fake_resume(**kwargs):
        resumed.append(kwargs)
        return {"ok": True}

    intent = {
        "type": "chat_card_intent",
        "verb": "skill_runtime_start",
        "payload": {
            "type": "skill_runtime_start",
            "threadId": "t-runtime",
            "skillName": "gongkan_skill",
            "requestId": "req-start-1",
            "action": "zhgk_step1_scene_filter",
        },
    }

    handled, msg = await dispatch_skill_runtime_intent(
        intent,
        thread_id="t-runtime",
        docman=None,
        pending_hitl_store=None,
        resume_runner=fake_resume,
    )

    assert handled is True
    assert "resumed" in msg
    assert len(resumed) == 1
    assert resumed[0]["thread_id"] == "t-runtime"
    assert resumed[0]["skill_name"] == "gongkan_skill"
    assert resumed[0]["request_id"] == "req-start-1"
    assert resumed[0]["action"] == "zhgk_step1_scene_filter"
    assert resumed[0]["status"] == "ok"


@pytest.mark.asyncio
async def test_dispatch_skill_runtime_result_intent_consumes_pending_hitl_idempotently(
    tmp_path: Path,
) -> None:
    from nanobot.web.pending_hitl_store import PendingHitlStore
    from nanobot.web.skill_runtime_bridge import dispatch_skill_runtime_intent

    store = PendingHitlStore(tmp_path / "hitl.db")
    await store.init()
    await store.create_pending_request(
        {
            "event": "hitl.file_request",
            "threadId": "t-runtime",
            "skillName": "gongkan_skill",
            "skillRunId": "run-1",
            "payload": {
                "requestId": "req-1",
                "resumeAction": "run_step1",
                "onCancelAction": "cancel_step1_upload",
                "expiresAt": int(1e15),
                "title": "请上传输入件",
            },
        }
    )

    intent = {
        "type": "chat_card_intent",
        "verb": "skill_runtime_result",
        "payload": {
            "type": "skill_runtime_result",
            "threadId": "t-runtime",
            "skillName": "gongkan_skill",
            "skillRunId": "run-2",
            "requestId": "req-1",
            "action": "run_step1",
            "status": "ok",
            "result": {"files": [{"fileId": "f1"}]},
        },
    }

    handled_1, msg_1 = await dispatch_skill_runtime_intent(
        intent, thread_id="t-runtime", docman=None, pending_hitl_store=store
    )
    handled_2, msg_2 = await dispatch_skill_runtime_intent(
        intent, thread_id="t-runtime", docman=None, pending_hitl_store=store
    )

    assert handled_1 is True
    assert "consumed" in msg_1
    assert handled_2 is True
    assert "duplicate" in msg_2


@pytest.mark.asyncio
async def test_dispatch_skill_runtime_result_rejects_invalid_payload_before_store() -> None:
    calls: list[dict] = []

    class _FakeStore:
        async def timeout_expired_requests(self, *args, **kwargs):
            return {"timed_out_request_ids": []}

        async def consume_result(self, payload):
            calls.append(payload)
            return {"ok": True, "duplicate": False, "terminal_status": "consumed"}

    from nanobot.web.skill_runtime_bridge import dispatch_skill_runtime_intent

    handled, msg = await dispatch_skill_runtime_intent(
        {
            "type": "chat_card_intent",
            "verb": "skill_runtime_result",
            "payload": {
                # missing type/threadId/skillName/requestId
                "status": "wat",  # invalid
            },
        },
        thread_id="t-runtime",
        docman=None,
        pending_hitl_store=_FakeStore(),
    )

    assert handled is True
    # Error message may be localized / encoding-dependent on Windows terminals; only assert the category.
    assert msg.startswith("skill_runtime_result")
    assert calls == []


@pytest.mark.asyncio
async def test_dispatch_skill_runtime_result_calls_resume_runner_once_on_consume(
    tmp_path: Path,
) -> None:
    from nanobot.web.pending_hitl_store import PendingHitlStore
    from nanobot.web.skill_runtime_bridge import dispatch_skill_runtime_intent

    store = PendingHitlStore(tmp_path / "hitl.db")
    await store.init()
    await store.create_pending_request(
        {
            "event": "hitl.choice_request",
            "threadId": "t-runtime",
            "skillName": "s1",
            "skillRunId": "run-1",
            "payload": {
                "requestId": "req-1",
                "resumeAction": "after_choice",
                "onCancelAction": "cancel_choice",
                "expiresAt": int(1e15),
                "title": "请选择",
                "options": [{"id": "a", "label": "A"}],
            },
        }
    )

    resumed: list[dict] = []

    async def fake_resume(**kwargs):
        resumed.append(kwargs)
        return {"ok": True, "resumeId": "resume-1"}

    intent = {
        "type": "chat_card_intent",
        "verb": "skill_runtime_result",
        "payload": {
            "type": "skill_runtime_result",
            "threadId": "t-runtime",
            "skillName": "s1",
            "skillRunId": "run-2",
            "requestId": "req-1",
            "action": "after_choice",
            "status": "ok",
            "result": {"selected": "a"},
        },
    }

    handled_1, msg_1 = await dispatch_skill_runtime_intent(
        intent,
        thread_id="t-runtime",
        docman=None,
        pending_hitl_store=store,
        resume_runner=fake_resume,
    )
    handled_2, msg_2 = await dispatch_skill_runtime_intent(
        intent,
        thread_id="t-runtime",
        docman=None,
        pending_hitl_store=store,
        resume_runner=fake_resume,
    )

    assert handled_1 is True
    assert "resumed" in msg_1
    assert handled_2 is True
    assert "duplicate" in msg_2
    assert len(resumed) == 1
    assert resumed[0]["thread_id"] == "t-runtime"
    assert resumed[0]["skill_name"] == "s1"
    assert resumed[0]["request_id"] == "req-1"
    assert resumed[0]["status"] == "ok"
    assert resumed[0]["action"] == "after_choice"


@pytest.mark.asyncio
async def test_dispatch_skill_runtime_result_passes_resolved_action_for_cancel(
    tmp_path: Path,
) -> None:
    from nanobot.web.pending_hitl_store import PendingHitlStore
    from nanobot.web.skill_runtime_bridge import dispatch_skill_runtime_intent

    store = PendingHitlStore(tmp_path / "hitl.db")
    await store.init()
    await store.create_pending_request(
        {
            "event": "hitl.confirm_request",
            "threadId": "t-runtime",
            "skillName": "s1",
            "skillRunId": "run-1",
            "payload": {
                "requestId": "req-1",
                "resumeAction": "approval_pass",
                "onCancelAction": "approval_defer",
                "expiresAt": int(1e15),
                "title": "确认",
            },
        }
    )

    resumed: list[dict] = []

    async def fake_resume(**kwargs):
        resumed.append(kwargs)
        return {"ok": True}

    intent = {
        "type": "chat_card_intent",
        "verb": "skill_runtime_result",
        "payload": {
            "type": "skill_runtime_result",
            "threadId": "t-runtime",
            "skillName": "s1",
            "skillRunId": "run-2",
            "requestId": "req-1",
            "action": "approval_pass",  # must be ignored for cancel
            "status": "cancel",
            "result": {"confirmed": False},
        },
    }

    handled, msg = await dispatch_skill_runtime_intent(
        intent,
        thread_id="t-runtime",
        docman=None,
        pending_hitl_store=store,
        resume_runner=fake_resume,
    )
    assert handled is True
    assert "resumed" in msg
    assert len(resumed) == 1
    assert resumed[0]["action"] == "approval_defer"
class _FakeAgent:
    model = "fake-model"

    async def close_mcp(self):
        return None

    def set_tool_approval_callback(self, callback):
        return object()

    def set_skill_ui_patch_emitter(self, callback):
        return object()

    def set_skill_ui_chat_card_emitter(self, callback):
        return object()

    def set_module_session_focus_emitter(self, callback):
        return object()

    def set_task_status_emitter(self, callback):
        return object()

    def set_skill_ui_bootstrap_emitter(self, callback):
        return object()

    def reset_tool_approval_callback(self, token):
        return None

    def reset_skill_ui_patch_emitter(self, token):
        return None

    def reset_skill_ui_bootstrap_emitter(self, token):
        return None

    def reset_skill_ui_chat_card_emitter(self, token):
        return None

    def reset_module_session_focus_emitter(self, token):
        return None

    def reset_task_status_emitter(self, token):
        return None

    def set_current_thread_id(self, thread_id):
        return object()

    def reset_current_thread_id(self, token):
        return None

    async def process_direct(self, *args, **kwargs):
        raise AssertionError("fast-path should bypass agent.process_direct")


@pytest.mark.asyncio
async def test_handle_chat_skill_runtime_event_returns_run_finished(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_dispatch(
        intent,
        *,
        thread_id,
        docman=None,
        pending_hitl_store=None,
        resume_runner=None,
    ):
        return True, "runtime bridge ok"

    monkeypatch.setattr(
        "nanobot.web.skill_runtime_bridge.dispatch_skill_runtime_intent",
        fake_dispatch,
    )

    app = create_app(config=None, agent_loop=_FakeAgent())

    async with TestClient(TestServer(app)) as client:
        response = await client.post(
            "/api/chat",
            json={
                "threadId": f"thread-{uuid4().hex}",
                "runId": f"run-{uuid4().hex}",
                "messages": [
                    {"role": "user", "content": json.dumps(
                        {
                            "type": "chat_card_intent",
                            "verb": "skill_runtime_event",
                            "payload": {"event": "chat.guidance", "payload": {}},
                        },
                        ensure_ascii=False,
                    )}
                ],
            },
        )
        assert response.status == 200
        body = await response.text()

    finished = _first_sse_data(body, "RunFinished")
    assert finished is not None
    assert finished["message"] == "runtime bridge ok"


@pytest.mark.asyncio
async def test_handle_chat_skill_runtime_result_intent_consumes_pending_hitl(
    tmp_path: Path,
) -> None:
    from nanobot.web.pending_hitl_store import PendingHitlStore
    from nanobot.web.app import create_app

    store = PendingHitlStore(tmp_path / "hitl.db")
    await store.init()
    await store.create_pending_request(
        {
            "event": "hitl.file_request",
            "threadId": "t-runtime",
            "skillName": "gongkan_skill",
            "skillRunId": "run-1",
            "payload": {
                "requestId": "req-1",
                "resumeAction": "run_step1",
                "onCancelAction": "cancel_step1_upload",
                "expiresAt": int(1e15),
                "title": "请上传输入件",
            },
        }
    )

    app = create_app(
        config=None,
        agent_loop=_FakeAgent(),
        pending_hitl_store=store,
        enable_skill_first_resume_runner=False,
    )

    intent = {
        "type": "chat_card_intent",
        "verb": "skill_runtime_result",
        "payload": {
            "type": "skill_runtime_result",
            "threadId": "t-runtime",
            "skillName": "gongkan_skill",
            "skillRunId": "run-2",
            "requestId": "req-1",
            "action": "run_step1",
            "status": "ok",
            "result": {"files": [{"fileId": "f1"}]},
        },
    }

    async with TestClient(TestServer(app)) as client:
        resp1 = await client.post(
            "/api/chat",
            json={
                "threadId": "t-runtime",
                "runId": f"run-{uuid4().hex}",
                "messages": [{"role": "user", "content": json.dumps(intent, ensure_ascii=False)}],
            },
        )
        assert resp1.status == 200
        body1 = await resp1.text()

        resp2 = await client.post(
            "/api/chat",
            json={
                "threadId": "t-runtime",
                "runId": f"run-{uuid4().hex}",
                "messages": [{"role": "user", "content": json.dumps(intent, ensure_ascii=False)}],
            },
        )
        assert resp2.status == 200
        body2 = await resp2.text()

    fin1 = _first_sse_data(body1, "RunFinished")
    assert fin1 is not None
    assert "consumed" in fin1["message"]

    fin2 = _first_sse_data(body2, "RunFinished")
    assert fin2 is not None
    assert "duplicate" in fin2["message"]


@pytest.mark.asyncio
async def test_handle_chat_skill_runtime_result_intent_triggers_resume_runner_once(
    tmp_path: Path,
) -> None:
    from nanobot.web.pending_hitl_store import PendingHitlStore
    from nanobot.web.app import create_app

    store = PendingHitlStore(tmp_path / "hitl.db")
    await store.init()
    await store.create_pending_request(
        {
            "event": "hitl.choice_request",
            "threadId": "t-runtime",
            "skillName": "s1",
            "skillRunId": "run-1",
            "payload": {
                "requestId": "req-1",
                "resumeAction": "after_choice",
                "onCancelAction": "cancel_choice",
                "expiresAt": int(1e15),
                "title": "请选择",
                "options": [{"id": "a", "label": "A"}],
            },
        }
    )

    resumed: list[dict] = []

    async def fake_resume(**kwargs):
        resumed.append(kwargs)
        return {"ok": True}

    app = create_app(
        config=None,
        agent_loop=_FakeAgent(),
        pending_hitl_store=store,
        skill_resume_runner=fake_resume,
    )

    intent = {
        "type": "chat_card_intent",
        "verb": "skill_runtime_result",
        "payload": {
            "type": "skill_runtime_result",
            "threadId": "t-runtime",
            "skillName": "s1",
            "skillRunId": "run-2",
            "requestId": "req-1",
            "action": "after_choice",
            "status": "ok",
            "result": {"selected": "a"},
        },
    }

    async with TestClient(TestServer(app)) as client:
        resp1 = await client.post(
            "/api/chat",
            json={
                "threadId": "t-runtime",
                "runId": f"run-{uuid4().hex}",
                "messages": [{"role": "user", "content": json.dumps(intent, ensure_ascii=False)}],
            },
        )
        assert resp1.status == 200
        body1 = await resp1.text()

        resp2 = await client.post(
            "/api/chat",
            json={
                "threadId": "t-runtime",
                "runId": f"run-{uuid4().hex}",
                "messages": [{"role": "user", "content": json.dumps(intent, ensure_ascii=False)}],
            },
        )
        assert resp2.status == 200
        body2 = await resp2.text()

    fin1 = _first_sse_data(body1, "RunFinished")
    assert fin1 is not None
    assert "resumed" in fin1["message"]
    fin2 = _first_sse_data(body2, "RunFinished")
    assert fin2 is not None
    assert "duplicate" in fin2["message"]
    assert len(resumed) == 1


@pytest.mark.asyncio
async def test_create_app_defaults_enable_skill_first_resume_runner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When no skill_resume_runner is injected, create_app should enable skill-first runner by default."""
    from nanobot.web.pending_hitl_store import PendingHitlStore
    from nanobot.web.app import create_app

    store = PendingHitlStore(tmp_path / "hitl.db")
    await store.init()
    await store.create_pending_request(
        {
            "event": "hitl.choice_request",
            "threadId": "t-runtime",
            "skillName": "demo_skill",
            "skillRunId": "run-1",
            "payload": {
                "requestId": "req-1",
                "resumeAction": "after_choice",
                "onCancelAction": "cancel_choice",
                "expiresAt": int(1e15),
                "title": "请选择",
                "options": [{"id": "a", "label": "A"}],
            },
        }
    )

    emitted: list[dict] = []

    async def fake_run_skill_runtime_driver(*, skill_name, request, python_executable=None):
        return [{"event": "chat.guidance", "payload": {"context": "resumed", "actions": []}}]

    async def fake_emit_skill_runtime_event(*, envelope, thread_id, docman=None, pending_hitl_store=None):
        emitted.append({"envelope": envelope, "thread_id": thread_id})
        return {"ok": True, "event": envelope.get("event"), "summary": "ok"}

    monkeypatch.setattr(
        "nanobot.web.skill_resume_runner.run_skill_runtime_driver",
        fake_run_skill_runtime_driver,
    )
    monkeypatch.setattr(
        "nanobot.web.skill_resume_runner.emit_skill_runtime_event",
        fake_emit_skill_runtime_event,
    )

    # IMPORTANT: do NOT pass skill_resume_runner (default should enable).
    app = create_app(config=None, agent_loop=_FakeAgent(), pending_hitl_store=store)

    intent = {
        "type": "chat_card_intent",
        "verb": "skill_runtime_result",
        "payload": {
            "type": "skill_runtime_result",
            "threadId": "t-runtime",
            "skillName": "demo_skill",
            "skillRunId": "run-2",
            "requestId": "req-1",
            "action": "after_choice",
            "status": "ok",
            "result": {"selected": "a"},
        },
    }

    async with TestClient(TestServer(app)) as client:
        resp = await client.post(
            "/api/chat",
            json={
                "threadId": "t-runtime",
                "runId": f"run-{uuid4().hex}",
                "messages": [{"role": "user", "content": json.dumps(intent, ensure_ascii=False)}],
            },
        )
        assert resp.status == 200
        body = await resp.text()

    fin = _first_sse_data(body, "RunFinished")
    assert fin is not None
    assert "resumed" in fin["message"]
    assert len(emitted) == 1
    assert emitted[0]["envelope"]["event"] == "chat.guidance"
