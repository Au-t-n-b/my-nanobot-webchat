# Hermes 技能管理改进总览

> 记录 Hermes（技能自动萃取 + 审核系统）从初始版本到当前版本的所有改进。
> 最后更新：2026-05-19

---

## 一、系统架构

```
用户对话 → AgentLoop → Hermes 触发门控
                          │
                          ▼
                   _run_skill_review (后台)
                   ├─ 对话蒸馏 (distill snapshot)
                   ├─ 证据摘要生成 (evidence summary)
                   ├─ 拒绝反馈注入 (reject feedback)
                   └─ LLM 工具调用 → SkillManageTool.execute()
                                        │
                                        ▼
                                  prefilter_and_judge (async)
                                  ├─ N-gram 候选召回 (top-5)
                                  └─ LLM 语义判断 (Qwen3/其他)
                                        │
                                        ▼
                                  SkillChangeStore.create_request()
                                  ├─ same_duplicate → 合并到已有 pending
                                  ├─ related_but_distinct → 新建 pending + 关联 ID
                                  ├─ blacklist_hit → 阻止创建
                                  └─ 无候选/LLM失败 → 新建普通 pending
                                        │
                                        ▼
                                  前端 SkillRequestPanel 审核界面
                                  ├─ 批准 → 写入 skills/ 目录
                                  ├─ 拒绝（可选加入黑名单）
                                  └─ 过期自动清理
```

---

## 二、改进清单

### Round 1：基础 Hermes 门控

| 改进 | 说明 |
|------|------|
| SkillChangeStore | SQLite 持久化存储，CRUD 操作，状态机 (pending→approved/rejected/expired) |
| 触发门控 | 四重门控：nudge_interval、cooldown_turns、max_pending、max_reviews_per_session |
| SkillManageTool | create/edit/patch/delete 四种操作，全部走 pending review 流程 |
| 文件系统安全 | 路径遍历防护、名称校验、frontmatter 校验、原子写入 |
| 前端审核面板 | SkillRequestPanel 组件，批准/拒绝/查看内容 |
| 路由层 | `/api/skill-requests` CRUD + approve/reject 端点 |

### Round 2：对话蒸馏 + 反馈循环

| 改进 | 说明 |
|------|------|
| 对话蒸馏 (`_distill_for_review`) | 压缩 tool 输出、保留用户意图和纠正、截断过长消息 |
| 拒绝反馈注入 | 最近 5 条带 note 的 rejected 请求注入 review prompt，防止 Hermes 重复犯错 |
| 蒸馏快照 | `hermes_distill_snapshot` 配置项，用蒸馏版本替代 deepcopy 降低上下文开销 |
| Hermes 状态管理 | per-session LRU 状态（max 100 entries），追踪 iteration/turn/review 计数 |
| 配置化 | `SkillsAutoConfig` 含所有门控参数 |

### Round 3A：中文优先 + 证据摘要

| 改进 | 说明 |
|------|------|
| 证据摘要 (`_build_review_evidence_summary`) | 四段式中文摘要：【用户意图】【用户偏好/纠正】【关键工具行为】【触发原因】 |
| 敏感信息脱敏 (`_redact`) | 证据摘要和 LLM judge 输入中自动剥离 API_KEY、Bearer token、password |
| 大小限制 | 证据摘要上限 8000 字符，judge 输入各字段截断 200-500 字符 |
| trigger_conversation 存储 | 每条 request 记录触发时的证据摘要，前端可展示"为什么 Hermes 提出这个建议" |
| 前端中文化 | 所有 UI 文案转为中文，拒绝快捷原因（太具体/一次性、已有重复、判断错误等） |

### Round 3A+ Adjustment：LLM 语义判断

| 改进 | 说明 |
|------|------|
| N-gram 降级为 prefilter | char 3-gram + Jaccard 相似度仅用于候选召回（threshold 0.35），永不单独决定合并/阻止 |
| LLM 语义判断 (`prefilter_and_judge`) | async 方法，先 n-gram 召回 top-5 候选，再调 LLM 做语义等价判断 |
| 判断决策矩阵 | `same_duplicate`(≥0.80→合并)、`related_but_distinct`(新建+关联)、`blacklist_hit`(≥0.85→阻止) |
| maybe_duplicate_ids | JSON 数组字段，关联"相关但不相同"的 pending 请求，前端展示提醒 |
| duplicate_count + last_matched_at | 合并时递增计数、延长 expiry（grace_days），前端展示"已有 N 次相似萃取" |
| thinking 模型兼容 | 自动剥离 `<think...</think` 标签，支持 Qwen3/DeepSeek 等思考模型 |
| 健壮 JSON 提取 | markdown code fence 剥离 + regex 提取 JSON 对象，容错 prose 包裹 |
| Provider 延迟绑定 | `set_provider()` 在 AgentLoop 构造后/重载时更新，避免初始化顺序问题 |

### Round 3A+ Addition：黑名单管理 ✅

| 改进 | 说明 |
|------|------|
| skill_request_blacklist 表 | 独立 SQLite 表，存储被拒绝的 pattern |
| 黑名单 LLM 门控 | n-gram 召回 → LLM 判断 `blacklist_hit`，confidence ≥ 0.85 才阻止，0.6-0.84 创建 pending + 警告 |
| 黑名单 CRUD API | `GET /api/skill-blacklist`、`POST /api/skill-blacklist/{id}/disable` |
| 前端黑名单面板 | 拒绝时可勾选"加入黑名单"，独立面板管理黑名单条目（查看/解除） |
| 柔性黑名单 | 低置信度命中不阻止流程，仅标记为 suspected_blacklist |

### Round 3C：Duplicate Event + Generate Enhanced Candidate ✅

| 改进 | 说明 |
|------|------|
| skill_request_duplicate_events 表 | 轻量 SQLite 表，记录每次 same_duplicate 合并的事件详情（reason/trigger_conversation/content_excerpt/judge_confidence/judge_reason_zh） |
| DuplicateEvent CRUD | `create_duplicate_event`、`list_duplicate_events`、`get_duplicate_events_by_ids` |
| _merge_into_existing 记录事件 | 合并时先插入 DuplicateEvent，失败仅 warning 不影响主流程 |
| 两阶段 LLM pipeline | Stage 1 (`_call_llm_merge_brief_async`): 分析 canonical + duplicate events → merge_brief JSON；Stage 2 (`_call_llm_merge_generate_async`): merge_brief → 完整 enhanced SKILL.md |
| absorbed_points source 验证 | source 只允许 `canonical` / `dup:<selected_event_id>` / `other_extra`，非法 source 拒绝 |
| enhanced SKILL.md 校验 | frontmatter name 匹配 canonical、description 非空、必选 section (When to use / Rules)、final secret scan |
| generate_enhanced_candidate 编排器 | 验证 → brief → generate → 校验 → 创建新 pending（`[增强版候选]` 前缀） |
| trigger_conversation 增强 | 记录 absorbed/ignored/conflicts 实际内容（非仅计数），上限 8000 字符 |
| _SENSITIVE_RE 增加 cookie | 脱敏正则补充 `cookie` 字段 |
| 前端相似萃取区域 | 可折叠 "相似萃取/额外参考" section，checkbox 最多 3 条 + textarea 最多 1000 字 + "生成增强版候选" 按钮 |
| generate-enhanced API | `GET /api/skill-requests/{id}/duplicate-events`（懒加载）、`POST /api/skill-requests/{id}/generate-enhanced` |
| 安全审计修复 | source 验证、section 验证、name 匹配、description 非空、secret scan、trigger_conversation 详情 |

---

## 三、修改文件清单

| 文件 | 改动性质 |
|------|---------|
| `nanobot/agent/skill_change_store.py` | **核心文件**。相似度函数、LLM judge、SQLite store、黑名单 CRUD、duplicate event CRUD、两阶段 LLM pipeline、冲突检测、过期清理 |
| `nanobot/agent/loop.py` | Hermes 触发逻辑、证据摘要、对话蒸馏、store 创建 + provider 绑定 |
| `nanobot/agent/tools/skill_manage.py` | SkillManageTool：async prefilter→create_request 流程、输入校验、文件系统操作 |
| `nanobot/web/routes.py` | skill-requests CRUD + approve/reject、blacklist list/disable、duplicate events + generate-enhanced 路由 |
| `nanobot/config/schema.py` | `SkillsAutoConfig`（11 个 hermes_* 配置项）、`LangfuseConfig` |
| `nanobot/providers/custom_provider.py` | httpx client 加 `trust_env: False` 绕过公司代理（本地调试改动，不上库） |
| `frontend/components/SkillRequestPanel.tsx` | 审核面板：中文 UI、黑名单管理、证据摘要、合并/关联展示、拒绝快捷原因、相似萃取折叠区、生成增强版候选、related-existing 警告 |
| `frontend/components/SkillAutoPanel.tsx` | Hermes 开关面板 |
| `tests/test_hermes_create_only.py` | **新增**。P0 测试：allowed_actions、prompt 验证、enhanced 守卫、跨 action 合并守卫 |
| `tests/test_existing_skill_coverage.py` | **新增**。P0.5 测试：ExistingSkillSummary、prefilter、coverage judge、create_request 集成 |

---

## 四、SQLite Schema

### skill_change_requests

```sql
CREATE TABLE IF NOT EXISTS skill_change_requests (
    id TEXT PRIMARY KEY,
    action TEXT NOT NULL,              -- create / edit / patch / delete
    skill_name TEXT NOT NULL,
    proposed_content TEXT,             -- 完整 SKILL.md 内容
    old_string TEXT,                   -- patch 用的查找文本
    new_string TEXT,                   -- patch 用的替换文本
    reason TEXT NOT NULL,              -- LLM 给出的变更原因
    trigger_session TEXT,              -- 触发的 session key
    trigger_conversation TEXT,         -- 证据摘要
    status TEXT DEFAULT 'pending',     -- pending / approved / rejected / expired / blocked_by_blacklist / merged_with_existing
    priority INTEGER DEFAULT 0,        -- 冲突时提升
    conflict_ids TEXT,                 -- JSON: 冲突的 request ID 列表
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    reviewed_at TEXT,
    reviewer_note TEXT,
    duplicate_count INTEGER DEFAULT 0, -- 被合并的次数
    last_matched_at TEXT,              -- 最近一次被匹配的时间
    similarity_key TEXT,               -- N-gram 相似度 key
    maybe_duplicate_ids TEXT           -- JSON: 关联但不相同的 request ID 列表
);
-- Indexes: idx_scr_status(status), idx_scr_skill(skill_name)
```

### skill_request_blacklist

```sql
CREATE TABLE IF NOT EXISTS skill_request_blacklist (
    id TEXT PRIMARY KEY,
    skill_name TEXT NOT NULL,
    similarity_key TEXT NOT NULL,      -- 用于 N-gram 召回
    reason TEXT,
    reviewer_note TEXT,
    source_request_id TEXT,            -- 来源 rejected request
    created_at TEXT NOT NULL,
    updated_at TEXT,
    expires_at TEXT,
    enabled INTEGER DEFAULT 1          -- 软删除
);
-- Indexes: idx_bl_enabled(enabled), idx_bl_skill(skill_name)
```

### skill_request_duplicate_events

```sql
CREATE TABLE IF NOT EXISTS skill_request_duplicate_events (
    id TEXT PRIMARY KEY,
    target_request_id TEXT NOT NULL,   -- 关联的主 pending request
    candidate_skill_name TEXT,         -- 合并候选的 skill_name (≤64 chars)
    candidate_reason TEXT,             -- 合并候选的 reason (≤300 chars, 已脱敏)
    candidate_trigger_conversation TEXT, -- 合并候选的证据摘要 (≤500 chars, 已脱敏)
    candidate_content_excerpt TEXT,    -- 合并候选的内容摘要 (≤500 chars, 已脱敏)
    judge_confidence REAL,             -- LLM judge 置信度
    judge_reason_zh TEXT,              -- LLM judge 中文解释 (≤300 chars, 已脱敏)
    created_at TEXT NOT NULL
);
-- Indexes: idx_sde_target(target_request_id)
```

> **注意**：duplicate event 不是独立审核对象，只是主 pending 的 evidence。只能通过 `GET /api/skill-requests/{id}/duplicate-events` 懒加载。

---

## 五、关键算法

### 5.1 触发门控

```python
should_trigger = (
    iters_since_skill_manage >= hermes_nudge_interval     # 默认 10 次工具调用
    and pending_count < hermes_max_pending                # 默认 < 5
    and user_turns_since_review >= hermes_cooldown_turns  # 默认 >= 5 轮
    and reviews_this_session < hermes_max_reviews_per_session  # 默认 < 3
)
```

### 5.2 N-gram 候选召回 (Prefilter Only)

```
输入: 新请求的 (action, skill_name, reason)
     ↓
normalize_text_for_similarity  →  char_ngrams(text, n=3)  →  Jaccard similarity
     ↓
召回条件:
  - exact action+name match → score=1.0（强候选）
  - similarity_key Jaccard ≥ 0.35（弱候选）
  - skill_name Jaccard ≥ 0.75（仅当无 similarity_key 时）
     ↓
取 top-5 候选送 LLM judge
```

### 5.3 LLM 语义判断决策矩阵

```
LLM judge 返回 JSON:
{
  "decision": "same_duplicate | related_but_distinct | blacklist_hit | uncertain",
  "confidence": 0.0-1.0,
  "target_id": "...",
  "reason_zh": "中文解释"
}

应用规则:
┌─────────────────────┬───────────┬──────────────────────────────────────┐
│ decision            │ confidence│ 操作                                 │
├─────────────────────┼───────────┼──────────────────────────────────────┤
│ same_duplicate      │ ≥ 0.80    │ 合并到 target pending                │
│                     │           │ duplicate_count++, 延长 expiry       │
│ same_duplicate      │ < 0.80    │ 新建 pending + maybe_duplicate_ids   │
│ related_but_distinct│ any       │ 新建 pending + maybe_duplicate_ids   │
│ blacklist_hit       │ ≥ 0.85    │ 阻止创建 (blocked_by_blacklist)      │
│ blacklist_hit       │ 0.60-0.84 │ 新建 pending + suspected 标记        │
│ blacklist_hit       │ < 0.60    │ 新建普通 pending                     │
│ 无候选 / LLM 失败  │ N/A       │ 新建普通 pending（永不自动合并/阻止） │
└─────────────────────┴───────────┴──────────────────────────────────────┘
```

### 5.4 证据摘要生成

```
对话历史 → 四段式中文摘要:
  【用户意图】     ← 前 3 条 user 消息 (各 ≤500 字符)
  【用户偏好/纠正】 ← 匹配纠正关键词的 user 消息 ("以后"、"不要"、"记住"...)
  【关键工具行为】  ← tool summary 中的 errors、test_results、file_paths
  【触发原因】     ← hermes_state 统计 (iter/turn/review/pending_count)

所有字段经过 _redact() 脱敏处理
总长度 ≤ 8000 字符
```

---

## 六、配置项

```yaml
skills_auto:
  darwin_enabled: false                    # Darwin 技能自动优化
  hermes_enabled: false                    # Hermes 技能自动萃取+审核
  hermes_nudge_interval: 10                # 触发间隔（工具调用次数）
  request_expiry_days: 60                  # pending 请求自动过期天数
  hermes_cooldown_turns: 5                 # 最少用户轮次间隔
  hermes_max_pending: 5                    # pending 上限（暂停触发）
  hermes_max_reviews_per_session: 3        # 单 session 最大审核次数
  hermes_distill_snapshot: true            # 使用蒸馏版本
  hermes_use_reject_feedback: true         # 注入拒绝反馈
  hermes_duplicate_grace_days: 14          # 合并时延长审核宽限期
```

---

## 七、测试覆盖

| 测试文件 | 用例数 | 覆盖范围 |
|---------|--------|---------|
| `test_hermes_gating.py` | 21 | CRUD、冲突检测、过期、四重门控条件 |
| `test_hermes_round3.py` | 35 | 证据摘要、trigger_conversation、N-gram prefilter、LLM judge 合并/阻止/回退、黑名单 CRUD、配置、脱敏 |
| `test_hermes_distill_feedback.py` | 24 | 对话蒸馏、拒绝反馈注入、蒸馏压缩 |
| `test_skill_apply_security.py` | 26 | 名称校验、路径遍历防护、create/edit/patch/delete 文件系统操作 |
| `test_hermes_duplicate_events.py` | 35 | DuplicateEvent 模型、事件 CRUD、same_duplicate 合并记录、两阶段 LLM pipeline、安全审计（source 验证、secret scan、name 匹配、section 校验、description 非空、trigger_conversation 详情）|
| `test_hermes_llm_judge_live.py` | 16 | 真实 Qwen3-235B 调用：正向（合并/等价/黑名单命中）+ 负向（无关/同类别不同目的/重叠关键词/roundtrip）|
| `test_hermes_create_only.py` | 18 | **新增 (P0)**：allowed_actions schema/runtime 守卫、Hermes prompt 验证、generate-enhanced action 守卫、跨 action 合并拒绝 |
| `test_existing_skill_coverage.py` | 25 | **新增 (P0.5)**：ExistingSkillSummary 扫描/解析、prefilter 候选召回、LLM coverage judge、create_request 集成（covered/related/no_match/blacklist 优先级）、to_dict 新字段 |
| `test_hermes_toctou_replace_all.py` | 18 | **新增 (P0)**：TOCTOU 文件状态快照（hash/mtime/size）、磁盘冲突检测（create 已存在/patch hash 变/edit 删/delete 已删）、replace_all 全链路、DB 迁移幂等 |
| `test_hermes_conservation_law.py` | 16 | **新增 (P0.5)**：Conservation Law prompt 验证、change_summary 提取/校验、fail-closed（缺失/非 dict/非 list/无 reason）、trigger_conversation 变更摘要、proposed_content 清洁 |
| `test_hermes_audit_events.py` | 18 | **新增 (P1)**：AuditEvent schema、CRUD + 过滤、失败隔离、redact + 截断、黑名单/合并/增强失败/disk_conflict 决策点审计、input_hash 不可逆、5 场景 E2E smoke |

**总计：277+ 个测试，全部通过。**

运行命令：
```bash
# 单元测试（含 P0/P0.5）
python -m pytest tests/test_hermes_round3.py tests/test_hermes_gating.py \
    tests/test_hermes_distill_feedback.py tests/test_skill_apply_security.py \
    tests/test_hermes_duplicate_events.py tests/test_hermes_create_only.py \
    tests/test_existing_skill_coverage.py -v

# 实时 LLM 集成测试（需要 Qwen3 端点可达）
python -m pytest tests/test_hermes_llm_judge_live.py -v -s

# TypeScript 检查
cd frontend && npx tsc --noEmit
```

---

## 八、API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/skill-requests` | 列出所有变更请求，可选 `?status=pending` 过滤 |
| GET | `/api/skill-requests/{id}` | 获取单个请求详情 |
| POST | `/api/skill-requests/{id}/approve` | 批准并执行变更（写入 skills/ 目录） |
| POST | `/api/skill-requests/{id}/reject` | 拒绝，body: `{note, blacklist}` |
| GET | `/api/skill-requests/{id}/duplicate-events` | 懒加载 duplicate events（evidence，非审核对象）|
| POST | `/api/skill-requests/{id}/generate-enhanced` | 两阶段 LLM pipeline → 新 pending（不自动 approve）|
| GET | `/api/skill-blacklist` | 列出黑名单条目 |
| POST | `/api/skill-blacklist/{id}/disable` | 解除黑名单条目 |

---

## 九、LLM Judge 实测结果 (Qwen3-235B-Instruct)

### 正向测试

| 场景 | 判定 | 置信度 |
|------|------|--------|
| 近似重复请求 (CI 流水线搭建 vs 配置) | `same_duplicate` | 0.98 |
| 中文语义等价 (认证 vs 鉴权) | `same_duplicate` | 0.95 |
| 相关但不同 (K8s 部署 vs 监控) | `related_but_distinct` | 0.85 |
| 黑名单命中 (垃圾营销邮件) | `blacklist_hit` | 0.95 |
| 黑名单未命中 (营销邮件 vs 系统通知) | `related_but_distinct` | 0.85 |
| Roundtrip 合并 (Docker ECR 构建) | `merged_with_existing` | 0.95 |

### 负向测试（Hard Cases — prefilter 通过但 LLM 正确拒绝合并）

| 场景 | 判定 | 置信度 | 正确性 |
|------|------|--------|--------|
| Terraform vs Ansible（同 skill 名，不同工具） | `related_but_distinct` | 0.85 | ✓ |
| K8s 部署 vs K8s 监控（同 skill 名，不同领域） | `related_but_distinct` | 0.85 | ✓ |
| API 认证配置 vs Token 轮换（重叠关键词，不同目标） | `related_but_distinct` | 0.85 | ✓ |
| Kafka+Flink 实时 vs Airflow+Spark 批处理 (roundtrip) | `related_but_distinct` | 0.85 | ✓ |

**误合并率：0/10。**

---

## 九-B、Round 3D：Hermes Create-only + Existing Skill Coverage Check

> 实施日期：2026-05-18

### 设计目标

1. **Hermes 只负责创建新 skill**，不 patch/edit/delete 已有 skill。
2. **创建前检查已有正式 skill 是否覆盖**，防止 create-only 导致 skill 库膨胀。
3. 覆盖检查仅用于判断"是否需要创建"，不用于修改已有 skill。
4. 已有 skill 修改未来交给 Darwin / manual / admin 路径。

### P0 改动：Hermes Create-only

| 改动 | 说明 |
|------|------|
| `SkillManageTool.allowed_actions` | 构造函数新增 `allowed_actions: set[str] | None = None`；JSON schema `action.enum` 动态生成；`execute()` 开头硬校验 |
| Hermes review 传 `allowed_actions={"create"}` | Hermes sub-agent 只能看到 create action；主 agent 保持 unrestricted |
| Hermes prompt 重写 | 删除 "PREFER GENERALIZING" / `action='patch'` 引用；新增 "Do NOT patch, edit, or delete existing skills" |
| `generate_enhanced_candidate` 守卫 | `canonical.action != "create"` 时直接拒绝，不调 LLM |
| `_merge_into_existing` 跨 action 守卫 | incoming 与 existing action 不同时不合并，降级为 `related_but_distinct` |
| `prefilter_and_judge` 返回值变更 | 从 `dict | None` 改为 `(judge_result, coverage_result)` 元组 |

### P0.5 改动：Existing Skill Coverage Check ✅

| 改动 | 说明 |
|------|------|
| `ExistingSkillSummary` 数据类 | skill_name / description / path / content_excerpt / when_to_use / do_not_use / similarity_key / file_hash |
| `list_existing_skill_summaries()` | 扫描 skills_dir 下的 SKILL.md，解析 frontmatter + 正文，跳过无法解析的 skill |
| `_prefilter_existing_skills()` | 复用 n-gram/Jaccard，exact name → 1.0，Jaccard ≥ 0.35 → candidate，top-5 |
| `_EXISTING_COVERAGE_JUDGE_PROMPT` | 独立 LLM judge prompt，decision: existing_covered / existing_related_but_distinct / no_existing_match |
| `_call_llm_coverage_judge_async()` | 异步 LLM 调用，返回覆盖判断结果 |
| `create_request` 流程重排 | blacklist → existing coverage → pending duplicate → normal create |
| `covered_by_existing` 状态 | confidence ≥ 0.85 时不创建 pending，返回虚拟状态 |
| `related_existing` 元数据 | confidence ≥ 0.65 时创建 pending + related_existing_skill_ids / related_existing_skill_note |
| SQLite 新增 3 列 | related_existing_skill_ids / related_existing_skill_note / existing_coverage_status |
| 前端 related-existing 警告 | 黄色提示框："可能相关已有技能：xxx。Hermes 判断它相关但不完全覆盖，请审核是否真的需要新技能。" |

### create_request 流程顺序

```
blacklist (最高优先级)
  → existing skill coverage check
    → existing_covered (conf ≥ 0.85) → 不创建 pending
    → existing_related (conf ≥ 0.65) → 携带 related_existing 元数据
  → pending duplicate check
    → same_duplicate (conf ≥ 0.80, same action) → 合并 duplicate event
    → same_duplicate (不同 action) → 降级为 related_but_distinct
    → related_but_distinct → 创建 pending + maybe_duplicate_ids
  → normal create pending
```

### SQLite Schema 变化

```sql
-- 新增列（skill_change_requests 表）
ALTER TABLE skill_change_requests ADD COLUMN related_existing_skill_ids TEXT;
ALTER TABLE skill_change_requests ADD COLUMN related_existing_skill_note TEXT;
ALTER TABLE skill_change_requests ADD COLUMN existing_coverage_status TEXT;
```

### LLM Coverage Judge JSON 示例

```json
{
  "decision": "existing_covered",
  "confidence": 0.92,
  "skill_name": "k8s-deploy",
  "reason_zh": "已有技能「k8s-deploy」已覆盖 K8s 部署场景，触发条件和工作流相同。"
}
```

### covered_by_existing 返回示例

```json
{
  "success": true,
  "message": "已有技能「k8s-deploy」已覆盖该模式，未创建新建议。",
  "status": "covered_by_existing",
  "existing_skill_name": "k8s-deploy",
  "reason_zh": "已有技能已覆盖 K8s 部署场景"
}
```

### related_existing pending 示例

```json
{
  "id": "a1b2c3d4",
  "action": "create",
  "skill_name": "k8s-monitor",
  "status": "pending",
  "existing_coverage_status": "related_existing",
  "related_existing_skill_ids": "[\"k8s-deploy\"]",
  "related_existing_skill_note": "已有技能「k8s-deploy」相关但不完全覆盖。"
}
```

---

## 九-B-2、P0：TOCTOU File State Check + replace_all ✅

> 实施日期：2026-05-19

### 设计目标

Approve 时验证目标文件在 pending 创建后未被外部修改（TOCTOU 防护），并支持 `replace_all` 参数传递给 `apply_patch`。

### 核心改动

| 改动 | 说明 |
|------|------|
| `target_file_exists` / `target_file_hash` / `target_file_mtime` / `target_file_size` | `create_request` 时快照目标文件状态（sha256 / mtime / size） |
| `replace_all` 字段 | `create_request` 参数，存储到 DB，approve 时传给 `apply_patch` |
| `check_disk_conflict(req)` | 对比 pending 快照 vs 当前磁盘状态：create→是否已存在、edit/patch/delete→是否被删除或 hash 变化 |
| routes.py TOCTOU 检查 | approve 前调 `check_disk_conflict`，冲突返回 HTTP 409 + 中文错误消息 |
| 前端 409 处理 | `SkillRequestPanel.approve()` 对 409 显示 "文件冲突" 前缀错误 |
| DB 迁移幂等 | 5 列 ALTER TABLE 用 try/except OperationalError，重复执行不报错 |
| 旧数据兼容 | 迁移前创建的 pending（file state 字段为 NULL）不触发误报 |

### SQLite Schema 变化

```sql
ALTER TABLE skill_change_requests ADD COLUMN replace_all INTEGER DEFAULT 0;
ALTER TABLE skill_change_requests ADD COLUMN target_file_exists INTEGER;
ALTER TABLE skill_change_requests ADD COLUMN target_file_hash TEXT;
ALTER TABLE skill_change_requests ADD COLUMN target_file_mtime TEXT;
ALTER TABLE skill_change_requests ADD COLUMN target_file_size INTEGER;
```

---

## 九-B-3、P0.5：Conservation Law + change_summary_zh ✅

> 实施日期：2026-05-19

### 设计目标

generate-enhanced 产出必须通过 **守恒原则（Conservation Law）** 验证：不允许删除、弱化、重写 canonical pending 的核心规则。LLM 必须输出结构化变更摘要 `change_summary`，作为人类审核的审计追踪。

### 核心改动

| 改动 | 说明 |
|------|------|
| `_MERGE_GENERATE_PROMPT` 新增守恒原则 | 5 条核心规则 + change_summary 输出格式规范 |
| `change_summary` 结构 | `preserved_points` / `added_points` / `changed_points`（需 `reason_zh`）/ `ignored_points` |
| `_call_llm_merge_generate_async` 返回值变更 | 从 `str | None` 改为 `tuple[str | None, dict | None]`，提取并剥离 `---change_summary---` 块 |
| Fail-closed 校验 | `change_summary is None` → 拒绝；非 dict → 拒绝；字段非 list → 拒绝；`changed_points` 条目非 dict → 拒绝；缺 `reason_zh` → 拒绝 |
| 不完整标记处理 | 有 start marker 无 end marker 时剥离 start marker，不泄漏到 SKILL.md |
| `trigger_conversation` 增加变更摘要 | 审核者可看到保留/新增/修改/未吸收的完整变更摘要 |
| `proposed_content` 清洁 | change_summary block 在存入 pending 前被剥离 |

### change_summary 格式

```
---change_summary---
{"preserved_points": ["保留了规则A"], "added_points": ["新增了部署前检查"],
 "changed_points": [{"original_zh": "旧规则", "new_zh": "新规则", "reason_zh": "原因"}],
 "ignored_points": ["一次性路径"]}
---end_change_summary---
```

---

## 九-B-4、P1：Hermes Structured Audit Events ✅

> 实施日期：2026-05-19

### 设计目标

Hermes 的后台关键决策（judge / coverage / duplicate merge / enhanced pipeline / approve）记录为结构化事件，便于回答：
- 为什么这个 pending 被合并？
- 为什么这个 request 被 blacklist block？
- 为什么 generate-enhanced 失败？
- 为什么 approve 返回 disk_conflict？

### hermes_audit_events 表

```sql
CREATE TABLE IF NOT EXISTS hermes_audit_events (
    id TEXT PRIMARY KEY,                -- uuid hex[:16]
    created_at TEXT NOT NULL,           -- ISO UTC
    event_type TEXT NOT NULL,           -- 事件类型枚举
    request_id TEXT,                    -- 关联的 pending ID（nullable）
    skill_name TEXT,                    -- 技能名
    session_key TEXT,                   -- 触发 session
    decision TEXT,                      -- LLM judge/coverage 决策
    confidence REAL,                    -- LLM 置信度
    target_id TEXT,                     -- 匹配到的 target（pending ID 或 skill name）
    effect TEXT,                        -- 结果：blocked / merged / created / error
    reason_zh TEXT,                     -- 中文原因（≤500 字符，_redact 脱敏）
    error_code TEXT,                    -- 错误代码
    error_message TEXT,                 -- 错误消息（≤500 字符，_redact 脱敏）
    input_hash TEXT,                    -- sha256(action|name|reason[:200])[:16]
    metadata_json TEXT                  -- JSON 扩展字段（≤2000 字符，_redact 脱敏）
);
-- Indexes: idx_ae_event_type, idx_ae_request_id, idx_ae_skill_name, idx_ae_created_at
```

### 安全保障

- **不存完整 prompt / proposed_content / trigger_conversation**。仅存 `request_id` / `target_id` / `reason_zh` / `error_code`。
- **`reason_zh` / `error_message` / `metadata_json`**：统一经过 `_redact()` 脱敏 + 长度截断。
- **`input_hash`**：`sha256[:16]` 不可逆，不存原文。
- **写入失败不影响主流程**：`record_audit_event` 内部 try/except Exception，仅 `logger.warning`。

### 事件类型

| 类别 | event_type | 触发点 |
|------|-----------|--------|
| 判断 | `judge_blacklist_hit` | blacklist_hit conf≥0.85（blocked）/ 0.6-0.84（downgraded） |
| 判断 | `judge_same_duplicate` | same_duplicate 合并成功 |
| 判断 | `judge_related_but_distinct` | related_but_distinct 新建 pending |
| 覆盖 | `coverage_covered` | existing_covered 跳过创建 |
| 覆盖 | `coverage_not_covered` | existing_related_but_distinct 关联已有 |
| 增强 | `merge_brief_invalid` | brief LLM 返回失败 |
| 增强 | `merge_brief_rejected` | brief 判定无新增价值 |
| 增强 | `change_summary_missing` | LLM 未输出 change_summary |
| 增强 | `change_summary_invalid` | change_summary schema 不合法 |
| 增强 | `enhanced_validation_failed` | name/frontmatter/size/section/secrets 校验失败 |
| 增强 | `enhanced_pending_created` | 增强版候选创建成功 |
| 审批 | `approve_disk_conflict` | TOCTOU 检测到文件变化 |
| 审批 | `approve_apply_failed` | apply 异常或返回失败 |
| 审批 | `approve_apply_success` | apply + approve 均成功 |

### Store 方法

- `record_audit_event(*, event_type, request_id, skill_name, session_key, decision, confidence, target_id, effect, reason_zh, error_code, error_message, input_hash, metadata)` — 写入审计事件
- `list_audit_events(*, request_id=None, skill_name=None, event_type=None, limit=50)` → `list[AuditEvent]`

### 剩余非阻塞项

1. **Audit TTL** — `hermes_audit_events` 表无清理机制，持续增长。后续加 `DELETE WHERE created_at < ?`。
2. **`approve_request()` store-level 审计** — 目前 `approve_apply_success` 在 routes.py 层记录。其他代码直接调用 `approve_request()` 不会产生审计。低优先级。
3. **测试 warning** — `test_audit_event_recorded_for_generate_enhanced_failure` 曾使用 `asyncio.get_event_loop()` 产生 DeprecationWarning，已改为 `@pytest.mark.asyncio`。

---

## 九-C、Round 3E：Hermes Runtime Hot Reload

> 实施日期：2026-05-19

### 设计目标

配置更新 API 修改 `hermes_enabled` / `nudge_interval` / `cooldown` / `max_pending` / `max_reviews` 等 `skills_auto` 配置后，**不需要重启 nanobot 服务**。热生效只从下一轮用户消息或下一次 agent loop 边界开始，不追溯历史。

### 修改前行为

- `_skills_auto_config` 在 `AgentLoop.__init__` 里读取一次，运行期间不更新。
- `routes.py` 配置更新只 reload provider/model/email/welink，不 reload `skills_auto`。
- 改 `hermes_enabled` 后必须重启 nanobot 才生效。

### 核心改动

| 改动 | 说明 |
|------|------|
| `AgentLoop.reload_skills_auto_config()` | 同步方法，重新 `load_config().skills_auto`，更新内存配置、context builder、tool registry |
| `_hermes_epoch` | 全局计数器，每次 hermes_enabled 或门控配置变化时递增 |
| `_get_hermes_state()` lazy epoch reset | 发现 epoch 不匹配时重置 `iters_since_skill_manage=0`, `reviews_this_session=0`, `user_turns_since_review=cooldown_turns` |
| `_run_skill_review()` epoch guard | 入口处检查 `hermes_enabled` 和 epoch，不匹配时直接 return，防止 stale write |
| `routes.py` 配置更新 API | 保存后调用 `reload_skills_auto_config()`，返回新字段 |
| Tool registry rebuild | `reload_skills_auto_config()` 内注册/注销 `skill_manage` tool |

### Runtime Reload 语义

1. **生效边界**：`next_turn` / next loop boundary。当前 in-flight model call 不中断，新配置从下一轮开始生效。
2. **不追溯历史**：off→on 后从新工具调用开始计数（epoch reset → iters=0），不追溯旧的 tool call 历史。
3. **不立刻 review**：on 之后不立即触发 review，需满足 nudge_interval / cooldown / pending_count / max_reviews 门控。
4. **Cooldown 满足**：off→on 后 `user_turns_since_review` 初始化为 `cooldown_turns`，避免第一次 review 被不存在的"上一次 review"阻塞。
5. **Disable 不删 pending**：关闭 Hermes 时已有 pending 保留。
6. **In-flight 防护**：已调度的 `_run_skill_review` 在写入前检查 epoch 和 `hermes_enabled`，不匹配则放弃。

### Epoch / State Reset 逻辑

```
reload_skills_auto_config():
  new_cfg = load_config().skills_auto
  old_cfg = self._skills_auto_config
  self._skills_auto_config = new_cfg
  self.context.set_skills_auto_config(new_cfg)
  rebuild_tool_registry(new_cfg)

  if hermes_enabled or gating fields changed:
    self._hermes_epoch += 1

_get_hermes_state(session_key):
  entry = get_or_create(session_key)
  if entry.epoch != self._hermes_epoch:
    entry.iters_since_skill_manage = 0
    entry.reviews_this_session = 0
    entry.user_turns_since_review = new_cfg.hermes_cooldown_turns
    entry.epoch = self._hermes_epoch
  return entry

_run_skill_review(snapshot, review_epoch=...):
  if not hermes_enabled: return        # disabled → abort
  if review_epoch != current_epoch: return  # stale → abort
  ... proceed with review ...
```

### 配置更新 API 响应示例

```json
{
  "ok": true,
  "saved": true,
  "reloaded": true,
  "runtime_applied": true,
  "effective_from": "next_turn",
  "requires_restart": false,
  "skills_auto_applied": true,
  "current_model": "qwen3-235b-a22b",
  "current_provider": "custom"
}
```

### Review-now 设计（未实现，预留）

```
POST /api/sessions/{id}/hermes/review-now

语义：
- 显式对当前 session snapshot 触发一次 review
- 可以绕过 nudge_interval
- 仍遵守 pending_count / blacklist / existing coverage / create-only
- 计入 reviews_this_session
```

### 测试覆盖

| 测试 | 说明 |
|------|------|
| `test_reload_skills_auto_config_updates_enabled_without_restart` | reload 后 hermes_enabled 更新，tool 注册 |
| `test_enable_hermes_mid_session_starts_counting_from_zero` | off→on 后计数器从 0 开始 |
| `test_enable_hermes_does_not_retroactively_trigger_review` | 不追溯历史 tool call |
| `test_enable_hermes_initializes_cooldown_as_satisfied` | user_turns_since_review=cooldown_turns |
| `test_disable_hermes_stops_future_triggers` | off 后 tool 注销、不触发 |
| `test_disable_hermes_prevents_inflight_review_write` | epoch guard 阻止 stale write |
| `test_reload_skills_auto_config_increments_epoch_on_toggle` | epoch 在 toggle 时递增 |
| `test_reload_skills_auto_config_rebuilds_tools_for_next_turn` | tool registry 正确重建 |
| `test_config_update_api_reports_runtime_applied` | API 返回新字段 |
| `test_pending_survives_disable` | pending 不受 disable 影响 |
| `test_epoch_bumps_on_gating_config_change` | nudge_interval 等变化也触发 epoch |
| `test_lazy_epoch_reset_resets_all_counters` | epoch reset 时所有计数器归零 |

---

## 十、待改进方向

1. **LLM judge 成本控制** — 高频场景加 debounce（同 session 30s 内不重复调 judge）
2. **Judge prompt A/B 测试** — 对比不同 prompt 版本的 merge 准确率
3. **黑名单半自动提升** — 多次被 judge 标记 blacklist_hit 但 confidence 不足的 pattern 可自动升级
4. **前端批量操作** — maybe_duplicate_ids 积累多个关联 pending 时支持一键合并
5. ~~**Metrics 采集**~~ → 已由 P1 audit events 部分覆盖，可通过 `list_audit_events` 查询 decision 分布
6. **Thinking 模型适配** — 当前仅处理 `<think` 标签，可进一步支持 reasoning_content 字段直接取值
7. **apply_delete 非原子** — 当前使用 `shutil.rmtree`，可改为 rename-to-trash 作为 P2 安全改进
8. **reviews_this_session 生命周期** — 当前按 session 生命周期累计上限，未随时间重置（已知限制）
9. **Audit TTL** — `hermes_audit_events` 表无清理机制，持续增长，需加 `DELETE WHERE created_at < ?`
10. **`approve_request()` store-level 审计** — 直接调用 `approve_request()` 不走 routes.py 时不产生审计事件
11. **Existing skill coverage cache** — 大量 skill 时避免每次扫描文件系统
