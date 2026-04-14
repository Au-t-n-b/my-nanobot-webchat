# 站点交付模块 交付说明

## 模块目标
演示站点交付模块的参考案例。

## 本次样板执行结果
- 策略选择：稳妥推进
- 上传材料：未记录材料
- 交付吞吐：88
- 验收质量：85
- 遗留风险：8
- 综合健康度：88%

## 给业务同事的改造建议
1. 保留 guide/start/choose_strategy/upload_evidence/after_upload/finish 六段流程。
2. 按真实业务替换 Stepper 文案与 Chart 指标，不要改掉节点 id。
3. 让上传材料与策略选择都走会话内 HITL 卡片，不要退回纯文本交互。
4. 每个关键阶段都发 SkillUiDataPatch，让右侧大盘和左侧对话保持同步。
