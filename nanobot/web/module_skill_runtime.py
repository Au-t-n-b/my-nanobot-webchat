"""统一模块 Skill 运行时：按 module.json + flow 驱动大盘 Patch 与 HITL ChatCard。

业务团队在 ``<skills_root>/<module_id>/`` 下交付 ``module.json``、``SKILL.md``、``data/dashboard.json``；
模型通过工具 ``module_skill_runtime`` 或 Fast-path ``chat_card_intent`` 调用本模块。
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any

from loguru import logger

from nanobot.agent.loop import get_current_thread_id
from nanobot.web.module_contract_schema import (
    validate_dashboard_contract,
    validate_module_contract,
)
from nanobot.web.mission_control import MissionControlManager
from nanobot.web.task_progress import load_task_status_payload, task_progress_file_path

# 执行结束后发 idle。guide/start 不发 idle，让前端保持「模块进行中」并停在模块大盘，直到 finish/cancel。
_ACTIONS_EMIT_IDLE_AFTER: frozenset[str] = frozenset({"cancel", "finish"})


async def _emit_module_session_focus(thread_id: str, module_id: str, status: str) -> None:
    from nanobot.agent.loop import emit_module_session_focus_event

    st = (status or "").strip().lower()
    if st not in ("running", "idle"):
        return
    tid = (thread_id or "").strip()
    mid = (module_id or "").strip()
    if not tid or not mid:
        return
    await emit_module_session_focus_event({"threadId": tid, "moduleId": mid, "status": st})
from nanobot.web.skill_ui_patch import SkillUiPatchPusher
from nanobot.web.skills import get_skills_root

# (thread_id, module_id) -> 跨 HITL 步骤的合并状态（样本级；生产可换 Redis）
_SESSION: dict[tuple[str, str], dict[str, Any]] = {}


def _session_key(thread_id: str, module_id: str) -> tuple[str, str]:
    return (thread_id.strip(), module_id.strip())


def merge_module_session(thread_id: str, module_id: str, patch: dict[str, Any]) -> dict[str, Any]:
    key = _session_key(thread_id, module_id)
    cur = _SESSION.setdefault(key, {})
    cur.update({k: v for k, v in patch.items() if v is not None})
    return cur


def clear_module_session(thread_id: str, module_id: str) -> None:
    _SESSION.pop(_session_key(thread_id, module_id), None)


def _merge_uploads(existing: Any, incoming: Any) -> list[dict[str, Any]]:
    prev = existing if isinstance(existing, list) else []
    nxt = incoming if isinstance(incoming, list) else []
    merged: list[dict[str, Any]] = []
    seen_paths: set[str] = set()
    for item in [*prev, *nxt]:
        if not isinstance(item, dict):
            continue
        logical_path = str(item.get("logicalPath") or "").strip()
        file_id = str(item.get("fileId") or "").strip()
        dedupe_key = logical_path or file_id
        if not dedupe_key or dedupe_key in seen_paths:
            continue
        seen_paths.add(dedupe_key)
        merged.append(item)
    return merged


def _uploads_as_artifacts(uploads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []
    for index, item in enumerate(uploads, start=1):
        logical_path = str(item.get("logicalPath") or "").strip()
        if not logical_path:
            continue
        name = str(item.get("name") or "").strip() or Path(logical_path).name or f"upload-{index}"
        suffix = Path(name).suffix.lstrip(".").lower() or "other"
        kind = suffix if suffix in {"docx", "xlsx", "pdf", "html", "json", "md", "png"} else "other"
        artifacts.append(
            {
                "id": str(item.get("fileId") or logical_path or f"upload-{index}"),
                "label": name,
                "path": logical_path,
                "kind": kind,
                "status": "ready",
            }
        )
    return artifacts


def _latest_upload_meta(state: dict[str, Any]) -> dict[str, Any]:
    upload = state.get("upload")
    if isinstance(upload, dict):
        return upload
    uploads = state.get("uploads")
    if isinstance(uploads, list):
        for item in reversed(uploads):
            if isinstance(item, dict):
                return item
    return {}


def _default_task_progress_payload() -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "updatedAt": None,
        "progress": [
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
            }
        ],
    }


def _default_workbench_task_names() -> list[str]:
    return [
        "模块待启动",
        "分析目标已确认",
        "资料已上传",
        "并行分析进行中",
        "结论汇总中",
        "分析完成",
    ]


def _task_progress_definition(module_name: str, module_cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    raw = module_cfg.get("taskProgress") if isinstance(module_cfg, dict) and isinstance(module_cfg.get("taskProgress"), dict) else {}
    tasks_raw = raw.get("tasks")
    tasks = [
        str(item).strip()
        for item in tasks_raw
        if str(item).strip()
    ] if isinstance(tasks_raw, list) else []
    if not tasks:
        tasks = _default_workbench_task_names()
    return {
        "module_id": str(raw.get("moduleId") or "m_7").strip() or "m_7",
        "module_name": str(raw.get("moduleName") or module_name).strip() or module_name,
        "tasks": tasks,
        "action_mapping": raw.get("actionMapping") if isinstance(raw.get("actionMapping"), dict) else {},
    }


def _configured_completed_tasks(
    module_cfg: dict[str, Any] | None,
    action: str,
    fallback: set[str],
    *,
    module_name: str,
) -> set[str]:
    definition = _task_progress_definition(module_name, module_cfg)
    mapping = definition["action_mapping"]
    configured = mapping.get(action) if isinstance(mapping, dict) else None
    if not isinstance(configured, list):
        return fallback
    names = {str(item).strip() for item in configured if str(item).strip()}
    return names or fallback


def _upload_config(cfg: dict[str, Any], purpose: str) -> dict[str, Any]:
    uploads = cfg.get("uploads")
    if not isinstance(uploads, list):
        return {}
    wanted = (purpose or "").strip()
    for item in uploads:
        if not isinstance(item, dict):
            continue
        if str(item.get("purpose") or "").strip() == wanted:
            return item
    return {}


def _set_project_progress(
    module_name: str,
    completed_names: set[str],
    module_cfg: dict[str, Any] | None = None,
) -> None:
    definition = _task_progress_definition(module_name, module_cfg)
    path = task_progress_file_path()
    try:
        if path.exists():
            payload = json.loads(path.read_text(encoding="utf-8"))
        else:
            payload = _default_task_progress_payload()
    except Exception:
        payload = _default_task_progress_payload()

    progress = payload.get("progress")
    if not isinstance(progress, list):
        progress = []
        payload["progress"] = progress

    target = None
    for item in progress:
        if isinstance(item, dict) and str(item.get("moduleName") or "") == definition["module_name"]:
            target = item
            break
    if target is None:
        target = {
            "moduleId": definition["module_id"],
            "moduleName": definition["module_name"],
            "updatedAt": None,
            "tasks": [{"name": name, "completed": False} for name in definition["tasks"]],
        }
        progress.append(target)

    tasks = target.get("tasks")
    if not isinstance(tasks, list):
        tasks = []
        target["tasks"] = tasks
    expected_task_order = definition["tasks"]
    existing_names = {
        str(task.get("name") or "").strip()
        for task in tasks
        if isinstance(task, dict)
    }
    for name in expected_task_order:
        if name and name not in existing_names:
            tasks.append({"name": name, "completed": False})
    for task in tasks:
        if isinstance(task, dict):
            task["completed"] = str(task.get("name") or "") in completed_names
    now = int(time.time())
    payload["updatedAt"] = now
    target["updatedAt"] = now
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


async def _emit_task_status_update() -> None:
    from nanobot.agent.loop import emit_task_status_event

    await emit_task_status_event(load_task_status_payload())


async def _set_project_progress_and_emit(
    module_name: str,
    completed_names: set[str],
    module_cfg: dict[str, Any] | None = None,
) -> None:
    _set_project_progress(module_name, completed_names, module_cfg)
    await _emit_task_status_update()


def load_module_config(module_id: str) -> dict[str, Any]:
    root = get_skills_root()
    module_dir = root / module_id.strip()
    path = module_dir / "module.json"
    if not path.is_file():
        raise FileNotFoundError(f"module.json missing: {path}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("module.json must be a JSON object")
    cfg = validate_module_contract(raw)

    dashboard_path = module_dir / "data" / "dashboard.json"
    if not dashboard_path.is_file():
        raise FileNotFoundError(f"dashboard.json missing: {dashboard_path}")
    dashboard = json.loads(dashboard_path.read_text(encoding="utf-8"))
    if not isinstance(dashboard, dict):
        raise ValueError("dashboard.json must be a JSON object")
    validate_dashboard_contract(dashboard)
    return cfg


def synthetic_path_for_data_file(data_file: str) -> str:
    """构建与前端 SduiView 一致的 syntheticPath（dataFile 为 workspace 相对片段）。"""
    df = (data_file or "").strip()
    if not df:
        raise ValueError("dataFile is empty")
    return f"skill-ui://SduiView?dataFile={df}"


# 与 ``templates/module_skill_demo``、``module_boilerplate`` 等大盘里 Stepper 的 ``id`` 一致。
SDUI_STEPPER_MAIN_ID = "stepper-main"


class BoilerplateDashboardIds:
    """与 ``templates/module_boilerplate/data/dashboard.json`` 中节点 ``id`` 必须逐字一致，否则 merge Patch 不生效。"""

    CHART_DONUT = "chart-donut"
    CHART_BAR = "chart-bar"
    GOLDEN_METRICS = "golden-metrics"
    SUMMARY_TEXT = "summary-text"
    UPLOADED_FILES = "uploaded-files"
    ARTIFACTS = "artifacts"


def _boilerplate_case_config(cfg: dict[str, Any], module_id: str) -> dict[str, Any]:
    raw = cfg.get("caseTemplate") if isinstance(cfg.get("caseTemplate"), dict) else {}
    metric_labels = raw.get("metricLabels") if isinstance(raw.get("metricLabels"), dict) else {}
    strategy_options = raw.get("strategyOptions") if isinstance(raw.get("strategyOptions"), list) else []

    normalized_options: list[dict[str, str]] = []
    for item in strategy_options:
        if not isinstance(item, dict):
            continue
        sid = str(item.get("id") or "").strip()
        label = str(item.get("label") or "").strip()
        if sid and label:
            normalized_options.append({"id": sid, "label": label})

    if not normalized_options:
        normalized_options = [
            {"id": "balanced", "label": "均衡（默认）"},
            {"id": "speed", "label": "优先速度"},
            {"id": "quality", "label": "优先质量"},
        ]

    return {
        "module_title": str(raw.get("moduleTitle") or "模块案例模板").strip() or "模块案例模板",
        "module_goal": str(
            raw.get("moduleGoal")
            or "用于给业务团队复制并改造成各自模块 Skill 的参考案例。"
        ).strip(),
        "strategy_prompt": str(
            raw.get("strategyPrompt")
            or "请选择本模块案例的执行策略（用于演示 HITL 选择与后续大盘指标更新）："
        ).strip(),
        "metric_labels": {
            "throughput": str(metric_labels.get("throughput") or "吞吐").strip() or "吞吐",
            "quality": str(metric_labels.get("quality") or "质量").strip() or "质量",
            "risk": str(metric_labels.get("risk") or "风险").strip() or "风险",
        },
        "report_label": str(raw.get("reportLabel") or "模块案例交付说明.md").strip() or "模块案例交付说明.md",
        "report_file_name": str(raw.get("reportFileName") or "module_case_handover.md").strip() or "module_case_handover.md",
        "strategy_options": normalized_options,
    }


def _boilerplate_strategy_label(case_cfg: dict[str, Any], strategy_id: str) -> str:
    sid = (strategy_id or "").strip()
    for item in case_cfg.get("strategy_options", []):
        if str(item.get("id") or "").strip() == sid:
            return str(item.get("label") or sid).strip() or sid
    return sid or "未指定"


def _boilerplate_bar_data(case_cfg: dict[str, Any], throughput: int, quality: int, risk: int) -> list[dict[str, Any]]:
    labels = case_cfg["metric_labels"]
    return [
        {"label": labels["throughput"], "value": throughput, "color": "accent"},
        {"label": labels["quality"], "value": quality, "color": "success"},
        {"label": labels["risk"], "value": risk, "color": "warning"},
    ]


def _boilerplate_golden_metrics_data(
    case_cfg: dict[str, Any], throughput: int, quality: int, risk: int
) -> list[dict[str, Any]]:
    labels = case_cfg["metric_labels"]
    return [
        {"id": "metric-throughput", "label": labels["throughput"], "value": throughput, "color": "accent"},
        {"id": "metric-quality", "label": labels["quality"], "value": quality, "color": "success"},
        {"id": "metric-risk", "label": labels["risk"], "value": risk, "color": "warning"},
    ]


def _boilerplate_metrics_nodes(
    case_cfg: dict[str, Any],
    throughput: int,
    quality: int,
    risk: int,
    *,
    center_value: str,
    completed: int,
    pending: int,
    center_label: str | None = None,
) -> list[tuple[str, str, dict[str, Any]]]:
    donut_payload: dict[str, Any] = {
        "centerValue": center_value,
        "segments": [
            {"label": "已完成", "value": completed, "color": "success"},
            {"label": "待办", "value": pending, "color": "subtle"},
        ],
    }
    if center_label:
        donut_payload["centerLabel"] = center_label
    return [
        (
            BoilerplateDashboardIds.CHART_DONUT,
            "DonutChart",
            donut_payload,
        ),
        (
            BoilerplateDashboardIds.CHART_BAR,
            "BarChart",
            {"valueUnit": "分", "data": _boilerplate_bar_data(case_cfg, throughput, quality, risk)},
        ),
        (
            BoilerplateDashboardIds.GOLDEN_METRICS,
            "GoldenMetrics",
            {"metrics": _boilerplate_golden_metrics_data(case_cfg, throughput, quality, risk)},
        ),
    ]


def _write_boilerplate_report(
    *,
    module_id: str,
    case_cfg: dict[str, Any],
    strategy_label: str,
    upload_name: str,
    throughput: int,
    quality: int,
    risk: int,
) -> str:
    out_dir = get_skills_root() / module_id / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / case_cfg["report_file_name"]
    health = max(0, min(100, round((throughput + quality + (100 - risk)) / 3)))
    content = (
        f"# {case_cfg['module_title']} 交付说明\n\n"
        f"## 模块目标\n"
        f"{case_cfg['module_goal']}\n\n"
        f"## 本次样板执行结果\n"
        f"- 策略选择：{strategy_label}\n"
        f"- 上传材料：{upload_name}\n"
        f"- {case_cfg['metric_labels']['throughput']}：{throughput}\n"
        f"- {case_cfg['metric_labels']['quality']}：{quality}\n"
        f"- {case_cfg['metric_labels']['risk']}：{risk}\n"
        f"- 综合健康度：{health}%\n\n"
        f"## 给业务同事的改造建议\n"
        f"1. 保留 guide/start/choose_strategy/upload_evidence/after_upload/finish 六段流程。\n"
        f"2. 按真实业务替换 Stepper 文案与 Chart 指标，不要改掉节点 id。\n"
        f"3. 让上传材料与策略选择都走会话内 HITL 卡片，不要退回纯文本交互。\n"
        f"4. 每个关键阶段都发 SkillUiDataPatch，让右侧大盘和左侧对话保持同步。\n"
    )
    out_file.write_text(content, encoding="utf-8")
    return f"workspace/skills/{module_id}/output/{out_file.name}"


def _write_zhgk_case_report(
    *,
    module_id: str,
    case_cfg: dict[str, Any],
    strategy_label: str,
    upload_name: str,
    throughput: int,
    quality: int,
    risk: int,
) -> str:
    out_dir = get_skills_root() / module_id / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / case_cfg["report_file_name"]
    content = (
        f"# {case_cfg['module_title']} 迁移说明\n\n"
        f"## 模块目标\n"
        f"{case_cfg['module_goal']}\n\n"
        f"## 本次模块案例输入\n"
        f"- 勘测场景：{strategy_label}\n"
        f"- 资料包：{upload_name}\n\n"
        f"## 提取后的业务主线\n"
        f"1. 场景过滤：根据 BOQ / 预置集识别制冷方式、确认勘测场景，并初始化定制化底表。\n"
        f"2. 勘测汇总：汇总勘测结果、现场图片和补充材料，输出全量勘测结果表与待办清单。\n"
        f"3. 报告生成：生成满足度评估表、风险识别结果表和工勘报告。\n"
        f"4. 审批分发：把最终报告发送给专家审批，再通知干系人闭环。\n\n"
        f"## 样板大盘指标\n"
        f"- {case_cfg['metric_labels']['throughput']}：{throughput}\n"
        f"- {case_cfg['metric_labels']['quality']}：{quality}\n"
        f"- {case_cfg['metric_labels']['risk']}：{risk}\n\n"
        f"## 给业务同事的迁移建议\n"
        f"1. 继续保留 guide/start/choose_strategy/upload_evidence/after_upload/finish 的模块节奏。\n"
        f"2. 把本模块里的“勘测场景选择”替换为你们业务自己的关键 HITL 决策点。\n"
        f"3. 上传卡片建议统一收敛到资料包、底表或外部系统导出文件，避免回退为纯文本输入。\n"
        f"4. 所有阶段都要通过 SkillUiDataPatch 更新 Stepper、黄金指标和产物区，确保大盘实时同步。\n"
    )
    out_file.write_text(content, encoding="utf-8")
    return f"workspace/skills/{module_id}/output/{out_file.name}"


def _write_workbench_report(
    *,
    module_id: str,
    case_cfg: dict[str, Any],
    goal_label: str,
    upload_name: str,
    throughput: int,
    quality: int,
    risk: int,
) -> str:
    out_dir = get_skills_root() / module_id / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / case_cfg["report_file_name"]
    content = (
        f"# {case_cfg['module_title']} 结论报告\n\n"
        f"## 本次分析目标\n"
        f"- 目标：{goal_label}\n"
        f"- 上传资料：{upload_name}\n\n"
        f"## 分析阶段摘要\n"
        f"1. 已完成资料接收与结构化预览。\n"
        f"2. 已并行执行资料盘点、质量扫描、风险信号识别三个分析阶段。\n"
        f"3. 已完成串行结论汇总，并生成最终建议。\n\n"
        f"## 黄金指标\n"
        f"- {case_cfg['metric_labels']['throughput']}：{throughput}\n"
        f"- {case_cfg['metric_labels']['quality']}：{quality}\n"
        f"- {case_cfg['metric_labels']['risk']}：{risk}\n\n"
        f"## 结论建议\n"
        f"- 当前工作台展示的是标准模块骨架，可直接替换为实际业务 skill。\n"
        f"- 项目层进度建议继续由 task_progress 驱动，模块层细节建议继续由 dashboard patch 驱动。\n"
    )
    out_file.write_text(content, encoding="utf-8")
    return f"workspace/skills/{module_id}/output/{out_file.name}"


def _skill_input_dir_has_files(module_id: str) -> bool:
    """``<skills_root>/<module_id>/input`` 下是否存在至少一个文件（用于 Skill 侧预检，不经由模型）。"""
    mid = (module_id or "").strip()
    if not mid:
        return False
    d = get_skills_root() / mid / "input"
    if not d.is_dir():
        return False
    try:
        return any(p.is_file() for p in d.iterdir())
    except OSError:
        return False


def _pusher_for(cfg: dict[str, Any]) -> SkillUiPatchPusher:
    doc_id = str(cfg.get("docId") or "").strip()
    data_file = str(cfg.get("dataFile") or "").strip()
    if not doc_id or not data_file:
        raise ValueError("module.json requires docId and dataFile")
    return SkillUiPatchPusher(synthetic_path_for_data_file(data_file), doc_id=doc_id)


async def _stream_patch_frames(
    pusher: SkillUiPatchPusher,
    frames: list[list[tuple[str, str, dict[str, Any]]]],
    *,
    pause_seconds: float = 0.45,
) -> None:
    """Emit a short partial stream, then stabilize on the last frame."""
    if not frames:
        return
    for index, updates in enumerate(frames):
        is_last = index == len(frames) - 1
        await pusher.update_nodes(updates, is_partial=not is_last)
        if not is_last and pause_seconds > 0:
            await asyncio.sleep(pause_seconds)


# ── demo_compliance 流程（标准样本）────────────────────────────────────────


async def _flow_demo_compliance(
    *,
    module_id: str,
    action: str,
    state: dict[str, Any],
    thread_id: str,
    docman: Any,
    cfg: dict[str, Any],
) -> dict[str, Any]:
    pusher = _pusher_for(cfg)
    doc_id = str(cfg["docId"])
    sp = synthetic_path_for_data_file(str(cfg["dataFile"]))
    mc = MissionControlManager(thread_id=thread_id, docman=docman)
    sess = merge_module_session(thread_id, module_id, state)
    case_cfg = _boilerplate_case_config(cfg, module_id)

    if action == "cancel":
        clear_module_session(thread_id, module_id)
        return {"ok": True, "cancelled": True}

    if action == "guide":
        clear_module_session(thread_id, module_id)
        await pusher.update_node(
            SDUI_STEPPER_MAIN_ID,
            "Stepper",
            {
                "steps": [
                    {"id": "s1", "title": "初始化检查", "status": "waiting",
                     "detail": [{"title": "等待启动…", "status": "waiting"}]},
                    {"id": "s2", "title": "选择检查标准", "status": "waiting",
                     "detail": [{"title": "等待用户确认", "status": "waiting"}]},
                    {"id": "s3", "title": "上传补充材料", "status": "waiting",
                     "detail": [{"title": "等待上传", "status": "waiting"}]},
                    {"id": "s4", "title": "生成合规报告", "status": "waiting",
                     "detail": [{"title": "尚未开始", "status": "waiting"}]},
                ]
            },
        )
        await mc.emit_guidance(
            context=(
                "【安全合规检查】模块已就绪。\n"
                "流程：初始化 → 选择标准 → 上传材料 → 生成报告。\n"
                "点击下方按钮启动，或由助手调用 module_skill_runtime(action=\"start\")。"
            ),
            actions=[
                {
                    "label": "启动安全检查",
                    "verb": "module_action",
                    "payload": {"moduleId": module_id, "action": "start", "state": {}},
                },
                {
                    "label": "取消",
                    "verb": "module_action",
                    "payload": {"moduleId": module_id, "action": "cancel", "state": {}},
                },
            ],
        )
        return {"ok": True, "next": "start"}

    if action == "start":
        await pusher.update_node(
            SDUI_STEPPER_MAIN_ID,
            "Stepper",
            {
                "steps": [
                    {"id": "s1", "title": "初始化检查", "status": "running",
                     "detail": [{"title": "正在扫描配置项…", "status": "running"}]},
                    {"id": "s2", "title": "选择检查标准", "status": "waiting",
                     "detail": [{"title": "等待用户确认", "status": "waiting"}]},
                    {"id": "s3", "title": "上传补充材料", "status": "waiting",
                     "detail": [{"title": "等待上传", "status": "waiting"}]},
                    {"id": "s4", "title": "生成合规报告", "status": "waiting",
                     "detail": [{"title": "尚未开始", "status": "waiting"}]},
                ]
            },
        )
        await pusher.update_nodes([
            ("stat-total", "Statistic", {"value": "42"}),
            ("stat-passed", "Statistic", {"value": "0", "color": "success"}),
            ("stat-failed", "Statistic", {"value": "0", "color": "danger"}),
            ("stat-progress", "Statistic", {"value": "10%"}),
        ])
        return {"ok": True, "next": "choose_standard"}

    if action == "choose_standard":
        await pusher.update_node(
            SDUI_STEPPER_MAIN_ID,
            "Stepper",
            {
                "steps": [
                    {"id": "s1", "title": "初始化检查", "status": "done",
                     "detail": [{"title": "扫描完成，共 42 项", "status": "done"}]},
                    {"id": "s2", "title": "选择检查标准", "status": "running",
                     "detail": [{"title": "等待用户选择", "status": "running"}]},
                    {"id": "s3", "title": "上传补充材料", "status": "waiting",
                     "detail": [{"title": "等待上传", "status": "waiting"}]},
                    {"id": "s4", "title": "生成合规报告", "status": "waiting",
                     "detail": [{"title": "尚未开始", "status": "waiting"}]},
                ]
            },
        )
        await pusher.update_node("stat-progress", "Statistic", {"value": "25%"})
        await mc.emit_choices(
            title="请选择本次合规检查所依据的标准：",
            options=[
                {"id": "iso27001", "label": "ISO 27001（信息安全管理）"},
                {"id": "gdpr", "label": "GDPR（数据隐私保护）"},
                {"id": "pci_dss", "label": "PCI DSS（支付卡行业安全）"},
                {"id": "gb_t22080", "label": "GB/T 22080（国家标准）"},
            ],
            module_id=module_id,
            next_action="upload_material",
        )
        return {"ok": True, "next": "upload_material"}

    if action == "upload_material":
        standard = str(sess.get("standard") or state.get("standard") or "未指定")
        merge_module_session(thread_id, module_id, {"standard": standard})
        await pusher.update_node(
            SDUI_STEPPER_MAIN_ID,
            "Stepper",
            {
                "steps": [
                    {"id": "s1", "title": "初始化检查", "status": "done",
                     "detail": [{"title": "扫描完成，共 42 项", "status": "done"}]},
                    {"id": "s2", "title": "选择检查标准", "status": "done",
                     "detail": [{"title": f"已选：{standard}", "status": "done"}]},
                    {"id": "s3", "title": "上传补充材料", "status": "running",
                     "detail": [{"title": "等待上传授权声明书", "status": "running"}]},
                    {"id": "s4", "title": "生成合规报告", "status": "waiting",
                     "detail": [{"title": "尚未开始", "status": "waiting"}]},
                ]
            },
        )
        await pusher.update_node("stat-progress", "Statistic", {"value": "50%"})
        await mc.ask_for_file(
            purpose="compliance_docs",
            title=f"请上传【{standard}】所需的授权声明书（PDF/Word）",
            accept=".pdf,.doc,.docx",
            multiple=False,
            module_id=module_id,
            next_action="after_upload",
            save_relative_dir=f"skills/{module_id}/input",
        )
        return {"ok": True, "next": "after_upload"}

    if action == "after_upload":
        merged = merge_module_session(thread_id, module_id, dict(state))
        up = merged.get("upload") if isinstance(merged.get("upload"), dict) else {}
        name = str(up.get("name") or "文件")
        cid = str(merged.get("cardId") or state.get("cardId") or "").strip()
        if cid:
            await mc.replace_card(
                card_id=cid,
                title="文件已收到",
                node={
                    "type": "Card",
                    "title": f"已收到：{name}",
                    "density": "compact",
                    "children": [
                        {
                            "type": "Text",
                            "content": "材料已记录。请让助手执行 module_skill_runtime(action=\"finish\") 生成报告。",
                            "variant": "body",
                            "color": "subtle",
                        },
                    ],
                },
                doc_id=f"chat:{thread_id}",
            )
        std = str(merged.get("standard") or "")
        await pusher.update_node(
            SDUI_STEPPER_MAIN_ID,
            "Stepper",
            {
                "steps": [
                    {"id": "s1", "title": "初始化检查", "status": "done",
                     "detail": [{"title": "扫描完成，共 42 项", "status": "done"}]},
                    {"id": "s2", "title": "选择检查标准", "status": "done",
                     "detail": [{"title": f"已选：{std or '—'}", "status": "done"}]},
                    {"id": "s3", "title": "上传补充材料", "status": "done",
                     "detail": [{"title": "授权声明书已接收", "status": "done"}]},
                    {"id": "s4", "title": "生成合规报告", "status": "running",
                     "detail": [{"title": "等待生成", "status": "running"}]},
                ]
            },
        )
        await pusher.update_node("stat-progress", "Statistic", {"value": "75%"})
        return {"ok": True, "next": "finish", "hint": "调用 action=finish 完成大盘与产物"}

    if action == "finish":
        standard = str(sess.get("standard") or state.get("standard") or "合规标准")
        passed = int(state.get("passed", 38))
        failed = int(state.get("failed", 4))
        await pusher.update_node(
            SDUI_STEPPER_MAIN_ID,
            "Stepper",
            {
                "steps": [
                    {"id": "s1", "title": "初始化检查", "status": "done",
                     "detail": [{"title": "扫描完成，共 42 项", "status": "done"}]},
                    {"id": "s2", "title": "选择检查标准", "status": "done",
                     "detail": [{"title": f"已选：{standard}", "status": "done"}]},
                    {"id": "s3", "title": "上传补充材料", "status": "done",
                     "detail": [{"title": "授权声明书已接收", "status": "done"}]},
                    {"id": "s4", "title": "生成合规报告", "status": "done",
                     "detail": [{"title": "报告已生成", "status": "done"}]},
                ]
            },
        )
        await pusher.update_nodes([
            ("stat-passed", "Statistic", {"value": str(passed), "color": "success"}),
            ("stat-failed", "Statistic", {"value": str(failed), "color": "danger"}),
            ("stat-progress", "Statistic", {"value": "100%", "color": "success"}),
        ])
        out_path = f"workspace/skills/{module_id}/output/compliance_report.pdf"
        await mc.add_artifact(
            doc_id,
            synthetic_path=sp,
            artifact_id="compliance-report-001",
            label=f"{standard} 合规检查报告.pdf",
            path=out_path,
            kind="pdf",
            status="ready",
        )
        clear_module_session(thread_id, module_id)
        return {
            "ok": True,
            "done": True,
            "summary": f"检查完成：{passed} 项通过，{failed} 项风险，报告已生成。",
        }

    return {"ok": False, "error": f"unknown action: {action!r}"}


# ── module_boilerplate 流程（同事参考样板：三块大盘 + 三阶段 HITL）────────


async def _flow_module_boilerplate(
    *,
    module_id: str,
    action: str,
    state: dict[str, Any],
    thread_id: str,
    docman: Any,
    cfg: dict[str, Any],
) -> dict[str, Any]:
    pusher = _pusher_for(cfg)
    doc_id = str(cfg["docId"])
    sp = synthetic_path_for_data_file(str(cfg["dataFile"]))
    mc = MissionControlManager(thread_id=thread_id, docman=docman)
    sess = merge_module_session(thread_id, module_id, state)

    async def _emit_boilerplate_strategy_choices() -> None:
        await pusher.update_node(
            SDUI_STEPPER_MAIN_ID,
            "Stepper",
            {
                "steps": [
                    {
                        "id": "s1",
                        "title": "引导与启动",
                        "status": "done",
                        "detail": [
                            {"title": "加载配置", "status": "done"},
                            {"title": "预热指标", "status": "done"},
                        ],
                    },
                    {
                        "id": "s2",
                        "title": "策略选择 (HITL)",
                        "status": "running",
                        "detail": [{"title": "请在会话卡片中选择", "status": "running"}],
                    },
                    {
                        "id": "s3",
                        "title": "材料上传 (HITL)",
                        "status": "waiting",
                        "detail": [{"title": "等待上传", "status": "waiting"}],
                    },
                    {
                        "id": "s4",
                        "title": "交付总结",
                        "status": "waiting",
                        "detail": [{"title": "尚未开始", "status": "waiting"}],
                    },
                ]
            },
        )
        await pusher.update_node(
            BoilerplateDashboardIds.CHART_DONUT,
            "DonutChart",
            {
                "centerValue": "40%",
                "segments": [
                    {"label": "已完成", "value": 2, "color": "success"},
                    {"label": "待办", "value": 2, "color": "subtle"},
                ],
            },
        )
        await pusher.update_node(
            BoilerplateDashboardIds.CHART_BAR,
            "BarChart",
            {
                "valueUnit": "分",
                "data": _boilerplate_bar_data(case_cfg, 66, 54, 22),
            },
        )
        await pusher.update_node(
            BoilerplateDashboardIds.SUMMARY_TEXT,
            "Text",
            {
                "content": (
                    f"{case_cfg['module_title']} 已完成预热，当前进入 HITL 策略选择。"
                    " 这里的策略卡片、后续上传卡片和右侧大盘会一起联动，供各业务模块直接参考。"
                ),
                "variant": "body",
                "color": "subtle",
            },
        )
        await mc.emit_choices(
            title=case_cfg["strategy_prompt"],
            options=case_cfg["strategy_options"],
            module_id=module_id,
            next_action="upload_evidence",
        )

    if action == "cancel":
        clear_module_session(thread_id, module_id)
        return {"ok": True, "cancelled": True}

    if action == "guide":
        clear_module_session(thread_id, module_id)
        await pusher.update_node(
            SDUI_STEPPER_MAIN_ID,
            "Stepper",
            {
                "steps": [
                    {
                        "id": "s1",
                        "title": "引导与启动",
                        "status": "waiting",
                        "detail": [
                            {"title": "等待进入流程", "status": "waiting"},
                            {"title": "点击下方启动", "status": "waiting"},
                        ],
                    },
                    {
                        "id": "s2",
                        "title": "策略选择 (HITL)",
                        "status": "waiting",
                        "detail": [{"title": "等待会话内选择卡片", "status": "waiting"}],
                    },
                    {
                        "id": "s3",
                        "title": "材料上传 (HITL)",
                        "status": "waiting",
                        "detail": [{"title": "等待文件上传", "status": "waiting"}],
                    },
                    {
                        "id": "s4",
                        "title": "交付总结",
                        "status": "waiting",
                        "detail": [{"title": "生成产物与总结", "status": "waiting"}],
                    },
                ]
            },
        )
        await pusher.update_nodes(
            [
                (
                    BoilerplateDashboardIds.CHART_DONUT,
                    "DonutChart",
                    {
                        "centerLabel": "任务健康度",
                        "centerValue": "0%",
                        "segments": [
                            {"label": "已完成", "value": 0, "color": "subtle"},
                            {"label": "待办", "value": 4, "color": "subtle"},
                        ],
                    },
                ),
                (
                    BoilerplateDashboardIds.CHART_BAR,
                    "BarChart",
                    {
                        "valueUnit": "分",
                        "data": [
                            {"label": "吞吐", "value": 0, "color": "accent"},
                            {"label": "质量", "value": 0, "color": "success"},
                            {"label": "风险", "value": 0, "color": "warning"},
                        ],
                    },
                ),
            ]
        )
        await pusher.update_node(
            BoilerplateDashboardIds.SUMMARY_TEXT,
            "Text",
            {
                "content": (
                    f"{case_cfg['module_title']} 已就绪：先打开模块大盘，再通过会话内 HITL 卡片推进策略选择与材料上传。"
                    " 这是给业务同事复制并替换为自有模块 Skill 的参考案例。"
                ),
                "variant": "body",
                "color": "subtle",
            },
        )
        await mc.emit_guidance(
            context=(
                f"【{case_cfg['module_title']}】{case_cfg['module_goal']}\n"
                "本案例用于演示：先打开模块大盘，再通过左侧会话内嵌 HITL（选择 / 上传）推进流程，"
                "同时让右侧进展、黄金指标、产物总结跟着实时更新。\n"
                "流程：启动 → 策略选择 → 文件上传 → 助手调用 finish 交付。\n"
                "点击下方启动，或由助手执行 module_skill_runtime(module_id=\"module_boilerplate\", action=\"start\")。"
            ),
            actions=[
                {
                    "label": "启动样板流程",
                    "verb": "module_action",
                    "payload": {"moduleId": module_id, "action": "start", "state": {}},
                },
                {
                    "label": "取消",
                    "verb": "module_action",
                    "payload": {"moduleId": module_id, "action": "cancel", "state": {}},
                },
            ],
        )
        return {"ok": True, "next": "start"}

    if action == "start":
        fc = cfg.get("flowOptions") if isinstance(cfg.get("flowOptions"), dict) else {}
        if fc.get("requireEvidenceBeforeStrategy") and not _skill_input_dir_has_files(module_id):
            ev_dir = str(fc.get("evidenceSaveRelativeDir") or f"skills/{module_id}/input").strip()
            ev_dir = ev_dir.replace("\\", "/").strip("/")
            await pusher.update_node(
                SDUI_STEPPER_MAIN_ID,
                "Stepper",
                {
                    "steps": [
                        {
                            "id": "s1",
                            "title": "引导与启动",
                            "status": "done",
                            "detail": [
                                {"title": "加载配置", "status": "done"},
                                {"title": "预热指标", "status": "done"},
                            ],
                        },
                        {
                            "id": "s2",
                            "title": "策略选择 (HITL)",
                            "status": "waiting",
                            "detail": [{"title": "请先完成材料上传", "status": "waiting"}],
                        },
                        {
                            "id": "s3",
                            "title": "材料上传 (HITL)",
                            "status": "running",
                            "detail": [{"title": "将文件拖入会话内上传区", "status": "running"}],
                        },
                        {
                            "id": "s4",
                            "title": "交付总结",
                            "status": "waiting",
                            "detail": [{"title": "尚未开始", "status": "waiting"}],
                        },
                    ]
                },
            )
            await pusher.update_nodes(
                [
                    (
                        BoilerplateDashboardIds.CHART_DONUT,
                        "DonutChart",
                        {
                            "centerLabel": "任务健康度",
                            "centerValue": "12%",
                            "segments": [
                                {"label": "已完成", "value": 0, "color": "subtle"},
                                {"label": "待办", "value": 4, "color": "subtle"},
                            ],
                        },
                    ),
                (
                    BoilerplateDashboardIds.CHART_BAR,
                    "BarChart",
                    {
                        "valueUnit": "分",
                        "data": _boilerplate_bar_data(case_cfg, 20, 20, 40),
                    },
                ),
            ]
        )
            await pusher.update_node(
                BoilerplateDashboardIds.SUMMARY_TEXT,
            "Text",
            {
                "content": (
                    f"{case_cfg['module_title']} 尚未检测到上传材料。请在会话内使用 **拖拽上传**，"
                    f"文件将落盘到 `{ev_dir}/`；上传完成后会自动进入策略选择并同步刷新右侧指标。"
                ),
                "variant": "body",
                "color": "subtle",
            },
            )
            await mc.ask_for_file(
                purpose="boilerplate_evidence_gate",
                title="请先上传佐证材料（拖拽到会话内上传区或点击选择）",
                accept=".pdf,.doc,.docx,.txt",
                multiple=False,
                module_id=module_id,
                next_action="resume_after_evidence_gate",
                save_relative_dir=ev_dir,
            )
            return {"ok": True, "next": "resume_after_evidence_gate"}

        await pusher.update_node(
            SDUI_STEPPER_MAIN_ID,
            "Stepper",
            {
                "steps": [
                    {
                        "id": "s1",
                        "title": "引导与启动",
                        "status": "running",
                        "detail": [
                            {"title": "加载配置", "status": "done"},
                            {"title": "预热指标", "status": "running"},
                        ],
                    },
                    {
                        "id": "s2",
                        "title": "策略选择 (HITL)",
                        "status": "waiting",
                        "detail": [{"title": "等待选择卡片", "status": "waiting"}],
                    },
                    {
                        "id": "s3",
                        "title": "材料上传 (HITL)",
                        "status": "waiting",
                        "detail": [{"title": "等待上传", "status": "waiting"}],
                    },
                    {
                        "id": "s4",
                        "title": "交付总结",
                        "status": "waiting",
                        "detail": [{"title": "尚未开始", "status": "waiting"}],
                    },
                ]
            },
        )
        await pusher.update_nodes(
            [
                (
                    BoilerplateDashboardIds.CHART_DONUT,
                    "DonutChart",
                    {
                        "centerLabel": "任务健康度",
                        "centerValue": "25%",
                        "segments": [
                            {"label": "已完成", "value": 1, "color": "success"},
                            {"label": "待办", "value": 3, "color": "subtle"},
                        ],
                    },
                ),
                (
                    BoilerplateDashboardIds.CHART_BAR,
                    "BarChart",
                    {
                        "valueUnit": "分",
                        "data": _boilerplate_bar_data(case_cfg, 62, 55, 18),
                    },
                ),
            ]
        )
        await pusher.update_node(
            BoilerplateDashboardIds.SUMMARY_TEXT,
            "Text",
            {
                "content": (
                    f"{case_cfg['module_title']} 已完成启动预热，大盘已同步到“待选择策略”状态。"
                    " 接下来请通过会话内 ChoiceCard 选择执行策略。"
                ),
                "variant": "body",
                "color": "subtle",
            },
        )
        return {"ok": True, "next": "choose_strategy", "hint": "调用 module_skill_runtime(action=\"choose_strategy\") 下发 HITL 选择"}

    if action == "resume_after_evidence_gate":
        merge_module_session(thread_id, module_id, dict(state))
        await _emit_boilerplate_strategy_choices()
        return {"ok": True, "next": "upload_evidence"}

    if action == "choose_strategy":
        await _emit_boilerplate_strategy_choices()
        return {"ok": True, "next": "upload_evidence"}

    if action == "upload_evidence":
        strategy = str(sess.get("standard") or state.get("standard") or "balanced")
        merge_module_session(thread_id, module_id, {"standard": strategy})
        fc_ev = cfg.get("flowOptions") if isinstance(cfg.get("flowOptions"), dict) else {}
        sess_u = merge_module_session(thread_id, module_id, {})
        up_gate = sess_u.get("upload") if isinstance(sess_u.get("upload"), dict) else {}
        if fc_ev.get("requireEvidenceBeforeStrategy") and str(up_gate.get("fileId") or "").strip():
            return await _flow_module_boilerplate(
                module_id=module_id,
                action="after_upload",
                state=dict(state),
                thread_id=thread_id,
                docman=docman,
                cfg=cfg,
            )
        pretty = _boilerplate_strategy_label(case_cfg, strategy)
        await pusher.update_node(
            SDUI_STEPPER_MAIN_ID,
            "Stepper",
            {
                "steps": [
                    {
                        "id": "s1",
                        "title": "引导与启动",
                        "status": "done",
                        "detail": [
                            {"title": "加载配置", "status": "done"},
                            {"title": "预热指标", "status": "done"},
                        ],
                    },
                    {
                        "id": "s2",
                        "title": "策略选择 (HITL)",
                        "status": "done",
                        "detail": [{"title": f"已选：{pretty}", "status": "done"}],
                    },
                    {
                        "id": "s3",
                        "title": "材料上传 (HITL)",
                        "status": "running",
                        "detail": [{"title": "等待上传示例附件", "status": "running"}],
                    },
                    {
                        "id": "s4",
                        "title": "交付总结",
                        "status": "waiting",
                        "detail": [{"title": "尚未开始", "status": "waiting"}],
                    },
                ]
            },
        )
        await pusher.update_nodes(
            [
                (
                    BoilerplateDashboardIds.CHART_DONUT,
                    "DonutChart",
                    {
                        "centerValue": "55%",
                        "segments": [
                            {"label": "已完成", "value": 2, "color": "success"},
                            {"label": "待办", "value": 2, "color": "subtle"},
                        ],
                    },
                ),
                (
                    BoilerplateDashboardIds.CHART_BAR,
                    "BarChart",
                    {
                        "data": _boilerplate_bar_data(
                            case_cfg,
                            72,
                            68 if strategy == "quality" else 58,
                            12 if strategy == "speed" else 20,
                        ),
                    },
                ),
            ]
        )
        await pusher.update_node(
            BoilerplateDashboardIds.SUMMARY_TEXT,
            "Text",
            {
                "content": (
                    f"{case_cfg['module_title']} 已选策略：{pretty}。"
                    " 请在会话内上传一份示例材料，上传完成后右侧进展和指标会自动继续推进。"
                ),
                "variant": "body",
                "color": "subtle",
            },
        )
        await mc.ask_for_file(
            purpose="boilerplate_evidence",
            title=f"请上传一份示例材料（策略：{pretty}）",
            accept=".pdf,.doc,.docx,.txt",
            multiple=False,
            module_id=module_id,
            next_action="after_upload",
            save_relative_dir=f"skills/{module_id}/input",
        )
        return {"ok": True, "next": "after_upload"}

    if action == "after_upload":
        merged = merge_module_session(thread_id, module_id, dict(state))
        up = merged.get("upload") if isinstance(merged.get("upload"), dict) else {}
        name = str(up.get("name") or "文件")
        cid = str(merged.get("cardId") or state.get("cardId") or "").strip()
        pretty_std = _boilerplate_strategy_label(case_cfg, str(merged.get("standard") or ""))
        if cid:
            await mc.replace_card(
                card_id=cid,
                title="上传已收到",
                node={
                    "type": "Card",
                    "title": f"已收到：{name}",
                    "density": "compact",
                    "children": [
                        {
                            "type": "Text",
                            "content": "材料已记录。请让助手执行 module_skill_runtime(module_id=\"module_boilerplate\", action=\"finish\") 生成交付物与总结。",
                            "variant": "body",
                            "color": "subtle",
                        },
                    ],
                },
                doc_id=f"chat:{thread_id}",
            )
        await pusher.update_node(
            SDUI_STEPPER_MAIN_ID,
            "Stepper",
            {
                "steps": [
                    {
                        "id": "s1",
                        "title": "引导与启动",
                        "status": "done",
                        "detail": [
                            {"title": "加载配置", "status": "done"},
                            {"title": "预热指标", "status": "done"},
                        ],
                    },
                    {
                        "id": "s2",
                        "title": "策略选择 (HITL)",
                        "status": "done",
                        "detail": [{"title": f"策略：{pretty_std or '—'}", "status": "done"}],
                    },
                    {
                        "id": "s3",
                        "title": "材料上传 (HITL)",
                        "status": "done",
                        "detail": [{"title": f"已接收：{name}", "status": "done"}],
                    },
                    {
                        "id": "s4",
                        "title": "交付总结",
                        "status": "running",
                        "detail": [{"title": "等待 finish", "status": "running"}],
                    },
                ]
            },
        )
        await pusher.update_nodes(
            [
                (
                    BoilerplateDashboardIds.CHART_DONUT,
                    "DonutChart",
                    {
                        "centerValue": "75%",
                        "segments": [
                            {"label": "已完成", "value": 3, "color": "success"},
                            {"label": "待办", "value": 1, "color": "subtle"},
                        ],
                    },
                ),
                (
                    BoilerplateDashboardIds.CHART_BAR,
                    "BarChart",
                    {
                        "valueUnit": "分",
                        "data": _boilerplate_bar_data(case_cfg, 78, 74, 8),
                    },
                ),
                (
                    BoilerplateDashboardIds.SUMMARY_TEXT,
                    "Text",
                    {
                        "content": (
                            f"{case_cfg['module_title']} 已收到材料：{name}。"
                            " 现在可以调用 action=finish 生成最终交付说明，并把产物挂到右侧产物区。"
                        ),
                        "variant": "body",
                        "color": "subtle",
                    },
                ),
            ]
        )
        return {"ok": True, "next": "finish", "hint": "调用 action=finish 完成交付"}

    if action == "finish":
        strategy = str(sess.get("standard") or state.get("standard") or "balanced")
        strategy_label = _boilerplate_strategy_label(case_cfg, strategy)
        upload_meta = sess.get("upload") if isinstance(sess.get("upload"), dict) else {}
        upload_name = str(upload_meta.get("name") or "未记录材料")
        throughput = 88
        quality = 85
        risk = 8
        await pusher.update_node(
            SDUI_STEPPER_MAIN_ID,
            "Stepper",
            {
                "steps": [
                    {
                        "id": "s1",
                        "title": "引导与启动",
                        "status": "done",
                        "detail": [
                            {"title": "加载配置", "status": "done"},
                            {"title": "预热指标", "status": "done"},
                        ],
                    },
                    {
                        "id": "s2",
                        "title": "策略选择 (HITL)",
                        "status": "done",
                        "detail": [{"title": f"策略：{strategy_label}", "status": "done"}],
                    },
                    {
                        "id": "s3",
                        "title": "材料上传 (HITL)",
                        "status": "done",
                        "detail": [{"title": f"材料已归档：{upload_name}", "status": "done"}],
                    },
                    {
                        "id": "s4",
                        "title": "交付总结",
                        "status": "done",
                        "detail": [{"title": "产物已生成", "status": "done"}],
                    },
                ]
            },
        )
        await pusher.update_nodes(
            [
                (
                    BoilerplateDashboardIds.CHART_DONUT,
                    "DonutChart",
                    {
                        "centerValue": "100%",
                        "segments": [
                            {"label": "已完成", "value": 4, "color": "success"},
                            {"label": "待办", "value": 0, "color": "subtle"},
                        ],
                    },
                ),
                (
                    BoilerplateDashboardIds.CHART_BAR,
                    "BarChart",
                    {
                        "data": _boilerplate_bar_data(case_cfg, throughput, quality, risk),
                    },
                ),
                (
                    BoilerplateDashboardIds.SUMMARY_TEXT,
                    "Text",
                    {
                        "content": (
                            f"{case_cfg['module_title']} 已跑通：策略={strategy_label}，上传材料={upload_name}。"
                            " 右侧 Stepper、黄金指标、产物总结已经全程联动；同事可以复制本模块目录，"
                            "替换业务文案、图表节点和 finish 阶段的真实产物生成逻辑。"
                        ),
                        "variant": "body",
                        "color": "subtle",
                    },
                ),
            ]
        )
        out_path = _write_boilerplate_report(
            module_id=module_id,
            case_cfg=case_cfg,
            strategy_label=strategy_label,
            upload_name=upload_name,
            throughput=throughput,
            quality=quality,
            risk=risk,
        )
        await mc.add_artifact(
            doc_id,
            synthetic_path=sp,
            artifact_id="boilerplate-report-001",
            label=case_cfg["report_label"],
            path=out_path,
            kind="md",
            status="ready",
        )
        clear_module_session(thread_id, module_id)
        return {
            "ok": True,
            "done": True,
            "summary": "module_boilerplate 完成：HITL 与大盘 Patch 全链路已演示。",
        }

    return {"ok": False, "error": f"unknown action: {action!r}"}


async def _flow_zhgk_module_case(
    *,
    module_id: str,
    action: str,
    state: dict[str, Any],
    thread_id: str,
    docman: Any,
    cfg: dict[str, Any],
) -> dict[str, Any]:
    pusher = _pusher_for(cfg)
    doc_id = str(cfg["docId"])
    sp = synthetic_path_for_data_file(str(cfg["dataFile"]))
    mc = MissionControlManager(thread_id=thread_id, docman=docman)
    sess = merge_module_session(thread_id, module_id, state)
    case_cfg = _boilerplate_case_config(cfg, module_id)

    async def _emit_scene_choices() -> None:
        await pusher.update_node(
            SDUI_STEPPER_MAIN_ID,
            "Stepper",
            {
                "steps": [
                    {
                        "id": "s1",
                        "title": "大盘预热",
                        "status": "done",
                        "detail": [{"title": "模块上下文已加载", "status": "done"}],
                    },
                    {
                        "id": "s2",
                        "title": "勘测场景选择 (HITL)",
                        "status": "running",
                        "detail": [{"title": "等待用户确认场景", "status": "running"}],
                    },
                    {
                        "id": "s3",
                        "title": "资料上传 (HITL)",
                        "status": "waiting",
                        "detail": [{"title": "等待上传 BOQ / 勘测资料包", "status": "waiting"}],
                    },
                    {
                        "id": "s4",
                        "title": "工勘交付总结",
                        "status": "waiting",
                        "detail": [{"title": "尚未开始", "status": "waiting"}],
                    },
                ]
            },
        )
        await pusher.update_nodes(
            [
                (
                    BoilerplateDashboardIds.CHART_DONUT,
                    "DonutChart",
                    {
                        "centerLabel": "工勘健康度",
                        "centerValue": "40%",
                        "segments": [
                            {"label": "已完成", "value": 2, "color": "success"},
                            {"label": "待办", "value": 2, "color": "subtle"},
                        ],
                    },
                ),
                (
                    BoilerplateDashboardIds.CHART_BAR,
                    "BarChart",
                    {
                        "valueUnit": "分",
                        "data": _boilerplate_bar_data(case_cfg, 58, 46, 18),
                    },
                ),
                (
                    BoilerplateDashboardIds.SUMMARY_TEXT,
                    "Text",
                    {
                        "content": (
                            "智慧工勘模块案例已进入场景确认阶段。这里把原来的 Step 1 场景过滤能力"
                            " 收敛成会话内的 HITL 选择，选完后会继续要求上传 BOQ 或勘测资料包。"
                        ),
                        "variant": "body",
                        "color": "subtle",
                    },
                ),
            ]
        )
        await mc.emit_choices(
            title=case_cfg["strategy_prompt"],
            options=case_cfg["strategy_options"],
            module_id=module_id,
            next_action="upload_evidence",
        )

    if action == "cancel":
        clear_module_session(thread_id, module_id)
        return {"ok": True, "cancelled": True}

    if action == "guide":
        clear_module_session(thread_id, module_id)
        await pusher.update_node(
            SDUI_STEPPER_MAIN_ID,
            "Stepper",
            {
                "steps": [
                    {
                        "id": "s1",
                        "title": "大盘预热",
                        "status": "waiting",
                        "detail": [{"title": "等待启动模块案例", "status": "waiting"}],
                    },
                    {
                        "id": "s2",
                        "title": "勘测场景选择 (HITL)",
                        "status": "waiting",
                        "detail": [{"title": "待打开选择卡片", "status": "waiting"}],
                    },
                    {
                        "id": "s3",
                        "title": "资料上传 (HITL)",
                        "status": "waiting",
                        "detail": [{"title": "待打开上传卡片", "status": "waiting"}],
                    },
                    {
                        "id": "s4",
                        "title": "工勘交付总结",
                        "status": "waiting",
                        "detail": [{"title": "待生成交付说明", "status": "waiting"}],
                    },
                ]
            },
        )
        await pusher.update_nodes(
            [
                (
                    BoilerplateDashboardIds.CHART_DONUT,
                    "DonutChart",
                    {
                        "centerLabel": "工勘健康度",
                        "centerValue": "0%",
                        "segments": [
                            {"label": "已完成", "value": 0, "color": "subtle"},
                            {"label": "待办", "value": 4, "color": "subtle"},
                        ],
                    },
                ),
                (
                    BoilerplateDashboardIds.CHART_BAR,
                    "BarChart",
                    {
                        "valueUnit": "分",
                        "data": _boilerplate_bar_data(case_cfg, 0, 0, 0),
                    },
                ),
                (
                    BoilerplateDashboardIds.SUMMARY_TEXT,
                    "Text",
                    {
                        "content": (
                            "智慧工勘模块案例已就绪。这个版本把旧的场景过滤、勘测汇总、报告生成、审批分发"
                            " 四段业务主线压缩成一个可复制的模块样板，便于你们在 nanobot 上继续扩展。"
                        ),
                        "variant": "body",
                        "color": "subtle",
                    },
                ),
            ]
        )
        await mc.emit_guidance(
            context=(
                f"【{case_cfg['module_title']}】{case_cfg['module_goal']}\n"
                "模块会先打开右侧大盘，再通过左侧会话卡片完成勘测场景选择和资料上传，"
                "最终把提炼后的智慧工勘业务逻辑写入交付说明。"
            ),
            actions=[
                {
                    "label": "启动智慧工勘模块案例",
                    "verb": "module_action",
                    "payload": {"moduleId": module_id, "action": "start", "state": {}},
                },
                {
                    "label": "取消",
                    "verb": "module_action",
                    "payload": {"moduleId": module_id, "action": "cancel", "state": {}},
                },
            ],
        )
        return {"ok": True, "next": "start"}

    if action == "start":
        await pusher.update_node(
            SDUI_STEPPER_MAIN_ID,
            "Stepper",
            {
                "steps": [
                    {
                        "id": "s1",
                        "title": "大盘预热",
                        "status": "running",
                        "detail": [
                            {"title": "加载模块配置", "status": "done"},
                            {"title": "初始化业务指标", "status": "running"},
                        ],
                    },
                    {
                        "id": "s2",
                        "title": "勘测场景选择 (HITL)",
                        "status": "waiting",
                        "detail": [{"title": "等待下发场景卡片", "status": "waiting"}],
                    },
                    {
                        "id": "s3",
                        "title": "资料上传 (HITL)",
                        "status": "waiting",
                        "detail": [{"title": "待选择完成后上传", "status": "waiting"}],
                    },
                    {
                        "id": "s4",
                        "title": "工勘交付总结",
                        "status": "waiting",
                        "detail": [{"title": "尚未开始", "status": "waiting"}],
                    },
                ]
            },
        )
        await pusher.update_nodes(
            [
                (
                    BoilerplateDashboardIds.CHART_DONUT,
                    "DonutChart",
                    {
                        "centerLabel": "工勘健康度",
                        "centerValue": "20%",
                        "segments": [
                            {"label": "已完成", "value": 1, "color": "success"},
                            {"label": "待办", "value": 3, "color": "subtle"},
                        ],
                    },
                ),
                (
                    BoilerplateDashboardIds.CHART_BAR,
                    "BarChart",
                    {
                        "valueUnit": "分",
                        "data": _boilerplate_bar_data(case_cfg, 35, 22, 6),
                    },
                ),
                (
                    BoilerplateDashboardIds.SUMMARY_TEXT,
                    "Text",
                    {
                        "content": (
                            "模块大盘已打开并完成预热。下一步会要求用户选择勘测场景，"
                            "对应旧智慧工勘 Step 1 里的场景确认与过滤起点。"
                        ),
                        "variant": "body",
                        "color": "subtle",
                    },
                ),
            ]
        )
        return {"ok": True, "next": "choose_strategy"}

    if action == "choose_strategy":
        await _emit_scene_choices()
        return {"ok": True, "next": "upload_evidence"}

    if action == "upload_evidence":
        strategy = str(sess.get("standard") or state.get("standard") or "new_site")
        merge_module_session(thread_id, module_id, {"standard": strategy})
        strategy_label = _boilerplate_strategy_label(case_cfg, strategy)
        await pusher.update_node(
            SDUI_STEPPER_MAIN_ID,
            "Stepper",
            {
                "steps": [
                    {
                        "id": "s1",
                        "title": "大盘预热",
                        "status": "done",
                        "detail": [{"title": "模块上下文已加载", "status": "done"}],
                    },
                    {
                        "id": "s2",
                        "title": "勘测场景选择 (HITL)",
                        "status": "done",
                        "detail": [{"title": f"已选：{strategy_label}", "status": "done"}],
                    },
                    {
                        "id": "s3",
                        "title": "资料上传 (HITL)",
                        "status": "running",
                        "detail": [{"title": "等待上传 BOQ / 勘测资料包", "status": "running"}],
                    },
                    {
                        "id": "s4",
                        "title": "工勘交付总结",
                        "status": "waiting",
                        "detail": [{"title": "等待资料入库", "status": "waiting"}],
                    },
                ]
            },
        )
        await pusher.update_nodes(
            [
                (
                    BoilerplateDashboardIds.CHART_DONUT,
                    "DonutChart",
                    {
                        "centerValue": "55%",
                        "segments": [
                            {"label": "已完成", "value": 2, "color": "success"},
                            {"label": "待办", "value": 2, "color": "subtle"},
                        ],
                    },
                ),
                (
                    BoilerplateDashboardIds.CHART_BAR,
                    "BarChart",
                    {
                        "valueUnit": "分",
                        "data": _boilerplate_bar_data(case_cfg, 62, 48, 10),
                    },
                ),
                (
                    BoilerplateDashboardIds.SUMMARY_TEXT,
                    "Text",
                    {
                        "content": (
                            f"当前勘测场景为：{strategy_label}。请上传 BOQ、勘测结果或预置资料包，"
                            " 上传完成后会模拟推进到勘测汇总、报告生成与审批准备状态。"
                        ),
                        "variant": "body",
                        "color": "subtle",
                    },
                ),
            ]
        )
        await mc.ask_for_file(
            purpose="zhgk_case_bundle",
            title=f"请上传智慧工勘资料包（场景：{strategy_label}）",
            accept=".zip,.xlsx,.doc,.docx,.pdf",
            multiple=False,
            module_id=module_id,
            next_action="after_upload",
            save_relative_dir=f"skills/{module_id}/input",
        )
        return {"ok": True, "next": "after_upload"}

    if action == "after_upload":
        merged = merge_module_session(thread_id, module_id, dict(state))
        upload_meta = merged.get("upload") if isinstance(merged.get("upload"), dict) else {}
        upload_name = str(upload_meta.get("name") or "资料包")
        strategy_label = _boilerplate_strategy_label(case_cfg, str(merged.get("standard") or ""))
        cid = str(merged.get("cardId") or state.get("cardId") or "").strip()
        if cid:
            await mc.replace_card(
                card_id=cid,
                title="资料包已收到",
                node={
                    "type": "Card",
                    "title": f"已收到：{upload_name}",
                    "density": "compact",
                    "children": [
                        {
                            "type": "Text",
                            "content": (
                                "资料已记录。请让助手执行 "
                                "module_skill_runtime(module_id=\"zhgk_module_case\", action=\"finish\") "
                                "生成智慧工勘迁移说明。"
                            ),
                            "variant": "body",
                            "color": "subtle",
                        },
                    ],
                },
                doc_id=f"chat:{thread_id}",
            )
        await _stream_patch_frames(
            pusher,
            [
                [
                    (
                        SDUI_STEPPER_MAIN_ID,
                        "Stepper",
                        {
                            "steps": [
                                {
                                    "id": "s1",
                                    "title": "大盘预热",
                                    "status": "done",
                                    "detail": [{"title": "模块上下文已加载", "status": "done"}],
                                },
                                {
                                    "id": "s2",
                                    "title": "勘测场景选择 (HITL)",
                                    "status": "done",
                                    "detail": [{"title": f"场景：{strategy_label or '—'}", "status": "done"}],
                                },
                                {
                                    "id": "s3",
                                    "title": "资料上传 (HITL)",
                                    "status": "done",
                                    "detail": [{"title": f"已接收：{upload_name}", "status": "done"}],
                                },
                                {
                                    "id": "s4",
                                    "title": "工勘交付总结",
                                    "status": "running",
                                    "detail": [{"title": "正在解析上传资料", "status": "running"}],
                                },
                            ]
                        },
                    ),
                    (
                        BoilerplateDashboardIds.CHART_DONUT,
                        "DonutChart",
                        {
                            "centerValue": "68%",
                            "segments": [
                                {"label": "已完成", "value": 3, "color": "success"},
                                {"label": "待办", "value": 1, "color": "subtle"},
                            ],
                        },
                    ),
                    (
                        BoilerplateDashboardIds.CHART_BAR,
                        "BarChart",
                        {
                            "valueUnit": "分",
                            "data": _boilerplate_bar_data(case_cfg, 72, 61, 9),
                        },
                    ),
                    (
                        BoilerplateDashboardIds.SUMMARY_TEXT,
                        "Text",
                        {
                            "content": f"资料包 {upload_name} 已接收，正在做场景过滤与资料解析。",
                            "variant": "body",
                            "color": "subtle",
                        },
                    ),
                ],
                [
                    (
                        SDUI_STEPPER_MAIN_ID,
                        "Stepper",
                        {
                            "steps": [
                                {
                                    "id": "s1",
                                    "title": "大盘预热",
                                    "status": "done",
                                    "detail": [{"title": "模块上下文已加载", "status": "done"}],
                                },
                                {
                                    "id": "s2",
                                    "title": "勘测场景选择 (HITL)",
                                    "status": "done",
                                    "detail": [{"title": f"场景：{strategy_label or '—'}", "status": "done"}],
                                },
                                {
                                    "id": "s3",
                                    "title": "资料上传 (HITL)",
                                    "status": "done",
                                    "detail": [{"title": f"已接收：{upload_name}", "status": "done"}],
                                },
                                {
                                    "id": "s4",
                                    "title": "工勘交付总结",
                                    "status": "running",
                                    "detail": [{"title": "正在整理勘测汇总与风险项", "status": "running"}],
                                },
                            ]
                        },
                    ),
                    (
                        BoilerplateDashboardIds.CHART_DONUT,
                        "DonutChart",
                        {
                            "centerValue": "74%",
                            "segments": [
                                {"label": "已完成", "value": 3, "color": "success"},
                                {"label": "待办", "value": 1, "color": "subtle"},
                            ],
                        },
                    ),
                    (
                        BoilerplateDashboardIds.CHART_BAR,
                        "BarChart",
                        {
                            "valueUnit": "分",
                            "data": _boilerplate_bar_data(case_cfg, 77, 69, 6),
                        },
                    ),
                    (
                        BoilerplateDashboardIds.SUMMARY_TEXT,
                        "Text",
                        {
                            "content": (
                                f"资料包 {upload_name} 已入库，正在把场景过滤、勘测汇总、报告生成、审批分发"
                                f" 四段旧逻辑映射成统一模块骨架，场景={strategy_label or '未指定'}。"
                            ),
                            "variant": "body",
                            "color": "subtle",
                        },
                    ),
                ],
                [
                    (
                        SDUI_STEPPER_MAIN_ID,
                        "Stepper",
                        {
                            "steps": [
                                {
                                    "id": "s1",
                                    "title": "大盘预热",
                                    "status": "done",
                                    "detail": [{"title": "模块上下文已加载", "status": "done"}],
                                },
                                {
                                    "id": "s2",
                                    "title": "勘测场景选择 (HITL)",
                                    "status": "done",
                                    "detail": [{"title": f"场景：{strategy_label or '—'}", "status": "done"}],
                                },
                                {
                                    "id": "s3",
                                    "title": "资料上传 (HITL)",
                                    "status": "done",
                                    "detail": [{"title": f"已接收：{upload_name}", "status": "done"}],
                                },
                                {
                                    "id": "s4",
                                    "title": "工勘交付总结",
                                    "status": "running",
                                    "detail": [{"title": "汇总四段业务主线", "status": "running"}],
                                },
                            ]
                        },
                    ),
                    (
                        BoilerplateDashboardIds.CHART_DONUT,
                        "DonutChart",
                        {
                            "centerValue": "78%",
                            "segments": [
                                {"label": "已完成", "value": 3, "color": "success"},
                                {"label": "待办", "value": 1, "color": "subtle"},
                            ],
                        },
                    ),
                    (
                        BoilerplateDashboardIds.CHART_BAR,
                        "BarChart",
                        {
                            "valueUnit": "分",
                            "data": _boilerplate_bar_data(case_cfg, 80, 72, 5),
                        },
                    ),
                    (
                        BoilerplateDashboardIds.SUMMARY_TEXT,
                        "Text",
                        {
                            "content": (
                                f"资料包 {upload_name} 已入库。当前会把“场景过滤、勘测汇总、报告生成、审批分发”"
                                f" 四段旧逻辑整理成一份模块迁移说明，场景={strategy_label or '未指定'}。"
                            ),
                            "variant": "body",
                            "color": "subtle",
                        },
                    ),
                ],
            ],
        )
        return {"ok": True, "next": "finish", "hint": "调用 action=finish 生成交付说明"}

    if action == "finish":
        strategy = str(sess.get("standard") or state.get("standard") or "new_site")
        strategy_label = _boilerplate_strategy_label(case_cfg, strategy)
        upload_meta = sess.get("upload") if isinstance(sess.get("upload"), dict) else {}
        upload_name = str(upload_meta.get("name") or "未记录资料包")
        throughput = 92
        quality = 86
        risk = 4
        await pusher.update_node(
            SDUI_STEPPER_MAIN_ID,
            "Stepper",
            {
                "steps": [
                    {
                        "id": "s1",
                        "title": "大盘预热",
                        "status": "done",
                        "detail": [{"title": "模块上下文已加载", "status": "done"}],
                    },
                    {
                        "id": "s2",
                        "title": "勘测场景选择 (HITL)",
                        "status": "done",
                        "detail": [{"title": f"场景：{strategy_label}", "status": "done"}],
                    },
                    {
                        "id": "s3",
                        "title": "资料上传 (HITL)",
                        "status": "done",
                        "detail": [{"title": f"资料包：{upload_name}", "status": "done"}],
                    },
                    {
                        "id": "s4",
                        "title": "工勘交付总结",
                        "status": "done",
                        "detail": [{"title": "迁移说明已生成", "status": "done"}],
                    },
                ]
            },
        )
        await pusher.update_nodes(
            [
                (
                    BoilerplateDashboardIds.CHART_DONUT,
                    "DonutChart",
                    {
                        "centerValue": "100%",
                        "segments": [
                            {"label": "已完成", "value": 4, "color": "success"},
                            {"label": "待办", "value": 0, "color": "subtle"},
                        ],
                    },
                ),
                (
                    BoilerplateDashboardIds.CHART_BAR,
                    "BarChart",
                    {
                        "valueUnit": "分",
                        "data": _boilerplate_bar_data(case_cfg, throughput, quality, risk),
                    },
                ),
                (
                    BoilerplateDashboardIds.SUMMARY_TEXT,
                    "Text",
                    {
                        "content": (
                            "智慧工勘模块案例已完成迁移：右侧大盘能够跟随 HITL 场景选择、资料上传和最终交付"
                            " 实时刷新；交付说明已把旧版四段业务主线提炼成一个可复制的模块样板。"
                        ),
                        "variant": "body",
                        "color": "subtle",
                    },
                ),
            ]
        )
        out_path = _write_zhgk_case_report(
            module_id=module_id,
            case_cfg=case_cfg,
            strategy_label=strategy_label,
            upload_name=upload_name,
            throughput=throughput,
            quality=quality,
            risk=risk,
        )
        await mc.add_artifact(
            doc_id,
            synthetic_path=sp,
            artifact_id="zhgk-module-case-report-001",
            label=case_cfg["report_label"],
            path=out_path,
            kind="md",
            status="ready",
        )
        clear_module_session(thread_id, module_id)
        return {
            "ok": True,
            "done": True,
            "summary": "zhgk_module_case 完成：智慧工勘模块案例已生成并挂载交付说明。",
        }

    return {"ok": False, "error": f"unknown action: {action!r}"}


async def _flow_intelligent_analysis_workbench(
    *,
    module_id: str,
    action: str,
    state: dict[str, Any],
    thread_id: str,
    docman: Any,
    cfg: dict[str, Any],
) -> dict[str, Any]:
    pusher = _pusher_for(cfg)
    doc_id = str(cfg["docId"])
    sp = synthetic_path_for_data_file(str(cfg["dataFile"]))
    mc = MissionControlManager(thread_id=thread_id, docman=docman)
    sess = merge_module_session(thread_id, module_id, state)
    case_cfg = _boilerplate_case_config(cfg, module_id)
    progress_module_name = _task_progress_definition(case_cfg["module_title"], cfg)["module_name"]

    if action == "cancel":
        clear_module_session(thread_id, module_id)
        await _set_project_progress_and_emit(progress_module_name, set(), cfg)
        return {"ok": True, "cancelled": True}

    if action == "guide":
        clear_module_session(thread_id, module_id)
        await _set_project_progress_and_emit(
            progress_module_name,
            _configured_completed_tasks(cfg, "guide", {"模块待启动"}, module_name=progress_module_name),
            cfg,
        )
        await pusher.update_nodes(
            [
                (
                    SDUI_STEPPER_MAIN_ID,
                    "Stepper",
                    {
                        "steps": [
                            {"id": "s1", "title": "项目引导与进入模块", "status": "running", "detail": [{"title": "已从项目总览进入", "status": "running"}]},
                            {"id": "s2", "title": "目标选择 (HITL)", "status": "waiting", "detail": [{"title": "等待选择分析目标", "status": "waiting"}]},
                            {"id": "s3", "title": "资料上传与预览", "status": "waiting", "detail": [{"title": "等待上传分析资料", "status": "waiting"}]},
                            {"id": "s4", "title": "并行分析执行", "status": "waiting", "detail": [{"title": "等待启动分析阶段", "status": "waiting"}]},
                            {"id": "s5", "title": "结论汇总与产物", "status": "waiting", "detail": [{"title": "等待生成结论", "status": "waiting"}]},
                        ]
                    },
                ),
                *_boilerplate_metrics_nodes(
                    case_cfg,
                    8,
                    5,
                    0,
                    center_label="分析健康度",
                    center_value="8%",
                    completed=0,
                    pending=5,
                ),
                (
                    BoilerplateDashboardIds.SUMMARY_TEXT,
                    "Text",
                    {
                        "content": "你已进入智能分析工作台。下一步请先选择本次分析目标，再上传资料并进入并行分析阶段。",
                        "variant": "body",
                        "color": "subtle",
                    },
                ),
                (
                    BoilerplateDashboardIds.UPLOADED_FILES,
                    "ArtifactGrid",
                    {"title": "已上传文件", "mode": "input", "artifacts": []},
                ),
            ]
        )
        await mc.emit_guidance(
            context="智能分析工作台已就绪。先选择分析目标，再上传资料，随后系统会进入并行分析与结论汇总。",
            actions=[
                {
                    "label": "选择分析目标",
                    "verb": "module_action",
                    "payload": {"moduleId": module_id, "action": "select_goal", "state": {}},
                }
            ],
        )
        return {"ok": True, "next": "select_goal"}

    if action == "select_goal":
        await pusher.update_nodes(
            [
                (
                    SDUI_STEPPER_MAIN_ID,
                    "Stepper",
                    {
                        "steps": [
                            {"id": "s1", "title": "项目引导与进入模块", "status": "done", "detail": [{"title": "模块已打开", "status": "done"}]},
                            {"id": "s2", "title": "目标选择 (HITL)", "status": "running", "detail": [{"title": "等待用户选择目标", "status": "running"}]},
                            {"id": "s3", "title": "资料上传与预览", "status": "waiting", "detail": [{"title": "等待目标确认", "status": "waiting"}]},
                            {"id": "s4", "title": "并行分析执行", "status": "waiting", "detail": [{"title": "等待分析阶段", "status": "waiting"}]},
                            {"id": "s5", "title": "结论汇总与产物", "status": "waiting", "detail": [{"title": "等待结论阶段", "status": "waiting"}]},
                        ]
                    },
                ),
                (
                    BoilerplateDashboardIds.SUMMARY_TEXT,
                    "Text",
                    {
                        "content": "请选择本次分析目标。这个 HITL 决策点会影响后续上传提示、并行分析重点和最终结论组织方式。",
                        "variant": "body",
                        "color": "subtle",
                    },
                ),
            ]
        )
        await mc.emit_choices(
            title=case_cfg["strategy_prompt"],
            options=case_cfg["strategy_options"],
            module_id=module_id,
            next_action="upload_bundle",
        )
        return {"ok": True, "next": "upload_bundle"}

    if action == "upload_bundle":
        goal = str(sess.get("standard") or state.get("standard") or "comprehensive")
        merge_module_session(thread_id, module_id, {"standard": goal})
        goal_label = _boilerplate_strategy_label(case_cfg, goal)
        await _set_project_progress_and_emit(
            progress_module_name,
            _configured_completed_tasks(
                cfg,
                "upload_bundle",
                {"模块待启动", "分析目标已确认"},
                module_name=progress_module_name,
            ),
            cfg,
        )
        upload_cfg = _upload_config(cfg, "analysis_bundle")
        await pusher.update_nodes(
            [
                (
                    SDUI_STEPPER_MAIN_ID,
                    "Stepper",
                    {
                        "steps": [
                            {"id": "s1", "title": "项目引导与进入模块", "status": "done", "detail": [{"title": "模块已打开", "status": "done"}]},
                            {"id": "s2", "title": "目标选择 (HITL)", "status": "done", "detail": [{"title": f"目标：{goal_label}", "status": "done"}]},
                            {"id": "s3", "title": "资料上传与预览", "status": "running", "detail": [{"title": "等待上传资料", "status": "running"}]},
                            {"id": "s4", "title": "并行分析执行", "status": "waiting", "detail": [{"title": "等待上传完成", "status": "waiting"}]},
                            {"id": "s5", "title": "结论汇总与产物", "status": "waiting", "detail": [{"title": "等待结论阶段", "status": "waiting"}]},
                        ]
                    },
                ),
                *_boilerplate_metrics_nodes(
                    case_cfg,
                    26,
                    18,
                    2,
                    center_value="22%",
                    completed=1,
                    pending=4,
                ),
                (
                    BoilerplateDashboardIds.SUMMARY_TEXT,
                    "Text",
                    {
                        "content": f"当前分析目标为：{goal_label}。请上传本次分析资料，上传后会先展示预览卡片，再进入并行分析阶段。",
                        "variant": "body",
                        "color": "subtle",
                    },
                ),
                (
                    BoilerplateDashboardIds.UPLOADED_FILES,
                    "ArtifactGrid",
                    {"title": "已上传文件", "mode": "input", "artifacts": []},
                ),
            ]
        )
        await mc.ask_for_file(
            purpose="analysis_bundle",
            title=f"请上传分析资料包（目标：{goal_label}）",
            accept=str(upload_cfg.get("accept") or ".zip,.xlsx,.csv,.pdf,.doc,.docx,.png,.jpg"),
            multiple=bool(upload_cfg.get("multiple", True)),
            module_id=module_id,
            next_action="upload_bundle_complete",
            save_relative_dir=str(upload_cfg.get("save_relative_dir") or f"skills/{module_id}/input"),
        )
        return {"ok": True, "next": "upload_bundle_complete"}

    if action == "upload_bundle_complete":
        merged = merge_module_session(thread_id, module_id, dict(state))
        uploads = _merge_uploads(merged.get("uploads"), state.get("uploads"))
        upload_meta = dict(_latest_upload_meta({"upload": merged.get("upload"), "uploads": uploads}))
        if not uploads and upload_meta:
            uploads = [upload_meta]
        merged = merge_module_session(
            thread_id,
            module_id,
            {"upload": upload_meta or None, "uploads": uploads},
        )
        upload_name = str(upload_meta.get("name") or "分析资料包")
        goal = str(merged.get("standard") or state.get("standard") or "comprehensive")
        goal_label = _boilerplate_strategy_label(case_cfg, goal)
        upload_count = len(uploads)
        await _set_project_progress_and_emit(
            progress_module_name,
            _configured_completed_tasks(
                cfg,
                "upload_bundle_complete",
                {"模块待启动", "分析目标已确认", "资料已上传"},
                module_name=progress_module_name,
            ),
            cfg,
        )
        await pusher.update_nodes(
            [
                (
                    SDUI_STEPPER_MAIN_ID,
                    "Stepper",
                    {
                        "steps": [
                            {"id": "s1", "title": "项目引导与进入模块", "status": "done", "detail": [{"title": "模块已打开", "status": "done"}]},
                            {"id": "s2", "title": "目标选择 (HITL)", "status": "done", "detail": [{"title": f"目标：{goal_label}", "status": "done"}]},
                            {"id": "s3", "title": "资料上传与预览", "status": "done", "detail": [{"title": f"已上传：{upload_name}", "status": "done"}]},
                            {"id": "s4", "title": "并行分析执行", "status": "waiting", "detail": [{"title": "等待启动分析", "status": "waiting"}]},
                            {"id": "s5", "title": "结论汇总与产物", "status": "waiting", "detail": [{"title": "等待结论阶段", "status": "waiting"}]},
                        ]
                    },
                ),
                *_boilerplate_metrics_nodes(case_cfg, 41, 29, 4, center_value="36%", completed=2, pending=3),
                (
                    BoilerplateDashboardIds.UPLOADED_FILES,
                    "ArtifactGrid",
                    {"title": "已上传文件", "mode": "input", "artifacts": _uploads_as_artifacts(uploads)},
                ),
                (
                    BoilerplateDashboardIds.SUMMARY_TEXT,
                    "Text",
                    {
                        "content": f"已接收 {upload_count} 份资料，最近上传：{upload_name}。你可以继续补传，或直接开始并行分析。",
                        "variant": "body",
                        "color": "subtle",
                    },
                ),
            ]
        )
        cid = str(merged.get("cardId") or state.get("cardId") or "").strip()
        if cid:
            await mc.replace_card(
                card_id=cid,
                title="资料已上传",
                node={
                    "type": "Stack",
                    "gap": "sm",
                    "children": [
                        {
                            "type": "Text",
                            "variant": "body",
                            "content": f"已接收 {upload_count} 份资料，目标为 {goal_label}。可继续补传资料，或直接进入并行分析。",
                            "color": "subtle",
                        },
                        {
                            "type": "ArtifactGrid",
                            "title": "已上传文件",
                            "mode": "input",
                            "artifacts": _uploads_as_artifacts(uploads),
                        },
                        {
                            "type": "GuidanceCard",
                            "cardId": cid,
                            "context": "资料已入库。可以继续上传更多文件，也可以开始并行分析。",
                            "actions": [
                                {
                                    "label": "继续上传",
                                    "verb": "module_action",
                                    "payload": {
                                        "moduleId": module_id,
                                        "action": "upload_bundle",
                                        "state": {"standard": goal, "upload": upload_meta, "uploads": uploads},
                                    },
                                },
                                {
                                    "label": "开始分析",
                                    "verb": "module_action",
                                    "payload": {
                                        "moduleId": module_id,
                                        "action": "run_parallel_skills",
                                        "state": {"standard": goal, "upload": upload_meta, "uploads": uploads},
                                    },
                                },
                            ],
                        },
                    ],
                },
                doc_id=f"chat:{thread_id}",
            )
        return {"ok": True, "next": "run_parallel_skills"}

    if action == "run_parallel_skills":
        merged = merge_module_session(thread_id, module_id, dict(state))
        uploads = _merge_uploads(merged.get("uploads"), state.get("uploads"))
        upload_meta = dict(_latest_upload_meta({"upload": merged.get("upload"), "uploads": uploads}))
        if not uploads and upload_meta:
            uploads = [upload_meta]
        merged = merge_module_session(
            thread_id,
            module_id,
            {"upload": upload_meta or None, "uploads": uploads},
        )
        upload_name = str(upload_meta.get("name") or "分析资料包")
        goal_label = _boilerplate_strategy_label(case_cfg, str(merged.get("standard") or "comprehensive"))
        await _set_project_progress_and_emit(
            progress_module_name,
            _configured_completed_tasks(
                cfg,
                "run_parallel_skills",
                {"模块待启动", "分析目标已确认", "资料已上传", "并行分析进行中"},
                module_name=progress_module_name,
            ),
            cfg,
        )
        cid = str(merged.get("cardId") or state.get("cardId") or "").strip()
        if cid:
            await mc.replace_card(
                card_id=cid,
                title="资料已上传",
                node={
                    "type": "Stack",
                    "gap": "sm",
                    "children": [
                        {
                            "type": "Text",
                            "content": f"已上传：{upload_name}，当前目标：{goal_label}。资料已接收，正在进入并行分析阶段。",
                            "variant": "body",
                            "color": "subtle",
                        },
                        {
                            "type": "ArtifactGrid",
                            "title": "已上传文件",
                            "mode": "input",
                            "artifacts": _uploads_as_artifacts(uploads),
                        },
                    ],
                },
                doc_id=f"chat:{thread_id}",
            )
        await _stream_patch_frames(
            pusher,
            [
                [
                    (
                        SDUI_STEPPER_MAIN_ID,
                        "Stepper",
                        {
                            "steps": [
                                {"id": "s1", "title": "项目引导与进入模块", "status": "done", "detail": [{"title": "模块已打开", "status": "done"}]},
                                {"id": "s2", "title": "目标选择 (HITL)", "status": "done", "detail": [{"title": f"目标：{goal_label}", "status": "done"}]},
                                {"id": "s3", "title": "资料上传与预览", "status": "done", "detail": [{"title": f"已上传：{upload_name}", "status": "done"}]},
                                {"id": "s4", "title": "并行分析执行", "status": "running", "detail": [{"title": "资料盘点进行中", "status": "running"}]},
                                {"id": "s5", "title": "结论汇总与产物", "status": "waiting", "detail": [{"title": "等待汇总", "status": "waiting"}]},
                            ]
                        },
                    ),
                    *_boilerplate_metrics_nodes(case_cfg, 48, 32, 6, center_value="40%", completed=2, pending=3),
                    (
                        BoilerplateDashboardIds.UPLOADED_FILES,
                        "ArtifactGrid",
                        {"title": "已上传文件", "mode": "input", "artifacts": _uploads_as_artifacts(uploads)},
                    ),
                    (BoilerplateDashboardIds.SUMMARY_TEXT, "Text", {"content": f"已接收 {upload_name}，正在并行执行资料盘点。", "variant": "body", "color": "subtle"}),
                ],
                [
                    (
                        SDUI_STEPPER_MAIN_ID,
                        "Stepper",
                        {
                            "steps": [
                                {"id": "s1", "title": "项目引导与进入模块", "status": "done", "detail": [{"title": "模块已打开", "status": "done"}]},
                                {"id": "s2", "title": "目标选择 (HITL)", "status": "done", "detail": [{"title": f"目标：{goal_label}", "status": "done"}]},
                                {"id": "s3", "title": "资料上传与预览", "status": "done", "detail": [{"title": f"已上传：{upload_name}", "status": "done"}]},
                                {"id": "s4", "title": "并行分析执行", "status": "running", "detail": [{"title": "质量扫描进行中", "status": "running"}]},
                                {"id": "s5", "title": "结论汇总与产物", "status": "waiting", "detail": [{"title": "等待汇总", "status": "waiting"}]},
                            ]
                        },
                    ),
                    *_boilerplate_metrics_nodes(case_cfg, 63, 49, 10, center_value="55%", completed=3, pending=2),
                    (
                        BoilerplateDashboardIds.UPLOADED_FILES,
                        "ArtifactGrid",
                        {"title": "已上传文件", "mode": "input", "artifacts": _uploads_as_artifacts(uploads)},
                    ),
                    (BoilerplateDashboardIds.SUMMARY_TEXT, "Text", {"content": f"{upload_name} 已进入质量扫描阶段，正在提取可用结构与异常点。", "variant": "body", "color": "subtle"}),
                ],
                [
                    (
                        SDUI_STEPPER_MAIN_ID,
                        "Stepper",
                        {
                            "steps": [
                                {"id": "s1", "title": "项目引导与进入模块", "status": "done", "detail": [{"title": "模块已打开", "status": "done"}]},
                                {"id": "s2", "title": "目标选择 (HITL)", "status": "done", "detail": [{"title": f"目标：{goal_label}", "status": "done"}]},
                                {"id": "s3", "title": "资料上传与预览", "status": "done", "detail": [{"title": f"已上传：{upload_name}", "status": "done"}]},
                                {"id": "s4", "title": "并行分析执行", "status": "running", "detail": [{"title": "风险信号识别进行中", "status": "running"}]},
                                {"id": "s5", "title": "结论汇总与产物", "status": "waiting", "detail": [{"title": "等待汇总", "status": "waiting"}]},
                            ]
                        },
                    ),
                    *_boilerplate_metrics_nodes(case_cfg, 72, 58, 16, center_value="68%", completed=3, pending=2),
                    (
                        BoilerplateDashboardIds.UPLOADED_FILES,
                        "ArtifactGrid",
                        {"title": "已上传文件", "mode": "input", "artifacts": _uploads_as_artifacts(uploads)},
                    ),
                    (BoilerplateDashboardIds.SUMMARY_TEXT, "Text", {"content": f"{upload_name} 已进入风险信号识别阶段，并行分析正在完成最后一轮收敛。", "variant": "body", "color": "subtle"}),
                ],
                [
                    (
                        SDUI_STEPPER_MAIN_ID,
                        "Stepper",
                        {
                            "steps": [
                                {"id": "s1", "title": "项目引导与进入模块", "status": "done", "detail": [{"title": "模块已打开", "status": "done"}]},
                                {"id": "s2", "title": "目标选择 (HITL)", "status": "done", "detail": [{"title": f"目标：{goal_label}", "status": "done"}]},
                                {"id": "s3", "title": "资料上传与预览", "status": "done", "detail": [{"title": f"已上传：{upload_name}", "status": "done"}]},
                                {"id": "s4", "title": "并行分析执行", "status": "done", "detail": [{"title": "三路分析已完成", "status": "done"}]},
                                {"id": "s5", "title": "结论汇总与产物", "status": "running", "detail": [{"title": "准备进入结论汇总", "status": "running"}]},
                            ]
                        },
                    ),
                    *_boilerplate_metrics_nodes(case_cfg, 79, 66, 14, center_value="74%", completed=4, pending=1),
                    (
                        BoilerplateDashboardIds.UPLOADED_FILES,
                        "ArtifactGrid",
                        {"title": "已上传文件", "mode": "input", "artifacts": _uploads_as_artifacts(uploads)},
                    ),
                    (BoilerplateDashboardIds.SUMMARY_TEXT, "Text", {"content": f"{upload_name} 的并行分析已完成，下一步开始串行汇总结论。", "variant": "body", "color": "subtle"}),
                ],
            ],
        )
        return {"ok": True, "next": "synthesize_result"}

    if action == "synthesize_result":
        merged = merge_module_session(thread_id, module_id, dict(state))
        upload_meta = _latest_upload_meta(merged)
        upload_name = str(upload_meta.get("name") or "分析资料包")
        goal_label = _boilerplate_strategy_label(case_cfg, str(merged.get("standard") or "comprehensive"))
        uploads = _merge_uploads(merged.get("uploads"), state.get("uploads"))
        await _set_project_progress_and_emit(
            progress_module_name,
            _configured_completed_tasks(
                cfg,
                "synthesize_result",
                {"模块待启动", "分析目标已确认", "资料已上传", "并行分析进行中", "结论汇总中"},
                module_name=progress_module_name,
            ),
            cfg,
        )
        await _stream_patch_frames(
            pusher,
            [
                [
                    (
                        BoilerplateDashboardIds.UPLOADED_FILES,
                        "ArtifactGrid",
                        {"title": "已上传文件", "mode": "input", "artifacts": _uploads_as_artifacts(uploads)},
                    ),
                    (BoilerplateDashboardIds.SUMMARY_TEXT, "Text", {"content": "正在汇总资料盘点、质量扫描和风险信号识别结果。", "variant": "body", "color": "subtle"}),
                    *_boilerplate_metrics_nodes(case_cfg, 82, 74, 12, center_value="82%", completed=4, pending=1),
                ],
                [
                    (
                        BoilerplateDashboardIds.UPLOADED_FILES,
                        "ArtifactGrid",
                        {"title": "已上传文件", "mode": "input", "artifacts": _uploads_as_artifacts(uploads)},
                    ),
                    (BoilerplateDashboardIds.SUMMARY_TEXT, "Text", {"content": f"已形成初步结论：目标={goal_label}，资料={upload_name}，建议进入最终产物生成。", "variant": "body", "color": "subtle"}),
                    *_boilerplate_metrics_nodes(case_cfg, 86, 81, 9, center_value="88%", completed=4, pending=1),
                ],
            ],
        )
        return {"ok": True, "next": "finish"}

    if action == "finish":
        goal = str(sess.get("standard") or state.get("standard") or "comprehensive")
        goal_label = _boilerplate_strategy_label(case_cfg, goal)
        upload_meta = _latest_upload_meta(sess)
        upload_name = str(upload_meta.get("name") or "分析资料包")
        uploads = _merge_uploads(sess.get("uploads"), state.get("uploads"))
        throughput = 92
        quality = 88
        risk = 7
        await _set_project_progress_and_emit(
            progress_module_name,
            _configured_completed_tasks(
                cfg,
                "finish",
                {"模块待启动", "分析目标已确认", "资料已上传", "并行分析进行中", "结论汇总中", "分析完成"},
                module_name=progress_module_name,
            ),
            cfg,
        )
        await pusher.update_nodes(
            [
                (
                    SDUI_STEPPER_MAIN_ID,
                    "Stepper",
                    {
                        "steps": [
                            {"id": "s1", "title": "项目引导与进入模块", "status": "done", "detail": [{"title": "模块已打开", "status": "done"}]},
                            {"id": "s2", "title": "目标选择 (HITL)", "status": "done", "detail": [{"title": f"目标：{goal_label}", "status": "done"}]},
                            {"id": "s3", "title": "资料上传与预览", "status": "done", "detail": [{"title": f"已上传：{upload_name}", "status": "done"}]},
                            {"id": "s4", "title": "并行分析执行", "status": "done", "detail": [{"title": "三路分析已完成", "status": "done"}]},
                            {"id": "s5", "title": "结论汇总与产物", "status": "done", "detail": [{"title": "最终结论已生成", "status": "done"}]},
                        ]
                    },
                ),
                *_boilerplate_metrics_nodes(case_cfg, throughput, quality, risk, center_value="100%", completed=5, pending=0),
                (
                    BoilerplateDashboardIds.UPLOADED_FILES,
                    "ArtifactGrid",
                    {"title": "已上传文件", "mode": "input", "artifacts": _uploads_as_artifacts(uploads)},
                ),
                (
                    BoilerplateDashboardIds.SUMMARY_TEXT,
                    "Text",
                    {
                        "content": (
                            f"智能分析工作台已完成本轮演示：目标={goal_label}，资料={upload_name}。"
                            " 已完整展示项目引导、HITL、上传预览、并行分析、串行汇总和产物结论。"
                        ),
                        "variant": "body",
                        "color": "subtle",
                    },
                ),
            ]
        )
        out_path = _write_workbench_report(
            module_id=module_id,
            case_cfg=case_cfg,
            goal_label=goal_label,
            upload_name=upload_name,
            throughput=throughput,
            quality=quality,
            risk=risk,
        )
        await mc.add_artifact(
            doc_id,
            synthetic_path=sp,
            artifact_id="intelligent-analysis-workbench-report-001",
            label=case_cfg["report_label"],
            path=out_path,
            kind="md",
            status="ready",
        )
        clear_module_session(thread_id, module_id)
        return {"ok": True, "done": True, "summary": "intelligent_analysis_workbench 完成：标准案例已生成。"}

    return {"ok": False, "error": f"unknown action: {action!r}"}


async def run_module_action(
    *,
    module_id: str,
    action: str,
    state: dict[str, Any] | None,
    thread_id: str | None,
    docman: Any = None,
) -> dict[str, Any]:
    tid = (thread_id or get_current_thread_id() or "").strip()
    if not tid:
        return {"ok": False, "error": "thread_id missing (not in web chat context)"}
    mid = (module_id or "").strip()
    act = (action or "").strip()
    if not mid or not act:
        return {"ok": False, "error": "module_id and action are required"}
    try:
        cfg = load_module_config(mid)
    except (OSError, ValueError, json.JSONDecodeError) as e:
        logger.warning("module_skill_runtime load failed | module={} | {}", mid, e)
        return {"ok": False, "error": str(e)}
    flow = str(cfg.get("flow") or "demo_compliance")
    st = dict(state or {})

    await _emit_module_session_focus(tid, mid, "running")
    try:
        if flow == "demo_compliance":
            result = await _flow_demo_compliance(
                module_id=mid,
                action=act,
                state=st,
                thread_id=tid,
                docman=docman,
                cfg=cfg,
            )
        elif flow == "module_boilerplate":
            result = await _flow_module_boilerplate(
                module_id=mid,
                action=act,
                state=st,
                thread_id=tid,
                docman=docman,
                cfg=cfg,
            )
        elif flow == "zhgk_module_case":
            result = await _flow_zhgk_module_case(
                module_id=mid,
                action=act,
                state=st,
                thread_id=tid,
                docman=docman,
                cfg=cfg,
            )
        elif flow == "intelligent_analysis_workbench":
            result = await _flow_intelligent_analysis_workbench(
                module_id=mid,
                action=act,
                state=st,
                thread_id=tid,
                docman=docman,
                cfg=cfg,
            )
        else:
            result = {"ok": False, "error": f"unsupported flow: {flow!r}"}
    except Exception as e:
        logger.exception("module_skill_runtime flow failed | module={} | action={} | {}", mid, act, e)
        await _emit_module_session_focus(tid, mid, "idle")
        return {"ok": False, "error": str(e)}

    if not result.get("ok"):
        await _emit_module_session_focus(tid, mid, "idle")
    elif act in _ACTIONS_EMIT_IDLE_AFTER:
        await _emit_module_session_focus(tid, mid, "idle")
    return result


def parse_module_action_payload(payload: Any) -> tuple[str, str, dict[str, Any]] | None:
    """从 chat_card_intent / module_action 的 payload 解析 (module_id, action, state)。"""
    if not isinstance(payload, dict):
        return None
    mid = str(payload.get("moduleId") or "").strip()
    act = str(payload.get("action") or "").strip()
    raw_state = payload.get("state")
    st: dict[str, Any] = dict(raw_state) if isinstance(raw_state, dict) else {}
    if not mid or not act:
        return None
    return mid, act, st


async def dispatch_chat_card_intent(
    intent: dict[str, Any] | None,
    *,
    thread_id: str,
    docman: Any = None,
) -> tuple[bool, str]:
    """解析会话内 HITL 的 ``chat_card_intent``；若已消费则返回 (True, RunFinished.message)。"""
    if not intent:
        return False, ""
    verb = str(intent.get("verb") or "")
    card_id = str(intent.get("cardId") or "").strip()
    payload = intent.get("payload")

    if verb == "module_action":
        parsed = parse_module_action_payload(payload)
        if not parsed:
            return True, json.dumps({"ok": False, "error": "invalid module_action payload"}, ensure_ascii=False)
        mid, act, st = parsed
        if card_id:
            st = {**st, "cardId": card_id}
        result = await run_module_action(
            module_id=mid, action=act, state=st, thread_id=thread_id, docman=docman
        )
        return True, json.dumps(result, ensure_ascii=False)

    if verb == "choice_selected" and isinstance(payload, dict):
        mid = str(payload.get("moduleId") or "").strip()
        na = str(payload.get("nextAction") or "").strip()
        opt = payload.get("optionId")
        if mid and na and opt is not None:
            st: dict[str, Any] = {"standard": str(opt)}
            if card_id:
                st["cardId"] = card_id
            result = await run_module_action(
                module_id=mid, action=na, state=st, thread_id=thread_id, docman=docman
            )
            return True, json.dumps(result, ensure_ascii=False)

    return False, ""
