"""Assemble raw caches once per report refresh; old outputs are read-only."""
import json,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;OLD=HERE.with_name('thesis_round2_20260924');RESUME=HERE.with_name('thesis_round2_resume_20260924')
sys.path.insert(0,str(OLD))
from common import readl,writel,dump
from compare import write
def main():
    oldids=set(json.loads((OLD/'selection.json').read_text())['samples']['test'])
    old=[r for r in readl(OLD/'packed.jsonl') if r['sample_id'] in oldids];new=readl(HERE/'packed.jsonl')
    index=[]
    for cohort,rows in [('old_test_800',old),('transfer_2048',new)]:
        for r in rows:index.append({k:r[k] for k in ['sample_id','group_id','domain','label','source_file','source_row']}|{'cohort':cohort,'mandatory_fields_overflow':r['window']['mandatory_fields_overflow'],'train_overlap':r.get('train_overlap',False)})
    ps=[]
    for s in [42,43,44]:
        ps += [p for p in readl(OLD/f'runs/E_field_seed{s}/predictions.jsonl') if p['sample_id'] in oldids]
        ps += readl(HERE/f'E_field_seed{s}_predictions.jsonl')
    ps += [p for p in readl(OLD/'R0_predictions.jsonl') if p['sample_id'] in oldids]+readl(HERE/'R0_predictions.jsonl')
    ps += [p for p in readl(RESUME/'llm_predictions.jsonl') if p['sample_id'] in oldids]+readl(HERE/'llm_predictions.jsonl')+readl(HERE/'short_predictions.jsonl')
    writel(HERE/'analysis_index.jsonl',index);writel(HERE/'predictions.jsonl',ps);write(HERE)
    calls=readl(HERE/'api_calls.jsonl');usage=[r.get('usage',{}) for r in calls]
    dump(HERE/'resource_usage.json',{'new_api_calls':len(calls),'main_calls':sum(r['stage']=='main' for r in calls),'short_calls':sum(r['stage']=='short' for r in calls),'input_tokens':sum(u.get('prompt_tokens',0) for u in usage),'output_tokens':sum(u.get('completion_tokens',0) for u in usage),'cache_hit_tokens':sum(u.get('prompt_cache_hit_tokens',0) for u in usage),'cache_miss_tokens':sum(u.get('prompt_cache_miss_tokens',0) for u in usage),'request_models':sorted({r['request_model'] for r in calls}),'response_models':sorted({r['response_model'] for r in calls if r.get('response_model')}),'system_fingerprints':sorted({r['system_fingerprint'] for r in calls if r.get('system_fingerprint')}),'HTTP_errors':sum(bool(r['error_code']) for r in calls),'api_latency_seconds_sum':sum(r['latency_ms'] for r in calls)/1000,'started_at':calls[0]['started_at'] if calls else None,'last_completed_at':calls[-1]['completed_at'] if calls else None,'old_test_cached_arms_reused':192,'old_cache_new_calls':0,'gpu':json.loads((HERE/'server_status.json').read_text()) if (HERE/'server_status.json').exists() else None,'cost_invoice_CNY':None,'cost_note':'Tokens reported; provider invoice unavailable, no price assumption introduced.'})
if __name__=='__main__':main()
