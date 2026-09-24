# GPT Pro审阅入口

论文题目：**基于语义表征与思维链推理协同的智能体恶意指令检测方法**

最新实验：`2026-09-24-p0-b234`。请以仓库当前提交为审阅依据，先查看以下材料：

1. [当前状态](CURRENT_STATUS.md)和[运行报告](runs/2026-09-24-p0-b234/RUN_STATUS.md)。
2. [消融表](runs/2026-09-24-p0-b234/ablation.csv)、[逐种子结果](runs/2026-09-24-p0-b234/results.csv)、[指标](runs/2026-09-24-p0-b234/metrics.json)。
3. [失败案例](runs/2026-09-24-p0-b234/cases.md)、[原始预测](runs/2026-09-24-p0-b234/predictions.jsonl)及[样本索引](runs/2026-09-24-p0-b234/sample_index.jsonl)。
4. [数据来源与边界](runs/2026-09-24-p0-b234/data_manifest.json)、[训练配置](runs/2026-09-24-p0-b234/training/config.json)、[算法快照](runs/2026-09-24-p0-b234/code)、[资源](runs/2026-09-24-p0-b234/resource_usage.json)。

## 可直接交给GPT Pro的请求

请检查上述实验的代码、原始预测和证据边界，区分已运行结论与设计。核对同数据/初始化/预算、PairAcc与F1是否一致、abstain和截断是否被隐藏、证据损失是否真正回传，以及负结果是否被完整保留。

优先判断当前问题是否仍值得推进：若规则已解决构造样本或B4未超同数据B2/B3，请明确指出，不包装创新或选择最好种子。审查原生数据适配、来源可信度、模板/重复泄漏、silver证据资格及缺少的额外监督对照。

请给出一个最小且可执行的下一轮建议，包括：具体要验证的问题、最少必要的数据/人工审阅、固定条件、强简单对照、评价指标、资源预算、成功与停止标准；如果应暂停，请直接说明。不要改变论文题目，不重写原仓库主入口，暂不安排RL、GUI或完整ShieldAgent复现。

当前人类gold审阅尚未完成；B4只是部分代理审核silver证据训练，静态分类不是闭环攻击成功率。此前P0已查看的样本不可改称盲测。

反馈回传后放到[reviews](reviews/README.md)，再记录采纳决定；这里尚未获得GPT Pro评审，不能假称其已认可。

仓库链接：https://github.com/boyang-x/thesis-agent-instruction-detection
