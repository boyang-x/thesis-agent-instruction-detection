"""Independently regroup public records, reproduce metrics and verify paired routing."""
import collections
import csv
import hashlib
import json
import math
from pathlib import Path
from round2_math import readl,recompute,key,quantile

def same(a,b,path='root'):
    if isinstance(a,dict):
        assert set(a)==set(b),(path,'keys')
        for k in a:same(a[k],b[k],path+'/'+k)
    elif isinstance(a,list):
        assert len(a)==len(b),path
        for i,(x,y) in enumerate(zip(a,b)):same(x,y,path+'/'+str(i))
    elif isinstance(a,float):assert math.isclose(a,b,rel_tol=1e-9,abs_tol=1e-9),(path,a,b)
    else:assert a==b,(path,a,b)

def verify(root):
    rows=readl(root/'predictions.jsonl');index={r['sample_id']:r for r in readl(root/'sample_index.jsonl')}
    assert len(index)==956
    assert len(rows)==len({(key(r),r['sample_id']) for r in rows})
    for r in rows:
        assert all(r[f]==index[r['sample_id']][f] for f in ('label','split','group_id'))
    groups={s:{r['group_id'] for r in index.values() if r['split']==s} for s in ('train','dev','test')}
    assert not groups['train']&groups['dev'] and not groups['train']&groups['test'] and not groups['dev']&groups['test']
    actual=recompute(rows);same(actual,json.loads((root/'metrics.json').read_text(encoding='utf-8')))
    selection=json.loads((root/'selection.json').read_text(encoding='utf-8'))['samples']
    llm={(r['sample_id'],r['model']):r for r in rows if r.get('phase')=='paired'}
    for arm in ('L_direct','L_relation'):
        for split in ('dev','test'):
            assert {sid for (sid,a),r in llm.items() if a==arm and r['split']==split}==set(selection[split])
    bases={(r['model'],r.get('seed'),r['sample_id']):r for r in rows if r.get('phase')=='baseline' and r['variant']=='fixed05'}
    gate_sets=collections.defaultdict(dict)
    for r in rows:
        if r.get('phase')!='cached_cascade':continue
        isrule=r['model'].startswith('R0_');model='R0' if isrule else 'E_field'
        b=bases[model,r.get('seed'),r['sample_id']]
        arm='L_relation' if r['model'].endswith('L_relation') else 'L_direct';teacher=llm[r['sample_id'],arm]
        if isrule:routed=b['prediction']=='abstain'
        else:
            dev=[x['unsafe_score'] for x in readl(root/f'training/E_field_seed{r["seed"]}/dev_calibration_predictions.jsonl')]
            cutoff=quantile([abs(p-.5) for p in dev],r['budget']);same(cutoff,r['gate_threshold'])
            routed=b['unsafe_score'] is None or abs(b['unsafe_score']-.5)<=cutoff
            gate_sets[r['seed'],r['budget']].setdefault(arm,set())
            if routed:gate_sets[r['seed'],r['budget']][arm].add(r['sample_id'])
        assert r['routed']==routed
        assert r['prediction']==(teacher if routed else b)['prediction']
        assert r['baseline_prediction']==b['prediction']
        assert r['routed_teacher_available']==(teacher.get('error_code') is None if routed else None)
    assert len(gate_sets)==9
    assert all(v['L_direct']==v['L_relation'] for v in gate_sets.values())
    calls=readl(root/'api_usage.jsonl');resource=json.loads((root/'resource_usage.json').read_text(encoding='utf-8'))
    assert len(calls)==resource['api']['calls']==resource['attempts_reserved']<=300
    assert len(calls)==len({r['attempt_id'] for r in calls})
    assert resource['api']['input_tokens']==sum(r.get('usage',{}).get('prompt_tokens',0) for r in calls)
    assert resource['api']['output_tokens']==sum(r.get('usage',{}).get('completion_tokens',0) for r in calls)
    assert resource['api']['errors']==dict(collections.Counter(r['error_code'] for r in calls if r.get('error_code')))
    pairhash=collections.defaultdict(set)
    for r in calls:
        if r['call_id'].startswith('paired__'):pairhash[r['call_id'].split('__')[1]].add(r['input_sha256'])
    assert len(pairhash)==128 and all(len(v)==1 for v in pairhash.values())
    for s in (42,43,44):
        status=json.loads((root/f'training/E_field_seed{s}/status.json').read_text(encoding='utf-8'))
        assert status['status']=='COMPLETED' and status['epochs']==8 and status['train_rows']==553
    fstatus=json.loads((root/'training/E_field_seed42/status.json').read_text(encoding='utf-8'))
    hstatus=json.loads((root/'training/E_head_seed42/status.json').read_text(encoding='utf-8'))
    assert fstatus['initial_head_sum']==hstatus['initial_head_sum']
    for r in csv.DictReader((root/'results.csv').open(encoding='utf-8',newline='')):
        k='|'.join(r[x] for x in ('phase','model','seed','variant','budget','split'));m=actual['results'][k]
        for f in ('N','TP','FP','TN','FN','abstain'):assert int(r[f])==m[f]
        for f in ('F1_covered','macro_F1_covered','PR_AUC_AP'):
            assert (r[f]=='' and m[f] is None) or math.isclose(float(r[f]),m[f],abs_tol=1e-9)
    for r in csv.DictReader((root/'ablation.csv').open(encoding='utf-8',newline='')):
        if r['status']!='COMPLETED':assert all(r[k]=='' for k in ('N','F1_covered','macro_F1_covered','coverage'))
    assert resource['gpu']['reserved_device_seconds']<7200
    result={'status':'PASS','publication_schema':'round2','prediction_rows':len(rows),'sample_index_rows':len(index),'metric_groups_recomputed':len(actual['results']),'same_gate_pairs_verified':9,'same_LLM_input_pairs_verified':128,'unrun_results_blank':True,'P2_effect_complete':False}
    (root/'publication_validation.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    return result
