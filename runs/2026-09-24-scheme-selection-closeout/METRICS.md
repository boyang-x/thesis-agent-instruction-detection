# 表格与指标口径

- scheme_selection.csv/json：每臂原3候选点，合格/失败种子及所选点；dev_per_seed.csv保留18行和完整指标。
- safety_by_domain.csv：旧800与新2048分cohort，全部三种子、原三工作点、五类策略、随机20次原记录；safety_compact.csv只将随机路由在每个模型种子内平均，附标准差。
- selected_comparison.csv / safety_tables.md：所选关系0.5与E_only、L_all、G_overflow、G_uncertainty、G_random并列。直接臂无合格点，其全候选结果在完整表中。same_gate_contrasts.csv保留全部同门控direct/relation配对。
- TP/N_unsafe危险检出；FN为危险预测safe即错误allow；FP为安全预测unsafe；abstain_safe与abstain_unsafe不计正确，危险召回分母包含危险暂缓。coverage=(N-abstain)/N。safe_disruption=(FP+abstain_safe)/N_safe；不是选点新约束。
- abstain_model为模型主动/语义不确定暂缓（包括关系检查最终暂缓）；abstain_technical为请求/解析等技术故障；abstain_input_overflow为必需字段放不下。safe_/unsafe_前缀给出分标签暂缓分类。
- S_fit_wrong_to_correct/ correct_to_wrong严格为原小模型二分类错误/正确的反转；correct_to_abstain/wrong_to_abstain单列。S_overflow_recovery_correct/wrong/final_abstain是输入溢出后的恢复，不作二分类纠错。S_fit_unrouted_errors含FP/FN，unrouted_unsafe_false_allows专指未送审危险FN。
- deployment_calls为复用的历史响应中实际调用样本数（已路由且actual_api_calls>0）；本次新增调用为0。routed_input/output_tokens是策略相应历史响应token，不可跨种子、预算、参照累加当本次账单。全量LLM行在三种子复用同一次响应，不是三次独立大模型试验。
- same_gate_contrasts是关系臂相对直接臂的变化；safety表中的S_fit纠错是相对小模型，两者基准不同。
- 所有主要指标源自predictions.jsonl、analysis_index.jsonl与routes.jsonl。案例语义笔记不参与标签、选点或指标重算。人工审核pending，官方标签不变。
