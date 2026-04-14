# Skill Manifest HITL Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a declarative `skill.manifest.json` runtime so workspace skills can trigger common file-upload and choice-card HITL flows without bespoke Python flow code per skill.

**Architecture:** Keep `SKILL.md` as human/agent guidance and introduce `skill.manifest.json` as executable configuration. Add a small backend runtime that loads and validates manifests, executes `file_gate` and `choice_gate`, and bridges those results into the existing `MissionControlManager` chat-card APIs and fast-path `chat_card_intent` loop.

**Tech Stack:** Python backend (`aiohttp`, existing nanobot web/runtime modules), existing frontend SDUI components (`FilePicker`, `ChoiceCard`), repo test suites under `tests/` and `frontend/scripts/`.

---

## File Map

- Create: `nanobot/skills/manifest_schema.py`
- Create: `nanobot/skills/manifest_loader.py`
- Create: `nanobot/skills/manifest_runtime.py`
- Create: `nanobot/web/skill_manifest_bridge.py`
- Modify: `nanobot/web/routes.py`
- Modify: `frontend/components/sdui/FilePicker.tsx`
- Modify: `frontend/components/sdui/ChoiceCard.tsx`
- Test: `tests/test_skill_manifest_runtime.py`
- Test: `tests/web/test_skill_manifest_fastpath.py`
- Test: `frontend/scripts/test-skill-manifest-hitl-payloads.mjs`

### Task 1: Manifest Schema

**Files:**
- Create: `nanobot/skills/manifest_schema.py`
- Test: `tests/test_skill_manifest_runtime.py`

- [ ] **Step 1: Write the failing tests**

Add tests for valid minimal manifests and invalid manifests:

```python
def test_parse_valid_file_gate_manifest() -> None:
    raw = {
        "version": 1,
        "entry": "prepare_inputs",
        "stateNamespace": "plan_progress",
        "steps": [
            {
                "id": "prepare_inputs",
                "type": "file_gate",
                "title": "请补齐输入文件",
                "files": [
                    {
                        "label": "到货表.xlsx",
                        "path": "workspace/skills/plan_progress/input/到货表.xlsx",
                        "match": "strict",
                    }
                ],
                "upload": {"saveDir": "skills/plan_progress/input", "multiple": True, "accept": ".xlsx"},
                "next": "choose_mode",
            }
        ],
    }
    manifest = parse_skill_manifest(raw)
    assert manifest.entry == "prepare_inputs"
    assert manifest.steps[0].type == "file_gate"


def test_parse_manifest_rejects_unknown_step_type() -> None:
    raw = {
        "version": 1,
        "entry": "x",
        "stateNamespace": "demo",
        "steps": [{"id": "x", "type": "unknown"}],
    }
    with pytest.raises(ValueError, match="unknown step type"):
        parse_skill_manifest(raw)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `D:\code\nanobot\.venv\Scripts\python.exe -m pytest tests/test_skill_manifest_runtime.py -k manifest -v`
Expected: FAIL because `parse_skill_manifest` does not exist yet.

- [ ] **Step 3: Write minimal implementation**

Implement typed parsing helpers in `nanobot/skills/manifest_schema.py`:

```python
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class FileSpec:
    label: str
    path: str
    match: Literal["strict"]


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
    options: list[dict[str, str]]
    store_as: str
    next_by_choice: dict[str, str]


@dataclass(frozen=True)
class SkillManifest:
    version: int
    entry: str
    state_namespace: str
    steps: list[FileGateStep | ChoiceGateStep]


def parse_skill_manifest(raw: dict[str, object]) -> SkillManifest:
    ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `D:\code\nanobot\.venv\Scripts\python.exe -m pytest tests/test_skill_manifest_runtime.py -k manifest -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add nanobot/skills/manifest_schema.py tests/test_skill_manifest_runtime.py
git commit -m "feat: add skill manifest schema"
```

### Task 2: Loader

**Files:**
- Create: `nanobot/skills/manifest_loader.py`
- Test: `tests/test_skill_manifest_runtime.py`

- [ ] **Step 1: Write the failing tests**

Add tests for loading from `workspace/skills/<skill>/skill.manifest.json` and for missing file:

```python
def test_load_skill_manifest_reads_workspace_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    skills_root = tmp_path / "skills"
    skill_dir = skills_root / "plan_progress"
    skill_dir.mkdir(parents=True)
    (skill_dir / "skill.manifest.json").write_text(
        json.dumps(
            {
                "version": 1,
                "entry": "prepare_inputs",
                "stateNamespace": "plan_progress",
                "steps": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("NANOBOT_AGUI_SKILLS_ROOT", str(skills_root))
    manifest = load_skill_manifest("plan_progress")
    assert manifest.state_namespace == "plan_progress"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `D:\code\nanobot\.venv\Scripts\python.exe -m pytest tests/test_skill_manifest_runtime.py -k load_skill_manifest -v`
Expected: FAIL because `load_skill_manifest` does not exist yet.

- [ ] **Step 3: Write minimal implementation**

Implement:

```python
from pathlib import Path
import json

from nanobot.skills.manifest_schema import SkillManifest, parse_skill_manifest
from nanobot.web.skills import get_skills_root


def load_skill_manifest(skill_name: str) -> SkillManifest:
    path = get_skills_root() / skill_name.strip() / "skill.manifest.json"
    if not path.is_file():
        raise FileNotFoundError(f"skill.manifest.json missing: {path}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("skill.manifest.json must be a JSON object")
    return parse_skill_manifest(raw)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `D:\code\nanobot\.venv\Scripts\python.exe -m pytest tests/test_skill_manifest_runtime.py -k load_skill_manifest -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add nanobot/skills/manifest_loader.py tests/test_skill_manifest_runtime.py
git commit -m "feat: add skill manifest loader"
```

### Task 3: Runtime Core

**Files:**
- Create: `nanobot/skills/manifest_runtime.py`
- Test: `tests/test_skill_manifest_runtime.py`

- [ ] **Step 1: Write the failing tests**

Add tests for `file_gate` and `choice_gate`:

```python
def test_run_file_gate_returns_completed_when_all_files_exist(tmp_path: Path) -> None:
    target = tmp_path / "workspace" / "skills" / "plan_progress" / "input" / "到货表.xlsx"
    target.parent.mkdir(parents=True)
    target.write_text("ok", encoding="utf-8")
    manifest = parse_skill_manifest(
        {
            "version": 1,
            "entry": "prepare_inputs",
            "stateNamespace": "plan_progress",
            "steps": [
                {
                    "id": "prepare_inputs",
                    "type": "file_gate",
                    "title": "请补齐输入文件",
                    "files": [
                        {
                            "label": "到货表.xlsx",
                            "path": str(target).replace("\\\\", "/"),
                            "match": "strict",
                        }
                    ],
                    "upload": {"saveDir": "skills/plan_progress/input", "multiple": True, "accept": ".xlsx"},
                    "next": "choose_mode",
                }
            ],
        }
    )
    result = run_manifest_step(manifest=manifest, step_id="prepare_inputs", state={})
    assert result["status"] == "completed"
    assert result["next"] == "choose_mode"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `D:\code\nanobot\.venv\Scripts\python.exe -m pytest tests/test_skill_manifest_runtime.py -k "file_gate or choice_gate" -v`
Expected: FAIL because `run_manifest_step` does not exist yet.

- [ ] **Step 3: Write minimal implementation**

Implement:

```python
def run_manifest_step(*, manifest: SkillManifest, step_id: str | None, state: dict[str, Any]) -> dict[str, Any]:
    ...


def _run_file_gate(step: FileGateStep, state: dict[str, Any]) -> dict[str, Any]:
    ...


def _run_choice_gate(step: ChoiceGateStep, state: dict[str, Any], option_id: str | None = None) -> dict[str, Any]:
    ...
```

Rules:
- `file_gate`: inspect files, return `completed` or `blocked_by_hitl`
- `choice_gate`: without `option_id` return `blocked_by_hitl`; with valid `option_id` return `completed`

- [ ] **Step 4: Run test to verify it passes**

Run: `D:\code\nanobot\.venv\Scripts\python.exe -m pytest tests/test_skill_manifest_runtime.py -k "file_gate or choice_gate" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add nanobot/skills/manifest_runtime.py tests/test_skill_manifest_runtime.py
git commit -m "feat: add skill manifest runtime"
```

### Task 4: HITL Bridge

**Files:**
- Create: `nanobot/web/skill_manifest_bridge.py`
- Test: `tests/web/test_skill_manifest_fastpath.py`

- [ ] **Step 1: Write the failing tests**

Add tests that assert:
- `file_gate` missing file calls `MissionControlManager.ask_for_file`
- `choice_gate` calls `MissionControlManager.emit_guidance`

```python
@pytest.mark.asyncio
async def test_file_gate_missing_file_requests_upload(monkeypatch: pytest.MonkeyPatch) -> None:
    ask_for_file = AsyncMock()
    monkeypatch.setattr("nanobot.web.mission_control.MissionControlManager.ask_for_file", ask_for_file)
    result = await execute_skill_manifest_hitl(
        skill_name="plan_progress",
        step_id="prepare_inputs",
        state={},
        thread_id="t1",
        docman=None,
    )
    assert result["status"] == "blocked_by_hitl"
    ask_for_file.assert_awaited()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `D:\code\nanobot\.venv\Scripts\python.exe -m pytest tests/web/test_skill_manifest_fastpath.py -v`
Expected: FAIL because `execute_skill_manifest_hitl` does not exist yet.

- [ ] **Step 3: Write minimal implementation**

Implement a bridge:

```python
async def execute_skill_manifest_hitl(
    *,
    skill_name: str,
    step_id: str | None,
    state: dict[str, Any],
    thread_id: str,
    docman: Any,
    intent_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ...
```

Rules:
- For `file_gate` blocked state, call `ask_for_file(...)`
- For `choice_gate` blocked state, call `emit_guidance(...)`
- Include `skillName`, `stepId`, `stateNamespace` in callback payloads

- [ ] **Step 4: Run test to verify it passes**

Run: `D:\code\nanobot\.venv\Scripts\python.exe -m pytest tests/web/test_skill_manifest_fastpath.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add nanobot/web/skill_manifest_bridge.py tests/web/test_skill_manifest_fastpath.py
git commit -m "feat: bridge skill manifest runtime to HITL cards"
```

### Task 5: Fast-Path Routing

**Files:**
- Modify: `nanobot/web/routes.py`
- Test: `tests/web/test_skill_manifest_fastpath.py`

- [ ] **Step 1: Write the failing tests**

Add tests for `chat_card_intent` payloads:

```python
@pytest.mark.asyncio
async def test_chat_skill_manifest_choice_intent_skips_llm(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ...
    intent = {
        "type": "chat_card_intent",
        "verb": "skill_manifest_choice_selected",
        "payload": {
            "skillName": "plan_progress",
            "stepId": "choose_mode",
            "stateNamespace": "plan_progress",
            "optionId": "balanced",
        },
    }
    ...
    assert fin is not None
    agent.process_direct.assert_not_called()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `D:\code\nanobot\.venv\Scripts\python.exe -m pytest tests/web/test_skill_manifest_fastpath.py -k intent -v`
Expected: FAIL because routes do not dispatch skill manifest intents yet.

- [ ] **Step 3: Write minimal implementation**

In `nanobot/web/routes.py`, after module fast-path detection, add:

```python
from nanobot.web.skill_manifest_bridge import dispatch_skill_manifest_intent

handled, hitl_message = await dispatch_skill_manifest_intent(
    intent,
    thread_id=thread_id,
    docman=docman,
)
if handled:
    ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `D:\code\nanobot\.venv\Scripts\python.exe -m pytest tests/web/test_skill_manifest_fastpath.py -k intent -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add nanobot/web/routes.py tests/web/test_skill_manifest_fastpath.py
git commit -m "feat: route skill manifest intents through chat fast-path"
```

### Task 6: Frontend Payload Wiring

**Files:**
- Modify: `frontend/components/sdui/FilePicker.tsx`
- Modify: `frontend/components/sdui/ChoiceCard.tsx`
- Test: `frontend/scripts/test-skill-manifest-hitl-payloads.mjs`

- [ ] **Step 1: Write the failing tests**

Create a source-level test:

```js
test("file picker and choice card preserve skill manifest payload fields", () => {
  assert.match(filePickerSource, /skillName/);
  assert.match(filePickerSource, /stepId/);
  assert.match(choiceCardSource, /skillName/);
  assert.match(choiceCardSource, /stepId/);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test .\\frontend\\scripts\\test-skill-manifest-hitl-payloads.mjs`
Expected: FAIL if the payload fields are not wired through yet.

- [ ] **Step 3: Write minimal implementation**

Update `FilePicker.tsx` and `ChoiceCard.tsx` so outgoing `chat_card_intent` payload preserves:

```ts
{
  skillName,
  stepId,
  stateNamespace,
}
```

Do not change existing module payload behavior; extend it compatibly.

- [ ] **Step 4: Run test to verify it passes**

Run: `node --test .\\frontend\\scripts\\test-skill-manifest-hitl-payloads.mjs`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/components/sdui/FilePicker.tsx frontend/components/sdui/ChoiceCard.tsx frontend/scripts/test-skill-manifest-hitl-payloads.mjs
git commit -m "feat: preserve skill manifest payload metadata in HITL cards"
```

### Task 7: Demo Skill

**Files:**
- Create: `templates/skill_manifest_demo/SKILL.md`
- Create: `templates/skill_manifest_demo/skill.manifest.json`
- Test: `tests/web/test_skill_manifest_fastpath.py`

- [ ] **Step 1: Write the failing test**

Add a test that copies the demo skill into a temp workspace and verifies:
- missing file -> upload card
- valid choice -> completed

- [ ] **Step 2: Run test to verify it fails**

Run: `D:\code\nanobot\.venv\Scripts\python.exe -m pytest tests/web/test_skill_manifest_fastpath.py -k demo -v`
Expected: FAIL because the demo skill does not exist yet.

- [ ] **Step 3: Write minimal implementation**

Create:

`templates/skill_manifest_demo/SKILL.md`

```md
---
name: skill_manifest_demo
description: Use when testing manifest-driven upload and choice HITL flows.
---

# skill_manifest_demo

This skill demonstrates manifest-driven file and choice gates.
```

`templates/skill_manifest_demo/skill.manifest.json`

```json
{
  "version": 1,
  "entry": "prepare_inputs",
  "stateNamespace": "skill_manifest_demo",
  "steps": [
    {
      "id": "prepare_inputs",
      "type": "file_gate",
      "title": "请上传示例文件",
      "description": "继续前请上传 demo.xlsx。",
      "files": [
        {
          "label": "demo.xlsx",
          "path": "workspace/skills/skill_manifest_demo/input/demo.xlsx",
          "match": "strict"
        }
      ],
      "upload": {
        "saveDir": "skills/skill_manifest_demo/input",
        "multiple": true,
        "accept": ".xlsx"
      },
      "next": "choose_mode"
    },
    {
      "id": "choose_mode",
      "type": "choice_gate",
      "title": "请选择模式",
      "description": "请选择 demo 模式。",
      "options": [
        { "id": "balanced", "label": "均衡模式" },
        { "id": "speed", "label": "快速模式" }
      ],
      "storeAs": "mode",
      "nextByChoice": {
        "balanced": "done",
        "speed": "done"
      }
    }
  ]
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `D:\code\nanobot\.venv\Scripts\python.exe -m pytest tests/web/test_skill_manifest_fastpath.py -k demo -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add templates/skill_manifest_demo/SKILL.md templates/skill_manifest_demo/skill.manifest.json tests/web/test_skill_manifest_fastpath.py
git commit -m "feat: add manifest HITL demo skill"
```
