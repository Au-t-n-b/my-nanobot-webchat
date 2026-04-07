# SDUI 协议与 JSON 生成指令规范

**版本**：与 `schemaVersion: 1` 及 `frontend/lib/sdui.ts` 对齐；破坏性变更须升版并同步宿主实现。

---

## 目录

- [第一章　总则与边界](#第一章总则与边界)
- [第二章　结构层（布局与容器）](#第二章结构层布局与容器)
- [第三章　内容层（展示）](#第三章内容层展示)
- [第四章　表单与数据编辑层](#第四章表单与数据编辑层)
- [第五章　交互层](#第五章交互层)
- [第六章　版本、校验与「纯语义」防呆](#第六章版本校验与纯语义防呆)
- [附录 A　节点类型与字段速查](#附录-a节点类型与字段速查)
- [附录 B　间距枚举 SpacingToken 与宿主像素映射](#附录-b间距枚举-spacingtoken-与宿主像素映射)
- [附录 C　最小合法 SduiDocument 示例](#附录-c最小合法-sduidocument-示例)
- [附录 C-1　含 Stepper 与 Tabs 的示例](#附录-c-1含-stepper-与-tabs-的示例智慧工勘看板布局)

---

## 第一章　总则与边界

### 1.1 定位

**SDUI**（Skill Declarative UI）是 **AI 原生工作流** 下的声明式 UI 协议：Skill / Agent 输出 **纯 JSON 文档**，由宿主（前端）解析为可交互界面，并把用户操作以约定形式回传 Agent。

- **单一事实源**：界面结构以 JSON 为准，**不**引入 Python Builder SDK 作为生成侧必选项；人工或脚本均可产出同一套 JSON。
- **宿主渲染**：顶层通过 Skill UI 挂载 `SduiView`（或等价入口），由 `root` 递归渲染原子组件。

### 1.2 样式与呈现边界（硬约束）

生成侧 JSON **严禁**携带任何「由模型或 Skill 直接控制最终视觉样式」的逃逸通道，包括但不限于：

| 禁止键 | 说明 |
|--------|------|
| `className` | 禁止 Tailwind / CSS 类名字符串 |
| `style` | 禁止行内样式对象或字符串 |
| `styles` | 禁止复数或嵌套样式包 |
| `css` | 禁止原始 CSS |

**间距**不得使用自由像素数字表达为 `gap: 16` 等；仅允许 **语义枚举** `SpacingToken`（见 [附录 B](#附录-b间距枚举-spacingtoken-与宿主像素映射)）。历史数字 `gap` 由宿主 **兼容映射** 为最近枚举（实现见 `frontend/lib/sduiTokens.ts`）。

### 1.3 文档根结构

根对象必须为 **SduiDocument**：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `schemaVersion` | `number` | 是 | 当前为 `1`。 |
| `type` | `"SduiDocument"` | 否 | 建议始终写出；宿主可补全。 |
| `root` | `SduiNode` | 是 | 单根节点树。 |
| `meta` | `Record<string, unknown>` | 否 | 元数据；**同样**不得包含 §1.2 禁止键。 |

---

## 第二章　结构层（布局与容器）

本章节点用于 **组织子树**，不直接承担业务文案（文案见第三章）。

### 2.1 共同规则

- 子节点放在 `children` 数组（无子则省略或空数组，由宿主容忍）。
- 可选 `id`：字符串，用于稳定 key 与排查；**非** DOM id 强制要求。
- **禁止**：§1.2 所列键；`Stack` / `Row` 上禁止数字 `gap`。

### 2.2 `SpacingToken` 与 `gap`

- **枚举值**：`"none"` \| `"xs"` \| `"sm"` \| `"md"` \| `"lg"` \| `"xl"`。
- **语义**：仅表示档位，**不**绑定具体像素；像素映射由宿主固定实现（附录 B）。
- **`Stack` / `Row`**：`gap` 为可选；未指定时宿主采用默认档（与实现一致，当前默认为 `md`）。

### 2.3 `Stack`

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `type` | `"Stack"` | 是 | |
| `gap` | `SpacingToken` | 否 | 纵向子项间距语义。 |
| `children` | `SduiNode[]` | 否 | |

### 2.4 `Row`

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `type` | `"Row"` | 是 | |
| `gap` | `SpacingToken` | 否 | 横向（及折行后行内）间距语义。 |
| `align` | `"start" \| "center" \| "end" \| "stretch" \| "baseline"` | 否 | 交叉轴对齐语义。 |
| `justify` | `"start" \| "end" \| "center" \| "between" \| "around"` | 否 | 主轴对齐（如产物行左右分布）。 |
| `wrap` | `boolean` | 否 | 是否允许折行。 |
| `children` | `SduiNode[]` | 否 | |

### 2.5 `Card`

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `type` | `"Card"` | 是 | |
| `title` | `string` | 否 | 卡片标题语义。 |
| `children` | `SduiNode[]` | 否 | |

### 2.6 `Divider`

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `type` | `"Divider"` | 是 | 分隔线语义，无额外字段。 |

### 2.7 `Tabs`

多标签容器：顶部为标签栏，**仅当前选中标签**的子树被渲染；激活标签底部有 **2px** 的强调下划线（宿主使用 `var(--accent)`）。

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `type` | `"Tabs"` | 是 | |
| `tabs` | `SduiTabPanel[]` | 是 | 至少一项；见下表。 |
| `defaultTabId` | `string` | 否 | 初始选中标签的 `id`；缺省为 `tabs[0].id`。 |

**`SduiTabPanel` 单项：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | `string` | 是 | 在同一 `Tabs` 内唯一。 |
| `label` | `string` | 是 | 标签文案。 |
| `icon` | 见下 | 否 | 语义图标枚举；宿主映射到内置图标（Lucide），**禁止**自定义 SVG/URL。 |
| `children` | `SduiNode[]` | 否 | 该标签下面板内容，递归渲染。 |

**`icon` 封闭枚举**：`"terminal"` \| `"clipboardCheck"` \| `"alertTriangle"` \| `"image"` \| `"fileText"` \| `"layoutDashboard"` \| `"circle"`。

**禁止**：§1.2 所列键；不得在 `Tabs` 上使用数字 `gap`（本节点不使用 `gap` 字段）。

### 2.8 `Stepper`

流程步骤条：**横向**时节点为 **32px** 圆形容器；`waiting` 显示灰色序号；`running` 为蓝色脉冲环 + 旋转加载图标；`done` 为绿色对勾；`error` 为危险色叉。连线位于**相邻两步之间**，若**前一步**为 `done` 则线段为成功色，否则为弱边框色。样式使用 `var(--canvas-rail)`、`var(--border-subtle)`、`var(--success)`、`var(--danger)`、`var(--text-*)`。

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `type` | `"Stepper"` | 是 | |
| `steps` | 见下 | 是 | 至少零项（零项时宿主展示空态）。 |
| `orientation` | `"horizontal"` \| `"vertical"` | 否 | 默认 `horizontal`。 |

**`steps` 单项：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | `string` | 是 | 稳定标识。 |
| `title` | `string` | 是 | 步骤标题。 |
| `status` | `"waiting"` \| `"running"` \| `"done"` \| `"error"` | 是 | 步骤状态。 |

### 2.9 `ChartPlaceholder`

无矢量图表时的**占位区**：虚线边框、弱背景、居中 Lucide 图标（`pie`→饼图语义，`bar`→柱状图语义）。**禁止**在 JSON 中写任意 SVG/HTML。

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `type` | `"ChartPlaceholder"` | 是 | |
| `variant` | `"pie"` \| `"bar"` | 是 | 图标与语义。 |
| `caption` | `string` | 否 | 图标下方短文案。 |

### 2.10 `FileKindBadge`

产物文件类型图标（Word 蓝 / Excel 绿 / PDF 红系 / 其它中性），用于列表行首。

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `type` | `"FileKindBadge"` | 是 | |
| `kind` | `"docx"` \| `"xlsx"` \| `"pdf"` \| `"other"` | 是 | 宿主映射颜色与图标。 |

---

## 第三章　内容层（展示）

本章节点以 **只读展示** 为主（编辑见第四章，交互见第五章）。

### 3.1 `Text`

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `type` | `"Text"` | 是 | |
| `content` | `string` | 是 | 纯文本；换行可保留。 |
| `variant` | `"title" \| "body" \| "muted" \| "mono"` | 否 | 语义档位，宿主映射字体层级。 |

### 3.2 `Markdown`

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `type` | `"Markdown"` | 是 | |
| `content` | `string` | 是 | Markdown 源码。 |

### 3.3 `Badge`

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `type` | `"Badge"` | 是 | |
| `text` | `string` | 是 | |
| `tone` | `"default" \| "success" \| "warning" \| "danger"` | 否 | 语义色调。 |

### 3.4 `Statistic`

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `type` | `"Statistic"` | 是 | |
| `title` | `string` | 是 | 指标标题。 |
| `value` | `string \| number` | 是 | 展示值。 |

### 3.5 `KeyValueList`

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `type` | `"KeyValueList"` | 是 | |
| `items` | `{ key: string, value: string }[]` | 是 | 键值对列表。 |

### 3.6 `Table`

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `type` | `"Table"` | 是 | |
| `headers` | `string[]` | 否 | 表头；省略则无表头行。 |
| `rows` | `string[][]` | 是 | 行 → 单元格字符串。 |

**禁止**：列宽像素、`style`、嵌套任意未文档化结构。

---

## 第四章　表单与数据编辑层

本章节点用于 **采集用户输入** 或 **编辑结构化行数据**，并通过已定义的 **回传协议** 将结果交给 Agent。  
**禁止**任何呈现层字段（重申：**无 `className`、无 `style`、无自由 `gap` 数值**）。

### 4.1 `TextArea`

**含义**：多行文本输入；可与按钮文案中的 `{{input:某 id}}` 占位符联动（由宿主在发送前展开）。

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `type` | `"TextArea"` | 是 | |
| `inputId` | `string` | 是 | 全局唯一，与占位符 `{{input:inputId}}` 一致。 |
| `label` | `string` | 否 | 字段标签。 |
| `placeholder` | `string` | 否 | |
| `rows` | `number` | 否 | 大致行数语义；宿主映射为行高，**非像素高度**。 |
| `defaultValue` | `string` | 否 | 初始内容。 |

**禁止**：`className`、`style`、`minHeight` 等。

---

### 4.2 `DataGrid`

**含义**：表格形编辑；列由 `columns` 声明，行由 `rows` 提供；用户修改后通过 **提交** 将 JSON 块回传 Agent。

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `type` | `"DataGrid"` | 是 | |
| `columns` | `{ key: string, label: string }[]` | 是 | 列定义；**禁止**列级宽度像素或 `style`。 |
| `rows` | `Record<string, unknown>[]` | 是 | 每行对象，键与 `columns[].key` 对应。 |
| `editable` | `boolean` | 否 | 是否可编辑单元格；默认由宿主决定。 |
| `submitLabel` | `string` | 否 | 提交按钮文案语义。 |
| `submitActionPrefix` | `string` | 否 | 拼在 fenced JSON 前的说明性前缀。 |

**回传语义（固定，与实现一致）**：

- 提交消息体为：可选 `submitActionPrefix` + Markdown 围栏代码块包裹的 `JSON.stringify(rows)`（格式化由宿主决定，**语义不变**）。

**禁止**：`className`、列对象中的 `width: "120px"`、未规范化的 `type: "select"` 等（若未来支持列级控件，须经协议升版并列入枚举）。

---

## 第五章　交互层

### 5.1 `Button`

**含义**：触发一次对 Agent 的意图投递或打开预览路径。

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `type` | `"Button"` | 是 | |
| `label` | `string` | 是 | 按钮文案。 |
| `variant` | `"primary" \| "secondary" \| "ghost" \| "outline"` | 否 | **语义强度**：主操作 / 次操作 / 弱操作 / 线框；宿主映射主题。 |
| `action` | `SduiAction` | 是 | 见下。 |

**`SduiAction` 封闭形式**：

- `{ "kind": "post_user_message", "text": "..." }`  
  - `text` 中允许 `{{input:id}}`，在发送前由宿主替换为对应 `TextArea` 当前值。  
- `{ "kind": "open_preview", "path": "..." }`  
  - `path` 为 workspace 相对路径或宿主约定的 synthetic path（如 `skill-ui://...`），**禁止**任意协议外链 unless 宿主白名单。

**禁止**：`className`、`style`、未在 `kind` 枚举中的动作类型。

---

### 5.2 `Link`

**含义**：文本链接；外跳或触发与 `Button` 同类动作（二选一）。

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `type` | `"Link"` | 是 | |
| `label` | `string` | 是 | |
| `href` | `string` | 否 | 若存在，按宿主规则打开（通常新标签）。 |
| `action` | `SduiAction` | 否 | 与 `href` 二选一或按宿主优先级；未定义时仅展示不可点。 |

**禁止**：`className`、`style`。

---

## 第六章　版本、校验与「纯语义」防呆

### 6.1 `schemaVersion`

- 当前协议版本为 **`1`**。  
- 破坏性变更（新增必填字段、改枚举含义、移除节点）须 **升版本** 并同步更新本规范与宿主实现。

### 6.2 生成侧自检清单（AI / 人工）

在输出 JSON 前必须确认：

1. 根对象含 `schemaVersion`、`type: "SduiDocument"`、`root`。  
2. 全文 **不出现** `className`、`style`、`styles`、`css` 及未文档化的呈现类键。  
3. `Stack` / `Row` 的 `gap` 仅为 **间距枚举**（见 [附录 B](#附录-b间距枚举-spacingtoken-与宿主像素映射)），**无**自由数字。  
4. 所有 `type` 均在白名单内；`action.kind` 仅在允许值内。

### 6.3 宿主侧极简防呆（推荐）

在解析文档前对 JSON **做一次递归净化**（实现：`frontend/lib/sduiNormalizer.ts`）：

- **删除**键名：`className`、`style`、`styles`、`css`（及团队后续补充的「样式逃逸」键）。  
- **兼容**：若存在历史 **`gap` 数字**，映射为**最近似的间距枚举**（映射表固定于 `sduiTokens.ts`）。  
- **开发模式**：若原始 payload 仍携带禁止键，在 `NODE_ENV === "development"` 下输出 `console.warn`，便于 Skill 作者修正（文案见实现注释）。

---

## 附录 A　节点类型与字段速查

| `type` | 章节 | 摘要 |
|--------|------|------|
| `SduiDocument` | §1.3 | `schemaVersion`, `type`, `root`, `meta?` |
| `Stack` | §2.3 | `gap?`, `children?` |
| `Row` | §2.4 | `gap?`, `align?`, `justify?`, `wrap?`, `children?` |
| `Card` | §2.5 | `title?`, `children?` |
| `Divider` | §2.6 | — |
| `Tabs` | §2.7 | `tabs`, `defaultTabId?` |
| `Stepper` | §2.8 | `steps`, `orientation?` |
| `ChartPlaceholder` | §2.9 | `variant`, `caption?` |
| `FileKindBadge` | §2.10 | `kind` |
| `Text` | §3.1 | `content`, `variant?` |
| `Markdown` | §3.2 | `content` |
| `Badge` | §3.3 | `text`, `tone?` |
| `Statistic` | §3.4 | `title`, `value` |
| `KeyValueList` | §3.5 | `items` |
| `Table` | §3.6 | `headers?`, `rows` |
| `TextArea` | §4.1 | `inputId`, `label?`, … |
| `DataGrid` | §4.2 | `columns`, `rows`, … |
| `Button` | §5.1 | `label`, `variant?`, `action` |
| `Link` | §5.2 | `label`, `href?`, `action?` |

各节点均可选 `id`（§2.1）。

---

## 附录 B　间距枚举 SpacingToken 与宿主像素映射

**枚举**（JSON 中唯一合法写法）：`none` \| `xs` \| `sm` \| `md` \| `lg` \| `xl`。

**宿主映射**（`frontend/lib/sduiTokens.ts`，**不得**写入 JSON）：

| Token | 像素（当前实现） |
|-------|-------------------|
| `none` | 0 |
| `xs` | 4 |
| `sm` | 8 |
| `md` | 12 |
| `lg` | 16 |
| `xl` | 24 |

未指定 `gap` 时，当前默认按 **`md`** 解析。

---

## 附录 C　最小合法 SduiDocument 示例

```json
{
  "schemaVersion": 1,
  "type": "SduiDocument",
  "root": {
    "type": "Stack",
    "gap": "md",
    "children": [
      {
        "type": "Text",
        "content": "Hello, SDUI",
        "variant": "title"
      }
    ]
  }
}
```

### 附录 C-1　含 `Stepper` 与 `Tabs` 的示例（智慧工勘看板布局）

```json
{
  "schemaVersion": 1,
  "type": "SduiDocument",
  "root": {
    "type": "Stack",
    "gap": "md",
    "children": [
      {
        "type": "Stepper",
        "steps": [
          { "id": "s1", "title": "场景过滤", "status": "running" },
          { "id": "s2", "title": "勘测汇总", "status": "waiting" },
          { "id": "s3", "title": "评估报告", "status": "waiting" },
          { "id": "s4", "title": "审批分发", "status": "waiting" }
        ]
      },
      {
        "type": "Tabs",
        "defaultTabId": "process",
        "tabs": [
          {
            "id": "process",
            "label": "执行详情",
            "icon": "terminal",
            "children": [
              {
                "type": "Markdown",
                "content": "🚀 发送指令后，AI Agent 执行过程将实时显示在这里。"
              }
            ]
          },
          {
            "id": "assess",
            "label": "满足度评估",
            "icon": "clipboardCheck",
            "children": [{ "type": "Text", "content": "暂无数据", "variant": "muted" }]
          }
        ]
      }
    ]
  }
}
```
