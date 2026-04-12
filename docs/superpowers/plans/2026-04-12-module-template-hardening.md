# Module Template Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden the `intelligent_analysis_workbench` module template so it demonstrates production-ready HITL upload cards, uploaded-file capsules, smooth streaming dashboard updates, and reliable project-overview synchronization.

**Architecture:** Keep project overview state on `task_progress` / `TaskStatusUpdate`, keep module dashboard state on SDUI patch, and force both to update at the same action boundary. Upgrade the existing `FilePicker` and `ArtifactGrid` instead of introducing parallel component systems.

**Tech Stack:** React/Next.js frontend, SDUI v3 patch protocol, Python `aiohttp` backend runtime, existing Nanobot module runtime and task-progress helpers.

---

### Task 1: Harden upload card behavior and multi-file state

**Files:**
- Modify: `D:\code\nanobot\frontend\components\sdui\FilePicker.tsx`
- Modify: `D:\code\nanobot\nanobot\web\mission_control.py`
- Modify: `D:\code\nanobot\nanobot\web\module_skill_runtime.py`
- Test: `D:\code\nanobot\frontend\components\sdui\FilePicker.tsx`

- [ ] **Step 1: Write the failing upload behavior test**

```tsx
it("keeps upload card appendable when multiple=true", async () => {
  render(
    <SduiFilePicker
      purpose="analysis_bundle"
      multiple
      moduleId="intelligent_analysis_workbench"
      nextAction="after_upload"
      cardId="upload-card-1"
      saveRelativeDir="skills/intelligent_analysis_workbench/input"
    />,
  );
  expect(screen.getByText("选择文件")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run the focused test to verify the current mismatch**

Run: `npm run lint`

Expected: existing repo warnings may remain, but current implementation still shows the upload card locking after one success and only processing the first selected file.

- [ ] **Step 3: Refactor `FilePicker` state to track an uploads array**

```tsx
type UploadedFile = {
  fileId: string;
  name: string;
  logicalPath?: string;
  savedDir?: string;
  uploadedAt: number;
};

const [uploadedFiles, setUploadedFiles] = useState<UploadedFile[]>([]);
```

- [ ] **Step 4: Process all selected files when `multiple=true` and preserve append behavior**

```tsx
const selected = multiple ? files : files.slice(0, 1);
for (const file of selected) {
  const uploaded = await uploadOne(file);
  nextUploads.push({
    fileId: uploaded.fileId,
    name: file.name,
    logicalPath: uploaded.logicalPath,
    savedDir: saveRelativeDir,
    uploadedAt: Date.now(),
  });
}
```

- [ ] **Step 5: Send both `upload` and `uploads` back to the module action**

```tsx
postToAgent(JSON.stringify({
  type: "chat_card_intent",
  verb: "module_action",
  cardId: cid,
  payload: {
    moduleId: mid,
    action: na,
    state: {
      upload: nextUploads[nextUploads.length - 1],
      uploads: nextUploads,
    },
  },
}));
```

- [ ] **Step 6: Update helper copy so the card clearly advertises drag/drop, append, and target directory**

```python
fp_node["helpText"] = (
    f"将文件拖到下方区域或点击选择；可多次追加上传；保存目录（workspace 相对）：{save_dir}/<文件名>"
    if save_dir
    else "将文件拖到下方区域或点击选择；上传成功后会同步会话、大盘和下一步状态。"
)
```

### Task 2: Make uploaded-file capsules visible in both chat and dashboard

**Files:**
- Modify: `D:\code\nanobot\frontend\components\sdui\SduiArtifactGrid.tsx`
- Modify: `D:\code\nanobot\nanobot\web\module_skill_runtime.py`
- Modify: `D:\code\nanobot\templates\intelligent_analysis_workbench\data\dashboard.json`

- [ ] **Step 1: Keep `ArtifactGrid` mode-aware but stable-keyed**

```tsx
const key = a.id || `${a.path}:${index}`;
```

- [ ] **Step 2: Ensure input mode uses the same preview click behavior as output mode**

```tsx
onClick={() => {
  if (!canPreview(a.path)) return;
  runtime.openPreview(a.path);
}}
```

- [ ] **Step 3: Ensure workbench upload actions always patch `uploaded-files`**

```python
(
    BoilerplateDashboardIds.UPLOADED_FILES,
    "ArtifactGrid",
    {"title": "已上传文件", "mode": "input", "artifacts": _uploads_as_artifacts(uploads)},
)
```

- [ ] **Step 4: Ensure chat-side replacement cards also show uploaded pills**

```python
await mc.replace_card(
    card_id=cid,
    title="资料已上传",
    node={
        "type": "Stack",
        "gap": "sm",
        "children": [
            {"type": "Text", "variant": "body", "content": f"已接收 {upload_name}，可继续追加资料或进入下一步。"},
            {"type": "ArtifactGrid", "title": "已上传文件", "mode": "input", "artifacts": _uploads_as_artifacts(uploads)},
        ],
    },
)
```

### Task 3: Remove dashboard flash by stabilizing patch targets

**Files:**
- Modify: `D:\code\nanobot\frontend\components\SkillUiWrapper.tsx`
- Modify: `D:\code\nanobot\frontend\components\sdui\SduiNodeView.tsx`
- Modify: `D:\code\nanobot\frontend\lib\sduiKeys.ts`
- Modify: `D:\code\nanobot\frontend\app\globals.css`

- [ ] **Step 1: Confirm only `id`-backed nodes participate in patch-driven animated regions**

```ts
if (typeof rawId === "string" && rawId.trim()) {
  return `id:${rawId.trim()}`;
}
```

- [ ] **Step 2: Pass `docId` into `SkillUiRuntimeProvider` so internal sync is not silently disabled**

```tsx
const resolvedDocId =
  baseDoc?.meta && typeof baseDoc.meta.docId === "string" ? baseDoc.meta.docId : undefined;

<SkillUiRuntimeProvider
  postToAgentRaw={postToAgentRaw}
  onOpenPreview={onOpenPreview}
  docId={resolvedDocId}
  enableInternalSync
>
```

- [ ] **Step 3: Reduce whole-node partial styling and favor property transitions**

```css
.sdui-patch-target {
  transition: color 0.28s ease, background-color 0.28s ease, border-color 0.28s ease, box-shadow 0.28s ease;
}

.sdui-partial {
  filter: none;
}
```

- [ ] **Step 4: Keep chart transitions on SVG attributes**

```tsx
style={{
  transition:
    "x 420ms cubic-bezier(0.4, 0, 0.2, 1), y 420ms cubic-bezier(0.4, 0, 0.2, 1), height 420ms cubic-bezier(0.4, 0, 0.2, 1)"
}}
```

### Task 4: Make stepper progress feel continuous instead of snapshot-jumping

**Files:**
- Modify: `D:\code\nanobot\frontend\components\sdui\SduiStepper.tsx`
- Modify: `D:\code\nanobot\frontend\app\globals.css`
- Modify: `D:\code\nanobot\nanobot\web\module_skill_runtime.py`

- [ ] **Step 1: Inspect current stepper fill element and attach a stable transition class**

```tsx
<div className="sdui-stepper-bar-fill" style={{ width: `${pct}%` }} />
```

- [ ] **Step 2: Add CSS for continuous width interpolation**

```css
.sdui-stepper-bar-fill {
  transition: width 0.5s linear;
}
```

- [ ] **Step 3: Break long workbench phases into more than one partial patch**

```python
await pusher.update_nodes([...], is_partial=True)
await asyncio.sleep(0.45)
await pusher.update_nodes([...], is_partial=True)
await asyncio.sleep(0.45)
await pusher.update_nodes([...], is_partial=False)
```

### Task 5: Reconcile module progress with project overview

**Files:**
- Modify: `D:\code\nanobot\nanobot\web\module_skill_runtime.py`
- Modify: `D:\code\nanobot\frontend\lib\projectOverviewStore.ts`
- Modify: `D:\code\nanobot\templates\intelligent_analysis_workbench\module.json`

- [ ] **Step 1: Ensure task-progress matching prefers configured `taskProgress.moduleId` but still falls back by name**

```ts
return (
  modules.find((item) => item.id === registryItem.taskProgress.moduleId) ??
  modules.find((item) => item.name === registryItem.taskProgress.moduleName) ??
  modules.find((item) => item.id === registryItem.moduleId) ??
  null
);
```

- [ ] **Step 2: Ensure runtime always emits task progress on `guide`, upload, parallel run, synthesize, and finish**

```python
await _set_project_progress_and_emit(
    progress_module_name,
    _configured_completed_tasks(cfg, action, fallback_names, module_name=progress_module_name),
    cfg,
)
```

- [ ] **Step 3: Verify the configured task mapping still points at `智能分析工作台` and not an orphan module**

```json
"taskProgress": {
  "moduleId": "intelligent_analysis_workbench",
  "moduleName": "智能分析工作台"
}
```

### Task 6: Verify the hardened template end to end

**Files:**
- Verify: `D:\code\nanobot\frontend\components\sdui\FilePicker.tsx`
- Verify: `D:\code\nanobot\frontend\components\SkillUiWrapper.tsx`
- Verify: `D:\code\nanobot\nanobot\web\module_skill_runtime.py`
- Verify: `D:\code\nanobot\templates\intelligent_analysis_workbench\data\dashboard.json`

- [ ] **Step 1: Run focused regression test for donut safety**

Run: `node --test .\scripts\test-sdui-donut.mjs`

Expected: PASS

- [ ] **Step 2: Run frontend lint to catch local regressions**

Run: `npm run lint`

Expected: existing repo warnings may remain, but no new errors from the touched files.

- [ ] **Step 3: Manual workflow verification**

Run:

```text
1. 打开项目总览
2. 进入“智能分析工作台”
3. 选择一个分析目标
4. 拖拽上传 2 个文件
5. 观察会话胶囊、大盘胶囊、总览进度和右侧图表是否同步推进
```

Expected:

- 上传卡片支持拖拽和追加
- 会话与大盘都显示输入胶囊
- 图表和 Stepper 平滑变化
- 项目总览进度同步推进到对应阶段
