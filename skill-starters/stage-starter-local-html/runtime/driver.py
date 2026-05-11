from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any


def _now_ms() -> int:
    return int(time.time() * 1000)


def _print_event(envelope: dict[str, Any]) -> None:
    line = (json.dumps(envelope, ensure_ascii=False) + "\n").encode("utf-8", errors="replace")
    sys.stdout.buffer.write(line)
    sys.stdout.buffer.flush()


def _as_str(v: Any) -> str:
    return str(v or "").strip()


def _skill_root_from_req(req: dict[str, Any]) -> str:
    explicit = _as_str(req.get("skill_root"))
    if explicit:
        p = Path(explicit).resolve()
        return str(p.parent if p.name == "runtime" else p)
    return str(Path(__file__).resolve().parent.parent)


def _targets(skill_root: str) -> tuple[str, str, str]:
    """Return (skill_name, synthetic_path, doc_id)."""
    skill_name = os.path.basename(os.path.normpath(os.path.abspath(skill_root)))
    data_file = f"skills/{skill_name}/data/dashboard.json"
    synthetic_path = f"skill-ui://SduiView?dataFile={data_file}"
    doc_id = "dashboard:stage-starter-local-html"
    try:
        mod = json.loads((Path(skill_root) / "module.json").read_text(encoding="utf-8"))
        if isinstance(mod, dict):
            doc_id = _as_str(mod.get("docId")) or doc_id
    except Exception:
        pass
    return skill_name, synthetic_path, doc_id


def _patch_merge(*, node_id: str, node_type: str, fields: dict[str, Any]) -> dict[str, Any]:
    return {
        "op": "merge",
        "target": {"by": "id", "nodeId": node_id},
        "value": {"type": node_type, "id": node_id, **fields},
    }

def _stepper(status_s0: str, status_s1: str, status_s2: str) -> dict[str, Any]:
    return _patch_merge(
        node_id="stepper-main",
        node_type="Stepper",
        fields={
            "orientation": "horizontal",
            "steps": [
                {"id": "s0", "title": "初始化", "status": status_s0},
                {"id": "s1", "title": "工作台编辑", "status": status_s1},
                {"id": "s2", "title": "发布产物", "status": status_s2},
            ],
        },
    )


def main() -> None:
    req = json.loads(sys.stdin.read() or "{}")
    if not isinstance(req, dict):
        req = {}

    skill_root = _skill_root_from_req(req)
    skill_name, synthetic_path, doc_id = _targets(skill_root)
    thread_id = _as_str(req.get("threadId")) or "thread-unknown"
    run_id = _as_str(req.get("skillRunId")) or f"run-{_now_ms()}"

    intent = req.get("intent")
    if not isinstance(intent, dict):
        intent = {}
    verb = _as_str(intent.get("verb"))
    payload = intent.get("payload") if isinstance(intent.get("payload"), dict) else {}
    action = _as_str(payload.get("action")) or "start"

    _print_event(
        {
            "threadId": thread_id,
            "skillName": skill_name,
            "skillRunId": run_id,
            "event": "chat.guidance",
            "payload": {
                "content": (
                    "这是【阶段 Starter：本地 HTML 工作台】示例。\n"
                    "- 右侧大盘包含 Stepper + 指标 + EmbeddedWeb（同源 workbench.html）。\n"
                    "- 你可以点工作台里的按钮触发 `skill_web_intent`，平台会把它作为 intent 回传给本 driver。\n"
                    "- 本示例不会阻塞等待输入，仅演示 dashboard.patch 与 artifact.publish 的最小闭环。"
                )
            },
        }
    )

    # 根据 action 做最小状态机：start -> workbench_done -> publish
    ops: list[dict[str, Any]] = []
    artifacts: list[dict[str, Any]] = []

    if action in ("start", "skill_runtime_start") or verb in ("skill_runtime_start", ""):
        ops.extend(
            [
                _stepper("done", "running", "waiting"),
                _patch_merge("stat-progress", "Statistic", {"value": "30%"}),
                _patch_merge("stat-status", "Statistic", {"value": "editing"}),
                _patch_merge(
                    "workbench-web",
                    "EmbeddedWeb",
                    {"state": {"title": "本地 HTML 工作台 Starter", "hint": "在工作台内点击“完成编辑”按钮以继续。"}},
                ),
            ]
        )

    elif action == "workbench_done":
        ops.extend(
            [
                _stepper("done", "done", "running"),
                _patch_merge("stat-progress", "Statistic", {"value": "70%"}),
                _patch_merge("stat-status", "Statistic", {"value": "ready_to_publish"}),
            ]
        )

    elif action == "publish":
        ops.extend(
            [
                _stepper("done", "done", "done"),
                _patch_merge("stat-progress", "Statistic", {"value": "100%"}),
                _patch_merge("stat-status", "Statistic", {"value": "done"}),
            ]
        )
        artifacts = [
            {
                "artifactId": "example-report",
                "label": "阶段产物示例（Markdown）",
                "path": "workspace/skills/{}/runtime/example_output.md".format(skill_name),
                "kind": "other",
                "status": "ready",
            }
        ]

        # 写一个可预览的示例文件到本技能目录（被复制到 workspace 后可直接预览）。
        try:
            out_path = Path(skill_root) / "runtime" / "example_output.md"
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(
                "# 阶段产物示例\n\n这是由 starter driver 生成的示例产物。\n\n- action: publish\n- ts: {}\n".format(_now_ms()),
                encoding="utf-8",
            )
        except Exception:
            pass

        # 更新“已发布产物”计数
        ops.append(_patch_merge("stat-artifacts", "Statistic", {"value": 1}))

    else:
        # 未识别 action 时，轻量回显，避免同事调试时“无反馈”
        ops.append(_patch_merge("stat-status", "Statistic", {"value": f"unknown_action:{action or 'empty'}"}))

    if ops:
        _print_event(
            {
                "threadId": thread_id,
                "skillName": skill_name,
                "skillRunId": run_id,
                "event": "dashboard.patch",
                "payload": {
                    "syntheticPath": synthetic_path,
                    "docId": doc_id,
                    "ops": ops,
                    "isPartial": True,
                },
            }
        )

    if artifacts:
        _print_event(
            {
                "threadId": thread_id,
                "skillName": skill_name,
                "skillRunId": run_id,
                "event": "artifact.publish",
                "payload": {
                    "syntheticPath": synthetic_path,
                    "docId": doc_id,
                    "artifactsNodeId": "artifacts",
                    "items": artifacts,
                },
            }
        )


if __name__ == "__main__":
    main()

