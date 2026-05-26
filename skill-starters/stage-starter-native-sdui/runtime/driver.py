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
    skill_name = os.path.basename(os.path.normpath(os.path.abspath(skill_root)))
    data_file = f"skills/{skill_name}/data/dashboard.json"
    synthetic_path = f"skill-ui://SduiView?dataFile={data_file}"
    doc_id = "dashboard:stage-starter-native-sdui"
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
                    "这是【阶段 Starter：纯 SDUI】示例。\n"
                    "- 点击大盘按钮会通过 post_user_message 回传 intent（skill_runtime_resume）。\n"
                    "- driver 收到 action 后用 dashboard.patch 更新节点内容，并可 artifact.publish 发布产物。"
                )
            },
        }
    )

    ops: list[dict[str, Any]] = []
    artifacts: list[dict[str, Any]] = []

    if action == "apply_note":
        note = _as_str(payload.get("note"))
        ops.extend(
            [
                _patch_merge(
                    node_id="status-md",
                    node_type="Markdown",
                    fields={"content": f"已写入备注：\n\n```\n{note or '(空)'}\n```\n\n- ts: `{_now_ms()}`"},
                ),
                _patch_merge("stat-progress", "Statistic", {"value": "50%"}),
            ]
        )
    elif action == "publish":
        # 写一个可预览的示例文件
        try:
            out_path = Path(skill_root) / "runtime" / "example_output.md"
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(
                "# 纯 SDUI Starter 产物\n\n由 `publish` action 生成。\n\n- ts: {}\n".format(_now_ms()),
                encoding="utf-8",
            )
        except Exception:
            pass

        artifacts = [
            {
                "artifactId": "native-sdui-report",
                "label": "纯 SDUI 产物示例（Markdown）",
                "path": "workspace/skills/{}/runtime/example_output.md".format(skill_name),
                "kind": "other",
                "status": "ready",
            }
        ]
        ops.append(_patch_merge("stat-progress", "Statistic", {"value": "100%"}))
        ops.append(_patch_merge("status-md", "Markdown", {"content": "已发布示例产物。"}))
    else:
        ops.append(_patch_merge("status-md", "Markdown", {"content": f"当前 action：`{action}`（可点击按钮触发 apply_note/publish）"}))

    _print_event(
        {
            "threadId": thread_id,
            "skillName": skill_name,
            "skillRunId": run_id,
            "event": "dashboard.patch",
            "payload": {"syntheticPath": synthetic_path, "docId": doc_id, "ops": ops, "isPartial": True},
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

