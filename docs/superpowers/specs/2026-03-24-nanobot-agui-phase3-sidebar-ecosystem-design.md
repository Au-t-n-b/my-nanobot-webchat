# Nanobot AGUI Phase 3 设计规格书（Sidebar & Workspace）

**状态:** Ready for Implementation  
**日期:** 2026-03-24  
**范围:** 仅覆盖 AGUI 计划中的 Phase 3（3.1/3.2/3.3）

---

## 1. 目标与边界

### 1.1 目标

- 为 AGUI 侧栏补齐工作区生态能力：
  - 技能树 API 联动（列表、刷新、打开目录/文件）
  - 动态文件索引与路径 Tooltip
  - 安全回收站删除流（单条删除 + 一键清空 + 二次确认）

### 1.2 明确约束（已确认）

- 技能根目录固定为 `~/.nanobot/workspace/skills`（运行时展开到用户主目录）。
- 技能列表排序：按名称 A->Z。
- 目录不存在时：后端自动创建目录并返回空列表。
- `open-folder` 支持定位到具体文件（如 `SKILL.md`）。
- `trash-files` 允许范围：`~/.nanobot/workspace/**`，越界必须拒绝。
- 点击技能项仅预览 `SKILL.md`。

### 1.3 非目标

- 本阶段不实现多文件树可视浏览器（仅单文件 `SKILL.md` 预览）。
- 不修改聊天主链路协议（SSE 事件契约保持不变）。
- 不引入与本阶段无关的 UI 体系改造（主题系统、全局搜索等属于其他 Phase）。

---

## 2. 架构与职责

### 2.1 后端职责（单一真相）

- 负责文件系统扫描、路径规范化、越界校验、安全删除、跨平台打开目录/文件。
- 输出稳定 API 契约，前端仅做渲染与交互状态管理。

### 2.2 前端职责

- 维护侧栏状态（skills、selectedSkill、indexedFiles、trashConfirmState）。
- 连接现有预览面板能力：技能点击后打开对应 `SKILL.md`。
- 提供刷新、打开文件夹、删除确认等交互。

### 2.3 安全边界

- 所有文件系统写操作/系统调用入口均进行路径边界校验。
- 校验策略：对目标路径执行 `realpath`（或等价）后，必须位于 `workspace_root` 下。
- 明确防护符号链接/重解析点：若解析后跳出 `workspace_root`，一律拒绝。
- 任何越界输入返回 400，且不执行后续动作。

---

## 3. API 契约

### 3.0 错误响应格式（统一）

- 所有 4xx/5xx JSON 错误统一为：

```json
{
  "error": {
    "code": "bad_request",
    "message": "human readable summary",
    "detail": "optional technical detail"
  }
}
```

- 最小字段集：
  - 400: `code`, `message`
  - 404: `code`, `message`
  - 500: `code`, `message`（`detail` 可选）

## 3.1 `GET /api/skills`

**作用:** 扫描 `~/.nanobot/workspace/skills/*/SKILL.md` 并返回技能列表。  
**目录不存在行为:** 自动创建后返回空数组。  
**排序:** 按 `name.lower()` 的 Unicode 码点升序（稳定排序）。
**路径格式:** API 统一返回**绝对路径**（不返回 `~`）。

**Response 200**

```json
{
  "items": [
    {
      "name": "brainstorming",
      "skillDir": "C:/Users/<user>/.nanobot/workspace/skills/brainstorming",
      "skillFile": "C:/Users/<user>/.nanobot/workspace/skills/brainstorming/SKILL.md",
      "mtimeMs": 1711260000000
    }
  ]
}
```

## 3.2 `POST /api/open-folder`

**作用:** 打开目录或定位到文件。  
**Request**

```json
{
  "target": "C:/Users/<user>/.nanobot/workspace/skills/brainstorming/SKILL.md"
}
```

**规则**

- `target` 解析后必须在 `~/.nanobot/workspace/**` 内。
- 文件目标：
  - Windows: 资源管理器选中该文件。
  - 其他平台: 降级打开父目录。

**Response 200**

```json
{"ok": true}
```

**Errors**

- 400: 非法路径/越界
- 404: 目标不存在
- 500: 系统调用失败

## 3.3 `POST /api/trash-files`

**作用:** 使用系统回收站删除（支持单条与批量）。  
**Request**

```json
{
  "paths": [
    "C:/Users/<user>/.nanobot/workspace/skills/brainstorming/SKILL.md"
  ]
}
```

**规则**

- 每个路径均需通过 workspace 边界校验。
- 目录路径允许删除（同样进入系统回收站）。
- 路径先去重后处理。
- 安全优先策略：`paths` 中只要出现任一越界路径，整批请求 `400`，且不执行任何删除。
- 在路径全部合法前提下，允许部分成功，返回明细（不存在或系统失败项进入 `failed[]`）。

**Response 200**

```json
{
  "ok": false,
  "deleted": [".../SKILL.md"],
  "failed": [
    {"path":".../missing.md","reason":"not found"}
  ]
}
```

**Errors**

- 400: 入参非法（如 `paths=[]`）或存在越界路径（整批拒绝）
- 500: 整体异常

**响应语义约定**

- 客户端判定删除结果以 `failed.length` 为准。
- `ok` 是冗余镜像字段，等价于 `failed.length === 0`。

**全成功示例**

```json
{
  "ok": true,
  "deleted": [".../a.md",".../b.md"],
  "failed": []
}
```

**全失败示例（路径都合法但操作失败）**

```json
{
  "ok": false,
  "deleted": [],
  "failed": [
    {"path":".../a.md","reason":"permission denied"},
    {"path":".../b.md","reason":"not found"}
  ]
}
```

---

## 4. 前端交互与状态流

### 4.1 侧栏状态

- `skills: SkillItem[]`
- `skillsLoading: boolean`
- `skillsError: string | null`
- `selectedSkill: string | null`
- `indexedFiles: IndexedFileItem[]`
- `trashModal: { open: boolean; mode: "one" | "all"; targets: string[] }`

### 4.2 技能区行为

- 页面初始化请求 `GET /api/skills`。
- 点击“刷新”重新拉取列表（保留可用选中态）。
- 点击技能项时：
  - 设置选中态；
  - 打开预览面板并加载该技能 `SKILL.md`。
- “打开文件夹”调用 `POST /api/open-folder`（目标可为目录或 `SKILL.md`）。

### 4.3 动态文件索引

- 从会话消息中抽取 `/api/file?path=...` 链接，构建去重文件列表。
- 列表显示文件名；完整路径只放 Tooltip（title）。
- 点击文件项直接联动右侧预览。

### 4.4 回收站交互

- 单条删除与一键清空均先弹二次确认。
- 确认后调用 `POST /api/trash-files`。
- 成功移除列表项；部分失败显示失败明细摘要。

---

## 5. 错误处理

### 5.1 后端

- 越界路径：400 + `detail`（如 `path escapes workspace`）。
- 目标不存在：404。
- 批量部分失败：200 + `failed[]`，并约定 `ok = (failed.length === 0)`。
- 系统调用失败：500 + 简要错误信息。

### 5.2 前端

- skills 拉取失败：保留旧列表并展示轻量错误提示，可重试。
- open-folder 失败：toast 提示，不中断当前预览态。
- trash 部分失败：弹窗反馈“成功 N / 失败 M”并保留失败项。

---

## 6. 测试策略

### 6.1 后端测试（`tests/web/`）

- `test_api_skills.py`
  - 目录不存在自动创建并返回空
  - 正确扫描并按 `name.lower()` 升序稳定排序
- `test_api_open_folder.py`
  - 打开目录/文件（mock 平台调用）
  - Windows 文件目标：断言“选中文件”分支
  - 非 Windows 文件目标：断言降级打开父目录
  - 越界 400、缺失 404
  - 符号链接/重解析点逃逸：realpath 越界返回 400
- `test_api_trash.py`
  - `paths=[]` 返回 400
  - 重复路径去重行为
  - 目录路径删除行为
  - workspace 内删除成功
  - 越界拒绝
  - 含越界项时整批拒绝且零副作用
  - 符号链接/重解析点逃逸：realpath 越界返回 400
  - 批量部分失败返回明细

### 6.2 前端测试（必测）

- 技能列表刷新、空态与错误态
- 技能点击联动预览且仅请求 `SKILL.md`
- 文件索引 Tooltip 行为
- 删除确认弹窗流程
- 批量删除部分失败时：成功项移除、失败项保留

### 6.3 手工验收脚本

1. 在 `~/.nanobot/workspace/skills` 下创建两个技能目录与 `SKILL.md`。
2. 启动 AGUI + 前端，确认侧栏按 A->Z 显示。
3. 点击技能后在右侧成功预览 `SKILL.md`。
4. 点击“打开文件夹”唤起系统资源管理器。
5. 执行单条删除与一键清空，确认文件进入系统回收站。

---

## 7. 演进建议（非本期）

- skills 列表可增量返回标签/描述字段，以支持分组过滤。
- 打开文件夹可统一抽象平台适配层，避免路由层混入系统细节。
- 回收站动作可增加审计日志（时间、操作者、路径）。

