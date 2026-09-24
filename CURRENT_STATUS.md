# 当前状态

论文题目：**基于语义表征与思维链推理协同的智能体恶意指令检测方法**。

最新实验：[2026-09-24-round2-native-collaboration](runs/2026-09-24-round2-native-collaboration/RUN_STATUS.md)。**P0/P1完成，P2因API余额不足部分阻塞；未证明方法优势。**

- 956条、46个任务组；train/dev/test=657/158/141（32/7/7组），均为本地已暴露探索划分。
- 32条训练拟合通过；TF-IDF与编码器三个种子、head512输入消融均完成。
- test141：规则正确129；编码器seed42/43/44正确118/112/115，均abstain23。完整指标含dev校准见表。
- 两种LLM提示有效配对dev31/32、test2/96；无有效完整测试协议/协同结论。真实router仅验证E、门控和余额熔断路径，成功LLM串联未运行。
- 264/300请求，79成功、185个HTTP402失败；131401输入、18466输出token；单卡GPU墙钟保守计数约9.00分钟（含校准分数恢复及router的SSH开销）。
- 12个重点案例待人工审核，已审核0；P3/RL/GUI/完整ShieldAgent未运行。第一轮负结果原样保留。

[原生基线](runs/2026-09-24-round2-native-collaboration/native_baselines.csv) · [推理/协同故障诊断表](runs/2026-09-24-round2-native-collaboration/reasoning_collaboration.csv) · [案例](runs/2026-09-24-round2-native-collaboration/cases.md) · [中期回填材料](runs/2026-09-24-round2-native-collaboration/midterm_results_insert.md) · [原始及衍生预测](runs/2026-09-24-round2-native-collaboration/predictions.jsonl)

公开重算验证：17768条记录、77组指标；9组同门控和128组同输入检查通过。记录数包含阈值变体和缓存级联，不是独立样本数或API次数。
