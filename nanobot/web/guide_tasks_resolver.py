"""Resolve the **current phase** ``guide_tasks.json`` and build a
``{phrase -> chat_card_intent payload}`` index for the chat fast-path.

Design constraints (mirror the project_guide driver):
- **Read-only, never raise**: any I/O / parse error returns ``None`` so the
  fast-path falls through to existing NL heuristics.
- **No template imports**: only depends on ``nanobot.web.skills.get_skill_dir``
  (name normalization) and ``nanobot.web.task_progress.task_progress_file_path``.
- **Current-phase scope**: the current phase is computed exactly like the
  driver — first phase whose tasks aren't all completed. NL phrases for any
  *other* phase MUST NOT trigger here, to avoid users skipping ahead.
"""

from __future__ import annotations

import json
import unicodedata
from pathlib import Path
from typing import Any

from nanobot.web.skills import get_skill_dir, get_skills_root
from nanobot.web.task_progress import task_progress_file_path


PROJECT_GUIDE_SKILL_NAME = "project_guide"


def _norm_phrase(s: Any) -> str:
    """Normalize a user-typed phrase for exact matching: NFKC + strip + collapse internal whitespace."""
    if s is None:
        return ""
    raw = str(s)
    nfkc = unicodedata.normalize("NFKC", raw)
    return "".join(nfkc.split())


def _read_json(path: Path) -> Any | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except Exception:
        return None


def _phase_completed(progress_entry: Any) -> bool:
    if not isinstance(progress_entry, dict):
        return False
    tasks = progress_entry.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        return False
    for t in tasks:
        if not isinstance(t, dict):
            return False
        if not bool(t.get("completed")):
            return False
    return True


def _compute_order_cur(phases: list[dict[str, Any]], task_progress: dict[str, Any] | None) -> int:
    """Mirror of phase_rules.compute_order_cur (first incomplete by order)."""
    by_module: dict[str, dict[str, Any]] = {}
    progress = (task_progress or {}).get("progress") if isinstance(task_progress, dict) else None
    if isinstance(progress, list):
        for entry in progress:
            if not isinstance(entry, dict):
                continue
            mid = entry.get("moduleId")
            if isinstance(mid, str):
                by_module[mid.strip()] = entry
    for p in phases:
        mid = str(p.get("moduleId") or "").strip()
        entry = by_module.get(mid)
        if not entry or not _phase_completed(entry):
            order = p.get("order")
            return int(order) if isinstance(order, int) else 0
    return len(phases)


def _load_phases() -> list[dict[str, Any]]:
    """Read ``<skills_root>/project_guide/data/phases.json`` and return the sorted phases list."""
    try:
        guide_dir = get_skill_dir(PROJECT_GUIDE_SKILL_NAME)
    except Exception:
        guide_dir = get_skills_root() / PROJECT_GUIDE_SKILL_NAME
    doc = _read_json(guide_dir / "data" / "phases.json")
    if not isinstance(doc, dict):
        return []
    items = doc.get("phases")
    if not isinstance(items, list):
        return []
    cleaned: list[dict[str, Any]] = []
    for raw in items:
        if not isinstance(raw, dict):
            continue
        order = raw.get("order")
        skill_dir = raw.get("skillDir")
        module_id = raw.get("moduleId")
        if not isinstance(order, int):
            continue
        if not isinstance(skill_dir, str) or not skill_dir.strip():
            continue
        if not isinstance(module_id, str) or not module_id.strip():
            continue
        cleaned.append(
            {
                "order": order,
                "skillDir": skill_dir.strip(),
                "moduleId": module_id.strip(),
                "displayName": str(raw.get("displayName") or "").strip(),
            }
        )
    cleaned.sort(key=lambda p: p["order"])
    return cleaned


def _load_task_progress() -> dict[str, Any] | None:
    try:
        path = task_progress_file_path()
    except Exception:
        return None
    return _read_json(path)


def _load_guide_tasks_for_skill(skill_dir_name: str) -> dict[str, Any] | None:
    try:
        skill_dir = get_skill_dir(skill_dir_name)
    except Exception:
        return None
    doc = _read_json(skill_dir / "data" / "guide_tasks.json")
    if not isinstance(doc, dict):
        return None
    tasks = doc.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        return None
    return doc


def _wrap_chat_card_intent(skill_runtime_start: dict[str, Any]) -> dict[str, Any]:
    """Build a fast-path ``chat_card_intent`` envelope from a ``skillRuntimeStart`` dict."""
    skill_name = str(skill_runtime_start.get("skillName") or "").strip()
    action = str(skill_runtime_start.get("action") or "").strip()
    request_id = str(skill_runtime_start.get("requestId") or "").strip()
    if not skill_name or not action:
        return {}
    payload = {
        "type": "skill_runtime_start",
        "skillName": skill_name,
        "requestId": request_id or f"req-start-{skill_name}",
        "action": action,
    }
    return {
        "type": "chat_card_intent",
        "verb": "skill_runtime_start",
        "payload": payload,
    }


def resolve_current_phase_guide_tasks() -> dict[str, Any] | None:
    """Return ``{"skillDir", "moduleId", "phrase_index"}`` for the current phase, or ``None``.

    ``phrase_index`` is a dict mapping each normalized trigger / alias to the
    fully-formed ``chat_card_intent`` envelope. Placeholder tasks are skipped.
    Any I/O failure returns ``None``.
    """
    phases = _load_phases()
    if not phases:
        return None
    progress = _load_task_progress()
    order_cur = _compute_order_cur(phases, progress)
    if order_cur < 0 or order_cur >= len(phases):
        return None
    cur = phases[order_cur]
    skill_dir = cur["skillDir"]
    guide = _load_guide_tasks_for_skill(skill_dir)
    if guide is None:
        return None
    raw_tasks = guide.get("tasks")
    if not isinstance(raw_tasks, list):
        return None

    phrase_index: dict[str, dict[str, Any]] = {}
    for raw in raw_tasks:
        if not isinstance(raw, dict):
            continue
        if bool(raw.get("placeholder")):
            continue
        srs = raw.get("skillRuntimeStart")
        if not isinstance(srs, dict):
            continue
        intent = _wrap_chat_card_intent(srs)
        if not intent:
            continue
        phrases: list[str] = []
        trigger = raw.get("trigger")
        if isinstance(trigger, str) and trigger.strip():
            phrases.append(trigger)
        aliases = raw.get("aliases")
        if isinstance(aliases, list):
            for a in aliases:
                if isinstance(a, str) and a.strip():
                    phrases.append(a)
        for p in phrases:
            key = _norm_phrase(p)
            if key and key not in phrase_index:
                phrase_index[key] = intent

    if not phrase_index:
        return None
    return {
        "skillDir": skill_dir,
        "moduleId": cur["moduleId"],
        "phrase_index": phrase_index,
    }


def match_phrase_to_intent(text: str) -> dict[str, Any] | None:
    """Single-shot helper for the chat fast-path.

    Returns the chat_card_intent envelope if ``text`` (after normalization) matches
    a current-phase trigger / alias; otherwise ``None``. Never raises.
    """
    try:
        idx = resolve_current_phase_guide_tasks()
    except Exception:
        return None
    if not idx:
        return None
    key = _norm_phrase(text)
    if not key:
        return None
    return idx.get("phrase_index", {}).get(key)


__all__ = [
    "PROJECT_GUIDE_SKILL_NAME",
    "resolve_current_phase_guide_tasks",
    "match_phrase_to_intent",
]
