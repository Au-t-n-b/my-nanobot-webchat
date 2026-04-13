"""统一模块 Skill 运行时：按 module.json + flow 驱动大盘 Patch 与 HITL ChatCard。

业务团队在 ``<skills_root>/<module_id>/`` 下交付 ``module.json``、``SKILL.md``、``data/dashboard.json``；
模型通过工具 ``module_skill_runtime`` 或 Fast-path ``chat_card_intent`` 调用本模块。
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
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
from nanobot.web.task_progress import load_task_status_payload, normalize_task_progress_payload, task_progress_file_path

# 执行结束后发 idle。guide/start 不发 idle，让前端保持「模块进行中」并停在模块大盘，直到 finish/cancel。
_ACTIONS_EMIT_IDLE_AFTER: frozenset[str] = frozenset({"cancel", "finish", "approval_pass"})


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
) -> dict[str, Any]:
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

    expected_task_order = definition["tasks"]
    target["tasks"] = [
        {"name": name, "completed": name in completed_names}
        for name in expected_task_order
        if name
    ]
    now = int(time.time())
    payload["updatedAt"] = now
    target["updatedAt"] = now
    try:
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as exc:
        logger.warning("task_progress write skipped | path={} | {}", path, exc)
    return payload


async def _emit_task_status_update() -> None:
    from nanobot.agent.loop import emit_task_status_event

    await emit_task_status_event(load_task_status_payload())


async def _set_project_progress_and_emit(
    module_name: str,
    completed_names: set[str],
    module_cfg: dict[str, Any] | None = None,
) -> None:
    payload = _set_project_progress(module_name, completed_names, module_cfg)
    from nanobot.agent.loop import emit_task_status_event

    await emit_task_status_event(normalize_task_progress_payload(payload))


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


def _embedded_web_golden_metrics_nodes(
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
    """
    与 ``_boilerplate_metrics_nodes`` 参数一致，但只更新 ``EmbeddedWeb`` 的 ``state``（建模仿真内网 access 页等指标联动）。

    同时写入 ``embedded-modeling-access`` 与旧 id ``embedded-bilibili-golden``：后者无节点时 merge 会被 doc 层跳过，便于旧版 dashboard 兼容。
    """
    metrics = {
        "throughput": throughput,
        "quality": quality,
        "risk": risk,
        "centerValue": center_value,
        "completed": completed,
        "pending": pending,
        "centerLabel": center_label or "仿真健康度",
        "labels": case_cfg["metric_labels"],
    }
    embed = {"state": {"metrics": dict(metrics)}}
    return [
        ("embedded-modeling-access", "EmbeddedWeb", dict(embed)),
        ("embedded-bilibili-golden", "EmbeddedWeb", dict(embed)),
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


def _simulation_stepper_steps(stage: int, upload_name: str = "") -> list[dict[str, Any]]:
    """建模仿真模块五阶段 Stepper：0-4 为当前阶段，5 表示全部完成。"""
    un = (upload_name or "").strip() or "BOQ资料包"
    specs = [
        ("s1", "BOQ提取", "请上传 BOQ 与建模资料包", f"已提取：{un}"),
        ("s2", "设备确认", "请确认识别出的设备清单", "设备清单已确认"),
        ("s3", "创建设备", "正在根据设备清单创建设备模型", "设备模型已创建"),
        ("s4", "拓扑确认", "请确认生成的拓扑结构", "拓扑结构已确认"),
        ("s5", "拓扑连接", "正在执行拓扑连接与结果固化", "拓扑连接已完成"),
    ]
    wait_msgs = [
        "等待进入模块",
        "等待 BOQ 提取完成",
        "等待设备清单确认",
        "等待设备模型生成",
        "等待拓扑结构确认",
    ]
    out: list[dict[str, Any]] = []
    for i, (sid, title, run_det, done_det) in enumerate(specs):
        if stage < i:
            out.append({"id": sid, "title": title, "status": "waiting", "detail": [{"title": wait_msgs[i], "status": "waiting"}]})
        elif stage == i:
            out.append({"id": sid, "title": title, "status": "running", "detail": [{"title": run_det, "status": "running"}]})
        else:
            out.append({"id": sid, "title": title, "status": "done", "detail": [{"title": done_det, "status": "done"}]})
    return out


def _write_modeling_simulation_report(
    *,
    module_id: str,
    case_cfg: dict[str, Any],
    upload_name: str,
    throughput: int,
    quality: int,
    risk: int,
) -> str:
    out_dir = get_skills_root() / module_id / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / case_cfg["report_file_name"]
    content = (
        f"# {case_cfg['module_title']} · 结果说明\n\n"
        f"## 本次输入\n"
        f"- 资料包：{upload_name}\n"
        f"- 流程：BOQ提取 → 设备确认 → 创建设备 → 拓扑确认 → 拓扑连接\n\n"
        f"## 阶段结论\n"
        f"1. 已完成 BOQ 资料接收与设备清单提取。\n"
        f"2. 已确认设备清单并创建设备模型。\n"
        f"3. 已完成拓扑预览确认与拓扑连接固化。\n\n"
        f"## 指标摘要\n"
        f"- {case_cfg['metric_labels']['throughput']}：{throughput}\n"
        f"- {case_cfg['metric_labels']['quality']}：{quality}\n"
        f"- {case_cfg['metric_labels']['risk']}：{risk}\n\n"
        f"## 集成建议\n"
        f"- 保持 `stepper-main`、`summary-text`、`uploaded-files`、`artifacts` 与嵌入页节点 id 不变。\n"
        f"- 后续可在 `create_device` / `topo_confirm` 中接入真实建模与拓扑 API。\n"
        f"- 项目总览继续由 `taskProgress.actionMapping` 驱动，模块细节由 dashboard patch 驱动。\n"
    )
    out_file.write_text(content, encoding="utf-8")
    return f"workspace/skills/{module_id}/output/{out_file.name}"


def _job_stepper_steps(stage: int, upload_name: str = "") -> list[dict[str, Any]]:
    """stage 0–3：当前阶段 running；4：四步均已确认；与作业管理大盘四阶段一致。"""
    un = (upload_name or "").strip() or "资料包"
    specs = [
        ("s1", "文件上传", "请上传作业资料", f"已上传：{un}"),
        ("s2", "规划设计排期", "确认规划设计窗口与里程碑", "规划设计排期已确认"),
        ("s3", "工程安装排期", "确认工程安装窗口与依赖", "工程安装排期已确认"),
        ("s4", "集群联调排期", "确认联调窗口与准入条件", "集群联调排期已确认"),
    ]
    wait_msgs = [
        "等待进入模块",
        "等待资料就绪",
        "等待规划设计确认",
        "等待工程安装确认",
    ]
    out: list[dict[str, Any]] = []
    for i, (sid, title, run_det, done_det) in enumerate(specs):
        if stage < i:
            out.append({"id": sid, "title": title, "status": "waiting", "detail": [{"title": wait_msgs[i], "status": "waiting"}]})
        elif stage == i:
            out.append({"id": sid, "title": title, "status": "running", "detail": [{"title": run_det, "status": "running"}]})
        else:
            out.append({"id": sid, "title": title, "status": "done", "detail": [{"title": done_det, "status": "done"}]})
    return out


def _write_job_management_report(
    *,
    module_id: str,
    case_cfg: dict[str, Any],
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
        f"# {case_cfg['module_title']} · 闭环说明\n\n"
        f"## 模块目标\n"
        f"{case_cfg['module_goal']}\n\n"
        f"## 本次执行摘要\n"
        f"- 上传材料：{upload_name}\n"
        f"- 阶段：文件上传 → 规划设计排期 → 工程安装排期 → 集群联调排期（均已完成）\n"
        f"- 实际执行引擎：plan_progress（Stage1 + Stage2 + Stage3）\n\n"
        f"## 黄金指标\n"
        f"- {case_cfg['metric_labels']['throughput']}：{throughput}\n"
        f"- {case_cfg['metric_labels']['quality']}：{quality}\n"
        f"- {case_cfg['metric_labels']['risk']}：{risk}\n"
        f"- 综合健康度：{health}%\n\n"
        f"## 给集成同事的提示\n"
        f"1. 当前大盘只保留四步展示，后台实际映射到 plan_progress 的三段执行链路。\n"
        f"2. 保持 `stepper-main` 与 `chart-donut` / `chart-bar` 节点 id，便于 Patch 对齐。\n"
        f"3. 项目层进度由 `taskProgress.actionMapping` 驱动，勿删 action 名除非同步前后端。\n"
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


_PLAN_PROGRESS_REQUIRED_INPUTS: tuple[str, str] = ("到货表.xlsx", "人员信息表.xlsx")


def _workspace_root() -> Path:
    return get_skills_root().parent


def _workspace_relative_path(path: Path) -> str:
    try:
        relative = path.resolve().relative_to(_workspace_root().resolve())
        return f"workspace/{relative.as_posix()}"
    except Exception:
        return str(path)


def _workspace_path_to_local(path_or_logical: str | Path) -> Path:
    raw = str(path_or_logical or "").strip()
    if not raw:
        return Path("")
    if raw.startswith("workspace/"):
        return (_workspace_root() / raw.removeprefix("workspace/")).resolve()
    return Path(raw).expanduser().resolve()


def _plan_progress_root() -> Path:
    return get_skills_root() / "plan_progress"


def _plan_progress_input_dir() -> Path:
    return _plan_progress_root() / "input"


def _plan_progress_runtime_dir() -> Path:
    path = _plan_progress_root() / "ProjectData" / "RunTime"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _plan_progress_env_file() -> Path | None:
    env_file = _plan_progress_root() / ".env"
    return env_file if env_file.is_file() else None


def _plan_progress_bundle_path() -> Path:
    return _plan_progress_runtime_dir() / "job_management_bundle.json"


def _plan_progress_required_uploads() -> tuple[list[dict[str, Any]], list[str]]:
    input_dir = _plan_progress_input_dir()
    uploads: list[dict[str, Any]] = []
    missing: list[str] = []
    for name in _PLAN_PROGRESS_REQUIRED_INPUTS:
        file_path = input_dir / name
        if file_path.is_file():
            uploads.append(
                {
                    "fileId": _workspace_relative_path(file_path),
                    "name": name,
                    "logicalPath": _workspace_relative_path(file_path),
                    "savedDir": "skills/plan_progress/input",
                }
            )
        else:
            missing.append(name)
    return uploads, missing


def _plan_progress_prompt_xlsx() -> Path:
    return _plan_progress_input_dir() / "人员信息表.xlsx"


def _plan_progress_arrival_xlsx() -> Path:
    return _plan_progress_input_dir() / "到货表.xlsx"


def _parse_json_output(raw: str) -> dict[str, Any]:
    text = (raw or "").strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {"value": parsed}
    except Exception:
        pass
    lines = [line for line in text.splitlines() if line.strip()]
    for index, line in enumerate(lines):
        if not line.lstrip().startswith("{"):
            continue
        candidate = "\n".join(lines[index:])
        try:
            parsed = json.loads(candidate)
            return parsed if isinstance(parsed, dict) else {"value": parsed}
        except Exception:
            continue
    for line in reversed(lines):
        try:
            parsed = json.loads(line)
            return parsed if isinstance(parsed, dict) else {"value": parsed}
        except Exception:
            continue
    return {"raw_stdout": text}


async def _run_plan_progress_command(
    command: list[str],
    *,
    cwd: Path,
    extra_env: dict[str, str] | None = None,
) -> dict[str, Any]:
    env = os.environ.copy()
    env["NANOBOT_WORKSPACE"] = str(_workspace_root())
    env["PLAN_FLOW_SKILL_ROOT"] = "plan_progress"
    if extra_env:
        env.update({str(k): str(v) for k, v in extra_env.items() if v is not None})
    proc = await asyncio.create_subprocess_exec(
        *command,
        cwd=str(cwd),
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout_bytes, stderr_bytes = await proc.communicate()
    stdout = stdout_bytes.decode("utf-8", errors="replace").strip()
    stderr = stderr_bytes.decode("utf-8", errors="replace").strip()
    parsed = _parse_json_output(stdout)
    result = {
        "ok": proc.returncode == 0,
        "returncode": int(proc.returncode or 0),
        "stdout": stdout,
        "stderr": stderr,
        "json": parsed,
    }
    if proc.returncode != 0:
        result["error"] = str(parsed.get("error") or stderr or stdout or f"command failed: {command[0]}")
    return result


async def _run_plan_progress_planning_phase() -> dict[str, Any]:
    uploads, missing = _plan_progress_required_uploads()
    if missing:
        return {"ok": False, "error": f"missing required files: {', '.join(missing)}"}
    root = _plan_progress_root()
    bundle_path = _plan_progress_bundle_path()
    prompt_xlsx = _plan_progress_prompt_xlsx()
    arrival_xlsx = _plan_progress_arrival_xlsx()
    env_file = _plan_progress_env_file()
    common_env = {
        "PROMPT_XLSX_PATH": str(prompt_xlsx),
        "ARRIVAL_XLSX_PATH": str(arrival_xlsx),
        "BUNDLE_PATH": str(bundle_path),
    }

    stage1_cmd = [
        sys.executable,
        str(root / "stage1_extracted" / "run_stage1_extracted.py"),
        "--bundle-out",
        str(bundle_path),
        "--prompt-xlsx",
        str(prompt_xlsx),
        "--arrival",
        str(arrival_xlsx),
        "--flow-task-name",
        "job-management-stage1",
    ]
    if env_file is not None:
        stage1_cmd.extend(["--env-file", str(env_file)])
    stage1 = await _run_plan_progress_command(stage1_cmd, cwd=root, extra_env=common_env)
    if not stage1["ok"]:
        return {"ok": False, "error": f"Stage1 failed: {stage1['error']}", "stage1": stage1}

    stage2_cmd = [
        sys.executable,
        str(root / "stage2_decoupled" / "scripts" / "run_stage2_decoupled.py"),
        "--bundle-in",
        str(bundle_path),
        "--bundle-out",
        str(bundle_path),
        "--user-text",
        "请生成规划设计排期。",
        "--flow-task-name",
        "job-management-stage2",
    ]
    if env_file is not None:
        stage2_cmd.extend(["--env-file", str(env_file)])
    stage2 = await _run_plan_progress_command(stage2_cmd, cwd=root, extra_env=common_env)
    if not stage2["ok"]:
        return {"ok": False, "error": f"Stage2 failed: {stage2['error']}", "stage1": stage1, "stage2": stage2}

    return {
        "ok": True,
        "bundle_path": _workspace_relative_path(bundle_path),
        "summary": "Stage1 与 Stage2 已完成，已生成规划设计排期输入。",
        "uploads": uploads,
        "stage1": stage1,
        "stage2": stage2,
    }


async def _run_plan_progress_engineering_phase(bundle_path: str) -> dict[str, Any]:
    bundle = _workspace_path_to_local(bundle_path)
    if not bundle.is_file():
        return {"ok": False, "error": f"bundle not found: {bundle_path}"}
    root = _plan_progress_root()
    prompt_xlsx = _plan_progress_prompt_xlsx()
    milestone = await _run_plan_progress_command(
        [
            sys.executable,
            str(root / "stage3_extracted" / "milestone" / "run_milestone.py"),
            "--bundle",
            str(bundle),
            "--prompt-xlsx",
            str(prompt_xlsx),
        ],
        cwd=root,
    )
    if not milestone["ok"]:
        return {"ok": False, "error": f"milestone failed: {milestone['error']}", "milestone": milestone}
    schedule = await _run_plan_progress_command(
        [
            sys.executable,
            str(root / "stage3_extracted" / "schedule" / "run_schedule.py"),
            "--bundle",
            str(bundle),
            "--prompt-xlsx",
            str(prompt_xlsx),
        ],
        cwd=root,
    )
    if not schedule["ok"]:
        return {
            "ok": False,
            "error": f"schedule failed: {schedule['error']}",
            "milestone": milestone,
            "schedule": schedule,
        }
    return {
        "ok": True,
        "bundle_path": _workspace_relative_path(bundle),
        "summary": "里程碑与排期已完成，工程安装排期结果已就绪。",
        "milestone": milestone,
        "schedule": schedule,
    }


async def _run_plan_progress_cluster_phase(bundle_path: str) -> dict[str, Any]:
    bundle = _workspace_path_to_local(bundle_path)
    if not bundle.is_file():
        return {"ok": False, "error": f"bundle not found: {bundle_path}"}
    root = _plan_progress_root()
    prompt_xlsx = _plan_progress_prompt_xlsx()
    reflection = await _run_plan_progress_command(
        [
            sys.executable,
            str(root / "stage3_extracted" / "reflection" / "run_reflection.py"),
            "--bundle",
            str(bundle),
            "--prompt-xlsx",
            str(prompt_xlsx),
        ],
        cwd=root,
    )
    if not reflection["ok"]:
        return {"ok": False, "error": f"reflection failed: {reflection['error']}", "reflection": reflection}
    return {
        "ok": True,
        "bundle_path": _workspace_relative_path(bundle),
        "summary": "反思与收尾已完成，集群联调排期结果已闭环。",
        "reflection": reflection,
    }


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
    case_cfg = _boilerplate_case_config(cfg, module_id)

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
    metrics_nodes_fn = (
        _embedded_web_golden_metrics_nodes
        if str(cfg.get("metricsPresentation") or "").strip() == "embedded_web"
        else _boilerplate_metrics_nodes
    )
    _brand = str(case_cfg.get("module_title") or "智能分析工作台").strip() or "智能分析工作台"
    _center_lbl = "仿真健康度" if metrics_nodes_fn is _embedded_web_golden_metrics_nodes else "分析健康度"
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
                *metrics_nodes_fn(
                    case_cfg,
                    8,
                    5,
                    0,
                    center_label=_center_lbl,
                    center_value="8%",
                    completed=0,
                    pending=5,
                ),
                (
                    BoilerplateDashboardIds.SUMMARY_TEXT,
                    "Text",
                    {
                        "content": f"你已进入{_brand}。下一步请先选择本次分析目标，再上传资料并进入并行分析阶段。",
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
            context=f"{_brand}已就绪。先选择分析目标，再上传资料，随后系统会进入并行分析与结论汇总。",
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
                *metrics_nodes_fn(
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
                *metrics_nodes_fn(case_cfg, 41, 29, 4, center_value="36%", completed=2, pending=3),
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
                    *metrics_nodes_fn(case_cfg, 48, 32, 6, center_value="40%", completed=2, pending=3),
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
                    *metrics_nodes_fn(case_cfg, 63, 49, 10, center_value="55%", completed=3, pending=2),
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
                    *metrics_nodes_fn(case_cfg, 72, 58, 16, center_value="68%", completed=3, pending=2),
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
                    *metrics_nodes_fn(case_cfg, 79, 66, 14, center_value="74%", completed=4, pending=1),
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
                    *metrics_nodes_fn(case_cfg, 82, 74, 12, center_value="82%", completed=4, pending=1),
                ],
                [
                    (
                        BoilerplateDashboardIds.UPLOADED_FILES,
                        "ArtifactGrid",
                        {"title": "已上传文件", "mode": "input", "artifacts": _uploads_as_artifacts(uploads)},
                    ),
                    (BoilerplateDashboardIds.SUMMARY_TEXT, "Text", {"content": f"已形成初步结论：目标={goal_label}，资料={upload_name}，建议进入最终产物生成。", "variant": "body", "color": "subtle"}),
                    *metrics_nodes_fn(case_cfg, 86, 81, 9, center_value="88%", completed=4, pending=1),
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
                *metrics_nodes_fn(case_cfg, throughput, quality, risk, center_value="100%", completed=5, pending=0),
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
                            f"{_brand}已完成本轮演示：目标={goal_label}，资料={upload_name}。"
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


def _smart_survey_skill_root() -> Path:
    return get_skills_root() / "gongkan_skill"


_SMART_SURVEY_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}
_SMART_SURVEY_PROGRESS_NAME_MAP = {
    "zhgk-scene-filter": "场景筛选与底表过滤",
    "zhgk-survey-build": "勘测数据汇总",
    "zhgk-report-gen": "报告生成",
    "zhgk-report-distribute": "审批分发",
}


def _smart_survey_project_dir(skill_root: Path) -> Path:
    path = skill_root / "ProjectData"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _smart_survey_start_dir(skill_root: Path) -> Path:
    path = _smart_survey_project_dir(skill_root) / "Start"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _smart_survey_input_dir(skill_root: Path) -> Path:
    path = _smart_survey_project_dir(skill_root) / "Input"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _smart_survey_images_dir(skill_root: Path) -> Path:
    path = _smart_survey_project_dir(skill_root) / "Images"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _smart_survey_runtime_dir(skill_root: Path) -> Path:
    path = _smart_survey_project_dir(skill_root) / "RunTime"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _smart_survey_output_dir(skill_root: Path) -> Path:
    path = _smart_survey_project_dir(skill_root) / "Output"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _smart_survey_stepper_steps(active_index: int) -> list[dict[str, Any]]:
    titles = [
        "场景筛选与底表过滤",
        "勘测数据汇总",
        "报告生成",
        "审批分发",
    ]
    steps: list[dict[str, Any]] = []
    for idx, title in enumerate(titles):
        if idx < active_index:
            status = "completed"
        elif idx == active_index:
            status = "running"
        else:
            status = "waiting"
        steps.append(
            {
                "id": f"s{idx + 1}",
                "title": title,
                "status": status,
                "detail": [],
            }
        )
    return steps


def _smart_survey_missing_step1_inputs(skill_root: Path) -> list[str]:
    start_dir = _smart_survey_start_dir(skill_root)
    input_dir = _smart_survey_input_dir(skill_root)
    missing: list[str] = []
    for name in ["勘测问题底表.xlsx", "评估项底表.xlsx", "工勘常见高风险库.xlsx"]:
        if not (start_dir / name).exists():
            missing.append(name)
    if not list(input_dir.glob("*BOQ*.xlsx")):
        missing.append("BOQ*.xlsx")
    if not (input_dir / "勘测信息预置集.docx").exists():
        missing.append("勘测信息预置集.docx")
    return missing


def _smart_survey_move_uploaded_images(skill_root: Path) -> None:
    input_dir = _smart_survey_input_dir(skill_root)
    image_dir = _smart_survey_images_dir(skill_root)
    for path in input_dir.iterdir():
        if not path.is_file() or path.suffix.lower() not in _SMART_SURVEY_IMAGE_SUFFIXES:
            continue
        target = image_dir / path.name
        if target.exists():
            continue
        try:
            shutil.copy2(path, target)
        except OSError:
            continue


def _smart_survey_missing_step2_inputs(skill_root: Path) -> list[str]:
    _smart_survey_move_uploaded_images(skill_root)
    input_dir = _smart_survey_input_dir(skill_root)
    image_dir = _smart_survey_images_dir(skill_root)
    runtime_dir = _smart_survey_runtime_dir(skill_root)
    missing: list[str] = []
    if not (runtime_dir / "勘测问题底表_过滤.xlsx").exists():
        missing.append("勘测问题底表_过滤.xlsx")
    if not (input_dir / "勘测结果.xlsx").exists():
        missing.append("勘测结果.xlsx")
    if not any(path.is_file() for path in image_dir.iterdir()):
        missing.append("现场照片")
    return missing


def _read_json_file(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _artifact_kind_for_path(path: Path) -> str:
    suffix = path.suffix.lstrip(".").lower()
    return suffix if suffix in {"docx", "xlsx", "pdf", "html", "json", "md", "png", "jpg", "jpeg"} else "other"


def _artifact_for_path(path: Path, *, prefix: str, index: int) -> dict[str, Any]:
    return {
        "id": f"{prefix}-{index}",
        "label": path.name,
        "path": _workspace_relative_path(path),
        "kind": _artifact_kind_for_path(path),
        "status": "ready",
    }


def _artifacts_for_existing_paths(paths: list[Path], *, prefix: str) -> list[dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []
    for index, path in enumerate(paths, start=1):
        if not path.exists():
            continue
        artifacts.append(_artifact_for_path(path, prefix=prefix, index=index))
    return artifacts


def _smart_survey_input_artifacts(skill_root: Path) -> list[dict[str, Any]]:
    input_dir = _smart_survey_input_dir(skill_root)
    image_dir = _smart_survey_images_dir(skill_root)
    files = sorted([path for path in input_dir.iterdir() if path.is_file()], key=lambda item: item.name)
    files.extend(sorted([path for path in image_dir.iterdir() if path.is_file()], key=lambda item: item.name))
    return _artifacts_for_existing_paths(files, prefix="smart-survey-input")


def _smart_survey_skill_result(skill_root: Path) -> dict[str, Any]:
    return _read_json_file(_smart_survey_output_dir(skill_root) / "skill_result.json")


def _smart_survey_progress_payload(skill_root: Path) -> dict[str, Any]:
    return _read_json_file(_smart_survey_runtime_dir(skill_root) / "progress.json")


def _smart_survey_completed_task_names(skill_root: Path) -> set[str]:
    payload = _smart_survey_progress_payload(skill_root)
    modules = payload.get("modules")
    if not isinstance(modules, list):
        return set()
    for item in modules:
        if not isinstance(item, dict):
            continue
        if str(item.get("moduleId") or "").strip() != "smart_survey":
            continue
        tasks = item.get("tasks")
        if not isinstance(tasks, list):
            return set()
        completed: set[str] = set()
        for task in tasks:
            if not isinstance(task, dict) or not bool(task.get("completed")):
                continue
            display_name = str(task.get("displayName") or "").strip()
            if display_name:
                completed.add(display_name)
                continue
            name = str(task.get("name") or "").strip()
            mapped = _SMART_SURVEY_PROGRESS_NAME_MAP.get(name)
            if mapped:
                completed.add(mapped)
        return completed
    return set()


async def _sync_smart_survey_task_progress(
    skill_root: Path,
    cfg: dict[str, Any],
    fallback: set[str],
) -> None:
    definition = _task_progress_definition("智慧工勘模块", cfg)
    completed = _smart_survey_completed_task_names(skill_root) or set(fallback)
    await _set_project_progress_and_emit(definition["module_name"], completed, cfg)


async def _run_gongkan_command(
    command: list[str],
    *,
    cwd: Path,
) -> dict[str, Any]:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    env["NANOBOT_WORKSPACE"] = str(_workspace_root())
    proc = await asyncio.create_subprocess_exec(
        *command,
        cwd=str(cwd),
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout_bytes, stderr_bytes = await proc.communicate()
    stdout = stdout_bytes.decode("utf-8", errors="replace").strip()
    stderr = stderr_bytes.decode("utf-8", errors="replace").strip()
    parsed = _parse_json_output(stdout)
    result = {
        "ok": proc.returncode == 0,
        "returncode": int(proc.returncode or 0),
        "stdout": stdout,
        "stderr": stderr,
        "json": parsed,
    }
    if proc.returncode != 0:
        result["error"] = str(parsed.get("error") or stderr or stdout or f"command failed: {command[0]}")
    return result


async def _run_gongkan_progress_update(skill_root: Path, task_name: str) -> dict[str, Any]:
    progress_path = _smart_survey_runtime_dir(skill_root) / "progress.json"
    if not progress_path.is_file():
        return {"ok": False, "error": f"progress file missing: {progress_path}"}
    return await _run_gongkan_command(
        [
            sys.executable,
            str(skill_root / "tools" / "update_progress.py"),
            "smart_survey",
            task_name,
        ],
        cwd=skill_root,
    )


def _smart_survey_step1_summary(skill_root: Path) -> str:
    result = _smart_survey_skill_result(skill_root)
    scene_filter = result.get("scene_filter") if isinstance(result.get("scene_filter"), dict) else {}
    cooling = str(scene_filter.get("cooling_tag") or "").strip()
    scenario = str(scene_filter.get("scenario") or "").strip()
    if cooling or scenario:
        return f"已完成场景筛选与底表过滤：制冷={cooling or '待确认'}，场景={scenario or '待确认'}。"
    return "已完成场景筛选与底表过滤。"


async def _run_gongkan_step1(skill_root: Path) -> dict[str, Any]:
    runtime_dir = _smart_survey_runtime_dir(skill_root)
    command = await _run_gongkan_command(
        [
            sys.executable,
            str(skill_root / "zhgk" / "scene-filter" / "scripts" / "scene_filter.py"),
        ],
        cwd=skill_root,
    )
    if not command.get("ok"):
        return {"ok": False, "error": str(command.get("error") or "scene filter failed"), "command": command}
    progress = await _run_gongkan_progress_update(skill_root, "zhgk-scene-filter")
    return {
        "ok": True,
        "summary": _smart_survey_step1_summary(skill_root),
        "uploaded_artifacts": _smart_survey_input_artifacts(skill_root),
        "artifacts": _artifacts_for_existing_paths(
            [
                runtime_dir / "定制工勘表.xlsx",
                runtime_dir / "勘测问题底表_过滤.xlsx",
                runtime_dir / "评估项底表_过滤.xlsx",
                runtime_dir / "工勘常见高风险库_过滤.xlsx",
            ],
            prefix="smart-survey-step1",
        ),
        "progress": progress,
    }


def _smart_survey_step2_result(skill_root: Path) -> dict[str, Any]:
    result = _smart_survey_skill_result(skill_root)
    survey = result.get("survey") if isinstance(result.get("survey"), dict) else {}
    empty_by_type = survey.get("empty_by_type") if isinstance(survey.get("empty_by_type"), dict) else {}
    total = int(survey.get("total_items") or 0)
    filled = int(survey.get("filled_items") or 0)
    completion = int(round(float(survey.get("completion_rate") or 0)))
    remaining = sum(int(value or 0) for value in empty_by_type.values())
    summary = f"已生成全量勘测结果表，已填写 {filled}/{total} 项，完整率 {completion}% 。"
    if remaining:
        summary += f" 当前仍有 {remaining} 个遗留项待补充。"
    return {
        "summary": summary,
        "uploaded_artifacts": _smart_survey_input_artifacts(skill_root),
        "artifacts": _artifacts_for_existing_paths(
            [
                _smart_survey_output_dir(skill_root) / "全量勘测结果表.xlsx",
                _smart_survey_output_dir(skill_root) / "待客户确认勘测项.xlsx",
                _smart_survey_output_dir(skill_root) / "待拍摄图片项.xlsx",
                _smart_survey_output_dir(skill_root) / "待补充勘测项.xlsx",
            ],
            prefix="smart-survey-step2",
        ),
        "metrics": {
            "completion": completion,
            "integrity": completion,
            "remaining": remaining,
        },
    }


async def _run_gongkan_step2(skill_root: Path) -> dict[str, Any]:
    _smart_survey_move_uploaded_images(skill_root)
    command = await _run_gongkan_command(
        [
            sys.executable,
            str(skill_root / "zhgk" / "survey-build" / "scripts" / "generate_survey_table.py"),
        ],
        cwd=skill_root,
    )
    if not command.get("ok"):
        return {"ok": False, "error": str(command.get("error") or "survey build failed"), "command": command}
    progress = await _run_gongkan_progress_update(skill_root, "zhgk-survey-build")
    result = _smart_survey_step2_result(skill_root)
    result.update({"ok": True, "progress": progress, "command": command})
    return result


def _smart_survey_step3_result(skill_root: Path) -> dict[str, Any]:
    result = _smart_survey_skill_result(skill_root)
    assessment = result.get("assessment") if isinstance(result.get("assessment"), dict) else {}
    remaining = result.get("remaining_issues") if isinstance(result.get("remaining_issues"), dict) else {}
    report = result.get("report") if isinstance(result.get("report"), dict) else {}
    risks = result.get("risks") if isinstance(result.get("risks"), dict) else {}
    satisfaction = int(round(float(assessment.get("satisfaction_rate") or 0)))
    remaining_total = int(remaining.get("total") or 0)
    risk_count = len(risks.get("triggered_risks", [])) if isinstance(risks.get("triggered_risks"), list) else 0
    summary = f"报告生成已完成：机房满足度 {satisfaction}% ，风险项 {risk_count} 个。"
    if bool(report.get("generated")):
        summary += " 工勘报告与整改待办已就绪。"
    return {
        "summary": summary,
        "uploaded_artifacts": _smart_survey_input_artifacts(skill_root),
        "artifacts": _artifacts_for_existing_paths(
            [
                _smart_survey_output_dir(skill_root) / "工勘报告.docx",
                _smart_survey_output_dir(skill_root) / "机房满足度评估表.xlsx",
                _smart_survey_output_dir(skill_root) / "风险识别结果表.xlsx",
                _smart_survey_output_dir(skill_root) / "整改待办.xlsx",
                _smart_survey_output_dir(skill_root) / "全量勘测结果表.xlsx",
            ],
            prefix="smart-survey-step3",
        ),
        "metrics": {
            "completion": 100,
            "integrity": max(satisfaction, 0),
            "remaining": remaining_total,
        },
    }


async def _run_gongkan_step3(skill_root: Path) -> dict[str, Any]:
    commands = [
        [sys.executable, str(skill_root / "zhgk" / "report-gen" / "scripts" / "generate_assessment.py")],
        [sys.executable, str(skill_root / "zhgk" / "report-gen" / "scripts" / "generate_risk.py")],
        [sys.executable, str(skill_root / "zhgk" / "report-gen" / "scripts" / "generate_report.py")],
    ]
    executed: list[dict[str, Any]] = []
    for command in commands:
        run = await _run_gongkan_command(command, cwd=skill_root)
        executed.append(run)
        if not run.get("ok"):
            return {"ok": False, "error": str(run.get("error") or "report generation failed"), "commands": executed}
    progress = await _run_gongkan_progress_update(skill_root, "zhgk-report-gen")
    result = _smart_survey_step3_result(skill_root)
    result.update({"ok": True, "progress": progress, "commands": executed})
    return result


async def _run_gongkan_step4_approve(skill_root: Path) -> dict[str, Any]:
    command = await _run_gongkan_command(
        [
            sys.executable,
            str(skill_root / "zhgk" / "report-distribute" / "scripts" / "distribute_report.py"),
        ],
        cwd=skill_root,
    )
    if not command.get("ok"):
        return {"ok": False, "error": str(command.get("error") or "report approve failed"), "command": command}
    result = _smart_survey_skill_result(skill_root)
    project_info = result.get("project_info") if isinstance(result.get("project_info"), dict) else {}
    project_name = str(project_info.get("项目名称") or "").strip()
    return {
        "ok": True,
        "summary": f"{project_name + ' ' if project_name else ''}已发送专家审批，等待回执。",
        "uploaded_artifacts": _smart_survey_input_artifacts(skill_root),
        "artifacts": _artifacts_for_existing_paths(
            [
                _smart_survey_output_dir(skill_root) / "工勘报告.docx",
                _smart_survey_output_dir(skill_root) / "机房满足度评估表.xlsx",
                _smart_survey_output_dir(skill_root) / "风险识别结果表.xlsx",
                _smart_survey_output_dir(skill_root) / "全量勘测结果表.xlsx",
            ],
            prefix="smart-survey-step4a",
        ),
        "command": command,
    }


async def _run_gongkan_step4_finish(skill_root: Path) -> dict[str, Any]:
    command = await _run_gongkan_command(
        [
            sys.executable,
            str(skill_root / "zhgk" / "report-distribute" / "scripts" / "distribute_report_4b.py"),
        ],
        cwd=skill_root,
    )
    if not command.get("ok"):
        return {"ok": False, "error": str(command.get("error") or "report distribute failed"), "command": command}
    progress = await _run_gongkan_progress_update(skill_root, "zhgk-report-distribute")
    result = _smart_survey_skill_result(skill_root)
    project_info = result.get("project_info") if isinstance(result.get("project_info"), dict) else {}
    remaining = result.get("remaining_issues") if isinstance(result.get("remaining_issues"), dict) else {}
    project_name = str(project_info.get("项目名称") or "").strip()
    return {
        "ok": True,
        "summary": f"{project_name + ' ' if project_name else ''}工勘流程已完成闭环，报告已分发给干系人。",
        "uploaded_artifacts": _smart_survey_input_artifacts(skill_root),
        "artifacts": _artifacts_for_existing_paths(
            [
                _smart_survey_output_dir(skill_root) / "工勘报告.docx",
                _smart_survey_output_dir(skill_root) / "机房满足度评估表.xlsx",
                _smart_survey_output_dir(skill_root) / "风险识别结果表.xlsx",
                _smart_survey_output_dir(skill_root) / "整改待办.xlsx",
                _smart_survey_output_dir(skill_root) / "全量勘测结果表.xlsx",
            ],
            prefix="smart-survey-step4b",
        ),
        "metrics": {
            "completion": 100,
            "integrity": 100,
            "remaining": int(remaining.get("total") or 0),
        },
        "progress": progress,
        "command": command,
    }


def _smart_survey_dashboard_nodes(
    cfg: dict[str, Any],
    result: dict[str, Any],
    *,
    completed: int,
    pending: int,
    center_value: str,
    center_label: str,
) -> list[tuple[str, str, dict[str, Any]]]:
    case_cfg = _boilerplate_case_config(cfg, "smart_survey_workbench")
    metrics = result.get("metrics") if isinstance(result.get("metrics"), dict) else {}
    throughput = int(metrics.get("completion") or 0)
    quality = int(metrics.get("integrity") or 0)
    risk = int(metrics.get("remaining") or 0)
    return [
        *_boilerplate_metrics_nodes(
            case_cfg,
            throughput,
            quality,
            risk,
            center_value=center_value,
            center_label=center_label,
            completed=completed,
            pending=pending,
        ),
        (
            BoilerplateDashboardIds.SUMMARY_TEXT,
            "Text",
            {
                "content": str(result.get("summary") or ""),
                "variant": "body",
                "color": "subtle",
            },
        ),
        (
            BoilerplateDashboardIds.UPLOADED_FILES,
            "ArtifactGrid",
            {
                "title": "已上传文件",
                "mode": "input",
                "artifacts": list(result.get("uploaded_artifacts") or []),
            },
        ),
        (
            BoilerplateDashboardIds.ARTIFACTS,
            "ArtifactGrid",
            {
                "title": "作业结果",
                "mode": "output",
                "artifacts": list(result.get("artifacts") or []),
            },
        ),
        ("alerts", "Stack", {"children": list(result.get("alerts") or [])}),
    ]


async def _flow_smart_survey_workflow(
    *,
    module_id: str,
    action: str,
    state: dict[str, Any],
    thread_id: str,
    docman: Any,
    cfg: dict[str, Any],
) -> dict[str, Any]:
    pusher = _pusher_for(cfg)
    mc = MissionControlManager(thread_id=thread_id, docman=docman)
    skill_root = _smart_survey_skill_root()
    upload_cfg = _upload_config(cfg, "smart_survey_inputs")

    if action == "cancel":
        clear_module_session(thread_id, module_id)
        return {"ok": True, "cancelled": True}

    if action == "guide":
        clear_module_session(thread_id, module_id)
        await pusher.update_nodes(
            [
                (SDUI_STEPPER_MAIN_ID, "Stepper", {"steps": _smart_survey_stepper_steps(0)}),
                *_smart_survey_dashboard_nodes(
                    cfg,
                    {
                        "summary": "智慧工勘模块已就绪，请先检查并补齐 Step 1 输入件。",
                        "uploaded_artifacts": [],
                        "artifacts": [],
                        "metrics": {"completion": 0, "integrity": 0, "remaining": 0},
                        "alerts": [],
                    },
                    completed=0,
                    pending=4,
                    center_value="0%",
                    center_label="勘测完成度",
                ),
            ]
        )
        return {"ok": True, "next": "prepare_step1"}

    if action == "prepare_step1":
        missing = _smart_survey_missing_step1_inputs(skill_root)
        if missing:
            await mc.ask_for_file(
                purpose="smart_survey_inputs",
                title="请补齐工勘 Step 1 输入件",
                accept=str(upload_cfg.get("accept") or ".xlsx,.docx"),
                multiple=bool(upload_cfg.get("multiple", True)),
                module_id=module_id,
                next_action="run_step1",
                save_relative_dir=str(upload_cfg.get("save_relative_dir") or "skills/gongkan_skill/ProjectData/Input"),
            )
        return {"ok": True, "next": "run_step1"}

    if action == "run_step1":
        result = await _run_gongkan_step1(skill_root)
        if not result.get("ok"):
            return result
        await _sync_smart_survey_task_progress(skill_root, cfg, {"场景筛选与底表过滤"})
        await pusher.update_nodes(
            [
                (SDUI_STEPPER_MAIN_ID, "Stepper", {"steps": _smart_survey_stepper_steps(1)}),
                *_smart_survey_dashboard_nodes(
                    cfg,
                    result,
                    completed=1,
                    pending=3,
                    center_value="25%",
                    center_label="勘测完成度",
                ),
            ]
        )
        await mc.emit_guidance(
            context="场景筛选已完成。请补齐勘测结果与现场照片，然后进入勘测数据汇总。",
            actions=[
                {
                    "label": "开始勘测数据汇总",
                    "verb": "module_action",
                    "payload": {"moduleId": module_id, "action": "prepare_step2", "state": dict(state)},
                }
            ],
        )
        return {"ok": True, "next": "prepare_step2"}

    if action == "prepare_step2":
        missing = _smart_survey_missing_step2_inputs(skill_root)
        if missing:
            await mc.ask_for_file(
                purpose="smart_survey_inputs",
                title="请补齐工勘 Step 2 输入件",
                accept=".xlsx,.jpg,.jpeg,.png",
                multiple=True,
                module_id=module_id,
                next_action="run_step2",
                save_relative_dir=str(upload_cfg.get("save_relative_dir") or "skills/gongkan_skill/ProjectData/Input"),
            )
        return {"ok": True, "next": "run_step2"}

    if action == "run_step2":
        result = await _run_gongkan_step2(skill_root)
        if not result.get("ok"):
            return result
        await _sync_smart_survey_task_progress(skill_root, cfg, {"场景筛选与底表过滤", "勘测数据汇总"})
        await pusher.update_nodes(
            [
                (SDUI_STEPPER_MAIN_ID, "Stepper", {"steps": _smart_survey_stepper_steps(2)}),
                *_smart_survey_dashboard_nodes(
                    cfg,
                    result,
                    completed=2,
                    pending=2,
                    center_value=f"{int((result.get('metrics') or {}).get('completion') or 0)}%",
                    center_label="勘测完成度",
                ),
            ]
        )
        await mc.emit_guidance(
            context="勘测数据汇总已完成。全量勘测结果表已生成，可以继续生成工勘报告。",
            actions=[
                {
                    "label": "生成工勘报告",
                    "verb": "module_action",
                    "payload": {"moduleId": module_id, "action": "prepare_step3", "state": dict(state)},
                }
            ],
        )
        return {"ok": True, "next": "prepare_step3"}

    if action == "prepare_step3":
        return {"ok": True, "next": "run_step3"}

    if action == "run_step3":
        result = await _run_gongkan_step3(skill_root)
        if not result.get("ok"):
            return result
        await _sync_smart_survey_task_progress(skill_root, cfg, {"场景筛选与底表过滤", "勘测数据汇总", "报告生成"})
        await pusher.update_nodes(
            [
                (SDUI_STEPPER_MAIN_ID, "Stepper", {"steps": _smart_survey_stepper_steps(3)}),
                *_smart_survey_dashboard_nodes(
                    cfg,
                    result,
                    completed=3,
                    pending=1,
                    center_value=f"{int((result.get('metrics') or {}).get('integrity') or 0)}%",
                    center_label="报告成熟度",
                ),
            ]
        )
        await mc.emit_guidance(
            context="工勘报告与评估表已生成。下一步可以发送给专家审批。",
            actions=[
                {
                    "label": "发送专家审批",
                    "verb": "module_action",
                    "payload": {"moduleId": module_id, "action": "prepare_step4", "state": dict(state)},
                }
            ],
        )
        return {"ok": True, "next": "prepare_step4"}

    if action == "prepare_step4":
        return {"ok": True, "next": "run_step4_approve"}

    if action == "run_step4_approve":
        result = await _run_gongkan_step4_approve(skill_root)
        if not result.get("ok"):
            return result
        await pusher.update_nodes(
            [
                (SDUI_STEPPER_MAIN_ID, "Stepper", {"steps": _smart_survey_stepper_steps(3)}),
                *_smart_survey_dashboard_nodes(
                    cfg,
                    result,
                    completed=3,
                    pending=1,
                    center_value="待审批",
                    center_label="专家回执",
                ),
            ]
        )
        await mc.emit_guidance(
            context="专家审批邮件已发送。收到回执后，请点击“审批通过”继续分发。",
            actions=[
                {
                    "label": "审批通过",
                    "verb": "module_action",
                    "payload": {"moduleId": module_id, "action": "approval_pass", "state": dict(state)},
                }
            ],
        )
        return {"ok": True, "next": "approval_pass"}

    if action == "approval_pass":
        result = await _run_gongkan_step4_finish(skill_root)
        if not result.get("ok"):
            return result
        await _sync_smart_survey_task_progress(
            skill_root,
            cfg,
            {"场景筛选与底表过滤", "勘测数据汇总", "报告生成", "审批分发"},
        )
        await pusher.update_nodes(
            [
                (SDUI_STEPPER_MAIN_ID, "Stepper", {"steps": _smart_survey_stepper_steps(4)}),
                *_smart_survey_dashboard_nodes(
                    cfg,
                    result,
                    completed=4,
                    pending=0,
                    center_value="100%",
                    center_label="流程闭环",
                ),
            ]
        )
        clear_module_session(thread_id, module_id)
        return {"ok": True, "done": True, "summary": str(result.get("summary") or "智慧工勘流程已完成")}

    return {"ok": False, "error": f"unknown action: {action!r}"}


async def _flow_simulation_workflow(
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
    metrics_nodes_fn = (
        _embedded_web_golden_metrics_nodes
        if str(cfg.get("metricsPresentation") or "").strip() == "embedded_web"
        else _boilerplate_metrics_nodes
    )
    progress_module_name = _task_progress_definition(case_cfg["module_title"], cfg)["module_name"]
    brand = str(case_cfg.get("module_title") or "建模仿真模块").strip() or "建模仿真模块"
    upload_cfg = _upload_config(cfg, "analysis_bundle")

    if action == "cancel":
        clear_module_session(thread_id, module_id)
        await _set_project_progress_and_emit(progress_module_name, set(), cfg)
        return {"ok": True, "cancelled": True}

    if action == "guide":
        clear_module_session(thread_id, module_id)
        await _set_project_progress_and_emit(
            progress_module_name,
            _configured_completed_tasks(cfg, "guide", {"BOQ提取"}, module_name=progress_module_name),
            cfg,
        )
        await pusher.update_nodes(
            [
                (SDUI_STEPPER_MAIN_ID, "Stepper", {"steps": _simulation_stepper_steps(0)}),
                *metrics_nodes_fn(
                    case_cfg,
                    6,
                    4,
                    1,
                    center_value="6%",
                    center_label="仿真健康度",
                    completed=0,
                    pending=5,
                ),
                (
                    BoilerplateDashboardIds.SUMMARY_TEXT,
                    "Text",
                    {
                        "content": f"{brand}已就绪。请先上传 BOQ 与建模资料包，系统会依次完成 BOQ 提取、设备确认、创建设备、拓扑确认与拓扑连接。",
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
            context=f"{brand}已进入建模仿真流程。第一步请上传 BOQ 与建模资料包，随后系统会提取设备清单并进入确认。",
            actions=[
                {
                    "label": "开始建模仿真",
                    "verb": "module_action",
                    "payload": {"moduleId": module_id, "action": "upload_bundle", "state": {}},
                }
            ],
        )
        return {"ok": True, "next": "upload_bundle"}

    if action == "upload_bundle":
        await _set_project_progress_and_emit(
            progress_module_name,
            _configured_completed_tasks(cfg, "upload_bundle", {"BOQ提取"}, module_name=progress_module_name),
            cfg,
        )
        await pusher.update_nodes(
            [
                (SDUI_STEPPER_MAIN_ID, "Stepper", {"steps": _simulation_stepper_steps(0)}),
                *metrics_nodes_fn(
                    case_cfg,
                    22,
                    18,
                    3,
                    center_value="18%",
                    center_label="仿真健康度",
                    completed=0,
                    pending=5,
                ),
                (
                    BoilerplateDashboardIds.SUMMARY_TEXT,
                    "Text",
                    {
                        "content": "请上传 BOQ、设备清单或建模资料包。上传完成后会先展示设备清单预览，再进入设备确认。",
                        "variant": "body",
                        "color": "subtle",
                    },
                ),
                (
                    BoilerplateDashboardIds.UPLOADED_FILES,
                    "ArtifactGrid",
                    {"title": "已上传文件", "mode": "input", "artifacts": _uploads_as_artifacts(_merge_uploads(sess.get('uploads'), state.get('uploads')))},
                ),
            ]
        )
        await mc.ask_for_file(
            purpose="analysis_bundle",
            title="请上传 BOQ 与建模资料包",
            accept=str(upload_cfg.get("accept") or ".zip,.xlsx,.csv,.pdf,.doc,.docx,.png,.jpg,.stp,.step,.iges,.stl,.json"),
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
        upload_name = str(upload_meta.get("name") or "BOQ资料包")
        await _set_project_progress_and_emit(
            progress_module_name,
            _configured_completed_tasks(
                cfg,
                "upload_bundle_complete",
                {"BOQ提取", "设备确认"},
                module_name=progress_module_name,
            ),
            cfg,
        )
        await pusher.update_nodes(
            [
                (SDUI_STEPPER_MAIN_ID, "Stepper", {"steps": _simulation_stepper_steps(1, upload_name)}),
                *metrics_nodes_fn(
                    case_cfg,
                    48,
                    42,
                    6,
                    center_value="36%",
                    center_label="仿真健康度",
                    completed=1,
                    pending=4,
                ),
                (
                    BoilerplateDashboardIds.UPLOADED_FILES,
                    "ArtifactGrid",
                    {"title": "已上传文件", "mode": "input", "artifacts": _uploads_as_artifacts(uploads)},
                ),
                (
                    BoilerplateDashboardIds.SUMMARY_TEXT,
                    "Text",
                    {
                        "content": f"已完成 BOQ 提取，最近上传：{upload_name}。当前已生成设备清单预览，请确认设备名称、数量与类型后进入创建设备。",
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
                title="BOQ 已提取",
                node={
                    "type": "Stack",
                    "gap": "sm",
                    "children": [
                        {
                            "type": "Text",
                            "variant": "body",
                            "content": f"已完成资料接收与 BOQ 提取，最近上传：{upload_name}。可继续补传文件，或直接确认设备清单。",
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
                            "context": "设备清单预览已准备好。请选择继续上传或进入设备确认。",
                            "actions": [
                                {
                                    "label": "继续上传",
                                    "verb": "module_action",
                                    "payload": {
                                        "moduleId": module_id,
                                        "action": "upload_bundle",
                                        "state": {"upload": upload_meta, "uploads": uploads},
                                    },
                                },
                                {
                                    "label": "确认设备清单",
                                    "verb": "module_action",
                                    "payload": {
                                        "moduleId": module_id,
                                        "action": "device_confirm",
                                        "state": {"upload": upload_meta, "uploads": uploads},
                                    },
                                },
                            ],
                        },
                    ],
                },
                doc_id=f"chat:{thread_id}",
            )
        return {"ok": True, "next": "device_confirm"}

    if action == "device_confirm":
        merged = merge_module_session(thread_id, module_id, dict(state))
        upload_meta = _latest_upload_meta(merged)
        upload_name = str(upload_meta.get("name") or "BOQ资料包")
        uploads = _merge_uploads(merged.get("uploads"), state.get("uploads"))
        await _set_project_progress_and_emit(
            progress_module_name,
            _configured_completed_tasks(
                cfg,
                "device_confirm",
                {"BOQ提取", "设备确认"},
                module_name=progress_module_name,
            ),
            cfg,
        )
        await pusher.update_nodes(
            [
                (SDUI_STEPPER_MAIN_ID, "Stepper", {"steps": _simulation_stepper_steps(1, upload_name)}),
                *metrics_nodes_fn(
                    case_cfg,
                    55,
                    48,
                    8,
                    center_value="44%",
                    center_label="仿真健康度",
                    completed=1,
                    pending=4,
                ),
                (
                    BoilerplateDashboardIds.UPLOADED_FILES,
                    "ArtifactGrid",
                    {"title": "已上传文件", "mode": "input", "artifacts": _uploads_as_artifacts(uploads)},
                ),
                (
                    BoilerplateDashboardIds.SUMMARY_TEXT,
                    "Text",
                    {
                        "content": f"请确认 {upload_name} 提取出的设备清单。确认后系统会据此创建设备模型，并继续生成拓扑结构。",
                        "variant": "body",
                        "color": "subtle",
                    },
                ),
            ]
        )
        await mc.emit_guidance(
            context="设备清单预览已生成。请确认设备识别结果，系统将开始创建设备模型。",
            actions=[
                {
                    "label": "开始创建设备",
                    "verb": "module_action",
                    "payload": {"moduleId": module_id, "action": "create_device", "state": dict(merged)},
                }
            ],
        )
        return {"ok": True, "next": "create_device"}

    if action == "create_device":
        merged = merge_module_session(thread_id, module_id, dict(state))
        upload_meta = _latest_upload_meta(merged)
        upload_name = str(upload_meta.get("name") or "BOQ资料包")
        uploads = _merge_uploads(merged.get("uploads"), state.get("uploads"))
        await _set_project_progress_and_emit(
            progress_module_name,
            _configured_completed_tasks(
                cfg,
                "create_device",
                {"BOQ提取", "设备确认", "创建设备"},
                module_name=progress_module_name,
            ),
            cfg,
        )
        await _stream_patch_frames(
            pusher,
            [
                [
                    (SDUI_STEPPER_MAIN_ID, "Stepper", {"steps": _simulation_stepper_steps(2, upload_name)}),
                    *metrics_nodes_fn(
                        case_cfg,
                        62,
                        58,
                        10,
                        center_value="56%",
                        center_label="仿真健康度",
                        completed=2,
                        pending=3,
                    ),
                    (
                        BoilerplateDashboardIds.UPLOADED_FILES,
                        "ArtifactGrid",
                        {"title": "已上传文件", "mode": "input", "artifacts": _uploads_as_artifacts(uploads)},
                    ),
                    (
                        BoilerplateDashboardIds.SUMMARY_TEXT,
                        "Text",
                        {
                            "content": f"正在根据 {upload_name} 中的设备清单创建设备模型，并生成可用于拓扑编排的实体。",
                            "variant": "body",
                            "color": "subtle",
                        },
                    ),
                ],
                [
                    (SDUI_STEPPER_MAIN_ID, "Stepper", {"steps": _simulation_stepper_steps(3, upload_name)}),
                    *metrics_nodes_fn(
                        case_cfg,
                        74,
                        68,
                        9,
                        center_value="70%",
                        center_label="仿真健康度",
                        completed=3,
                        pending=2,
                    ),
                    (
                        BoilerplateDashboardIds.UPLOADED_FILES,
                        "ArtifactGrid",
                        {"title": "已上传文件", "mode": "input", "artifacts": _uploads_as_artifacts(uploads)},
                    ),
                    (
                        BoilerplateDashboardIds.SUMMARY_TEXT,
                        "Text",
                        {
                            "content": "设备模型已创建完成，系统已生成拓扑预览。下一步请确认拓扑结构与连接关系。",
                            "variant": "body",
                            "color": "subtle",
                        },
                    ),
                ],
            ],
        )
        await mc.emit_guidance(
            context="设备模型已创建，拓扑预览已准备好。请进入拓扑确认阶段。",
            actions=[
                {
                    "label": "确认拓扑结构",
                    "verb": "module_action",
                    "payload": {"moduleId": module_id, "action": "topo_confirm", "state": dict(merged)},
                }
            ],
        )
        return {"ok": True, "next": "topo_confirm"}

    if action == "topo_confirm":
        merged = merge_module_session(thread_id, module_id, dict(state))
        upload_meta = _latest_upload_meta(merged)
        upload_name = str(upload_meta.get("name") or "BOQ资料包")
        uploads = _merge_uploads(merged.get("uploads"), state.get("uploads"))
        await _set_project_progress_and_emit(
            progress_module_name,
            _configured_completed_tasks(
                cfg,
                "topo_confirm",
                {"BOQ提取", "设备确认", "创建设备", "拓扑确认"},
                module_name=progress_module_name,
            ),
            cfg,
        )
        await pusher.update_nodes(
            [
                (SDUI_STEPPER_MAIN_ID, "Stepper", {"steps": _simulation_stepper_steps(3, upload_name)}),
                *metrics_nodes_fn(
                    case_cfg,
                    82,
                    76,
                    8,
                    center_value="84%",
                    center_label="仿真健康度",
                    completed=4,
                    pending=1,
                ),
                (
                    BoilerplateDashboardIds.UPLOADED_FILES,
                    "ArtifactGrid",
                    {"title": "已上传文件", "mode": "input", "artifacts": _uploads_as_artifacts(uploads)},
                ),
                (
                    BoilerplateDashboardIds.SUMMARY_TEXT,
                    "Text",
                    {
                        "content": "拓扑结构已生成。请确认关键设备节点、上下游关系和连接约束，确认后系统将执行拓扑连接并固化结果。",
                        "variant": "body",
                        "color": "subtle",
                    },
                ),
            ]
        )
        await mc.emit_guidance(
            context="拓扑结构待确认。确认后将执行拓扑连接并生成最终结果。",
            actions=[
                {
                    "label": "执行拓扑连接",
                    "verb": "module_action",
                    "payload": {"moduleId": module_id, "action": "finish", "state": dict(merged)},
                }
            ],
        )
        return {"ok": True, "next": "finish"}

    if action == "finish":
        upload_meta = _latest_upload_meta(sess)
        upload_name = str(upload_meta.get("name") or "BOQ资料包")
        uploads = _merge_uploads(sess.get("uploads"), state.get("uploads"))
        throughput = 92
        quality = 88
        risk = 5
        await _set_project_progress_and_emit(
            progress_module_name,
            _configured_completed_tasks(
                cfg,
                "finish",
                {"BOQ提取", "设备确认", "创建设备", "拓扑确认", "拓扑连接"},
                module_name=progress_module_name,
            ),
            cfg,
        )
        await pusher.update_nodes(
            [
                (SDUI_STEPPER_MAIN_ID, "Stepper", {"steps": _simulation_stepper_steps(5, upload_name)}),
                *metrics_nodes_fn(
                    case_cfg,
                    throughput,
                    quality,
                    risk,
                    center_value="100%",
                    center_label="仿真健康度",
                    completed=5,
                    pending=0,
                ),
                (
                    BoilerplateDashboardIds.UPLOADED_FILES,
                    "ArtifactGrid",
                    {"title": "已上传文件", "mode": "input", "artifacts": _uploads_as_artifacts(uploads)},
                ),
                (
                    BoilerplateDashboardIds.SUMMARY_TEXT,
                    "Text",
                    {
                        "content": f"{brand}已完成本轮建模仿真：资料={upload_name}。系统已完成设备创建、拓扑确认与拓扑连接，并生成最终结果说明。",
                        "variant": "body",
                        "color": "subtle",
                    },
                ),
            ]
        )
        out_path = _write_modeling_simulation_report(
            module_id=module_id,
            case_cfg=case_cfg,
            upload_name=upload_name,
            throughput=throughput,
            quality=quality,
            risk=risk,
        )
        await mc.add_artifact(
            doc_id,
            synthetic_path=sp,
            artifact_id="modeling-simulation-workbench-report-001",
            label=case_cfg["report_label"],
            path=out_path,
            kind="md",
            status="ready",
        )
        clear_module_session(thread_id, module_id)
        return {"ok": True, "done": True, "summary": "simulation_workflow 完成：建模仿真结果已生成。"}

    return {"ok": False, "error": f"unknown action: {action!r}"}


async def _flow_job_management_legacy(
    *,
    module_id: str,
    action: str,
    state: dict[str, Any],
    thread_id: str,
    docman: Any,
    cfg: dict[str, Any],
) -> dict[str, Any]:
    """作业管理大盘：上传 → 三段排期确认 → 闭环报告。"""
    pusher = _pusher_for(cfg)
    doc_id = str(cfg["docId"])
    sp = synthetic_path_for_data_file(str(cfg["dataFile"]))
    mc = MissionControlManager(thread_id=thread_id, docman=docman)
    sess = merge_module_session(thread_id, module_id, state)
    case_cfg = _boilerplate_case_config(cfg, module_id)
    progress_module_name = _task_progress_definition(case_cfg["module_title"], cfg)["module_name"]
    _brand = str(case_cfg.get("module_title") or "作业管理大盘").strip() or "作业管理大盘"

    if action == "cancel":
        clear_module_session(thread_id, module_id)
        await _set_project_progress_and_emit(progress_module_name, set(), cfg)
        return {"ok": True, "cancelled": True}

    if action == "guide":
        clear_module_session(thread_id, module_id)
        await _set_project_progress_and_emit(
            progress_module_name,
            _configured_completed_tasks(cfg, "guide", {"作业待启动"}, module_name=progress_module_name),
            cfg,
        )
        await pusher.update_nodes(
            [
                (
                    SDUI_STEPPER_MAIN_ID,
                    "Stepper",
                    {"steps": _job_stepper_steps(0)},
                ),
                *_boilerplate_metrics_nodes(
                    case_cfg,
                    18,
                    14,
                    10,
                    center_value="12%",
                    center_label="作业健康度",
                    completed=0,
                    pending=4,
                ),
                (
                    BoilerplateDashboardIds.SUMMARY_TEXT,
                    "Text",
                    {
                        "content": f"已进入{_brand}。请先上传作业资料，再依次确认规划设计、工程安装与集群联调排期。",
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
            context=f"{_brand}已就绪。请先上传作业资料包，再按引导确认各阶段排期。",
            actions=[
                {
                    "label": "上传作业资料",
                    "verb": "module_action",
                    "payload": {"moduleId": module_id, "action": "upload_bundle", "state": {}},
                }
            ],
        )
        return {"ok": True, "next": "upload_bundle"}

    if action == "upload_bundle":
        upload_cfg = _upload_config(cfg, "job_bundle")
        await pusher.update_nodes(
            [
                (
                    SDUI_STEPPER_MAIN_ID,
                    "Stepper",
                    {"steps": _job_stepper_steps(0)},
                ),
                *_boilerplate_metrics_nodes(
                    case_cfg,
                    20,
                    16,
                    10,
                    center_value="14%",
                    center_label="作业健康度",
                    completed=0,
                    pending=4,
                ),
                (
                    BoilerplateDashboardIds.SUMMARY_TEXT,
                    "Text",
                    {
                        "content": "请在会话卡片中选择文件并上传；上传完成后将自动进入「规划设计排期」确认。",
                        "variant": "body",
                        "color": "subtle",
                    },
                ),
            ]
        )
        await mc.ask_for_file(
            purpose="job_bundle",
            title="请上传作业资料包（清单、依赖或排期输入）",
            accept=str(upload_cfg.get("accept") or ".zip,.xlsx,.csv,.pdf,.doc,.docx,.png,.jpg,.json"),
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
        upload_name = str(upload_meta.get("name") or "作业资料包")
        upload_count = len(uploads)
        await _set_project_progress_and_emit(
            progress_module_name,
            _configured_completed_tasks(
                cfg,
                "upload_bundle_complete",
                {"作业待启动", "资料已上传"},
                module_name=progress_module_name,
            ),
            cfg,
        )
        await pusher.update_nodes(
            [
                (
                    SDUI_STEPPER_MAIN_ID,
                    "Stepper",
                    {"steps": _job_stepper_steps(1, upload_name)},
                ),
                *_boilerplate_metrics_nodes(
                    case_cfg,
                    38,
                    30,
                    12,
                    center_value="28%",
                    center_label="作业健康度",
                    completed=1,
                    pending=3,
                ),
                (
                    BoilerplateDashboardIds.UPLOADED_FILES,
                    "ArtifactGrid",
                    {"title": "已上传文件", "mode": "input", "artifacts": _uploads_as_artifacts(uploads)},
                ),
                (
                    BoilerplateDashboardIds.SUMMARY_TEXT,
                    "Text",
                    {
                        "content": f"已接收 {upload_count} 份资料（最近：{upload_name}）。请确认规划设计排期。",
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
                            "content": f"已接收 {upload_count} 份资料。下一步请确认规划设计排期。",
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
                            "context": "资料已入库。请确认规划设计排期窗口。",
                            "actions": [
                                {
                                    "label": "确认规划设计排期",
                                    "verb": "module_action",
                                    "payload": {
                                        "moduleId": module_id,
                                        "action": "confirm_planning_schedule",
                                        "state": {"upload": upload_meta, "uploads": uploads},
                                    },
                                }
                            ],
                        },
                    ],
                },
                doc_id=f"chat:{thread_id}",
            )
        else:
            await mc.emit_guidance(
                context="资料已入库。请确认规划设计排期。",
                actions=[
                    {
                        "label": "确认规划设计排期",
                        "verb": "module_action",
                        "payload": {
                            "moduleId": module_id,
                            "action": "confirm_planning_schedule",
                            "state": {"upload": upload_meta, "uploads": uploads},
                        },
                    }
                ],
            )
        return {"ok": True, "next": "confirm_planning_schedule"}

    if action == "confirm_planning_schedule":
        merged = merge_module_session(thread_id, module_id, dict(state))
        uploads = _merge_uploads(merged.get("uploads"), state.get("uploads"))
        upload_meta = dict(_latest_upload_meta({"upload": merged.get("upload"), "uploads": uploads}))
        if not uploads and upload_meta:
            uploads = [upload_meta]
        upload_name = str(upload_meta.get("name") or "作业资料包")
        await _set_project_progress_and_emit(
            progress_module_name,
            _configured_completed_tasks(
                cfg,
                "confirm_planning_schedule",
                {"作业待启动", "资料已上传", "规划设计排期已确认"},
                module_name=progress_module_name,
            ),
            cfg,
        )
        await pusher.update_nodes(
            [
                (
                    SDUI_STEPPER_MAIN_ID,
                    "Stepper",
                    {"steps": _job_stepper_steps(2, upload_name)},
                ),
                *_boilerplate_metrics_nodes(
                    case_cfg,
                    55,
                    48,
                    10,
                    center_value="50%",
                    center_label="作业健康度",
                    completed=2,
                    pending=2,
                ),
                (
                    BoilerplateDashboardIds.UPLOADED_FILES,
                    "ArtifactGrid",
                    {"title": "已上传文件", "mode": "input", "artifacts": _uploads_as_artifacts(uploads)},
                ),
                (
                    BoilerplateDashboardIds.SUMMARY_TEXT,
                    "Text",
                    {
                        "content": "规划设计排期已确认。请继续确认工程安装排期窗口与依赖。",
                        "variant": "body",
                        "color": "subtle",
                    },
                ),
            ]
        )
        await mc.emit_guidance(
            context="规划设计排期已登记。请确认工程安装排期。",
            actions=[
                {
                    "label": "确认工程安装排期",
                    "verb": "module_action",
                    "payload": {"moduleId": module_id, "action": "confirm_engineering_schedule", "state": {}},
                }
            ],
        )
        return {"ok": True, "next": "confirm_engineering_schedule"}

    if action == "confirm_engineering_schedule":
        merged = merge_module_session(thread_id, module_id, dict(state))
        uploads = _merge_uploads(merged.get("uploads"), state.get("uploads"))
        upload_meta = dict(_latest_upload_meta({"upload": merged.get("upload"), "uploads": uploads}))
        if not uploads and upload_meta:
            uploads = [upload_meta]
        upload_name = str(upload_meta.get("name") or "作业资料包")
        await _set_project_progress_and_emit(
            progress_module_name,
            _configured_completed_tasks(
                cfg,
                "confirm_engineering_schedule",
                {
                    "作业待启动",
                    "资料已上传",
                    "规划设计排期已确认",
                    "工程安装排期已确认",
                },
                module_name=progress_module_name,
            ),
            cfg,
        )
        await pusher.update_nodes(
            [
                (
                    SDUI_STEPPER_MAIN_ID,
                    "Stepper",
                    {"steps": _job_stepper_steps(3, upload_name)},
                ),
                *_boilerplate_metrics_nodes(
                    case_cfg,
                    72,
                    65,
                    8,
                    center_value="72%",
                    center_label="作业健康度",
                    completed=3,
                    pending=1,
                ),
                (
                    BoilerplateDashboardIds.UPLOADED_FILES,
                    "ArtifactGrid",
                    {"title": "已上传文件", "mode": "input", "artifacts": _uploads_as_artifacts(uploads)},
                ),
                (
                    BoilerplateDashboardIds.SUMMARY_TEXT,
                    "Text",
                    {
                        "content": "工程安装排期已确认。请最后确认集群联调排期与准入条件。",
                        "variant": "body",
                        "color": "subtle",
                    },
                ),
            ]
        )
        await mc.emit_guidance(
            context="工程安装排期已登记。请确认集群联调排期。",
            actions=[
                {
                    "label": "确认集群联调排期",
                    "verb": "module_action",
                    "payload": {"moduleId": module_id, "action": "confirm_cluster_schedule", "state": {}},
                }
            ],
        )
        return {"ok": True, "next": "confirm_cluster_schedule"}

    if action == "confirm_cluster_schedule":
        merged = merge_module_session(thread_id, module_id, dict(state))
        uploads = _merge_uploads(merged.get("uploads"), state.get("uploads"))
        upload_meta = dict(_latest_upload_meta({"upload": merged.get("upload"), "uploads": uploads}))
        if not uploads and upload_meta:
            uploads = [upload_meta]
        upload_name = str(upload_meta.get("name") or "作业资料包")
        await _set_project_progress_and_emit(
            progress_module_name,
            _configured_completed_tasks(
                cfg,
                "confirm_cluster_schedule",
                {
                    "作业待启动",
                    "资料已上传",
                    "规划设计排期已确认",
                    "工程安装排期已确认",
                    "集群联调排期已确认",
                },
                module_name=progress_module_name,
            ),
            cfg,
        )
        await pusher.update_nodes(
            [
                (
                    SDUI_STEPPER_MAIN_ID,
                    "Stepper",
                    {"steps": _job_stepper_steps(4, upload_name)},
                ),
                *_boilerplate_metrics_nodes(
                    case_cfg,
                    88,
                    84,
                    6,
                    center_value="92%",
                    center_label="作业健康度",
                    completed=4,
                    pending=0,
                ),
                (
                    BoilerplateDashboardIds.UPLOADED_FILES,
                    "ArtifactGrid",
                    {"title": "已上传文件", "mode": "input", "artifacts": _uploads_as_artifacts(uploads)},
                ),
                (
                    BoilerplateDashboardIds.SUMMARY_TEXT,
                    "Text",
                    {
                        "content": "四类主线已完成确认：上传资料与三段排期均已登记。可生成闭环说明并挂载产物区。",
                        "variant": "body",
                        "color": "subtle",
                    },
                ),
            ]
        )
        await mc.emit_guidance(
            context="集群联调排期已确认。可结束本模块并生成作业闭环说明。",
            actions=[
                {
                    "label": "完成闭环",
                    "verb": "module_action",
                    "payload": {"moduleId": module_id, "action": "finish", "state": {}},
                }
            ],
        )
        return {"ok": True, "next": "finish"}

    if action == "finish":
        upload_meta = _latest_upload_meta(sess)
        upload_name = str(upload_meta.get("name") or "作业资料包")
        uploads = _merge_uploads(sess.get("uploads"), state.get("uploads"))
        throughput = 92
        quality = 90
        risk = 5
        await _set_project_progress_and_emit(
            progress_module_name,
            _configured_completed_tasks(
                cfg,
                "finish",
                {
                    "作业待启动",
                    "资料已上传",
                    "规划设计排期已确认",
                    "工程安装排期已确认",
                    "集群联调排期已确认",
                    "作业闭环完成",
                },
                module_name=progress_module_name,
            ),
            cfg,
        )
        await pusher.update_nodes(
            [
                (
                    SDUI_STEPPER_MAIN_ID,
                    "Stepper",
                    {"steps": _job_stepper_steps(4, upload_name)},
                ),
                *_boilerplate_metrics_nodes(
                    case_cfg,
                    throughput,
                    quality,
                    risk,
                    center_value="100%",
                    center_label="作业健康度",
                    completed=4,
                    pending=0,
                ),
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
                            f"{_brand}本轮已闭环：资料={upload_name}，规划设计/工程安装/集群联调排期均已确认。"
                            " 产物说明已写入输出目录。"
                        ),
                        "variant": "body",
                        "color": "subtle",
                    },
                ),
            ]
        )
        out_path = _write_job_management_report(
            module_id=module_id,
            case_cfg=case_cfg,
            upload_name=upload_name,
            throughput=throughput,
            quality=quality,
            risk=risk,
        )
        await mc.add_artifact(
            doc_id,
            synthetic_path=sp,
            artifact_id="job-management-handover-001",
            label=case_cfg["report_label"],
            path=out_path,
            kind="md",
            status="ready",
        )
        clear_module_session(thread_id, module_id)
        return {"ok": True, "done": True, "summary": "job_management 完成：作业管理大盘已闭环。"}

    return {"ok": False, "error": f"unknown action: {action!r}"}


async def _flow_job_management(
    *,
    module_id: str,
    action: str,
    state: dict[str, Any],
    thread_id: str,
    docman: Any,
    cfg: dict[str, Any],
) -> dict[str, Any]:
    """作业管理大盘：沿用四步 UI，但实际执行 plan_progress Skill。"""
    pusher = _pusher_for(cfg)
    mc = MissionControlManager(thread_id=thread_id, docman=docman)
    sess = merge_module_session(thread_id, module_id, state)
    case_cfg = _boilerplate_case_config(cfg, module_id)
    progress_module_name = _task_progress_definition(case_cfg["module_title"], cfg)["module_name"]
    brand = str(case_cfg.get("module_title") or "作业管理大盘").strip() or "作业管理大盘"

    if action == "cancel":
        clear_module_session(thread_id, module_id)
        await _set_project_progress_and_emit(progress_module_name, set(), cfg)
        return {"ok": True, "cancelled": True}

    if action == "guide":
        clear_module_session(thread_id, module_id)
        await _set_project_progress_and_emit(
            progress_module_name,
            _configured_completed_tasks(cfg, "guide", {"作业待启动"}, module_name=progress_module_name),
            cfg,
        )
        await pusher.update_nodes(
            [
                (SDUI_STEPPER_MAIN_ID, "Stepper", {"steps": _job_stepper_steps(0)}),
                *_boilerplate_metrics_nodes(
                    case_cfg,
                    18,
                    14,
                    10,
                    center_value="12%",
                    center_label="作业健康度",
                    completed=0,
                    pending=4,
                ),
                (
                    BoilerplateDashboardIds.SUMMARY_TEXT,
                    "Text",
                    {
                        "content": (
                            f"已进入{brand}。请先校验并上传《到货表.xlsx》《人员信息表.xlsx》，"
                            "随后系统会依次执行规划设计、工程安装、集群联调三段排期。"
                        ),
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
            context=f"{brand}已就绪。请先准备《到货表.xlsx》《人员信息表.xlsx》。",
            actions=[
                {
                    "label": "校验并上传资料",
                    "verb": "module_action",
                    "payload": {"moduleId": module_id, "action": "upload_bundle", "state": {}},
                }
            ],
        )
        return {"ok": True, "next": "upload_bundle"}

    if action == "upload_bundle":
        discovered_uploads, missing = _plan_progress_required_uploads()
        if not missing:
            return await _flow_job_management(
                module_id=module_id,
                action="upload_bundle_complete",
                state={"uploads": discovered_uploads, "upload": discovered_uploads[-1]},
                thread_id=thread_id,
                docman=docman,
                cfg=cfg,
            )
        await pusher.update_nodes(
            [
                (SDUI_STEPPER_MAIN_ID, "Stepper", {"steps": _job_stepper_steps(0)}),
                *_boilerplate_metrics_nodes(
                    case_cfg,
                    20,
                    16,
                    10,
                    center_value="14%",
                    center_label="作业健康度",
                    completed=0,
                    pending=4,
                ),
                (
                    BoilerplateDashboardIds.SUMMARY_TEXT,
                    "Text",
                    {
                        "content": (
                            "当前缺少严格匹配的输入文件：到货表.xlsx、人员信息表.xlsx。"
                            " 请通过会话卡片上传这两个 Excel，文件名需完全一致。"
                        ),
                        "variant": "body",
                        "color": "subtle",
                    },
                ),
            ]
        )
        handle = await mc.ask_for_file(
            purpose="job_bundle",
            title="请上传到货表.xlsx 与 人员信息表.xlsx",
            accept=".xlsx",
            multiple=True,
            module_id=module_id,
            next_action="upload_bundle_complete",
            save_relative_dir="skills/plan_progress/input",
        )
        merge_module_session(thread_id, module_id, {"cardId": getattr(handle, "card_id", None)})
        return {"ok": True, "next": "upload_bundle_complete"}

    if action == "upload_bundle_complete":
        merged = merge_module_session(thread_id, module_id, dict(state))
        discovered_uploads, missing = _plan_progress_required_uploads()
        if missing:
            await pusher.update_nodes(
                [
                    (SDUI_STEPPER_MAIN_ID, "Stepper", {"steps": _job_stepper_steps(0)}),
                    (
                        BoilerplateDashboardIds.SUMMARY_TEXT,
                        "Text",
                        {
                            "content": f"仍缺少：{', '.join(missing)}。请补充上传后重试。",
                            "variant": "body",
                            "color": "subtle",
                        },
                    ),
                ]
            )
            handle = await mc.ask_for_file(
                purpose="job_bundle",
                title="请补充上传缺失的 Excel 文件",
                accept=".xlsx",
                multiple=True,
                module_id=module_id,
                next_action="upload_bundle_complete",
                save_relative_dir="skills/plan_progress/input",
            )
            merge_module_session(thread_id, module_id, {"cardId": getattr(handle, "card_id", None)})
            return {"ok": True, "next": "upload_bundle_complete"}

        uploads = _merge_uploads(_merge_uploads(merged.get("uploads"), state.get("uploads")), discovered_uploads)
        upload_meta = dict(_latest_upload_meta({"upload": merged.get("upload"), "uploads": uploads}))
        if not upload_meta and uploads:
            upload_meta = dict(uploads[-1])
        merged = merge_module_session(
            thread_id,
            module_id,
            {"upload": upload_meta or None, "uploads": uploads},
        )
        upload_name = str(upload_meta.get("name") or "人员信息表.xlsx")
        await _set_project_progress_and_emit(
            progress_module_name,
            _configured_completed_tasks(
                cfg,
                "upload_bundle_complete",
                {"作业待启动", "资料已上传"},
                module_name=progress_module_name,
            ),
            cfg,
        )
        await pusher.update_nodes(
            [
                (SDUI_STEPPER_MAIN_ID, "Stepper", {"steps": _job_stepper_steps(1, upload_name)}),
                *_boilerplate_metrics_nodes(
                    case_cfg,
                    38,
                    30,
                    12,
                    center_value="28%",
                    center_label="作业健康度",
                    completed=1,
                    pending=3,
                ),
                (
                    BoilerplateDashboardIds.UPLOADED_FILES,
                    "ArtifactGrid",
                    {"title": "已上传文件", "mode": "input", "artifacts": _uploads_as_artifacts(uploads)},
                ),
                (
                    BoilerplateDashboardIds.SUMMARY_TEXT,
                    "Text",
                    {
                        "content": "必需资料已齐备：到货表.xlsx、人员信息表.xlsx。下一步开始执行规划设计排期。",
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
                title="资料已校验",
                node={
                    "type": "Stack",
                    "gap": "sm",
                    "children": [
                        {
                            "type": "Text",
                            "variant": "body",
                            "content": "必需资料已齐备。下一步请启动规划设计排期。",
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
                            "context": "资料已入库。可开始规划设计排期。",
                            "actions": [
                                {
                                    "label": "开始规划设计排期",
                                    "verb": "module_action",
                                    "payload": {
                                        "moduleId": module_id,
                                        "action": "confirm_planning_schedule",
                                        "state": {"upload": upload_meta, "uploads": uploads},
                                    },
                                }
                            ],
                        },
                    ],
                },
                doc_id=f"chat:{thread_id}",
            )
        else:
            await mc.emit_guidance(
                context="资料已入库。请开始规划设计排期。",
                actions=[
                    {
                        "label": "开始规划设计排期",
                        "verb": "module_action",
                        "payload": {
                            "moduleId": module_id,
                            "action": "confirm_planning_schedule",
                            "state": {"upload": upload_meta, "uploads": uploads},
                        },
                    }
                ],
            )
        return {"ok": True, "next": "confirm_planning_schedule"}

    if action == "confirm_planning_schedule":
        merged = merge_module_session(thread_id, module_id, dict(state))
        discovered_uploads, missing = _plan_progress_required_uploads()
        if missing:
            return await _flow_job_management(
                module_id=module_id,
                action="upload_bundle",
                state={},
                thread_id=thread_id,
                docman=docman,
                cfg=cfg,
            )
        uploads = _merge_uploads(_merge_uploads(merged.get("uploads"), state.get("uploads")), discovered_uploads)
        upload_meta = dict(_latest_upload_meta({"upload": merged.get("upload"), "uploads": uploads}))
        if not upload_meta and uploads:
            upload_meta = dict(uploads[-1])
        upload_name = str(upload_meta.get("name") or "人员信息表.xlsx")
        await pusher.update_nodes(
            [
                (SDUI_STEPPER_MAIN_ID, "Stepper", {"steps": _job_stepper_steps(1, upload_name)}),
                *_boilerplate_metrics_nodes(
                    case_cfg,
                    44,
                    36,
                    11,
                    center_value="36%",
                    center_label="作业健康度",
                    completed=1,
                    pending=3,
                ),
                (
                    BoilerplateDashboardIds.UPLOADED_FILES,
                    "ArtifactGrid",
                    {"title": "已上传文件", "mode": "input", "artifacts": _uploads_as_artifacts(uploads)},
                ),
                (
                    BoilerplateDashboardIds.SUMMARY_TEXT,
                    "Text",
                    {
                        "content": "正在执行规划设计排期：先运行 plan_progress Stage1 与 Stage2。",
                        "variant": "body",
                        "color": "subtle",
                    },
                ),
            ]
        )
        planning = await _run_plan_progress_planning_phase()
        if not planning.get("ok"):
            await pusher.update_nodes(
                [
                    (
                        BoilerplateDashboardIds.SUMMARY_TEXT,
                        "Text",
                        {
                            "content": f"规划设计排期执行失败：{planning.get('error')}",
                            "variant": "body",
                            "color": "warning",
                        },
                    )
                ]
            )
            return planning
        bundle_path = str(planning.get("bundle_path") or "")
        merge_module_session(
            thread_id,
            module_id,
            {"bundlePath": bundle_path, "upload": upload_meta or None, "uploads": uploads},
        )
        await _set_project_progress_and_emit(
            progress_module_name,
            _configured_completed_tasks(
                cfg,
                "confirm_planning_schedule",
                {"作业待启动", "资料已上传", "规划设计排期已确认"},
                module_name=progress_module_name,
            ),
            cfg,
        )
        await pusher.update_nodes(
            [
                (SDUI_STEPPER_MAIN_ID, "Stepper", {"steps": _job_stepper_steps(2, upload_name)}),
                *_boilerplate_metrics_nodes(
                    case_cfg,
                    55,
                    48,
                    10,
                    center_value="50%",
                    center_label="作业健康度",
                    completed=2,
                    pending=2,
                ),
                (
                    BoilerplateDashboardIds.UPLOADED_FILES,
                    "ArtifactGrid",
                    {"title": "已上传文件", "mode": "input", "artifacts": _uploads_as_artifacts(uploads)},
                ),
                (
                    BoilerplateDashboardIds.SUMMARY_TEXT,
                    "Text",
                    {
                        "content": str(planning.get("summary") or "规划设计排期已完成。"),
                        "variant": "body",
                        "color": "subtle",
                    },
                ),
            ]
        )
        await mc.emit_guidance(
            context="规划设计排期已完成。请继续执行工程安装排期。",
            actions=[
                {
                    "label": "开始工程安装排期",
                    "verb": "module_action",
                    "payload": {
                        "moduleId": module_id,
                        "action": "confirm_engineering_schedule",
                        "state": {"bundlePath": bundle_path},
                    },
                }
            ],
        )
        return {"ok": True, "next": "confirm_engineering_schedule", "bundlePath": bundle_path}

    if action == "confirm_engineering_schedule":
        merged = merge_module_session(thread_id, module_id, dict(state))
        bundle_path = str(state.get("bundlePath") or merged.get("bundlePath") or "").strip()
        if not bundle_path:
            return {"ok": False, "error": "bundlePath missing for engineering phase"}
        discovered_uploads, _ = _plan_progress_required_uploads()
        uploads = _merge_uploads(_merge_uploads(merged.get("uploads"), state.get("uploads")), discovered_uploads)
        upload_meta = dict(_latest_upload_meta({"upload": merged.get("upload"), "uploads": uploads}))
        if not upload_meta and uploads:
            upload_meta = dict(uploads[-1])
        upload_name = str(upload_meta.get("name") or "人员信息表.xlsx")
        await pusher.update_nodes(
            [
                (SDUI_STEPPER_MAIN_ID, "Stepper", {"steps": _job_stepper_steps(2, upload_name)}),
                *_boilerplate_metrics_nodes(
                    case_cfg,
                    64,
                    56,
                    9,
                    center_value="62%",
                    center_label="作业健康度",
                    completed=2,
                    pending=2,
                ),
                (
                    BoilerplateDashboardIds.SUMMARY_TEXT,
                    "Text",
                    {
                        "content": "正在执行工程安装排期：依次生成里程碑与安装排期。",
                        "variant": "body",
                        "color": "subtle",
                    },
                ),
            ]
        )
        engineering = await _run_plan_progress_engineering_phase(bundle_path)
        if not engineering.get("ok"):
            await pusher.update_nodes(
                [
                    (
                        BoilerplateDashboardIds.SUMMARY_TEXT,
                        "Text",
                        {
                            "content": f"工程安装排期执行失败：{engineering.get('error')}",
                            "variant": "body",
                            "color": "warning",
                        },
                    )
                ]
            )
            return engineering
        bundle_path = str(engineering.get("bundle_path") or bundle_path)
        merge_module_session(thread_id, module_id, {"bundlePath": bundle_path, "upload": upload_meta or None, "uploads": uploads})
        await _set_project_progress_and_emit(
            progress_module_name,
            _configured_completed_tasks(
                cfg,
                "confirm_engineering_schedule",
                {"作业待启动", "资料已上传", "规划设计排期已确认", "工程安装排期已确认"},
                module_name=progress_module_name,
            ),
            cfg,
        )
        await pusher.update_nodes(
            [
                (SDUI_STEPPER_MAIN_ID, "Stepper", {"steps": _job_stepper_steps(3, upload_name)}),
                *_boilerplate_metrics_nodes(
                    case_cfg,
                    72,
                    65,
                    8,
                    center_value="72%",
                    center_label="作业健康度",
                    completed=3,
                    pending=1,
                ),
                (
                    BoilerplateDashboardIds.UPLOADED_FILES,
                    "ArtifactGrid",
                    {"title": "已上传文件", "mode": "input", "artifacts": _uploads_as_artifacts(uploads)},
                ),
                (
                    BoilerplateDashboardIds.SUMMARY_TEXT,
                    "Text",
                    {
                        "content": str(engineering.get("summary") or "工程安装排期已完成。"),
                        "variant": "body",
                        "color": "subtle",
                    },
                ),
            ]
        )
        await mc.emit_guidance(
            context="工程安装排期已完成。请继续执行集群联调排期。",
            actions=[
                {
                    "label": "开始集群联调排期",
                    "verb": "module_action",
                    "payload": {
                        "moduleId": module_id,
                        "action": "confirm_cluster_schedule",
                        "state": {"bundlePath": bundle_path},
                    },
                }
            ],
        )
        return {"ok": True, "next": "confirm_cluster_schedule", "bundlePath": bundle_path}

    if action == "confirm_cluster_schedule":
        merged = merge_module_session(thread_id, module_id, dict(state))
        bundle_path = str(state.get("bundlePath") or merged.get("bundlePath") or "").strip()
        if not bundle_path:
            return {"ok": False, "error": "bundlePath missing for cluster phase"}
        discovered_uploads, _ = _plan_progress_required_uploads()
        uploads = _merge_uploads(_merge_uploads(merged.get("uploads"), state.get("uploads")), discovered_uploads)
        upload_meta = dict(_latest_upload_meta({"upload": merged.get("upload"), "uploads": uploads}))
        if not upload_meta and uploads:
            upload_meta = dict(uploads[-1])
        upload_name = str(upload_meta.get("name") or "人员信息表.xlsx")
        await pusher.update_nodes(
            [
                (SDUI_STEPPER_MAIN_ID, "Stepper", {"steps": _job_stepper_steps(3, upload_name)}),
                *_boilerplate_metrics_nodes(
                    case_cfg,
                    80,
                    72,
                    7,
                    center_value="82%",
                    center_label="作业健康度",
                    completed=3,
                    pending=1,
                ),
                (
                    BoilerplateDashboardIds.SUMMARY_TEXT,
                    "Text",
                    {
                        "content": "正在执行集群联调排期：进入 Stage3 反思与收尾。",
                        "variant": "body",
                        "color": "subtle",
                    },
                ),
            ]
        )
        cluster = await _run_plan_progress_cluster_phase(bundle_path)
        if not cluster.get("ok"):
            await pusher.update_nodes(
                [
                    (
                        BoilerplateDashboardIds.SUMMARY_TEXT,
                        "Text",
                        {
                            "content": f"集群联调排期执行失败：{cluster.get('error')}",
                            "variant": "body",
                            "color": "warning",
                        },
                    )
                ]
            )
            return cluster
        bundle_path = str(cluster.get("bundle_path") or bundle_path)
        merge_module_session(thread_id, module_id, {"bundlePath": bundle_path, "upload": upload_meta or None, "uploads": uploads})
        await _set_project_progress_and_emit(
            progress_module_name,
            _configured_completed_tasks(
                cfg,
                "confirm_cluster_schedule",
                {
                    "作业待启动",
                    "资料已上传",
                    "规划设计排期已确认",
                    "工程安装排期已确认",
                    "集群联调排期已确认",
                },
                module_name=progress_module_name,
            ),
            cfg,
        )
        await pusher.update_nodes(
            [
                (SDUI_STEPPER_MAIN_ID, "Stepper", {"steps": _job_stepper_steps(4, upload_name)}),
                *_boilerplate_metrics_nodes(
                    case_cfg,
                    88,
                    84,
                    6,
                    center_value="92%",
                    center_label="作业健康度",
                    completed=4,
                    pending=0,
                ),
                (
                    BoilerplateDashboardIds.UPLOADED_FILES,
                    "ArtifactGrid",
                    {"title": "已上传文件", "mode": "input", "artifacts": _uploads_as_artifacts(uploads)},
                ),
                (
                    BoilerplateDashboardIds.SUMMARY_TEXT,
                    "Text",
                    {
                        "content": str(cluster.get("summary") or "集群联调排期已完成。"),
                        "variant": "body",
                        "color": "subtle",
                    },
                ),
            ]
        )
        await mc.emit_guidance(
            context="三段排期已完成。现在可以生成闭环说明。",
            actions=[
                {
                    "label": "完成闭环",
                    "verb": "module_action",
                    "payload": {"moduleId": module_id, "action": "finish", "state": {"bundlePath": bundle_path}},
                }
            ],
        )
        return {"ok": True, "next": "finish", "bundlePath": bundle_path}

    return await _flow_job_management_legacy(
        module_id=module_id,
        action=action,
        state=state,
        thread_id=thread_id,
        docman=docman,
        cfg=cfg,
    )


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
        elif flow == "simulation_workflow":
            result = await _flow_simulation_workflow(
                module_id=mid,
                action=act,
                state=st,
                thread_id=tid,
                docman=docman,
                cfg=cfg,
            )
        elif flow == "smart_survey_workflow":
            result = await _flow_smart_survey_workflow(
                module_id=mid,
                action=act,
                state=st,
                thread_id=tid,
                docman=docman,
                cfg=cfg,
            )
        elif flow == "job_management":
            result = await _flow_job_management(
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
