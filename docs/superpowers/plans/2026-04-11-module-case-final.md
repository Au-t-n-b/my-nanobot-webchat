# Module Case Final Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a final Nanobot module case that streams dashboard progress, supports HITL/file upload, and promotes top-level task progress into project overview.

**Architecture:** The backend module runtime becomes the single source for module-level streaming patches, while `/api/task-status` becomes the aggregation source for project-level progress. The frontend keeps module dashboards and project overview separate, but both consume aligned status semantics.

**Tech Stack:** Python, aiohttp, pytest, React, TypeScript, SDUI v3 patches

---

### Task 1: Lock protocol and progress aggregation behavior

**Files:**
- Modify: `D:\code\nanobot\tests\test_module_skill_runtime.py`
- Modify: `D:\code\nanobot\tests\web\test_task_status.py`

- [ ] Step 1: Add failing runtime assertions for streamed dashboard updates
- [ ] Step 2: Run targeted runtime tests and confirm failure
- [ ] Step 3: Add failing task-status assertions for project overview aggregation
- [ ] Step 4: Run targeted task-status tests and confirm failure

### Task 2: Implement backend streaming progress and project summary data

**Files:**
- Modify: `D:\code\nanobot\nanobot\web\module_skill_runtime.py`
- Modify: `D:\code\nanobot\nanobot\web\routes.py`
- Modify: `D:\code\nanobot\nanobot\web\skill_ui_patch.py`

- [ ] Step 1: Add backend helpers for partial/stable patch emission
- [ ] Step 2: Update `zhgk_module_case` flow to emit phased progress, metric, and summary patches
- [ ] Step 3: Extend task-status normalization with overview-friendly summary fields
- [ ] Step 4: Re-run targeted backend tests

### Task 3: Implement frontend project overview and dashboard polish

**Files:**
- Modify: `D:\code\nanobot\frontend\components\dashboard\ProjectOverview.tsx`
- Modify: `D:\code\nanobot\frontend\components\TaskProgressBar.tsx`
- Modify: `D:\code\nanobot\frontend\components\sdui\SduiStepper.tsx`

- [ ] Step 1: Update project overview to consume the richer task-status payload
- [ ] Step 2: De-emphasize duplicated top-bar progress and align semantics with overview
- [ ] Step 3: Improve stepper visual feedback for running/done states and streamed detail
- [ ] Step 4: Verify the changed paths compile and behave coherently

### Task 4: Finish the zhgk reference module and workspace sync

**Files:**
- Modify: `D:\code\nanobot\templates\zhgk_module_case\module.json`
- Modify: `D:\code\nanobot\templates\zhgk_module_case\data\dashboard.json`
- Modify: `D:\code\nanobot\templates\zhgk_module_case\SKILL.md`
- Modify: `D:\code\nanobot\templates\zhgk_module_case\references\flow.md`

- [ ] Step 1: Refine the template copy and dashboard placeholders around the final protocol
- [ ] Step 2: Sync the updated template to `C:\Users\华为\.nanobot\workspace\skills\zhgk_module_case`
- [ ] Step 3: Run targeted verification against repo files and workspace files

### Task 5: Verification and handoff

**Files:**
- Modify: `D:\code\nanobot\docs/superpowers/specs/2026-04-11-module-case-final-design.md`
- Modify: `D:\code\nanobot\docs/superpowers/plans/2026-04-11-module-case-final.md`

- [ ] Step 1: Re-check that implementation still matches the written design
- [ ] Step 2: Run the final targeted verification commands
- [ ] Step 3: Summarize what was verified, what was synced, and any remaining local-environment gaps
