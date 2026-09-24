"""Publish the bounded second-round repair without changing either historical run."""
import json
from datetime import datetime,timezone
from pathlib import Path
from publish_experiment import ROOT,TITLE,safe_copy,dump,lines,scan
from publish_round2 import public_prediction
from verify_resume import verify

def readl(p):return [json.loads(s) for s in p.read_text(encoding='utf-8').splitlines()]
FILES=['freeze_manifest.json','checkpoint_freeze.json','freeze_recheck.json','pricing.json','probe_status.json','PLAN.md','RUN_STATUS.md','midterm_summary.md','midterm_results_insert.md','case_index.jsonl','cases.md','metrics.json','abstention_details.json','results.csv','native_baselines.csv','reasoning_collaboration.csv','ablation.csv','resource_usage.json','response_lineage.jsonl','live_router_status.json','run_state.json']

def export(source,run_id):
    assert run_id=='2026-09-24-round2-http402-resume'
    dest=ROOT/'runs'/run_id;dest.mkdir(parents=True,exist_ok=True)
    for name in FILES+['checkpoint_recheck.json','guard_validation.json']:
        if (source/name).exists():safe_copy(source/name,dest/name)
    for name in ('predictions.jsonl','llm_predictions.jsonl','repair_predictions.jsonl','live_router_predictions.jsonl','live_teacher_predictions.jsonl'):
        if (source/name).exists():lines(dest/name,[public_prediction(r) for r in readl(source/name)])
    lines(dest/'error_samples.jsonl',[public_prediction(r) for r in readl(source/'predictions.jsonl') if r['prediction']!=r['label']])
    calls=readl(source/'api_calls.jsonl')
    lines(dest/'api_usage.jsonl',[{**{k:v for k,v in r.items() if k not in ('payload','error_body','error_message')},'finish_reason':(r.get('payload',{}).get('choices') or [{}])[0].get('finish_reason')} for r in calls])
    for name in ('resume.py','live_resume.py','analyze_resume.py','report_resume.py','test_budget_guard.py'):
        safe_copy(source/name,dest/'code'/name)
    parent=ROOT/'runs/2026-09-24-round2-native-collaboration'
    for name in ('sample_index.jsonl','selection.json','config.json','analysis_contract.json','prompts_frozen.json','live_selection.json','data_manifest.json'):
        safe_copy(parent/name,dest/name)
    dump(dest/'publication.json',{'publication_schema':'round2_resume','run_id':run_id,'parent_commit':'732834f3f07e508455a108128231a0aba91a5152','parent_run':'2026-09-24-round2-native-collaboration','exported_at':datetime.now(timezone.utc).isoformat(),'scope':'HTTP402 repair only; immutable input/model/prompt/gates; no retraining','native_raw_payloads':'retained locally, not redistributed','source_commit':'f059223210750857e9fb63f42e260ca45b09a779','source_code':'new bounded resume subdirectory; existing main entry unchanged'})
    scan(dest);result=verify(dest)
    state=json.loads((dest/'run_state.json').read_text(encoding='utf-8'));resource=json.loads((dest/'resource_usage.json').read_text(encoding='utf-8'));m=json.loads((dest/'metrics.json').read_text(encoding='utf-8'))
    ledger=json.loads((ROOT/'experiments.json').read_text(encoding='utf-8'));ledger=[r for r in ledger if r['run_id']!=run_id]+[{'run_id':run_id,'path':'runs/'+run_id,'state':state,'verification':result,'exported_at':datetime.now(timezone.utc).isoformat()}];dump(ROOT/'experiments.json',ledger)
    (ROOT/'EXPERIMENTS.md').write_text('# 实验记录\n\n| 实验 | 预测及衍生记录 | 状态 |\n|---|---:|---|\n'+''.join(f"| [{r['run_id']}]({r['path']}/RUN_STATUS.md) | {r['verification']['prediction_rows']} | {r['state'].get('status','见报告')} |\n" for r in ledger),encoding='utf-8')
    prefix='runs/'+run_id;test=m['paired_protocol_changes']['test']
    text=f'''论文题目：**{TITLE}**。

第二轮补跑 `{run_id}`，冻结父提交 `732834f3f07e508455a108128231a0aba91a5152`。**{state['status']}，本阶段结束，不追加新算法轮次。**

- 185个原HTTP402臂已补跑{state['repaired_arms']}；71个原生成功响应全部复用，包括错误响应，未把正常abstain重新请求。
- 配对dev/test有效数量：{state['valid_pairs']}。全部256个臂的故障、模型abstain、输入溢出保留总分母。
- test关系臂相对直接臂：纠正{test['corrected_errors']}个二分类错误，引入{test['introduced_errors']}个；转换至abstain另列。不能用单一covered指标声称收益。
- 两臂test均正确93/96；关系臂新增一条800-token输出截断技术暂缓，主动语义abstain为0。九组同门控中关系臂正确数6组减少、3组相同，没有关系协议优势证据；协同相对E的主要收益是恢复14条输入溢出中的判断。
- 三种子/三预算的原门控不变，完整纠错、改错、未送审错误与输入溢出恢复判断见表；原生基线未重训。
- 新增{resource['new']['requests']}/200次请求，按高峰价格保守估算{resource['new_estimated_CNY_peak']:.6f}/10元；输入{resource['new']['input_tokens']}、输出{resource['new']['output_tokens']}token，输入缓存命中{resource['new']['cache_hit_input_tokens']}、未命中{resource['new']['cache_miss_input_tokens']}token。实际账单金额未知。
- 原4个预选案例router：{resource['live_router']['status']}。训练GPU时间0，只有短时原检查点推理；人审仍0，P3/RL/GUI/完整ShieldAgent未运行。

[运行报告]({prefix}/RUN_STATUS.md) · [配对与协同表]({prefix}/reasoning_collaboration.csv) · [原生基线]({prefix}/native_baselines.csv) · [原始及衍生预测]({prefix}/predictions.jsonl) · [响应关联]({prefix}/response_lineage.jsonl) · [案例]({prefix}/cases.md) · [中期回填]({prefix}/midterm_results_insert.md) · [成本]({prefix}/resource_usage.json)
'''
    (ROOT/'CURRENT_STATUS.md').write_text('# 当前状态\n\n'+text,encoding='utf-8')
    (ROOT/'GPT_PRO_REVIEW.md').write_text('# GPT Pro审阅入口\n\n'+text+f'''
请审阅冻结补跑的完整证据，不将本阶段解释为新方法开发。检查原71个成功响应是否逐项保留、新185次是否只关联HTTP402、同门控送审ID是否一致，以及模型主动暂缓/技术错误/输入溢出和旧失败成本是否分别报告。核对全部三种子及三个预算，分析收益是二分类纠错还是较长LLM窗口恢复输入溢出。

请求名仍为deepseek-v4-flash，实际返回模型与服务指纹见[资源记录]({prefix}/resource_usage.json)。官方映射旧请求名到V4.1 Flash已单列披露；服务别名不能证明不可变权重。完整原生输入和API返回留在用户本地，公开数据通过来源索引定位。

报告依据是本仓库包含新run-id的发布提交；可在提交历史固定SHA。两个旧运行目录保持不变。本文不是GPT Pro已认可的结论。用户要求本阶段到此结束；此次只做结果审查，不要求也不自动启动下一轮算法。
''',encoding='utf-8')
    return dest,result
