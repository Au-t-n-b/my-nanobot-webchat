"""Schema parsing for declarative workspace skill manifests."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


def _require_str(raw: object, field_name: str) -> str:
    value = str(raw or "").strip()
    if not value:
        raise ValueError(f"{field_name} is required")
    return value


def _require_dict(raw: object, field_name: str) -> dict[str, object]:
    if not isinstance(raw, dict):
        raise ValueError(f"{field_name} must be an object")
    return raw


def _require_list(raw: object, field_name: str) -> list[object]:
    if not isinstance(raw, list):
        raise ValueError(f"{field_name} must be a list")
    return raw


@dataclass(frozen=True)
class FileSpec:
    label: str
    path: str
    match: Literal["strict"]


@dataclass(frozen=True)
class ChoiceOption:
    id: str
    label: str
    description: str = ""


@dataclass(frozen=True)
class FileGateStep:
    id: str
    type: Literal["file_gate"]
    title: str
    description: str
    files: list[FileSpec]
    upload: dict[str, object]
    next: str


@dataclass(frozen=True)
class ChoiceGateStep:
    id: str
    type: Literal["choice_gate"]
    title: str
    description: str
    options: list[ChoiceOption]
    store_as: str
    next_by_choice: dict[str, str]


@dataclass(frozen=True)
class FixedActionStep:
    id: str
    type: Literal["fixed_action"]
    title: str
    message: str
    state_patch: dict[str, object]


ManifestStep = FileGateStep | ChoiceGateStep | FixedActionStep


@dataclass(frozen=True)
class SkillManifest:
    version: int
    entry: str
    state_namespace: str
    steps: list[ManifestStep]

    def step_by_id(self, step_id: str) -> ManifestStep:
        target = str(step_id or "").strip()
        for step in self.steps:
            if step.id == target:
                return step
        raise KeyError(f"unknown manifest step: {target}")


def _parse_file_spec(raw: object) -> FileSpec:
    payload = _require_dict(raw, "files[]")
    match = _require_str(payload.get("match"), "files[].match")
    if match != "strict":
        raise ValueError(f"unsupported file match mode: {match}")
    return FileSpec(
        label=_require_str(payload.get("label"), "files[].label"),
        path=_require_str(payload.get("path"), "files[].path"),
        match="strict",
    )


def _parse_choice_option(raw: object) -> ChoiceOption:
    payload = _require_dict(raw, "options[]")
    return ChoiceOption(
        id=_require_str(payload.get("id"), "options[].id"),
        label=_require_str(payload.get("label"), "options[].label"),
        description=str(payload.get("description") or "").strip(),
    )


def _parse_file_gate_step(raw: object) -> FileGateStep:
    payload = _require_dict(raw, "steps[]")
    upload = _require_dict(payload.get("upload"), "steps[].upload")
    files = [_parse_file_spec(item) for item in _require_list(payload.get("files"), "steps[].files")]
    return FileGateStep(
        id=_require_str(payload.get("id"), "steps[].id"),
        type="file_gate",
        title=_require_str(payload.get("title"), "steps[].title"),
        description=str(payload.get("description") or "").strip(),
        files=files,
        upload={str(key): value for key, value in upload.items()},
        next=_require_str(payload.get("next"), "steps[].next"),
    )


def _parse_choice_gate_step(raw: object) -> ChoiceGateStep:
    payload = _require_dict(raw, "steps[]")
    raw_next = _require_dict(payload.get("nextByChoice"), "steps[].nextByChoice")
    next_by_choice = {str(key).strip(): _require_str(value, f"nextByChoice.{key}") for key, value in raw_next.items()}
    return ChoiceGateStep(
        id=_require_str(payload.get("id"), "steps[].id"),
        type="choice_gate",
        title=_require_str(payload.get("title"), "steps[].title"),
        description=str(payload.get("description") or "").strip(),
        options=[
            _parse_choice_option(item)
            for item in _require_list(payload.get("options"), "steps[].options")
        ],
        store_as=_require_str(payload.get("storeAs"), "steps[].storeAs"),
        next_by_choice=next_by_choice,
    )


def _parse_fixed_action_step(raw: object) -> FixedActionStep:
    payload = _require_dict(raw, "steps[]")
    raw_state_patch = payload.get("statePatch")
    state_patch = dict(raw_state_patch) if isinstance(raw_state_patch, dict) else {}
    return FixedActionStep(
        id=_require_str(payload.get("id"), "steps[].id"),
        type="fixed_action",
        title=_require_str(payload.get("title"), "steps[].title"),
        message=_require_str(payload.get("message"), "steps[].message"),
        state_patch={str(key): value for key, value in state_patch.items()},
    )


def parse_skill_manifest(raw: dict[str, object]) -> SkillManifest:
    if not isinstance(raw, dict):
        raise ValueError("skill.manifest.json must be a JSON object")

    version = raw.get("version")
    if not isinstance(version, int):
        raise ValueError("version must be an integer")

    steps: list[ManifestStep] = []
    for item in _require_list(raw.get("steps"), "steps"):
        payload = _require_dict(item, "steps[]")
        step_type = _require_str(payload.get("type"), "steps[].type")
        if step_type == "file_gate":
            steps.append(_parse_file_gate_step(payload))
            continue
        if step_type == "choice_gate":
            steps.append(_parse_choice_gate_step(payload))
            continue
        if step_type == "fixed_action":
            steps.append(_parse_fixed_action_step(payload))
            continue
        raise ValueError(f"unknown step type: {step_type}")

    return SkillManifest(
        version=version,
        entry=_require_str(raw.get("entry"), "entry"),
        state_namespace=_require_str(raw.get("stateNamespace"), "stateNamespace"),
        steps=steps,
    )
