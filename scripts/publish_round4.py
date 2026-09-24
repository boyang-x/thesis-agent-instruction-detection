"""Publish only round4 experiment evidence; preserve all previous runs."""
import json
from datetime import datetime,timezone
from publish_experiment import ROOT,safe_copy,dump,lines,scan
from publish_round2 import public_prediction
from verify_round4 import verify
def readl(p):return [json.loads(s) for s in p.read_text(encoding='utf-8').splitlines()]
def export(source,run_id):
    cfg=json.loads((source/'config.json').read_text());assert run_id==cfg['run_id']=='2026-09-24-round4-safety-completion'
    dest=ROOT/'runs'/run_id;dest.mkdir(parents=True,exist_ok=True)
    files=['PLAN.md','RUN_STATUS.md','EXPERIMENT_CONCLUSIONS.md','cases.md','case_index.jsonl','config.json','request_config.json','analysis_index.jsonl','routes.jsonl','safety_tradeoff.csv','missed_unsafe_cases.jsonl','task_group_results.csv','seed_summary.csv','operating_point_selection.json','safety_operating_points.csv','information_selection.json','reasoning_information_2x2.csv','reasoning_contrasts.csv','integration_selection.json','integration_status.json','interface_fault_checks.json','resource_usage.json','run_state.json']
    for name in files:safe_copy(source/name,dest/name)
    for name in ['predictions.jsonl','new_predictions.jsonl','integration_teacher_predictions.jsonl']:
        lines(dest/name,[{**public_prediction(p),'input_ref':'analysis_index.jsonl#'+p['sample_id']} for p in readl(source/name)])
    # Only twelve candidate tool calls are excerpts; full source trajectories stay local.
    safe_copy(source/'integration_results.jsonl',dest/'integration_results.jsonl')
    lines(dest/'api_usage.jsonl',[{**{k:v for k,v in r.items() if k not in ['payload','error_body','error_message']},'finish_reason':r.get('payload',{}).get('choices',[{}])[0].get('finish_reason')} for r in readl(source/'api_calls.jsonl')])
    for name in ['setup.py','requests_run.py','analyze.py','live_score.py','integration.py','finish.py']:safe_copy(source/name,dest/'code'/name)
    safe_copy(source.with_name('thesis_round3_20260924')/'compare.py',dest/'code/compare.py')
    safe_copy(source.parents[1]/'src/proofclarify_research/gate_e2_adapter.py',dest/'code/reused_gate_e2_adapter.py')
    dump(dest/'publication.json',dict(publication_schema='round4',run_id=run_id,parent_commit=cfg['frozen_public_commit'],source_commit='f059223210750857e9fb63f42e260ca45b09a779',exported_at=datetime.now(timezone.utc).isoformat(),native_text='Full native traces and provider bodies retained locally; twelve tool-call excerpts only for interface verification.',scope='Four user-authorized completion experiments, no training/new prompts/new architecture, no report/PPT',preexecution_entry='existing proofclarify_research.gate_e2_adapter.GuardedToolsExecutor; unchanged; recording-only runtime'))
    scan(dest);result=verify(dest);state=json.loads((dest/'run_state.json').read_text());ledger=json.loads((ROOT/'experiments.json').read_text());ledger=[r for r in ledger if r['run_id']!=run_id]+[dict(run_id=run_id,path='runs/'+run_id,state=state,verification=result,exported_at=datetime.now(timezone.utc).isoformat())];dump(ROOT/'experiments.json',ledger)
    (ROOT/'EXPERIMENTS.md').write_text('# 实验记录\n\n| 实验 | 预测记录 | 状态 |\n|---|---:|---|\n'+''.join(f"| [{r['run_id']}]({r['path']}/RUN_STATUS.md) | {r['verification']['prediction_rows']} | {r['state'].get('status','见报告')} |\n" for r in ledger),encoding='utf-8')
    prefix='runs/'+run_id;status=(source/'EXPERIMENT_CONCLUSIONS.md').read_text(encoding='utf-8');links=f'\n\n[安全性—调用量]({prefix}/safety_tradeoff.csv) · [未送审危险样本]({prefix}/missed_unsafe_cases.jsonl) · [工作点选择]({prefix}/operating_point_selection.json) · [源域/迁移工作点]({prefix}/safety_operating_points.csv) · [同信息2×2]({prefix}/reasoning_information_2x2.csv) · [协议与输入配对变化]({prefix}/reasoning_contrasts.csv) · [接口验证]({prefix}/integration_results.jsonl) · [案例]({prefix}/cases.md) · [实际资源]({prefix}/resource_usage.json)\n'
    (ROOT/'CURRENT_STATUS.md').write_text(status+links,encoding='utf-8')
    (ROOT/'GPT_PRO_REVIEW.md').write_text('# GPT Pro审阅入口：第四轮已完成\n\n'+status+links+'''\n请重点审阅：①总体正确率与unsafe召回是否分开；②是否严格使用源域dev158及共同95%召回/5%误报规则，未用迁移域标签选点；③同一64条四臂的输入内容、纠错/改错/暂缓是否可比；④接口遵从决定与检测正确性是否分开，错误allow是否保留；⑤未送审危险样本是否区分历史可见性、编码器高置信错误与教师未检出。三种子、三工作点、负结果和未运行项均保留。所有随机路由重复共用同批任务，不当独立数据。

仅有执行前接口与记录式模拟派发，没有真实业务写入、完整Agent任务闭环或攻击成功率实验。人工审核仍pending，不是gold。本轮四项完成即结束；不自行追加路由调参、证据蒸馏、RL或新算法，也未制作PPT、报告或讲稿。后续由用户与网页端根据这些真实结果决定。
''',encoding='utf-8')
    return dest,result
