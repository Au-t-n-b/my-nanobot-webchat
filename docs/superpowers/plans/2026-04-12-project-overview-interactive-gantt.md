# Project Overview Interactive Gantt Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the project overview's simplified stage lane with a realtime, read-only interactive gantt chart driven by `task_progress.json`.

**Architecture:** Keep the existing `/api/task-status` and `TaskStatusUpdate` SSE path as the only source of truth, and add a `frappe-gantt` anti-corruption layer on the frontend. The new gantt is isolated behind `ProjectGanttChart` and `ProjectGanttCanvas`, while pure task mapping, view mode, and pan/zoom logic live under `frontend/lib/projectGantt`.

**Tech Stack:** Next.js 15, React 19, TypeScript, Tailwind CSS, `frappe-gantt`

---

### Task 1: Add Gantt Dependency And Theme Shell

**Files:**
- Modify: `frontend/package.json`
- Modify: `frontend/package-lock.json`
- Create: `frontend/components/dashboard/frappe/frappe-gantt-theme.css`

- [ ] **Step 1: Add the gantt dependency**

Add `frappe-gantt` to `frontend/package.json` dependencies.

- [ ] **Step 2: Install the dependency**

Run:

```powershell
& 'C:\nvm4w\nodejs\npm.cmd' install frappe-gantt --prefix frontend
```

Expected: package installs successfully and updates `frontend/package-lock.json`.

- [ ] **Step 3: Create the gantt theme shell**

Create `frontend/components/dashboard/frappe/frappe-gantt-theme.css` with CSS variables and container rules for:

```css
.frappe-gantt-scroll-shell {}
.frappe-gantt-host {}
.frappe-gantt-shell .grid-header { position: sticky; top: 0; z-index: 2; }
```

- [ ] **Step 4: Verify the dependency is present**

Run:

```powershell
Test-Path 'D:\code\nanobot\frontend\node_modules\frappe-gantt'
```

Expected: `True`

### Task 2: Build The Mapping Layer

**Files:**
- Create: `frontend/lib/projectGantt/taskStatusToFrappeTasks.ts`
- Create: `frontend/lib/projectGantt/frappeViewModes.ts`
- Test: `frontend/lib/projectGantt/taskStatusToFrappeTasks.test.ts`

- [ ] **Step 1: Write a failing mapping test**

Add a test that verifies:

- task-status modules become one gantt task per module
- pending modules get stable inferred dates
- running modules keep stable inferred dates across repeated inputs
- completed modules derive progress `100`

- [ ] **Step 2: Run the test and confirm it fails**

Run:

```powershell
& 'C:\nvm4w\nodejs\npm.cmd' run lint --prefix frontend
```

Expected: the new test or new imports fail before implementation exists.

- [ ] **Step 3: Implement the mapping helpers**

Create pure helpers that:

- map `TaskStatusPayload["modules"]` to `frappe-gantt` task payloads
- infer stable `start` / `end` dates from status and cached anchors
- define `year / month / week / day` view-mode metadata

- [ ] **Step 4: Re-run verification**

Run:

```powershell
& 'C:\nvm4w\nodejs\npm.cmd' run lint --prefix frontend
```

Expected: no type/lint issues from the new mapping layer.

### Task 3: Build The Canvas And Toolbar

**Files:**
- Create: `frontend/components/dashboard/frappe/ProjectGanttCanvas.tsx`
- Create: `frontend/components/dashboard/frappe/GanttChartToolbar.tsx`
- Create: `frontend/lib/projectGantt/ganttPanZoom.ts`
- Create: `frontend/lib/projectGantt/ganttChrome.ts`

- [ ] **Step 1: Create the toolbar**

Add a presentational toolbar for:

- year / month / week / day
- zoom display
- scroll-to-today

- [ ] **Step 2: Create the Frappe host component**

Implement a host component that:

- creates one `Gantt` instance via `useEffect`
- stores the instance in `useRef`
- calls `gantt.refresh(tasks)` on data changes
- cleans up listeners on unmount

- [ ] **Step 3: Add pan and zoom helpers**

Implement shell-level mouse drag panning and wheel zoom, while filtering out bar and button targets to avoid interaction conflicts.

- [ ] **Step 4: Re-run verification**

Run:

```powershell
& 'C:\nvm4w\nodejs\npm.cmd' run lint --prefix frontend
```

Expected: new gantt components compile cleanly.

### Task 4: Wire Project Overview To The New Gantt

**Files:**
- Create: `frontend/components/dashboard/ProjectGanttChart.tsx`
- Modify: `frontend/components/dashboard/ProjectOverview.tsx`

- [ ] **Step 1: Add the project overview wrapper**

Create `ProjectGanttChart.tsx` that:

- reads `taskStatus` from `projectOverviewStore`
- maps modules to gantt tasks
- passes click events back to `onSelectModule`

- [ ] **Step 2: Replace the simplified lane chart**

Update `ProjectOverview.tsx` to render `ProjectGanttChart` in the “项目阶段甘特图” slot instead of `SduiGanttLane`.

- [ ] **Step 3: Keep existing summary rows**

Preserve the text summary rows under the chart so the user still sees `progressLabel` and `done/total` at a glance.

- [ ] **Step 4: Re-run verification**

Run:

```powershell
& 'C:\nvm4w\nodejs\npm.cmd' run lint --prefix frontend
```

Expected: project overview remains type-safe after the chart swap.

### Task 5: Smoke-Check Runtime Behavior

**Files:**
- Verify only

- [ ] **Step 1: Start or reuse the local dev app**

Use the already running local app if available.

- [ ] **Step 2: Refresh the project overview page**

Check these behaviors manually:

```text
1. Gantt chart renders in the project overview card
2. Switching year/month/week/day changes the grid
3. Dragging empty canvas pans the chart
4. Wheel zoom changes chart scale
5. Clicking a module bar opens its module dashboard
6. When TaskStatusUpdate arrives, the bar refreshes without full chart flash
```

- [ ] **Step 3: Record environment limitation if needed**

If automated verification cannot be completed, use this note:

```text
Frontend lint/build verification depends on the local nvm4w Node installation; if that command cannot be executed in the current shell context, fall back to file review plus browser smoke testing.
```
