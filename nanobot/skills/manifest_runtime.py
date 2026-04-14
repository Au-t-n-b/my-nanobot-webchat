"""Minimal runtime for declarative skill manifest HITL gates."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from nanobot.skills.manifest_schema import (
    ChoiceGateStep,
    FileGateStep,
    FixedActionStep,
    SkillManifest,
)
from nanobot.web.paths import normalize_file_query, resolve_file_target
from nanobot.web.skills import get_skills_root


def _default_workspace_root() -> Path:
    return get_skills_root().parent


def _resolve_manifest_file_target(raw_path: str, workspace_root: Path) -> Path:
    normalized = normalize_file_query(raw_path)
    return resolve_file_target(normalized, workspace_root)


def _run_file_gate(
    step: FileGateStep,
    state: dict[str, Any],
    workspace_root: Path,
) -> dict[str, Any]:
    missing_files: list[dict[str, str]] = []
    for file_spec in step.files:
        target = _resolve_manifest_file_target(file_spec.path, workspace_root)
        if target.is_file():
            continue
        missing_files.append(
            {
                "label": file_spec.label,
                "path": file_spec.path,
                "match": file_spec.match,
            }
        )

    if missing_files:
        return {
            "status": "blocked_by_hitl",
            "stepId": step.id,
            "stepType": step.type,
            "title": step.title,
            "description": step.description,
            "missingFiles": missing_files,
            "upload": dict(step.upload),
            "state": dict(state),
        }

    return {
        "status": "completed",
        "stepId": step.id,
        "stepType": step.type,
        "next": step.next,
        "state": dict(state),
    }


def _run_choice_gate(
    step: ChoiceGateStep,
    state: dict[str, Any],
    input_data: dict[str, Any] | None,
) -> dict[str, Any]:
    option_id = str((input_data or {}).get("optionId") or "").strip()
    if not option_id:
        return {
            "status": "blocked_by_hitl",
            "stepId": step.id,
            "stepType": step.type,
            "title": step.title,
            "description": step.description,
            "options": [
                {
                    "id": option.id,
                    "label": option.label,
                    "description": option.description,
                }
                for option in step.options
            ],
            "storeAs": step.store_as,
            "state": dict(state),
        }

    if option_id not in step.next_by_choice:
        raise ValueError(f"unknown option: {option_id}")

    next_state = dict(state)
    next_state[step.store_as] = option_id
    return {
        "status": "completed",
        "stepId": step.id,
        "stepType": step.type,
        "next": step.next_by_choice[option_id],
        "state": next_state,
    }


def _run_fixed_action(
    step: FixedActionStep,
    state: dict[str, Any],
) -> dict[str, Any]:
    next_state = dict(state)
    next_state.update(step.state_patch)
    return {
        "status": "completed",
        "stepId": step.id,
        "stepType": step.type,
        "summary": step.message,
        "state": next_state,
    }


def run_manifest_step(
    manifest: SkillManifest,
    step_id: str,
    state: dict[str, Any],
    input_data: dict[str, Any] | None = None,
    workspace_root: Path | None = None,
) -> dict[str, Any]:
    step = manifest.step_by_id(step_id)
    next_state = dict(state)

    if isinstance(step, FileGateStep):
        return _run_file_gate(step=step, state=next_state, workspace_root=(workspace_root or _default_workspace_root()))
    if isinstance(step, ChoiceGateStep):
        return _run_choice_gate(step=step, state=next_state, input_data=input_data)
    if isinstance(step, FixedActionStep):
        return _run_fixed_action(step=step, state=next_state)
    raise ValueError(f"unsupported manifest step type: {type(step).__name__}")
