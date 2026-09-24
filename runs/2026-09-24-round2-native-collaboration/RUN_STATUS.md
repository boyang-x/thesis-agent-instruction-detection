# 第二轮运行报告

论文题目：**基于语义表征与思维链推理协同的智能体恶意指令检测方法**。

Run ID：`2026-09-24-round2-native-collaboration`。第一轮负结果原目录保留。

P0/P1 已完成。**P2因原服务余额不足而部分阻塞，未完成有效的测试集协议/协同对照**：开发集只有31/32个完整配对，测试集只有2/96个完整配对；直接臂有效输出4条、关系臂5条，不能据此判定推理差异。P3、RL、GUI、完整 ShieldAgent、闭环攻击实验均未运行，不填成绩。全部指标来自 predictions.jsonl；HTTP402的abstain是系统故障回退，不是模型判断；缓存级联是衍生记录，不是额外 API 实验。

## 数据、学习与输入

官方步骤字段恢复，去掉额外 P1/P2/P3 政策；956 条按 46 个原始任务组划分为 train657/32组、dev158/7组、test141/7组。分组、规范化任务和完整输入无交叉；仍可能存在跨任务通用模板/工具模式，不能将任务组划分视为所有语义近重复已清除。均为 previously_exposed_exploratory，不是官方划分、独立盲测或人工 gold。

32 条拟合检查：训练损失 0.6914 → 0.1901，最终训练正确 32/32，耗时 6.4s。三种子完整训练各8epoch；checkpoint 只看 dev macro-F1。骨干是提示压缩微调过的 LLMLingua-2 multilingual BERT，不冒称标准 RoBERTa。

窗口强制保留任务、完整当前步骤及相关工具语义；train/dev/test 溢出分别 104/27/23，均计 abstain，训练可用553条，dev可用131条，test可用118条。head512 与 field512 训练/评价使用同一可用集；head 对照没有因更少必留字段而额外覆盖溢出项。两者初始化、种子、训练预算相同。测试集历史不完整 80/141；没有宣称所有关键历史均可见。LLM 共同较长输入不构成与小模型同信息预算比较。

## 原生基线：本地 test141，固定0.5

| model | seed | N | TP | FP | TN | FN | abstain | coverage | F1_covered | macro_F1_covered | correct_decisions/N_total |
|---|---|---|---|---|---|---|---|---|---|---|---|
| E_field | 42 | 141 | 34 | 0 | 84 | 0 | 23 | 0.837 | 1.000 | 1.000 | 0.837 |
| E_field | 43 | 141 | 34 | 6 | 78 | 0 | 23 | 0.837 | 0.919 | 0.941 | 0.794 |
| E_field | 44 | 141 | 34 | 3 | 81 | 0 | 23 | 0.837 | 0.958 | 0.970 | 0.816 |
| E_head | 42 | 141 | 29 | 12 | 72 | 5 | 23 | 0.837 | 0.773 | 0.834 | 0.716 |
| R0 | None | 141 | 40 | 0 | 89 | 4 | 8 | 0.943 | 0.952 | 0.965 | 0.915 |
| R1 | 42 | 141 | 30 | 0 | 84 | 4 | 23 | 0.837 | 0.938 | 0.957 | 0.809 |
| R1 | 43 | 141 | 30 | 0 | 84 | 4 | 23 | 0.837 | 0.938 | 0.957 | 0.809 |
| R1 | 44 | 141 | 30 | 0 | 84 | 4 | 23 | 0.837 | 0.938 | 0.957 | 0.809 |
| majority | None | 141 | 0 | 0 | 90 | 51 | 0 | 1.000 | 0.000 | 0.390 | 0.638 |

dev 阈值结果、train/dev/test 全部混淆矩阵、召回/FPR/AP及三种子均值/标准差见 native_baselines.csv 与 metrics.json。AP 仅用于连续分数模型，不将规则/离散 LLM 分数伪装成连续 PR 曲线。所有选择性指标同时保留总分母。

## 同批推理与协同：test96，服务故障诊断表，不能作为方法效果表

| model | seed | budget | N | FN | FP | abstain | coverage | correct_decisions/N_total | routed | corrected_errors | introduced_errors | wrong_to_abstain | correct_to_abstain | unrouted_binary_errors |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| E_to_L_direct | 42 | 0.1 | 96 | 0 | 0 | 18 | 0.812 | 0.812 | 18 | 0 | 0 | 0 | 4 | 0 |
| E_to_L_direct | 42 | 0.25 | 96 | 0 | 0 | 39 | 0.594 | 0.594 | 39 | 0 | 0 | 0 | 25 | 0 |
| E_to_L_direct | 42 | 0.5 | 96 | 0 | 0 | 50 | 0.479 | 0.479 | 50 | 0 | 0 | 0 | 36 | 0 |
| E_to_L_direct | 43 | 0.1 | 96 | 0 | 0 | 20 | 0.792 | 0.792 | 20 | 0 | 0 | 3 | 3 | 0 |
| E_to_L_direct | 43 | 0.25 | 96 | 0 | 0 | 39 | 0.594 | 0.594 | 39 | 0 | 0 | 3 | 22 | 0 |
| E_to_L_direct | 43 | 0.5 | 96 | 0 | 0 | 57 | 0.406 | 0.406 | 57 | 0 | 0 | 3 | 40 | 0 |
| E_to_L_direct | 44 | 0.1 | 96 | 0 | 2 | 23 | 0.760 | 0.740 | 23 | 0 | 0 | 0 | 9 | 2 |
| E_to_L_direct | 44 | 0.25 | 96 | 0 | 0 | 33 | 0.656 | 0.656 | 33 | 0 | 0 | 2 | 17 | 0 |
| E_to_L_direct | 44 | 0.5 | 96 | 0 | 0 | 54 | 0.438 | 0.438 | 54 | 0 | 0 | 2 | 38 | 0 |
| E_to_L_relation | 42 | 0.1 | 96 | 0 | 0 | 18 | 0.812 | 0.812 | 18 | 0 | 0 | 0 | 4 | 0 |
| E_to_L_relation | 42 | 0.25 | 96 | 0 | 0 | 39 | 0.594 | 0.594 | 39 | 0 | 0 | 0 | 25 | 0 |
| E_to_L_relation | 42 | 0.5 | 96 | 0 | 0 | 48 | 0.500 | 0.500 | 50 | 0 | 0 | 0 | 34 | 0 |
| E_to_L_relation | 43 | 0.1 | 96 | 0 | 0 | 20 | 0.792 | 0.792 | 20 | 0 | 0 | 3 | 3 | 0 |
| E_to_L_relation | 43 | 0.25 | 96 | 0 | 0 | 39 | 0.594 | 0.594 | 39 | 0 | 0 | 3 | 22 | 0 |
| E_to_L_relation | 43 | 0.5 | 96 | 0 | 0 | 55 | 0.427 | 0.427 | 57 | 0 | 0 | 3 | 38 | 0 |
| E_to_L_relation | 44 | 0.1 | 96 | 0 | 2 | 23 | 0.760 | 0.740 | 23 | 0 | 0 | 0 | 9 | 2 |
| E_to_L_relation | 44 | 0.25 | 96 | 0 | 0 | 33 | 0.656 | 0.656 | 33 | 0 | 0 | 2 | 17 | 0 |
| E_to_L_relation | 44 | 0.5 | 96 | 0 | 0 | 52 | 0.458 | 0.458 | 54 | 0 | 0 | 2 | 36 | 0 |
| R0_to_L_relation | None | abstain_only | 96 | 4 | 0 | 5 | 0.948 | 0.906 | 5 | 0 | 0 | 0 | 0 | 4 |
| E_field | 42 |  | 96 | 0 | 0 | 14 | 0.854 | 0.854 |  |  |  |  |  |  |
| E_field | 43 |  | 96 | 0 | 3 | 14 | 0.854 | 0.823 |  |  |  |  |  |  |
| E_field | 44 |  | 96 | 0 | 2 | 14 | 0.854 | 0.833 |  |  |  |  |  |  |
| R0 | None |  | 96 | 4 | 0 | 5 | 0.948 | 0.906 |  |  |  |  |  |  |
| L_direct |  |  | 96 | 0 | 0 | 92 | 0.042 | 0.042 |  |  |  |  |  |  |
| L_relation |  |  | 96 | 0 | 0 | 91 | 0.052 | 0.052 |  |  |  |  |  |  |

预算列是 dev10%/25%/50% 目标，实际调用率由 routed/96 得到，溢出也送审。两臂对每个种子/预算的送审 ID 完全相同。纠错=原先二分类错误变正确；改错=原先正确变二分类错误；与 abstain 的转换另列。表中由于HTTP402产生的变好/变差是故障回退效应，**不是纯推理协议效应**。完整协议效果、成功在线串联结果和方法增益留空；此处仅保留实际系统行为计数。routed_teacher_unavailable 见CSV，未把暂停算正确。

L_direct→L_relation 配对变化（开发集与测试集分开）：

```json
{
  "dev": {
    "N": 32,
    "both_arms_valid_N": 31,
    "protocol_effect_complete": false,
    "direct_to_relation_matrix": {
      "correct": {
        "correct": 29,
        "wrong": 0,
        "abstain": 0
      },
      "wrong": {
        "correct": 0,
        "wrong": 2,
        "abstain": 0
      },
      "abstain": {
        "correct": 0,
        "wrong": 0,
        "abstain": 1
      }
    },
    "matrix_note": "includes technical fallbacks; NOT a pure reasoning effect when protocol_effect_complete is false",
    "corrected_errors": 0,
    "introduced_errors": 0,
    "correct_to_abstain": 0,
    "wrong_to_abstain": 0,
    "valid_pairs_corrected_errors": 0,
    "valid_pairs_introduced_errors": 0
  },
  "test": {
    "N": 96,
    "both_arms_valid_N": 2,
    "protocol_effect_complete": false,
    "direct_to_relation_matrix": {
      "correct": {
        "correct": 2,
        "wrong": 0,
        "abstain": 2
      },
      "wrong": {
        "correct": 0,
        "wrong": 0,
        "abstain": 0
      },
      "abstain": {
        "correct": 3,
        "wrong": 0,
        "abstain": 89
      }
    },
    "matrix_note": "includes technical fallbacks; NOT a pure reasoning effect when protocol_effect_complete is false",
    "corrected_errors": 0,
    "introduced_errors": 0,
    "correct_to_abstain": 2,
    "wrong_to_abstain": 0,
    "valid_pairs_corrected_errors": 0,
    "valid_pairs_introduced_errors": 0
  }
}
```

dev 31个有效配对中两臂结果相同：29个正确、2个官方safe被误报，没有纠错或改错，另1个配对因HTTP402缺失；当前未见关系协议减少漏检的证据。提示保持冻结；未用 test 调提示。输出 ID 合法只说明定位存在，维度解释仍未人工审阅。测试集只有2个有效配对，不能估计协议优势。

## 实际路径和成本

真实 router：PATH_ONLY_SERVICE_BLOCKED，4 个样本，0 次新增 API；同一实际 E 前向结果供两个提示臂使用，先计算 E 再门控，需送审的样本因已确认余额不足被熔断并暂缓。**仅验证了E/门控/故障关闭路径，成功大模型串联未验证**。见 live_router_predictions.jsonl；启动开销与 warm 路径分开，不能称正常线上推理延迟。

本轮实际 API 264/300，输入 131401 token、输出 18466 token，网络重试 0，失败 {'HTTP_402': 185}。GPU 占用墙钟约 9.00 分钟，其中训练阶段 6.57 分钟；核函数实际活跃时间未测，不编造 GPU 利用积分。额度/账单金额未获取，币种费用留空。

全部大模型请求（含失败）计入。缓存级联表的 token、组件延迟相加仅是故障期间组件估计，不能估计正常服务费用和延迟。首次容器因 sklearn 缺失退出，补齐固定依赖后完成。原批处理缺少HTTP402全局熔断，造成185次失败请求继续发出；已修复，未隐去该执行器问题。余额恢复前不消耗剩余36次额度。

## 结论边界与下一步

本轮修复了可学习性和判定输入，建立可重复的原生静态基线；**配对协同主实验因服务余额失败未完成**，不得包装为完整主实验。规则总体正确129/141，高于三个编码器的118/112/115；编码器covered指标较高但23条必留字段溢出。seed42 field相对head在同覆盖集正确数118对101，支持本轮输入处理有帮助，单种子不证明一般化优势。12 条重点案例已整理，人工实际审核0条；无需等120条才完成可执行探索。先处理服务可用性，再在新的续跑ID补足冻结样本/提示对照；当前300次上限仍有效，不自行加购或换服务。训练侧关系证据监督及等量一般监督对照均 NOT_RUN，不沿用 u1/o_noise 作为充分关系监督。
