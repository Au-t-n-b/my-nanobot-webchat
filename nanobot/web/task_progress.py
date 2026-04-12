"""Shared helpers for project-level task progress payloads."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def task_progress_file_path() -> Path:
    from nanobot.config.loader import get_config_path

    return get_config_path().parent / "task_progress.json"


def default_task_progress_file_payload() -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "updatedAt": None,
        "progress": [
            {
                "moduleId": "m_1",
                "moduleName": "机房准备",
                "updatedAt": None,
                "tasks": [
                    {"name": "提资", "completed": False},
                    {"name": "工勘数据采集与处理", "completed": False},
                    {"name": "勘测记录智能分析", "completed": False},
                    {"name": "工勘报告生成", "completed": False},
                ],
            },
            {
                "moduleId": "m_2",
                "moduleName": "机房工勘",
                "updatedAt": None,
                "tasks": [
                    {"name": "数据解析/架构/空间设", "completed": False},
                    {"name": "数据智能提取", "completed": False},
                    {"name": "网段规划/格式转换", "completed": False},
                    {"name": "智能数据校验", "completed": False},
                ],
            },
            {
                "moduleId": "m_3",
                "moduleName": "规划设计",
                "updatedAt": None,
                "tasks": [
                    {"name": "施工智能调度", "completed": False},
                    {"name": "进度智能化反馈", "completed": False},
                ],
            },
            {
                "moduleId": "m_4",
                "moduleName": "硬装/昇腾安装",
                "updatedAt": None,
                "tasks": [
                    {"name": "智能化生成配置文件", "completed": False},
                    {"name": "昇腾软件安装", "completed": False},
                    {"name": "单机测试/集群测试", "completed": False},
                    {"name": "测试结果智能分析", "completed": False},
                ],
            },
            {
                "moduleId": "m_5",
                "moduleName": "软件部署/对接",
                "updatedAt": None,
                "tasks": [
                    {"name": "软件部署/测试", "completed": False},
                    {"name": "对接问题处理", "completed": False},
                    {"name": "平台对接", "completed": False},
                ],
            },
            {
                "moduleId": "m_6",
                "moduleName": "验收上线",
                "updatedAt": None,
                "tasks": [
                    {"name": "验收文档生成", "completed": False},
                    {"name": "问题定界定位", "completed": False},
                    {"name": "系统上线", "completed": False},
                ],
            },
            {
                "moduleId": "m_7",
                "moduleName": "智能分析工作台",
                "updatedAt": None,
                "tasks": [
                    {"name": "模块待启动", "completed": False},
                    {"name": "分析目标已确认", "completed": False},
                    {"name": "资料已上传", "completed": False},
                    {"name": "并行分析进行中", "completed": False},
                    {"name": "结论汇总中", "completed": False},
                    {"name": "分析完成", "completed": False},
                ],
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
            pending_count = sum(1 for module in modules if module.get("status") == "pending")
            total_count = len(modules)
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


def load_task_status_payload() -> dict[str, Any]:
    path = task_progress_file_path()
    if not path.is_file():
        return normalize_task_progress_payload(default_task_progress_file_payload())
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("task_progress.json must contain a JSON object")
    return normalize_task_progress_payload(raw)
