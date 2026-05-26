# ZIP Archive Explorer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在右侧预览器中支持 `.zip` 目录树浏览，并可点击 ZIP 内条目按需解压单文件，以 **递归方式**复用现有 Preview 引擎完成渲染（无需二次网络请求）。

**Architecture:** 扩展 `PreviewKind` 支持 `zip`；在 `previewParsers` 中用 JSZip 只读目录元数据构树；引入 `PreviewFileViewer`（单文件壳）与 `ParserContext.initialBuffer`，使嵌套预览可注入内存中的 ArrayBuffer 绕过 `/api/file` fetch；新增 `ArchiveRenderer` 左树右览并按需解压单 entry。

**Tech Stack:** Next.js/React、TypeScript、现有 preview（resolver/parsers/renderers）、新增 `jszip`

---

## File Structure（将创建/修改的文件）

**Create:**
- `d:\code\nanobot\frontend\components\preview\PreviewFileViewer.tsx`（单文件预览壳，支持 `initialBuffer`）
- `d:\code\nanobot\frontend\components\preview\renderers\ArchiveRenderer.tsx`（ZIP 左树右览）

**Modify:**
- `d:\code\nanobot\frontend\package.json`（新增依赖 `jszip`）
- `d:\code\nanobot\frontend\lib\previewKind.ts`（增加 `zip` kind）
- `d:\code\nanobot\frontend\components\preview\previewResolver.ts`（`zip` -> `fetch:"arrayBuffer"`）
- `d:\code\nanobot\frontend\components\preview\previewTypes.ts`（`ParserContext` + 扩展 `PreviewParser` 签名）
- `d:\code\nanobot\frontend\components\preview\previewParsers.ts`（新增 `zip` parser；arrayBuffer/text 支持 `initialBuffer` 短路）
- `d:\code\nanobot\frontend\components\preview\PreviewPanel.tsx`（内部改用 `PreviewFileViewer` 渲染 active tab；新增 `zip` 分支渲染 ArchiveRenderer）

**Verify:**
- `d:\code\nanobot\frontend`：`npx tsc --noEmit`
- `d:\code\nanobot`：`python -m pytest tests/web -q`

---

### Task 1: 引入 JSZip 依赖

**Files:**
- Modify: `d:\code\nanobot\frontend\package.json`

- [ ] **Step 1: 更新依赖**

将 `jszip` 添加到 dependencies（不锁死小版本，遵循现有依赖风格）：

```json
{
  "dependencies": {
    "jszip": "^3.10.1"
  }
}
```

- [ ] **Step 2: 安装依赖**

Run:
- `cd d:\code\nanobot\frontend`
- `npm install`

Expected: 安装成功，无新增构建错误。

- [ ] **Step 3: Commit**

```bash
git add frontend/package.json frontend/package-lock.json
git commit -m "chore(frontend): 添加 jszip 依赖用于 ZIP 预览"
```

---

### Task 2: 扩展 PreviewKind 支持 `zip`

**Files:**
- Modify: `d:\code\nanobot\frontend\lib\previewKind.ts`

- [ ] **Step 1: 增加 kind 与扩展名映射**

把 `PreviewKind` union 增加 `"zip"`，并在 `previewKindFromPath()` 中识别 `.zip`：

```ts
export type PreviewKind =
  | "zip"
  | /* existing kinds ... */;

// ...
if (ext === "zip") return "zip";
```

- [ ] **Step 2: 运行类型检查**

Run: `cd d:\code\nanobot\frontend && npx tsc --noEmit`

Expected: PASS。

- [ ] **Step 3: Commit**

```bash
git add frontend/lib/previewKind.ts
git commit -m "feat(preview): 支持 zip 作为 PreviewKind"
```

---

### Task 3: Resolver 为 `zip` 指定 `fetch:"arrayBuffer"`

**Files:**
- Modify: `d:\code\nanobot\frontend\components\preview\previewResolver.ts`

- [ ] **Step 1: 更新 resolvePreview**

让 `zip` 与 `docx/xlsx` 一样走 arrayBuffer：

```ts
if (kind === "xlsx" || kind === "docx" || kind === "zip") {
  return { path, kind, url, fetch: "arrayBuffer" };
}
```

- [ ] **Step 2: 运行类型检查**

Run: `cd d:\code\nanobot\frontend && npx tsc --noEmit`

Expected: PASS。

- [ ] **Step 3: Commit**

```bash
git add frontend/components/preview/previewResolver.ts
git commit -m "refactor(preview): zip 预览使用 arrayBuffer 预取策略"
```

---

### Task 4: 扩展 Parser 契约（ParserContext + initialBuffer）

**Files:**
- Modify: `d:\code\nanobot\frontend\components\preview\previewTypes.ts`

- [ ] **Step 1: 新增 ParserContext 与更新 PreviewParser 签名**

```ts
export interface ParserContext {
  initialBuffer?: ArrayBuffer;
}

export type PreviewParser<T = unknown> = (
  resolution: PreviewResolution,
  context?: ParserContext,
) => Promise<T>;
```

- [ ] **Step 2: 全局修复 previewParsers 对 PreviewParser 的使用**

确保 `previewParsers.ts` 里所有 parser/registry 的调用都兼容第二个参数（先不使用也可以）。

- [ ] **Step 3: 运行类型检查**

Run: `cd d:\code\nanobot\frontend && npx tsc --noEmit`

Expected: PASS。

- [ ] **Step 4: Commit**

```bash
git add frontend/components/preview/previewTypes.ts frontend/components/preview/previewParsers.ts
git commit -m "refactor(preview): parser 支持 initialBuffer 注入上下文"
```

---

### Task 5: 新增 `PreviewFileViewer`（单文件壳，支持 initialBuffer）

**Files:**
- Create: `d:\code\nanobot\frontend\components\preview\PreviewFileViewer.tsx`
- Modify: `d:\code\nanobot\frontend\components\preview\PreviewPanel.tsx`
- Modify: `d:\code\nanobot\frontend\components\preview\previewParsers.ts`

- [ ] **Step 1: 抽出单文件 viewer**

把当前 `PreviewPanel.tsx` 内部用于单文件的逻辑抽成：

```ts
export type PreviewFileViewerProps = {
  path: string;
  onOpenPath: (path: string) => void;
  activeSkillName?: string | null;
  onFillInput?: (text: string) => void;
  initialBuffer?: ArrayBuffer;
};
```

内部流程保持现状：`resolvePreview(path)` → parser → renderers。

- [ ] **Step 2: 在 PreviewPanel 中使用 PreviewFileViewer**

`PreviewPanel` 仍然负责 tabs；active tab 的内容改为：

```tsx
<PreviewFileViewer path={activeTab.path} ... />
```

- [ ] **Step 3: 在 parsers 里实现 initialBuffer 短路**

新增统一 helper：

```ts
async function fetchOrUseArrayBuffer(
  resolution: PreviewResolution,
  context?: ParserContext,
): Promise<ArrayBuffer> {
  if (context?.initialBuffer) return context.initialBuffer;
  const res = await fetchOk(resolution);
  return await res.arrayBuffer();
}
```

并将 `docx/xlsx/zip` 等 arrayBuffer parser 统一改为使用它。

对于 text（md/text/mermaid/json/csv），可保持 fetch；但为了支持 ZIP 内 `.md/.csv/.json` 的嵌套预览，应增加：

```ts
async function fetchOrUseText(resolution, context): Promise<string> {
  if (context?.initialBuffer) {
    return new TextDecoder("utf-8", { fatal: false }).decode(context.initialBuffer);
  }
  const res = await fetchOk(resolution);
  return await res.text();
}
```

并在 payload warning 中增加建议文案（若乱码：下载查看）。

- [ ] **Step 4: 运行类型检查**

Run: `cd d:\code\nanobot\frontend && npx tsc --noEmit`

Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add frontend/components/preview/PreviewFileViewer.tsx frontend/components/preview/PreviewPanel.tsx frontend/components/preview/previewParsers.ts
git commit -m "refactor(preview): 引入 PreviewFileViewer 并支持 initialBuffer 免请求预览"
```

---

### Task 6: ZIP Parser（只读目录树 + JSZip instance）

**Files:**
- Modify: `d:\code\nanobot\frontend\components\preview\previewParsers.ts`

- [ ] **Step 1: 定义 ZipTreeNode / ZipArchivePayload**

```ts
type ZipTreeNode =
  | { type: "dir"; name: string; path: string; children: ZipTreeNode[] }
  | { type: "file"; name: string; path: string; size?: number };

type ZipArchivePayload = {
  type: "zip";
  tree: ZipTreeNode;
  zip: JSZip;
  totalFiles: number;
  isTruncated: boolean;
  warning?: string;
};
```

- [ ] **Step 2: 实现 buildZipTree**

从 `Object.keys(zip.files)` 构建树；超过 `MAX_ZIP_ENTRIES=1000` 时停止并标记截断；排序：目录在前、文件在后、按 name。

- [ ] **Step 3: 注册到 parserRegistry**

```ts
parserRegistry.zip = async (resolution, context) => { ... };
```

ZIP parser 必须通过 `fetchOrUseArrayBuffer(resolution, context)` 获取 ZIP buffer（便于未来也支持 nested zip）。

- [ ] **Step 4: 运行类型检查**

Run: `cd d:\code\nanobot\frontend && npx tsc --noEmit`

Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add frontend/components/preview/previewParsers.ts
git commit -m "feat(preview): 新增 zip parser（目录树 + 按需解压 handle）"
```

---

### Task 7: ArchiveRenderer（左树右览 + 递归嵌套预览）

**Files:**
- Create: `d:\code\nanobot\frontend\components\preview\renderers\ArchiveRenderer.tsx`
- Modify: `d:\code\nanobot\frontend\components\preview\PreviewFileViewer.tsx`

- [ ] **Step 1: 实现目录树 UI（最小可用）**

要求：
- 目录可展开/收起（local state: openPaths Set）
- 文件可点击
- 如果 payload.isTruncated=true，顶部展示 warning banner

- [ ] **Step 2: 按需解压单文件并嵌套预览**

点击 file node：
- `zip.file(node.path)?.async("arraybuffer")`
- 保存到 state：`activeFile = { path: node.path, buffer }`

右侧渲染：
- 返回按钮：清空 activeFile
- `PreviewFileViewer path={activeFile.path} initialBuffer={activeFile.buffer} ...`

注意：
- entry 过大（例如 buffer > 10MB）应提示并拒绝渲染（避免 OOM）。
- 若文本解码乱码，提示用户下载查看（不引入 iconv 依赖）。

- [ ] **Step 3: 将 zip payload 路由到 ArchiveRenderer**

在 `PreviewFileViewer`（或其 payload switch）中新增：

```ts
if (payload.type === "zip") return <ArchiveRenderer ... />;
```

- [ ] **Step 4: 运行类型检查**

Run: `cd d:\code\nanobot\frontend && npx tsc --noEmit`

Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add frontend/components/preview/renderers/ArchiveRenderer.tsx frontend/components/preview/PreviewFileViewer.tsx
git commit -m "feat(preview): ZIP Archive Explorer（左树右览 + 递归嵌套预览）"
```

---

### Task 8: 验证与回归检查

**Files:**
- Verify: `d:\code\nanobot\frontend` / `d:\code\nanobot\tests\web`

- [ ] **Step 1: Typecheck**

Run: `cd d:\code\nanobot\frontend && npx tsc --noEmit`
Expected: PASS

- [ ] **Step 2: Backend tests (sanity)**

Run: `cd d:\code\nanobot && python -m pytest tests/web -q`
Expected: PASS（允许现有 skip）

- [ ] **Step 3: 手工 Smoke（ZIP）**

准备一个小 ZIP（包含：`a.md`、`b.json`、`c.xlsx`、`d.docx`、`img.png`）：
- 右侧打开 ZIP：能看到树
- 点击文件：右侧嵌套预览能工作（不触发二次 `/api/file?path=<entry>` 请求）
- 返回目录：tree 状态保留（展开状态可选保留）

- [ ] **Step 4: Commit（如有修复）**

如 smoke 暴露问题，按最小修复提交。

---

## Plan Self-Review

- Spec coverage：覆盖 `.zip` kind、JSZip 解析、tree payload、递归嵌套预览、initialBuffer 注入、阈值与降级。
- Placeholder scan：无 “TBD/TODO/handle edge cases” 空话；阈值与输出结构已写死。
- Type consistency：`PreviewParser` 签名与 registry 调用在 Task 4-7 统一使用。

