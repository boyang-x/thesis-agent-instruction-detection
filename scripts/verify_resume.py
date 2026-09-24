"""Verify merged responses, immutable parent records, routes and incremental costs."""
import collections
import csv
import json
import math
from pathlib import Path
from round2_math import readl,key,recompute
from verify_round2 import same
from resume_metrics import extended

def verify(root):
    parent=root.parent/'2026-09-24-round2-native-collaboration'
    rows=readl(root/'predictions.jsonl');old=readl(parent/'predictions.jsonl');by={(key(r),r['sample_id']):r for r in rows}
    assert len(rows)==len(by)
    same(recompute(rows),json.loads((root/'metrics.json').read_text(encoding='utf-8')))
    same(extended(rows),json.loads((root/'abstention_details.json').read_text(encoding='utf-8')))
    index={r['sample_id']:r for r in readl(parent/'sample_index.jsonl')}
    for r in rows:assert all(r[f]==index[r['sample_id']][f] for f in ('label','split','group_id'))
    newcalls=readl(root/'api_usage.jsonl');oldcalls=readl(parent/'api_usage.jsonl');oldbyid={r['attempt_id']:r for r in oldcalls}
    lineage=readl(root/'response_lineage.jsonl');assert len(lineage)==256
    repaired=[r for r in newcalls if r['phase']=='repair']
    assert len(repaired)==len({r['parent_attempt_id'] for r in repaired})
    for r in repaired:
        o=oldbyid[r['parent_attempt_id']]
        assert o['error_code']=='HTTP_402'
        assert r['call_id']==o['call_id'] and r['input_sha256']==o['input_sha256'] and r['system_prompt_sha256']==o['system_prompt_sha256']
        assert r['request_model']=='deepseek-v4-flash'
    newllm={(r['sample_id'],r['model']):r for r in rows if r['phase']=='paired'}
    oldllm={(r['sample_id'],r['model']):r for r in old if r['phase']=='paired'}
    for l in lineage:
        k=(l['sample_id'],l['arm']);o=oldllm[k];n=newllm[k]
        if l['origin']=='reused_original_success':
            assert o.get('error_code') is None
            for field in ('prediction','label','raw_decision','reference_valid','logical_inconsistency','latency_ms','input_tokens','output_tokens','unsafe_score'):assert n.get(field)==o.get(field),(k,field)
            assert not l['new_attempt_id']
        else:assert o['error_code']=='HTTP_402'
    assert sum(l['origin']=='reused_original_success' for l in lineage)==71
    for r in old:
        if r['phase'] in ('baseline','paired_reference'):
            n=by[key(r),r['sample_id']]
            assert all(n[k]==v for k,v in r.items())
        elif r['phase']=='cached_cascade':
            n=by[key(r),r['sample_id']]
            for f in ('routed','gate_threshold','baseline_prediction','baseline_state','seed','budget'):assert n[f]==r[f]
            arm='L_relation' if r['model'].endswith('L_relation') else 'L_direct'
            expected=newllm[r['sample_id'],arm]['prediction'] if r['routed'] else r['baseline_prediction']
            assert n['prediction']==expected
    paired_ids={s:{r['sample_id'] for r in newllm.values() if r['split']==s} for s in ('dev','test')}
    assert len(paired_ids['dev'])==32 and len(paired_ids['test'])==96
    groups=collections.defaultdict(dict)
    for r in rows:
        if r['phase']=='cached_cascade' and r['model'].startswith('E_'):
            k=(r['seed'],r['budget']);groups[k].setdefault(r['model'],set())
            if r['routed']:groups[k][r['model']].add(r['sample_id'])
    assert len(groups)==9 and all(g['E_to_L_direct']==g['E_to_L_relation'] for g in groups.values())
    live=readl(root/'live_router_predictions.jsonl');selection=json.loads((parent/'live_selection.json').read_text(encoding='utf-8'))
    if live:
        assert {r['sample_id'] for r in live}==set(selection['sample_ids']) and len(live)==8
        assert all(r['gate_threshold']==selection['gate_threshold'] for r in live)
    resource=json.loads((root/'resource_usage.json').read_text(encoding='utf-8'))
    assert len(newcalls)==resource['new']['requests']<=200
    assert len(newcalls)==len({r['attempt_id'] for r in newcalls})
    assert all(r['attempt_id'] not in oldbyid for r in newcalls)
    assert resource['new']['input_tokens']==sum(r['usage'].get('prompt_tokens',0) for r in newcalls)
    assert resource['new']['output_tokens']==sum(r['usage'].get('completion_tokens',0) for r in newcalls)
    assert resource['new']['cache_hit_input_tokens']==sum(r['usage'].get('prompt_cache_hit_tokens',0) for r in newcalls)
    same(resource['new_estimated_CNY_peak'],sum(r['cost_reserved_or_estimated_CNY'] for r in newcalls))
    for r in newcalls:
        if r['usage']:
            u=r['usage'];expected=(u.get('prompt_cache_hit_tokens',0)*.04+u.get('prompt_cache_miss_tokens',u.get('prompt_tokens',0))*2+u.get('completion_tokens',0)*8)/1_000_000
            same(expected,r['estimated_CNY_peak'])
    assert resource['new_estimated_CNY_peak']<=10
    # Sequential stop evidence: if 402 occurs, it must be the final issued call.
    assert all(r.get('error_code')!='HTTP_402' for r in newcalls[:-1])
    result={'status':'PASS','publication_schema':'round2_resume','prediction_rows':len(rows),'metric_groups_recomputed':len(recompute(rows)['results']),'reused_original_successes_verified':71,'new_402_repairs_verified':len(repaired),'same_gate_pairs_verified':9,'new_requests':len(newcalls),'parent_results_unchanged':True,'new_training':False}
    (root/'publication_validation.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');return result
