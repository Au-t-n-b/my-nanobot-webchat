from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from nanobot.web.skills import get_skill_dir


def _driver_path(skill_dir: Path) -> Path:
    return (skill_dir / "runtime" / "driver.py").resolve()


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
    driver = _driver_path(skill_dir)
    if not driver.is_file():
        # Dashboard tab label may humanize ``gongkan_skill`` → "Gongkan Skill"; callers can
        # mistakenly send spaces. ``get_skill_dir`` already maps that to the real folder when
        # it exists. If the slug is still wrong (e.g. template says ``gongkan_skill`` but disk
        # folder is ``zhgk``), try common aliases before failing.
        resolved = skill_dir.resolve()
        for alt in ("zhgk", "gongkan_skill"):
            if alt == resolved.name:
                continue
            try:
                d = get_skill_dir(alt)
            except ValueError:
                continue
            p = _driver_path(d)
            if p.is_file():
                skill_dir = d.resolve()
                driver = p
                break
    if not driver.is_file():
        raise FileNotFoundError(f"skill runtime driver not found: {driver}")

    canonical = skill_dir.name
    stdin_request = dict(request)
    stdin_request["skill_name"] = canonical

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

    payload = json.dumps(stdin_request, ensure_ascii=False).encode("utf-8")
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

