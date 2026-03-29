# Nanobot Remote Asset Center 设计规格书

**状态:** Ready for Implementation  
**日期:** 2026-03-28  
**范围:** 远端交付中心接入、组织资产展示、个人 Skill/产物上传

---

## 1. 目标与边界

### 1.1 目标

- 在 `nanobot` 前端接入远端交付中心，使用户能够查看当前账号可见的组织资产。
- 在 `nanobot` 前端新增个人资产能力，覆盖：
  - 个人 Skill 上传
  - 个人产物上传
  - 从组织资产复制为个人资产
- 保持现有 AGUI 主结构稳定，不破坏左侧既有模块与右侧预览体系。

### 1.2 明确约束（已确认）

- 左侧分栏中其他模块不变。
- “组织资产”使用 `Sidebar` 中当前已经预留的位置，不新增新的左侧主分区位置。
- 左侧组织资产模块中应有明确操作按钮，点击后可在右侧栏查看详情。
- 远端中心接入方式采用：前端只请求 `nanobot` 自身后端，由后端代理远端交付中心。
- 组织资产不仅可看，还需支持：
  - 列表展示与详情查看
  - 下载/导入到本地或工作区
  - 复制为个人资产
- 个人资产范围包括：
  - 会话产物文件
  - 用户手动选择的本地文件
  - 本地 Skill 文件夹整体上传
  - 单个 Skill zip 上传
- 上传默认归属为“当前项目”，但用户可切换为“个人空间”。

### 1.3 非目标

- 本阶段不重做 `Sidebar` 整体布局。
- 不替换现有 `PreviewPanel` 主体机制，只在其上承载新增详情视图。
- 不要求前端直接保存远端账号密码或长期持久化远端 token 到浏览器本地。
- 不在本阶段引入组织资产全文检索、复杂筛选、批量上传工作流。
- 本阶段桌面端优先；移动端不要求完整承载“左侧按钮打开右侧详情”的同构体验。

---

## 2. 架构决策（ADR）

| ID | 决策 | 内容 |
|----|------|------|
| R1 | 远端接入方式 | 前端仅调用 `nanobot` 自有 `/api/...`，由 `nanobot` 后端代理远端交付中心 |
| R2 | 左侧组织资产位置 | 复用 `frontend/components/Sidebar.tsx` 中现有“组织资产”预留卡片，不改变其他模块顺序 |
| R3 | 详情承载位置 | 组织资产详情、个人资产详情、上传面板统一在右侧栏打开 |
| R4 | 默认上传归属 | 默认上传到“当前项目”，允许切换为“个人空间” |
| R5 | 个人资产模型 | 个人资产拆分为两类：`personal skills` 与 `personal artifacts` |
| R6 | 远端状态真相源 | 远端登录态、当前用户、当前项目、远端 token 均以后端会话为单一真相源 |
| R7 | 字段兼容策略 | 后端对远端中心响应做统一映射，前端仅消费稳定契约，不直接依赖远端原始字段 |
| R8 | 详情打开方式 | 左侧组织资产卡片提供“查看详情”按钮；点击后右侧栏进入远端资产详情模式 |
| R9 | 会话模型 | 首版按“单机桌面单用户会话”建模：同一 `nanobot` 本地实例维护一份远端会话，不承诺多用户隔离 |
| R10 | 项目标识 | 对前端稳定暴露 `projectId` 与 `projectName`，切换项目以 `projectId` 为准 |
| R11 | 请求路径兼容 | 新前端请求必须沿用现有 `apiPath()`/同源代理策略，兼容 `NEXT_PUBLIC_AGUI_DIRECT` |

---

## 3. 现状与改造点

### 3.1 当前前端现状

- `Sidebar` 中已有本地 `skills` 列表能力，读取的是本机 `/api/skills`。
- `Sidebar` 中“组织资产”区域当前仅为占位文案，尚未接入真实数据。
- `page.tsx` 已存在右侧栏与 `PreviewPanel` 切换机制，可承载新增详情视图。

### 3.2 本次改造原则

- 不扰动现有“技能 / 产物 / 会话 / 设置”等已上线链路。
- 组织资产只替换占位内容，不整体改写侧栏交互模型。
- 新增“远端资产详情/上传”能力时，尽量复用右侧栏切换模式，而不是继续向左侧挤压复杂表单。

---

## 4. 系统架构

```text
Browser (Next.js)
  ├─ Sidebar
  │   ├─ 本地 Skills（现有）
  │   └─ 组织资产（复用预留位置，展示远端列表 + 查看详情按钮）
  ├─ Chat / Artifact 区（现有）
  └─ Right Panel
      ├─ PreviewPanel（现有预览）
      ├─ RemoteAssetDetailPanel（新增）
      └─ RemoteAssetUploadPanel（新增）

Nanobot Backend (aiohttp)
  ├─ RemoteCenterSessionStore（新增）
  ├─ RemoteCenterClient（新增）
  ├─ 组织资产代理接口（新增）
  ├─ 个人 Skill 上传接口（新增）
  └─ 个人产物上传接口（新增）

Remote Delivery Center
  ├─ /api/auth/login
  ├─ /api/auth/me
  ├─ /api/auth/projects
  ├─ /api/skills?ownership=organization
  ├─ /api/skills/{id}/download
  ├─ /api/skills/collected-sync
  └─ /api/validation-data/sync
```

### 4.1 前端职责

- 维护远端连接状态展示。
- 展示组织资产列表与详情入口。
- 提供个人资产上传入口与上传结果反馈。
- 统一在右侧栏展示详情或上传表单。

### 4.2 后端职责

- 负责远端登录、远端 token 保存、项目上下文维护。
- 负责将远端中心的接口与字段映射为本地稳定 API。
- 负责上传源统一封装：本地文件、zip、skill 文件夹、会话产物。
- 负责错误收敛与权限控制。

---

## 5. 前端信息架构

### 5.1 左侧栏

左侧栏保留当前整体顺序，仅对“组织资产”区块进行实装：

- `技能`：维持现有本地 Skills 列表
- `组织资产`：由占位卡升级为真实远端资产列表
- 其他模块：位置、功能、主交互保持不变

### 5.1.1 远端连接入口

远端连接入口不放入左侧新增主模块，建议放在右侧设置/配置体系中：

- 在现有设置或配置面板中增加“远端交付中心”区块
- 字段包括：
  - `frontendBase`
  - `apiBase`
  - `workId`
  - `password`
- 支持：
  - 登录
  - 登出
  - 查看当前连接用户
  - 查看/切换当前项目

未连接时：

- 左侧组织资产区块显示“未连接远端中心”的空态提示
- 可提供“去连接”按钮，打开右侧配置/设置面板

### 5.2 组织资产区块设计

组织资产区块应包含：

- 标题与远端状态提示
- 刷新按钮
- 组织资产列表（建议先支持 Skill 类）
- 每个列表项至少包含：
  - 名称
  - 简短描述或来源标签
  - 一个明确的“查看详情”按钮

交互规则：

- 点击“查看详情”按钮后，右侧栏切换为资产详情模式。
- 左侧本身只负责列表浏览与入口，不承载完整详情信息。
- 若右侧当前已打开同一资产详情，再次点击可保持当前页，不要求做 toggle close。

### 5.3 右侧栏

右侧栏新增两类内容模式。文档中统一使用实现层枚举命名：

- `remoteAssetDetail`
  - 展示组织资产详情
  - 展示个人 Skill / 个人产物详情
- `remoteAssetUpload`
  - 承载上传表单

与现有 `preview/settings/config` 的切换规则：

- 右侧栏同一时刻只显示一种模式。
- 当切换到 `remoteAssetDetail` 或 `remoteAssetUpload` 时，已有 `previewPath` 可保留在状态中，但不显示。
- 当用户关闭远端详情/上传面板时，右侧栏回到默认 `preview` 模式；若存在先前 `previewPath`，则恢复该预览，否则显示空预览态。
- `selectedOrgAssetId` 与 `previewPath` 使用独立状态，不互相覆盖。

详情页中组织资产需支持操作：

- 查看元数据
- 导入到本地工作区
- 复制为个人资产

### 5.4 上传入口

建议右侧栏提供统一“上传资产”入口，再细分来源：

- 上传 Skill
  - 本地 Skill 文件夹
  - 单个 Skill zip
  - 从组织资产复制
- 上传产物
  - 会话产物
  - 用户手动选择本地文件

---

## 6. 远端会话与状态模型

### 6.1 会话状态

后端维护远端会话状态。首版明确采用“单机桌面单用户会话”模型：

- 一份 `nanobot` 本地运行实例仅维护一份远端会话。
- 不承诺浏览器多标签下的独立远端登录隔离。
- 新登录会覆盖旧登录。
- 服务重启后远端会话可失效，前端需接受重新登录。

后端会话至少保存：

- `connected: boolean`
- `frontendBase: string`
- `apiBase: string`
- `user: { workId, name, role } | null`
- `projects: ProjectSummary[]`
- `selectedProjectId: string | null`
- `selectedProjectName: string | null`

### 6.2 前端消费状态

前端不直接管理远端 token，仅拉取后端整合后的会话快照：

```json
{
  "connected": true,
  "frontendBase": "http://100.99.198.128:3000",
  "apiBase": "http://100.99.198.128:8000",
  "user": {
    "workId": "j00954996",
    "name": "xxx",
    "role": "xxx"
  },
  "projects": [
    { "id": "project-a", "name": "项目A" }
  ],
  "selectedProjectId": "project-a",
  "selectedProjectName": "项目A"
}
```

---

## 7. API 契约

### 7.0 错误响应格式（统一）

所有 4xx/5xx 错误统一为：

```json
{
  "error": {
    "code": "remote_not_connected",
    "message": "human readable summary",
    "detail": "optional technical detail"
  }
}
```

建议稳定错误码：

- `remote_not_connected`
- `remote_login_failed`
- `remote_project_required`
- `remote_permission_denied`
- `remote_timeout`
- `remote_bad_response`
- `invalid_upload_source`
- `upload_failed`

### 7.1 `POST /api/remote-center/login`

**作用:** 登录远端交付中心，并在后端保存远端会话。  

**Request**

```json
{
  "frontendBase": "http://100.99.198.128:3000",
  "apiBase": "http://100.99.198.128:8000",
  "workId": "j00954996",
  "password": "123456"
}
```

**Response 200**

```json
{
  "connected": true,
  "user": {
    "workId": "j00954996",
    "name": "张三",
    "role": "user"
  },
  "projects": [
    { "id": "project-a", "name": "项目A" }
  ],
  "selectedProjectId": null,
  "selectedProjectName": null
}
```

### 7.2 `GET /api/remote-center/session`

**作用:** 获取当前远端连接状态、用户信息与项目上下文。  

**Response 200**

```json
{
  "connected": false,
  "frontendBase": "http://100.99.198.128:3000",
  "apiBase": "http://100.99.198.128:8000",
  "user": null,
  "projects": [],
  "selectedProjectId": null,
  "selectedProjectName": null
}
```

### 7.3 `POST /api/remote-center/logout`

**作用:** 清理远端会话。  

**Response 200**

```json
{
  "ok": true
}
```

### 7.4 `POST /api/remote-center/project`

**作用:** 绑定或切换当前项目。  

**Request**

```json
{
  "projectId": "project-a"
}
```

**Response 200**

```json
{
  "selectedProjectId": "project-a",
  "selectedProjectName": "项目A"
}
```

### 7.5 `GET /api/remote-assets/org-skills`

**作用:** 获取远端组织级 Skill 列表。  

**Response 200**

```json
{
  "items": [
    {
      "id": "101",
      "name": "report-gen",
      "title": "工勘报告生成",
      "description": "自动生成工勘报告",
      "version": "1.0.0",
      "organizationName": "交付中心",
      "updatedAt": "2026-03-28T10:00:00Z"
    }
  ]
}
```

### 7.6 `GET /api/remote-assets/org-skills/{id}`

**作用:** 获取组织资产详情。  

**Response 200**

```json
{
  "id": "101",
  "kind": "org-skill",
  "name": "report-gen",
  "title": "工勘报告生成",
  "description": "自动生成工勘报告",
  "version": "1.0.0",
  "organizationName": "交付中心",
  "uploaderId": "j00954996",
  "updatedAt": "2026-03-28T10:00:00Z",
  "tags": ["report", "survey"],
  "canImport": true,
  "canClone": true
}
```

### 7.7 `POST /api/remote-assets/org-skills/{id}/import`

**作用:** 将组织资产导入本地工作区或本地 Skills 目录。  

**Request**

```json
{
  "target": "workspace-skills"
}
```

**Response 200**

```json
{
  "ok": true,
  "target": "workspace-skills",
  "importedPath": "C:/Users/<user>/.nanobot/workspace/skills/report-gen"
}
```

### 7.8 `POST /api/remote-assets/org-skills/{id}/clone-to-personal`

**作用:** 将组织资产复制为个人资产。  

**Request**

```json
{
  "scope": "project",
  "projectId": "project-a"
}
```

**Response 200**

```json
{
  "ok": true,
  "item": {
    "id": "ps-2",
    "kind": "personal-skill",
    "title": "工勘报告生成",
    "scope": "project",
    "projectId": "project-a",
    "projectName": "项目A"
  }
}
```

### 7.9 `GET /api/remote-assets/personal-skills`

**作用:** 获取个人 Skill 列表。  

**Response 200**

```json
{
  "items": [
    {
      "id": "ps-1",
      "kind": "personal-skill",
      "title": "我的报告生成",
      "scope": "project",
      "projectId": "project-a",
      "projectName": "项目A",
      "sourceType": "zip_file",
      "updatedAt": "2026-03-28T12:00:00Z"
    }
  ]
}
```

### 7.10 `POST /api/remote-assets/personal-skills/upload`

**作用:** 统一个人 Skill 上传入口。  

**Request (multipart/form-data)**

- `sourceType`: `folder_zip` | `zip_file` | `org_clone`
- `scope`: `project` | `personal`
- `projectId`: optional
- `file`: optional
- `orgSkillId`: required when `sourceType=org_clone`
- `title`, `description`, `tags`, `version`: optional metadata

说明：

- 本地 Skill 文件夹由前端先打包为 zip 后上传，后端不直接读取浏览器外部目录。
- 从组织资产复制可复用独立接口，也可在后端统一归并到本上传入口；若保留两条链路，则前端默认优先调用 `POST /api/remote-assets/org-skills/{id}/clone-to-personal`。

**Response 200**

```json
{
  "ok": true,
  "item": {
    "id": "ps-3",
    "kind": "personal-skill",
    "title": "我的新 Skill",
    "scope": "project",
    "projectId": "project-a",
    "projectName": "项目A"
  }
}
```

### 7.11 `GET /api/remote-assets/personal-artifacts`

**作用:** 获取个人产物列表。  

**Response 200**

```json
{
  "items": [
    {
      "id": "pa-1",
      "kind": "personal-artifact",
      "filename": "report.docx",
      "scope": "project",
      "projectId": "project-a",
      "projectName": "项目A",
      "sizeBytes": 102400,
      "sourceType": "session_output",
      "updatedAt": "2026-03-28T12:10:00Z"
    }
  ]
}
```

### 7.12 `POST /api/remote-assets/personal-artifacts/upload`

**作用:** 上传用户手动选择的本地产物文件。  

**Request (multipart/form-data)**

- `scope`: `project` | `personal`
- `projectId`: optional
- `files[]`

**Response 200**

```json
{
  "ok": true,
  "items": [
    {
      "id": "pa-2",
      "kind": "personal-artifact",
      "filename": "report.docx",
      "scope": "project",
      "projectId": "project-a",
      "projectName": "项目A"
    }
  ]
}
```

### 7.13 `POST /api/remote-assets/personal-artifacts/upload-from-session`

**作用:** 将当前会话中的产物上传为远端个人产物。  

**Request**

```json
{
  "scope": "project",
  "projectId": "project-a",
  "paths": [
    "C:/Users/<user>/.nanobot/workspace/output/report.docx"
  ]
}
```

安全约束：

- `paths` 中所有路径必须位于 `nanobot workspace root` 下。
- 仅允许读取工作区内产物路径，不允许读取任意绝对路径。
- 任一路径越界时整批拒绝，返回 `400 invalid_upload_source`。

**Response 200**

```json
{
  "ok": true,
  "items": [
    {
      "id": "pa-3",
      "kind": "personal-artifact",
      "filename": "report.docx",
      "scope": "project",
      "projectId": "project-a",
      "projectName": "项目A"
    }
  ]
}
```

---

## 8. 前端交互与状态流

### 8.1 启动阶段

1. 页面初始化时获取本地配置与远端会话快照。
2. 若远端已连接，则拉取组织资产列表。
3. 左侧“组织资产”区块显示加载态、空态或正常列表。
4. 相关前端请求必须沿用现有 `apiPath()` 或同等封装，兼容同源代理与 `NEXT_PUBLIC_AGUI_DIRECT`。

### 8.2 查看组织资产详情

1. 用户在左侧组织资产模块中点击“查看详情”按钮。
2. 前端记录当前资产 ID。
3. 右侧栏切换到 `remote-asset-detail`。
4. 前端请求组织资产详情接口并渲染。

### 8.3 从组织资产复制为个人资产

1. 用户在右侧详情中点击“复制为个人资产”。
2. 默认归属为当前项目，可切换为个人空间。
3. 提交成功后刷新个人 Skill 列表。

### 8.4 上传个人 Skill

1. 用户打开上传资产入口。
2. 选择 `Skill` 类型与上传来源（本地文件夹 / zip）。
3. 设置归属（默认当前项目）。
4. 上传成功后刷新个人 Skill 列表与详情。

### 8.5 上传个人产物

1. 用户打开上传资产入口。
2. 选择 `产物` 类型与来源（会话产物 / 本地文件）。
3. 设置归属（默认当前项目）。
4. 上传成功后刷新个人产物列表。

---

## 9. 组件设计

### 9.1 `Sidebar`

改造点：

- 将当前组织资产占位块替换为真实列表。
- 每个组织资产列表项至少包含一个“查看详情”按钮。
- 保持现有其他区块 DOM 结构与交互习惯尽量不变。

建议新增前端状态：

- `orgAssets: OrgAssetSummary[]`
- `orgAssetsLoading: boolean`
- `orgAssetsError: string | null`
- `selectedOrgAssetId: string | null`

### 9.2 右侧栏模式

建议在 `page.tsx` 的右侧模式中新增：

- `remoteAssetDetail`
- `remoteAssetUpload`

移动端策略：

- 首版可不实现完整右侧栏远端资产详情体验。
- 移动端可继续维持现有主聊天布局；若后续补齐，可采用全屏页或底部抽屉承载远端资产详情。

### 9.3 详情面板组件

建议新增：

- `RemoteAssetDetailPanel`
- `RemoteAssetUploadPanel`

详情面板应可根据传入对象类型切换展示：

- `org-skill`
- `personal-skill`
- `personal-artifact`

---

## 10. 后端实现建议

### 10.1 客户端封装

建议新增一个远端中心客户端封装，统一处理：

- base url 规范化
- 登录
- 请求头注入
- 远端异常转换
- 超时控制

### 10.2 会话存储

建议新增轻量级远端会话存储对象，保存：

- `token`
- `api_base`
- `frontend_base`
- `current_user`
- `projects`
- `selected_project`

### 10.3 上传打包策略

- 本地 Skill 文件夹：前端打包 zip 再传给后端。
- 单个 zip：前端直传。
- 会话产物：后端根据路径读取本地文件，再上传远端。
- 用户本地文件：前端 multipart 上传给后端，再由后端转发远端。

---

## 11. 错误处理

### 11.1 前端

- 左侧列表区分：
  - 未连接
  - 加载中
  - 空列表
  - 加载失败
- 右侧详情区分：
  - 未选择资产
  - 详情加载中
  - 详情加载失败

### 11.2 后端

- 远端鉴权失败：返回 `401/403` 对应统一错误码
- 当前项目缺失但请求要求项目归属：返回 `400 remote_project_required`
- 远端超时：返回 `504 remote_timeout`
- 远端返回结构异常：返回 `502 remote_bad_response`

---

## 12. 测试计划

### 12.1 后端

- 登录代理成功/失败
- 获取远端会话快照
- 获取组织资产列表与详情
- 复制组织资产为个人资产
- 上传个人 Skill（zip）
- 上传个人产物（本地文件、会话产物）

### 12.2 前端

- 组织资产区块加载态/空态/错误态
- 点击“查看详情”后右侧栏正确打开
- 右侧详情页按钮操作后的刷新链路
- 上传表单默认归属为当前项目

### 12.3 联调

- 使用真实远端地址验证：
  - 登录成功
  - 组织资产可见
  - 详情可打开
  - Skill 上传成功
  - 产物上传成功

---

## 13. 分阶段实施顺序

1. 实现远端登录、会话快照、项目绑定代理
2. 替换 `Sidebar` 中组织资产占位块，接入组织资产列表
3. 增加“查看详情”按钮，打通右侧详情模式
4. 实现个人 Skill / 个人产物列表与刷新，形成最小闭环
5. 实现组织资产导入与复制为个人资产
6. 实现个人产物上传
7. 实现个人 Skill 上传
8. 补充状态优化与错误提示

---

## 14. 验收标准

- 左侧其他模块保持现状，不发生结构性回归。
- 左侧组织资产区块不再是占位文案，而是可加载远端组织资产列表。
- 每个组织资产至少可通过按钮在右侧栏查看详情。
- 用户可以在 `nanobot` 中完成个人 Skill 上传。
- 用户可以在 `nanobot` 中完成个人产物上传。
- 上传默认归属当前项目，但允许切换为个人空间。

