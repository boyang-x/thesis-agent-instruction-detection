# 当前状态

论文题目：**基于语义表征与思维链推理协同的智能体恶意指令检测方法**。

第二轮补跑 `2026-09-24-round2-http402-resume`，冻结父提交 `732834f3f07e508455a108128231a0aba91a5152`。**COMPLETED_WITH_TECHNICAL_ABSTENTION_STAGE_CLOSED，本阶段结束，不追加新算法轮次。**

- 185个原HTTP402臂已补跑185；71个原生成功响应全部复用，包括错误响应，未把正常abstain重新请求。
- 配对dev/test有效数量：{'dev': 32, 'test': 95}。全部256个臂的故障、模型abstain、输入溢出保留总分母。
- test关系臂相对直接臂：纠正1个二分类错误，引入1个；转换至abstain另列。不能用单一covered指标声称收益。
- 两臂test均正确93/96；关系臂新增一条800-token输出截断技术暂缓，主动语义abstain为0。九组同门控中关系臂正确数6组减少、3组相同，没有关系协议优势证据；协同相对E的主要收益是恢复14条输入溢出中的判断。
- 三种子/三预算的原门控不变，完整纠错、改错、未送审错误与输入溢出恢复判断见表；原生基线未重训。
- 新增190/200次请求，按高峰价格保守估算0.977260/10元；输入356927、输出44529token，输入缓存命中47360、未命中309567token。实际账单金额未知。
- 原4个预选案例router：COMPLETED。训练GPU时间0，只有短时原检查点推理；人审仍0，P3/RL/GUI/完整ShieldAgent未运行。

[运行报告](runs/2026-09-24-round2-http402-resume/RUN_STATUS.md) · [配对与协同表](runs/2026-09-24-round2-http402-resume/reasoning_collaboration.csv) · [原生基线](runs/2026-09-24-round2-http402-resume/native_baselines.csv) · [原始及衍生预测](runs/2026-09-24-round2-http402-resume/predictions.jsonl) · [响应关联](runs/2026-09-24-round2-http402-resume/response_lineage.jsonl) · [案例](runs/2026-09-24-round2-http402-resume/cases.md) · [中期回填](runs/2026-09-24-round2-http402-resume/midterm_results_insert.md) · [成本](runs/2026-09-24-round2-http402-resume/resource_usage.json)
