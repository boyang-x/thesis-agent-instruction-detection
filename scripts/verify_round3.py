"""Recompute the round-three tables from public raw decisions and frozen gates."""
import collections,csv,importlib.util,json,math,statistics
from pathlib import Path
def readl(p):return [json.loads(s) for s in p.read_text(encoding='utf-8').splitlines()]
def verify(root):
    spec=importlib.util.spec_from_file_location('round3_compare',root/'code/compare.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    tables,routes,info=module.compute(root)
    def check(filename,expected):
        stored=list(csv.DictReader((root/filename).open(encoding='utf-8')));assert len(stored)==len(expected),(filename,len(stored),len(expected))
        for actual,row in zip(stored,expected):
            for k,v in row.items():
                a=actual[k]
                if v is None:assert a=='',(filename,k,a)
                elif isinstance(v,(int,float)):assert math.isclose(float(a),v,abs_tol=1e-10),(filename,k,a,v)
                else:assert a==str(v),(filename,k,a,v)
    check('mechanism_ablation.csv',[r for r in tables if r['cohort']=='old_test_800']);check('transfer_results.csv',[r for r in tables if r['cohort']=='transfer_2048']);check('information_control.csv',info)
    assert routes==readl(root/'routes.jsonl')
    # Paired prompt arms use identical routing; every random repetition matches calls by domain.
    route_by={(r['cohort'],r['seed'],r['gate'],r['budget'],r['random_seed'],r['arm']):r['routed_ids'] for r in routes}
    for key,ids in route_by.items():
        if key[-1]=='L_direct':assert ids==route_by[key[:-1]+('L_relation',)]
    for r in tables:
        if r['gate']=='G_random':
            u=next(x for x in tables if all(x[k]==r[k] for k in ['cohort','domain','seed','arm','budget']) and x['gate']=='G_uncertainty')
            assert r['deployment_calls']==u['deployment_calls'] and r['routed']==u['routed']
    preds=readl(root/'predictions.jsonl');idx={r['sample_id']:r for r in readl(root/'analysis_index.jsonl')}
    assert all(r['label']==idx[r['sample_id']]['label'] for r in preds)
    assert len(preds)==len({(p['model'],p['sample_id']) for p in preds})
    random_groups=collections.defaultdict(list)
    for row in tables:
        if row['gate']=='G_random':random_groups[tuple(str(row[k]) for k in ['cohort','domain','seed','arm','budget'])].append(row)
    for row in csv.DictReader((root/'random_summary.csv').open(encoding='utf-8')):
        samples=random_groups[tuple(row[k] for k in ['cohort','domain','seed','arm','budget'])]
        assert len(samples)==int(row['repetitions'])==20
        for k in ['correct','correct_over_N','binary_net_correction','actual_call_rate','incremental_correct_vs_overflow','group_macro_correct_over_N']:
            vals=[s[k] for s in samples]
            assert math.isclose(float(row[k+'_mean']),statistics.mean(vals),abs_tol=1e-10)
            assert math.isclose(float(row[k+'_sd']),statistics.stdev(vals),abs_tol=1e-10)
    by={(p['model'],p['sample_id']):p for p in preds}
    for row in csv.DictReader((root/'paired_results.csv').open(encoding='utf-8')):
        subset=[r for r in idx.values() if r['cohort']==row['cohort'] and (row['domain']=='combined' or row['domain']==r['domain']) and (row['view']=='all' or r['mandatory_fields_overflow']==(row['view']=='S_overflow'))]
        assert len(subset)==int(row['N'])
        for arm,key in [('L_direct','direct_correct'),('L_relation','relation_correct')]:assert sum(by[arm,r['sample_id']]['prediction']==r['label'] for r in subset)==int(row[key])
    for r in tables:
        assert r['correct']==r['TP']+r['TN']
        assert r['N']==r['TP']+r['TN']+r['FP']+r['FN']+r['abstain']
        assert r['abstain']==r['abstain_input_overflow']+r['abstain_technical']+r['abstain_model']+r['abstain_rule_unsupported']+r['abstain_rule_unresolved']
    calls=readl(root/'api_usage.jsonl');res=json.loads((root/'resource_usage.json').read_text())
    assert res['new_api_calls']==len(calls)
    assert res['input_tokens']==sum(r['usage'].get('prompt_tokens',0) for r in calls)
    assert res['output_tokens']==sum(r['usage'].get('completion_tokens',0) for r in calls)
    assert res['cache_hit_tokens']==sum(r['usage'].get('prompt_cache_hit_tokens',0) for r in calls)
    main=[p for p in preds if p.get('phase')=='main'];short=[p for p in preds if p.get('phase')=='short']
    assert len(main)==528 and len(short)==64
    assert {p['sample_id'] for p in short}==set(json.loads((root/'information_selection.json').read_text())['sample_ids'])
    assert all(p.get('max_tokens')==2048 for p in main+short)
    assert len({r['call_id'] for r in calls})==592,'unexpected retries: disclose and adapt count instead of hiding'
    result={'prediction_rows':len(preds),'verified_table_rows':len(tables)+len(info),'verified_route_settings':len(routes),'new_api_calls':len(calls),'status':'VERIFIED'}
    return result
