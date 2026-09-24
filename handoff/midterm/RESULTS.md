# RESULTS：主结果、指标与可写结论

论文：**《基于语义表征与思维链推理协同的智能体恶意指令检测方法》**。实验来源提交`614b4d40102d78d606a0f37bc8b678d7eec67d4e`；本次仅摘录、排序和格式化已有结果。没有新增实验、修改预测、重选工作点或调整指标。CSV保留已有精度，Markdown显示四舍五入值；补充的分母/综合受阻仅按已定义公式对既有整数求和。身份/模板参见[START_HERE.md](START_HERE.md)。

## 0. 指标口径和不得混淆的分母

unsafe为危险类、safe为安全类；TP危险判unsafe、FP安全判unsafe、TN安全判safe、FN危险判safe（错误allow）。`A_u/A_s`分别为危险/安全样本暂缓。`N_u=TP+FN+A_u`，`N_s=TN+FP+A_s`，`N=N_u+N_s`。

- 危险检出率=`TP/N_u`；错误放行率=`FN/N_u`，FN与危险abstain不同。abstain不算正确，不能用暂停拦住危险就提高检出数。
- 安全误报率=`FP/N_s`；安全暂缓率=`A_s/N_s`；综合受阻率=`(FP+A_s)/N_s`，两者都妨碍官方安全任务。coverage覆盖率=`(N−A_u−A_s)/N`；正确决定率=`(TP+TN)/N`。
- covered F1/macro-F1只在非暂缓样本上算，是历史辅助指标。危险召回主分母包含暂缓，不能以covered F1=1代替完整安全目标。
- 暂缓分主动语义不确定、技术故障、必留输入溢出；规则还单列未知工具/未决规则。机器表保留分类计数。语义unknown造成的最终暂缓也必须计成本。
- `S_fit`表示小模型必留输入可放入窗口；仅在这里统计真正二分类纠错（小模型错→最终对）和改错（小模型对→最终错），正确/错误转暂缓单列。`S_overflow`是原先无二分类决定的输入溢出；恢复正确/错误/仍暂缓单列，不能计成二分类纠错。
- “实际调用/N”是用既有成功/失败响应回放该策略时的调用样本数，不是本交接新增费用。种子、策略、预算共享教师响应；随机20次取种子内均值（可有小数），不是20倍独立任务。
- 同门控直接/关系的“纠错”以直接臂为参照；协同表S_fit纠错以小模型为参照，两者不同。

权威计算口径：[METRICS.md](https://github.com/boyang-x/thesis-agent-instruction-detection/blob/614b4d40102d78d606a0f37bc8b678d7eec67d4e/runs/2026-09-24-scheme-selection-closeout/METRICS.md)；[statistics_for](https://github.com/boyang-x/thesis-agent-instruction-detection/blob/614b4d40102d78d606a0f37bc8b678d7eec67d4e/runs/2026-09-24-round3-transfer-ablation/code/compare.py)；[metric / select_dev](https://github.com/boyang-x/thesis-agent-instruction-detection/blob/614b4d40102d78d606a0f37bc8b678d7eec67d4e/runs/2026-09-24-scheme-selection-closeout/code/analyze.py)。暂缓处理未为写作而改动。原始预测字段`prediction`为最终有效决定，`raw_decision`可能被关系规则改为暂缓/unsafe。

## 表1：数据范围与训练概况

[data_scope.csv](tables/data_scope.csv)，来源分别为CSV的source_path；源域全test141、LLM子集test96、新域264与固定64嵌套，**不可相加为测试总样本数**。

|cohort|领域|N|危险/安全|任务组|必留溢出|可输入条数|来源run|
|---|---|---|---|---|---|---|---|
|source_train|slack+workspace|657|207/450|32|104|553|2026-09-24-round2-native-collaboration|
|source_dev|slack+workspace|158|46/112|7|27|131|2026-09-24-round2-native-collaboration|
|source_test|slack+workspace|141|51/90|7|23|118|2026-09-24-round2-native-collaboration|
|old_test_800|combined|96|35/61|7|14|82|2026-09-24-scheme-selection-closeout|
|transfer_2048|combined|264|48/216|12|18|246|2026-09-24-scheme-selection-closeout|
|transfer_2048|banking|87|28/59|6|0|87|2026-09-24-scheme-selection-closeout|
|transfer_2048|travel|177|20/157|6|18|159|2026-09-24-scheme-selection-closeout|
|fixed64_new2048|banking32+travel32|64|17/47|12|0|64|2026-09-24-round4-safety-completion|

源域train657中553条实际训练，dev158中131条用于checkpoint/分位数，完整dev158用于后续安全选点。三种子都基于同一划分；训练明细[training.csv](tables/training.csv)，逐种子设置与选中轮见METHOD§3。旧配对dev32是dev158子集，未与后续完整dev合并为190条；固定64是新域264子集，不新增领域。[selection.json](https://github.com/boyang-x/thesis-agent-instruction-detection/blob/614b4d40102d78d606a0f37bc8b678d7eec67d4e/runs/2026-09-24-round2-native-collaboration/selection.json)保留dev32/test96预选ID；[information_selection.json](https://github.com/boyang-x/thesis-agent-instruction-detection/blob/614b4d40102d78d606a0f37bc8b678d7eec67d4e/runs/2026-09-24-round4-safety-completion/information_selection.json)保留64 ID。

## 表2：源域原生基线（test141，不含教师调用）

主表统一fixed05，domain=slack+workspace，N=141，危险51/安全90，cohort=source_test141；run-id=`2026-09-24-round2-native-collaboration`。TF-IDF、编码器全三种子；E_head仅运行42，另外两种子留未运行。规则输入范围不同且可覆盖多数长输入，因此不是严格同信息上限对比。完整CSV同时保留另存的dev_threshold参照，不能择优拼表：[native_baselines.csv](tables/native_baselines.csv)。

|模型|seed|TP/FP/TN/FN|暂缓危险/安全|正确/N|危险检出|FP率|综合受阻|覆盖|
|---|---|---|---|---|---|---|---|---|
|E_field|42|34/0/84/0|17/6|118/141|66.67%|0.00%|6.67%|83.69%|
|E_field|43|34/6/78/0|17/6|112/141|66.67%|6.67%|13.33%|83.69%|
|E_field|44|34/3/81/0|17/6|115/141|66.67%|3.33%|10.00%|83.69%|
|E_head|42|29/12/72/5|17/6|101/141|56.86%|13.33%|20.00%|83.69%|
|R0|None|40/0/89/4|7/1|129/141|78.43%|0.00%|1.11%|94.33%|
|R1|42|30/0/84/4|17/6|114/141|58.82%|0.00%|6.67%|83.69%|
|R1|43|30/0/84/4|17/6|114/141|58.82%|0.00%|6.67%|83.69%|
|R1|44|30/0/84/4|17/6|114/141|58.82%|0.00%|6.67%|83.69%|
|majority|None|0/0/90/51|0/0|90/141|0.00%|0.00%|0.00%|100.00%|

可写：普通编码器学习链通过训练拟合检查；seed42字段优先比头截断正确118对101，二者同有23条必留溢出。**不可写**“小模型安全检出100%”：主三种子TP均34/51，另17条危险溢出暂缓。规则正确129/141高于三种子编码器118/112/115，说明并未证明学习方法全面超越简单规则。[native_baselines.csv](https://github.com/boyang-x/thesis-agent-instruction-detection/blob/614b4d40102d78d606a0f37bc8b678d7eec67d4e/runs/2026-09-24-round2-native-collaboration/native_baselines.csv)；[predictions.jsonl](https://github.com/boyang-x/thesis-agent-instruction-detection/blob/614b4d40102d78d606a0f37bc8b678d7eec67d4e/runs/2026-09-24-round2-native-collaboration/predictions.jsonl)（行键model/seed/split/sample_id）。

第一轮历史负结果独立保留：[pilot_status.csv](tables/pilot_status.csv)保留所有未运行格空白；[pilot_seed_results.csv](tables/pilot_seed_results.csv)保留24条构造评估上的各实际种子。B2/B3/B4平均PairAcc分别0.04167/0.125/0.125，F1分别0.57143/0.35714/0.39048；规则在同24条为1。PairAcc指成对变体同时判断正确的比例，**只属于该构造实验**，不套用原生分类。B4未优于B3的PairAcc且未优于B2的F1，不能声称联合证据训练有优势。第一轮曾删掉Thought并加入额外策略，源原生投影与第二轮不同，956和944等计数不能直接当扩数据效果。证据：[training/config.json](https://github.com/boyang-x/thesis-agent-instruction-detection/blob/614b4d40102d78d606a0f37bc8b678d7eec67d4e/runs/2026-09-24-p0-b234/training/config.json)；[results.csv](https://github.com/boyang-x/thesis-agent-instruction-detection/blob/614b4d40102d78d606a0f37bc8b678d7eec67d4e/runs/2026-09-24-p0-b234/results.csv)；[LABEL_INPUT_AUDIT.md](https://github.com/boyang-x/thesis-agent-instruction-detection/blob/614b4d40102d78d606a0f37bc8b678d7eec67d4e/runs/2026-09-24-round2-native-collaboration/LABEL_INPUT_AUDIT.md)。

## 表3：协同机制消融，旧域800-token

策略名称：E_only=仅小模型；G_overflow=仅输入溢出送教师；G_uncertainty=输入溢出加置信度门控送教师；G_random=同调用量随机送教师；L_all=全量送教师。L_direct/L_relation分别为直接判断/关系核对。R0=规则、R1=TF-IDF逻辑回归；E_field/E_head分别为字段优先/头截断编码器。TP等混淆计数见§0；F1是精确率与召回率的调和平均，macro-F1为两类F1平均。

cohort=`old_test_800`，test96（危险35/安全61），run-id=`2026-09-24-scheme-selection-closeout`，引用冻结第二轮补跑响应。展示原0.1直接臂与小模型/仅溢出/同调用量随机/全量直接教师；名义0.1不是实际调用比例。[cooperation_old800.csv](tables/cooperation_old800.csv)同时保留两臂、三个点、三个种子、slack/workspace分域与随机标准差，非仅本主表。

|领域|seed|策略/臂/点|N(危险/安全)|TP/FP/TN/FN|暂缓危险/安全|检出率|FP率|综合受阻率|覆盖率|调用/N|纠错/改错|溢出恢复对/错|
|---|---|---|---|---|---|---|---|---|---|---|---|---|
|combined|42|E_only/E/—|96(35/61)|25/0/57/0|10/4|71.43%|0.00%|6.56%|85.42%|0/96|0/0|0/0|
|combined|42|G_overflow/L_direct/—|96(35/61)|35/1/60/0|0/0|100.00%|1.64%|1.64%|100.00%|14/96|0/0|13/1|
|combined|42|L_all/L_direct/—|96(35/61)|35/3/58/0|0/0|100.00%|4.92%|4.92%|100.00%|96/96|0/2|13/1|
|combined|42|G_uncertainty/L_direct/0.1|96(35/61)|35/1/60/0|0/0|100.00%|1.64%|1.64%|100.00%|18/96|0/0|13/1|
|combined|42|G_random/L_direct/0.1|96(35/61)|35/1/60/0|0/0|100.00%|1.64%|1.64%|100.00%|18/96|0/0|13/1|
|combined|43|E_only/E/—|96(35/61)|25/3/54/0|10/4|71.43%|4.92%|11.48%|85.42%|0/96|0/0|0/0|
|combined|43|G_overflow/L_direct/—|96(35/61)|35/4/57/0|0/0|100.00%|6.56%|6.56%|100.00%|14/96|0/0|13/1|
|combined|43|L_all/L_direct/—|96(35/61)|35/3/58/0|0/0|100.00%|4.92%|4.92%|100.00%|96/96|3/2|13/1|
|combined|43|G_uncertainty/L_direct/0.1|96(35/61)|35/1/60/0|0/0|100.00%|1.64%|1.64%|100.00%|20/96|3/0|13/1|
|combined|43|G_random/L_direct/0.1|96(35/61)|35/3.80/57.20/0|0/0|100.00%|6.23%|6.23%|100.00%|20/96|0.30/0.10|13/1|
|combined|44|E_only/E/—|96(35/61)|25/2/55/0|10/4|71.43%|3.28%|9.84%|85.42%|0/96|0/0|0/0|
|combined|44|G_overflow/L_direct/—|96(35/61)|35/3/58/0|0/0|100.00%|4.92%|4.92%|100.00%|14/96|0/0|13/1|
|combined|44|L_all/L_direct/—|96(35/61)|35/3/58/0|0/0|100.00%|4.92%|4.92%|100.00%|96/96|2/2|13/1|
|combined|44|G_uncertainty/L_direct/0.1|96(35/61)|35/4/57/0|0/0|100.00%|6.56%|6.56%|100.00%|23/96|0/1|13/1|
|combined|44|G_random/L_direct/0.1|96(35/61)|35/3.05/57.95/0|0/0|100.00%|5.00%|5.00%|100.00%|23/96|0.10/0.15|13/1|

旧关系全量及多个送审策略留有1条800-token技术输出失败暂缓，故与直接臂正确数同为93/96也不代表相同FP/覆盖。原响应与错误没有为了提高分数重跑。三种子全量教师标签相同，但纠错列相对不同小模型，故重复列出并不表示教师独立运行了三次。

## 表4：协同机制消融，新域2048-token

cohort=`transfer_2048`，N=264（危险48/安全216），run-id=`2026-09-24-scheme-selection-closeout`；新域教师来自第三轮，冻结检查点/输入/门控。原0.1主点在看新域结果前确定；本次整理已暴露数据不称盲测。

|领域|seed|策略/臂/点|N(危险/安全)|TP/FP/TN/FN|暂缓危险/安全|检出率|FP率|综合受阻率|覆盖率|调用/N|纠错/改错|溢出恢复对/错|
|---|---|---|---|---|---|---|---|---|---|---|---|---|
|combined|42|E_only/E/—|264(48/216)|7/13/193/33|8/10|14.58%|6.02%|10.65%|93.18%|0/264|0/0|0/0|
|combined|42|G_overflow/L_direct/—|264(48/216)|15/15/201/33|0/0|31.25%|6.94%|6.94%|100.00%|18/264|0/0|16/2|
|combined|42|L_all/L_direct/—|264(48/216)|45/14/202/3|0/0|93.75%|6.48%|6.48%|100.00%|264/264|40/9|16/2|
|combined|42|G_uncertainty/L_direct/0.1|264(48/216)|26/6/210/22|0/0|54.17%|2.78%|2.78%|100.00%|50/264|21/1|16/2|
|combined|42|G_random/L_direct/0.1|264(48/216)|21.60/12.75/203.25/26.40|0/0|45.00%|5.90%|5.90%|100.00%|50/264|10.40/1.55|16/2|
|combined|43|E_only/E/—|264(48/216)|22/8/198/18|8/10|45.83%|3.70%|8.33%|93.18%|0/264|0/0|0/0|
|combined|43|G_overflow/L_direct/—|264(48/216)|30/10/206/18|0/0|62.50%|4.63%|4.63%|100.00%|18/264|0/0|16/2|
|combined|43|L_all/L_direct/—|264(48/216)|45/14/202/3|0/0|93.75%|6.48%|6.48%|100.00%|264/264|20/9|16/2|
|combined|43|G_uncertainty/L_direct/0.1|264(48/216)|41/8/208/7|0/0|85.42%|3.70%|3.70%|100.00%|73/264|16/3|16/2|
|combined|43|G_random/L_direct/0.1|264(48/216)|33.80/9.75/206.25/14.20|0/0|70.42%|4.51%|4.51%|100.00%|73/264|6.30/2.25|16/2|
|combined|44|E_only/E/—|264(48/216)|22/3/203/18|8/10|45.83%|1.39%|6.02%|93.18%|0/264|0/0|0/0|
|combined|44|G_overflow/L_direct/—|264(48/216)|30/5/211/18|0/0|62.50%|2.31%|2.31%|100.00%|18/264|0/0|16/2|
|combined|44|L_all/L_direct/—|264(48/216)|45/14/202/3|0/0|93.75%|6.48%|6.48%|100.00%|264/264|16/10|16/2|
|combined|44|G_uncertainty/L_direct/0.1|264(48/216)|43/7/209/5|0/0|89.58%|3.24%|3.24%|100.00%|69/264|14/3|16/2|
|combined|44|G_random/L_direct/0.1|264(48/216)|33.80/6.80/209.20/14.20|0/0|70.42%|3.15%|3.15%|100.00%|69/264|4.40/2.40|16/2|

新增领域中，0.1直接臂三种子正确236/249/252（N264），超过各自E_only与G_overflow；但危险检出26/41/43（分母48），seed42有22条危险错误未送审。必须同时报告总体正确与安全检出。随机对照均值来自原20次，不挑最好抽样；逐重复明细仍在[safety_by_domain.csv](https://github.com/boyang-x/thesis-agent-instruction-detection/blob/614b4d40102d78d606a0f37bc8b678d7eec67d4e/runs/2026-09-24-scheme-selection-closeout/safety_by_domain.csv)，主表未把重复扩成样本。

## 表5：同门控直接/关系对照，所有原工作点

[same_gate_contrasts.csv](tables/same_gate_contrasts.csv)有cohort、domain、seed、gate、budget、N及两臂变化计数；以下只折叠展示combined，两域分表标识，仍保留每个seed/点。正向“纠正/引错”是关系相对直接最终决定，并非相对小模型。分开列S_fit变化，避免溢出混入二分类改进；相应TP/FP/TN/FN、调用和覆盖在表3/4的完整CSV按同键连接。

|cohort|seed|点|N|纠正/引错|正确→暂缓|错误→暂缓|暂缓→正确|TP差|FP差|S_fit纠正/引错|
|---|---|---|---|---|---|---|---|---|---|---|
|old_test_800|42|0.1|96|0/1|0|1|0|0|0|0/0|
|old_test_800|42|0.25|96|0/1|0|1|0|0|0|0/0|
|old_test_800|42|0.5|96|0/1|0|1|0|0|0|0/0|
|old_test_800|43|0.1|96|0/1|0|1|0|0|0|0/0|
|old_test_800|43|0.25|96|0/1|0|1|0|0|0|0/0|
|old_test_800|43|0.5|96|1/1|0|1|0|0|-1|1/0|
|old_test_800|44|0.1|96|0/1|0|1|0|0|0|0/0|
|old_test_800|44|0.25|96|1/1|0|1|0|0|-1|1/0|
|old_test_800|44|0.5|96|1/1|0|1|0|0|-1|1/0|
|transfer_2048|42|0.1|264|1/2|1|1|0|0|0|0/0|
|transfer_2048|42|0.25|264|1/2|1|1|0|0|0|0/0|
|transfer_2048|42|0.5|264|2/2|1|1|0|0|-1|1/0|
|transfer_2048|43|0.1|264|1/2|1|1|0|0|0|0/0|
|transfer_2048|43|0.25|264|1/2|1|1|0|0|0|0/0|
|transfer_2048|43|0.5|264|5/2|1|1|0|0|-4|4/0|
|transfer_2048|44|0.1|264|2/2|1|1|0|0|-1|1/0|
|transfer_2048|44|0.25|264|2/2|1|1|0|0|-1|1/0|
|transfer_2048|44|0.5|264|4/2|1|1|0|0|-3|3/0|

不能用各臂各自选中的点比较取代本表。本数据上关系臂未带来同门控危险检出数提升；减少部分FP的同时可能增加安全暂缓、损失溢出恢复正确。方法优势没有统一成立。

## 表6：共同选点负结果与新增方案级选点

源域cohort=`dev_2048`，2048-token完整dev158、危险46/安全112；本次展示来源run-id=`2026-09-24-scheme-selection-closeout`。原第四轮同时要求两臂×三种子均危险召回≥95%、安全FP率≤5%，无共同合格点。原[operating_point_selection.json](https://github.com/boyang-x/thesis-agent-instruction-detection/blob/614b4d40102d78d606a0f37bc8b678d7eec67d4e/runs/2026-09-24-round4-safety-completion/operating_point_selection.json)及其“所选共同点迁移NOT_RUN”保留。新增方案级分析是后来另行授权的探索：每臂分别全三种子满足同两项，合格时取平均实际调用率最低的原点，没放宽目标/新增阈值，也没用目标域标签选点。

[dev_per_seed.csv](tables/dev_per_seed.csv)保存18行全指标；[scheme_selection.csv](tables/scheme_selection.csv)保存六个方案×点及失败约束。

|臂|点|seed|TP/46|FP/112|安全暂缓|coverage|综合受阻率|调用/158|单seed达标|
|---|---|---|---|---|---|---|---|---|---|
|L_direct|0.1|42|43/46|4/112|0|100.00%|3.57%|40/158|False|
|L_direct|0.25|42|44/46|4/112|0|100.00%|3.57%|60/158|True|
|L_direct|0.5|42|46/46|7/112|0|100.00%|6.25%|93/158|False|
|L_relation|0.1|42|43/46|3/112|0|100.00%|2.68%|40/158|False|
|L_relation|0.25|42|44/46|3/112|0|100.00%|2.68%|60/158|True|
|L_relation|0.5|42|46/46|5/112|1|99.37%|5.36%|93/158|True|
|L_direct|0.1|43|43/46|4/112|0|100.00%|3.57%|41/158|False|
|L_direct|0.25|43|43/46|4/112|0|100.00%|3.57%|60/158|False|
|L_direct|0.5|43|46/46|6/112|0|100.00%|5.36%|93/158|False|
|L_relation|0.1|43|43/46|3/112|0|100.00%|2.68%|41/158|False|
|L_relation|0.25|43|43/46|3/112|0|100.00%|2.68%|60/158|False|
|L_relation|0.5|43|46/46|5/112|0|100.00%|4.46%|93/158|True|
|L_direct|0.1|44|42/46|4/112|0|100.00%|3.57%|40/158|False|
|L_direct|0.25|44|44/46|6/112|0|100.00%|5.36%|60/158|False|
|L_direct|0.5|44|45/46|7/112|0|100.00%|6.25%|93/158|False|
|L_relation|0.1|44|42/46|4/112|0|100.00%|3.57%|40/158|False|
|L_relation|0.25|44|44/46|4/112|1|99.37%|4.46%|60/158|True|
|L_relation|0.5|44|45/46|5/112|1|99.37%|5.36%|93/158|True|

结论：L_direct无合格点；L_relation仅0.5合格（调用均93/158=58.86%），TP46/46、46/46、45/46；FP均5/112。安全暂缓1/0/1导致综合受阻6/112、5/112、6/112（5.36%、4.46%、5.36%），**不是综合受阻也达5%目标**。筛选目标没有把暂缓加入FP约束；这里披露代价而不是偷偷更换筛选准则。小dev经验达标不提供统计安全保证。

## 表7：方案级关系0.5在新域的分领域结果

直接臂没有可报告的“所选合格点迁移”，不临时挑一个最好种子。下表保持全部三个种子，来自[cooperation_new2048.csv](tables/cooperation_new2048.csv)，键arm=L_relation、gate=G_uncertainty、budget=0.5。新域已经看过，属于**已暴露探索性分析**，不是独立确认。直接臂同0.5仍在同门控表中作为参照，而非合格配置。

|领域|seed|策略/臂/点|N(危险/安全)|TP/FP/TN/FN|暂缓危险/安全|检出率|FP率|综合受阻率|覆盖率|调用/N|纠错/改错|溢出恢复对/错|
|---|---|---|---|---|---|---|---|---|---|---|---|---|
|combined|42|G_uncertainty/L_relation/0.5|264(48/216)|38/9/205/10|0/2|79.17%|4.17%|5.09%|99.24%|80/264|32/3|15/3|
|banking|42|G_uncertainty/L_relation/0.5|87(28/59)|25/6/51/3|0/2|89.29%|10.17%|13.56%|97.70%|51/87|27/3|0/0|
|travel|42|G_uncertainty/L_relation/0.5|177(20/157)|13/3/154/7|0/0|65.00%|1.91%|1.91%|100.00%|29/177|5/0|15/3|
|combined|43|G_uncertainty/L_relation/0.5|264(48/216)|45/10/204/3|0/2|93.75%|4.63%|5.56%|99.24%|175/264|20/5|15/3|
|banking|43|G_uncertainty/L_relation/0.5|87(28/59)|25/6/51/3|0/2|89.29%|10.17%|13.56%|97.70%|52/87|11/4|0/0|
|travel|43|G_uncertainty/L_relation/0.5|177(20/157)|20/4/153/0|0/0|100.00%|2.55%|2.55%|100.00%|123/177|9/1|15/3|
|combined|44|G_uncertainty/L_relation/0.5|264(48/216)|45/10/204/3|0/2|93.75%|4.63%|5.56%|99.24%|131/264|16/5|15/3|
|banking|44|G_uncertainty/L_relation/0.5|87(28/59)|25/6/51/3|0/2|89.29%|10.17%|13.56%|97.70%|52/87|8/4|0/0|
|travel|44|G_uncertainty/L_relation/0.5|177(20/157)|20/4/153/0|0/0|100.00%|2.55%|2.55%|100.00%|79/177|8/1|15/3|

新域总危险检出38/48、45/48、45/48均低于95%；banking为25/28且FP6/59、安全暂缓2/59，三个种子综合受阻8/59=13.56%。travel为13/20、20/20、20/20，说明领域及种子差异不能由总体均值隐藏。seed42仍7条危险样本未送审，两个教师缓存均能检出；seed43/44未送审危险FN为0却仍有3个教师共同漏检。具体ID：[unrouted_unsafe.jsonl](https://github.com/boyang-x/thesis-agent-instruction-detection/blob/614b4d40102d78d606a0f37bc8b678d7eec67d4e/runs/2026-09-24-scheme-selection-closeout/unrouted_unsafe.jsonl)（seed42/budget0.5/transfer_2048）；不是新运行的案例实验。

旧域关系0.5对应三种子TP35/35、FP2/61、安全技术暂缓1/61，调用50/57/54（N96），见cooperation_old800.csv同键。源dev、旧test与新域结果分开，不能用旧域成功代表迁移达标。

## 表8：固定64条的短/长输入×直接/关系协议

run-id=`2026-09-24-round4-safety-completion`，cohort=`fixed64_new2048`，同64 ID（危险17/安全47，banking32/travel32），四臂统一2048-token上限。短输入与小模型相同；长输入共享相同更长上下文。教师不是三种子独立训练，故seed不适用，不能复制成三次独立验证。[reasoning_information_2x2.csv](tables/reasoning_information_2x2.csv)保留combined/banking/travel。

|输入/协议|N|TP/FP/TN/FN|暂缓危险/安全|正确/N|危险检出|覆盖|调用|
|---|---|---|---|---|---|---|---|
|short/direct|64|16/7/40/1|0/0|56/64|94.12%|100.00%|64|
|short/relation|64|16/5/39/0|1/3|55/64|94.12%|93.75%|64|
|long/direct|64|16/5/42/1|0/0|58/64|94.12%|100.00%|64|
|long/relation|64|16/3/43/1|0/1|59/64|94.12%|98.44%|64|

短relation相对短direct没有二分类纠错，1个正确及3个错误转暂缓；危险检出同16/17，FN从1变0但该危险样本改为暂缓，不是召回提升。长relation相对长direct纠正2、引错0、正确转暂缓1。长输入增加正确数不等于纯推理能力提升；64条有选择范围限制。逐例配对变化来源[reasoning_contrasts.csv](https://github.com/boyang-x/thesis-agent-instruction-detection/blob/614b4d40102d78d606a0f37bc8b678d7eec67d4e/runs/2026-09-24-round4-safety-completion/reasoning_contrasts.csv)；四组主表safe综合受阻分别7/47、8/47、5/47、4/47，safe暂缓已计入。

## 表9：既有受控接口和资源

run-id=`2026-09-24-round4-safety-completion`，cohort=`controlled_interface12`，seed42/budget0.1，四路各3个预选案例，12唯一样本×两臂=24记录。接口遵从24/24；检测正确22/24；危险错误allow2条记录（同一banking_0002两臂），不是2个不同样本。9次实际编码器前向、3条溢出，12次实际教师调用。下游仅记录式替身。全部24记录导出[interface_cases.csv](tables/interface_cases.csv)，包含官方标签、分数、送审、检测决定、派发决定和正确性。

|统计|数量|来源|
|---|---:|---|
|预选唯一案例|12|integration_selection.json|
|两臂接口遵从决定|24/24|integration_results.jsonl: interface_compliant|
|两臂检测正确|22/24|integration_results.jsonl: detection_correct|
|危险错误allow记录|2/24|unsafe_allowed；同一sample_id|
|额外合约检查|2/2|interface_fault_checks.json：policy异常BLOCK、语义暂缓ASK，均无派发|

这些检查不是完整Agent攻击成功率，不混入静态主表。已有第二轮4例串联补跑另见[live_router记录](https://github.com/boyang-x/thesis-agent-instruction-detection/blob/614b4d40102d78d606a0f37bc8b678d7eec67d4e/runs/2026-09-24-round2-http402-resume/resource_usage.json)，不能与第四轮12例拼成独立任务成功率。第四轮直接来源：[integration_results.jsonl](https://github.com/boyang-x/thesis-agent-instruction-detection/blob/614b4d40102d78d606a0f37bc8b678d7eec67d4e/runs/2026-09-24-round4-safety-completion/integration_results.jsonl)；[integration_status.json](https://github.com/boyang-x/thesis-agent-instruction-detection/blob/614b4d40102d78d606a0f37bc8b678d7eec67d4e/runs/2026-09-24-round4-safety-completion/integration_status.json)；[interface_fault_checks.json](https://github.com/boyang-x/thesis-agent-instruction-detection/blob/614b4d40102d78d606a0f37bc8b678d7eec67d4e/runs/2026-09-24-round4-safety-completion/interface_fault_checks.json)。

[resources.csv](tables/resources.csv)逐阶段只计新增真实请求，未知账单金额空白；GPU时间语义不同，不能直接称GPU算力活跃总时长。

|run-id|新增请求|输入token|输出token|缓存命中token|GPU记录秒|实付人民币|
|---|---|---|---|---|---|---|
|2026-09-24-p0-b234|137|74774|26062|未知|87.21|未知|
|2026-09-24-round2-native-collaboration|264|131401|18466|15488|539.71|未知|
|2026-09-24-round2-http402-resume|190|356927|44529|47360|29.83|未知|
|2026-09-24-round3-transfer-ablation|592|1011372|126999|145408|15.94|未知|
|2026-09-24-round4-safety-completion|392|737960|102915|193916|42.40|未知|
|2026-09-24-scheme-selection-closeout|0|0|0|0|0|0|

本交接整理也无新增API/训练/GPU。第二轮264含185次HTTP402失败；补跑只计新增190，不能再加combined_actual454。补跑0.97726/0.48863元是历史按峰/谷单价估算，**不是实际账单**，不填实付列；本次不重新查价、不据token编造费用。第四轮GPU42.40秒为worker驻留含等候API。详细时间、请求名、响应名、指纹在各run的resource_usage.json及api_usage.jsonl；教师重复使用不再次收费。

## 结论—证据—限定条件

|可写表述|具体证据与定位|必要限定|
|---|---|---|
|训练实现能拟合小诊断集|[training/debug_fit32/status.json](https://github.com/boyang-x/thesis-agent-instruction-detection/blob/614b4d40102d78d606a0f37bc8b678d7eec67d4e/runs/2026-09-24-round2-native-collaboration/training/debug_fit32/status.json)，train_final=32/32|训练拟合，不是测试准确率|
|字段优先优于本次头截断对照|表2；[native_baselines.csv](https://github.com/boyang-x/thesis-agent-instruction-detection/blob/614b4d40102d78d606a0f37bc8b678d7eec67d4e/runs/2026-09-24-round2-native-collaboration/native_baselines.csv)，test/seed42/fixed05 E_field与E_head|同23条溢出；E_head仅42，不能泛化成三种子结论|
|原0.1协同在新域提高正确决定|表4；[safety_compact.csv](https://github.com/boyang-x/thesis-agent-instruction-detection/blob/614b4d40102d78d606a0f37bc8b678d7eec67d4e/runs/2026-09-24-scheme-selection-closeout/safety_compact.csv)，transfer_2048/combined/各seed/L_direct/0.1|仍有危险漏检；收益分二分类纠错与溢出恢复；不是CoT单独贡献|
|原共同安全选点无合格点|[operating_point_selection.json](https://github.com/boyang-x/thesis-agent-instruction-detection/blob/614b4d40102d78d606a0f37bc8b678d7eec67d4e/runs/2026-09-24-round4-safety-completion/operating_point_selection.json)，selected_budget=null|两臂×三种子共同规则，原负结果保留|
|关系0.5方案级源dev合格|表6；[scheme_selection.json](https://github.com/boyang-x/thesis-agent-instruction-detection/blob/614b4d40102d78d606a0f37bc8b678d7eec67d4e/runs/2026-09-24-scheme-selection-closeout/scheme_selection.json)，selected_budget_by_arm|新增探索，不替换原规则；综合受阻可能>5%|
|源dev安全目标未稳定迁移|表7；[safety_compact.csv](https://github.com/boyang-x/thesis-agent-instruction-detection/blob/614b4d40102d78d606a0f37bc8b678d7eec67d4e/runs/2026-09-24-scheme-selection-closeout/safety_compact.csv)，transfer_2048/L_relation/0.5|新域已暴露；全部三种子；无独立确认或置信保证|
|高置信漏送审与教师错误并存|[unrouted_unsafe.jsonl](https://github.com/boyang-x/thesis-agent-instruction-detection/blob/614b4d40102d78d606a0f37bc8b678d7eec67d4e/runs/2026-09-24-scheme-selection-closeout/unrouted_unsafe.jsonl)，seed42/0.5七条；[case_review.jsonl](https://github.com/boyang-x/thesis-agent-instruction-detection/blob/614b4d40102d78d606a0f37bc8b678d7eec67d4e/runs/2026-09-24-scheme-selection-closeout/case_review.jsonl)，banking_0014|AI案例复核非gold，标签边界未解决|
|关系协议独立稳定收益不足|表5/8；[reasoning_contrasts.csv](https://github.com/boyang-x/thesis-agent-instruction-detection/blob/614b4d40102d78d606a0f37bc8b678d7eec67d4e/runs/2026-09-24-round4-safety-completion/reasoning_contrasts.csv)|同模型、同门控/输入；不能将长上下文归为纯推理|
|执行前接口连接已验证|表9；[integration_results.jsonl](https://github.com/boyang-x/thesis-agent-instruction-detection/blob/614b4d40102d78d606a0f37bc8b678d7eec67d4e/runs/2026-09-24-round4-safety-completion/integration_results.jsonl)，24记录|记录替身、22/24检测正确、错误allow保留；非业务闭环|

不支持或未验证：超过ShieldAgent/他人公开分数；通用或校准安全保证；CoT原创或统一优势；完整证据蒸馏已成功；人工gold已完成；真实业务攻击成功率下降；个人独立贡献/企业应用/论文专利。不能从本交接推出这些结论。

## 表格索引与冲突处理

CSV的source_path/run_id是原证据定位，experiment_source_commit在直接摘录表中给固定提交。附加数据/训练/资源表均据同一截止版本，未包含新实验。主表可用相同CSV重新作图，不新增视觉素材。各表的run_id长名称对应START_HERE的来源目录，不是多个独立数据集。

|CSV|用途/行键|主要证据|
|---|---|---|
|data_scope.csv|cohort/domain；数据分母与溢出|R2/R3 data_manifest、RC analysis_index、R4固定64|
|training.csv|model/seed|R2训练status/config|
|native_baselines.csv|model/seed/variant/test|R2 native_baselines，含fixed05与dev_threshold|
|pilot_status.csv / pilot_seed_results.csv|model/seed/cohort|R1原始消融与逐种子成绩，未运行空白|
|cooperation_old800.csv|cohort/domain/seed/arm/gate/budget|RC safety_compact旧域全点|
|cooperation_new2048.csv|同上|RC safety_compact新域全点|
|same_gate_contrasts.csv|cohort/domain/seed/budget|RC同门控两臂变化，保留全三点|
|dev_per_seed.csv / scheme_selection.csv|arm/budget/seed|RC dev选点及规则；原共同点仍在R4|
|reasoning_information_2x2.csv|domain/input_length/protocol|R4四组64条|
|interface_cases.csv|sample_id/arm|R4原24条接口日志|
|resources.csv|run_id|各轮真实resource_usage，不累计复用响应|

常见表面冲突已明确：141与96是全集/子集；原共同无点与关系单臂有点是两种选择规则；旧P3未运行/服务阻塞与后续接口成功属于不同阶段；F1_covered完美不代表全分母危险召回完美；旧800与新2048不是同配置。不得自行选漂亮数字抹掉这些差异。本次未发现需要更改原预测或指标的数值冲突；若后续模板中的历史总结与表格不一致，先列冲突并核对行键，禁止重算“清洗后更高分”。
