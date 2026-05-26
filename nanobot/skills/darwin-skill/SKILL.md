---
name: darwin-skill
description: "Darwin Skill (达尔文.skill): autonomous skill optimizer inspired by Karpathy's autoresearch. Evaluates SKILL.md files using an 8-dimension rubric (structure + effectiveness), runs hill-climbing with git version control, validates improvements through test prompts. Use when user mentions \"优化skill\", \"skill评分\", \"自动优化\", \"auto optimize\", \"skill质量检查\", \"达尔文\", \"darwin\", \"帮我改改skill\", \"skill怎么样\", \"提升skill质量\", \"skill review\", \"skill打分\"."
---

# Darwin Skill

> 借鉴 Karpathy autoresearch 的自主实验循环，对 skills 进行持续优化。
> 核心理念：**评估 → 改进 → 实测验证 → 人类确认 → 保留或回滚**

---

## 设计哲学

1. **单一可编辑资产** — 每次只改一个 SKILL.md
2. **双重评估** — 结构评分（静态分析）+ 效果验证（跑测试看输出）
3. **棘轮机制** — 只保留改进，自动回滚退步
4. **独立评分** — 评分用子agent，避免「自己改自己评」的偏差
5. **人在回路** — 每个skill优化完后暂停，用户确认再继续

---

## 评估 Rubric（8维度，总分100）

### 结构维度（60分）

| # | 维度 | 权重 | 评分标准 |
|---|------|------|---------|
| 1 | **Frontmatter质量** | 8 | name规范、description包含做什么+何时用+触发词、≤1024字符 |
| 2 | **工作流清晰度** | 15 | 步骤明确可执行、有序号、每步有明确输入/输出 |
| 3 | **边界条件覆盖** | 10 | 处理异常情况、有fallback路径、错误恢复 |
| 4 | **检查点设计** | 7 | 关键决策前有用户确认、防止自主失控 |
| 5 | **指令具体性** | 15 | 不模糊、有具体参数/格式/示例、可直接执行 |
| 6 | **资源整合度** | 5 | references/scripts/assets引用正确、路径可达 |

### 效果维度（40分）

| # | 维度 | 权重 | 评分标准 |
|---|------|------|---------|
| 7 | **整体架构** | 15 | 结构层次清晰、不冗余不遗漏 |
| 8 | **实测表现** | 25 | 用测试prompt跑一遍，输出质量是否符合skill宣称的能力 |

### 评分规则
- 维度1-7：每个维度打 1-10 分，乘以权重得到该维度得分
- 维度8：跑2-3个测试prompt，按输出质量打1-10分
- **总分 = Σ(维度分 × 权重) / 10**，满分100
- 改进后总分必须**严格高于**改进前才保留

---

## 自主优化循环

### Phase 0: 环境检查与初始化

**Step 0.1: Git 环境检测**

```
用 exec 执行以下检查：
1. cd {workspace}/skills && git rev-parse --is-inside-work-tree
```

根据结果走不同分支：

| 检测结果 | 处理动作 |
|----------|---------|
| skills 目录不在 git 仓库内 | 告知用户并询问：是否在 skills 目录执行 `git init`？若用户拒绝，整个优化终止（无版本控制无法回滚） |
| skills 在 git 仓库内 | 继续 Step 0.2 |

**Step 0.2: 未提交改动检测**

```
用 exec 执行：
cd {workspace} && git status --porcelain -- skills/
```

| 检测结果 | 处理动作 |
|----------|---------|
| 无未提交改动 | 干净状态，继续 Step 0.3 |
| 有未提交改动（M/??/A 等） | 告知用户："检测到以下文件有未保存的改动：[列出文件]。需要先提交一个 baseline 快照，确保优化过程 diff 干净。" 自动执行 `git add skills/ && git commit -m "chore: pre-optimization baseline"` 后继续 |

**Step 0.3: 确认范围并创建分支**

```
1. 确认优化范围：
   - 全部skills → 用 list_dir 扫描 workspace/skills/*/SKILL.md
   - 指定skills → 用户指定列表
2. 创建 git 分支：auto-optimize/YYYYMMDD-HHMM
3. 初始化 results.tsv（如不存在）
```

### Phase 0.5: 测试Prompt设计

```
for each skill:
  1. 用 read_file 读取 SKILL.md，理解它做什么
  2. 设计2-3个测试prompt，覆盖典型使用场景
  3. 用 write_file 保存到 skill目录/test-prompts.json
展示所有测试prompt给用户，确认后再进入评估。
```

### Phase 1: 基线评估

```
for each skill:
  # 结构评分
  1. read_file SKILL.md 全文
  2. 按维度1-7逐项打分（附简短理由）

  # 效果评分
  3. spawn子agent执行测试prompt（带skill vs 不带skill）
  4. 对比输出，打维度8的分

  # 汇总
  5. 计算加权总分
  6. 记录到 results.tsv
```

展示评分卡，**暂停等用户确认**。

### Phase 2: 优化循环

```
for each skill (按分数从低到高):
  round = 0
  while round < 3:
    round += 1
    Step 1: 找出得分最低的维度
    Step 2: 针对该维度生成1个改进方案
    Step 3: 用 edit_file 修改 SKILL.md → git commit
    Step 4: 重新评估（子agent独立评分）
    Step 5: 新分 > 旧分 → keep; 否则 → git revert
    Step 6: 记录 results.tsv

  展示改动摘要，等用户确认。
```

### Phase 2.5: 探索性重写（可选）

当 hill-climbing 连续2个skill涨不动时，提议从头重写 SKILL.md。**必须征得用户同意。**

### Phase 3: 汇总报告

生成分数变化表格、保留/回滚统计、主要改进摘要。

---

## results.tsv 格式

```tsv
timestamp	commit	skill	old_score	new_score	status	dimension	note	eval_mode
2026-03-31T10:00	baseline	skill-name	-	78	baseline	-	初始评估	full_test
```

文件位置：`workspace/skills/darwin-skill/results.tsv`

---

## 优化策略库

| 优先级 | 策略 | 操作 |
|--------|------|------|
| P0 | 效果问题 | 测试输出偏离意图 → 检查误导性指令 |
| P1 | 结构问题 | 缺少Phase/Step结构 → 重组为线性流程 |
| P2 | 具体性 | 步骤模糊 → 改为具体操作和参数 |
| P3 | 可读性 | 段落过长 → 拆分+用表格 |

---

## 约束规则

1. **不改变skill的核心功能** — 只优化"怎么写"，不改"做什么"
2. **不引入新依赖** — 不添加skill原本没有的文件
3. **每轮只改一个维度** — 可归因
4. **保持文件大小合理** — 不超过原始大小150%
5. **可回滚** — 所有改动在git分支上
6. **优化前必须干净基线** — 有未提交改动时先 commit baseline，保证 diff 只包含 Darwin 的改动
7. **中文为主、简洁为上** — 风格保持一致

---

## 异常与边界条件

| 场景 | 触发条件 | 处理动作 |
|------|---------|---------|
| skills 不在 git 仓库 | `git rev-parse` 失败 | 询问用户是否 `git init`；拒绝则终止优化 |
| 有未提交改动 | `git status --porcelain` 非空 | 自动 `git add + commit` 作为 pre-optimization baseline |
| 分支已存在 | `git checkout -b` 失败 | 分支名末尾加 `-2`/`-3`；第3次失败则切回现有分支 |
| `git revert` 失败 | 冲突 | 先 `git stash`，重试；仍失败则从上个 commit 读出文件手动恢复 |
| MAX_ROUNDS 触顶（默认3） | 已跑3轮仍有短板 | 问用户「继续加1轮 / 探索性重写 / 收工」 |
| 优化后超 150% 体积 | 新文件 > 原 × 1.5 | 拒绝提交，精简后重新评估 |
| SKILL.md 找不到 | 目录存在但无 SKILL.md | 该 skill 终止，results.tsv 记 `status=error` |
| test-prompts.json 已存在 | 文件已在 skill 目录 | 复用并展示，问用户「复用 / 重写 / 追加」 |

---

## 使用方式

- "优化所有skills" → Phase 0-3 完整流程
- "优化 xxx skill" → 单个skill Phase 0.5-2
- "评估所有skills质量" → 只评估不优化（Phase 0.5-1）
- "看看skill优化历史" → 读取并展示 results.tsv
