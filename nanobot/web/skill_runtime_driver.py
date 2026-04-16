from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from nanobot.web.skills import get_skill_dir


async def run_skill_runtime_driver(
    *,
    skill_name: str,
    request: dict[str, Any],
    python_executable: str | None = None,
) -> list[dict[str, Any]]:
    """Run a skill's runtime driver as a subprocess and collect emitted event envelopes.

    Contract (minimal):
    - Skill provides `<skill_dir>/runtime/driver.py`
    - Platform passes a JSON request to stdin
    - Skill prints one JSON object per line to stdout (each is an event envelope)
    """
    skill_dir = get_skill_dir(skill_name)
    driver = (skill_dir / "runtime" / "driver.py").resolve()
    if not driver.is_file():
        raise FileNotFoundError(f"skill runtime driver not found: {driver}")

    exe = python_executable or sys.executable
    proc = await asyncio.create_subprocess_exec(
        exe,
        str(driver),
        cwd=str(skill_dir),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    assert proc.stdin is not None
    assert proc.stdout is not None
    assert proc.stderr is not None

    payload = json.dumps(request, ensure_ascii=False).encode("utf-8")
    stdout_b, stderr_b = await proc.communicate(input=payload)
    if proc.returncode != 0:
        err = stderr_b.decode("utf-8", errors="ignore").strip()
        raise RuntimeError(f"skill driver failed (exit={proc.returncode}): {err}")

    out: list[dict[str, Any]] = []
    text = stdout_b.decode("utf-8", errors="ignore")
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            out.append(obj)
    return out

