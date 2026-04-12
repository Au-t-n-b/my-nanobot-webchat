# Intelligent Analysis Workbench Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a project-guided, full-capability demo module called `intelligent_analysis_workbench` that showcases HITL, real uploads, streaming dashboard updates, parallel analysis, serial synthesis, and artifact presentation.

**Architecture:** Project-level guidance comes from `task_progress.json` and the task-status API, while module-level execution comes from a new module runtime flow plus SDUI dashboard patches. The chat area owns interactive cards and upload previews; the right dashboard owns runtime progress, metrics, and final artifacts.

**Tech Stack:** Python, aiohttp, pytest, React, TypeScript, SDUI v3 patches

---

### Task 1: Define the new workbench contract

**Files:**
- Create: `D:\code\nanobot\templates\intelligent_analysis_workbench\module.json`
- Create: `D:\code\nanobot\templates\intelligent_analysis_workbench\data\dashboard.json`
- Create: `D:\code\nanobot\templates\intelligent_analysis_workbench\SKILL.md`
- Create: `D:\code\nanobot\templates\intelligent_analysis_workbench\references\flow.md`
- Test: `D:\code\nanobot\tests\test_module_skill_runtime.py`

- [ ] Write failing tests for loading the new module config and expected flow name.
- [ ] Run the targeted runtime tests and confirm they fail because the module does not exist yet.
- [ ] Add the minimal template files for `intelligent_analysis_workbench`.
- [ ] Re-run the targeted tests and confirm the config loads.

### Task 2: Add project-level task-progress guidance

**Files:**
- Modify: `D:\code\nanobot\nanobot\web\routes.py`
- Modify: `D:\code\nanobot\tests\web\test_task_status.py`

- [ ] Write failing tests that expect the default task-progress payload to include the intelligent analysis workbench stage module.
- [ ] Run the task-status tests and confirm failure.
- [ ] Update the default task-progress payload and normalization logic so the workbench appears as a project stage by default.
- [ ] Re-run the task-status tests and confirm pass.

### Task 3: Implement the workbench runtime flow

**Files:**
- Modify: `D:\code\nanobot\nanobot\web\module_skill_runtime.py`
- Modify: `D:\code\nanobot\nanobot\web\mission_control.py`
- Test: `D:\code\nanobot\tests\test_module_skill_runtime.py`

- [ ] Write failing tests for the new flow actions: `guide`, `select_goal`, `upload_bundle`, `run_parallel_skills`, `synthesize_result`, `finish`.
- [ ] Run the targeted runtime tests and confirm failure.
- [ ] Implement the new flow with GuidanceCard, ChoiceCard, FilePicker, upload preview replacement, streaming stepper updates, and final artifact generation.
- [ ] Re-run the targeted runtime tests and confirm pass.

### Task 4: Represent upload preview and streaming dashboard progress

**Files:**
- Modify: `D:\code\nanobot\frontend\components\sdui\FilePicker.tsx`
- Modify: `D:\code\nanobot\frontend\components\dashboard\ModuleDashboard.tsx`
- Modify: `D:\code\nanobot\frontend\components\sdui\SduiStepper.tsx`
- Modify: `D:\code\nanobot\frontend\components\dashboard\ProjectOverview.tsx`

- [ ] Write or extend focused tests for upload preview replacement and stepper streaming states where the current harness allows it.
- [ ] Update the chat/upload UI to show structured file preview capsules after upload.
- [ ] Update the dashboard visuals so partial patches feel progressive instead of blink-and-jump.
- [ ] Verify the workbench module is discoverable from project overview and opens the right dashboard.

### Task 5: Add the parallel-plus-serial analysis narrative

**Files:**
- Modify: `D:\code\nanobot\nanobot\web\module_skill_runtime.py`
- Modify: `D:\code\nanobot\templates\intelligent_analysis_workbench\references\flow.md`
- Test: `D:\code\nanobot\tests\test_module_skill_runtime.py`

- [ ] Write failing tests that expect multiple analysis phases before synthesis.
- [ ] Run the targeted runtime tests and confirm failure.
- [ ] Implement a simulated or lightweight real parallel-analysis stage followed by a serial synthesis stage, with dashboard and summary updates for each phase.
- [ ] Re-run the targeted runtime tests and confirm pass.

### Task 6: Sync the live workspace module and verify end-to-end wiring

**Files:**
- Copy to: `C:\Users\华为\.nanobot\workspace\skills\intelligent_analysis_workbench\...`
- Modify: `D:\code\nanobot\docs/superpowers/specs/2026-04-11-intelligent-analysis-workbench-design.md`
- Modify: `D:\code\nanobot\docs/superpowers/plans/2026-04-11-intelligent-analysis-workbench.md`

- [ ] Sync the new template into the Nanobot workspace as a live module.
- [ ] Run targeted structural verification for repo files and workspace files.
- [ ] Check the spec and plan for consistency with the implementation and fix any drift inline.
