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
    doc_id = "dashboard:stage-starter-external-web"
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

    _print_event(
        {
            "threadId": thread_id,
            "skillName": skill_name,
            "skillRunId": run_id,
            "event": "chat.guidance",
            "payload": {
                "content": (
                    "这是【阶段 Starter：外链 iframe】示例。\n"
                    "- 右侧大盘通过 EmbeddedWeb.src 嵌入外部系统页面。\n"
                    "- 外链如果被浏览器策略拦截（CSP / X-Frame-Options），需要外链系统侧放通。\n"
                    "- 本示例仅演示最小 dashboard.patch：更新提示文案。"
                )
            },
        }
    )

    ops = [
        _patch_merge(
            node_id="hint-md",
            node_type="Markdown",
            fields={
                "content": (
                    "外链 iframe 已尝试加载。\n\n"
                    f"- ts: `{_now_ms()}`\n"
                    f"- skill: `{skill_name}`\n"
                    "\n如果页面空白/报错，优先检查外链站点是否允许被嵌入。"
                )
            },
        )
    ]

    _print_event(
        {
            "threadId": thread_id,
            "skillName": skill_name,
            "skillRunId": run_id,
            "event": "dashboard.patch",
            "payload": {"syntheticPath": synthetic_path, "docId": doc_id, "ops": ops, "isPartial": True},
        }
    )


if __name__ == "__main__":
    main()

