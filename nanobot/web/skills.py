"""Skill discovery helpers for AGUI Phase 3."""

from __future__ import annotations

import io
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
import zipfile
from typing import Any

from nanobot.web.module_contract_schema import validate_module_contract

REMOTE_SKILL_METADATA_FILE = ".nanobot-remote-skill.json"


def get_skills_root() -> Path:
    """Return fixed skills root (test override allowed via env)."""
    override = os.environ.get("NANOBOT_AGUI_SKILLS_ROOT", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return (Path.home() / ".nanobot" / "workspace" / "skills").resolve()


def _normalize_skill_dir_key(name: str) -> str:
    """Fold UI/LLM variants (spaces vs underscores/dashes, case) for directory matching."""
    s = str(name or "").strip()
    s = re.sub(r"\s+", "_", s)
    s = s.replace("-", "_")
    return s.lower()


def _find_skill_child_dir(root: Path, requested: str) -> Path | None:
    """Return an existing ``<skills_root>/<child>/`` whose name matches ``requested`` under normalization."""
    if not requested.strip():
        return None
    want = _normalize_skill_dir_key(requested)
    try:
        children = list(root.iterdir())
    except OSError:
        return None
    for child in children:
        if not child.is_dir():
            continue
        if _normalize_skill_dir_key(child.name) == want:
            return child.resolve()
    return None


def get_skill_dir(skill_name: str) -> Path:
    target = str(skill_name or "").strip()
    if not target:
        raise ValueError("skill name is required")
    root = get_skills_root().resolve()
    root.mkdir(parents=True, exist_ok=True)
    matched = _find_skill_child_dir(root, target)
    if matched is not None:
        try:
            matched.relative_to(root)
        except ValueError as exc:
            raise ValueError("invalid skill name") from exc
        return matched
    candidate = (root / target).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError("invalid skill name") from exc
    return candidate


def skill_dir_keys_equivalent(a: str, b: str) -> bool:
    """True if two skill slug strings refer to the same ``skills/<name>/`` folder (case / space / ``_`` / ``-``)."""
    return _normalize_skill_dir_key(a) == _normalize_skill_dir_key(b)


def _parse_frontmatter_description(content: str) -> str:
    """Extract the ``description`` value from YAML frontmatter, or return ''."""
    if not content.startswith("---"):
        return ""
    match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
    if not match:
        return ""
    for line in match.group(1).splitlines():
        if line.startswith("description:"):
            return line[len("description:"):].strip().strip("\"'")
    return ""


def parse_skill_metadata(skill_dir: Path) -> dict[str, object]:
    skill_file = skill_dir / "SKILL.md"
    try:
        content = skill_file.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return {"name": skill_dir.name, "description": "", "version": "", "tags": []}

    metadata = {
        "name": skill_dir.name,
        "description": "",
        "version": "",
        "tags": [],
    }
    if content.startswith("---"):
        match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
        if match:
            for line in match.group(1).splitlines():
                field = re.match(r"^([A-Za-z0-9_]+)\s*:\s*(.+)$", line)
                if not field:
                    continue
                key = field.group(1).strip().lower()
                value = field.group(2).strip().strip("\"'")
                if key == "name" and value:
                    metadata["name"] = value
                elif key == "description":
                    metadata["description"] = value
                elif key == "version":
                    metadata["version"] = value
                elif key in {"tags", "tag"}:
                    metadata["tags"] = [part.strip() for part in value.strip("[]").split(",") if part.strip()]
    heading = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
    if heading and not str(metadata["name"]).strip():
        metadata["name"] = heading.group(1).strip()
    return metadata


def read_remote_skill_metadata(skill_dir: Path) -> dict[str, object] | None:
    metadata_file = skill_dir / REMOTE_SKILL_METADATA_FILE
    if not metadata_file.is_file():
        return None
    try:
        payload = json.loads(metadata_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def write_remote_skill_metadata(skill_dir: Path, payload: dict[str, object]) -> None:
    metadata_file = skill_dir / REMOTE_SKILL_METADATA_FILE
    metadata_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def skill_description(skill_dir: Path) -> str:
    return str(parse_skill_metadata(skill_dir).get("description") or "")


def skill_latest_modified_at(skill_dir: Path) -> str | None:
    latest = 0.0
    for path in skill_dir.rglob("*"):
        if path.is_file() and path.name != REMOTE_SKILL_METADATA_FILE:
            latest = max(latest, path.stat().st_mtime)
    if latest <= 0:
        return None
    return datetime.fromtimestamp(latest, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def build_skill_archive(skill_dir: Path) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(skill_dir.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(skill_dir).as_posix()
            if relative == REMOTE_SKILL_METADATA_FILE:
                continue
            zf.writestr(relative, path.read_bytes())
    return buffer.getvalue()


def list_skills() -> list[dict[str, object]]:
    """Scan ``<skills_root>/*/SKILL.md`` and return stable A->Z list."""
    root = get_skills_root()
    root.mkdir(parents=True, exist_ok=True)

    items: list[dict[str, object]] = []
    for child in root.iterdir():
        if not child.is_dir():
            continue
        skill_file = child / "SKILL.md"
        if not skill_file.is_file():
            continue
        st = skill_file.stat()
        try:
            content = skill_file.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            content = ""
        remote_meta = read_remote_skill_metadata(child) or {}
        source = str(remote_meta.get("source") or "local")
        items.append(
            {
                "name": child.name,
                "skillDir": str(child.resolve()),
                "skillFile": str(skill_file.resolve()),
                "mtimeMs": int(st.st_mtime * 1000),
                "source": source,
                "description": _parse_frontmatter_description(content),
                "remoteSkillId": str(remote_meta.get("remoteSkillId") or ""),
                "remoteTitle": str(remote_meta.get("remoteTitle") or ""),
                "organizationName": str(remote_meta.get("organizationName") or ""),
            }
        )

    items.sort(key=lambda it: str(it["name"]).lower())
    return items


def _module_registry_item_from_config(raw: dict[str, Any]) -> dict[str, object]:
    cfg = validate_module_contract(raw)
    module_id = str(cfg.get("moduleId") or "").strip()
    task_progress = cfg.get("taskProgress") if isinstance(cfg.get("taskProgress"), dict) else {}
    case_template = cfg.get("caseTemplate") if isinstance(cfg.get("caseTemplate"), dict) else {}
    label = (
        str(case_template.get("moduleTitle") or "").strip()
        or str(task_progress.get("moduleName") or "").strip()
        or module_id
    )
    description = (
        str(case_template.get("moduleGoal") or "").strip()
        or str(cfg.get("description") or "").strip()
    )
    task_names = task_progress.get("tasks")
    capabilities = cfg.get("capabilities") if isinstance(cfg.get("capabilities"), dict) else {}
    raw_show_stepper = capabilities.get("showWorkbenchModuleStepper")
    # 作业管理默认不占用工作台顶栏「流程进度」；显式写 true 可恢复
    if raw_show_stepper is None and module_id.replace("-", "_") == "job_management":
        show_workbench_module_stepper = False
    else:
        show_workbench_module_stepper = True if raw_show_stepper is None else bool(raw_show_stepper)
    return {
        "moduleId": module_id,
        "label": label,
        "description": description,
        "showWorkbenchModuleStepper": show_workbench_module_stepper,
        "taskProgress": {
            "moduleId": str(task_progress.get("moduleId") or module_id).strip() or module_id,
            "moduleName": str(task_progress.get("moduleName") or label).strip() or label,
            "tasks": [
                str(item).strip()
                for item in task_names
                if str(item).strip()
            ] if isinstance(task_names, list) else [],
        },
        "dashboard": {
            "docId": str(cfg.get("docId") or "").strip(),
            "dataFile": str(cfg.get("dataFile") or "").strip(),
        },
    }


def list_modules() -> list[dict[str, object]]:
    """Scan ``<skills_root>/*/module.json`` and return valid module registry items."""
    root = get_skills_root()
    root.mkdir(parents=True, exist_ok=True)

    items: list[dict[str, object]] = []
    for child in root.iterdir():
        if not child.is_dir():
            continue
        module_file = child / "module.json"
        if not module_file.is_file():
            continue
        try:
            raw = json.loads(module_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(raw, dict):
            continue
        try:
            items.append(_module_registry_item_from_config(raw))
        except ValueError:
            continue

    items.sort(key=lambda it: str(it["moduleId"]).lower())
    return items

