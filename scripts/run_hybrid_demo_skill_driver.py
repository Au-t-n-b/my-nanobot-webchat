from __future__ import annotations

import asyncio
import os

from nanobot.web.skill_runtime_driver import run_skill_runtime_driver


async def main() -> None:
    # Point to repo-local .nanobot skill tree for quick manual tests.
    os.environ.setdefault(
        "NANOBOT_AGUI_SKILLS_ROOT",
        r"d:\code\nanobot\.nanobot\workspace\skills",
    )
    evts = await run_skill_runtime_driver(
        skill_name="hybrid_demo",
        request={
            "thread_id": "t-demo",
            "skill_name": "hybrid_demo",
            "request_id": "req-demo-hybrid",
            "action": "start",
            "status": "ok",
            "result": {},
        },
    )
    print("events:", len(evts))
    for e in evts:
        print("-", e.get("event"))


if __name__ == "__main__":
    asyncio.run(main())

