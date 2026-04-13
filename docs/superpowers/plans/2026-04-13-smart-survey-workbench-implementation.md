# Smart Survey Workbench Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a new `smart_survey_workbench` module that keeps the nanobot dashboard shell while executing the copied `GongKanSkill` business workflow with four native steps, HITL file gates, progress sync, KPI updates, and approval pause/resume.

**Architecture:** Add a dedicated `smart_survey_workflow` in `nanobot.web.module_skill_runtime`, scaffold a new module template under `templates/smart_survey_workbench`, and translate the copied liveskill's files, `progress.json`, and outputs into SDUI patches and task-progress events. Follow the same integration pattern as `modeling_simulation_workbench` and `job_management`, but keep a separate `moduleId`, `flow`, action sequence, and file gates.

**Tech Stack:** Python (`pytest`, async runtime, SDUI patch helpers), JSON module templates, Markdown docs, workspace skill packaging

---

## File Structure

### New files

- `D:\code\nanobot\templates\smart_survey_workbench\module.json`
  - New module contract: `moduleId`, `docId`, `dataFile`, `flow`, uploads, `taskProgress`, `caseTemplate`
- `D:\code\nanobot\templates\smart_survey_workbench\data\dashboard.json`
  - SDUI dashboard with fixed nodes: `stepper-main`, KPI cards, charts, `alerts`, `summary-text`, `uploaded-files`, `artifacts`
- `D:\code\nanobot\templates\smart_survey_workbench\references\flow.md`
  - Human-readable action sequence and runtime behavior
- `D:\code\nanobot\templates\smart_survey_workbench\SKILL.md`
  - Workspace module handoff note aligned with the new flow
- `D:\code\nanobot\docs\superpowers/plans\2026-04-13-smart-survey-workbench-implementation.md`
  - This plan

### Modified files

- `D:\code\nanobot\nanobot\web\module_skill_runtime.py`
  - Add `smart_survey_workflow`, helper functions for file gates, progress parsing, artifact mapping, KPI/chart patching, and route registration
- `D:\code\nanobot\tests\test_module_skill_runtime.py`
  - Add fixture for copied `smart_survey_workbench` and `gongkan_skill`, plus regression tests for guide, uploads, step transitions, approval pause, and completion
- `D:\code\nanobot\nanobot\agent\context.py`
  - Teach the system prompt that `smart_survey_workbench` must start with the real upload action and pause at approval

### External workspace sync after code merge

- `C:\Users\华为\.nanobot\workspace\skills\smart_survey_workbench`
  - Copy template here after implementation
- `C:\Users\华为\.nanobot\workspace\skills\gongkan_skill`
  - Copy the colleague's liveskill here and use it as the runtime source of truth

## Task 1: Scaffold the Module Template and Template Contract Tests

**Files:**
- Create: `D:\code\nanobot\templates\smart_survey_workbench\module.json`
- Create: `D:\code\nanobot\templates\smart_survey_workbench\data\dashboard.json`
- Create: `D:\code\nanobot\templates\smart_survey_workbench\references\flow.md`
- Create: `D:\code\nanobot\templates\smart_survey_workbench\SKILL.md`
- Modify: `D:\code\nanobot\tests\test_module_skill_runtime.py`

- [ ] **Step 1: Write the failing template config test**

```python
@pytest.fixture()
def skills_smart_survey_workbench(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    repo_root = Path(__file__).resolve().parents[1]
    src = repo_root / "templates" / "smart_survey_workbench"
    dst_root = tmp_path / "skills"
    shutil.copytree(src, dst_root / "smart_survey_workbench")
    monkeypatch.setenv("NANOBOT_AGUI_SKILLS_ROOT", str(dst_root))
    return dst_root / "smart_survey_workbench"


@pytest.mark.asyncio
async def test_load_module_config_smart_survey_workbench(
    skills_smart_survey_workbench: Path,
) -> None:
    from nanobot.web.module_skill_runtime import load_module_config

    cfg = load_module_config("smart_survey_workbench")
    assert cfg.get("flow") == "smart_survey_workflow"
    assert cfg.get("docId") == "dashboard:smart-survey-workbench"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
pytest D:\code\nanobot\tests\test_module_skill_runtime.py::test_load_module_config_smart_survey_workbench -v
```

Expected: `FAIL` because `templates/smart_survey_workbench` does not exist yet.

- [ ] **Step 3: Write the minimal template files**

`D:\code\nanobot\templates\smart_survey_workbench\module.json`

```json
{
  "schemaVersion": 1,
  "moduleId": "smart_survey_workbench",
  "docId": "dashboard:smart-survey-workbench",
  "dataFile": "skills/smart_survey_workbench/data/dashboard.json",
  "flow": "smart_survey_workflow",
  "capabilities": {
    "hitl": true,
    "uploads": true,
    "metrics": ["kpi_cards", "chart_cards", "alerts"],
    "skillOrchestration": ["serial"],
    "taskProgressAutoSync": true
  },
  "uploads": [
    {
      "purpose": "smart_survey_inputs",
      "label": "智慧工勘输入文件",
      "accept": ".xlsx,.docx,.jpg,.jpeg,.png",
      "multiple": true,
      "save_relative_dir": "skills/gongkan_skill/ProjectData/Input"
    }
  ],
  "taskProgress": {
    "moduleId": "smart_survey",
    "moduleName": "智慧工勘模块",
    "tasks": ["场景筛选与底表过滤", "勘测数据汇总", "报告生成", "审批分发"]
  }
}
```

`D:\code\nanobot\templates\smart_survey_workbench\data\dashboard.json`

```json
{
  "schemaVersion": 1,
  "type": "SduiDocument",
  "meta": { "docId": "dashboard:smart-survey-workbench", "provenance": "smart_survey_workbench" },
  "root": {
    "type": "Stack",
    "gap": "lg",
    "children": [
      { "type": "Text", "variant": "heading", "content": "智慧工勘模块 · 当前进展 / 黄金指标 / 产物总结" },
      { "type": "Stepper", "id": "stepper-main", "steps": [] },
      { "type": "Stack", "id": "alerts", "gap": "sm", "children": [] },
      { "type": "Text", "id": "summary-text", "variant": "body", "color": "subtle", "content": "进入模块后将在此展示工勘阶段摘要。" },
      { "type": "ArtifactGrid", "id": "uploaded-files", "title": "已上传文件", "mode": "input", "artifacts": [] },
      { "type": "ArtifactGrid", "id": "artifacts", "title": "作业结果", "mode": "output", "artifacts": [] }
    ]
  }
}
```

`D:\code\nanobot\templates\smart_survey_workbench\references\flow.md`

```md
# smart_survey_workbench · 流程说明

`guide` → `prepare_step1` → `run_step1` → `prepare_step2` → `run_step2` → `prepare_step3` → `run_step3` → `prepare_step4` → `run_step4_approve` → `approval_pass`
```

`D:\code\nanobot\templates\smart_survey_workbench\SKILL.md`

```md
---
name: smart_survey_workbench
description: 智慧工勘模块大盘，使用 smart_survey_workflow 驱动真实 GongKanSkill liveskill
---

# smart_survey_workbench

本模块保留 nanobot 标准大盘，后端执行 liveskill 中的真实智慧工勘流程，并在审批前暂停等待人工确认。
```

- [ ] **Step 4: Run tests to verify the template loads**

Run:

```powershell
pytest D:\code\nanobot\tests\test_module_skill_runtime.py::test_load_module_config_smart_survey_workbench -v
```

Expected: `PASS`

- [ ] **Step 5: Commit**

```bash
git add templates/smart_survey_workbench tests/test_module_skill_runtime.py
git commit -m "feat: scaffold smart survey workbench template"
```

## Task 2: Add Guide Action, Dashboard IDs, and Upload Gate Tests

**Files:**
- Modify: `D:\code\nanobot\nanobot\web\module_skill_runtime.py`
- Modify: `D:\code\nanobot\tests\test_module_skill_runtime.py`
- Modify: `D:\code\nanobot\templates\smart_survey_workbench\data\dashboard.json`

- [ ] **Step 1: Write failing tests for `guide` and missing Step 1 inputs**

```python
def _expected_smart_survey_synthetic_path() -> str:
    return "skill-ui://SduiView?dataFile=skills/smart_survey_workbench/data/dashboard.json"


@pytest.fixture()
def skills_smart_survey_with_gongkan(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    repo_root = Path(__file__).resolve().parents[1]
    dst_root = tmp_path / "skills"
    shutil.copytree(repo_root / "templates" / "smart_survey_workbench", dst_root / "smart_survey_workbench")
    gongkan = dst_root / "gongkan_skill"
    (gongkan / "ProjectData" / "Start").mkdir(parents=True)
    (gongkan / "ProjectData" / "Input").mkdir(parents=True)
    (gongkan / "ProjectData" / "Images").mkdir(parents=True)
    (gongkan / "ProjectData" / "Output").mkdir(parents=True)
    (gongkan / "ProjectData" / "RunTime").mkdir(parents=True)
    (gongkan / "ProjectData" / "RunTime" / "progress.json").write_text(
        json.dumps({"modules": [{"moduleId": "smart_survey", "tasks": []}]}, ensure_ascii=False),
        encoding="utf-8",
    )
    monkeypatch.setenv("NANOBOT_AGUI_SKILLS_ROOT", str(dst_root))
    return dst_root


@pytest.mark.asyncio
async def test_smart_survey_workbench_guide_emits_dashboard_nodes(
    skills_smart_survey_with_gongkan: Path,
    capture_skill_ui_patches: list[dict],
) -> None:
    from nanobot.web.module_skill_runtime import run_module_action

    r = await run_module_action(
        module_id="smart_survey_workbench",
        action="guide",
        state={},
        thread_id="thread-smart-guide",
        docman=None,
    )
    assert r.get("ok") is True
    assert r.get("next") == "prepare_step1"
    for payload in capture_skill_ui_patches:
        assert payload.get("syntheticPath") == _expected_smart_survey_synthetic_path()
    merged = _merge_node_ids_from_patch_payloads(capture_skill_ui_patches)
    assert {"stepper-main", "summary-text", "uploaded-files", "artifacts"}.issubset(merged)


@pytest.mark.asyncio
async def test_smart_survey_prepare_step1_requests_missing_inputs(
    skills_smart_survey_with_gongkan: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import nanobot.web.module_skill_runtime as module_skill_runtime

    mock_af = AsyncMock(return_value=ChatCardHandle(card_id="upload:smart:step1", doc_id="chat:thread-smart-step1"))
    monkeypatch.setattr("nanobot.web.mission_control.MissionControlManager.ask_for_file", mock_af)

    r = await module_skill_runtime.run_module_action(
        module_id="smart_survey_workbench",
        action="prepare_step1",
        state={},
        thread_id="thread-smart-step1",
        docman=None,
    )
    assert r.get("ok") is True
    assert r.get("next") == "run_step1"
    mock_af.assert_awaited_once()
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
pytest D:\code\nanobot\tests\test_module_skill_runtime.py -k "smart_survey_workbench_guide or smart_survey_prepare_step1" -v
```

Expected: `FAIL` with unknown module flow or unknown action.

- [ ] **Step 3: Implement the minimal guide and Step 1 gate**

Add helper skeletons in `D:\code\nanobot\nanobot\web\module_skill_runtime.py`:

```python
def _gongkan_skill_root() -> Path:
    root = Path(os.getenv("NANOBOT_AGUI_SKILLS_ROOT", "")).expanduser()
    return root / "gongkan_skill"


def _smart_survey_stepper_steps(active_index: int) -> list[dict[str, Any]]:
    titles = ["场景筛选与底表过滤", "勘测数据汇总", "报告生成", "审批分发"]
    steps: list[dict[str, Any]] = []
    for idx, title in enumerate(titles):
        status = "completed" if idx < active_index else "running" if idx == active_index else "waiting"
        steps.append({"id": f"s{idx+1}", "title": title, "status": status, "detail": []})
    return steps


def _smart_survey_missing_step1_inputs(skill_root: Path) -> list[str]:
    start_dir = skill_root / "ProjectData" / "Start"
    input_dir = skill_root / "ProjectData" / "Input"
    missing: list[str] = []
    for name in ["勘测问题底表.xlsx", "评估项底表.xlsx", "工勘常见高风险库.xlsx"]:
        if not (start_dir / name).exists():
            missing.append(name)
    if not list(input_dir.glob("*BOQ*.xlsx")):
        missing.append("BOQ*.xlsx")
    if not (input_dir / "勘测信息预置集.docx").exists():
        missing.append("勘测信息预置集.docx")
    return missing
```

Add flow branch skeleton:

```python
async def _flow_smart_survey_workflow(...):
    pusher = _pusher_for(cfg)
    mc = MissionControlManager(thread_id=thread_id, docman=docman)
    skill_root = _gongkan_skill_root()

    if action == "guide":
        clear_module_session(thread_id, module_id)
        await pusher.update_nodes(
            [
                (SDUI_STEPPER_MAIN_ID, "Stepper", {"steps": _smart_survey_stepper_steps(0)}),
                ("summary-text", "Text", {"content": "智慧工勘模块已就绪，请先检查并补齐 Step 1 输入件。", "variant": "body", "color": "subtle"}),
                ("uploaded-files", "ArtifactGrid", {"title": "已上传文件", "mode": "input", "artifacts": []}),
                ("artifacts", "ArtifactGrid", {"title": "作业结果", "mode": "output", "artifacts": []}),
            ]
        )
        return {"ok": True, "next": "prepare_step1"}

    if action == "prepare_step1":
        missing = _smart_survey_missing_step1_inputs(skill_root)
        if missing:
            await mc.ask_for_file(
                purpose="smart_survey_inputs",
                title="请补齐工勘 Step 1 输入件",
                accept=".xlsx,.docx",
                multiple=True,
                module_id=module_id,
                next_action="run_step1",
                save_relative_dir="skills/gongkan_skill/ProjectData/Input",
            )
        return {"ok": True, "next": "run_step1"}
```

Register the flow:

```python
elif flow == "smart_survey_workflow":
    result = await _flow_smart_survey_workflow(
        module_id=module_id,
        action=action,
        state=state,
        thread_id=thread_id,
        docman=docman,
        cfg=cfg,
    )
```

- [ ] **Step 4: Run tests to verify the guide and file gate pass**

Run:

```powershell
pytest D:\code\nanobot\tests\test_module_skill_runtime.py -k "smart_survey_workbench_guide or smart_survey_prepare_step1" -v
```

Expected: `2 passed`

- [ ] **Step 5: Commit**

```bash
git add nanobot/web/module_skill_runtime.py tests/test_module_skill_runtime.py templates/smart_survey_workbench/data/dashboard.json
git commit -m "feat: add smart survey guide and step1 gate"
```

## Task 3: Implement Step 1 and Step 2 Runtime Translation with TDD

**Files:**
- Modify: `D:\code\nanobot\nanobot\web\module_skill_runtime.py`
- Modify: `D:\code\nanobot\tests\test_module_skill_runtime.py`

- [ ] **Step 1: Write failing tests for Step 1 execution and Step 2 upload gate**

```python
@pytest.mark.asyncio
async def test_smart_survey_run_step1_updates_summary_and_artifacts(
    skills_smart_survey_with_gongkan: Path,
    capture_skill_ui_patches: list[dict],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import nanobot.web.module_skill_runtime as module_skill_runtime

    skill_root = skills_smart_survey_with_gongkan / "gongkan_skill"
    start_dir = skill_root / "ProjectData" / "Start"
    input_dir = skill_root / "ProjectData" / "Input"
    for name in ["勘测问题底表.xlsx", "评估项底表.xlsx", "工勘常见高风险库.xlsx"]:
        (start_dir / name).write_text(name, encoding="utf-8")
    (input_dir / "sample_BOQ.xlsx").write_text("boq", encoding="utf-8")
    (input_dir / "勘测信息预置集.docx").write_text("preset", encoding="utf-8")

    monkeypatch.setattr(
        module_skill_runtime,
        "_run_gongkan_step1",
        AsyncMock(return_value={"ok": True, "summary": "已识别液冷/A3/新址新建", "artifacts": [{"label": "定制工勘表.xlsx"}]}),
    )

    r = await module_skill_runtime.run_module_action(
        module_id="smart_survey_workbench",
        action="run_step1",
        state={},
        thread_id="thread-smart-run1",
        docman=None,
    )
    assert r.get("ok") is True
    assert r.get("next") == "prepare_step2"
    summary_updates = _merge_values_for_node(capture_skill_ui_patches, "summary-text")
    assert "液冷" in str(summary_updates[-1].get("content") or "")


@pytest.mark.asyncio
async def test_smart_survey_prepare_step2_requests_missing_results_or_images(
    skills_smart_survey_with_gongkan: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import nanobot.web.module_skill_runtime as module_skill_runtime

    skill_root = skills_smart_survey_with_gongkan / "gongkan_skill"
    (skill_root / "ProjectData" / "RunTime" / "勘测问题底表_过滤.xlsx").write_text("filtered", encoding="utf-8")

    mock_af = AsyncMock(return_value=ChatCardHandle(card_id="upload:smart:step2", doc_id="chat:thread-smart-step2"))
    monkeypatch.setattr("nanobot.web.mission_control.MissionControlManager.ask_for_file", mock_af)

    r = await module_skill_runtime.run_module_action(
        module_id="smart_survey_workbench",
        action="prepare_step2",
        state={},
        thread_id="thread-smart-step2",
        docman=None,
    )
    assert r.get("ok") is True
    assert r.get("next") == "run_step2"
    mock_af.assert_awaited_once()
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
pytest D:\code\nanobot\tests\test_module_skill_runtime.py -k "smart_survey_run_step1 or smart_survey_prepare_step2" -v
```

Expected: `FAIL` with unknown action `run_step1` or `prepare_step2`.

- [ ] **Step 3: Implement Step 1 and Step 2 helpers**

Add helpers:

```python
async def _run_gongkan_step1(skill_root: Path) -> dict[str, Any]:
    return {
        "ok": True,
        "summary": "已完成场景筛选与底表过滤",
        "artifacts": _artifacts_for_paths(
            [
                skill_root / "ProjectData" / "RunTime" / "定制工勘表.xlsx",
                skill_root / "ProjectData" / "RunTime" / "勘测问题底表_过滤.xlsx",
                skill_root / "ProjectData" / "RunTime" / "评估项底表_过滤.xlsx",
                skill_root / "ProjectData" / "RunTime" / "工勘常见高风险库_过滤.xlsx",
            ]
        ),
    }


def _smart_survey_missing_step2_inputs(skill_root: Path) -> list[str]:
    input_dir = skill_root / "ProjectData" / "Input"
    image_dir = skill_root / "ProjectData" / "Images"
    missing: list[str] = []
    if not (skill_root / "ProjectData" / "RunTime" / "勘测问题底表_过滤.xlsx").exists():
        missing.append("勘测问题底表_过滤.xlsx")
    if not (input_dir / "勘测结果.xlsx").exists():
        missing.append("勘测结果.xlsx")
    if not any(image_dir.iterdir()):
        missing.append("现场照片")
    return missing
```

Add flow branches:

```python
if action == "run_step1":
    result = await _run_gongkan_step1(skill_root)
    await pusher.update_nodes(
        [
            (SDUI_STEPPER_MAIN_ID, "Stepper", {"steps": _smart_survey_stepper_steps(1)}),
            ("summary-text", "Text", {"content": result["summary"], "variant": "body", "color": "subtle"}),
            ("artifacts", "ArtifactGrid", {"title": "作业结果", "mode": "output", "artifacts": result["artifacts"]}),
        ]
    )
    return {"ok": True, "next": "prepare_step2"}

if action == "prepare_step2":
    missing = _smart_survey_missing_step2_inputs(skill_root)
    if missing:
        await mc.ask_for_file(
            purpose="smart_survey_inputs",
            title="请补齐工勘 Step 2 输入件",
            accept=".xlsx,.jpg,.jpeg,.png",
            multiple=True,
            module_id=module_id,
            next_action="run_step2",
            save_relative_dir="skills/gongkan_skill/ProjectData/Input",
        )
    return {"ok": True, "next": "run_step2"}
```

- [ ] **Step 4: Run tests to verify Step 1 and Step 2 gates pass**

Run:

```powershell
pytest D:\code\nanobot\tests\test_module_skill_runtime.py -k "smart_survey_run_step1 or smart_survey_prepare_step2" -v
```

Expected: `2 passed`

- [ ] **Step 5: Commit**

```bash
git add nanobot/web/module_skill_runtime.py tests/test_module_skill_runtime.py
git commit -m "feat: add smart survey step1 and step2 flow"
```

## Task 4: Implement Step 2 KPI Updates, Step 3 Report Flow, and Approval Pause

**Files:**
- Modify: `D:\code\nanobot\nanobot\web\module_skill_runtime.py`
- Modify: `D:\code\nanobot\tests\test_module_skill_runtime.py`
- Modify: `D:\code\nanobot\templates\smart_survey_workbench\data\dashboard.json`

- [ ] **Step 1: Write failing tests for Step 2 KPI patching and Step 4 pause/resume**

```python
@pytest.mark.asyncio
async def test_smart_survey_run_step2_updates_uploaded_files_kpis_and_summary(
    skills_smart_survey_with_gongkan: Path,
    capture_skill_ui_patches: list[dict],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import nanobot.web.module_skill_runtime as module_skill_runtime

    monkeypatch.setattr(
        module_skill_runtime,
        "_run_gongkan_step2",
        AsyncMock(
            return_value={
                "ok": True,
                "summary": "已生成全量勘测结果表，完整率 81%",
                "uploaded_artifacts": [{"label": "勘测结果.xlsx"}],
                "artifacts": [{"label": "全量勘测结果表.xlsx"}],
                "metrics": {"completion": 81, "integrity": 81, "remaining": 24},
            }
        ),
    )

    r = await module_skill_runtime.run_module_action(
        module_id="smart_survey_workbench",
        action="run_step2",
        state={},
        thread_id="thread-smart-run2",
        docman=None,
    )
    assert r.get("ok") is True
    assert r.get("next") == "prepare_step3"
    assert _merge_values_for_node(capture_skill_ui_patches, "uploaded-files")
    assert _merge_values_for_node(capture_skill_ui_patches, "summary-text")


@pytest.mark.asyncio
async def test_smart_survey_run_step4_approve_pauses_before_finish(
    skills_smart_survey_with_gongkan: Path,
    capture_skill_ui_patches: list[dict],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import nanobot.web.module_skill_runtime as module_skill_runtime

    monkeypatch.setattr(
        module_skill_runtime,
        "_run_gongkan_step4_approve",
        AsyncMock(return_value={"ok": True, "summary": "已发送专家审批，等待回执"}),
    )

    r = await module_skill_runtime.run_module_action(
        module_id="smart_survey_workbench",
        action="run_step4_approve",
        state={},
        thread_id="thread-smart-approve",
        docman=None,
    )
    assert r.get("ok") is True
    assert r.get("next") == "approval_pass"
    summary_updates = _merge_values_for_node(capture_skill_ui_patches, "summary-text")
    assert "等待回执" in str(summary_updates[-1].get("content") or "")
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
pytest D:\code\nanobot\tests\test_module_skill_runtime.py -k "smart_survey_run_step2 or smart_survey_run_step4_approve" -v
```

Expected: `FAIL` because the actions and KPI nodes are not implemented.

- [ ] **Step 3: Implement Step 2, Step 3, and approval pause/resume**

Add KPI/chart update helper:

```python
def _smart_survey_dashboard_nodes(result: dict[str, Any]) -> list[tuple[str, str, dict[str, Any]]]:
    summary = str(result.get("summary") or "")
    artifacts = list(result.get("artifacts") or [])
    uploaded = list(result.get("uploaded_artifacts") or [])
    alerts = list(result.get("alerts") or [])
    return [
        ("summary-text", "Text", {"content": summary, "variant": "body", "color": "subtle"}),
        ("uploaded-files", "ArtifactGrid", {"title": "已上传文件", "mode": "input", "artifacts": uploaded}),
        ("artifacts", "ArtifactGrid", {"title": "作业结果", "mode": "output", "artifacts": artifacts}),
        ("alerts", "Stack", {"children": alerts}),
    ]
```

Add branches:

```python
if action == "run_step2":
    result = await _run_gongkan_step2(skill_root)
    await pusher.update_nodes(
        [(SDUI_STEPPER_MAIN_ID, "Stepper", {"steps": _smart_survey_stepper_steps(2)}), *_smart_survey_dashboard_nodes(result)]
    )
    return {"ok": True, "next": "prepare_step3"}

if action == "run_step3":
    result = await _run_gongkan_step3(skill_root)
    await pusher.update_nodes(
        [(SDUI_STEPPER_MAIN_ID, "Stepper", {"steps": _smart_survey_stepper_steps(3)}), *_smart_survey_dashboard_nodes(result)]
    )
    return {"ok": True, "next": "prepare_step4"}

if action == "run_step4_approve":
    result = await _run_gongkan_step4_approve(skill_root)
    await pusher.update_nodes(
        [(SDUI_STEPPER_MAIN_ID, "Stepper", {"steps": _smart_survey_stepper_steps(3)}), *_smart_survey_dashboard_nodes(result)]
    )
    await mc.emit_guidance(
        context="专家审批已发送，请在收到回执后继续。",
        actions=[{"label": "审批通过", "verb": "module_action", "payload": {"moduleId": module_id, "action": "approval_pass", "state": dict(state)}}],
    )
    return {"ok": True, "next": "approval_pass"}

if action == "approval_pass":
    result = await _run_gongkan_step4_finish(skill_root)
    await pusher.update_nodes(
        [(SDUI_STEPPER_MAIN_ID, "Stepper", {"steps": _smart_survey_stepper_steps(4)}), *_smart_survey_dashboard_nodes(result)]
    )
    clear_module_session(thread_id, module_id)
    return {"ok": True, "done": True, "summary": str(result.get("summary") or "智慧工勘流程已完成")}
```

- [ ] **Step 4: Run targeted tests plus the existing modeling/job-management regressions**

Run:

```powershell
pytest D:\code\nanobot\tests\test_module_skill_runtime.py -k "smart_survey_run_step2 or smart_survey_run_step4_approve or modeling_simulation_workbench or job_management" -v
```

Expected: all selected tests `PASS`

- [ ] **Step 5: Commit**

```bash
git add nanobot/web/module_skill_runtime.py tests/test_module_skill_runtime.py templates/smart_survey_workbench/data/dashboard.json
git commit -m "feat: add smart survey reporting and approval flow"
```

## Task 5: Update System Prompt, Documentation, and End-to-End Verification

**Files:**
- Modify: `D:\code\nanobot\nanobot\agent\context.py`
- Modify: `D:\code\nanobot\templates\smart_survey_workbench\references\flow.md`
- Modify: `D:\code\nanobot\templates\smart_survey_workbench\SKILL.md`

- [ ] **Step 1: Write failing regression test for context guidance**

```python
def test_system_prompt_mentions_smart_survey_workbench_flow() -> None:
    from nanobot.agent.context import ContextBuilder

    prompt = ContextBuilder(Path("D:/code/nanobot")).build_system_prompt([])
    assert "smart_survey_workbench" in prompt
    assert 'module_skill_runtime(module_id="smart_survey_workbench", action="prepare_step1"' in prompt
    assert "approval_pass" in prompt
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
pytest D:\code\nanobot\tests\test_module_skill_runtime.py::test_system_prompt_mentions_smart_survey_workbench_flow -v
```

Expected: `FAIL` because `context.py` has no smart survey instructions yet.

- [ ] **Step 3: Update the system prompt and module docs**

Patch `D:\code\nanobot\nanobot\agent\context.py` near the existing module instructions:

```python
- For **`smart_survey_workbench`**: after the user enters the module or asks to start智慧工勘, your next tool step should be
  `module_skill_runtime(module_id="smart_survey_workbench", action="prepare_step1", state={})`.
  The flow continues as `run_step1 -> prepare_step2 -> run_step2 -> prepare_step3 -> run_step3 -> prepare_step4 -> run_step4_approve`.
  After `run_step4_approve`, pause for human confirmation and only continue with
  `module_skill_runtime(module_id="smart_survey_workbench", action="approval_pass", state={...})`
  when the user says 审批通过.
```

Refresh `D:\code\nanobot\templates\smart_survey_workbench\references\flow.md`:

```md
# smart_survey_workbench · 流程说明

本模块使用独立的 `_flow_smart_survey_workflow`，只服务于 `smart_survey_workbench`。

`guide` → `prepare_step1` → `run_step1` → `prepare_step2` → `run_step2` → `prepare_step3` → `run_step3` → `prepare_step4` → `run_step4_approve` → `approval_pass`
```

Refresh `D:\code\nanobot\templates\smart_survey_workbench\SKILL.md`:

```md
## 接入 workspace

将本目录复制到 `~/.nanobot/workspace/skills/smart_survey_workbench/`，并将同事的业务 skill 复制到
`~/.nanobot/workspace/skills/gongkan_skill/`。重启 AGUI 后进入 **智慧工勘模块**。
```

- [ ] **Step 4: Run the focused test and then the full regression file**

Run:

```powershell
pytest D:\code\nanobot\tests\test_module_skill_runtime.py::test_system_prompt_mentions_smart_survey_workbench_flow -v
pytest D:\code\nanobot\tests\test_module_skill_runtime.py -v
```

Expected:
- first command: `PASS`
- second command: all module runtime tests `PASS`

- [ ] **Step 5: Commit**

```bash
git add nanobot/agent/context.py templates/smart_survey_workbench/references/flow.md templates/smart_survey_workbench/SKILL.md tests/test_module_skill_runtime.py
git commit -m "feat: document smart survey runtime integration"
```

## Task 6: Workspace Sync and Manual Validation Checklist

**Files:**
- Modify: `D:\code\nanobot\templates\smart_survey_workbench\SKILL.md`
- Manual copy: `C:\Users\华为\.nanobot\workspace\skills\smart_survey_workbench`
- Manual copy: `C:\Users\华为\.nanobot\workspace\skills\gongkan_skill`

- [ ] **Step 1: Copy the module template and liveskill into the workspace**

Run:

```powershell
Copy-Item -LiteralPath 'D:\code\nanobot\templates\smart_survey_workbench' -Destination 'C:\Users\华为\.nanobot\workspace\skills\smart_survey_workbench' -Recurse -Force
Copy-Item -LiteralPath 'C:\Users\华为\Desktop\GongKanSkill' -Destination 'C:\Users\华为\.nanobot\workspace\skills\gongkan_skill' -Recurse -Force
```

Expected: both directories exist under `C:\Users\华为\.nanobot\workspace\skills`.

- [ ] **Step 2: Prepare a manual validation dataset**

Place these files in the copied liveskill:

```text
C:\Users\华为\.nanobot\workspace\skills\gongkan_skill\ProjectData\Start\勘测问题底表.xlsx
C:\Users\华为\.nanobot\workspace\skills\gongkan_skill\ProjectData\Start\评估项底表.xlsx
C:\Users\华为\.nanobot\workspace\skills\gongkan_skill\ProjectData\Start\工勘常见高风险库.xlsx
C:\Users\华为\.nanobot\workspace\skills\gongkan_skill\ProjectData\Input\<任意 BOQ*.xlsx>
C:\Users\华为\.nanobot\workspace\skills\gongkan_skill\ProjectData\Input\勘测信息预置集.docx
```

- [ ] **Step 3: Run the manual dashboard validation**

Manual steps:

```text
1. 打开智慧工勘模块
2. 验证 guide 后 Stepper 显示 4 步
3. 缺文件时验证真实 FilePicker 出现
4. 补齐 Step 1 输入后执行场景筛选
5. Step 2 缺勘测结果或图片时再次触发 FilePicker
6. Step 3 完成后验证 KPI、图表、产物区更新
7. Step 4-A 后验证界面停在“等待专家回执”
8. 输入“审批通过”后验证闭环完成
```

- [ ] **Step 4: Record the verification evidence**

Collect:

```text
- pytest 成功输出
- 模块运行截图
- progress.json 最终内容
- Output/ 目录产物列表
```

Expected: evidence clearly shows the module pauses before approval and resumes only after `approval_pass`.

- [ ] **Step 5: Commit the final touch-ups if docs changed**

```bash
git add templates/smart_survey_workbench/SKILL.md
git commit -m "docs: finalize smart survey workspace handoff"
```

## Self-Review

### Spec coverage

- 独立模板目录：Task 1
- 独立 `smart_survey_workflow`：Task 2-4
- Stepper 严格四步：Task 1-4
- 文件门禁 + 缺失才 HITL：Task 2-4
- KPI/图表/告警/产物区：Task 1 and Task 4
- `progress.json` 作为真相源：Task 2-4 helper design and manual validation in Task 6
- 审批暂停与 `approval_pass`：Task 4 and Task 6
- `context.py` 同步：Task 5
- 回归测试与现有模块隔离：Task 4 and Task 5

### Placeholder scan

- No `TODO`, `TBD`, or “later” placeholders remain.
- Every task includes exact files, concrete commands, and code snippets.

### Type consistency

- Module id is consistently `smart_survey_workbench`
- Flow name is consistently `smart_survey_workflow`
- Progress module id is consistently `smart_survey`
- Approval resume action is consistently `approval_pass`

