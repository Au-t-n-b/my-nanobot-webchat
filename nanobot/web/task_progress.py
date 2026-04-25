"""Shared helpers for project-level task progress payloads."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from datetime import datetime, timezone


def task_progress_file_path() -> Path:
    """Persist ``task_progress.json`` under the user workspace (``~/.nanobot/workspace/`` by default).

    * ``NANOBOT_TASK_PROGRESS_FILE`` — full path to the JSON file (tests, overrides).
    """
    p = (os.environ.get("NANOBOT_TASK_PROGRESS_FILE") or "").strip()
    if p:
        return Path(p)
    return Path.home() / ".nanobot" / "workspace" / "task_progress.json"


def _tasks(names: list[str]) -> list[dict[str, Any]]:
    return [{"name": n, "completed": False} for n in names]


def default_task_progress_file_payload() -> dict[str, Any]:
    """Six high-level delivery phases; ``moduleId`` values match frontend :func:`composeProjectRegistryItems`."""
    return {
        "schemaVersion": 1,
        "updatedAt": None,
        "progress": [
            {
                "moduleId": "job_management",
                "moduleName": "作业管理",
                "updatedAt": None,
                "tasks": _tasks(
                    [
                        "作业待启动",
                        "资料已上传",
                        "规划设计排期已确认",
                        "工程安装排期已确认",
                        "集群联调排期已确认",
                        "作业闭环完成",
                    ],
                ),
            },
            {
                "moduleId": "smart_survey",
                "moduleName": "智慧工勘",
                "updatedAt": None,
                "tasks": _tasks(
                    [
                        "场景筛选与底表过滤",
                        "勘测数据汇总",
                        "报告生成",
                        "审批与分发闭环",
                    ],
                ),
            },
            {
                "moduleId": "modeling_simulation_workbench",
                "moduleName": "建模仿真",
                "updatedAt": None,
                "tasks": _tasks(
                    [
                        "BOQ 提取",
                        "设备确认",
                        "创建设备",
                        "拓扑确认",
                        "拓扑连接",
                    ],
                ),
            },
            {
                "moduleId": "system_design",
                "moduleName": "系统设计",
                "updatedAt": None,
                "tasks": _tasks(
                    [
                        "需求与范围基线",
                        "方案与架构评审",
                        "设计基线冻结",
                        "变更与风险登记",
                    ],
                ),
            },
            {
                "moduleId": "device_install",
                "moduleName": "设备安装",
                "updatedAt": None,
                "tasks": _tasks(
                    [
                        "进场与验货",
                        "安装与上电",
                        "单机自检",
                        "系统联线",
                        "安规与资产标签",
                    ],
                ),
            },
            {
                "moduleId": "sw_deploy_commission",
                "moduleName": "软件部署与调测",
                "updatedAt": None,
                "tasks": _tasks(
                    [
                        "环境基线",
                        "应用与中间件部署",
                        "联调对点",
                        "性能与稳定验证",
                        "移交与培训",
                    ],
                ),
            },
        ],
    }


def normalize_task_progress_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize persisted progress data into the frontend's task-status shape."""
    if "modules" in payload and "overall" in payload:
        modules = payload.get("modules")
        if not isinstance(modules, list):
            modules = []
        if "summary" not in payload:
            active_count = sum(1 for module in modules if module.get("status") == "running")
            completed_count = sum(1 for module in modules if module.get("status") == "completed")
            failed_count = sum(1 for module in modules if module.get("status") == "failed")
            skipped_count = sum(1 for module in modules if module.get("status") == "skipped")
            pending_count = sum(1 for module in modules if module.get("status") == "pending")
            total_count = len(modules)
            remainder = total_count - active_count - completed_count - pending_count - failed_count - skipped_count
            if remainder > 0:
                pending_count += remainder
            payload["summary"] = {
                "activeCount": active_count,
                "pendingCount": pending_count,
                "completedCount": completed_count,
                "completionRate": round((completed_count / total_count) * 100) if total_count else 0,
            }
        return payload

    progress = payload.get("progress")
    if not isinstance(progress, list):
        progress = []

    modules: list[dict[str, Any]] = []
    for mod_index, raw_module in enumerate(progress, start=1):
        module_id = str(raw_module.get("moduleId") or f"m_{mod_index}")
        module_name = str(raw_module.get("moduleName") or module_id)
        raw_tasks = raw_module.get("tasks")
        if not isinstance(raw_tasks, list):
            raw_tasks = []

        steps: list[dict[str, Any]] = []
        completed_count = 0
        for task_index, raw_task in enumerate(raw_tasks, start=1):
            done = bool(raw_task.get("completed"))
            if done:
                completed_count += 1
            steps.append(
                {
                    "id": f"{module_id}_s_{task_index}",
                    "name": str(raw_task.get("name") or f"任务 {task_index}"),
                    "done": done,
                }
            )

        if steps and completed_count == len(steps):
            status = "completed"
        elif completed_count > 0:
            status = "running"
        else:
            status = "pending"

        modules.append(
            {
                "id": module_id,
                "name": module_name,
                "status": status,
                "steps": steps,
            }
        )

    done_count = sum(1 for module in modules if module["status"] == "completed")
    active_count = sum(1 for module in modules if module["status"] == "running")
    pending_count = sum(1 for module in modules if module["status"] == "pending")
    return {
        "updatedAt": payload.get("updatedAt"),
        "overall": {"doneCount": done_count, "totalCount": len(modules)},
        "summary": {
            "activeCount": active_count,
            "pendingCount": pending_count,
            "completedCount": done_count,
            "completionRate": round((done_count / len(modules)) * 100) if modules else 0,
        },
        "modules": modules,
    }


def _job_management_ui_state_path() -> Path:
    return (
        Path.home()
        / ".nanobot"
        / "workspace"
        / "skills"
        / "job_management"
        / "ProjectData"
        / "RunTime"
        / "ui_state.json"
    )


def _coerce_done_from_flow_item(item: dict[str, Any]) -> bool:
    status = str(item.get("status") or "").strip().lower()
    if status in {"done", "completed", "complete", "success"}:
        return True
    pct = item.get("pct")
    if isinstance(pct, (int, float)) and pct >= 100:
        return True
    return False


def _load_job_management_steps_from_ui_state() -> list[dict[str, Any]] | None:
    """Read job_management runtime ui_state.json and derive steps from topFlow (stage-level)."""
    path = _job_management_ui_state_path()
    if not path.is_file():
        return None
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return None

    top_flow = raw.get("topFlow")
    if not isinstance(top_flow, list) or not top_flow:
        return None

    steps: list[dict[str, Any]] = []
    for top in top_flow:
        if not isinstance(top, dict):
            continue
        top_id = str(top.get("id") or "").strip()
        top_label = str(top.get("label") or top_id or "阶段").strip()
        if not top_id:
            continue
        steps.append(
            {
                "id": f"job_management_top_{top_id}",
                "name": top_label,
                "done": _coerce_done_from_flow_item(top),
            }
        )

    return steps or None


def _overlay_job_management_steps(task_status: dict[str, Any]) -> dict[str, Any]:
    """If ui_state.json has topFlow, override job_management steps/status in task_status payload."""
    modules = task_status.get("modules")
    if not isinstance(modules, list) or not modules:
        return task_status

    steps = _load_job_management_steps_from_ui_state()
    if not steps:
        return task_status

    for module in modules:
        if not isinstance(module, dict):
            continue
        if str(module.get("id") or "") != "job_management":
            continue
        module["steps"] = steps
        done_count = sum(1 for s in steps if isinstance(s, dict) and s.get("done") is True)
        if done_count == len(steps):
            module["status"] = "completed"
        elif done_count > 0:
            module["status"] = "running"
        else:
            module["status"] = "pending"
        break

    return task_status


def _sync_job_management_task_progress_from_ui_state(raw_task_progress: dict[str, Any]) -> bool:
    """Sync job_management task_progress.json tasks from ui_state.json topFlow (stage-level).

    Returns True if the in-memory payload was modified.
    """
    if not isinstance(raw_task_progress, dict):
        return False
    progress = raw_task_progress.get("progress")
    if not isinstance(progress, list) or not progress:
        return False

    path = _job_management_ui_state_path()
    if not path.is_file():
        return False

    try:
        ui_state = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return False
    if not isinstance(ui_state, dict):
        return False

    top_flow = ui_state.get("topFlow")
    if not isinstance(top_flow, list) or not top_flow:
        return False

    jm = None
    for m in progress:
        if isinstance(m, dict) and str(m.get("moduleId") or "") == "job_management":
            jm = m
            break
    if not isinstance(jm, dict):
        return False
    tasks = jm.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        return False

    top_tasks: list[dict[str, Any]] = []
    for top in top_flow:
        if not isinstance(top, dict):
            continue
        label = str(top.get("label") or "").strip()
        if not label:
            continue
        top_tasks.append({"name": label, "completed": _coerce_done_from_flow_item(top)})
    if not top_tasks:
        return False

    # Replace job_management tasks to match topFlow exactly.
    changed = tasks != top_tasks
    if changed:
        jm["tasks"] = top_tasks

    if changed:
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        raw_task_progress["updatedAt"] = ui_state.get("updatedAt") or now
        jm["updatedAt"] = ui_state.get("updatedAt") or now
    return changed


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def load_task_status_payload() -> dict[str, Any]:
    path = task_progress_file_path()
    if not path.is_file():
        return _overlay_job_management_steps(normalize_task_progress_payload(default_task_progress_file_payload()))
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("task_progress.json must contain a JSON object")
    # Keep persisted job_management tasks aligned with runtime ui_state.json.
    if _sync_job_management_task_progress_from_ui_state(raw):
        try:
            _write_json_atomic(path, raw)
        except OSError:
            # If disk write fails, still serve the request (best-effort sync).
            pass
    return _overlay_job_management_steps(normalize_task_progress_payload(raw))
