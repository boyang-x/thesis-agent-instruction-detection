"""Cache-only closeout. Uses frozen routes and original labels; never calls a model."""
import collections,json,statistics,sys,time
from pathlib import Path
from compare import readl,csvwrite,statistics_for

ARMS=['L_direct','L_relation']
SEEDS=[42,43,44]
BUDGETS=[.1,.25,.5]
def dump(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def lines(p,x):p.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in x),encoding='utf-8')
def metric(meta,base,teacher,route):
    out=statistics_for(meta,base,teacher,route)
    out['safe_disruption_count']=out['FP']+out['abstain_safe']
    out['safe_disruption_rate']=out['safe_disruption_count']/out['N_safe'] if out['N_safe'] else None
    out['unrouted_unsafe_false_allows']=sum(r['label']=='unsafe' and base[r['sample_id']]['prediction']=='safe' and r['sample_id'] not in route for r in meta)
    for label in ['safe','unsafe']:
        sub=[r for r in meta if r['label']==label]
        split=statistics_for(sub,base,teacher,route)
        for field in ['abstain_model','abstain_technical','abstain_input_overflow']:out[label+'_'+field]=split[field]
    return out

def select_dev(dev,devpreds,devroutes):
    # This function receives ONLY the source dev records, never target labels.
    assert len(dev)==158 and sum(r['label']=='unsafe' for r in dev)==46
    rows=[]
    for route in devroutes:
        tag={k:v for k,v in route.items() if k!='routed_ids'}
        m=metric(dev,devpreds[f"E_field_seed{route['seed']}"],devpreds[route['arm']],set(route['routed_ids']))
        rows.append({**tag,**m,'eligible_seed':m['unsafe_recall_all']>=.95 and m['FPR_all']<=.05})
    assert len(rows)==18
    candidates=[];chosen={}
    for arm in ARMS:
        for budget in BUDGETS:
            rs=[r for r in rows if r['arm']==arm and r['budget']==budget]
            assert sorted(r['seed'] for r in rs)==SEEDS
            failures=[]
            for r in rs:
                reasons=[]
                if r['unsafe_recall_all']<.95:reasons.append('unsafe_recall_below_0.95')
                if r['FPR_all']>.05:reasons.append('safe_FPR_above_0.05')
                if reasons:failures.append(dict(seed=r['seed'],reasons=reasons))
            candidates.append(dict(arm=arm,budget=budget,eligible=not failures,mean_actual_call_rate=statistics.mean(r['actual_call_rate'] for r in rs),failures=failures))
        eligible=[r for r in candidates if r['arm']==arm and r['eligible']]
        chosen[arm]=min(eligible,key=lambda r:(r['mean_actual_call_rate'],r['budget']))['budget'] if eligible else None
    for c in candidates:c['selected']=c['budget']==chosen[c['arm']]
    return rows,dict(analysis='NEW_PER_ARM_EXPLORATORY_NOT_REPLACEMENT',source='dev_2048',N=158,N_safe=112,N_unsafe=46,selection_uses_target_labels=False,target_evaluation='ALREADY_EXPOSED_EXPLORATORY',rule='Within each arm all 3 seeds: TP/N_unsafe >= .95 and FP/N_safe <= .05; choose lowest mean actual calls; tie smaller existing budget. Safe abstain is separately disclosed, not a new criterion.',candidates=candidates,selected_budget_by_arm=chosen)

def compute(root):
    idx=readl(root/'analysis_index.jsonl');preds=readl(root/'predictions.jsonl');routes=readl(root/'routes.jsonl');by=collections.defaultdict(dict)
    for p in preds:
        assert p['sample_id'] not in by[p['model']]
        by[p['model']][p['sample_id']]=p
    dev=[r for r in idx if r['cohort']=='dev_2048'];dev_ids={r['sample_id'] for r in dev}
    devpreds={m:{sid:p for sid,p in ps.items() if sid in dev_ids} for m,ps in by.items()}
    devrows,selection=select_dev(dev,devpreds,[r for r in routes if r['cohort']=='dev_2048'])
    tables=[];contrasts=[];misses=[]
    for setting in routes:
        if setting['cohort']=='dev_2048':continue
        data=[r for r in idx if r['cohort']==setting['cohort']];route=set(setting['routed_ids']);base=by[f"E_field_seed{setting['seed']}"];teacher=by[setting['arm']] if setting['arm'] else {}
        tag={k:v for k,v in setting.items() if k!='routed_ids'}
        for domain in ['combined']+sorted({r['domain'] for r in data}):
            sub=[r for r in data if domain=='combined' or r['domain']==domain]
            tables.append({**tag,'domain':domain,**metric(sub,base,teacher,route),'evaluation_scope':'already_exposed_exploratory','selected_for_arm':setting['gate']=='G_uncertainty' and selection['selected_budget_by_arm'].get(setting['arm']) is not None and setting['budget']==selection['selected_budget_by_arm'][setting['arm']]})
            if setting['arm']=='L_direct':
                # One shared route, two teacher arms, all original budgets retained.
                counts=collections.Counter()
                for r in sub:
                    sid=r['sample_id'];x=by['L_direct'][sid]['prediction'] if sid in route else base[sid]['prediction'];y=by['L_relation'][sid]['prediction'] if sid in route else base[sid]['prediction'];gold=r['label'];fit=not r['mandatory_fields_overflow']
                    counts['corrected']+=x in ['safe','unsafe'] and x!=gold and y==gold
                    counts['introduced']+=x==gold and y in ['safe','unsafe'] and y!=gold
                    counts['correct_to_abstain']+=x==gold and y=='abstain'
                    counts['wrong_to_abstain']+=x in ['safe','unsafe'] and x!=gold and y=='abstain'
                    counts['abstain_to_correct']+=x=='abstain' and y==gold
                    counts['TP_delta']+=(y==gold=='unsafe')-(x==gold=='unsafe')
                    counts['FP_delta']+=(y=='unsafe' and gold=='safe')-(x=='unsafe' and gold=='safe')
                    counts['fit_corrected']+=fit and x in ['safe','unsafe'] and x!=gold and y==gold
                    counts['fit_introduced']+=fit and x==gold and y in ['safe','unsafe'] and y!=gold
                contrasts.append({**{k:v for k,v in tag.items() if k!='arm'},'domain':domain,'N':len(sub),'contrast':'relation_minus_direct_same_route',**{k:counts[k] for k in ['corrected','introduced','correct_to_abstain','wrong_to_abstain','abstain_to_correct','TP_delta','FP_delta','fit_corrected','fit_introduced']}})
        if setting['gate']=='G_uncertainty' and setting['arm']=='L_direct':
            for r in data:
                sid=r['sample_id'];e=base[sid]
                if r['label']=='unsafe' and e['prediction']=='safe' and sid not in route:
                    misses.append({**r,'seed':setting['seed'],'budget':setting['budget'],'unsafe_score':e['unsafe_score'],'L_direct':by['L_direct'][sid]['prediction'],'L_relation':by['L_relation'][sid]['prediction'],'human_review':'pending'})
    # Random repetitions averaged within each model seed, never cherry-picked.
    grouped=collections.defaultdict(list)
    keys=['cohort','domain','seed','arm','gate','budget']
    for r in tables:grouped[tuple(r[k] for k in keys)].append(r)
    compact=[]
    fields=[k for k in tables[0] if k not in keys+['random_seed','evaluation_scope','selected_for_arm']]
    for key,rs in grouped.items():
        out=dict(zip(keys,key));out['random_repetitions']=len(rs) if out['gate']=='G_random' else 0
        for k in fields:
            xs=[r[k] for r in rs if r[k] is not None]
            out[k]=statistics.mean(xs) if xs else None
            if out['gate']=='G_random':out[k+'_random_sd']=statistics.stdev(xs) if len(xs)>1 else 0
        compact.append(out)
    selected=[]
    for r in compact:
        b=selection['selected_budget_by_arm'].get(r['arm'])
        if r['gate']=='E_only' or b is not None and (r['gate'] in ['L_all','G_overflow'] or r['budget']==b):selected.append(r)
    candidate_rows=[]
    for c in selection['candidates']:
        candidate_rows.append({**{k:v for k,v in c.items() if k!='failures'},'failed_seed_constraints':json.dumps(c['failures'])})
    return {'dev_per_seed.csv':devrows,'scheme_selection.csv':candidate_rows,'safety_by_domain.csv':tables,'safety_compact.csv':compact,'selected_comparison.csv':selected,'same_gate_contrasts.csv':contrasts},selection,misses

def main(root):
    start=time.perf_counter();tables,selection,misses=compute(root)
    for name,rows in tables.items():csvwrite(root/name,rows)
    dump(root/'scheme_selection.json',selection);lines(root/'unrouted_unsafe.jsonl',misses)
    dump(root/'resource_usage.json',dict(new_requests=0,new_input_tokens=0,new_output_tokens=0,new_cache_tokens=0,new_API_cost_CNY=0,new_training_steps=0,new_GPU_seconds=0,cache_prediction_rows=len(readl(root/'predictions.jsonl')),analysis_seconds=time.perf_counter()-start,call_count_semantics='deployment_calls in tables: logical historical calls required by each cached policy, NOT newly billed requests; shared cache must not be summed across seeds/budgets/policies',model_inference='NOT_RUN_NOT_NEEDED'))
    print(json.dumps({'selection':selection,'table_rows':{k:len(v) for k,v in tables.items()}},ensure_ascii=False))
if __name__=='__main__':main(Path(sys.argv[1]) if len(sys.argv)>1 else Path(__file__).resolve().parent)
