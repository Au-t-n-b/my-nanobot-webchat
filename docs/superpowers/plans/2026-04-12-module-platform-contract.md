# Module Platform Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the reusable module platform defined in the approved Scheme C design: config-validated modules, configurable HITL/upload/metrics/task-progress behavior, reusable uploaded-file pills, and an upgraded `intelligent_analysis_workbench` mother template.

**Architecture:** Keep project-level progress (`task_progress`) and module-level dashboards (`dashboard.json` + patch stream) separate. Move module variability into validated config and runtime conventions, while the platform owns upload, preview, patch, and task-progress synchronization. Reuse existing SDUI nodes wherever possible instead of inventing parallel widget systems.

**Tech Stack:** Python runtime (`aiohttp`, Nanobot web runtime), TypeScript/React frontend, SDUI v3 patch protocol, JSON Schema validation, existing test suites under `tests/`.

---

### Task 1: Add module config and dashboard schema validation

**Files:**
- Create: `D:\code\nanobot\nanobot\web\module_contract_schema.py`
- Modify: `D:\code\nanobot\nanobot\web\module_skill_runtime.py`
- Modify: `D:\code\nanobot\templates\intelligent_analysis_workbench\module.json`
- Test: `D:\code\nanobot\tests\test_module_skill_runtime.py`

- [ ] **Step 1: Write the failing validation tests**

```python
def test_load_module_config_rejects_missing_save_relative_dir(tmp_path):
    module_dir = tmp_path / "bad_module"
    module_dir.mkdir()
    (module_dir / "module.json").write_text(json.dumps({
        "moduleId": "bad_module",
        "flow": "intelligent_analysis_workbench",
        "docId": "skill-ui:bad",
        "dataFile": "skills/bad_module/data/dashboard.json",
        "uploads": [{"purpose": "bundle"}],
    }), encoding="utf-8")
    (module_dir / "data").mkdir()
    (module_dir / "data" / "dashboard.json").write_text(json.dumps({"type": "Page", "children": []}), encoding="utf-8")

    with pytest.raises(ValueError, match="save_relative_dir"):
        load_module_config("bad_module")


def test_load_module_config_rejects_missing_uploaded_files_node(tmp_path):
    module_dir = tmp_path / "bad_dashboard"
    module_dir.mkdir()
    (module_dir / "module.json").write_text(json.dumps({
        "moduleId": "bad_dashboard",
        "flow": "intelligent_analysis_workbench",
        "docId": "skill-ui:bad",
        "dataFile": "skills/bad_dashboard/data/dashboard.json",
    }), encoding="utf-8")
    (module_dir / "data").mkdir()
    (module_dir / "data" / "dashboard.json").write_text(json.dumps({
        "type": "Page",
        "children": [{"type": "Text", "id": "summary-text", "content": "x"}],
    }), encoding="utf-8")

    with pytest.raises(ValueError, match="uploaded-files"):
        load_module_config("bad_dashboard")
```

- [ ] **Step 2: Run the targeted tests to verify failure**

Run: `pytest tests/test_module_skill_runtime.py -k "save_relative_dir or uploaded_files_node" -v`

Expected: FAIL with missing validation because `load_module_config()` currently accepts malformed configs.

- [ ] **Step 3: Implement schema validation helpers**

```python
REQUIRED_DASHBOARD_NODE_IDS = {
    "stepper-main",
    "summary-text",
    "artifacts",
    "uploaded-files",
}


def validate_module_contract(raw: dict[str, Any]) -> dict[str, Any]:
    module_id = str(raw.get("moduleId") or "").strip()
    flow = str(raw.get("flow") or "").strip()
    doc_id = str(raw.get("docId") or "").strip()
    data_file = str(raw.get("dataFile") or "").strip()
    if not module_id or not flow or not doc_id or not data_file:
        raise ValueError("module.json missing required fields: moduleId, flow, docId, dataFile")
    for upload in raw.get("uploads", []):
        if not str(upload.get("save_relative_dir") or "").strip():
            raise ValueError("upload config missing save_relative_dir")
    return raw


def validate_dashboard_contract(document: dict[str, Any]) -> None:
    seen_ids: set[str] = set()

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            node_id = str(node.get("id") or "").strip()
            if node_id:
                seen_ids.add(node_id)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(document)
    missing = sorted(REQUIRED_DASHBOARD_NODE_IDS - seen_ids)
    if missing:
        raise ValueError(f"dashboard.json missing required node ids: {', '.join(missing)}")
```

- [ ] **Step 4: Wire validation into module loading**

```python
def load_module_config(module_id: str) -> dict[str, Any]:
    root = get_skills_root()
    module_dir = root / module_id.strip()
    path = module_dir / "module.json"
    if not path.is_file():
        raise FileNotFoundError(f"module.json missing: {path}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("module.json must be a JSON object")
    cfg = validate_module_contract(raw)

    dashboard_path = module_dir / "data" / "dashboard.json"
    dashboard = json.loads(dashboard_path.read_text(encoding="utf-8"))
    if not isinstance(dashboard, dict):
        raise ValueError("dashboard.json must be a JSON object")
    validate_dashboard_contract(dashboard)
    return cfg
```

- [ ] **Step 5: Re-run tests**

Run: `pytest tests/test_module_skill_runtime.py -k "save_relative_dir or uploaded_files_node" -v`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add nanobot/web/module_contract_schema.py nanobot/web/module_skill_runtime.py templates/intelligent_analysis_workbench/module.json tests/test_module_skill_runtime.py
git commit -m "feat: validate module contract and dashboard schema"
```

### Task 2: Make uploaded-file pills a first-class reusable SDUI pattern

**Files:**
- Modify: `D:\code\nanobot\frontend\components\sdui\SduiArtifactGrid.tsx`
- Modify: `D:\code\nanobot\frontend\lib\sdui.ts`
- Modify: `D:\code\nanobot\templates\intelligent_analysis_workbench\data\dashboard.json`
- Test: `D:\code\nanobot\frontend\components\sdui\SduiArtifactGrid.tsx`

- [ ] **Step 1: Add a failing component test or fixture case for input mode**

```tsx
const node = {
  type: "ArtifactGrid",
  mode: "input",
  artifacts: [
    { id: "u1", label: "资料清单.xlsx", path: "workspace/skills/demo/input/资料清单.xlsx", kind: "xlsx" },
  ],
} satisfies SduiArtifactGridNode;
```

Run expectation: input artifacts should render with uploaded-file copy and still call `openPreview(path)`.

- [ ] **Step 2: Update SDUI typings to support input/output modes**

```ts
export type SduiArtifactItem = {
  id?: string;
  label?: string;
  path?: string;
  kind?: string;
  status?: string;
};

export type SduiArtifactGridNode = {
  type: "ArtifactGrid";
  id?: string;
  title?: string;
  mode?: "input" | "output";
  artifacts: SduiArtifactItem[];
};
```

- [ ] **Step 3: Implement mode-aware visual treatment without changing preview behavior**

```tsx
export function SduiArtifactGrid({ artifacts, mode = "output", title }: Props) {
  const runtime = useSkillUiRuntime();
  const badgeLabel = mode === "input" ? "已上传文件" : "产物";
  const chipClass = mode === "input"
    ? "border-amber-500/30 bg-amber-500/10 text-amber-100"
    : "border-emerald-500/30 bg-emerald-500/10 text-emerald-100";

  return (
    <section>
      <div className="mb-2 text-xs ui-text-muted">{title ?? badgeLabel}</div>
      {normalizedArtifacts.map((a) => (
        <button key={a.id} className={chipClass} onClick={() => runtime.openPreview(a.path)}>
          {a.label}
        </button>
      ))}
    </section>
  );
}
```

- [ ] **Step 4: Add the uploaded-files region to the mother dashboard**

```json
{
  "type": "ArtifactGrid",
  "id": "uploaded-files",
  "title": "已上传文件",
  "mode": "input",
  "artifacts": []
}
```

- [ ] **Step 5: Manually verify the dashboard fixture shape**

Run: `rg -n "\"uploaded-files\"|\"mode\": \"input\"" templates/intelligent_analysis_workbench/data/dashboard.json frontend/components/sdui/SduiArtifactGrid.tsx frontend/lib/sdui.ts`

Expected: one dashboard node plus type support plus component support.

- [ ] **Step 6: Commit**

```bash
git add frontend/components/sdui/SduiArtifactGrid.tsx frontend/lib/sdui.ts templates/intelligent_analysis_workbench/data/dashboard.json
git commit -m "feat: reuse artifact grid for uploaded file pills"
```

### Task 3: Generalize upload state and preview wiring in the module runtime

**Files:**
- Modify: `D:\code\nanobot\nanobot\web\mission_control.py`
- Modify: `D:\code\nanobot\nanobot\web\module_skill_runtime.py`
- Modify: `D:\code\nanobot\frontend\components\sdui\FilePicker.tsx`
- Test: `D:\code\nanobot\tests\test_module_skill_runtime.py`
- Test: `D:\code\nanobot\tests\web\test_api_chat.py`

- [ ] **Step 1: Add failing runtime tests for uploads array and uploaded-files patch**

```python
def test_workbench_upload_writes_uploads_array_and_uploaded_files_patch(...):
    result = await run_module_action(
        module_id="intelligent_analysis_workbench",
        action="run_parallel_skills",
        state={"upload": {"fileId": "f1", "name": "资料.xlsx", "logicalPath": "workspace/skills/intelligent_analysis_workbench/input/资料.xlsx"}},
        thread_id="t-1",
        docman=docman,
    )
    assert result["ok"] is True
    assert latest_patch_contains_node("uploaded-files")
    assert session_state["uploads"][0]["logicalPath"].endswith("资料.xlsx")
```

- [ ] **Step 2: Run the targeted tests to verify failure**

Run: `pytest tests/test_module_skill_runtime.py -k "uploads_array or uploaded_files_patch" -v`

Expected: FAIL because current runtime only stores a single `upload` object and does not patch `uploaded-files`.

- [ ] **Step 3: Normalize upload records in the FilePicker callback**

```tsx
state: {
  uploads: [{
    fileId,
    name: file.name,
    logicalPath,
    savedDir: saveRelativeDir,
    uploadedAt: Date.now(),
  }],
  upload: {
    fileId,
    name: file.name,
    logicalPath,
  },
}
```

- [ ] **Step 4: Add runtime helpers to merge uploads and build input artifact entries**

```python
def _merge_uploads(existing: Any, incoming: Any) -> list[dict[str, Any]]:
    prev = existing if isinstance(existing, list) else []
    nxt = incoming if isinstance(incoming, list) else []
    seen: set[str] = set()
    merged: list[dict[str, Any]] = []
    for item in prev + nxt:
        if not isinstance(item, dict):
            continue
        path = str(item.get("logicalPath") or "").strip()
        if not path or path in seen:
            continue
        seen.add(path)
        merged.append(item)
    return merged


def _uploads_as_artifacts(uploads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "id": str(item.get("fileId") or item.get("logicalPath") or f"upload-{idx}"),
            "label": str(item.get("name") or "未命名文件"),
            "path": str(item.get("logicalPath") or ""),
            "kind": Path(str(item.get("name") or "")).suffix.lstrip(".") or "file",
            "status": "ready",
        }
        for idx, item in enumerate(uploads, start=1)
        if str(item.get("logicalPath") or "").strip()
    ]
```

- [ ] **Step 5: Patch both the chat card replacement and the dashboard uploaded-files node**

```python
uploads = _merge_uploads(sess.get("uploads"), state.get("uploads"))
merge_module_session(thread_id, module_id, {"uploads": uploads})
await pusher.update_node(
    "uploaded-files",
    "ArtifactGrid",
    {"title": "已上传文件", "mode": "input", "artifacts": _uploads_as_artifacts(uploads)},
)
```

- [ ] **Step 6: Re-run backend tests**

Run: `pytest tests/test_module_skill_runtime.py -k "uploads_array or uploaded_files_patch" -v`

Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add nanobot/web/mission_control.py nanobot/web/module_skill_runtime.py frontend/components/sdui/FilePicker.tsx tests/test_module_skill_runtime.py tests/web/test_api_chat.py
git commit -m "feat: sync uploaded files into chat and dashboard"
```

### Task 4: Make task_progress config-driven and action-based

**Files:**
- Modify: `D:\code\nanobot\nanobot\web\module_skill_runtime.py`
- Modify: `D:\code\nanobot\web\task_progress.py`
- Modify: `D:\code\nanobot\templates\intelligent_analysis_workbench\module.json`
- Test: `D:\code\nanobot\tests\web\test_task_status.py`
- Test: `D:\code\nanobot\tests\test_module_skill_runtime.py`

- [ ] **Step 1: Write failing tests for action-to-task mapping**

```python
def test_module_action_updates_task_progress_from_config(...):
    result = await run_module_action(
        module_id="intelligent_analysis_workbench",
        action="upload_bundle",
        state={"standard": "comprehensive"},
        thread_id="thread-1",
        docman=docman,
    )
    payload = load_task_status_payload()
    module = next(item for item in payload["modules"] if item["id"] == "intelligent_analysis_workbench")
    assert any(step["name"] == "分析目标已确认" and step["done"] for step in module["steps"])
```

- [ ] **Step 2: Run the targeted tests to verify failure**

Run: `pytest tests/web/test_task_status.py tests/test_module_skill_runtime.py -k "task_progress_from_config" -v`

Expected: FAIL because progress is currently hard-coded per flow.

- [ ] **Step 3: Move hard-coded progress logic behind a generic helper**

```python
def _configured_completed_tasks(cfg: dict[str, Any], action: str) -> set[str]:
    task_cfg = cfg.get("taskProgress") if isinstance(cfg.get("taskProgress"), dict) else {}
    mapping = task_cfg.get("actionMapping") if isinstance(task_cfg.get("actionMapping"), dict) else {}
    names = mapping.get(action)
    if not isinstance(names, list):
        return set()
    return {str(item).strip() for item in names if str(item).strip()}
```

- [ ] **Step 4: Replace flow-specific progress updates with config-driven calls**

```python
completed_names = _configured_completed_tasks(cfg, action)
if completed_names:
    await _set_project_progress_and_emit(case_cfg["module_title"], completed_names)
```

- [ ] **Step 5: Add the taskProgress block to the mother template**

```json
"taskProgress": {
  "moduleId": "intelligent_analysis_workbench",
  "moduleName": "智能分析工作台",
  "tasks": [
    "模块待启动",
    "分析目标已确认",
    "资料已上传",
    "并行分析进行中",
    "结论汇总中",
    "分析完成"
  ],
  "actionMapping": {
    "guide": ["模块待启动"],
    "upload_bundle": ["模块待启动", "分析目标已确认"],
    "run_parallel_skills": ["模块待启动", "分析目标已确认", "资料已上传", "并行分析进行中"],
    "synthesize_result": ["模块待启动", "分析目标已确认", "资料已上传", "并行分析进行中", "结论汇总中"],
    "finish": ["模块待启动", "分析目标已确认", "资料已上传", "并行分析进行中", "结论汇总中", "分析完成"]
  }
}
```

- [ ] **Step 6: Re-run tests**

Run: `pytest tests/web/test_task_status.py tests/test_module_skill_runtime.py -k "task_progress_from_config" -v`

Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add nanobot/web/module_skill_runtime.py nanobot/web/task_progress.py templates/intelligent_analysis_workbench/module.json tests/web/test_task_status.py tests/test_module_skill_runtime.py
git commit -m "feat: drive task progress from module config"
```

### Task 5: Upgrade the intelligent analysis workbench mother template and document the contract

**Files:**
- Modify: `D:\code\nanobot\templates\intelligent_analysis_workbench\module.json`
- Modify: `D:\code\nanobot\templates\intelligent_analysis_workbench\data\dashboard.json`
- Modify: `D:\code\nanobot\templates\intelligent_analysis_workbench\SKILL.md`
- Modify: `D:\code\nanobot\templates\intelligent_analysis_workbench\references\flow.md`
- Modify: `D:\code\nanobot\docs\superpowers\specs\2026-04-12-module-platform-contract-design.md`
- Test: `D:\code\nanobot\tests\test_module_skill_runtime.py`

- [ ] **Step 1: Update the mother template config to showcase configurable module abilities**

```json
"capabilities": {
  "hitl": true,
  "uploads": true,
  "metrics": ["kpi_cards", "bar_chart", "donut_chart", "embedded_web"],
  "skillOrchestration": ["serial", "parallel", "hybrid"],
  "taskProgressAutoSync": true
}
```

- [ ] **Step 2: Update the dashboard skeleton to show the canonical zones**

```json
[
  { "type": "Stepper", "id": "stepper-main", "steps": [] },
  { "type": "GoldenMetrics", "id": "golden-metrics", "metrics": [] },
  { "type": "BarChart", "id": "chart-bar", "data": [] },
  { "type": "ArtifactGrid", "id": "uploaded-files", "title": "已上传文件", "mode": "input", "artifacts": [] },
  { "type": "Text", "id": "summary-text", "content": "" },
  { "type": "ArtifactGrid", "id": "artifacts", "title": "作业结果", "mode": "output", "artifacts": [] }
]
```

- [ ] **Step 3: Rewrite the template guidance docs for downstream developers**

```md
## 模块开发者可配置项

- HITL 选项和下一步动作
- 上传文件类型与保存路径
- 黄金指标表现形式
- 串行 / 并行 / 混合 skill 编排
- task_progress 任务映射
```

- [ ] **Step 4: Run regression tests for the mother template flow**

Run: `pytest tests/test_module_skill_runtime.py -k "intelligent_analysis_workbench" -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add templates/intelligent_analysis_workbench/module.json templates/intelligent_analysis_workbench/data/dashboard.json templates/intelligent_analysis_workbench/SKILL.md templates/intelligent_analysis_workbench/references/flow.md docs/superpowers/specs/2026-04-12-module-platform-contract-design.md tests/test_module_skill_runtime.py
git commit -m "docs: finalize module platform mother template"
```

### Task 6: End-to-end verification and workspace sync

**Files:**
- Modify: `D:\code\nanobot\tests\web\test_api_chat.py`
- Modify: `D:\code\nanobot\tests\web\test_task_status.py`
- Modify: `D:\code\nanobot\scripts\verify_bootstrap_sse.py`
- Sync target: `C:\Users\华为\.nanobot\workspace\skills\intelligent_analysis_workbench`

- [ ] **Step 1: Add an integration test that covers guide -> upload -> preview -> task progress**

```python
def test_module_case_emits_uploaded_files_and_task_status(client):
    # create thread, trigger module_action, then assert SSE includes:
    # - SkillUiChatCard with FilePicker
    # - SkillUiDataPatch for uploaded-files
    # - TaskStatusUpdate after action success
    ...
```

- [ ] **Step 2: Run the relevant verification suites**

Run: `pytest tests/test_module_skill_runtime.py tests/web/test_api_chat.py tests/web/test_task_status.py -v`

Expected: PASS

- [ ] **Step 3: Sync the updated mother template into the runtime workspace**

Run:

```powershell
& 'C:\Program Files\PowerShell\7\pwsh.exe' -Command "$src = 'D:\code\nanobot\templates\intelligent_analysis_workbench'; $dst = 'C:\Users\华为\.nanobot\workspace\skills\intelligent_analysis_workbench'; New-Item -ItemType Directory -Force -Path $dst | Out-Null; Copy-Item -LiteralPath (Join-Path $src 'module.json') -Destination (Join-Path $dst 'module.json') -Force; Copy-Item -LiteralPath (Join-Path $src 'data\dashboard.json') -Destination (Join-Path $dst 'data\dashboard.json') -Force; Copy-Item -LiteralPath (Join-Path $src 'SKILL.md') -Destination (Join-Path $dst 'SKILL.md') -Force; Copy-Item -LiteralPath (Join-Path $src 'references\flow.md') -Destination (Join-Path $dst 'references\flow.md') -Force"
```

Expected: workspace template files are updated without touching unrelated modules.

- [ ] **Step 4: Manual smoke test in the app**

Run checklist:

```text
1. Open a new thread.
2. Enter the intelligent analysis workbench.
3. Trigger a configurable HITL choice.
4. Upload a real file into the configured save_relative_dir.
5. Confirm chat pills and dashboard uploaded-files both appear.
6. Click a pill and verify right-panel preview opens.
7. Confirm project overview progress updates after each action.
```

- [ ] **Step 5: Commit**

```bash
git add tests/web/test_api_chat.py tests/web/test_task_status.py scripts/verify_bootstrap_sse.py
git commit -m "test: verify module platform end to end"
```
