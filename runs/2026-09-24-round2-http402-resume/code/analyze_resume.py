"""Merge-only analysis: reuse all parent successes, replace only recorded HTTP402 arms."""
import collections
import csv
import json
from pathlib import Path
import sys
import hashlib
from resume import HERE,PARENT,FROZEN,RID,price
from common import readl,writel,dump,frac
from compute import recompute,key,state

def reason(r):
    if r['prediction']!='abstain':return None
    e=r.get('error_code')
    if e in ('mandatory_fields_overflow','LLM_MANDATORY_OVERFLOW'):return 'input_overflow'
    if r['model']=='R0' and e not in ('HTTP_402',):return 'rule_abstain'
    if e:return 'technical_failure'
    return 'model_abstain'

def get_rows():
    original=readl(PARENT/'llm_predictions.jsonl');repairs={(r['sample_id'],r['model']):r for r in readl(HERE/'repair_predictions.jsonl')}
    oldcalls={r['call_id']:r for r in readl(PARENT/'api_calls.jsonl')}
    merged=[];lineage=[]
    for r in original:
        k=(r['sample_id'],r['model']);cid='paired__'+'__'.join(k);oldcall=oldcalls[cid]
        if r.get('error_code')=='HTTP_402' and k in repairs:
            p=dict(repairs[k]);source='new_402_repair'
        else:
            p=dict(r);source='reused_original_success' if not r.get('error_code') else 'unrepaired_original_failure'
            if source=='reused_original_success':
                assert all(p[x]==r[x] for x in r)
                p['response_model']=oldcall['payload'].get('model');p['system_fingerprint']=oldcall['payload'].get('system_fingerprint')
                p['cache_hit_tokens']=oldcall['usage'].get('prompt_cache_hit_tokens');p['cache_miss_tokens']=oldcall['usage'].get('prompt_cache_miss_tokens')
        p['record_origin']=source;p['original_attempt_id']=oldcall['attempt_id'];p['abstention_reason']=reason(p)
        merged.append(p);lineage.append({'sample_id':k[0],'arm':k[1],'original_attempt_id':oldcall['attempt_id'],'original_error_code':r.get('error_code'),'new_attempt_id':p.get('new_attempt_id'),'origin':source,'original_prediction':r['prediction'],'final_prediction':p['prediction'],'final_error_code':p.get('error_code')})
    assert not any(k not in {(r['sample_id'],r['model']) for r in original if r.get('error_code')=='HTTP_402'} for k in repairs)
    writel(HERE/'llm_predictions.jsonl',merged);writel(HERE/'response_lineage.jsonl',lineage)
    old=readl(PARENT/'predictions.jsonl');llm={(r['sample_id'],r['model']):r for r in merged}
    baseline={(r['sample_id'],r['model'],r.get('seed')):r for r in old if r['phase']=='baseline' and r['variant']=='fixed05'}
    rows=[]
    for r in old:
        if r['phase'] in ('paired','live_router'):continue
        p=dict(r)
        if r['phase']=='cached_cascade':
            arm='L_relation' if r['model'].endswith('L_relation') else 'L_direct'
            l=llm[r['sample_id'],arm];b=baseline[r['sample_id'],'R0' if r['model'].startswith('R0') else 'E_field',r['seed']]
            choice=l if r['routed'] else b
            p.update(prediction=choice['prediction'],error_code=choice.get('error_code'),latency_ms=b.get('latency_ms',0)+(l.get('latency_ms',0) if r['routed'] else 0),input_tokens=l.get('input_tokens',0) if r['routed'] else 0,output_tokens=l.get('output_tokens',0) if r['routed'] else 0,routed_teacher_available=l.get('error_code') is None if r['routed'] else None,teacher_error_code=l.get('error_code') if r['routed'] else None,semantic_unknown=l.get('semantic_unknown',False) if r['routed'] else False,raw_decision=l.get('raw_decision') if r['routed'] else None,baseline_input_overflow=b.get('error_code')=='mandatory_fields_overflow')
        p['abstention_reason']=reason(p);rows.append(p)
    rows+=merged
    for r in readl(HERE/'live_router_predictions.jsonl'):rows.append({**r,'abstention_reason':reason(r)})
    writel(HERE/'predictions.jsonl',rows)
    return rows

def extended(rows):
    groups=collections.defaultdict(list)
    for r in rows:groups[key(r)].append(r)
    out={}
    for k,rs in groups.items():
        counts=collections.Counter(reason(r) for r in rs if r['prediction']=='abstain')
        v={'abstention_reasons':dict(counts),'raw_model_abstain':sum(r.get('raw_decision')=='abstain' for r in rs),'mechanically_paused_despite_raw_binary':sum(r['prediction']=='abstain' and r.get('raw_decision') in ('safe','unsafe') and not r.get('error_code') for r in rs)}
        if 'routed' in rs[0]:
            v['input_overflow_sent']=sum(r.get('baseline_input_overflow',False) and r['routed'] for r in rs)
            v['input_overflow_resolved_correct']=sum(r.get('baseline_input_overflow',False) and r['prediction']==r['label'] for r in rs)
            v['baseline_abstain_to_correct']=sum(r['baseline_state']=='abstain' and state(r)=='correct' for r in rs)
            v['baseline_abstain_to_wrong']=sum(r['baseline_state']=='abstain' and state(r)=='wrong' for r in rs)
        out[k]=v
    return out

def resources():
    calls=readl(HERE/'api_calls.jsonl');old=readl(PARENT/'api_calls.jsonl')
    def usage(rs):return {'requests':len(rs),'successful_HTTP200':sum(r.get('http_status')==200 for r in rs),'failures':dict(collections.Counter(r['error_code'] for r in rs if r.get('error_code'))),'input_tokens':sum(r['usage'].get('prompt_tokens',0) for r in rs),'output_tokens':sum(r['usage'].get('completion_tokens',0) for r in rs),'cache_hit_input_tokens':sum(r['usage'].get('prompt_cache_hit_tokens',r['usage'].get('prompt_tokens_details',{}).get('cached_tokens',0)) for r in rs),'cache_miss_input_tokens':sum(r['usage'].get('prompt_cache_miss_tokens',r['usage'].get('prompt_tokens',0)-r['usage'].get('prompt_cache_hit_tokens',0)) for r in rs)}
    phase={s:usage([r for r in calls if r['phase']==s]) for s in ('probe','repair','live')}
    live=json.loads((HERE/'live_router_status.json').read_text()) if (HERE/'live_router_status.json').exists() else {'status':'NOT_RUN'}
    r={'new':usage(calls),'new_by_phase':phase,'old_including_failures':usage(old),'combined_actual':usage(old+calls),'new_estimated_CNY_peak':sum(r['cost_reserved_or_estimated_CNY'] for r in calls),'new_estimated_CNY_offpeak':sum(price(r['usage'])/2 for r in calls),'billing_amount_CNY':None,'pricing_source':'https://api-docs.deepseek.com/zh-cn/quick_start/pricing/','cost_note':'published peak/offpeak token-price estimates, not account bill; failed calls without usage reserve upper estimate','max_new_requests':200,'max_estimated_CNY':10,'gpu_training_seconds':0,'gpu_router_wall_seconds_upper_bound':live.get('wall_seconds',0),'live_router':live,'request_models':sorted({r['request_model'] for r in calls}),'response_models':sorted({r.get('response_model','NO_RESPONSE') for r in calls}),'new_system_fingerprints':sorted({r.get('system_fingerprint','NO_RESPONSE') for r in calls}),'old_system_fingerprints':sorted({r['payload'].get('system_fingerprint','') for r in old if r.get('payload')}),'started_at':calls[0]['started_at'] if calls else None,'completed_at':calls[-1]['completed_at'] if calls else None,'same_alias_does_not_prove_immutable_weights':True}
    assert r['new']['requests']<=200 and r['new_estimated_CNY_peak']<=10
    dump(HERE/'resource_usage.json',r);return r

def export_csv(name,rows):
    fields=list(dict.fromkeys(k for r in rows for k in r))
    with (HERE/name).open('w',encoding='utf-8',newline='') as f:w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)

def main():
    rows=get_rows();m=recompute(rows);x=extended(rows);dump(HERE/'metrics.json',m);dump(HERE/'abstention_details.json',x);resources()
    out=[]
    for k,v in m['results'].items():
        phase,model,seed,variant,budget,split=k.split('|');r=dict(phase=phase,model=model,seed=seed,variant=variant,budget=budget,split=split)
        for f in ('N','task_groups','TP','FP','TN','FN','abstain','abstain_safe','abstain_unsafe','coverage','F1_covered','macro_F1_covered','correct_decisions/N_total','TP/N_unsafe_total','FPR_all_safe','safety_block_if_abstain_pauses','normal_task_pause_cost'):
            r[f]=v[f]['value'] if isinstance(v[f],dict) else v[f]
        for a in ('technical_failure','model_abstain','input_overflow','rule_abstain'):r[a]=x[k]['abstention_reasons'].get(a,0)
        if 'routing' in v:
            for f in ('routed','corrected_errors','introduced_errors','unrouted_binary_errors','correct_to_abstain','wrong_to_abstain','cached_deployment_token_estimate'):r[f]=v['routing'][f]
            r['call_rate']=v['routing']['call_rate']['value'];r['baseline_abstain_to_correct']=x[k]['baseline_abstain_to_correct'];r['baseline_abstain_to_wrong']=x[k]['baseline_abstain_to_wrong']
        out.append(r)
    export_csv('results.csv',out);export_csv('reasoning_collaboration.csv',[r for r in out if r['phase']!='baseline']);export_csv('native_baselines.csv',[r for r in out if r['phase']=='baseline'])
    frozen=json.loads((HERE/'freeze_manifest.json').read_text());assert all(hashlib.sha256((PARENT/f).read_bytes()).hexdigest()==v for f,v in frozen['sha256'].items())
    dump(HERE/'freeze_recheck.json',{'status':'PASS','all_parent_file_hashes_unchanged':True,'reused_successes':sum(r.get('record_origin')=='reused_original_success' for r in rows),'new_requests':len(readl(HERE/'api_calls.jsonl'))})
    print(json.dumps({'rows':len(rows),'metric_groups':len(m['results']),'paired_changes':m['paired_protocol_changes']}))

if __name__=='__main__':main()
