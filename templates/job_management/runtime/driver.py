from __future__ import annotations

import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from typing import Any


def _now_ms() -> int:
    return int(time.time() * 1000)


def _print_event(evt: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(evt, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _as_str(v: Any) -> str:
    return str(v or "").strip()


def _read_json(path: str) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _write_json(path: str, obj: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_schedule() -> dict[str, Any]:
    # Minimal editable schedule schema for the web editor.
    base = datetime.now(timezone.utc).date()
    def d(days: int) -> str:
        return datetime.fromordinal(base.toordinal() + int(days)).date().isoformat()
    return {
        "schemaVersion": 1,
        "updatedAt": _iso_now(),
        "tasks": [
            {"id": "t1", "name": "规划设计排期", "group": "计划初排", "start": d(0), "end": d(3)},
            {"id": "t2", "name": "工程安装排期", "group": "计划初排", "start": d(3), "end": d(8)},
            {"id": "t3", "name": "集群联调排期", "group": "计划初排", "start": d(8), "end": d(12)},
        ],
        "milestones": [
            {"id": "m1", "name": "到货", "kind": "diamond", "planDate": d(1), "actualDate": d(2)},
            {"id": "m2", "name": "上电", "kind": "circle", "planDate": d(5), "actualDate": d(6)},
            {"id": "m3", "name": "上线", "kind": "rect", "planDate": d(11), "actualDate": d(12)},
        ],
        "criticalPaths": [
            {"id": "cp1", "name": "关键路径一", "tasks": ["t1", "t2", "t3"]},
            {"id": "cp2", "name": "关键路径二", "tasks": ["t2"]},
            {"id": "cp3", "name": "关键路径三", "tasks": ["t3"]},
        ],
    }


def _emit_task_progress(*, thread_id: str, skill_name: str, run_id: str, done: int, total: int) -> None:
    _print_event(
        {
            "event": "task_progress.sync",
            "threadId": thread_id,
            "skillName": skill_name,
            "skillRunId": run_id,
            "timestamp": _now_ms(),
            "payload": {
                "schemaVersion": 1,
                "updatedAt": _now_ms(),
                "modules": [
                    {
                        "moduleId": "job_management",
                        "moduleName": "作业管理（模板）",
                        "updatedAt": _now_ms(),
                        "tasks": [
                            {"name": "upload_inputs", "displayName": "上传资料", "completed": done >= 1},
                            {"name": "choose_strategy", "displayName": "选择策略", "completed": done >= 2},
                            {"name": "confirm_run", "displayName": "确认执行", "completed": done >= 3},
                            {"name": "edit_workbench", "displayName": "工作台编辑", "completed": done >= 4},
                            {"name": "publish", "displayName": "发布产物", "completed": done >= 5},
                        ],
                    }
                ],
                "overall": {"doneCount": int(done), "totalCount": int(total)},
            },
        }
    )


def _emit_patch(*, thread_id: str, skill_name: str, run_id: str, synthetic_path: str, doc_id: str, ops: list[dict[str, Any]]) -> None:
    _print_event(
        {
            "event": "dashboard.patch",
            "threadId": thread_id,
            "skillName": skill_name,
            "skillRunId": run_id,
            "timestamp": _now_ms(),
            "payload": {"syntheticPath": synthetic_path, "docId": doc_id, "ops": ops},
        }
    )


def _emit_summary(*, thread_id: str, skill_name: str, run_id: str, synthetic_path: str, doc_id: str, content: str) -> None:
    _emit_patch(
        thread_id=thread_id,
        skill_name=skill_name,
        run_id=run_id,
        synthetic_path=synthetic_path,
        doc_id=doc_id,
        ops=[
            {
                "op": "merge",
                "target": {"by": "id", "nodeId": "summary-text"},
                "value": {"type": "Text", "variant": "body", "color": "subtle", "content": content},
            }
        ],
    )


def _emit_stepper(*, thread_id: str, skill_name: str, run_id: str, synthetic_path: str, doc_id: str, done: int, active: int) -> None:
    """曾向 id=stepper-main 发 patch；大盘已去掉 SDUI Stepper，此处不再更新。"""
    return


def _default_ui_state() -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "updatedAt": _iso_now(),
        "execPct": 40,
        "dashBoxOpen": False,
        "dashBoxForTopId": "first",
        "topFlow": [
            {"id": "prep", "label": "数据准备", "status": "done"},
            {"id": "first", "label": "计划初排", "status": "active"},
            {"id": "adjust", "label": "计划调整", "status": "waiting"},
            {"id": "dispatch", "label": "任务下发", "status": "waiting"},
        ],
        "subFlowsByTopId": {
            "prep": [
                {"id": "prep_in", "label": "资料收集", "status": "done"},
                {"id": "prep_check", "label": "资料校验", "status": "done"},
                {"id": "prep_ready", "label": "就绪", "status": "done"},
            ],
            "first": [
                {"id": "plan", "label": "规划设计排期", "status": "active"},
                {"id": "eng", "label": "工程安装排期", "status": "waiting"},
                {"id": "cluster", "label": "集群联调排期", "status": "waiting"},
            ],
            "adjust": [
                {"id": "adj_review", "label": "评审", "status": "waiting"},
                {"id": "adj_opt", "label": "优化", "status": "waiting"},
                {"id": "adj_confirm", "label": "确认", "status": "waiting"},
            ],
            "dispatch": [
                {"id": "dis_pkg", "label": "打包下发", "status": "waiting"},
                {"id": "dis_track", "label": "跟踪执行", "status": "waiting"},
                {"id": "dis_done", "label": "闭环", "status": "waiting"},
            ],
        },
    }


def _read_choice_value(result_obj: Any) -> str:
    if not isinstance(result_obj, dict):
        return ""
    return _as_str(result_obj.get("value") or result_obj.get("choice") or result_obj.get("optionId") or result_obj.get("selected"))


def main() -> int:
    raw = os.environ.get("NANOBOT_REQUEST_JSON")
    if not raw and len(sys.argv) >= 2 and isinstance(sys.argv[1], str) and sys.argv[1].strip():
        raw = sys.argv[1]
    if not raw:
        try:
            if not sys.stdin.isatty():
                raw = sys.stdin.read()
        except Exception:
            raw = None
    req = json.loads(raw or "{}")
    thread_id = _as_str(req.get("thread_id")) or "thread-unknown"
    skill_name = _as_str(req.get("skill_name")) or "job_management"
    request_id = _as_str(req.get("request_id")) or f"req-{uuid.uuid4().hex}"
    action = _as_str(req.get("action")) or "jm_start"
    status = _as_str(req.get("status")) or "ok"
    result_obj = req.get("result")

    synthetic_path = "skill-ui://SduiView?dataFile=skills/job_management/data/dashboard.json"
    doc_id = "dashboard:job-management"
    run_id = f"run-{uuid.uuid4().hex}"

    skill_root = os.getcwd()
    rt_dir = os.path.join(skill_root, "ProjectData", "RunTime")
    os.makedirs(rt_dir, exist_ok=True)
    schedule_path = os.path.join(rt_dir, "schedule_draft.json")
    ui_state_path = os.path.join(rt_dir, "ui_state.json")
    uploads_path = os.path.join(rt_dir, "uploaded_files.json")
    strategy_path = os.path.join(rt_dir, "strategy.json")
    input_dir = os.path.join(skill_root, "ProjectData", "Input")
    os.makedirs(input_dir, exist_ok=True)

    if status != "ok":
        _emit_summary(
            thread_id=thread_id,
            skill_name=skill_name,
            run_id=run_id,
            synthetic_path=synthetic_path,
            doc_id=doc_id,
            content=f"收到非 ok 状态（{status}），已停止。",
        )
        return 0

    ui_state = _read_json(ui_state_path)
    if not isinstance(ui_state, dict):
        ui_state = _default_ui_state()

    schedule = _read_json(schedule_path)
    if not isinstance(schedule, dict):
        schedule = _default_schedule()
        _write_json(schedule_path, schedule)

    uploaded_files = _read_json(uploads_path)
    if not isinstance(uploaded_files, list):
        uploaded_files = []

    strategy = _read_json(strategy_path)
    if not isinstance(strategy, dict):
        strategy = {}

    # ──────────────────────────────────────────────────────────────────────────────
    # Step 1: HITL file upload (skill_runtime_result -> PendingHitlStore)
    # ──────────────────────────────────────────────────────────────────────────────
    if action == "jm_start":
        _emit_stepper(thread_id=thread_id, skill_name=skill_name, run_id=run_id, synthetic_path=synthetic_path, doc_id=doc_id, done=0, active=1)
        _emit_summary(
            thread_id=thread_id,
            skill_name=skill_name,
            run_id=run_id,
            synthetic_path=synthetic_path,
            doc_id=doc_id,
            content="Step1：请先上传作业管理所需资料（模板演示 HITL 文件上传闭环）。上传完成后将自动进入“策略选择”。",
        )
        _emit_task_progress(thread_id=thread_id, skill_name=skill_name, run_id=run_id, done=0, total=5)
        _print_event(
            {
                "event": "hitl.file_request",
                "threadId": thread_id,
                "skillName": skill_name,
                "skillRunId": run_id,
                "timestamp": _now_ms(),
                "payload": {
                    "requestId": f"{request_id}:upload_inputs",
                    "cardId": "jobm:step1:file",
                    "purpose": "jobm-inputs",
                    "title": "请上传作业管理资料",
                    "description": "示例：需求文档/到货清单/排期约束/现场照片等。可多文件上传。",
                    "accept": ".zip,.pdf,.docx,.doc,.xlsx,.xls,.png,.jpg,.jpeg,.webp",
                    "multiple": True,
                    "saveRelativeDir": "skills/job_management/ProjectData/Input",
                    "resumeAction": "jm_after_upload",
                    "onCancelAction": "jm_start",
                    "skillName": skill_name,
                    "stateNamespace": skill_name,
                    "stepId": "jobm.step1.upload",
                    "expiresAt": _now_ms() + 30 * 60 * 1000,
                },
            }
        )
        return 0

    if action == "jm_after_upload":
        if isinstance(result_obj, dict):
            # Normalize upload envelope from FilePicker: {upload, uploads}
            ups = result_obj.get("uploads") if isinstance(result_obj.get("uploads"), list) else None
            if ups is None and isinstance(result_obj.get("upload"), dict):
                ups = [result_obj.get("upload")]
            if isinstance(ups, list):
                cleaned = []
                for it in ups:
                    if not isinstance(it, dict):
                        continue
                    file_id = _as_str(it.get("fileId") or it.get("id"))
                    name = _as_str(it.get("name") or it.get("filename") or it.get("label"))
                    logical = _as_str(it.get("logicalPath") or it.get("path"))
                    cleaned.append(
                        {
                            "fileId": file_id or f"f-{uuid.uuid4().hex}",
                            "name": name or (os.path.basename(logical) if logical else "uploaded"),
                            "logicalPath": logical,
                            "uploadedAt": int(it.get("uploadedAt") or _now_ms()),
                        }
                    )
                if cleaned:
                    uploaded_files = cleaned
                    _write_json(uploads_path, uploaded_files)

        # Patch uploaded-files grid (dashboard SDUI)
        items = []
        for it in uploaded_files:
            if not isinstance(it, dict):
                continue
            fid = _as_str(it.get("fileId")) or f"f-{uuid.uuid4().hex}"
            label = _as_str(it.get("name")) or fid
            path = _as_str(it.get("logicalPath")) or ""
            items.append({"id": fid, "label": label, "path": path, "kind": "other", "status": "ready"})

        _emit_patch(
            thread_id=thread_id,
            skill_name=skill_name,
            run_id=run_id,
            synthetic_path=synthetic_path,
            doc_id=doc_id,
            ops=[
                {
                    "op": "merge",
                    "target": {"by": "id", "nodeId": "uploaded-files"},
                    "value": {"type": "ArtifactGrid", "id": "uploaded-files", "title": "已上传文件", "mode": "input", "artifacts": items},
                }
            ],
        )

        _emit_stepper(thread_id=thread_id, skill_name=skill_name, run_id=run_id, synthetic_path=synthetic_path, doc_id=doc_id, done=1, active=2)
        _emit_summary(
            thread_id=thread_id,
            skill_name=skill_name,
            run_id=run_id,
            synthetic_path=synthetic_path,
            doc_id=doc_id,
            content="Step2：请选择排期策略（模板演示 HITL 选择卡）。",
        )
        _emit_task_progress(thread_id=thread_id, skill_name=skill_name, run_id=run_id, done=1, total=5)
        _print_event(
            {
                "event": "hitl.choice_request",
                "threadId": thread_id,
                "skillName": skill_name,
                "skillRunId": run_id,
                "timestamp": _now_ms(),
                "payload": {
                    "requestId": f"{request_id}:choose_strategy",
                    "cardId": "jobm:step2:choice",
                    "title": "选择排期策略",
                    "description": "这是模板示例：Skill 通过标准事件驱动 Choice 交互，平台只负责渲染与回执。",
                    "options": [
                        {"label": "快速初排（偏速度）", "value": "fast"},
                        {"label": "严格约束（偏质量）", "value": "strict"},
                        {"label": "自定义（后续在工作台微调）", "value": "custom"},
                    ],
                    "resumeAction": "jm_after_choice",
                    "onCancelAction": "jm_after_upload",
                    "skillName": skill_name,
                    "stateNamespace": skill_name,
                    "stepId": "jobm.step2.choice",
                    "expiresAt": _now_ms() + 15 * 60 * 1000,
                },
            }
        )
        return 0

    if action == "jm_after_choice":
        choice = _read_choice_value(result_obj) or "fast"
        strategy = {"choice": choice, "updatedAt": _iso_now()}
        _write_json(strategy_path, strategy)

        _emit_stepper(thread_id=thread_id, skill_name=skill_name, run_id=run_id, synthetic_path=synthetic_path, doc_id=doc_id, done=2, active=3)
        _emit_summary(
            thread_id=thread_id,
            skill_name=skill_name,
            run_id=run_id,
            synthetic_path=synthetic_path,
            doc_id=doc_id,
            content=f"Step3：你选择了「{choice}」。确认后将进入工作台（EmbeddedWeb）并允许拖拽甘特写回 JSON。",
        )
        _emit_task_progress(thread_id=thread_id, skill_name=skill_name, run_id=run_id, done=2, total=5)
        _print_event(
            {
                "event": "hitl.confirm_request",
                "threadId": thread_id,
                "skillName": skill_name,
                "skillRunId": run_id,
                "timestamp": _now_ms(),
                "payload": {
                    "requestId": f"{request_id}:confirm_enter_workbench",
                    "cardId": "jobm:step3:confirm",
                    "title": "确认进入排期工作台？",
                    "confirmLabel": "进入工作台",
                    "cancelLabel": "稍后",
                    "resumeAction": "jm_init_workbench",
                    "onCancelAction": "jm_after_choice",
                    "skillName": skill_name,
                    "stateNamespace": skill_name,
                    "stepId": "jobm.step3.confirm",
                    "expiresAt": _now_ms() + 30 * 60 * 1000,
                    "state": {"strategy": choice},
                },
            }
        )
        return 0

    if action == "jm_workbench_ui":
        patch = result_obj.get("uiStatePatch") if isinstance(result_obj, dict) else None
        if isinstance(patch, dict):
            merged = dict(ui_state)
            merged.update(patch)
            merged["updatedAt"] = _iso_now()
            ui_state = merged
            _write_json(ui_state_path, ui_state)

    if action == "jm_apply_schedule_draft":
        draft = result_obj.get("scheduleDraft") if isinstance(result_obj, dict) else None
        if isinstance(draft, dict):
            draft["updatedAt"] = _iso_now()
            _write_json(schedule_path, draft)
            schedule = draft

    if action == "jm_init_workbench":
        # Enter workbench: patch embedded state and publish schedule artifact.
        _emit_stepper(thread_id=thread_id, skill_name=skill_name, run_id=run_id, synthetic_path=synthetic_path, doc_id=doc_id, done=3, active=4)
        _emit_summary(
            thread_id=thread_id,
            skill_name=skill_name,
            run_id=run_id,
            synthetic_path=synthetic_path,
            doc_id=doc_id,
            content="Step4：已进入工作台。你可以点击圆圈展开子流程；拖拽甘特并在右下角确认写回 schedule_draft.json（走 skill_runtime_resume，静默完成）。",
        )
        _emit_task_progress(thread_id=thread_id, skill_name=skill_name, run_id=run_id, done=3, total=5)

    # Patch: inject state to EmbeddedWeb so iframe can render the full "图二" workbench.
    _emit_patch(
        thread_id=thread_id,
        skill_name=skill_name,
        run_id=run_id,
        synthetic_path=synthetic_path,
        doc_id=doc_id,
        ops=[
            {
                "op": "merge",
                "target": {"by": "id", "nodeId": "jm-workbench-web"},
                "value": {
                    "type": "EmbeddedWeb",
                    "id": "jm-workbench-web",
                    "src": "/api/file?path=workspace/skills/job_management/ui/job_workbench.html",
                    "minHeight": 720,
                    "state": {
                        "threadId": thread_id,
                        "skillName": skill_name,
                        "schedulePath": "workspace/skills/job_management/ProjectData/RunTime/schedule_draft.json",
                        "uiStatePath": "workspace/skills/job_management/ProjectData/RunTime/ui_state.json",
                        "requestIdBase": request_id,
                        "schedule": schedule,
                        "uiState": ui_state,
                        "strategy": strategy,
                    },
                },
            },
        ],
    )

    # Publish artifacts only on meaningful milestones to avoid noise on every UI tick.
    if action in {"jm_init_workbench", "jm_apply_schedule_draft"}:
        _print_event(
            {
                "event": "artifact.publish",
                "threadId": thread_id,
                "skillName": skill_name,
                "skillRunId": run_id,
                "timestamp": _now_ms(),
                "payload": {
                    "syntheticPath": synthetic_path,
                    "docId": doc_id,
                    "artifactsNodeId": "artifacts",
                    "items": [
                        {
                            "artifactId": "schedule_draft",
                            "label": "schedule_draft.json",
                            "path": "workspace/skills/job_management/ProjectData/RunTime/schedule_draft.json",
                            "kind": "json",
                            "status": "ready",
                        }
                    ],
                },
            }
        )

    if action == "jm_apply_schedule_draft":
        _emit_summary(
            thread_id=thread_id,
            skill_name=skill_name,
            run_id=run_id,
            synthetic_path=synthetic_path,
            doc_id=doc_id,
            content="已写回 schedule_draft.json 并发布到右侧预览（模板演示 artifact.publish）。",
        )
        _emit_stepper(thread_id=thread_id, skill_name=skill_name, run_id=run_id, synthetic_path=synthetic_path, doc_id=doc_id, done=4, active=5)
        _emit_task_progress(thread_id=thread_id, skill_name=skill_name, run_id=run_id, done=4, total=5)
        # Finalize publish step (template signal)
        _emit_stepper(thread_id=thread_id, skill_name=skill_name, run_id=run_id, synthetic_path=synthetic_path, doc_id=doc_id, done=5, active=5)
        _emit_task_progress(thread_id=thread_id, skill_name=skill_name, run_id=run_id, done=5, total=5)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

