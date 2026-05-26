# Job Management Plan Progress Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep the existing `job_management` dashboard UX while executing the real `plan_progress` skill backend and streaming mapped progress into the dashboard.

**Architecture:** The existing `job_management` flow stays in place as the UI shell. A new adapter inside `nanobot/web/module_skill_runtime.py` validates required files under the workspace `plan_progress/input` folder, launches the `plan_progress` orchestrator, reads its sidecar flow events, and translates them into the existing four dashboard steps plus project task progress.

**Tech Stack:** Python async runtime, existing `MissionControlManager`, `SkillUiPatchPusher`, workspace skill scripts, Node tests, pytest-style runtime tests

---

### Task 1: Lock file-gate behavior with tests

**Files:**
- Modify: `D:\code\nanobot\tests\test_module_skill_runtime.py`
- Test: `D:\code\nanobot\tests\test_module_skill_runtime.py`

- [ ] **Step 1: Write the failing test**

```python
@pytest.mark.asyncio
async def test_job_management_upload_bundle_requests_missing_required_files(...):
    r = await run_module_action(
        module_id="job_management",
        action="upload_bundle",
        state={},
        thread_id="thread-job-missing-files",
        docman=None,
    )
    assert r.get("ok") is True
    assert r.get("next") == "upload_bundle_complete"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_module_skill_runtime.py -k job_management_upload_bundle_requests_missing_required_files -v`
Expected: FAIL because current `job_management` flow does not validate strict filenames under `skills/plan_progress/input`

- [ ] **Step 3: Write minimal implementation**

```python
def _plan_progress_required_inputs() -> list[str]:
    return ["到货表.xlsx", "人员信息表.xlsx"]

def _plan_progress_input_dir() -> Path:
    return get_skills_root() / "plan_progress" / "input"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_module_skill_runtime.py -k job_management_upload_bundle_requests_missing_required_files -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_module_skill_runtime.py nanobot/web/module_skill_runtime.py
git commit -m "test: cover job management required input gating"
```

### Task 2: Lock stage mapping with tests

**Files:**
- Modify: `D:\code\nanobot\tests\test_module_skill_runtime.py`
- Test: `D:\code\nanobot\tests\test_module_skill_runtime.py`

- [ ] **Step 1: Write the failing test**

```python
@pytest.mark.asyncio
async def test_job_management_maps_plan_progress_stage_events_to_dashboard(...):
    result = _job_management_dashboard_state_from_flow_event(
        stage_id="s3_schedule",
        status="running",
        message="Stage3 排期开始执行",
    )
    assert result["active_step"] == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_module_skill_runtime.py -k job_management_maps_plan_progress_stage_events_to_dashboard -v`
Expected: FAIL because no mapping helper exists yet

- [ ] **Step 3: Write minimal implementation**

```python
def _job_management_stage_index(stage_id: str) -> int:
    mapping = {
        "s1_preplan": 1,
        "s2_multiround": 1,
        "s2_observe_demand": 1,
        "s3_milestone": 2,
        "s3_schedule": 2,
        "s3_reflection": 3,
    }
    return mapping.get(stage_id, 0)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_module_skill_runtime.py -k job_management_maps_plan_progress_stage_events_to_dashboard -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_module_skill_runtime.py nanobot/web/module_skill_runtime.py
git commit -m "test: cover job management stage mapping"
```

### Task 3: Implement plan_progress adapter in runtime

**Files:**
- Modify: `D:\code\nanobot\nanobot\web\module_skill_runtime.py`
- Test: `D:\code\nanobot\tests\test_module_skill_runtime.py`

- [ ] **Step 1: Write the failing test**

```python
@pytest.mark.asyncio
async def test_job_management_confirm_planning_schedule_runs_plan_progress_adapter(...):
    r = await run_module_action(
        module_id="job_management",
        action="confirm_planning_schedule",
        state={},
        thread_id="thread-job-stage12",
        docman=None,
    )
    assert r.get("ok") is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_module_skill_runtime.py -k job_management_confirm_planning_schedule_runs_plan_progress_adapter -v`
Expected: FAIL because current flow does not call `plan_progress`

- [ ] **Step 3: Write minimal implementation**

```python
async def _run_plan_progress_stage12(...):
    cmd = [
        python_bin,
        str(plan_progress_root / "scripts" / "run_all_stages.py"),
        "--bundle-path",
        str(bundle_path),
        "--prompt-xlsx",
        str(prompt_xlsx),
    ]
    proc = await asyncio.create_subprocess_exec(*cmd, ...)
    return await proc.wait()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_module_skill_runtime.py -k job_management_confirm_planning_schedule_runs_plan_progress_adapter -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add nanobot/web/module_skill_runtime.py tests/test_module_skill_runtime.py
git commit -m "feat: run plan progress from job management"
```

### Task 4: Update template docs and prompts

**Files:**
- Modify: `D:\code\nanobot\templates\job_management\references\flow.md`
- Modify: `D:\code\nanobot\templates\job_management\module.json`
- Modify: `D:\code\nanobot\nanobot\agent\context.py`

- [ ] **Step 1: Write the failing test**

```python
def test_job_management_module_config_mentions_plan_progress():
    cfg = load_module_config("job_management")
    assert cfg["uploads"][0]["purpose"] == "job_bundle"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_module_skill_runtime.py -k job_management_module_config_mentions_plan_progress -v`
Expected: FAIL until docs/config are updated consistently

- [ ] **Step 3: Write minimal implementation**

```json
{
  "moduleGoal": "以 plan_progress 作为实际作业编排引擎..."
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_module_skill_runtime.py -k job_management_module_config_mentions_plan_progress -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add templates/job_management/module.json templates/job_management/references/flow.md nanobot/agent/context.py
git commit -m "docs: document job management plan progress integration"
```

### Task 5: Verify targeted behavior and sync workspace skill if needed

**Files:**
- Modify: `D:\code\nanobot\tests\test_module_skill_runtime.py`

- [ ] **Step 1: Write the failing test**

```python
@pytest.mark.asyncio
async def test_job_management_finish_marks_all_steps_complete(...):
    r = await run_module_action(
        module_id="job_management",
        action="finish",
        state={},
        thread_id="thread-job-finish",
        docman=None,
    )
    assert r.get("done") is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_module_skill_runtime.py -k job_management_finish_marks_all_steps_complete -v`
Expected: FAIL until final task progress mapping matches the new adapter flow

- [ ] **Step 3: Write minimal implementation**

```python
await _set_project_progress_and_emit(
    progress_module_name,
    {"作业待启动", "资料已上传", "规划设计排期已确认", "工程安装排期已确认", "集群联调排期已确认", "作业闭环完成"},
    cfg,
)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_module_skill_runtime.py -k job_management -v`
Expected: PASS for the targeted job-management integration tests

- [ ] **Step 5: Commit**

```bash
git add nanobot/web/module_skill_runtime.py tests/test_module_skill_runtime.py
git commit -m "test: verify job management plan progress completion"
```

