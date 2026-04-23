"""兼容占位：冷启动已改为「主 Agent + project_guide/SKILL.md」，不再由本 driver 发引导。

若仍有旧版 UI 调用 ``skill_runtime_start``，本进程无 stdout 事件正常退出，resume_runner 仍返回 ok。
"""
from __future__ import annotations

import json
import sys


def main() -> int:
    try:
        json.loads(sys.stdin.read() or "{}")
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
