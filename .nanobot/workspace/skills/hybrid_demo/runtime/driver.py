from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any


def _now_ms() -> int:
    return int(time.time() * 1000)


def _print_event(evt: dict[str, Any]) -> None:
    line = (json.dumps(evt, ensure_ascii=False) + "\n").encode("utf-8", errors="replace")
    sys.stdout.buffer.write(line)
    sys.stdout.buffer.flush()


def _skill_root_from_driver_cwd() -> Path:
    # Platform runs driver with cwd=skill_dir
    return Path(os.getcwd()).resolve()


def _ensure_demo_files(skill_root: Path) -> Path:
    out_dir = skill_root / "ProjectData" / "Output"
    out_dir.mkdir(parents=True, exist_ok=True)
    p = out_dir / "skill_result.json"
    if not p.is_file():
        p.write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "skill_name": "hybrid_demo",
                    "demo": {
                        "scenario": "混合模式验证",
                        "note": "该文件由 driver 生成，供受控子任务 read_file 读取并总结。",
                    },
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    return p


def main() -> int:
    try:
        req = json.loads(sys.stdin.read() or "{}")
    except Exception:
        req = {}

    thread_id = str(req.get("thread_id") or req.get("threadId") or "").strip() or "thread-unknown"
    skill_name = str(req.get("skill_name") or req.get("skillName") or "").strip() or "hybrid_demo"
    request_id = str(req.get("request_id") or req.get("requestId") or "").strip() or "req-hybrid-demo"
    action = str(req.get("action") or "").strip() or "start"

    skill_root = _skill_root_from_driver_cwd()
    synthetic_path = "skill-ui://SduiView?dataFile=workspace/skills/hybrid_demo/data/dashboard.json"
    doc_id = "dashboard:hybrid-demo"
    run_id = f"{request_id}:{_now_ms()}"

    # Always ensure a readable demo artifact exists for hybrid subtask.
    result_path = _ensure_demo_files(skill_root)

    if action not in {"start", "analyze_upload"}:
        _print_event(
            {
                "event": "chat.guidance",
                "threadId": thread_id,
                "skillName": skill_name,
                "skillRunId": run_id,
                "timestamp": _now_ms(),
                "payload": {
                    "context": f"hybrid_demo 未识别 action={action}，仅支持 start/analyze_upload。",
                    "actions": [],
                    "cardId": "hybrid_demo:unknown_action",
                },
            }
        )
        return 0

    if action == "start":
        # Step 0: Ask user to upload a doc/docx for analysis.
        _print_event(
            {
                "event": "hitl.file_request",
                "threadId": thread_id,
                "skillName": skill_name,
                "skillRunId": run_id,
                "timestamp": _now_ms(),
                "payload": {
                    "requestId": f"{request_id}:upload_doc",
                    "cardId": "hybrid_demo:upload_doc",
                    "purpose": "hybrid-demo-doc",
                    "title": "请上传一个 .doc 或 .docx 文件（用于混合子任务分析）",
                    "description": "上传后将自动触发受控子任务读取并生成摘要，回填到右侧大盘。",
                    "accept": ".doc,.docx",
                    "multiple": False,
                    "mode": "replace",
                    "resumeAction": "analyze_upload",
                    "saveRelativeDir": "skills/hybrid_demo/ProjectData/Input",
                    "stepId": "hybrid_demo.step0.upload",
                },
            }
        )
        _print_event(
            {
                "event": "chat.guidance",
                "threadId": thread_id,
                "skillName": skill_name,
                "skillRunId": run_id,
                "timestamp": _now_ms(),
                "payload": {
                    "context": "请先上传 .doc/.docx 文件；上传完成后我会用混合子任务读取并生成摘要。",
                    "actions": [],
                    "cardId": "hybrid_demo:upload_prompt",
                },
            }
        )
        return 0

    # action == analyze_upload
    # Try to locate uploaded file name from resume payload; fall back to listing Input dir.
    raw_result = req.get("result")
    uploaded_name = ""
    if isinstance(raw_result, dict):
        files = raw_result.get("files")
        if isinstance(files, list) and files:
            first = files[0]
            if isinstance(first, dict):
                uploaded_name = str(first.get("name") or "").strip()
    input_dir = skill_root / "ProjectData" / "Input"
    doc_path = ""
    if uploaded_name:
        doc_path = str((input_dir / uploaded_name).resolve())
    else:
        try:
            for cand in sorted(input_dir.glob("*")):
                if cand.suffix.lower() in {".doc", ".docx"}:
                    doc_path = str(cand.resolve())
                    break
        except Exception:
            doc_path = ""

    # 1) 主流程先写一段提示到 dashboard
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
                        "value": {
                            "type": "Text",
                            "id": "summary-text",
                            "content": "已收到上传文件：即将委托受控 Agent 子任务读取 .doc/.docx 并生成摘要…",
                        },
                    }
                ],
            },
        }
    )

    # 2) 委托受控 Agent 子任务：提取 doc/docx 文本并总结，然后回填同一节点
    _print_event(
        {
            "event": "skill.agent_task_execute",
            "threadId": thread_id,
            "skillName": skill_name,
            "skillRunId": run_id,
            "timestamp": _now_ms(),
            "payload": {
                "parentRequestId": request_id,
                "taskId": f"{request_id}:hybrid_demo:summary",
                "stepId": "hybrid_demo.step1.summary",
                "goal": (
                    "你将收到一个上传的 Word 文件路径。请使用工具 `extract_doc_text` 提取其文本后，输出简短中文摘要（<=200字）。\n"
                    f"- Word 文件：{doc_path or '(未找到上传文件，请先 list_dir skills/hybrid_demo/ProjectData/Input)'}\n"
                    "要求：不要编造未提取到的内容。"
                ),
                "allowedTools": ["extract_doc_text", "list_dir"],
                "maxIterations": 4,
                "resultSchema": {"type": "string"},
                "syntheticPath": synthetic_path,
                "docId": doc_id,
                "summaryNodeId": "summary-text",
                "summaryNodeType": "Text"
            },
        }
    )

    # 3) 在聊天侧提示：右栏 summary-text 会被子任务覆盖为摘要文本
    _print_event(
        {
            "event": "chat.guidance",
            "threadId": thread_id,
            "skillName": skill_name,
            "skillRunId": run_id,
            "timestamp": _now_ms(),
            "payload": {
                "context": "已发起混合子任务：右侧大盘 summary-text 将更新为摘要；顶部不会被 hybrid: 进度污染。",
                "actions": [],
                "cardId": "hybrid_demo:started",
            },
        }
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

