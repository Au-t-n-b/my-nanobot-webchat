# ZIP Archive Explorer（压缩包浏览器）设计稿

**日期**：2026-04-21  
**阶段**：Phase 2（ZIP 目录树预览 + 递归嵌套预览）  
**目标**：在右侧预览器中支持 `.zip`（只读目录树），点击条目按需解压单个文件并复用现有 Preview 引擎渲染。

---

## Goal（目标）

- **ZIP 预览**：对 `.zip` 文件展示目录树（文件/文件夹），不落盘、不走后端解压。
- **按需抽血**：点击某个 entry 时，**只解压该 entry** 到内存（ArrayBuffer），不解压整个 ZIP。
- **递归预览**：复用现有 Preview 子系统（resolver + parsers + renderers），在 ArchiveRenderer 内部嵌套预览选中的 entry。
- **安全与性能**：避免 OOM / DOM 爆炸 / zip bomb 的最小防御（阈值 + 降级提示）。

---

## Non-goals（非目标）

- 不支持写入/编辑 ZIP 内容（只读）。
- 不支持预览 `.zip` 内的“嵌套压缩包递归解压”（Phase 2 仅做一层；后续可扩展）。
- 不做“完整文件系统”能力（重命名/删除/拖拽等）。

---

## Constraints（硬约束）

沿用当前 Preview 子系统的三条 Contract：

1. **Renderers 无副作用**：不 fetch、不读全局 store、不读 URL 参数；只吃 props 输出 UI。
2. **Resolver 纯函数**：同 path 输入 => 同 resolution 输出。
3. **统一 Props 协议**：所有 renderer 通过统一的 `BaseRendererProps` 接口协作。

ZIP 特有约束：

- 只允许通过 `/api/file?path=...` 拉取 ZIP 的 ArrayBuffer（与现有文件预览一致）。
- ZIP 的“解压”行为只能发生在前端内存，且**必须**可中断/可限制规模。

---

## 核心设计（推荐方案）

### 1) PreviewKind 扩展

- 在 `previewKindFromPath()` 增加 `zip` kind（基于 `.zip` 扩展名）。
- `resolvePreview(path)` 对 `zip` 返回 `fetch: "arrayBuffer"`（ZIP 一律以 ArrayBuffer 进入 parser）。

### 2) Parser：`zip` 只读骨架（JSZip）

**依赖**：使用 `jszip`（API 适合按需解压：`zip.file(name).async("arraybuffer")`）。

**Parser 输入**：`PreviewResolution`（含 `url`）。  
**Parser 输出**：`ZipArchivePayload`（仅包含目录树 + 可按需解压的 handle + 元数据）。

建议输出形态：

```ts
type ZipTreeNode =
  | { type: "dir"; name: string; path: string; children: ZipTreeNode[] }
  | { type: "file"; name: string; path: string; size?: number };

type ZipArchivePayload = {
  type: "zip";
  tree: ZipTreeNode;          // 根节点（dir）
  totalFiles: number;
  isTruncated: boolean;       // tree 截断标识（避免 DOM 爆炸）
  warning?: string;           // 例如 “仅展示前 1000 个条目”
  zip: JSZip;                 // 仅存在于前端内存（不可序列化）；用于按需解压单文件
};
```

**阈值建议**（Phase 2 最小防御）：

- `MAX_ZIP_ENTRIES = 1000`：构树时超过即停止并标记截断（同时输出 warning）。
- `MAX_ENTRY_BYTES = 10MB`：点击解压单 entry 前先读元信息（若可得），超过则提示并拒绝解压（防 OOM）。

> 说明：ZIP entry size 在 JSZip 的元数据中可得性不稳定；如果拿不到，就在解压后对 buffer 做 size check 并立刻丢弃 + 提示。

### 3) Renderer：`ArchiveRenderer`（左树右预览）

布局：

- 左侧：目录树（可折叠）；顶部可选搜索框（只过滤 name/path，Phase 2 可以先不做）。
- 右侧：当选中文件时，进入“嵌套预览”视图；提供返回按钮（清空选中）。

交互：

- 点击 `dir`：展开/收起
- 点击 `file`：触发 `zip.file(node.path).async("arraybuffer")` 解压单个文件 -> 得到 `ArrayBuffer`
- 将 `{ path: node.path, buffer }` 存入本地 state

### 4) 递归预览接口：支持 `initialBuffer`

为了不走网络二次 fetch，需要给 Preview 引擎提供一个“本地内容注入”口子。

推荐新增一个新的、面向单文件的壳组件（不含 Tab UI），供 ArchiveRenderer 与未来其它场景复用：

```ts
type PreviewFileViewerProps = {
  path: string;
  onOpenPath: (path: string) => void;
  activeSkillName?: string | null;
  onFillInput?: (text: string) => void;
  initialBuffer?: ArrayBuffer; // 若提供，parser 应优先使用它而不是 fetch(resolution.url)
};
```

实现原则：

- `PreviewPanel`（带 tabs 的外壳）保持不变，仅内部使用 `PreviewFileViewer`。
- `previewParsers` 新增一个“数据源”约定：当 kind 需要 arrayBuffer 时，如果 `initialBuffer` 存在，则跳过 fetch。
- 对 text 类型（json/csv/普通文本）未来也可扩展 `initialText`，但 Phase 2 只要求 arrayBuffer（ZIP entry 常见是二进制）。

---

## 方案对比（2-3 种）

### 方案 A（推荐）：JSZip + ZipPayload 持有 zip 实例 + PreviewFileViewer(initialBuffer)

- **优点**：实现最直接；“递归魔法”路径最短；不需要全局缓存；与现有 parser/renderers 分层一致。
- **缺点**：payload 持有不可序列化对象（JSZip 实例），但它只在 React state 内存在，符合前端现实。

### 方案 B：JSZip 实例放入模块级 WeakMap（key=zipPath），payload 只带 token

- **优点**：payload 更“纯数据”；更像可序列化协议。
- **缺点**：引入隐藏全局状态与生命周期复杂度（清理、同名冲突、热更新行为），违背“纯净架构”精神。

### 方案 C：后端解压（不推荐）

- **优点**：前端简单。
- **缺点**：慢、占磁盘、要清理、带安全风险，与本项目追求的“前端只读骨架”方向相悖。

---

## Error handling（错误与降级）

- ZIP 拉取失败：复用现有 error UI。
- ZIP 解析失败（损坏/加密/格式异常）：提示 “无法解析 ZIP” + 下载链接（binary fallback）。
- 目录条目过多：只展示前 `MAX_ZIP_ENTRIES`，顶部 warning。
- 单 entry 过大：拒绝解压并提示下载原文件。

---

## Security notes（安全提示）

- **Zip bomb**：通过 entry 数量阈值 + entry size 阈值进行最小防御。
- **路径安全**：ZIP 内路径仅作为 UI/逻辑键，不写入文件系统；无目录穿越风险。
- **HTML/script**：若 zip 内含 `.html`，仍按现有 html iframe 预览；后续可评估是否需要额外沙箱策略。

---

## Acceptance（验收标准）

- `.zip` 在右侧可展示目录树
- 点击任意小文件（如 `.md` / `.json` / `.docx` / `.xlsx`）可在右侧嵌套预览，且不触发 `/api/file?path=entry` 的二次请求
- 大 ZIP / 大 entry 有明确降级提示，不导致页面卡死或明显内存暴涨

