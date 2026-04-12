# SDUI v3.0 Visual Stream（“视觉流”）设计说明（Milestone-2）

**目标**：让 SDUI UI 能像文字一样“流式长出来”（Visual Stream），避免等待全量 JSON 准备好后瞬时闪现。  
**范围（你已确认 B）**：仅支持对以下数组字段做追加：

- **容器节点**：`children[]`（`Stack` / `Row` / `Card` / `Tabs.tab.children` 等递归子树）
- **表格组件**：`DataGrid.rows[]`

**硬护栏**：

- 不改动现有业务逻辑链路（Session/Skill/SSE 主流程不动）
- Patch 仍以 `docId + revision` 做幂等与防串台
- 仅允许白名单字段 append；其他结构字段仍禁止（避免变成“任意 JSON 解释器”）

---

## 1. 背景与现状

当前 SDUI v3 (M1) 已支持 `SduiPatch`（`merge/replace/remove`），且前端 `applySduiPatch` 有明确护栏：**不允许 patch `children` / `tabs`**，以避免结构性变更造成卸载/闪烁/一致性问题。

Visual Stream 属于 **M2**：在严格受控范围内开放“结构性增量”（append），让列表/容器可增量生长。

---

## 2. 协议扩展：`append` op + `isPartial`

### 2.1 Patch Envelope 扩展（SkillUiDataPatch）

在补丁 envelope 中新增：

- **`isPartial: boolean`**：标记本 patch 是否为“生成中片段”。
  - `true`：流式片段（前端可呈现 skeleton/pulse）
  - `false`：稳定状态（结束流式、清理视觉态）

建议位置：`patch.isPartial`（与 `revision/docId/ops` 同层），因为它描述的是 **整批 ops 的语义**。

### 2.2 新 op：`append`

新增 op：

- `op: "append"`
- `target`：仍以 `by="id"` 寻址节点，同时指定数组字段：
  - `target: { by: "id"; nodeId: string; field: "children" | "rows" }`
- `value`：
  - 若 `field === "children"`：`value` 为 `SduiNode` 或 `SduiNode[]`
  - 若 `field === "rows"`：`value` 为 `Record<string, unknown>` 或其数组（与现有 `DataGrid.rows` 形状一致）

### 2.3 Patch JSON 示例

#### 示例 A：向容器 `children[]` 追加一个节点（流式片段）

```json
{
  "syntheticPath": "skill-ui://SduiView?dataFile=workspace/dashboard.json",
  "patch": {
    "schemaVersion": 3,
    "type": "SduiPatch",
    "docId": "dashboard:gc",
    "revision": 42,
    "isPartial": true,
    "ops": [
      {
        "op": "append",
        "target": { "by": "id", "nodeId": "report-body", "field": "children" },
        "value": {
          "type": "Text",
          "id": "line-7",
          "variant": "mono",
          "content": "第 7 行：已生成…"
        }
      }
    ]
  }
}
```

#### 示例 B：向 `DataGrid.rows[]` 追加一行（流式片段）

```json
{
  "syntheticPath": "skill-ui://SduiView?dataFile=test-scan.json",
  "patch": {
    "schemaVersion": 3,
    "type": "SduiPatch",
    "docId": "test:scan",
    "revision": 9,
    "isPartial": true,
    "ops": [
      {
        "op": "append",
        "target": { "by": "id", "nodeId": "scan-grid", "field": "rows" },
        "value": { "asset": "PDU-01", "status": "ok", "latencyMs": 17 }
      }
    ]
  }
}
```

#### 示例 C：结束流式（稳定态）

结束流式可用两种方式：

- **方式 1（推荐）**：发一个 `isPartial=false` 的空 ops 补丁，只用于“关闭视觉态/停止 pulse”
- **方式 2**：发 `isPartial=false` 并带少量 `merge` 纠正最终值（例如总计、汇总行）

```json
{
  "syntheticPath": "skill-ui://SduiView?dataFile=test-scan.json",
  "patch": {
    "schemaVersion": 3,
    "type": "SduiPatch",
    "docId": "test:scan",
    "revision": 10,
    "isPartial": false,
    "ops": []
  }
}
```

---

## 3. 后端：SkillUiStreamer（流式发射器）

### 3.1 目标

封装一个 `SkillUiStreamer`，在 **LLM token-by-token 流式输出**阶段，持续构造局部 JSON 片段并通过 `emit_skill_ui_data_patch_event` 投递。

### 3.2 行为（最小闭环）

- 监听 LLM stream 的增量文本
- 通过“增量 JSON 片段闭合检测”决定何时触发 append：
  - 表格：每闭合一行 row JSON → append rows
  - 容器：每闭合一个 node JSON → append children
- 每次 emit 都带 `isPartial=true`
- 结束时 emit 一次 `isPartial=false`

### 3.3 风险与护栏

- **幂等**：追加元素必须有稳定 key（children 节点用 `id`；DataGrid 行建议包含可重复计算的 key 字段，或由 streamer 注入 `_rowId`）
- **乱序**：严格按 `revision` 单调递增发射；前端丢弃旧 revision
- **回滚**：稳定态（isPartial=false）可选择做一次最终 merge 校准

---

## 4. 前端：`applySduiPatch` 的 append 语义 + Buffer

### 4.1 append 语义

当 op 为 `append`：

- 定位到 `target.nodeId`
- 读取 `target.field` 指定数组
- 进行 `prev.concat(next)`（不覆盖原数组）

### 4.2 白名单字段与安全

仅允许：

- `field === "children"`：目标节点必须是带 `children?: SduiNode[]` 的容器节点
- `field === "rows"`：目标节点必须是 `type === "DataGrid"` 且有 `rows: Array<Record<string, unknown>>`

其他 field 一律忽略（安全降级）。

### 4.3 防抖/缓冲（Buffer）

为避免高频 patch 导致 React 频繁重绘：

- 引入一个“极短 buffer”队列（例如 16–33ms）
- 将时间窗口内的 append ops 合并为一次批处理应用
- `revision` 仍按顺序单调应用；buffer 只影响同一 tick 内的应用频率

---

## 5. 视觉：isPartial 的 Skeleton Pulse + 追加滑入

### 5.1 Skeleton Pulse（partial 视觉态）

当最近一次应用的 patch 为 `isPartial=true`：

- 对“刚 append 的元素”在渲染层打上 `data-sdui-partial` 或 class（如 `animate-pulse` + 轻微透明度）
- 当收到 `isPartial=false`：清理该标记（恢复为稳定态）

### 5.2 滑入动画

优先策略：

- **零依赖**：使用 Tailwind `transition` + `opacity/translate-y` 做一次 mount 动画（稳定、无额外依赖）
- 若需要更丝滑的布局动画，再评估引入 `framer-motion` 的成本与打包影响（后续里程碑）

---

## 6. 验收标准（Definition of Done）

- 协议：`append` + `isPartial` 能被端到端传输（SSE → 前端）
- 前端：`children[]` 与 `DataGrid.rows[]` 能流式追加且不覆盖历史内容
- 性能：连续追加 200+ 行不会明显卡顿（buffer 生效）
- 视觉：partial 期间有轻微 pulse，结束后自动恢复稳定态
- 护栏：不影响现有 `merge` 路径；不触碰 Session/Skill/SSE 业务逻辑

