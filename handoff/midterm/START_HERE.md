# START HERE：中期材料跨会话交接

论文题目逐字保持：**《基于语义表征与思维链推理协同的智能体恶意指令检测方法》**。

这是**已有实验的写作交接包**，不是最终中期报告、PPT或讲稿。实验已暂停；接手会话的任务是依据用户上传的正式模板组织材料，不能自动继续训练、调用模型、调参、改标签或设计新算法。整理日期：2026-09-24。姓名、学号、学院、专业、导师、学校、规定报告日期均**待用户提供/核实**，不能由账户名或本机用户名推定。

## 版本与先读顺序

- 实验来源提交：`614b4d40102d78d606a0f37bc8b678d7eec67d4e`。本次检查本地及远端一致，没有晚于该提交的新实验结果。
- 交接发布提交：是新增本目录的Git提交，**不是新实验提交**；以用户收到的固定 `/blob/<实际发布SHA>/handoff/midterm/START_HERE.md` 链接中SHA为准。实验数字始终引用上面的来源提交，不混入未来main。
- 阅读顺序：[METHOD.md](METHOD.md) → [RESULTS.md](RESULTS.md) → [CASES_AND_LIMITATIONS.md](CASES_AND_LIMITATIONS.md)，之后读取用户的模板与开题原件。四份正文可独立上传到ChatGPT项目；CSV位于[tables/](tables/)。ZIP只装这四份正文和CSV，原始证据通过下列固定版本链接访问。
- 模板决定格式；正式开题报告决定原计划；实验记录决定完成情况。现有早期方案稿与任务书不是实验事实，不能把预期目标填成已完成。

## 一页总述

研究对象是智能体执行前的**当前候选步骤安全检测**：给定原始用户任务、既往历史、完整候选步骤和工具语义，判断safe/unsafe；输入放不下、信息不足或技术失败时保留abstain（暂缓）。恶意内容出现在历史中、当前动作有风险、攻击在真实环境中成功是三件事。本阶段主要有第一/二者相关的静态检测证据，没有完整Agent闭环攻击成功率证据。

实际实现了原生字段/标签适配、按原任务分组的本地探索性划分、512-token字段优先窗口、普通编码器三种子训练、规则与TF-IDF对照；冻结小模型、提示和门控，比较同一教师的直接判断与四维安全关系核对。小模型高置信样本直接决定，低置信或输入溢出样本交教师复核；复用缓存比较不同送审策略。另有固定64条的输入长度×推理协议对照，以及12条受控执行前接口验证。

最可靠的正结果是：小模型学习链可拟合32条训练诊断样本；字段优先输入相较朴素头截断在seed42源test上改善正确决定（118/141对101/141，固定分类阈值0.5），但不是完整信息保证。新域原0.1直接臂三种子正确236/264、249/264、252/264，优于各自小模型200/264、220/264、225/264；这些收益混合了二分类纠错和输入溢出恢复，不能全归因于推理。接口24/24遵从检测决定，展示了实际连接路径；其中检测正确仅22/24，两个错误allow必须保留。

主要负结果与局限同等重要：新域0.1直接臂危险检出仅26/48、41/48、43/48；第四轮原两臂×三种子无共同合格点。后续新增方案级探索仅关系0.5在源dev158通过原95%召回/5%误报规则，但计入安全暂缓后两个种子受阻5.36%；迁移检出38/48、45/48、45/48均不到95%。64条四组检出均16/17，关系推理的独立稳定增益不足。所有数据已暴露；人工gold未完成；当前步骤与受污染历史/Thought的标签边界有歧义；骨干不是标准RoBERTa，教师也不是独立人工标注员。

尚未完成/不能写成成果：合格关系证据监督或蒸馏优势、稳定跨域安全目标、完整Agent业务闭环、RL、GUI、完整ShieldAgent复现、企业部署及论文/专利成果。前期BindGuard不计入本检测方法成绩；本交接不引用其数字充当对照。

## 来源目录（相对仓库路径与固定证据）

|run-id|用途|原始证据相对本目录|固定入口|
|---|---|---|---|
|`2026-09-24-p0-b234`|第一轮P0与B2/B3/B4负结果；旧投影口径，仅历史|`../../runs/2026-09-24-p0-b234/`|[RUN_STATUS.md](https://github.com/boyang-x/thesis-agent-instruction-detection/blob/614b4d40102d78d606a0f37bc8b678d7eec67d4e/runs/2026-09-24-p0-b234/RUN_STATUS.md)；[预测](https://github.com/boyang-x/thesis-agent-instruction-detection/blob/614b4d40102d78d606a0f37bc8b678d7eec67d4e/runs/2026-09-24-p0-b234/predictions.jsonl)；[资源](https://github.com/boyang-x/thesis-agent-instruction-detection/blob/614b4d40102d78d606a0f37bc8b678d7eec67d4e/runs/2026-09-24-p0-b234/resource_usage.json)|
|`2026-09-24-round2-native-collaboration`|原生输入/划分修复、规则/TF-IDF/编码器训练；HTTP402原失败|`../../runs/2026-09-24-round2-native-collaboration/`|[RUN_STATUS.md](https://github.com/boyang-x/thesis-agent-instruction-detection/blob/614b4d40102d78d606a0f37bc8b678d7eec67d4e/runs/2026-09-24-round2-native-collaboration/RUN_STATUS.md)；[预测](https://github.com/boyang-x/thesis-agent-instruction-detection/blob/614b4d40102d78d606a0f37bc8b678d7eec67d4e/runs/2026-09-24-round2-native-collaboration/predictions.jsonl)；[资源](https://github.com/boyang-x/thesis-agent-instruction-detection/blob/614b4d40102d78d606a0f37bc8b678d7eec67d4e/runs/2026-09-24-round2-native-collaboration/resource_usage.json)|
|`2026-09-24-round2-http402-resume`|冻结缺失响应补齐；保留原失败与成功响应|`../../runs/2026-09-24-round2-http402-resume/`|[RUN_STATUS.md](https://github.com/boyang-x/thesis-agent-instruction-detection/blob/614b4d40102d78d606a0f37bc8b678d7eec67d4e/runs/2026-09-24-round2-http402-resume/RUN_STATUS.md)；[预测](https://github.com/boyang-x/thesis-agent-instruction-detection/blob/614b4d40102d78d606a0f37bc8b678d7eec67d4e/runs/2026-09-24-round2-http402-resume/predictions.jsonl)；[资源](https://github.com/boyang-x/thesis-agent-instruction-detection/blob/614b4d40102d78d606a0f37bc8b678d7eec67d4e/runs/2026-09-24-round2-http402-resume/resource_usage.json)|
|`2026-09-24-round3-transfer-ablation`|旧缓存消融、新域264与64条直接短输入|`../../runs/2026-09-24-round3-transfer-ablation/`|[RUN_STATUS.md](https://github.com/boyang-x/thesis-agent-instruction-detection/blob/614b4d40102d78d606a0f37bc8b678d7eec67d4e/runs/2026-09-24-round3-transfer-ablation/RUN_STATUS.md)；[预测](https://github.com/boyang-x/thesis-agent-instruction-detection/blob/614b4d40102d78d606a0f37bc8b678d7eec67d4e/runs/2026-09-24-round3-transfer-ablation/predictions.jsonl)；[资源](https://github.com/boyang-x/thesis-agent-instruction-detection/blob/614b4d40102d78d606a0f37bc8b678d7eec67d4e/runs/2026-09-24-round3-transfer-ablation/resource_usage.json)|
|`2026-09-24-round4-safety-completion`|源dev158、64条关系短输入、12条接口|`../../runs/2026-09-24-round4-safety-completion/`|[RUN_STATUS.md](https://github.com/boyang-x/thesis-agent-instruction-detection/blob/614b4d40102d78d606a0f37bc8b678d7eec67d4e/runs/2026-09-24-round4-safety-completion/RUN_STATUS.md)；[预测](https://github.com/boyang-x/thesis-agent-instruction-detection/blob/614b4d40102d78d606a0f37bc8b678d7eec67d4e/runs/2026-09-24-round4-safety-completion/predictions.jsonl)；[资源](https://github.com/boyang-x/thesis-agent-instruction-detection/blob/614b4d40102d78d606a0f37bc8b678d7eec67d4e/runs/2026-09-24-round4-safety-completion/resource_usage.json)|
|`2026-09-24-scheme-selection-closeout`|方案级选点与安全性缓存收尾；11例AI核对|`../../runs/2026-09-24-scheme-selection-closeout/`|[RUN_STATUS.md](https://github.com/boyang-x/thesis-agent-instruction-detection/blob/614b4d40102d78d606a0f37bc8b678d7eec67d4e/runs/2026-09-24-scheme-selection-closeout/RUN_STATUS.md)；[预测](https://github.com/boyang-x/thesis-agent-instruction-detection/blob/614b4d40102d78d606a0f37bc8b678d7eec67d4e/runs/2026-09-24-scheme-selection-closeout/predictions.jsonl)；[资源](https://github.com/boyang-x/thesis-agent-instruction-detection/blob/614b4d40102d78d606a0f37bc8b678d7eec67d4e/runs/2026-09-24-scheme-selection-closeout/resource_usage.json)|

## 本包文件与使用方式

- `START_HERE.md`：范围、版本、总述、缺失资料和唯一入口。
- `METHOD.md`：实际输入/模型/训练/门控/教师/接口流程，代码定位，原计划与完成情况。
- `RESULTS.md`：主表、指标定义、结论—证据—限定条件、所有CSV索引。
- `CASES_AND_LIMITATIONS.md`：8条可独立阅读的既有案例，含任务、参数、分数、送审及最终决定；歧义与失败完整保留。
- `tables/`：UTF-8 CSV供网页端按模板绘图，机器表保留完整精度与来源路径。Markdown仅为四舍五入展示。不同样本集/配置分表，不能拼成更大独立测试集。

所有原始预测/训练日志/提示/代码均已有公开固定路径，**不是只有服务器本地材料**。完整第三方原生轨迹不再分发；案例给足够中文准确转述与原始行索引。ZIP离线可读主文与表格，深入原始记录需访问固定GitHub链接。

给新会话的任务：先读四份Markdown并确认来源提交，再读取用户模板和开题报告；按模板撰写中期报告与PPT。严格区分已运行结果、原设计、暂缓和未完成项，保留全部种子/负结果。引用RESULTS的表号与证据链接，不从历史方案推断已实现。缺少身份、导师、时间安排或正式要求时留占位并询问用户。

待用户补充：正式中期报告模板、PPT模板/页数与时长要求、正式开题报告、学校/学院/专业/姓名/学号/导师及报告日期；需要写个人分工、导师指导或参考文献时提供可核实来源。当前仓库、指定下载目录及已知论文资料目录未找到正式开题原件，本包不伪造其内容。模板和开题原件由用户在新会话上传，不公开到GitHub。
