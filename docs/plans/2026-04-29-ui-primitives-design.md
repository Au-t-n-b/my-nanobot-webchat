# UI Primitives Constitution (方案 B)：强约束 UI 基元层

日期：2026-04-29  
范围：`frontend/`（Next.js App Router）  
目标：将 UI 外观从“散落的 Tailwind 色板/魔法数”收敛到“单一 Token + 单一 Elevation 梯度 + 少数基元组件”。

---

## 1. 背景与问题陈述（为什么会“丑”）

当前仓内已具备较完整的自研 Token 体系（见 `frontend/app/globals.css`），包括：

- `--surface-* / --paper-* / --canvas-*`（背景层级）
- `--text-*`（文字层级）
- `--border-*`（边框强弱）
- `--shadow-* / --highlight-inset`（阴影与高光）
- `--interactive-*`（hover/active/selected/focus）
- `--accent / --accent-soft`（主操作色）
- `--motion-* / --ease-out`（动效基线）

但在组件实现中仍存在**三套视觉语言混用**：

- Token（`var(--*)`）驱动的 UI
- Tailwind 默认色板（如 `bg-slate-* / text-white / border-slate-*`）驱动的 UI
- 零散的特例阴影/描边/透明度/圆角/尺寸（“魔法数”）驱动的 UI

这会导致：

- 主题（dark/light/soft）下观感漂移
- 同类控件在不同页面/模块样式不一致
- “哪里不对劲但说不上来”的企业级质感缺失

本设计的核心，是让“外观”成为可被工程化约束的系统，而不是 Code Review 的肉眼劳动。

---

## 2. 设计目标（Non-negotiable）

- **单一视觉来源**：UI 外观必须来自 `globals.css` Tokens。
- **单一层级系统**：所有“层级感”只能来自统一的 Elevation 梯度（`ui-elevation-*` 或其 alias）。
- **业务零皮肤**：业务组件不得自行定义皮肤（颜色/阴影/描边/圆角/交互色）。
- **主题可靠**：dark/light/soft 下对比度、边框、hover、focus 行为一致且可预测。

---

## 3. 基本法（Constitution Rules）

### 3.1 禁用 Tailwind 默认色板做“组件皮肤”

#### 禁止（Hard Fail）
在 UI 皮肤层（按钮/卡片/输入/弹层/菜单/徽章等）中，禁止使用以下风格的 class 作为外观表达：

- `bg-slate-* / text-slate-* / border-slate-*`
- `bg-gray-* / text-gray-* / border-gray-*`
- `bg-white* / text-white / border-white*`
- `bg-black* / text-black / border-black*`
- `ring-black* / ring-white*`

> 允许用于**布局与排版**的 Tailwind utility（`flex/grid/gap/p-*/w-*/h-*/text-sm/font-*` 等），但不能用默认色板来定义“皮肤”。

#### 允许
- `bg-[var(--...)] / text-[var(--...)] / border-[var(--...)]`
- `color-mix(...)`（但必须基于 tokens）
- 语义色仅通过 tokens（`--success/--warning/--danger` 等）或显式的 SDUI 语义映射层（见 6.1）

### 3.2 所有交互态必须走 `--interactive-*`

- hover：`--interactive-hover-bg`
- active：`--interactive-active-bg`
- selected：`--interactive-selected-bg`
- focus ring：`--interactive-focus-ring`

禁止组件自行发明 hover/focus 的颜色。

### 3.3 Elevation：一个元素只能用一种层级

Elevation 梯度（推荐）：
- `ui-elevation-0..4`

规则：
- 一个元素只允许选择一个 elevation
- 禁止同时叠加 `shadow-*` + `ring-*` + 自定义 border 来“手搓层级”
- 如确需特殊效果，必须沉淀为基元（primitives）能力并复用

### 3.4 去 demo 化（默认企业级）

任何 “hackathon 气质” 的符号元素（emoji、彩蛋、调试 UI）：
- 默认不在主 UI 出现
- 如需保留，必须以可配置 Feature Flag 的形式存在（默认关闭）

---

## 4. UI 基元层（Primitives）边界

业务组件（Workbench/Landing/Register/SDUI 卡片）只能通过基元组合表达外观。

### 4.1 建议的 8 类基元

- **Surface**：统一背景/边框/阴影/圆角（Elevation 的载体）
- **Text**：统一字阶（`ui-text-eyebrow/label/body/title`）
- **Button**：`primary/secondary/ghost/outline/danger`
- **IconButton**：固定尺寸（32/36/40）与 hover/focus
- **Input/TextArea/Select**：统一底色/边框/聚焦 ring
- **Menu/Popover/Tooltip**：统一浮层（Elevation=4）
- **Badge/StatusPill**：语义色统一入口（success/warn/danger/running）
- **Divider**：仅用 `--border-subtle`

> 当前仓内已有 `ui-*` utilities 与部分组件（如 `SduiCard`），本方案以“收敛与强约束”为主，不强制一次性引入大型组件库。

---

## 5. 工程化强约束（不是口头约定）

### 5.1 自动化拦截（ESLint / CI Hard Fail）

新增 lint 规则（或脚本）扫描“违禁词”：

- `bg-slate-`、`text-white`、`bg-white`、`border-gray-`、`ring-black` 等

策略：
- 允许在极少数“非 UI 皮肤层”出现（如图表库第三方输出，必须白名单路径）
- 对 `components/ui/*`（基元层）仍要遵守 tokens；仅在“语义色映射”处允许受控映射

### 5.2 目录边界（集中皮肤）

约定一个“基元目录”（建议）：

- `frontend/components/ui/*`（或 `frontend/components/primitives/*`）

规则：
- 业务组件不得新增外观 class（颜色/阴影/边框/交互态）
- 新外观能力必须进入 primitives，并被复用

---

## 6. 迁移策略（渐进式）

优先顺序遵循“ROI 最大”原则：先修复能污染全站的基元/入口组件。

### 6.1 第一刀（高 ROI，立刻收益）

1) **SDUI Button 去 slate 化**：`frontend/components/sdui/Button.tsx`  
2) **ChatInput 模型条 hover 去 slate 化**：`frontend/components/ChatInput.tsx`  
3) **侧栏去 🦞 demo 化**：`frontend/components/Sidebar.tsx` 与 `frontend/app/workbench/WorkbenchContent.tsx`

### 6.2 第二刀（WorkBench 统一皮肤）

- `Sidebar`、`MessageList`、`PreviewPanel`、`ConfigModal` 等外观收敛
- 清理 `shadow-[...] / ring-black/white / text-slate-*` 等违禁用法

### 6.3 验收标准（每一刀都可验收）

- 仓内不再出现违禁 class（或仅出现在白名单路径）
- 主题切换（dark/light/soft）下按钮/输入框/卡片 hover/focus 行为一致
- 同类控件（Button/Input/Card）在不同页面/SDUI 输出下外观一致

---

## 7. 附录：术语

- **Token**：`globals.css` 中以 `--*` 暴露的主题变量（颜色/阴影/动效等）
- **UI 皮肤**：决定“看起来像什么”的部分（背景/文字颜色/边框/阴影/交互态）
- **基元（Primitive）**：承载 UI 皮肤的可复用组件/utility，业务只能组合，不得自绘

