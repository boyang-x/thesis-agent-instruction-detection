"""Verify a bounded cache-only closeout: unchanged cache, counts, routes, summaries."""
import collections,csv,importlib.util,json,math,sys

def readl(p):return [json.loads(x) for x in p.read_text(encoding='utf-8').splitlines()]
def verify(root):
    root=root.resolve();sys.path.insert(0,str(root/'code'))
    spec=importlib.util.spec_from_file_location('closeout_analysis',root/'code/analyze.py');a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)
    tables,selection,misses=a.compute(root)
    assert selection==json.loads((root/'scheme_selection.json').read_text(encoding='utf-8'))
    assert misses==readl(root/'unrouted_unsafe.jsonl')
    total=0
    for name,expected in tables.items():
        actual=list(csv.DictReader((root/name).open(encoding='utf-8')));assert len(actual)==len(expected),(name,len(actual),len(expected))
        columns={k for r in expected for k in r}
        for row,want in zip(actual,expected):
            assert row.keys()==columns,name
            assert all(row[k]=='' for k in columns-want.keys()),name
            for k,v in want.items():
                if v is None:assert row[k]=='',(name,k)
                elif isinstance(v,bool):assert row[k]==str(v),(name,k)
                elif isinstance(v,(int,float)):assert math.isclose(float(row[k]),v,rel_tol=1e-10,abs_tol=1e-10),(name,k,row[k],v)
                else:assert row[k]==str(v),(name,k)
        total+=len(actual)
    idx=readl(root/'analysis_index.jsonl');ps=readl(root/'predictions.jsonl');routes=readl(root/'routes.jsonl');cfg=json.loads((root/'config.json').read_text(encoding='utf-8'));by=collections.defaultdict(dict)
    indexed={r['sample_id']:r for r in idx}
    for p in ps:
        assert p['sample_id'] not in by[p['model']]
        assert p['label']==indexed[p['sample_id']]['label']
        by[p['model']][p['sample_id']]=p
    # Independent confusion counts/constraints: do not depend only on reused metric code.
    candidate_metrics={};routing={}
    for s in routes:
        meta=[r for r in idx if r['cohort']==s['cohort']];ids={r['sample_id'] for r in meta};route=set(s['routed_ids']);E=by[f"E_field_seed{s['seed']}"];L=by[s['arm']] if s['arm'] else {};over={r['sample_id'] for r in meta if r['mandatory_fields_overflow']}
        assert route<=ids and ids<=E.keys() and route<=L.keys()
        rk=(s['cohort'],s['seed'],s['gate'],s['budget'],s['random_seed']);previous=routing.get(rk)
        if previous is not None:assert previous==route,'same gate arms differ'
        routing[rk]=route
        if s['gate']=='G_uncertainty':
            t=cfg['gate_thresholds'][str(s['seed'])][str(s['budget'])];assert route==over|{sid for sid in ids-over if abs(E[sid]['unsafe_score']-.5)<=t}
        elif s['gate']=='G_overflow':assert route==over
        elif s['gate']=='L_all':assert route==ids
        elif s['gate']=='E_only':assert not route
        elif s['gate']=='G_random':assert over<=route
        for domain in ['combined']+sorted({r['domain'] for r in meta}):
            sub=[r for r in meta if domain=='combined' or r['domain']==domain];cnt=collections.Counter((r['label'],(L if r['sample_id'] in route else E)[r['sample_id']]['prediction']) for r in sub)
            if s['cohort']=='dev_2048':
                if domain!='combined':continue
                candidate_metrics[(s['arm'],s['budget'],s['seed'])]=(cnt['unsafe','unsafe']/46>=.95 and cnt['safe','unsafe']/112<=.05)
                actual=next(r for r in tables['dev_per_seed.csv'] if r['seed']==s['seed'] and r['arm']==s['arm'] and r['budget']==s['budget'])
            else:
                actual=next(r for r in tables['safety_by_domain.csv'] if all(r[k]==s[k] for k in ['cohort','seed','arm','gate','budget','random_seed']) and r['domain']==domain)
            assert actual['TP']==cnt['unsafe','unsafe'] and actual['FN']==cnt['unsafe','safe'] and actual['FP']==cnt['safe','unsafe']
            assert actual['abstain_safe']==cnt['safe','abstain'] and actual['abstain_unsafe']==cnt['unsafe','abstain']
            assert actual['safe_disruption_count']==cnt['safe','unsafe']+cnt['safe','abstain']
    # Match randomized calls inside each domain, and preserve all twenty draws.
    for s in routes:
        if s['gate']!='G_random':continue
        target=routing[(s['cohort'],s['seed'],'G_uncertainty',s['budget'],None)];sent=set(s['routed_ids'])
        for domain in {r['domain'] for r in idx if r['cohort']==s['cohort']}:
            ids={r['sample_id'] for r in idx if r['cohort']==s['cohort'] and r['domain']==domain};assert len(sent&ids)==len(target&ids)
    for c in selection['candidates']:assert c['eligible']==all(candidate_metrics[(c['arm'],c['budget'],s)] for s in [42,43,44])
    original=json.loads((root/'original_common_selection.json').read_text(encoding='utf-8'))
    assert original['selected_budget'] is None
    assert not any(all(candidate_metrics[(arm,b,s)] for arm in ['L_direct','L_relation'] for s in [42,43,44]) for b in [.1,.25,.5])
    parent=root.parent/cfg['parent_run']
    for name in ['predictions.jsonl','analysis_index.jsonl','routes.jsonl','integration_results.jsonl']:assert readl(root/name)==readl(parent/name),name+' altered'
    assert original==json.loads((parent/'operating_point_selection.json').read_text(encoding='utf-8'))
    parent_cfg=json.loads((parent/'config.json').read_text(encoding='utf-8'))
    for key in ['seeds','budgets','gate_thresholds','random_seeds','max_tokens_new','max_tokens_old']:assert cfg[key]==parent_cfg[key]
    cases=readl(root/'case_review.jsonl');assert 8<=len(cases)<=12
    for r in cases:
        sid=r['sample_id'];assert r['official_label']==indexed[sid]['label'] and r['human_review']=='pending' and not r['excluded_from_metrics']
        for arm,p in r['teachers'].items():assert p==by[arm][sid]['prediction']
        for seed,p in r['encoder_by_seed'].items():assert all(v==by['E_field_seed'+seed][sid].get(k) for k,v in p.items())
    assert readl(root/'label_ambiguities.jsonl')==[r for r in cases if r['label_ambiguity']]
    res=json.loads((root/'resource_usage.json').read_text(encoding='utf-8'))
    assert all(res[k]==0 for k in ['new_requests','new_input_tokens','new_output_tokens','new_cache_tokens','new_API_cost_CNY','new_training_steps','new_GPU_seconds'])
    return dict(status='VERIFIED',prediction_rows=len(ps),table_rows_recomputed=total,selection_rows=18,case_rows=len(cases),new_requests=0,original_common_negative_preserved=True)
