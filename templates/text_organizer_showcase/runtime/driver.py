from __future__ import annotations

import json
import os
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


def _list_dir(path: str) -> list[str]:
    try:
        return sorted(os.listdir(path))
    except Exception:
        return []


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
                                {"id": "s1", "title": "收集材料", "status": s1},
                                {"id": "s2", "title": "选择整理目标", "status": s2},
                                {"id": "s3", "title": "确认并生成", "status": s3},
                                {"id": "s4", "title": "发布产物", "status": s4},
                            ],
                        },
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


def _emit_task_progress(done: int, total: int) -> None:
    # Minimal payload shape; backend normalizes it anyway.
    _print_event(
        {
            "event": "task_progress.sync",
            "threadId": "t",
            "skillName": "text_organizer_showcase",
            "skillRunId": f"run-{uuid.uuid4().hex}",
            "timestamp": _now_ms(),
            "payload": {
                "schemaVersion": 1,
                "updatedAt": _now_ms(),
                "modules": [
                    {
                        "moduleId": "text_organizer_showcase",
                        "moduleName": "文本内容整理（演示）",
                        "updatedAt": _now_ms(),
                        "tasks": [
                            {"name": "collect_inputs", "displayName": "收集材料", "completed": done >= 1},
                            {"name": "choose_format", "displayName": "选择目标", "completed": done >= 2},
                            {"name": "confirm_run", "displayName": "确认生成", "completed": done >= 3},
                            {"name": "publish", "displayName": "发布产物", "completed": done >= 4},
                        ],
                    }
                ],
                "overall": {"doneCount": done, "totalCount": total},
            },
        }
    )


def _read_choice_value(result_obj: Any) -> str:
    if not isinstance(result_obj, dict):
        return ""
    return _as_str(result_obj.get("value") or result_obj.get("choice") or result_obj.get("optionId") or result_obj.get("selected"))


def main() -> int:
    req = json.loads(sys.stdin.read() or "{}")
    thread_id = _as_str(req.get("thread_id")) or "thread-unknown"
    skill_name = _as_str(req.get("skill_name")) or "text_organizer_showcase"
    request_id = _as_str(req.get("request_id")) or f"req-{uuid.uuid4().hex}"
    action = _as_str(req.get("action")) or "txo_step1_collect_inputs"
    status = _as_str(req.get("status")) or "ok"
    result_obj = req.get("result")

    synthetic_path = "skill-ui://SduiView?dataFile=skills/text_organizer_showcase/data/dashboard.json"
    doc_id = "dashboard:text-organizer-showcase"
    run_id = f"run-{uuid.uuid4().hex}"

    # Skill root expectation: invoked with cwd=<skill_dir>
    skill_root = os.getcwd()
    input_dir = os.path.join(skill_root, "ProjectData", "Input")
    output_dir = os.path.join(skill_root, "ProjectData", "Output")
    os.makedirs(input_dir, exist_ok=True)
    os.makedirs(output_dir, exist_ok=True)

    if status != "ok":
        _emit_stepper(
            thread_id=thread_id,
            skill_name=skill_name,
            run_id=run_id,
            synthetic_path=synthetic_path,
            doc_id=doc_id,
            s1="error",
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
            content=f"收到非 ok 状态（{status}），已停止在当前步骤。",
        )
        return 0

    if action == "txo_step1_collect_inputs":
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
        files = [f for f in _list_dir(input_dir) if not f.lower().endswith(".md")]
        if not files:
            _emit_summary(
                thread_id=thread_id,
                skill_name=skill_name,
                run_id=run_id,
                synthetic_path=synthetic_path,
                doc_id=doc_id,
                content="Step1：请上传待整理的文本材料（txt/md/pdf/docx/zip 等）。上传完成后会自动进入下一步。",
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
                        "cardId": "txo:step1:file",
                        "purpose": "text-organizer-inputs",
                        "title": "请上传待整理的文本材料",
                        "accept": ".txt,.md,.pdf,.docx,.zip",
                        "multiple": True,
                        "saveRelativeDir": "skills/text_organizer_showcase/ProjectData/Input",
                        "resumeAction": "txo_step2_choose_format",
                        "onCancelAction": "txo_step1_collect_inputs",
                        "skillName": skill_name,
                        "stateNamespace": skill_name,
                        "stepId": "txo.step1.inputs",
                        "expiresAt": _now_ms() + 30 * 60 * 1000,
                    },
                }
            )
            _emit_task_progress(0, 4)
            return 0

        uploaded_items = [
            {
                "artifactId": f"in-{i}",
                "label": name,
                "path": f"workspace/skills/text_organizer_showcase/ProjectData/Input/{name}",
                "kind": "other",
                "status": "ready",
            }
            for i, name in enumerate(files, start=1)
        ]
        _publish_artifacts(
            thread_id=thread_id,
            skill_name=skill_name,
            run_id=run_id,
            synthetic_path=synthetic_path,
            doc_id=doc_id,
            node_id="uploaded-files",
            items=uploaded_items,
        )
        _emit_summary(
            thread_id=thread_id,
            skill_name=skill_name,
            run_id=run_id,
            synthetic_path=synthetic_path,
            doc_id=doc_id,
            content=f"Step1：已收到 {len(files)} 份材料。下一步请选择整理目标。",
        )
        _emit_task_progress(1, 4)
        # Fallthrough to choice step by asking immediately
        action = "txo_step2_choose_format"

    if action == "txo_step2_choose_format":
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
            content="Step2：请选择你希望生成的整理结果类型。",
        )
        _print_event(
            {
                "event": "hitl.choice_request",
                "threadId": thread_id,
                "skillName": skill_name,
                "skillRunId": run_id,
                "timestamp": _now_ms(),
                "payload": {
                    "requestId": f"{request_id}:step2_choose_format",
                    "cardId": "txo:step2:choice",
                    "title": "请选择整理目标",
                    "options": [
                        {"label": "摘要（summary.md）", "value": "summary"},
                        {"label": "大纲（outline.md）", "value": "outline"},
                        {"label": "FAQ（faq.md）", "value": "faq"},
                        {"label": "行动项（action_items.md）", "value": "action_items"},
                    ],
                    "resumeAction": "txo_step3_confirm_and_run",
                    "onCancelAction": "txo_step2_choose_format",
                    "skillName": skill_name,
                    "stateNamespace": skill_name,
                    "stepId": "txo.step2.choice",
                    "expiresAt": _now_ms() + 30 * 60 * 1000,
                },
            }
        )
        _emit_task_progress(1, 4)
        return 0

    if action == "txo_step3_confirm_and_run":
        choice = _read_choice_value(result_obj)
        if not choice:
            # If platform didn't carry result (unexpected), ask again.
            _emit_summary(
                thread_id=thread_id,
                skill_name=skill_name,
                run_id=run_id,
                synthetic_path=synthetic_path,
                doc_id=doc_id,
                content="Step3：未收到选择结果，将重新询问整理目标。",
            )
            _print_event(
                {
                    "event": "hitl.choice_request",
                    "threadId": thread_id,
                    "skillName": skill_name,
                    "skillRunId": run_id,
                    "timestamp": _now_ms(),
                    "payload": {
                        "requestId": f"{request_id}:step2_choose_format_retry",
                        "title": "请选择整理目标",
                        "options": [{"label": "摘要", "value": "summary"}],
                        "resumeAction": "txo_step3_confirm_and_run",
                        "onCancelAction": "txo_step2_choose_format",
                        "skillName": skill_name,
                        "stateNamespace": skill_name,
                        "stepId": "txo.step2.choice",
                        "expiresAt": _now_ms() + 15 * 60 * 1000,
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
            content=f"Step3：你选择了「{choice}」。确认后将生成产物并发布到右侧大盘。",
        )
        _print_event(
            {
                "event": "hitl.confirm_request",
                "threadId": thread_id,
                "skillName": skill_name,
                "skillRunId": run_id,
                "timestamp": _now_ms(),
                "payload": {
                    "requestId": f"{request_id}:step3_confirm_run",
                    "cardId": "txo:step3:confirm",
                    "title": "确认开始生成？",
                    "confirmLabel": "开始生成",
                    "cancelLabel": "稍后",
                    "resumeAction": "txo_step4_publish",
                    "onCancelAction": "txo_step2_choose_format",
                    "skillName": skill_name,
                    "stateNamespace": skill_name,
                    "stepId": "txo.step3.confirm",
                    "expiresAt": _now_ms() + 30 * 60 * 1000,
                    # Carry choice forward (best-effort; platform result may also contain it)
                    "state": {"format": choice},
                },
            }
        )
        _emit_task_progress(2, 4)
        return 0

    if action == "txo_step4_publish":
        # Determine format from result/state
        fmt = ""
        if isinstance(result_obj, dict):
            fmt = _as_str(result_obj.get("format") or result_obj.get("value") or result_obj.get("choice"))
            st = result_obj.get("state")
            if not fmt and isinstance(st, dict):
                fmt = _as_str(st.get("format"))
        fmt = fmt or "summary"

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
            content=f"Step4：正在生成并发布产物（{fmt}）。",
        )

        out_name = {
            "summary": "summary.md",
            "outline": "outline.md",
            "faq": "faq.md",
            "action_items": "action_items.md",
        }.get(fmt, "summary.md")
        out_path = os.path.join(output_dir, out_name)
        # v1: deterministic placeholder content (no LLM dependency)
        content = "\n".join(
            [
                f"# {fmt}（演示产物）",
                "",
                "本文件用于展示平台的 `artifact.publish` 能力。",
                "",
                "## 输入材料",
                "\n".join([f"- {x}" for x in _list_dir(input_dir)]),
                "",
                "## 说明",
                "- v1 不接 LLM，保证闭环可跑；后续可替换为真实总结/抽取逻辑。",
                "",
            ]
        )
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(content)

        _publish_artifacts(
            thread_id=thread_id,
            skill_name=skill_name,
            run_id=run_id,
            synthetic_path=synthetic_path,
            doc_id=doc_id,
            node_id="artifacts",
            items=[
                {
                    "artifactId": f"out-{fmt}",
                    "label": out_name,
                    "path": f"workspace/skills/text_organizer_showcase/ProjectData/Output/{out_name}",
                    "kind": "md",
                    "status": "ready",
                }
            ],
        )
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
            content=f"完成：已生成并发布 `{out_name}`。",
        )
        _emit_task_progress(4, 4)
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

