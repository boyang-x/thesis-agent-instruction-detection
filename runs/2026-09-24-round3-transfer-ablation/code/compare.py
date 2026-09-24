"""Deterministic cache-only gate comparisons, all seeds and random repetitions."""
import collections,csv,json,random,statistics
from pathlib import Path
def readl(p):return [json.loads(x) for x in Path(p).read_text(encoding='utf-8').splitlines()] if Path(p).exists() else []
def div(a,b):return a/b if b else None
def csvwrite(p,rows):
    fields=list(dict.fromkeys(k for r in rows for k in r))
    with Path(p).open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
def statistics_for(meta,base,llm,route):
    n=len(meta);cnt=collections.Counter();group=collections.defaultdict(list);tokenin=tokenout=0;deployment_calls=0
    for r in meta:
        sid=r['sample_id'];b=base[sid];sent=sid in route;p=llm[sid] if sent else b;y=r['label'];d=p['prediction'];bd=b['prediction'];fit=not r['mandatory_fields_overflow']
        cnt['correct']+=d==y;cnt['abstain']+=d=='abstain';cnt['N_unsafe']+=y=='unsafe';cnt['N_safe']+=y=='safe';cnt['TP']+=d==y=='unsafe';cnt['TN']+=d==y=='safe';cnt['FP']+=d=='unsafe' and y=='safe';cnt['FN']+=d=='safe' and y=='unsafe';cnt['abstain_unsafe']+=d=='abstain' and y=='unsafe';cnt['abstain_safe']+=d=='abstain' and y=='safe'
        cnt['routed']+=sent;cnt['S_fit_N']+=fit;cnt['S_overflow_N']+=not fit
        if fit:
            cnt['S_fit_wrong_to_correct']+=bd in ['safe','unsafe'] and bd!=y and d==y
            cnt['S_fit_correct_to_wrong']+=bd==y and d in ['safe','unsafe'] and d!=y
            cnt['S_fit_correct_to_abstain']+=bd==y and d=='abstain'
            cnt['S_fit_wrong_to_abstain']+=bd in ['safe','unsafe'] and bd!=y and d=='abstain'
            cnt['S_fit_unrouted_errors']+=not sent and bd in ['safe','unsafe'] and bd!=y
            cnt['S_fit_correct']+=d==y
        else:
            cnt['S_overflow_recovery_correct']+=sent and d==y;cnt['S_overflow_recovery_wrong']+=sent and d in ['safe','unsafe'] and d!=y;cnt['S_overflow_final_abstain']+=d=='abstain';cnt['S_overflow_unrouted']+=not sent
        if d=='abstain':
            err=p.get('error_code')
            if err in ['mandatory_fields_overflow','LLM_MANDATORY_OVERFLOW']:cnt['abstain_input_overflow']+=1
            elif p.get('model')=='R0' and err=='unsupported_tool':cnt['abstain_rule_unsupported']+=1
            elif p.get('model')=='R0' and err!='candidate_parse_failure':cnt['abstain_rule_unresolved']+=1
            elif err:cnt['abstain_technical']+=1
            else:cnt['abstain_model']+=1
        if sent:
            deployment_calls+=p.get('actual_api_calls',1)>0
            tokenin+=p.get('input_tokens',0);tokenout+=p.get('output_tokens',0)
        group[r['group_id']].append(d==y)
    names=['correct','abstain','N_unsafe','N_safe','TP','TN','FP','FN','abstain_unsafe','abstain_safe','routed','S_fit_N','S_overflow_N','S_fit_wrong_to_correct','S_fit_correct_to_wrong','S_fit_correct_to_abstain','S_fit_wrong_to_abstain','S_fit_unrouted_errors','S_fit_correct','S_overflow_recovery_correct','S_overflow_recovery_wrong','S_overflow_final_abstain','S_overflow_unrouted','abstain_input_overflow','abstain_technical','abstain_model']
    out={k:cnt[k] for k in names};out['abstain_rule_unsupported']=cnt['abstain_rule_unsupported'];out['abstain_rule_unresolved']=cnt['abstain_rule_unresolved'];out.update(N=n,task_groups=len(group),correct_over_N=div(cnt['correct'],n),coverage=div(n-cnt['abstain'],n),unsafe_recall_all=div(cnt['TP'],cnt['N_unsafe']),unsafe_recall_covered=div(cnt['TP'],cnt['TP']+cnt['FN']),FPR_all=div(cnt['FP'],cnt['N_safe']),FPR_covered=div(cnt['FP'],cnt['FP']+cnt['TN']),actual_call_rate=div(deployment_calls,n),deployment_calls=deployment_calls,route_rate=div(cnt['routed'],n),routed_input_tokens=tokenin,routed_output_tokens=tokenout,group_macro_correct_over_N=statistics.mean(sum(v)/len(v) for v in group.values()) if group else None,binary_net_correction=cnt['S_fit_wrong_to_correct']-cnt['S_fit_correct_to_wrong'])
    return out
def compute(root):
    root=Path(root);cfg=json.loads((root/'config.json').read_text(encoding='utf-8'));meta=readl(root/'analysis_index.jsonl');pred=readl(root/'predictions.jsonl')
    by=collections.defaultdict(dict)
    for p in pred:
        assert p['sample_id'] not in by[p['model']],(p['model'],p['sample_id'])
        by[p['model']][p['sample_id']]=p
    tables=[];routes=[]
    for cohort in ['old_test_800','transfer_2048']:
        data=[r for r in meta if r['cohort']==cohort and not r.get('train_overlap')]
        if not data:continue
        ids={r['sample_id'] for r in data};over={r['sample_id'] for r in data if r['mandatory_fields_overflow']};domains=['combined'] if cohort.startswith('old') else ['combined','banking','travel']
        def add(base,arm,route,seed,gate,budget=None,rng=None):
            L=by[arm] if arm else {}
            if not ids<=base.keys() or not route<=L.keys():return
            tag=dict(cohort=cohort,seed=seed,arm=arm or '',gate=gate,budget=budget,random_seed=rng)
            routes.append({**tag,'routed_ids':sorted(route)})
            for domain in domains:
                rs=[r for r in data if domain=='combined' or r['domain']==domain]
                tables.append({**tag,'domain':domain,**statistics_for(rs,base,L,route)})
        for seed in cfg['seeds']:
            E=by[f'E_field_seed{seed}'];add(E,None,set(),seed,'E_only')
            for arm in ['L_direct','L_relation']:
                if not ids<=by[arm].keys():continue
                add(E,arm,over,seed,'G_overflow');add(E,arm,ids,seed,'L_all')
                for budget in cfg['budgets']:
                    threshold=cfg['gate_thresholds'][str(seed)][str(budget)]
                    route=over|{i for i in ids-over if abs(E[i]['unsafe_score']-.5)<=threshold}
                    add(E,arm,route,seed,'G_uncertainty',budget)
                    for rs in cfg['random_seeds']:
                        rng=random.Random(rs);randomroute=set(over)
                        # Match calls within each domain, so combined and domain controls both match.
                        for domain in sorted({r['domain'] for r in data}):
                            pool=sorted(r['sample_id'] for r in data if r['domain']==domain and r['sample_id'] not in over)
                            n=sum(sid in route for sid in pool);randomroute.update(rng.sample(pool,n))
                        add(E,arm,randomroute,seed,'G_random',budget,rs)
        R=by['R0'];add(R,None,set(),None,'R0_only')
        for arm in ['L_direct','L_relation']:
            add(R,arm,{i for i in ids if R[i]['prediction']=='abstain'},None,'R0_abstain_to_L')
    reference={(r['cohort'],r['domain'],r['seed'],r['arm']):r for r in tables if r['gate']=='G_overflow'}
    for r in tables:
        b=reference.get((r['cohort'],r['domain'],r['seed'],r['arm']))
        r['incremental_calls_vs_overflow']=r['deployment_calls']-b['deployment_calls'] if b else None
        r['incremental_correct_vs_overflow']=r['correct']-b['correct'] if b else None
    info=[];selection=json.loads((root/'information_selection.json').read_text()) if (root/'information_selection.json').exists() else {'sample_ids':[]}
    subset=[r for r in meta if r['sample_id'] in selection['sample_ids']]
    if subset:
        for model in [f'E_field_seed{s}' for s in cfg['seeds']]+['L_direct_short','L_direct','L_relation']:
            if not {r['sample_id'] for r in subset}<=by[model].keys():continue
            for domain in ['combined','banking','travel']:
                rs=[r for r in subset if domain=='combined' or r['domain']==domain]
                # LLM full routing for token/call reporting, E none.
                sent={r['sample_id'] for r in rs} if model.startswith('L_') else set()
                info.append(dict(model=model,domain=domain,**statistics_for(rs,by[model],by[model],sent)))
    return tables,routes,info
def write(root):
    root=Path(root);tables,routes,info=compute(root)
    csvwrite(root/'mechanism_ablation.csv',[r for r in tables if r['cohort']=='old_test_800'])
    csvwrite(root/'transfer_results.csv',[r for r in tables if r['cohort']=='transfer_2048'])
    csvwrite(root/'information_control.csv',info)
    (root/'routes.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in routes),encoding='utf-8')
    groups=collections.defaultdict(list)
    for r in tables:
        if r['gate']=='G_random':groups[tuple(r[k] for k in ['cohort','domain','seed','arm','budget'])].append(r)
    summary=[]
    for key,rs in groups.items():
        r=dict(zip(['cohort','domain','seed','arm','budget'],key));r['repetitions']=len(rs)
        for metric in ['correct','correct_over_N','binary_net_correction','actual_call_rate','incremental_correct_vs_overflow','group_macro_correct_over_N']:
            vals=[x[metric] for x in rs];r[metric+'_mean']=statistics.mean(vals);r[metric+'_sd']=statistics.stdev(vals) if len(vals)>1 else 0
        summary.append(r)
    csvwrite(root/'random_summary.csv',summary)
    print(json.dumps({'table_rows':len(tables),'settings':len(routes),'information_rows':len(info)}))
if __name__=='__main__':
    import sys
    write(Path(sys.argv[1]) if len(sys.argv)>1 else Path(__file__).resolve().parent)
