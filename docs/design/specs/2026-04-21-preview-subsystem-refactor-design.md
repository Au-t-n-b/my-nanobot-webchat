# 分屏预览子系统（Preview Subsystem）重构设计稿

**日期**：2026-04-21  
**范围**：Phase 0（仅重构抽象与目录结构，不改变预览行为与功能）  
**目标用户**：Nanobot AGUI / Workbench 右侧分屏预览（文件、网页、表格、代码等）

---

## Goal（目标）

将现有 `PreviewPanel.tsx` 从“巨石组件（策略 + 拉取 + 渲染）”拆分为高内聚的预览领域模块：

- `PreviewPanel`：仅负责 UI 骨架、状态机与通用错误展示
- `previewResolver`：负责“策略决策”（path → kind / url / meta / policy）
- `renderers/*`：按 kind 插件化渲染器（docx/xlsx/md/pdf/image/binary 等）

并将代码从单文件迁移到独立领域目录 `frontend/components/preview/`，**全量更新引用**，不保留旧 re-export。

---

## Non-goals（非目标）

- 不新增任何新格式/新功能（json/csv 表格、zip 浏览等留给 Phase 1+）
- 不引入新的协议（agent-view:// 等留给 Phase 3+）
- 不改变后端 `/api/file` 行为或路径规范

---

## Architecture（架构概览）

### 目录结构（最终形态）

```
frontend/components/preview/
├── index.ts
├── PreviewPanel.tsx
├── previewResolver.ts
├── previewTypes.ts
└── renderers/
    ├── ImageRenderer.tsx
    ├── IframeRenderer.tsx
    ├── MarkdownRenderer.tsx
    ├── CodeRenderer.tsx
    ├── XlsxRenderer.tsx
    ├── DocxRenderer.tsx
    ├── MermaidRenderer.tsx
    └── FallbackRenderer.tsx
```

### 核心接口

#### `PreviewKind`

与当前实现一致（browser/image/pdf/html/md/text/code/xlsx/docx/mermaid/binary/skill-ui 等），Phase 0 不新增 kind。

#### `PreviewResolution`

`previewResolver` 的输出，表达“怎么预览”：

- `kind`: PreviewKind
- `url?`: `/api/file?path=...` 或 browser:// 等
- `path`: 原始输入 path
- `meta?`: 可选（lang、contentType hint、title 等）

#### `Renderer`

渲染器只关心“拿到什么 URL/内容怎么展示”，不负责策略判断。

---

## Data flow（数据流）

1. Workbench/ChatArea 调用 `PreviewPanel` 打开某个 `path`
2. `PreviewPanel` 调用 `resolvePreview(path)` 获取 `PreviewResolution`
3. `PreviewPanel` 根据 `kind` 选择渲染器并渲染
4. 渲染器内部按需要 fetch `/api/file`（文本/arrayBuffer）并渲染（mammoth/XLSX/mermaid 等）

---

## Risks & Governance（风险与治理）

- **风险：回归**：Phase 0 仅拆分搬迁，必须通过 `npx tsc --noEmit` 与现有 `tests/web`（后端）保持绿灯；前端无测试用例时，通过人工 smoke（docx/xlsx/md/pdf）验证。
- **风险：import 路径变更**：选择“全量更新引用”，避免遗留 re-export 技术债；需要一次性改完所有 `@/components/PreviewPanel` 引用。
- **可观测性**：保持现有错误提示逻辑不变；Phase 1 再引入标准化 error code。

---

## Entry points（最该改的 3 个入口点）

1. `frontend/components/PreviewPanel.tsx`：拆分并迁移为领域模块壳
2. `frontend/lib/previewKind.ts`：继续作为路径→kind 的基础类型判定（Phase 0 保持原样，Phase 1 扩展策略）
3. `frontend/lib/apiFile.ts`：统一构造 `/api/file` URL，渲染器复用

---

## Acceptance（验收标准）

- 所有对 `PreviewPanel` 的引用均指向 `frontend/components/preview` 的出口（无旧路径残留）
- 行为一致：docx/xlsx/md/pdf/html/image/binary 的现有预览无明显变化
- `npx tsc --noEmit` 通过

