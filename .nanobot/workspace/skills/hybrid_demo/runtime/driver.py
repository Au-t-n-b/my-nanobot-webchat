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

    if action not in {"start"}:
        _print_event(
            {
                "event": "chat.guidance",
                "threadId": thread_id,
                "skillName": skill_name,
                "skillRunId": run_id,
                "timestamp": _now_ms(),
                "payload": {
                    "context": f"hybrid_demo 未识别 action={action}，仅支持 start。",
                    "actions": [],
                    "cardId": "hybrid_demo:unknown_action",
                },
            }
        )
        return 0

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
                            "content": "主流程已启动：即将委托受控 Agent 子任务读取 skill_result.json 并生成摘要…",
                        },
                    }
                ],
            },
        }
    )

    # 2) 委托受控 Agent 子任务：读取 workspace 内文件并总结，然后回填同一节点
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
                    "请在当前技能工作区内使用工具读取事实并输出简短中文摘要（<=200字）：\n"
                    f"- 文件：{result_path.as_posix()}\n"
                    "要求：不要编造未读到的字段。"
                ),
                "allowedTools": ["read_file", "list_dir"],
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

