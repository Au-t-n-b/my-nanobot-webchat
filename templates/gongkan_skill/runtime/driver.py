from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import uuid
from typing import Any


def _now_ms() -> int:
    return int(time.time() * 1000)


def _print_event(evt: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(evt, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _as_str(v: Any) -> str:
    return str(v or "").strip()


def _read_json(path: str) -> dict[str, Any] | None:
    try:
        with open(path, "r", encoding="utf-8") as f:
            obj = json.load(f)
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


def _list_dir(path: str) -> list[str]:
    try:
        return sorted(os.listdir(path))
    except Exception:
        return []


def _detect_step1_inputs(input_dir: str) -> dict[str, Any]:
    files = _list_dir(input_dir)
    boq = next((f for f in files if f.lower().endswith(".xlsx") and "boq" in f.lower()), "")
    preset = "勘测信息预置集.docx" if "勘测信息预置集.docx" in files else ""
    missing: list[str] = []
    if not boq:
        missing.append("BOQ_xxx.xlsx（文件名需包含“BOQ”）")
    if not preset:
        missing.append("勘测信息预置集.docx")
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
    _print_event(
        {
            "event": "artifact.publish",
            "threadId": thread_id,
            "skillName": skill_name,
            "skillRunId": run_id,
            "timestamp": _now_ms(),
            "payload": {"syntheticPath": synthetic_path, "docId": doc_id, "artifactsNodeId": node_id, "items": items},
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


def main() -> int:
    req = json.loads(sys.stdin.read() or "{}")
    thread_id = _as_str(req.get("thread_id")) or "thread-unknown"
    skill_name = _as_str(req.get("skill_name")) or "gongkan_skill"
    request_id = _as_str(req.get("request_id")) or f"req-{uuid.uuid4().hex}"
    action = _as_str(req.get("action")) or "start"
    status = _as_str(req.get("status")) or "ok"

    synthetic_path = "skill-ui://SduiView?dataFile=skills/gongkan_skill/data/dashboard.json"
    doc_id = "dashboard:smart-survey-workbench"
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

    # ---- Step1 ----
    if action in {"start", "zhgk_step1_scene_filter"}:
        missing_start = [
            f
            for f in ["勘测问题底表.xlsx", "评估项底表.xlsx", "工勘常见高风险库.xlsx"]
            if not os.path.exists(os.path.join(START_DIR, f))
        ]
        if missing_start:
            _emit_stepper(
                thread_id=thread_id,
                skill_name=skill_name,
                run_id=run_id,
                synthetic_path=synthetic_path,
                doc_id=doc_id,
                s1="running",
                s2="waiting",
                s3="waiting",
                s4="waiting",
            )
            _emit_summary(
                thread_id=thread_id,
                skill_name=skill_name,
                run_id=run_id,
                synthetic_path=synthetic_path,
                doc_id=doc_id,
                content="Step1 环境缺失：ProjectData/Start/ 未就绪。\n" + "\n".join([f"- {x}" for x in missing_start]),
            )
            return 0

        detected = _detect_step1_inputs(INPUT_DIR)
        missing_inputs: list[str] = detected["missing"]
        if missing_inputs:
            _emit_stepper(
                thread_id=thread_id,
                skill_name=skill_name,
                run_id=run_id,
                synthetic_path=synthetic_path,
                doc_id=doc_id,
                s1="running",
                s2="waiting",
                s3="waiting",
                s4="waiting",
            )
            _emit_summary(
                thread_id=thread_id,
                skill_name=skill_name,
                run_id=run_id,
                synthetic_path=synthetic_path,
                doc_id=doc_id,
                content="Step1：检测到缺少必需输入件，请上传后系统将自动继续执行场景筛选。\n缺失项：\n"
                + "\n".join([f"- {x}" for x in missing_inputs]),
            )
            _print_event(
                {
                    "event": "hitl.file_request",
                    "threadId": thread_id,
                    "skillName": skill_name,
                    "skillRunId": run_id,
                    "timestamp": _now_ms(),
                    "payload": {
                        "requestId": f"{request_id}:step1_upload_inputs",
                        "cardId": "gongkan:step1:file",
                        "purpose": "gongkan-step1-inputs",
                        "title": "请上传智慧工勘 Step1 必需输入件",
                        "description": "缺失项：\n" + "\n".join([f"- {x}" for x in missing_inputs]),
                        "accept": ".xlsx,.docx",
                        "multiple": True,
                        "saveRelativeDir": "skills/gongkan_skill/ProjectData/Input",
                        "resumeAction": "zhgk_step1_scene_filter",
                        "onCancelAction": "cancel_step1_upload",
                        "skillName": skill_name,
                        "stateNamespace": skill_name,
                        "stepId": "zhgk.step1.inputs",
                        "expiresAt": _now_ms() + 30 * 60 * 1000,
                    },
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
            s2="running",
            s3="waiting",
            s4="waiting",
        )
        _emit_summary(
            thread_id=thread_id,
            skill_name=skill_name,
            run_id=run_id,
            synthetic_path=synthetic_path,
            doc_id=doc_id,
            content="Step1：输入件齐备，开始执行场景筛选与底表过滤（scene_filter.py）。",
        )

        ok, tail = _run_py(skill_root=skill_root, script_rel="zhgk/scene-filter/scripts/scene_filter.py")
        if not ok:
            _print_event(
                {
                    "event": "chat.guidance",
                    "threadId": thread_id,
                    "skillName": skill_name,
                    "skillRunId": run_id,
                    "timestamp": _now_ms(),
                    "payload": {"context": "Step1 执行失败：\n" + tail, "actions": []},
                }
            )
            return 0

        skill_result_path = os.path.join(OUTPUT_DIR, "skill_result.json")
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
            content="\n".join(lines),
        )

        uploaded_items = [
            {
                "artifactId": f"input-{i}",
                "label": name,
                "path": f"workspace/skills/gongkan_skill/ProjectData/Input/{name}",
                "kind": "other",
                "status": "ready",
            }
            for i, name in enumerate(_list_dir(INPUT_DIR), start=1)
        ]
        if uploaded_items:
            _publish_artifacts(
                thread_id=thread_id,
                skill_name=skill_name,
                run_id=run_id,
                synthetic_path=synthetic_path,
                doc_id=doc_id,
                node_id="uploaded-files",
                items=uploaded_items,
            )

        runtime_items = [
            {
                "artifactId": f"runtime-{i}",
                "label": name,
                "path": f"workspace/skills/gongkan_skill/ProjectData/RunTime/{name}",
                "kind": "other",
                "status": "ready",
            }
            for i, name in enumerate(_list_dir(RUNTIME_DIR), start=1)
            if name.lower().endswith((".xlsx", ".json"))
        ]
        if os.path.exists(skill_result_path):
            runtime_items.append(
                {
                    "artifactId": "skill-result",
                    "label": "skill_result.json",
                    "path": "workspace/skills/gongkan_skill/ProjectData/Output/skill_result.json",
                    "kind": "other",
                    "status": "ready",
                }
            )
        if runtime_items:
            _publish_artifacts(
                thread_id=thread_id,
                skill_name=skill_name,
                run_id=run_id,
                synthetic_path=synthetic_path,
                doc_id=doc_id,
                node_id="artifacts",
                items=runtime_items,
            )

        return 0

    # ---- Step2 ----
    if action in {"zhgk_step2_survey_build", "zhgk_step2_merge_rebuild"}:
        # Step2 prerequisites
        need = [
            ("RunTime/勘测问题底表_过滤.xlsx", os.path.join(RUNTIME_DIR, "勘测问题底表_过滤.xlsx")),
            ("Input/勘测结果.xlsx", os.path.join(INPUT_DIR, "勘测结果.xlsx")),
        ]
        missing = [label for label, path in need if not os.path.exists(path)]
        if missing:
            _emit_stepper(
                thread_id=thread_id,
                skill_name=skill_name,
                run_id=run_id,
                synthetic_path=synthetic_path,
                doc_id=doc_id,
                s1="done",
                s2="done",
                s3="running",
                s4="waiting",
            )
            _emit_summary(
                thread_id=thread_id,
                skill_name=skill_name,
                run_id=run_id,
                synthetic_path=synthetic_path,
                doc_id=doc_id,
                content="Step2：缺少必要输入，上传后将自动继续执行勘测汇总。\n缺失项：\n"
                + "\n".join([f"- {x}" for x in missing]),
            )
            _print_event(
                {
                    "event": "hitl.file_request",
                    "threadId": thread_id,
                    "skillName": skill_name,
                    "skillRunId": run_id,
                    "timestamp": _now_ms(),
                    "payload": {
                        "requestId": f"{request_id}:step2_upload_inputs",
                        "cardId": "gongkan:step2:file",
                        "purpose": "gongkan-step2-inputs",
                        "title": "请上传智慧工勘 Step2 勘测汇总所需文件",
                        "description": "缺失项：\n" + "\n".join([f"- {x}" for x in missing]),
                        "accept": ".xlsx,.zip,.jpg,.jpeg,.png,.webp",
                        "multiple": True,
                        "saveRelativeDir": "skills/gongkan_skill/ProjectData/Input",
                        "resumeAction": "zhgk_step2_survey_build",
                        "onCancelAction": "cancel_step2_upload",
                        "skillName": skill_name,
                        "stateNamespace": skill_name,
                        "stepId": "zhgk.step2.inputs",
                        "expiresAt": _now_ms() + 45 * 60 * 1000,
                    },
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
            s3="running",
            s4="waiting",
        )
        _emit_summary(
            thread_id=thread_id,
            skill_name=skill_name,
            run_id=run_id,
            synthetic_path=synthetic_path,
            doc_id=doc_id,
            content="Step2：开始生成全量勘测结果表与三类待办表。",
        )

        script_rel = (
            "zhgk/survey-build/scripts/merge_and_rebuild.py"
            if action == "zhgk_step2_merge_rebuild"
            else "zhgk/survey-build/scripts/generate_survey_table.py"
        )
        ok, tail = _run_py(skill_root=skill_root, script_rel=script_rel)
        if not ok:
            _print_event(
                {
                    "event": "chat.guidance",
                    "threadId": thread_id,
                    "skillName": skill_name,
                    "skillRunId": run_id,
                    "timestamp": _now_ms(),
                    "payload": {"context": "Step2 执行失败：\n" + tail, "actions": []},
                }
            )
            return 0

        # Summarize from skill_result.json (事实源)
        skill_result_path = os.path.join(OUTPUT_DIR, "skill_result.json")
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
            thread_id=thread_id,
            skill_name=skill_name,
            run_id=run_id,
            synthetic_path=synthetic_path,
            doc_id=doc_id,
            s1="done",
            s2="done",
            s3="done",
            s4="waiting",
        )
        _emit_summary(
            thread_id=thread_id,
            skill_name=skill_name,
            run_id=run_id,
            synthetic_path=synthetic_path,
            doc_id=doc_id,
            content="Step2 完成。\n"
            + f"全量勘测项：{filled}/{total}\n"
            + ("待办分类：\n" + "\n".join(todo_lines) if todo_lines else ""),
        )

        uploaded_items = [
            {
                "artifactId": f"input-{i}",
                "label": name,
                "path": f"workspace/skills/gongkan_skill/ProjectData/Input/{name}",
                "kind": "other",
                "status": "ready",
            }
            for i, name in enumerate(_list_dir(INPUT_DIR), start=1)
        ]
        if uploaded_items:
            _publish_artifacts(
                thread_id=thread_id,
                skill_name=skill_name,
                run_id=run_id,
                synthetic_path=synthetic_path,
                doc_id=doc_id,
                node_id="uploaded-files",
                items=uploaded_items,
            )

        # Output artifacts
        output_files = [
            "全量勘测结果表.xlsx",
            "待客户确认勘测项.xlsx",
            "待拍摄图片项.xlsx",
            "待补充勘测项.xlsx",
        ]
        out_items: list[dict[str, Any]] = []
        for idx, name in enumerate(output_files, start=1):
            if os.path.exists(os.path.join(OUTPUT_DIR, name)):
                out_items.append(
                    {
                        "artifactId": f"out-{idx}",
                        "label": name,
                        "path": f"workspace/skills/gongkan_skill/ProjectData/Output/{name}",
                        "kind": "other",
                        "status": "ready",
                    }
                )
        if os.path.exists(skill_result_path):
            out_items.append(
                {
                    "artifactId": "skill-result",
                    "label": "skill_result.json",
                    "path": "workspace/skills/gongkan_skill/ProjectData/Output/skill_result.json",
                    "kind": "other",
                    "status": "ready",
                }
            )
        if out_items:
            _publish_artifacts(
                thread_id=thread_id,
                skill_name=skill_name,
                run_id=run_id,
                synthetic_path=synthetic_path,
                doc_id=doc_id,
                node_id="artifacts",
                items=out_items,
            )

        return 0

    # ---- Step3 ----
    if action in {"zhgk_step3_report_gen"}:
        prereq = [
            ("Output/全量勘测结果表.xlsx", os.path.join(OUTPUT_DIR, "全量勘测结果表.xlsx")),
            ("RunTime/评估项底表_过滤.xlsx", os.path.join(RUNTIME_DIR, "评估项底表_过滤.xlsx")),
            ("RunTime/工勘常见高风险库_过滤.xlsx", os.path.join(RUNTIME_DIR, "工勘常见高风险库_过滤.xlsx")),
            ("RunTime/project_info.json", os.path.join(RUNTIME_DIR, "project_info.json")),
            ("Start/新版项目工勘报告模板.docx", os.path.join(START_DIR, "新版项目工勘报告模板.docx")),
        ]
        missing = [label for label, path in prereq if not os.path.exists(path)]
        if missing:
            _emit_stepper(
                thread_id=thread_id,
                skill_name=skill_name,
                run_id=run_id,
                synthetic_path=synthetic_path,
                doc_id=doc_id,
                s1="done",
                s2="done",
                s3="done",
                s4="running",
            )
            _emit_summary(
                thread_id=thread_id,
                skill_name=skill_name,
                run_id=run_id,
                synthetic_path=synthetic_path,
                doc_id=doc_id,
                content="Step3：缺少前置依赖，无法生成报告。\n缺失项：\n" + "\n".join([f"- {x}" for x in missing]),
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
            s4="running",
        )
        _emit_summary(
            thread_id=thread_id,
            skill_name=skill_name,
            run_id=run_id,
            synthetic_path=synthetic_path,
            doc_id=doc_id,
            content="Step3：开始生成满足度评估、风险识别与工勘报告。",
        )

        scripts = [
            "zhgk/report-gen/scripts/generate_assessment.py",
            "zhgk/report-gen/scripts/generate_risk.py",
            "zhgk/report-gen/scripts/generate_report.py",
        ]
        for rel in scripts:
            ok, tail = _run_py(skill_root=skill_root, script_rel=rel)
            if not ok:
                _print_event(
                    {
                        "event": "chat.guidance",
                        "threadId": thread_id,
                        "skillName": skill_name,
                        "skillRunId": run_id,
                        "timestamp": _now_ms(),
                        "payload": {"context": f"Step3 执行失败（{rel}）：\n{tail}", "actions": []},
                    }
                )
                return 0

        # Attach outputs (facts can be derived from skill_result.json but v1 only needs artifacts + progress)
        out_names = ["机房满足度评估表.xlsx", "风险识别结果表.xlsx", "工勘报告.docx", "整改待办.xlsx"]
        items: list[dict[str, Any]] = []
        for idx, name in enumerate(out_names, start=1):
            if os.path.exists(os.path.join(OUTPUT_DIR, name)):
                items.append(
                    {
                        "artifactId": f"s3-{idx}",
                        "label": name,
                        "path": f"workspace/skills/gongkan_skill/ProjectData/Output/{name}",
                        "kind": "other",
                        "status": "ready",
                    }
                )
        skill_result_path = os.path.join(OUTPUT_DIR, "skill_result.json")
        if os.path.exists(skill_result_path):
            items.append(
                {
                    "artifactId": "skill-result",
                    "label": "skill_result.json",
                    "path": "workspace/skills/gongkan_skill/ProjectData/Output/skill_result.json",
                    "kind": "other",
                    "status": "ready",
                }
            )

        _emit_summary(
            thread_id=thread_id,
            skill_name=skill_name,
            run_id=run_id,
            synthetic_path=synthetic_path,
            doc_id=doc_id,
            content="Step3 完成：报告与评估产物已生成，可进入 Step4 发送审批。",
        )
        if items:
            _publish_artifacts(
                thread_id=thread_id,
                skill_name=skill_name,
                run_id=run_id,
                synthetic_path=synthetic_path,
                doc_id=doc_id,
                node_id="artifacts",
                items=items,
            )
        return 0

    # ---- Step4 ----
    if action in {"zhgk_step4_send_for_approval"}:
        required = ["工勘报告.docx", "全量勘测结果表.xlsx", "机房满足度评估表.xlsx", "风险识别结果表.xlsx"]
        missing = [name for name in required if not os.path.exists(os.path.join(OUTPUT_DIR, name))]
        if missing:
            _emit_stepper(
                thread_id=thread_id,
                skill_name=skill_name,
                run_id=run_id,
                synthetic_path=synthetic_path,
                doc_id=doc_id,
                s1="done",
                s2="done",
                s3="done",
                s4="running",
            )
            _emit_summary(
                thread_id=thread_id,
                skill_name=skill_name,
                run_id=run_id,
                synthetic_path=synthetic_path,
                doc_id=doc_id,
                content="Step4：缺少报告产物，无法发送审批邮件。\n缺失项：\n" + "\n".join([f"- {x}" for x in missing]),
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
            s4="running",
        )
        _emit_summary(
            thread_id=thread_id,
            skill_name=skill_name,
            run_id=run_id,
            synthetic_path=synthetic_path,
            doc_id=doc_id,
            content="Step4：已发送专家审批邮件。请根据专家反馈选择后续动作。",
        )

        ok, tail = _run_py(skill_root=skill_root, script_rel="zhgk/report-distribute/scripts/distribute_report.py")
        if not ok:
            _print_event(
                {
                    "event": "chat.guidance",
                    "threadId": thread_id,
                    "skillName": skill_name,
                    "skillRunId": run_id,
                    "timestamp": _now_ms(),
                    "payload": {"context": "Step4-A 执行失败：\n" + tail, "actions": []},
                }
            )
            return 0

        _print_event(
            {
                "event": "hitl.choice_request",
                "threadId": thread_id,
                "skillName": skill_name,
                "skillRunId": run_id,
                "timestamp": _now_ms(),
                "payload": {
                    "requestId": f"{request_id}:step4_approval_decision",
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
                    "skillName": skill_name,
                    "stateNamespace": skill_name,
                    "stepId": "zhgk.step4.approval",
                    "expiresAt": _now_ms() + 7 * 24 * 60 * 60 * 1000,
                },
            }
        )
        return 0

    if action in {"zhgk_step4_handle_approval", "zhgk_step4_distribute_to_stakeholders", "zhgk_step4_back_to_step2"}:
        # Read choice result from platform result payload (skill_runtime_result.result)
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
                s3="running",
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
                        "accept": ".xlsx,.zip,.jpg,.jpeg,.png,.webp",
                        "multiple": True,
                        "saveRelativeDir": "skills/gongkan_skill/ProjectData/Input",
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
            return 0

        # no_reply / waiting
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

