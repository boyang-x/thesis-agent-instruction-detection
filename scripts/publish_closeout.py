"""Publish only cache-derived closeout evidence with the existing push workflow."""
import json
from datetime import datetime,timezone
from publish_experiment import ROOT,safe_copy,dump,scan
from verify_closeout import verify

def export(source,run_id):
    cfg=json.loads((source/'config.json').read_text(encoding='utf-8'));assert cfg['run_id']==run_id=='2026-09-24-scheme-selection-closeout'
    dest=ROOT/'runs'/run_id;dest.mkdir(parents=True,exist_ok=True)
    files=['PLAN.md','RUN_STATUS.md','EXPERIMENT_CONCLUSIONS.md','METRICS.md','config.json','parent_config.json','original_common_selection.json','predictions.jsonl','analysis_index.jsonl','routes.jsonl','integration_results.jsonl','resource_usage.json','run_state.json','scheme_selection.json','scheme_selection.csv','scheme_selection.md','dev_per_seed.csv','safety_by_domain.csv','safety_compact.csv','selected_comparison.csv','safety_tables.md','same_gate_contrasts.csv','unrouted_unsafe.jsonl','case_review.jsonl','label_ambiguities.jsonl','cases.md']
    for name in files:safe_copy(source/name,dest/name)
    for name in ['analyze.py','compare.py','finish.py']:safe_copy(source/name,dest/'code'/name)
    dump(dest/'publication.json',dict(publication_schema='closeout',run_id=run_id,parent_commit=cfg['frozen_public_commit'],exported_at=datetime.now(timezone.utc).isoformat(),scope='Cache-only per-arm exploratory selection and safety/error closeout; no model calls/training/threshold or prompt changes',original_common_selection='preserved',target_status='already_exposed_exploratory',native_text='Semantic paraphrases and original row indices only; full native case contexts retained locally',omitted=['cases.local.md'],prediction_numeric_fields_unchanged=True))
    scan(dest);result=verify(dest);state=json.loads((dest/'run_state.json').read_text(encoding='utf-8'));ledger=json.loads((ROOT/'experiments.json').read_text(encoding='utf-8'))
    ledger=[r for r in ledger if r['run_id']!=run_id]+[dict(run_id=run_id,path='runs/'+run_id,state=state,verification=result,exported_at=datetime.now(timezone.utc).isoformat())];dump(ROOT/'experiments.json',ledger)
    (ROOT/'EXPERIMENTS.md').write_text('# 实验记录\n\n| 实验 | 预测记录 | 状态 |\n|---|---:|---|\n'+''.join(f"| [{r['run_id']}]({r['path']}/RUN_STATUS.md) | {r['verification']['prediction_rows']} | {r['state'].get('status','见报告')} |\n" for r in ledger),encoding='utf-8')
    prefix='runs/'+run_id;status=(source/'EXPERIMENT_CONCLUSIONS.md').read_text(encoding='utf-8')
    links='\n\n'+ ' · '.join(f'[{label}]({prefix}/{name})' for label,name in [('方案级选点','scheme_selection.md'),('逐种子源dev','dev_per_seed.csv'),('分领域安全对照','safety_tables.md'),('全部三点/种子/策略摘要','safety_compact.csv'),('含20次随机的完整表','safety_by_domain.csv'),('同门控两臂','same_gate_contrasts.csv'),('11例AI核对','cases.md'),('标签歧义单列','label_ambiguities.jsonl'),('原始预测','predictions.jsonl'),('资源','resource_usage.json'),('指标口径','METRICS.md')])+'\n'
    historical='\n\n第四轮原负结果、64条2×2及12条接口结果完整保留：[第四轮历史结论](runs/2026-09-24-round4-safety-completion/EXPERIMENT_CONCLUSIONS.md)；[原共同选点](runs/2026-09-24-round4-safety-completion/operating_point_selection.json)。第三轮及更早负结果见[全部实验记录](EXPERIMENTS.md)。\n'
    (ROOT/'CURRENT_STATUS.md').write_text(status+links+historical,encoding='utf-8')
    (ROOT/'GPT_PRO_REVIEW.md').write_text('# GPT Pro审阅入口：缓存实验收尾已完成\n\n'+status+links+historical+'\n审阅重点：原共同选点负结果与新增方案级探索结论是否区分；安全暂缓是否进入综合代价；新域是否明确已暴露；同门控对照、全部种子/工作点/随机重复是否完整；二分类纠错和溢出恢复是否分开；AI案例复核是否保留标签歧义且未删样本。本次完成即结束，唯一后续问题仅为记录，不授权自动启动新算法或实验。\n',encoding='utf-8')
    return dest,result
