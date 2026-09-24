# 基于语义表征与思维链推理协同的智能体恶意指令检测方法

本科毕业设计的公开进度与实验审阅仓库。用于把真实实验结果交给GPT Pro检查，并记录后续指导和执行结果。

**审阅入口：[GPT_PRO_REVIEW.md](GPT_PRO_REVIEW.md)**

- [当前进度](CURRENT_STATUS.md)
- [全部实验记录](EXPERIMENTS.md)
- [毕设任务书](Codex_毕设实施与实验任务书.md)
- [GPT Pro反馈与采纳记录](reviews/README.md)
- [每轮结果同步约定](AGENTS.md)

## 第三轮：机制消融与新增领域迁移

[第三轮结果](runs/2026-09-24-round3-transfer-ablation/RUN_STATUS.md)：旧test96缓存消融、banking/travel共264条的冻结三种子迁移、64条同信息对照均完成。新增592次API；新域主门控直接臂正确236/249/252（N=264），实际调用50/73/69次，均优于仅溢出和对应20次随机送审均值。全量关系臂249/264略高于直接247/264，但主门控关系臂三种子均少于直接臂，不能宣称统一关系收益。

**网页端生成报告/PPT请读取[GPT_PRO_HANDOFF.md](runs/2026-09-24-round3-transfer-ablation/GPT_PRO_HANDOFF.md)**，结合完整CSV与8例。按用户最新要求，本地不生成中期报告/PPT；所有人工审阅仍pending。本轮结束。

## 第二轮补跑收尾（历史）

[冻结HTTP402补跑](runs/2026-09-24-round2-http402-resume/RUN_STATUS.md)：只补185个原失败臂，复用71个成功响应；未重训或改数据/提示/门控。新增190次请求，4个原预选案例的真实串联路径已验证。test两臂均正确93/96，关系臂纠正1个错误、引入1个错误，另有1个输出截断技术暂缓。九组同门控没有总正确数增益，完整种子/预算与成本均保留。[中期回填](runs/2026-09-24-round2-http402-resume/midterm_results_insert.md)。本阶段到此结束，不追加新算法轮次。

## 第二轮首次运行（历史）

[原生基线与协同探索](runs/2026-09-24-round2-native-collaboration/RUN_STATUS.md)：数据、窗口修复及三种子基线完成；P2因大模型余额不足部分阻塞。原生test141：规则正确129，编码器三个种子正确118/112/115、均暂缓23。LLM测试集仅2/96个有效配对，不能声称协议或协同优势。[中期回填材料](runs/2026-09-24-round2-native-collaboration/midterm_results_insert.md)包含全部种子、故障边界和未完成项。

## 第一轮已运行结果

[2026-09-24 P0与B2/B3/B4](runs/2026-09-24-p0-b234/RUN_STATUS.md)：规则基线和三种子微调已运行，**尚未建立方法优势**。规则解出全部构造诊断；B4没有在PairAcc上超出B3，且F1低于B2。人工gold审阅未完成，原生长输入存在严重截断。silver、静态分类、未运行与失败记录均保留。

原始数值、配置和可审阅代码见每轮 `runs/<实验标识>/`，最新结论以“当前进度”指向的实验为准。

## 无需模型的数值核查

```bash
python scripts/verify_run.py runs/2026-09-24-p0-b234
python scripts/verify_run.py runs/2026-09-24-round2-native-collaboration
python scripts/verify_run.py runs/2026-09-24-round2-http402-resume
python scripts/verify_run.py runs/2026-09-24-round3-transfer-ablation
```

仅使用Python标准库，从公开逐样本预测重算指标。第一轮核查42组，第二轮核查77组并验证9组同门控及128组同输入。第三轮核查2224条原始预测、1602行表格及792个路由配置，随机送审按领域匹配实际调用数。原生输入通过上游commit、文件及行号定位；第一轮自建诊断输入随包提供。

## 后续同步方式

每轮实验完成后，在此仓库执行：

```bash
python scripts/publish_experiment.py --source <本轮产物目录> --run-id <唯一实验标识> --push
```

脚本导出必要文件、验证数值、更新审阅入口与索引，然后fetch检查远端差异、提交并推送，最后核对远端HEAD。已有暂存改动或远端更新会明确中止，交由执行者处理；不force-push。

这是实验收尾约定和发布工具，不是无人值守实验或后台定时任务。

## 实现与材料边界

继续复用已有 `boyang-x/agent-guardrail-research` 的实现和执行入口；本仓库不重写主入口。每轮仅保存相关算法快照及必要结果，来源见 `publication.json`。

不上传凭据、内部服务器教程、模型权重或整份第三方轨迹。发布时省略的字段记录在各轮 `publication.json`，逐样本预测、标签、分数、分母和时间数值保持原样。工具调用分类不是闭环攻击成功率，未运行项不填数字。

未为第三方数据或模型重新授予许可证；来源与许可待核实项见每轮data manifest。
