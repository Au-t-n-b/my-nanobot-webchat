# 智慧工勘模块交付说明

## 交付内容

本次交付包含两部分：

1. `nanobot` 代码分支
2. workspace skills 目录

缺少任何一部分，同事都无法完整运行当前版本的智慧工勘模块。

## 一、代码获取方式

同事需要先拉取你当前提交并推送的代码分支。

建议执行：

```powershell
git clone https://github.com/Au-t-n-b/my-nanobot-webchat.git
cd my-nanobot-webchat
git fetch origin
git checkout codex/作业管理
git pull origin codex/作业管理
```

如果她已经有本地仓库，则执行：

```powershell
git fetch origin
git checkout codex/作业管理
git pull origin codex/作业管理
```

## 二、需要解压的 skill

同事还需要将以下两个目录放到她本机的 workspace skills 下：

1. `smart_survey_workbench`
2. `gongkan_skill`

目标路径为：

```text
C:\Users\<她的用户名>\.nanobot\workspace\skills\
```

解压后的结果必须是：

```text
C:\Users\<她的用户名>\.nanobot\workspace\skills\smart_survey_workbench
C:\Users\<她的用户名>\.nanobot\workspace\skills\gongkan_skill
```

注意：

1. 不要多一层外层目录，例如 `smart_survey_delivery\smart_survey_workbench` 这种嵌套要避免。
2. `gongkan_skill` 必须保留完整 `ProjectData`、`tools`、`zhgk` 目录结构。

## 三、同事侧部署步骤

### 1. 拉取代码

按“代码获取方式”中的命令拉取 `codex/作业管理` 分支。

### 2. 解压 skill 包

将你提供的交付压缩包解压后，把以下目录复制到：

```text
C:\Users\<她的用户名>\.nanobot\workspace\skills\
```

需要复制的目录：

```text
smart_survey_workbench
gongkan_skill
```

### 3. 重启应用

完成代码拉取和 skill 解压后，重启 AGUI / nanobot 服务。

### 4. 进入模块验证

进入“智慧工勘模块”后，预期流程如下：

1. 首次进入模块会打开大盘。
2. 系统会先走 `prepare_step1`。
3. 如果缺少 Step 1 输入件，会触发 HITL 文件上传。
4. Step 1 完成后，大盘会更新 Stepper、黄金指标和产物区。
5. Step 2 缺少 `勘测结果.xlsx` 或现场照片时，会再次触发 HITL 上传。
6. Step 3 完成后，会展示报告类产物。
7. Step 4-A 发送审批后，流程会停在“等待回执”。
8. 用户明确输入“审批通过”后，才继续执行 `approval_pass` 完成闭环。

## 四、真实运行依赖

`gongkan_skill` 运行依赖以下能力：

1. Python 环境可用
2. 依赖包已安装，至少包括：

```text
openpyxl
python-docx
pywin32
Pillow
requests
```

如果同事本机缺少这些依赖，业务脚本执行会失败，即使大盘本身能打开。

## 五、关键目录说明

智慧工勘真实业务目录主要在：

```text
gongkan_skill\ProjectData\Start
gongkan_skill\ProjectData\Input
gongkan_skill\ProjectData\Images
gongkan_skill\ProjectData\RunTime
gongkan_skill\ProjectData\Output
```

其中：

1. `Start` 放底表、模板和人员信息
2. `Input` 放 BOQ、勘测结果、补充材料
3. `Images` 放现场照片
4. `RunTime` 放中间结果和 `progress.json`
5. `Output` 放最终报告与结果表

## 六、建议的最小验证步骤

同事收到交付后，建议按以下顺序验证：

1. 打开智慧工勘模块，确认大盘能正常显示。
2. 验证 Stepper 为四步：
   `场景筛选与底表过滤`、`勘测数据汇总`、`报告生成`、`审批分发`
3. 缺文件时确认会弹出真实上传卡片。
4. 执行到 Step 2 后确认黄金指标和上传区同步变化。
5. 执行到 Step 4-A 后确认流程暂停。
6. 输入“审批通过”后确认流程闭环。

## 七、当前模块特性

当前版本已具备：

1. 独立 `smart_survey_workbench` 模块
2. 独立后端 flow：`smart_survey_workflow`
3. 对真实 `gongkan_skill` 的脚本桥接
4. 大盘 Stepper / 黄金指标 / 产物区联动
5. Step 1 / Step 2 文件门禁与 HITL 上传
6. Step 4-A 审批暂停与 `approval_pass` 恢复

## 八、备注

如果同事只拉代码、不解压 skill：

1. 模块可能无法出现
2. 或只能看到壳子，真实业务脚本无法执行

如果同事只解压 skill、不拉代码：

1. 后端没有 `smart_survey_workflow`
2. 大盘和业务 skill 无法正确联动
