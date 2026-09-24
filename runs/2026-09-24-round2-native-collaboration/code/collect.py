"""Combine measured predictions and derive dev-only calibrated and cached cascades."""
import collections
import json
from pathlib import Path
from common import readl,writel,dump,score
from compute import recompute,state

HERE=Path(__file__).resolve().parent

def collect():
    cfg=json.loads((HERE/'config.json').read_text());selected=json.loads((HERE/'selection.json').read_text())['samples']
    data={r['sample_id']:r for r in readl(HERE/'sample_index.jsonl')}
    rows=[];base={};statuses={}
    files=[(HERE/'R0_predictions.jsonl','R0',None),(HERE/'majority_predictions.jsonl','majority',None)]
    files += [(HERE/f'R1_seed{s}_predictions.jsonl','R1',s) for s in cfg['seeds']]
    files += [(HERE/f'runs/E_field_seed{s}/predictions.jsonl','E_field',s) for s in cfg['seeds']]
    files += [(HERE/'runs/E_head_seed42/predictions.jsonl','E_head',42)]
    for path,model,seed in files:
        raw=readl(path)
        if not raw:continue
        ps=[{**r,'model':model,'seed':seed,'phase':'baseline','variant':'fixed05','score_is_continuous':model not in ('R0','majority')} for r in raw]
        base[model,seed]={r['sample_id']:r for r in ps};rows+=ps
        if model.startswith('E_'):
            status=json.loads((path.parent/'status.json').read_text());statuses[model,seed]=status
            threshold=status['threshold_dev']
        elif model=='R1':
            dev=[r for r in ps if r['split']=='dev' and r['unsafe_score'] is not None]
            threshold=max((score([{**r,'prediction':'unsafe' if r['unsafe_score']>=t else 'safe'} for r in dev])['macro_F1_covered'],-abs(t-.5),t) for t in cfg['threshold_grid'])[2]
        else:continue
        rows += [{**r,'variant':'dev_threshold','threshold':threshold,'prediction':('abstain' if r['unsafe_score'] is None else 'unsafe' if r['unsafe_score']>=threshold else 'safe')} for r in ps]
    llms=[{**r,'model_decision_observed':r.get('error_code') is None} for r in readl(HERE/'llm_predictions.jsonl')];rows+=llms
    byllm={(r['sample_id'],r['model']):r for r in llms}
    for (model,seed),by in base.items():
        if model not in ('E_field','R0'):continue
        rs=[by[sid] for sid in selected['test']]
        rows += [{**r,'phase':'paired_reference'} for r in rs]
        budgets=cfg['gate_budgets'] if model=='E_field' else ['abstain_only']
        arms=('L_direct','L_relation') if model=='E_field' else ('L_relation',)
        for budget in budgets:
            gate=statuses[model,seed]['gate_thresholds_dev'][str(budget)] if model=='E_field' else None
            for arm in arms:
                if any((r['sample_id'],arm) not in byllm for r in rs):continue
                for r in rs:
                    routed=r['prediction']=='abstain' if model=='R0' else r['unsafe_score'] is None or abs(r['unsafe_score']-.5)<=gate
                    l=byllm[r['sample_id'],arm];choice=l if routed else r
                    rows.append({**{k:r[k] for k in ('sample_id','group_id','split','label','seed','input_ref')},
                        'phase':'cached_cascade','model':('R0_to_' if model=='R0' else 'E_to_')+arm,'variant':'fixed05','budget':budget,
                        'gate_threshold':gate,'routed':routed,'baseline_prediction':r['prediction'],'baseline_state':state(r),
                        'routed_teacher_available':l.get('error_code') is None if routed else None,
                        'teacher_error_code':l.get('error_code') if routed else None,
                        'prediction':choice['prediction'],'unsafe_score':None,'score_is_continuous':False,
                        'error_code':choice.get('error_code'),'latency_ms':r.get('latency_ms',0)+(l.get('latency_ms',0) if routed else 0),
                        'latency_semantics':'component sum estimate, NOT measured online router',
                        'input_tokens':l.get('input_tokens',0) if routed else 0,'output_tokens':l.get('output_tokens',0) if routed else 0,
                        'additional_actual_api_calls':0})
    rows+=readl(HERE/'live_router_predictions.jsonl')
    for r in rows:
        assert r['label']==data[r['sample_id']]['label']
    writel(HERE/'predictions.jsonl',rows);dump(HERE/'metrics.json',recompute(rows))
    return rows

if __name__=='__main__':
    ps=collect();print(json.dumps({'predictions':len(ps),'groups':len(recompute(ps)['results'])}))
