# Project Overview Control Plane Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a single source of truth for project overview state so module registry, task progress, overview navigation, and auto-guide all stay synchronized.

**Architecture:** Keep `/api/task-status` as the live project progress source, add a module-registry API for static module metadata, and move frontend consumers onto one client-side control-plane store. `useAgentChat` becomes the SSE ingestion entry, while `ProjectOverview` and `DashboardNavigator` become pure consumers plus navigation triggers.

**Tech Stack:** aiohttp, Python task-progress helpers, Next.js 15, React 19, TypeScript, client-side store implemented inside `frontend/lib` without adding new external state dependencies.

---

### Task 1: Add backend module registry endpoint

**Files:**
- Modify: `D:\code\nanobot\nanobot\web\routes.py`
- Modify: `D:\code\nanobot\nanobot\web\skills.py`
- Test: `D:\code\nanobot\nanobot\web\task_progress.py`

- [ ] **Step 1: Write the failing behavior check**

Expected contract:

```json
{
  "items": [
    {
      "moduleId": "intelligent_analysis_workbench",
      "label": "智能分析工作台",
      "description": "标准母版模块",
      "taskProgress": {
        "moduleId": "m_7",
        "moduleName": "智能分析工作台",
        "tasks": ["模块待启动", "分析目标已确认"]
      },
      "dashboard": {
        "docId": "intelligent_analysis_workbench.dashboard",
        "dataFile": "skills/intelligent_analysis_workbench/data/dashboard.json"
      }
    }
  ]
}
```

- [ ] **Step 2: Verify the route does not exist yet**

Run:

```powershell
rg -n "handle_modules|/api/modules" "D:\code\nanobot\nanobot\web\routes.py"
```

Expected: no existing handler for `/api/modules`

- [ ] **Step 3: Implement minimal registry helpers**

Add a helper that scans `get_skills_root()/*/module.json`, skips invalid entries, and returns normalized module registry items with:

```python
{
    "moduleId": module_id,
    "label": module_title,
    "description": description,
    "taskProgress": {
        "moduleId": task_progress_module_id,
        "moduleName": task_progress_module_name,
        "tasks": task_names,
    },
    "dashboard": {
        "docId": doc_id,
        "dataFile": data_file,
    },
}
```

- [ ] **Step 4: Expose `GET /api/modules`**

Register the route in `setup_routes()` and return:

```python
return web.json_response({"items": list_modules()})
```

- [ ] **Step 5: Verify the route wiring**

Run:

```powershell
rg -n "handle_modules|/api/modules" "D:\code\nanobot\nanobot\web\routes.py"
```

Expected: handler and route registration are both present

### Task 2: Add frontend control-plane store

**Files:**
- Create: `D:\code\nanobot\frontend\lib\projectOverviewStore.ts`
- Modify: `D:\code\nanobot\frontend\hooks\useAgentChat.ts`
- Test: `D:\code\nanobot\frontend\scripts\test-file-resolver.mjs`

- [ ] **Step 1: Write the failing store expectations**

Target behavior:

```ts
const empty = createProjectOverviewState();
empty.registry.items.length === 0;
empty.taskStatus === null;

const merged = mergeTaskStatusSnapshot(prev, incoming);
merged.modules.length >= prev.modules.length;
```

- [ ] **Step 2: Verify no existing project overview store exists**

Run:

```powershell
rg -n "projectOverviewStore|useProjectOverviewStore" "D:\code\nanobot\frontend"
```

Expected: no matches

- [ ] **Step 3: Implement the store module**

Implement a lightweight client store with:

```ts
type ProjectModuleRegistryItem = {
  moduleId: string;
  label: string;
  description: string;
  taskProgress: { moduleId: string; moduleName: string; tasks: string[] };
  dashboard: { docId: string; dataFile: string };
};

type ProjectOverviewState = {
  registry: { items: ProjectModuleRegistryItem[]; loaded: boolean };
  taskStatus: TaskStatusPayload | null;
  activeModuleId: string | null;
  autoGuidedModuleIds: string[];
};
```

and actions for:

```ts
hydrateProjectOverview()
applyTaskStatusSnapshot(payload)
selectProjectModule(moduleId)
markModuleAutoGuided(moduleId)
resetProjectOverviewForThread()
```

- [ ] **Step 4: Route SSE updates through the store**

When `TaskStatusUpdate` arrives in `useAgentChat`, continue exposing `taskStatusEvent` for compatibility, but also call:

```ts
applyTaskStatusSnapshot(data as TaskStatusPayload);
```

- [ ] **Step 5: Verify build-time type usage**

Run:

```powershell
rg -n "applyTaskStatusSnapshot|hydrateProjectOverview|selectProjectModule" "D:\code\nanobot\frontend"
```

Expected: store actions are referenced from hook/components, not left unused

### Task 3: Refactor `ProjectOverview` into a pure view

**Files:**
- Modify: `D:\code\nanobot\frontend\components\dashboard\ProjectOverview.tsx`
- Modify: `D:\code\nanobot\frontend\components\TaskProgressBar.tsx`

- [ ] **Step 1: Write the failing UI rules**

Expected behavior:

```tsx
// ProjectOverview should no longer own fetch/setInterval.
// Progress bars should derive from taskStatus steps, not hard-coded 60%.
```

- [ ] **Step 2: Verify polling code is still present**

Run:

```powershell
rg -n "setInterval|fetch\\(aguiRequestPath\\(\"/api/task-status\"\\)\" "D:\code\nanobot\frontend\components\dashboard\ProjectOverview.tsx" "D:\code\nanobot\frontend\components\TaskProgressBar.tsx"
```

Expected: matches exist before refactor

- [ ] **Step 3: Remove local polling and derive from store-fed data**

`ProjectOverview` should accept normalized registry + task snapshot props and compute:

```ts
progressPct = module.steps.length ? Math.round((doneCount / module.steps.length) * 100) : 0;
```

`TaskProgressBar` should stop polling and only render from `liveTaskStatus`.

- [ ] **Step 4: Keep the workbench CTA and gantt interaction**

Click actions should still call:

```ts
onSelectModule(moduleId)
```

but the displayed rows/cards should come from merged registry + task status data.

- [ ] **Step 5: Verify polling removal**

Run:

```powershell
rg -n "setInterval|fetch\\(aguiRequestPath\\(\"/api/task-status\"\\)\" "D:\code\nanobot\frontend\components\dashboard\ProjectOverview.tsx" "D:\code\nanobot\frontend\components\TaskProgressBar.tsx"
```

Expected: no matches

### Task 4: Wire dashboard navigation to the control plane

**Files:**
- Modify: `D:\code\nanobot\frontend\components\DashboardNavigator.tsx`
- Modify: `D:\code\nanobot\frontend\app\page.tsx`

- [ ] **Step 1: Write the failing navigation behavior**

Expected behavior:

```ts
// Clicking a module in the overview:
// 1. sets active module in shared store
// 2. switches to module view
// 3. sends guide once if module is still idle
```

- [ ] **Step 2: Verify guide dedupe is still local-only**

Run:

```powershell
rg -n "autoGuidedModulesRef|guide" "D:\code\nanobot\frontend\components\DashboardNavigator.tsx"
```

Expected: guide dedupe currently lives only inside `DashboardNavigator`

- [ ] **Step 3: Move selection and guide dedupe onto shared state**

Use the control-plane store to keep:

```ts
activeModuleId
autoGuidedModuleIds
```

and gate guide dispatch with the shared dedupe state so overview click, patch auto-open, and skill auto-open all reuse the same idempotency rule.

- [ ] **Step 4: Bootstrap registry load from the page shell**

On page load and thread creation/switch:

```ts
void hydrateProjectOverview();
resetProjectOverviewForThread();
```

Keep `useAgentChat` as the transport entry and `DashboardNavigator` as the view orchestrator.

- [ ] **Step 5: Verify navigation references**

Run:

```powershell
rg -n "activeModuleId|autoGuidedModuleIds|hydrateProjectOverview|selectProjectModule" "D:\code\nanobot\frontend\app\page.tsx" "D:\code\nanobot\frontend\components\DashboardNavigator.tsx"
```

Expected: dashboard shell and navigator both read the same control-plane actions/state

### Task 5: Verify the end-to-end project overview loop

**Files:**
- Verify: `D:\code\nanobot\frontend\components\dashboard\ProjectOverview.tsx`
- Verify: `D:\code\nanobot\frontend\components\DashboardNavigator.tsx`
- Verify: `D:\code\nanobot\nanobot\web\routes.py`

- [ ] **Step 1: Run backend route smoke check**

Run:

```powershell
rg -n "handle_modules|handle_task_status|/api/modules|/api/task-status" "D:\code\nanobot\nanobot\web\routes.py"
```

Expected: both module registry and task-status routes are present

- [ ] **Step 2: Run frontend reference check**

Run:

```powershell
rg -n "projectOverviewStore|hydrateProjectOverview|applyTaskStatusSnapshot|selectProjectModule" "D:\code\nanobot\frontend"
```

Expected: store is wired into hook, page shell, and overview/dashboard components

- [ ] **Step 3: Run a focused TypeScript lint/build check if available**

Run:

```powershell
npm run lint
```

Working directory:

```powershell
D:\code\nanobot\frontend
```

Expected: no type or lint errors introduced by the refactor

- [ ] **Step 4: Manual behavior check**

Verify manually in the app:

```text
1. 项目总览只展示已绑定模块
2. 模块卡片/甘特条显示真实进度，不再是假 60%
3. 模块执行时，总览随 TaskStatusUpdate 实时变化
4. 点击总览模块可切到模块大盘
5. 冷启动 guide 只发送一次，不因重渲染重复触发
```

- [ ] **Step 5: Commit**

```bash
git add D:/code/nanobot/docs/superpowers/plans/2026-04-12-project-overview-control-plane.md D:/code/nanobot/nanobot/web/routes.py D:/code/nanobot/nanobot/web/skills.py D:/code/nanobot/frontend/lib/projectOverviewStore.ts D:/code/nanobot/frontend/hooks/useAgentChat.ts D:/code/nanobot/frontend/components/dashboard/ProjectOverview.tsx D:/code/nanobot/frontend/components/DashboardNavigator.tsx D:/code/nanobot/frontend/components/TaskProgressBar.tsx D:/code/nanobot/frontend/app/page.tsx
git commit -m "feat: unify project overview control plane"
```
