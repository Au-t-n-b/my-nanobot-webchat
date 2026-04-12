# Shell Entry Relayout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move shell-level controls into the chat header, add explicit left/right panel toggles, and merge configuration/settings into one unified control-center entry without breaking existing module and preview flows.

**Architecture:** Keep existing panel implementations intact and introduce a thin wrapper panel for the merged control center. Update the page shell to promote frequently used actions into the top-right toolbar while leaving sidebar, preview, and remote asset detail/upload flows functionally unchanged.

**Tech Stack:** Next.js, React, TypeScript, Lucide

---

### Task 1: Add unified control-center wrapper

**Files:**
- Create: `D:\code\nanobot\frontend\components\ControlCenterPanel.tsx`
- Modify: `D:\code\nanobot\frontend\components\SettingsPanel.tsx`
- Modify: `D:\code\nanobot\frontend\components\ConfigPanel.tsx`

- [ ] Expose the existing settings/config content cleanly for embedding in a shared modal.
- [ ] Add a lightweight tabbed wrapper that hosts both panels.

### Task 2: Move desktop shell actions into header toolbar

**Files:**
- Modify: `D:\code\nanobot\frontend\app\page.tsx`

- [ ] Replace separate settings/config modal state with a unified control-center state.
- [ ] Add header actions for left nav, right preview, artifacts, skills, theme, and control center.
- [ ] Remove duplicated bottom-left utility buttons from the collapsed nav rail.

### Task 3: Verify interaction paths

**Files:**
- Modify: `D:\code\nanobot\frontend\app\page.tsx`

- [ ] Confirm keyboard escape behavior still closes the correct modal/panel.
- [ ] Confirm preview expand/collapse and remote upload/detail entry points still work.
