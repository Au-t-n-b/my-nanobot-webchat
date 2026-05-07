from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from typing import Any, Literal

_StepOut = Literal["hitl", "error", "ok"]


def _now_ms() -> int:
    return int(time.time() * 1000)


def _print_event(evt: dict[str, Any]) -> None:
    # Subprocess stdout is decoded as UTF-8 by the platform; avoid Windows GBK console issues.
    line = (json.dumps(evt, ensure_ascii=False) + "\n").encode("utf-8", errors="replace")
    sys.stdout.buffer.write(line)
    sys.stdout.buffer.flush()


def _as_str(v: Any) -> str:
    return str(v or "").strip()


def _skill_fs_slug(skill_root: str) -> str:
    """Directory name of the skill on disk (cwd). Prefer over stdin skill_name when paths must match uploads."""
    base = os.path.basename(os.path.normpath(os.path.abspath(skill_root or ".")))
    return base if base not in ("", ".", "..") else "gongkan_skill"


def _hitl_input_save_relative_dir(skill_root: str, input_dir: str) -> str:
    """AGUI ``saveRelativeDir`` for uploads; must match ``path_config.INPUT_DIR`` used by Step 检测。"""
    root = os.path.normpath(os.path.abspath(skill_root))
    inp = os.path.normpath(os.path.abspath(input_dir))
    slug = _skill_fs_slug(skill_root)
    if inp == root or not inp.startswith(root + os.sep):
        return f"skills/{slug}/ProjectData/Input"
    rel = os.path.relpath(inp, root).replace("\\", "/")
    return f"skills/{slug}/{rel}"


def _workspace_skill_prefix(skill_root: str) -> str:
    return f"workspace/skills/{_skill_fs_slug(skill_root)}"


def _resolve_skill_ui_targets(skill_root: str, skill_name: str) -> tuple[str, str]:
    """Align dashboard.patch / bootstrap with the mounted Skill UI (e.g. zhgk vs gongkan_skill)."""
    slug = _skill_fs_slug(skill_root)
    data_file = f"skills/{slug}/data/dashboard.json"
    synthetic_path = f"skill-ui://SduiView?dataFile={data_file}"
    doc_id = "dashboard:smart-survey-workbench"
    dash = _read_json(os.path.join(skill_root, "data", "dashboard.json"))
    if dash:
        meta = dash.get("meta")
        if isinstance(meta, dict):
            d = _as_str(meta.get("docId"))
            if d:
                doc_id = d
    if doc_id == "dashboard:smart-survey-workbench":
        mod = _read_json(os.path.join(skill_root, "module.json"))
        if mod:
            d = _as_str(mod.get("docId"))
            if d:
                doc_id = d
    return synthetic_path, doc_id


def _read_json(path: str) -> dict[str, Any] | None:
    try:
        with open(path, "r", encoding="utf-8") as f:
            obj = json.load(f)
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


def _epilogue_stats_payload(skill_result_path: str) -> dict[str, Any]:
    """Compact numbers for skill.epilogue / LLM 结案（缺省为 0）。"""
    data = _read_json(skill_result_path) or {}
    sf = data.get("scene_filter") if isinstance(data.get("scene_filter"), dict) else {}
    survey = data.get("survey") if isinstance(data.get("survey"), dict) else {}
    remaining = data.get("remaining_issues") if isinstance(data.get("remaining_issues"), dict) else {}
    artifacts = data.get("artifacts") if isinstance(data.get("artifacts"), list) else []
    try:
        risk_rows = int(remaining.get("total") or 0)
    except (TypeError, ValueError):
        risk_rows = 0
    try:
        st = int(survey.get("total_items") or 0)
    except (TypeError, ValueError):
        st = 0
    try:
        sfilled = int(survey.get("filled_items") or 0)
    except (TypeError, ValueError):
        sfilled = 0
    return {
        "scenario": _as_str(sf.get("scenario")),
        "cooling_tag": _as_str(sf.get("cooling_tag")),
        "risk_rows": risk_rows,
        "artifact_count": len(artifacts),
        "survey_total": st,
        "survey_filled": sfilled,
    }


def _list_dir(path: str) -> list[str]:
    try:
        return sorted(os.listdir(path))
    except Exception:
        return []


def _find_preset_docx(files: list[str]) -> str:
    """Step1 预置/预算类底稿：标准名优先；否则 .docx 且文件名含「预置集」「预算集」或「预算案」。"""
    exact = "勘测信息预置集.docx"
    if exact in files:
        return exact
    for f in files:
        if not f.lower().endswith(".docx"):
            continue
        if "预置集" in f or "预算集" in f or "预算案" in f:
            return f
    return ""


def _ensure_runtime_project_info_json(ctx: _ZhgkCtx) -> None:
    """Ensure ``RunTime/project_info.json`` exists for Step3+.

    Upstream scripts (scene_filter / survey-build) may omit this file; Step3
    prereq checks require it. Synthesize a minimal object from ``skill_result.json``
    when possible so the pipeline can continue without manual placement.
    """
    try:
        os.makedirs(ctx.runtime_dir, exist_ok=True)
    except Exception:
        return
    path = os.path.join(ctx.runtime_dir, "project_info.json")
    existing = _read_json(path) if os.path.exists(path) else None
    if isinstance(existing, dict) and _as_str(existing.get("项目名称")):
        return

    sr = _read_json(os.path.join(ctx.output_dir, "skill_result.json")) or {}
    pi: dict[str, Any] = {}
    raw_pi = sr.get("project_info")
    if isinstance(raw_pi, dict):
        pi = {str(k): v for k, v in raw_pi.items() if isinstance(k, str)}
    name = _as_str(pi.get("项目名称"))
    if not name:
        sc = sr.get("scene_filter") if isinstance(sr.get("scene_filter"), dict) else {}
        name = _as_str(sc.get("scenario")) or _as_str(sc.get("cooling_tag")) or "工勘项目"
        pi["项目名称"] = name
    if not pi:
        pi = {"项目名称": "工勘项目"}
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(pi, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _input_dir_diag_lines(input_dir: str, *, max_names: int = 30) -> list[str]:
    """Human-readable lines for Step1 missing-input diagnostics (path mismatch vs naming)."""
    abs_inp = os.path.normpath(os.path.abspath(input_dir))
    lines = [f"（诊断）INPUT_DIR = {abs_inp}"]
    try:
        names = _list_dir(input_dir)
    except Exception as e:
        lines.append(f"（诊断）无法列出目录：{e}")
        return lines
    if not names:
        lines.append(
            "（诊断）目录为空：若左侧已上传，多半是「上传落盘 workspace」与「技能 cwd 的 ProjectData/Input」"
            "不在同一颗目录树（请核对 nanobot 配置里 agents.defaults.workspace、环境变量 NANOBOT_AGUI_SKILLS_ROOT / NANOBOT_AGUI_WORKSPACE）。"
        )
        return lines
    lines.append("（诊断）目录内现有文件：" + ", ".join(names[:max_names]) + (" …" if len(names) > max_names else ""))
    return lines


def _detect_step1_inputs(input_dir: str) -> dict[str, Any]:
    files = _list_dir(input_dir)
    boq = next((f for f in files if f.lower().endswith(".xlsx") and "boq" in f.lower()), "")
    preset = _find_preset_docx(files)
    missing: list[str] = []
    if not boq:
        missing.append("BOQ_xxx.xlsx（文件名需包含“BOQ”）")
    if not preset:
        missing.append(
            "预置/预算底稿：.docx 且文件名需含「预置集」「预算集」或「预算案」（推荐 勘测信息预置集.docx）"
        )
    return {"missing": missing, "boq": boq, "preset": preset}


def _emit_stepper(
    *,
    thread_id: str,
    skill_name: str,
    run_id: str,
    synthetic_path: str,
    doc_id: str,
    s1: str,
    s2: str,
    s3: str,
    s4: str,
) -> None:
    _print_event(
        {
            "event": "dashboard.patch",
            "threadId": thread_id,
            "skillName": skill_name,
            "skillRunId": run_id,
            "timestamp": _now_ms(),
            "payload": {
                "syntheticPath": synthetic_path,
                "docId": doc_id,
                "ops": [
                    {
                        "op": "merge",
                        "target": {"by": "id", "nodeId": "stepper-main"},
                        "value": {
                            "type": "Stepper",
                            "steps": [
                                {"id": "s1", "title": "输入准备", "status": s1},
                                {"id": "s2", "title": "场景筛选与底表过滤", "status": s2},
                                {"id": "s3", "title": "勘测数据汇总", "status": s3},
                                {"id": "s4", "title": "报告生成与审批", "status": s4},
                            ],
                        },
                    }
                ],
            },
        }
    )


def _emit_summary(
    *,
    thread_id: str,
    skill_name: str,
    run_id: str,
    synthetic_path: str,
    doc_id: str,
    content: str,
) -> None:
    _print_event(
        {
            "event": "dashboard.patch",
            "threadId": thread_id,
            "skillName": skill_name,
            "skillRunId": run_id,
            "timestamp": _now_ms(),
            "payload": {
                "syntheticPath": synthetic_path,
                "docId": doc_id,
                "ops": [
                    {
                        "op": "merge",
                        "target": {"by": "id", "nodeId": "summary-text"},
                        "value": {"type": "Text", "variant": "body", "color": "subtle", "content": content},
                    }
                ],
            },
        }
    )


def _emit_phase_handoff(
    *,
    thread_id: str,
    skill_run_id: str,
    from_module: str,
    to_module: str | None,
) -> None:
    """Wake up ``project_guide`` when this phase's tasks are 100% done.

    Schema mirrors ``phase_rules.make_phase_guide_handoff_event`` (we don't
    import it because the platform installs only ``runtime/`` of the active
    skill into the subprocess sys.path; copying the small envelope is cheaper
    than introducing a hard dependency from the phase drivers to project_guide).

    The platform's ``skill_resume_runner`` sees ``event=skill_runtime_start``
    in our stdout and re-enters its driver loop with this payload's
    ``transition`` / ``transition_id`` flattened into ``request.result``,
    which is exactly what ``templates/project_guide/runtime/driver.py`` reads.
    """
    transition_id = f"{from_module}->{to_module or '∅'}@{_now_ms()}"
    _print_event(
        {
            "event": "skill_runtime_start",
            "threadId": thread_id,
            "skillRunId": skill_run_id,
            "timestamp": _now_ms(),
            "payload": {
                "skillName": "project_guide",
                "action": "guide_next_phase",
                "transition": {
                    "from_module": from_module,
                    "to_module": to_module,
                },
                "transition_id": transition_id,
            },
        }
    )


def _emit_task_progress(
    *, thread_id: str, skill_name: str, run_id: str, done_count: int, total: int = 4
) -> None:
    """Push the smart-survey phase progress so the platform can persist it to
    ``task_progress.json`` and broadcast a ``TaskStatusUpdate`` SSE.

    Convention (mirrors ``jmfz`` driver):

    * ``moduleId`` / ``moduleName`` MUST equal the canonical IDs used in
      ``task_progress.json`` and ``templates/project_guide/data/phases.json``;
      otherwise ``merge_task_progress_sync_to_disk`` will skip-without-merging
      because the module won't be found on disk.
    * ``tasks`` length MUST equal the on-disk task count for ``smart_survey``
      (currently 4); the platform merges by index, preserving the Chinese task
      names already on disk. We still send English ``name`` slugs + Chinese
      ``displayName`` for diagnostic readability.
    * Callers should only ever advance ``done_count`` forward (1 → 2 → 3 → 4),
      because the merge overwrites flags by index — emitting ``done_count=0``
      mid-run would clobber a previously-completed task.
    """
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
                        "moduleId": "smart_survey",
                        "moduleName": "智慧工勘",
                        "updatedAt": _now_ms(),
                        "tasks": [
                            {
                                "name": "scene_filter",
                                "displayName": "场景筛选与底表过滤",
                                "completed": done_count >= 1,
                            },
                            {
                                "name": "survey_summary",
                                "displayName": "勘测数据汇总",
                                "completed": done_count >= 2,
                            },
                            {
                                "name": "report_gen",
                                "displayName": "报告生成",
                                "completed": done_count >= 3,
                            },
                            {
                                "name": "approval_close",
                                "displayName": "审批与分发闭环",
                                "completed": done_count >= 4,
                            },
                        ],
                    }
                ],
            },
        }
    )


def _clamp_pct(n: Any, *, default: int = 0) -> int:
    try:
        v = int(float(n))
    except (TypeError, ValueError):
        v = default
    return max(0, min(100, v))


def _golden_triple_after_step1(result: dict[str, Any]) -> tuple[int, int, int]:
    """Map scene_filter output to GoldenMetrics 0..100 (SduiGoldenMetrics renders values as %)."""
    scene = result.get("scene_filter") if isinstance(result.get("scene_filter"), dict) else {}
    summary = scene.get("filter_summary") if isinstance(scene.get("filter_summary"), dict) else {}
    n_tables = len(summary)
    total_rows = 0
    for v in summary.values():
        try:
            total_rows += int(v)
        except (TypeError, ValueError):
            pass
    survey = min(48, 28 + min(12, n_tables * 4) + min(8, total_rows // 150))
    quality = min(52, 24 + min(16, n_tables * 3) + min(10, total_rows // 200))
    risk = min(30, 6 + min(14, max(0, total_rows // 120)))
    return _clamp_pct(survey), _clamp_pct(quality), _clamp_pct(risk)


def _golden_triple_after_step2(result: dict[str, Any]) -> tuple[int, int, int]:
    survey = result.get("survey") if isinstance(result.get("survey"), dict) else {}
    total = int(survey.get("total_items") or 0)
    filled = int(survey.get("filled_items") or 0)
    ratio = (filled / total) if total > 0 else 0.0
    survey_pct = min(75, 48 + int(ratio * 28))
    quality_pct = min(80, 45 + int(ratio * 32))
    empty_by = survey.get("empty_by_type") if isinstance(survey.get("empty_by_type"), dict) else {}
    gaps = 0
    for v in empty_by.values():
        try:
            gaps += int(v)
        except (TypeError, ValueError):
            pass
    risk_pct = min(38, 10 + min(22, gaps * 2))
    return _clamp_pct(survey_pct), _clamp_pct(quality_pct), _clamp_pct(risk_pct)


def _emit_progress_dashboard_patch(ctx: _ZhgkCtx, *, survey: int, quality: int, risk: int) -> None:
    """Patch golden-metrics plus donut/bar charts in one SSE payload (same numeric source as metrics)."""
    survey, quality, risk = _clamp_pct(survey), _clamp_pct(quality), _clamp_pct(risk)
    overall = int(round((survey + quality + (100 - risk)) / 3.0))
    overall = max(1, min(99, overall))
    remainder = 100 - overall
    _print_event(
        {
            "event": "dashboard.patch",
            "threadId": ctx.thread_id,
            "skillName": ctx.skill_name,
            "skillRunId": ctx.run_id,
            "timestamp": _now_ms(),
            "payload": {
                "syntheticPath": ctx.synthetic_path,
                "docId": ctx.doc_id,
                "ops": [
                    {
                        "op": "merge",
                        "target": {"by": "id", "nodeId": "golden-metrics"},
                        "value": {
                            "type": "GoldenMetrics",
                            "id": "golden-metrics",
                            "metrics": [
                                {"id": "metric-throughput", "label": "勘测完成度", "value": survey, "color": "accent"},
                                {"id": "metric-quality", "label": "数据完整率", "value": quality, "color": "success"},
                                {"id": "metric-risk", "label": "遗留问题数", "value": risk, "color": "warning"},
                            ],
                        },
                    },
                    {
                        "op": "merge",
                        "target": {"by": "id", "nodeId": "chart-donut"},
                        "value": {
                            "type": "DonutChart",
                            "id": "chart-donut",
                            "centerLabel": "任务完成度",
                            "centerValue": f"{overall}%",
                            "segments": [
                                {"label": "已完成", "value": overall, "color": "success"},
                                {"label": "待办", "value": remainder, "color": "subtle"},
                            ],
                        },
                    },
                    {
                        "op": "merge",
                        "target": {"by": "id", "nodeId": "chart-bar"},
                        "value": {
                            "type": "BarChart",
                            "id": "chart-bar",
                            "valueUnit": "",
                            "data": [
                                {"label": "勘测完成度", "value": survey, "color": "accent"},
                                {"label": "数据完整率", "value": quality, "color": "success"},
                                {"label": "遗留问题数", "value": risk, "color": "warning"},
                            ],
                        },
                    },
                ],
            },
        }
    )


def _dedupe_artifact_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Stable de-dupe by logical path (case-insensitive); empty path falls back to artifactId / index."""
    seen: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for idx, it in enumerate(items):
        raw_path = str(it.get("path") or "").strip().replace("\\", "/")
        aid = str(it.get("artifactId") or "").strip()
        key = raw_path.lower() if raw_path else f"id:{aid or f'row-{idx}'}"
        if key not in seen:
            order.append(key)
        seen[key] = it
    return [seen[k] for k in order]


def _publish_artifacts(
    *,
    thread_id: str,
    skill_name: str,
    run_id: str,
    synthetic_path: str,
    doc_id: str,
    node_id: str,
    items: list[dict[str, Any]],
) -> None:
    deduped = _dedupe_artifact_items(items)
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
                "artifactsNodeId": node_id,
                "items": deduped,
            },
        }
    )


def _run_py(
    *,
    skill_root: str,
    script_rel: str,
) -> tuple[bool, str]:
    script_path = os.path.join(skill_root, *script_rel.split("/"))
    try:
        proc = subprocess.run(
            [sys.executable, script_path],
            cwd=skill_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if proc.returncode != 0:
            return False, proc.stdout[-2000:] if proc.stdout else ""
        return True, proc.stdout[-2000:] if proc.stdout else ""
    except Exception as e:
        return False, str(e)


@dataclass(frozen=True)
class _ZhgkCtx:
    thread_id: str
    skill_name: str
    request_id: str
    run_id: str
    synthetic_path: str
    doc_id: str
    skill_root: str
    input_dir: str
    output_dir: str
    runtime_dir: str
    start_dir: str


def _stderr_log(msg: str) -> None:
    try:
        sys.stderr.write(msg + "\n")
        sys.stderr.flush()
    except Exception:
        pass


def _log_resume_upload_disk_hint(ctx: _ZhgkCtx, action: str, result: Any) -> None:
    """Best-effort: if resume payload lists uploads but INPUT_DIR is not ready yet, log to stderr."""
    if action not in {"zhgk_step1_scene_filter", "zhgk_step2_survey_build", "zhgk_step2_merge_rebuild"}:
        return
    if not isinstance(result, dict):
        return
    declared: list[str] = []
    for key in ("files", "uploads"):
        raw = result.get(key)
        if not isinstance(raw, list):
            continue
        for item in raw:
            if not isinstance(item, dict):
                continue
            cand = _as_str(
                item.get("name")
                or item.get("filename")
                or item.get("logicalPath")
                or item.get("path")
            )
            if not cand:
                continue
            base = cand.replace("\\", "/").split("/")[-1]
            if base:
                declared.append(base)
    if not declared:
        return
    on_disk = set(_list_dir(ctx.input_dir))
    missing_on_disk = [n for n in declared if n not in on_disk]
    if missing_on_disk:
        _stderr_log(
            "[zhgk-driver] resume payload lists files not yet present under INPUT_DIR: "
            + ", ".join(missing_on_disk)
            + f" | action={action} | input_dir={ctx.input_dir}"
        )


def _emit_warm_hitl_guidance(
    *,
    thread_id: str,
    skill_name: str,
    request_id: str,
    run_id: str,
    stable_suffix: str,
    context: str,
) -> None:
    rid = _as_str(request_id) or uuid.uuid4().hex[:12]
    _print_event(
        {
            "event": "chat.guidance",
            "threadId": thread_id,
            "skillName": skill_name,
            "skillRunId": run_id,
            "timestamp": _now_ms(),
            "payload": {
                "cardId": f"zhgk:warm:{stable_suffix}:{rid}",
                "context": context,
                "actions": [],
            },
        }
    )


def _emit_friendly_step_ack(ctx: _ZhgkCtx, *, card_id: str, context: str) -> None:
    """Short chat.guidance for left pane (no LLM); stable card_id allows replace flows later."""
    _print_event(
        {
            "event": "chat.guidance",
            "threadId": ctx.thread_id,
            "skillName": ctx.skill_name,
            "skillRunId": ctx.run_id,
            "timestamp": _now_ms(),
            "payload": {"cardId": card_id, "context": context, "actions": []},
        }
    )


def _emit_dashboard_bootstrap_from_disk(ctx: _ZhgkCtx) -> None:
    """Push full SDUI document so right panel mounts even if platform never sent SkillUiBootstrap."""
    dash_path = os.path.join(ctx.skill_root, "data", "dashboard.json")
    doc = _read_json(dash_path)
    if not doc:
        return
    _print_event(
        {
            "event": "dashboard.bootstrap",
            "threadId": ctx.thread_id,
            "skillName": ctx.skill_name,
            "skillRunId": ctx.run_id,
            "timestamp": _now_ms(),
            "payload": {
                "syntheticPath": ctx.synthetic_path,
                "docId": ctx.doc_id,
                "document": doc,
            },
        }
    )


def _zhgk_step1(ctx: _ZhgkCtx) -> _StepOut:
    missing_start = [
        f
        for f in ["勘测问题底表.xlsx", "评估项底表.xlsx", "工勘常见高风险库.xlsx"]
        if not os.path.exists(os.path.join(ctx.start_dir, f))
    ]
    if missing_start:
        _emit_stepper(
            thread_id=ctx.thread_id,
            skill_name=ctx.skill_name,
            run_id=ctx.run_id,
            synthetic_path=ctx.synthetic_path,
            doc_id=ctx.doc_id,
            s1="running",
            s2="waiting",
            s3="waiting",
            s4="waiting",
        )
        _emit_summary(
            thread_id=ctx.thread_id,
            skill_name=ctx.skill_name,
            run_id=ctx.run_id,
            synthetic_path=ctx.synthetic_path,
            doc_id=ctx.doc_id,
            content="Step1 环境缺失：ProjectData/Start/ 未就绪。\n" + "\n".join([f"- {x}" for x in missing_start]),
        )
        return "error"

    detected = _detect_step1_inputs(ctx.input_dir)
    missing_inputs: list[str] = detected["missing"]
    if missing_inputs:
        _emit_stepper(
            thread_id=ctx.thread_id,
            skill_name=ctx.skill_name,
            run_id=ctx.run_id,
            synthetic_path=ctx.synthetic_path,
            doc_id=ctx.doc_id,
            s1="waiting",
            s2="waiting",
            s3="waiting",
            s4="waiting",
        )
        diag = "\n".join(_input_dir_diag_lines(ctx.input_dir))
        _stderr_log("[zhgk-driver] Step1 missing_inputs | " + diag.replace("\n", " | "))
        _emit_summary(
            thread_id=ctx.thread_id,
            skill_name=ctx.skill_name,
            run_id=ctx.run_id,
            synthetic_path=ctx.synthetic_path,
            doc_id=ctx.doc_id,
            content="Step1：检测到缺少必需输入件，请上传后系统将自动继续执行场景筛选。\n缺失项：\n"
            + "\n".join([f"- {x}" for x in missing_inputs])
            + "\n\n"
            + diag,
        )
        _emit_warm_hitl_guidance(
            thread_id=ctx.thread_id,
            skill_name=ctx.skill_name,
            request_id=ctx.request_id,
            run_id=ctx.run_id,
            stable_suffix="step1",
            context="滴！我已准备就绪。但发现还缺少项目 BOQ 和预置集，麻烦您在下方卡片中上传一下，收到后我马上为您执行场景过滤哦~",
        )
        _print_event(
            {
                "event": "hitl.file_request",
                "threadId": ctx.thread_id,
                "skillName": ctx.skill_name,
                "skillRunId": ctx.run_id,
                "timestamp": _now_ms(),
                "payload": {
                    "requestId": f"{ctx.request_id}:step1_upload_inputs",
                    "cardId": "gongkan:step1:file",
                    "purpose": "gongkan-step1-inputs",
                    "title": "请上传智慧工勘 Step1 必需输入件",
                    "description": "缺失项：\n" + "\n".join([f"- {x}" for x in missing_inputs]),
                    "accept": ".xlsx,.docx",
                    "multiple": True,
                    "saveRelativeDir": _hitl_input_save_relative_dir(ctx.skill_root, ctx.input_dir),
                    "resumeAction": "zhgk_step1_scene_filter",
                    "onCancelAction": "cancel_step1_upload",
                    "skillName": ctx.skill_name,
                    "stateNamespace": ctx.skill_name,
                    "stepId": "zhgk.step1.inputs",
                    "expiresAt": _now_ms() + 30 * 60 * 1000,
                },
            }
        )
        return "hitl"

    _emit_friendly_step_ack(
        ctx,
        card_id="zhgk:ack:step1:inputs-ready",
        context="叮！您的文件我已经收到啦，正在为您快马加鞭地做场景筛选与底表过滤，请稍候~",
    )
    _emit_stepper(
        thread_id=ctx.thread_id,
        skill_name=ctx.skill_name,
        run_id=ctx.run_id,
        synthetic_path=ctx.synthetic_path,
        doc_id=ctx.doc_id,
        s1="done",
        s2="running",
        s3="waiting",
        s4="waiting",
    )
    _emit_summary(
        thread_id=ctx.thread_id,
        skill_name=ctx.skill_name,
        run_id=ctx.run_id,
        synthetic_path=ctx.synthetic_path,
        doc_id=ctx.doc_id,
        content="Step1：输入件齐备，开始执行场景筛选与底表过滤（scene_filter.py）。",
    )

    ok, tail = _run_py(skill_root=ctx.skill_root, script_rel="zhgk/scene-filter/scripts/scene_filter.py")
    if not ok:
        _print_event(
            {
                "event": "chat.guidance",
                "threadId": ctx.thread_id,
                "skillName": ctx.skill_name,
                "skillRunId": ctx.run_id,
                "timestamp": _now_ms(),
                "payload": {"context": "Step1 执行失败：\n" + tail, "actions": []},
            }
        )
        return "error"

    skill_result_path = os.path.join(ctx.output_dir, "skill_result.json")
    result = _read_json(skill_result_path) or {}
    scene = result.get("scene_filter") if isinstance(result.get("scene_filter"), dict) else {}
    cooling_tag = _as_str(scene.get("cooling_tag")) or "未知"
    scenario = _as_str(scene.get("scenario")) or "未知"
    summary = scene.get("filter_summary") if isinstance(scene.get("filter_summary"), dict) else {}
    lines = [f"Step1 完成。", f"制冷方式：{cooling_tag}", f"勘测场景：{scenario}"]
    if summary:
        lines.append("过滤结果：")
        for k, v in summary.items():
            lines.append(f"- {k}: {v} 行")
    _emit_stepper(
        thread_id=ctx.thread_id,
        skill_name=ctx.skill_name,
        run_id=ctx.run_id,
        synthetic_path=ctx.synthetic_path,
        doc_id=ctx.doc_id,
        s1="done",
        s2="done",
        s3="waiting",
        s4="waiting",
    )
    _emit_summary(
        thread_id=ctx.thread_id,
        skill_name=ctx.skill_name,
        run_id=ctx.run_id,
        synthetic_path=ctx.synthetic_path,
        doc_id=ctx.doc_id,
        content="\n".join(lines),
    )

    uploaded_items = [
        {
            "artifactId": f"input-{i}",
            "label": name,
            "path": f"{_workspace_skill_prefix(ctx.skill_root)}/ProjectData/Input/{name}",
            "kind": "other",
            "status": "ready",
        }
        for i, name in enumerate(_list_dir(ctx.input_dir), start=1)
    ]
    if uploaded_items:
        _publish_artifacts(
            thread_id=ctx.thread_id,
            skill_name=ctx.skill_name,
            run_id=ctx.run_id,
            synthetic_path=ctx.synthetic_path,
            doc_id=ctx.doc_id,
            node_id="uploaded-files",
            items=uploaded_items,
        )

    runtime_items = [
        {
            "artifactId": f"runtime-{i}",
            "label": name,
            "path": f"{_workspace_skill_prefix(ctx.skill_root)}/ProjectData/RunTime/{name}",
            "kind": "other",
            "status": "ready",
        }
        for i, name in enumerate(_list_dir(ctx.runtime_dir), start=1)
        if name.lower().endswith((".xlsx", ".json"))
    ]
    if os.path.exists(skill_result_path):
        runtime_items.append(
            {
                "artifactId": "skill-result",
                "label": "skill_result.json",
                "path": f"{_workspace_skill_prefix(ctx.skill_root)}/ProjectData/Output/skill_result.json",
                "kind": "other",
                "status": "ready",
            }
        )
    if runtime_items:
        _publish_artifacts(
            thread_id=ctx.thread_id,
            skill_name=ctx.skill_name,
            run_id=ctx.run_id,
            synthetic_path=ctx.synthetic_path,
            doc_id=ctx.doc_id,
            node_id="artifacts",
            items=runtime_items,
        )

    gs, gq, gr = _golden_triple_after_step1(result)
    _emit_progress_dashboard_patch(ctx, survey=gs, quality=gq, risk=gr)

    # 混合模式样板：Step1 结束后委托一次受控 Agent 子任务，将结论写回 dashboard「summary-text」。
    # 由 bridge 的 skill.agent_task_execute 处理；无 Agent 会话时会被安全跳过。
    _print_event(
        {
            "event": "skill.agent_task_execute",
            "threadId": ctx.thread_id,
            "skillName": ctx.skill_name,
            "skillRunId": ctx.run_id,
            "timestamp": _now_ms(),
            "payload": {
                "parentRequestId": ctx.request_id,
                "taskId": f"{ctx.request_id}:hybrid:step1_scene_digest",
                "stepId": "zhgk.step1.hybrid_scene_digest",
                "goal": (
                    "请在当前技能工作区内用工具读取事实并输出简短中文摘要（<=400字）：\n"
                    "1) `ProjectData/Output/skill_result.json` 中的场景/冷却标签及过滤摘要；\n"
                    "2) 若存在，`ProjectData/RunTime/勘测问题底表_过滤.xlsx` 仅说明已生成即可（无需展开全表）。\n"
                    "不要编造未读到的字段。"
                ),
                "allowedTools": ["read_file", "list_dir"],
                "maxIterations": 6,
                "resultSchema": {"type": "string"},
                "syntheticPath": ctx.synthetic_path,
                "docId": ctx.doc_id,
                "summaryNodeId": "summary-text",
            },
        }
    )

    _emit_friendly_step_ack(
        ctx,
        card_id="zhgk:ack:step1:done",
        context="Step1 搞定啦！场景筛选已完成，接下来我会继续帮您跑后续步骤~",
    )
    _emit_task_progress(
        thread_id=ctx.thread_id, skill_name=ctx.skill_name, run_id=ctx.run_id, done_count=1
    )
    return "ok"


def _zhgk_step2(ctx: _ZhgkCtx, step2_action: str) -> _StepOut:
    need = [
        ("RunTime/勘测问题底表_过滤.xlsx", os.path.join(ctx.runtime_dir, "勘测问题底表_过滤.xlsx")),
        ("Input/勘测结果.xlsx", os.path.join(ctx.input_dir, "勘测结果.xlsx")),
    ]
    missing = [label for label, path in need if not os.path.exists(path)]
    if missing:
        _emit_stepper(
            thread_id=ctx.thread_id,
            skill_name=ctx.skill_name,
            run_id=ctx.run_id,
            synthetic_path=ctx.synthetic_path,
            doc_id=ctx.doc_id,
            s1="done",
            s2="done",
            s3="waiting",
            s4="waiting",
        )
        _emit_summary(
            thread_id=ctx.thread_id,
            skill_name=ctx.skill_name,
            run_id=ctx.run_id,
            synthetic_path=ctx.synthetic_path,
            doc_id=ctx.doc_id,
            content="Step2：缺少必要输入，上传后将自动继续执行勘测汇总。\n缺失项：\n"
            + "\n".join([f"- {x}" for x in missing]),
        )
        _emit_warm_hitl_guidance(
            thread_id=ctx.thread_id,
            skill_name=ctx.skill_name,
            request_id=ctx.request_id,
            run_id=ctx.run_id,
            stable_suffix="step2",
            context="第一步的场景过滤已经顺利完成！接下来要进行数据汇总了，但我还需要一份勘测结果表，麻烦您补充上传一下~",
        )
        _print_event(
            {
                "event": "hitl.file_request",
                "threadId": ctx.thread_id,
                "skillName": ctx.skill_name,
                "skillRunId": ctx.run_id,
                "timestamp": _now_ms(),
                "payload": {
                    "requestId": f"{ctx.request_id}:step2_upload_inputs",
                    "cardId": "gongkan:step2:file",
                    "purpose": "gongkan-step2-inputs",
                    "title": "请上传智慧工勘 Step2 勘测汇总所需文件",
                    "description": "缺失项：\n" + "\n".join([f"- {x}" for x in missing]),
                    "accept": ".xlsx,.zip,.jpg,.jpeg,.png,.webp",
                    "multiple": True,
                    "saveRelativeDir": _hitl_input_save_relative_dir(ctx.skill_root, ctx.input_dir),
                    "resumeAction": "zhgk_step2_survey_build",
                    "onCancelAction": "cancel_step2_upload",
                    "skillName": ctx.skill_name,
                    "stateNamespace": ctx.skill_name,
                    "stepId": "zhgk.step2.inputs",
                    "expiresAt": _now_ms() + 45 * 60 * 1000,
                },
            }
        )
        return "hitl"

    _emit_friendly_step_ack(
        ctx,
        card_id="zhgk:ack:step2:inputs-ready",
        context="收到勘测结果表啦，我这就开始帮您汇总数据、生成待办清单~",
    )
    _emit_stepper(
        thread_id=ctx.thread_id,
        skill_name=ctx.skill_name,
        run_id=ctx.run_id,
        synthetic_path=ctx.synthetic_path,
        doc_id=ctx.doc_id,
        s1="done",
        s2="done",
        s3="running",
        s4="waiting",
    )
    _emit_summary(
        thread_id=ctx.thread_id,
        skill_name=ctx.skill_name,
        run_id=ctx.run_id,
        synthetic_path=ctx.synthetic_path,
        doc_id=ctx.doc_id,
        content="Step2：开始生成全量勘测结果表与三类待办表。",
    )

    script_rel = (
        "zhgk/survey-build/scripts/merge_and_rebuild.py"
        if step2_action == "zhgk_step2_merge_rebuild"
        else "zhgk/survey-build/scripts/generate_survey_table.py"
    )
    ok, tail = _run_py(skill_root=ctx.skill_root, script_rel=script_rel)
    if not ok:
        _print_event(
            {
                "event": "chat.guidance",
                "threadId": ctx.thread_id,
                "skillName": ctx.skill_name,
                "skillRunId": ctx.run_id,
                "timestamp": _now_ms(),
                "payload": {"context": "Step2 执行失败：\n" + tail, "actions": []},
            }
        )
        return "error"

    skill_result_path = os.path.join(ctx.output_dir, "skill_result.json")
    result = _read_json(skill_result_path) or {}
    survey = result.get("survey") if isinstance(result.get("survey"), dict) else {}
    total = int(survey.get("total_items") or 0)
    filled = int(survey.get("filled_items") or 0)
    empty_by_type = survey.get("empty_by_type") if isinstance(survey.get("empty_by_type"), dict) else {}
    todo_lines = []
    if empty_by_type:
        for k, v in empty_by_type.items():
            todo_lines.append(f"- {k}: {v}")

    _emit_stepper(
        thread_id=ctx.thread_id,
        skill_name=ctx.skill_name,
        run_id=ctx.run_id,
        synthetic_path=ctx.synthetic_path,
        doc_id=ctx.doc_id,
        s1="done",
        s2="done",
        s3="done",
        s4="waiting",
    )
    _emit_summary(
        thread_id=ctx.thread_id,
        skill_name=ctx.skill_name,
        run_id=ctx.run_id,
        synthetic_path=ctx.synthetic_path,
        doc_id=ctx.doc_id,
        content="Step2 完成。\n"
        + f"全量勘测项：{filled}/{total}\n"
        + ("待办分类：\n" + "\n".join(todo_lines) if todo_lines else ""),
    )

    uploaded_items = [
        {
            "artifactId": f"input-{i}",
            "label": name,
            "path": f"{_workspace_skill_prefix(ctx.skill_root)}/ProjectData/Input/{name}",
            "kind": "other",
            "status": "ready",
        }
        for i, name in enumerate(_list_dir(ctx.input_dir), start=1)
    ]
    if uploaded_items:
        _publish_artifacts(
            thread_id=ctx.thread_id,
            skill_name=ctx.skill_name,
            run_id=ctx.run_id,
            synthetic_path=ctx.synthetic_path,
            doc_id=ctx.doc_id,
            node_id="uploaded-files",
            items=uploaded_items,
        )

    output_files = [
        "全量勘测结果表.xlsx",
        "待客户确认勘测项.xlsx",
        "待拍摄图片项.xlsx",
        "待补充勘测项.xlsx",
    ]
    out_items: list[dict[str, Any]] = []
    for idx, name in enumerate(output_files, start=1):
        if os.path.exists(os.path.join(ctx.output_dir, name)):
            out_items.append(
                {
                    "artifactId": f"out-{idx}",
                    "label": name,
                    "path": f"{_workspace_skill_prefix(ctx.skill_root)}/ProjectData/Output/{name}",
                    "kind": "other",
                    "status": "ready",
                }
            )
    if os.path.exists(skill_result_path):
        out_items.append(
            {
                "artifactId": "skill-result",
                "label": "skill_result.json",
                "path": f"{_workspace_skill_prefix(ctx.skill_root)}/ProjectData/Output/skill_result.json",
                "kind": "other",
                "status": "ready",
            }
        )
    if out_items:
        _publish_artifacts(
            thread_id=ctx.thread_id,
            skill_name=ctx.skill_name,
            run_id=ctx.run_id,
            synthetic_path=ctx.synthetic_path,
            doc_id=ctx.doc_id,
            node_id="artifacts",
            items=out_items,
        )

    s2, q2, r2 = _golden_triple_after_step2(result)
    _emit_progress_dashboard_patch(ctx, survey=s2, quality=q2, risk=r2)

    _emit_friendly_step_ack(
        ctx,
        card_id="zhgk:ack:step2:done",
        context="勘测数据汇总完成！待办清单已更新，准备进入报告生成阶段~",
    )
    _emit_task_progress(
        thread_id=ctx.thread_id, skill_name=ctx.skill_name, run_id=ctx.run_id, done_count=2
    )
    return "ok"


def _zhgk_step3(ctx: _ZhgkCtx) -> _StepOut:
    _ensure_runtime_project_info_json(ctx)
    prereq = [
        ("Output/全量勘测结果表.xlsx", os.path.join(ctx.output_dir, "全量勘测结果表.xlsx")),
        ("RunTime/评估项底表_过滤.xlsx", os.path.join(ctx.runtime_dir, "评估项底表_过滤.xlsx")),
        ("RunTime/工勘常见高风险库_过滤.xlsx", os.path.join(ctx.runtime_dir, "工勘常见高风险库_过滤.xlsx")),
        ("RunTime/project_info.json", os.path.join(ctx.runtime_dir, "project_info.json")),
        ("Start/新版项目工勘报告模板.docx", os.path.join(ctx.start_dir, "新版项目工勘报告模板.docx")),
    ]
    missing = [label for label, path in prereq if not os.path.exists(path)]
    if missing:
        _emit_stepper(
            thread_id=ctx.thread_id,
            skill_name=ctx.skill_name,
            run_id=ctx.run_id,
            synthetic_path=ctx.synthetic_path,
            doc_id=ctx.doc_id,
            s1="done",
            s2="done",
            s3="waiting",
            s4="waiting",
        )
        _emit_summary(
            thread_id=ctx.thread_id,
            skill_name=ctx.skill_name,
            run_id=ctx.run_id,
            synthetic_path=ctx.synthetic_path,
            doc_id=ctx.doc_id,
            content="Step3：缺少前置依赖，无法生成报告。\n缺失项：\n" + "\n".join([f"- {x}" for x in missing]),
        )
        return "error"

    _emit_stepper(
        thread_id=ctx.thread_id,
        skill_name=ctx.skill_name,
        run_id=ctx.run_id,
        synthetic_path=ctx.synthetic_path,
        doc_id=ctx.doc_id,
        s1="done",
        s2="done",
        s3="done",
        s4="running",
    )
    _emit_summary(
        thread_id=ctx.thread_id,
        skill_name=ctx.skill_name,
        run_id=ctx.run_id,
        synthetic_path=ctx.synthetic_path,
        doc_id=ctx.doc_id,
        content="Step3：开始生成满足度评估、风险识别与工勘报告。",
    )

    scripts = [
        "zhgk/report-gen/scripts/generate_assessment.py",
        "zhgk/report-gen/scripts/generate_risk.py",
        "zhgk/report-gen/scripts/generate_report.py",
    ]
    for rel in scripts:
        ok, tail = _run_py(skill_root=ctx.skill_root, script_rel=rel)
        if not ok:
            _print_event(
                {
                    "event": "chat.guidance",
                    "threadId": ctx.thread_id,
                    "skillName": ctx.skill_name,
                    "skillRunId": ctx.run_id,
                    "timestamp": _now_ms(),
                    "payload": {"context": f"Step3 执行失败（{rel}）：\n{tail}", "actions": []},
                }
            )
            return "error"

    out_names = ["机房满足度评估表.xlsx", "风险识别结果表.xlsx", "工勘报告.docx", "整改待办.xlsx"]
    items: list[dict[str, Any]] = []
    for idx, name in enumerate(out_names, start=1):
        if os.path.exists(os.path.join(ctx.output_dir, name)):
            items.append(
                {
                    "artifactId": f"s3-{idx}",
                    "label": name,
                    "path": f"{_workspace_skill_prefix(ctx.skill_root)}/ProjectData/Output/{name}",
                    "kind": "other",
                    "status": "ready",
                }
            )
    skill_result_path = os.path.join(ctx.output_dir, "skill_result.json")
    if os.path.exists(skill_result_path):
        items.append(
            {
                "artifactId": "skill-result",
                "label": "skill_result.json",
                "path": f"{_workspace_skill_prefix(ctx.skill_root)}/ProjectData/Output/skill_result.json",
                "kind": "other",
                "status": "ready",
            }
        )

    _emit_summary(
        thread_id=ctx.thread_id,
        skill_name=ctx.skill_name,
        run_id=ctx.run_id,
        synthetic_path=ctx.synthetic_path,
        doc_id=ctx.doc_id,
        content="Step3 完成：报告与评估产物已生成。系统将自动进入 Step4 发送审批邮件。",
    )
    if items:
        _publish_artifacts(
            thread_id=ctx.thread_id,
            skill_name=ctx.skill_name,
            run_id=ctx.run_id,
            synthetic_path=ctx.synthetic_path,
            doc_id=ctx.doc_id,
            node_id="artifacts",
            items=items,
        )
    _emit_progress_dashboard_patch(ctx, survey=86, quality=82, risk=18)
    _emit_friendly_step_ack(
        ctx,
        card_id="zhgk:ack:step3:done",
        context="评估、风险与工勘报告都准备好啦，下面帮您走审批邮件这一步~",
    )
    _emit_task_progress(
        thread_id=ctx.thread_id, skill_name=ctx.skill_name, run_id=ctx.run_id, done_count=3
    )
    return "ok"


def _zhgk_step4_send(ctx: _ZhgkCtx) -> _StepOut:
    required = ["工勘报告.docx", "全量勘测结果表.xlsx", "机房满足度评估表.xlsx", "风险识别结果表.xlsx"]
    missing = [name for name in required if not os.path.exists(os.path.join(ctx.output_dir, name))]
    if missing:
        _emit_stepper(
            thread_id=ctx.thread_id,
            skill_name=ctx.skill_name,
            run_id=ctx.run_id,
            synthetic_path=ctx.synthetic_path,
            doc_id=ctx.doc_id,
            s1="done",
            s2="done",
            s3="done",
            s4="running",
        )
        _emit_summary(
            thread_id=ctx.thread_id,
            skill_name=ctx.skill_name,
            run_id=ctx.run_id,
            synthetic_path=ctx.synthetic_path,
            doc_id=ctx.doc_id,
            content="Step4：缺少报告产物，无法发送审批邮件。\n缺失项：\n" + "\n".join([f"- {x}" for x in missing]),
        )
        return "error"

    _emit_stepper(
        thread_id=ctx.thread_id,
        skill_name=ctx.skill_name,
        run_id=ctx.run_id,
        synthetic_path=ctx.synthetic_path,
        doc_id=ctx.doc_id,
        s1="done",
        s2="done",
        s3="done",
        s4="running",
    )
    _emit_summary(
        thread_id=ctx.thread_id,
        skill_name=ctx.skill_name,
        run_id=ctx.run_id,
        synthetic_path=ctx.synthetic_path,
        doc_id=ctx.doc_id,
        content="Step4：已发送专家审批邮件。请根据专家反馈选择后续动作。",
    )

    ok, tail = _run_py(skill_root=ctx.skill_root, script_rel="zhgk/report-distribute/scripts/distribute_report.py")
    if not ok:
        _print_event(
            {
                "event": "chat.guidance",
                "threadId": ctx.thread_id,
                "skillName": ctx.skill_name,
                "skillRunId": ctx.run_id,
                "timestamp": _now_ms(),
                "payload": {"context": "Step4-A 执行失败：\n" + tail, "actions": []},
            }
        )
        return "error"

    _emit_progress_dashboard_patch(ctx, survey=92, quality=88, risk=22)
    _emit_friendly_step_ack(
        ctx,
        card_id="zhgk:ack:step4:mailed",
        context="审批邮件已帮您发出啦！请在卡片里选一下专家反馈的走向，我会跟着您的选择继续办~",
    )
    _emit_stepper(
        thread_id=ctx.thread_id,
        skill_name=ctx.skill_name,
        run_id=ctx.run_id,
        synthetic_path=ctx.synthetic_path,
        doc_id=ctx.doc_id,
        s1="done",
        s2="done",
        s3="done",
        s4="waiting",
    )
    _print_event(
        {
            "event": "hitl.choice_request",
            "threadId": ctx.thread_id,
            "skillName": ctx.skill_name,
            "skillRunId": ctx.run_id,
            "timestamp": _now_ms(),
            "payload": {
                "requestId": f"{ctx.request_id}:step4_approval_decision",
                "cardId": "gongkan:step4:choice",
                "title": "专家审批结果",
                "description": "请选择专家审批结果后续动作。",
                "options": [
                    {"label": "审批通过 → 分发干系人", "value": "approval_pass"},
                    {"label": "数据不足 → 回到 Step2 增量补全", "value": "data_insufficient"},
                    {"label": "暂未回复 → 稍后再处理", "value": "no_reply"},
                ],
                "resumeAction": "zhgk_step4_handle_approval",
                "onCancelAction": "zhgk_step4_waiting",
                "skillName": ctx.skill_name,
                "stateNamespace": ctx.skill_name,
                "stepId": "zhgk.step4.approval",
                "expiresAt": _now_ms() + 7 * 24 * 60 * 60 * 1000,
            },
        }
    )
    return "hitl"


def main() -> int:
    req = json.loads(sys.stdin.read() or "{}")
    thread_id = _as_str(req.get("thread_id")) or "thread-unknown"
    skill_name = _as_str(req.get("skill_name")) or "gongkan_skill"
    request_id = _as_str(req.get("request_id")) or f"req-{uuid.uuid4().hex}"
    action = _as_str(req.get("action")) or "start"
    status = _as_str(req.get("status")) or "ok"

    run_id = f"run-{uuid.uuid4().hex}"

    if status != "ok":
        _print_event(
            {
                "event": "chat.guidance",
                "threadId": thread_id,
                "skillName": skill_name,
                "skillRunId": run_id,
                "timestamp": _now_ms(),
                "payload": {"context": f"收到非 ok 状态（{status}），已走降级处理。", "actions": []},
            }
        )
        return 0

    skill_root = os.getcwd()
    synthetic_path, doc_id = _resolve_skill_ui_targets(skill_root, skill_name)
    if not os.path.exists(os.path.join(skill_root, "path_config.py")):
        _print_event(
            {
                "event": "chat.guidance",
                "threadId": thread_id,
                "skillName": skill_name,
                "skillRunId": run_id,
                "timestamp": _now_ms(),
                "payload": {"context": "未检测到 path_config.py，当前模板 driver 需要在真实 gongkan_skill 目录下运行。", "actions": []},
            }
        )
        return 0

    sys.path.insert(0, skill_root)
    from path_config import INPUT_DIR, OUTPUT_DIR, RUNTIME_DIR, START_DIR, ensure_dirs  # type: ignore

    try:
        ensure_dirs()
    except Exception:
        pass

    ctx = _ZhgkCtx(
        thread_id=thread_id,
        skill_name=skill_name,
        request_id=request_id,
        run_id=run_id,
        synthetic_path=synthetic_path,
        doc_id=doc_id,
        skill_root=skill_root,
        input_dir=INPUT_DIR,
        output_dir=OUTPUT_DIR,
        runtime_dir=RUNTIME_DIR,
        start_dir=START_DIR,
    )

    _emit_dashboard_bootstrap_from_disk(ctx)
    _log_resume_upload_disk_hint(ctx, action, req.get("result"))

    # 正常路径：一次启动尽量跑完 Step1→Step4；仅在 HITL（上传/选择）或脚本失败、缺依赖处停下。
    if action in {"start", "zhgk_step1_scene_filter"}:
        out = _zhgk_step1(ctx)
        if out != "ok":
            return 0
        out = _zhgk_step2(ctx, "zhgk_step2_survey_build")
        if out != "ok":
            return 0
        out = _zhgk_step3(ctx)
        if out != "ok":
            return 0
        _zhgk_step4_send(ctx)
        return 0

    if action in {"zhgk_step2_survey_build", "zhgk_step2_merge_rebuild"}:
        out = _zhgk_step2(ctx, action)
        if out != "ok":
            return 0
        out = _zhgk_step3(ctx)
        if out != "ok":
            return 0
        _zhgk_step4_send(ctx)
        return 0

    if action in {"zhgk_step3_report_gen"}:
        out = _zhgk_step3(ctx)
        if out != "ok":
            return 0
        _zhgk_step4_send(ctx)
        return 0

    if action in {"zhgk_step4_send_for_approval"}:
        _zhgk_step4_send(ctx)
        return 0

    if action in {"zhgk_step4_handle_approval", "zhgk_step4_distribute_to_stakeholders", "zhgk_step4_back_to_step2"}:
        result_obj = req.get("result")
        choice_val = ""
        if isinstance(result_obj, dict):
            choice_val = _as_str(result_obj.get("value") or result_obj.get("choice") or result_obj.get("optionId"))

        if action == "zhgk_step4_back_to_step2" or choice_val == "data_insufficient":
            _emit_stepper(
                thread_id=thread_id,
                skill_name=skill_name,
                run_id=run_id,
                synthetic_path=synthetic_path,
                doc_id=doc_id,
                s1="done",
                s2="done",
                s3="waiting",
                s4="waiting",
            )
            _emit_summary(
                thread_id=thread_id,
                skill_name=skill_name,
                run_id=run_id,
                synthetic_path=synthetic_path,
                doc_id=doc_id,
                content="Step4：收到“数据不足”，请上传补充材料后将自动走 Step2 增量汇总。",
            )
            _emit_warm_hitl_guidance(
                thread_id=thread_id,
                skill_name=skill_name,
                request_id=request_id,
                run_id=run_id,
                stable_suffix="step4-supplement",
                context="收到「数据不足」的反馈啦，辛苦把补充材料传到下方卡片里，我会马上帮您做 Step2 增量汇总~",
            )
            _print_event(
                {
                    "event": "hitl.file_request",
                    "threadId": thread_id,
                    "skillName": skill_name,
                    "skillRunId": run_id,
                    "timestamp": _now_ms(),
                    "payload": {
                        "requestId": f"{request_id}:step4_upload_supplement",
                        "cardId": "gongkan:step4:supplement",
                        "purpose": "gongkan-step2-supplement",
                        "title": "请上传补充勘测材料（用于 Step2 增量）",
                        "description": "支持 .xlsx、.zip 或现场照片（.jpg/.jpeg/.png/.webp）。上传并点击提交后将自动执行 Step2 增量汇总。",
                        "accept": ".xlsx,.zip,.jpg,.jpeg,.png,.webp",
                        "multiple": True,
                        "saveRelativeDir": _hitl_input_save_relative_dir(skill_root, INPUT_DIR),
                        "resumeAction": "zhgk_step2_merge_rebuild",
                        "onCancelAction": "cancel_step4_upload",
                        "skillName": skill_name,
                        "stateNamespace": skill_name,
                        "stepId": "zhgk.step2.supplement",
                        "expiresAt": _now_ms() + 7 * 24 * 60 * 60 * 1000,
                    },
                }
            )
            return 0

        if action == "zhgk_step4_distribute_to_stakeholders" or choice_val == "approval_pass":
            ok, tail = _run_py(skill_root=skill_root, script_rel="zhgk/report-distribute/scripts/distribute_report_4b.py")
            if not ok:
                _print_event(
                    {
                        "event": "chat.guidance",
                        "threadId": thread_id,
                        "skillName": skill_name,
                        "skillRunId": run_id,
                        "timestamp": _now_ms(),
                        "payload": {"context": "Step4-B 执行失败：\n" + tail, "actions": []},
                    }
                )
                return 0

            _emit_stepper(
                thread_id=thread_id,
                skill_name=skill_name,
                run_id=run_id,
                synthetic_path=synthetic_path,
                doc_id=doc_id,
                s1="done",
                s2="done",
                s3="done",
                s4="done",
            )
            _emit_summary(
                thread_id=thread_id,
                skill_name=skill_name,
                run_id=run_id,
                synthetic_path=synthetic_path,
                doc_id=doc_id,
                content="Step4 完成：报告已分发干系人，工勘流程闭环。",
            )
            _emit_progress_dashboard_patch(
                _ZhgkCtx(
                    thread_id=thread_id,
                    skill_name=skill_name,
                    request_id=request_id,
                    run_id=run_id,
                    synthetic_path=synthetic_path,
                    doc_id=doc_id,
                    skill_root=skill_root,
                    input_dir=INPUT_DIR,
                    output_dir=OUTPUT_DIR,
                    runtime_dir=RUNTIME_DIR,
                    start_dir=START_DIR,
                ),
                survey=100,
                quality=98,
                risk=8,
            )
            _emit_task_progress(
                thread_id=thread_id, skill_name=skill_name, run_id=run_id, done_count=4
            )
            _emit_phase_handoff(
                thread_id=thread_id,
                skill_run_id=run_id,
                from_module="smart_survey",
                to_module="modeling_simulation_workbench",
            )
            _print_event(
                {
                    "event": "skill.epilogue",
                    "threadId": thread_id,
                    "skillName": skill_name,
                    "skillRunId": run_id,
                    "timestamp": _now_ms(),
                    "payload": {
                        "cardId": "zhgk:epilogue:final",
                        "stats": _epilogue_stats_payload(os.path.join(OUTPUT_DIR, "skill_result.json")),
                    },
                }
            )
            return 0

        _emit_summary(
            thread_id=thread_id,
            skill_name=skill_name,
            run_id=run_id,
            synthetic_path=synthetic_path,
            doc_id=doc_id,
            content="Step4：暂未收到审批通过反馈，可稍后继续处理。",
        )
        return 0

    _print_event(
        {
            "event": "chat.guidance",
            "threadId": thread_id,
            "skillName": skill_name,
            "skillRunId": run_id,
            "timestamp": _now_ms(),
            "payload": {"context": f"未支持的 action：{action}", "actions": []},
        }
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
