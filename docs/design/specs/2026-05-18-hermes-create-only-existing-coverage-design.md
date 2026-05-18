# Hermes Create-only + Existing Skill Coverage Check 设计规格

> 日期：2026-05-18
> 状态：待审核

## 一、目标

1. Hermes 后台自动萃取只负责创建新 skill，不允许 edit/patch/delete。
2. 创建新 skill 前必须与已有正式 skills 做覆盖检查，避免 skill 库膨胀。
3. 覆盖检查仅用于判断"是否需要创建"，不用于修改已有 skill。

## 二、P0：Hermes create-only

### 2.1 skill_manage.py — allowed_actions

`SkillManageTool.__init__` 新增参数：
```python
def __init__(self, workspace, change_store, session_key="",
             trigger_conversation="", allowed_actions: set[str] | None = None):
    self._allowed_actions = allowed_actions
```

JSON schema `action.enum` 动态生成：
- `allowed_actions=None` → `["create", "edit", "patch", "delete"]`
- `allowed_actions={"create"}` → `["create"]`

`execute()` 开头硬校验：
```python
if self._allowed_actions is not None and action not in self._allowed_actions:
    return {"success": False, "error": f"Action '{action}' is not allowed in this context."}
```

### 2.2 loop.py — Hermes 传 allowed_actions={"create"}

Hermes review sub-agent 实例化：
```python
SkillManageTool(
    workspace=self.workspace,
    change_store=self.skill_change_store,
    trigger_conversation=evidence_summary,
    allowed_actions={"create"},
)
```

主 agent 实例化保持 unrestricted（`allowed_actions=None`）。

Hermes prompt 重写要点：
- 删除 "PREFER GENERALIZING" 和 `action='patch'` 引用
- 新增：Hermes 只能调用 `skill_manage(action="create")`
- 新增：如果已有 skill 已覆盖该模式，不创建新 skill
- 新增：如果已有 skill 相关但不完全覆盖，仅在确实是独立可复用能力时才 create

### 2.3 skill_change_store.py — generate-enhanced + merge 守卫

`generate_enhanced_candidate`：`canonical.action != "create"` 时直接返回错误，不调 LLM。

`_merge_into_existing`：`incoming.action != existing.action` 时不自动合并，降级为 `related_but_distinct` + `maybe_duplicate_ids`。

## 三、P0.5：Existing Skill Coverage Check

### 3.1 ExistingSkillSummary

```python
@dataclass
class ExistingSkillSummary:
    skill_name: str
    description: str
    path: str
    content_excerpt: str          # 正文前 500 字符
    when_to_use: str              # "When to use" 段落
    do_not_use: str               # "Do not use when" 段落
    similarity_key: str
    file_hash: str | None
```

来源：扫描 `skills/<skill_name>/SKILL.md`，解析 YAML frontmatter + 正文。

`list_existing_skill_summaries(skills_dir: Path) -> list[ExistingSkillSummary]`
- 无法解析的 skill 记录 warning 后跳过

### 3.2 Existing skill prefilter

复用 `normalize_text_for_similarity` + `char_ngrams` + Jaccard：
- exact name match → score=1.0
- similarity_key Jaccard ≥ 0.35 → candidate
- 取 top-5 送 LLM coverage judge

### 3.3 LLM coverage judge

独立 prompt `_EXISTING_COVERAGE_JUDGE_PROMPT`，不复用 duplicate prompt。

decision 枚举：
- `existing_covered` — 已有 skill 已覆盖，不应创建
- `existing_related_but_distinct` — 相关但有独立边界，可以创建
- `no_existing_match` — 无匹配，正常创建

阈值：
- `existing_covered` + confidence ≥ 0.85 → 不创建 pending，返回 `covered_by_existing`
- `existing_related_but_distinct` + confidence ≥ 0.65 → 创建 pending + 记录 related_existing
- LLM 失败 → fallback normal pending

### 3.4 create_request 流程顺序

```
blacklist → existing skill coverage → pending duplicate → normal create
```

### 3.5 SQLite 新增字段

`skill_change_requests` 表新增 3 个 nullable 列：
- `related_existing_skill_ids TEXT` — JSON 数组
- `related_existing_skill_note TEXT`
- `existing_coverage_status TEXT`

### 3.6 前端展示

TypeScript 类型新增对应字段。Detail modal 中：
- 有 `related_existing_skill_ids` 时显示中文提示："可能相关已有技能：xxx。Hermes 判断它相关但不完全覆盖，请审核是否真的需要新技能。"

## 四、不做的事项

- file_hash / optimistic locking
- origin/source 字段
- Metrics/Audit、Darwin、skill usage telemetry
- patch/edit/delete existing skill
- Diff UI、PII scanner
- apply_delete rename-to-trash

## 五、新增测试

P0（7 个）：
- test_skill_manage_tool_respects_allowed_actions
- test_skill_manage_tool_schema_limits_action_enum
- test_skill_manage_tool_unrestricted_allows_all_actions
- test_hermes_review_tool_allows_only_create
- test_hermes_prompt_does_not_reference_patch
- test_generate_enhanced_rejects_non_create_action
- test_duplicate_merge_rejects_different_action_types

P0.5（15 个）：
- test_list_existing_skill_summaries_reads_frontmatter
- test_existing_skill_summary_skips_invalid_skill
- test_existing_skill_summary_includes_description_and_excerpt
- test_existing_skill_prefilter_exact_name_match
- test_existing_skill_prefilter_chinese_similarity
- test_existing_skill_prefilter_limits_top_5
- test_existing_coverage_judge_covered_blocks_creation
- test_existing_coverage_judge_related_allows_pending_with_warning
- test_existing_coverage_judge_no_match_allows_pending
- test_existing_coverage_judge_invalid_json_fallback_normal_pending
- test_create_request_blocked_when_existing_skill_covers
- test_create_request_related_existing_still_creates_pending
- test_blacklist_still_has_priority_over_existing_coverage
- test_existing_coverage_runs_before_pending_duplicate
- test_skill_request_to_dict_includes_related_existing

## 六、修改文件清单

| 文件 | 改动性质 |
|------|---------|
| `nanobot/agent/tools/skill_manage.py` | allowed_actions 参数 + schema 动态化 + execute 硬校验 |
| `nanobot/agent/loop.py` | Hermes 传 allowed_actions={"create"} + prompt 重写 |
| `nanobot/agent/skill_change_store.py` | ExistingSkillSummary + coverage check + merge 守卫 + generate-enhanced 守卫 + SQLite 字段 + to_dict |
| `nanobot/web/routes.py` | 返回新字段（如有需要） |
| `frontend/components/SkillRequestPanel.tsx` | TypeScript 类型 + related-existing 展示 |
| `tests/test_hermes_create_only.py` | P0 测试 |
| `tests/test_existing_skill_coverage.py` | P0.5 测试 |
| `docs/HERMES-IMPROVEMENTS.md` | Round 3D 文档更新 |
