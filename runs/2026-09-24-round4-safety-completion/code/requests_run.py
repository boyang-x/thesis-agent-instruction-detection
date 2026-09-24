"""Round3 request settings/parser reused; append-only round4 request ledger."""
import argparse,json,sys,time
from pathlib import Path
import httpx
HERE=Path(__file__).resolve().parent;OLD=HERE.with_name('thesis_round2_20260924')
sys.path.insert(0,str(OLD));sys.path.insert(0,str(HERE.parents[1]/'src'))
from common import readl,append,dump,make_prediction
from llm_compare import interpret
from choiceguard_research.runner import PROVIDERS,read_environment_value,utc_now
F=json.loads((OLD/'prompts_frozen.json').read_text(encoding='utf-8'));P=PROVIDERS['deepseek']
def send(inp,arm,cid,phase,client=None):
    if (HERE/'STOP.json').exists():raise RuntimeError('service circuit open')
    attempts=readl(HERE/'api_attempts.jsonl');calls=readl(HERE/'api_calls.jsonl');assert len(attempts)==len(calls),'inspect unresolved attempt; no silent rerun'
    existing=[r for r in calls if r['call_id']==cid]
    if existing:return existing[-1]
    prompt_arm='L_relation' if 'relation' in arm else 'L_direct'
    request={'model':F['model'],'messages':[{'role':'system','content':F[prompt_arm]},{'role':'user','content':json.dumps(inp,ensure_ascii=False)}],'temperature':0,'max_tokens':2048,'stream':False,'thinking':{'type':'disabled'}}
    key=read_environment_value(P.api_key_env);assert key and P.base_url==F['base_url']
    own=client is None;client=client or httpx.Client(timeout=70)
    try:
        for attempt in [0,1]:
            aid='round4__'+cid+f'__attempt{attempt}';start=time.perf_counter();began=utc_now()
            append(HERE/'api_attempts.jsonl',dict(attempt_id=aid,call_id=cid,phase=phase,started_at=began,request=request))
            raw=dict(attempt_id=aid,call_id=cid,phase=phase,started_at=began,request_model=F['model'],error_code=None,usage={})
            try:
                resp=client.post(P.base_url+'/chat/completions',headers={'Authorization':'Bearer '+key},json=request);raw['http_status']=resp.status_code
                if resp.status_code==200:
                    raw['payload']=resp.json();raw['usage']=raw['payload'].get('usage',{});raw['response_model']=raw['payload'].get('model');raw['system_fingerprint']=raw['payload'].get('system_fingerprint')
                else:raw['error_code']='HTTP_'+str(resp.status_code);raw['error_body']=resp.text[:500].replace(key,'[REDACTED]')
            except Exception as e:raw['error_code']=type(e).__name__;raw['error_message']=str(e)[:250].replace(key,'[REDACTED]')
            raw['latency_ms']=(time.perf_counter()-start)*1000;raw['completed_at']=utc_now();append(HERE/'api_calls.jsonl',raw)
            if raw['error_code']=='HTTP_402':dump(HERE/'STOP.json',dict(reason='HTTP_402',attempt_id=aid,time=utc_now()))
            if raw['error_code'] not in ['ConnectError','ReadTimeout','ConnectTimeout','RemoteProtocolError','HTTP_429','HTTP_500','HTTP_502','HTTP_503','HTTP_504']:break
        return raw
    finally:
        if own:client.close()
def prediction(row,inp,arm,raw,phase):
    parsed=interpret(raw,inp,'L_relation' if 'relation' in arm else 'L_direct');d=parsed.pop('prediction');u=raw['usage']
    return make_prediction(row,arm,d,phase=phase,**parsed,attempt_id=raw['attempt_id'],actual_api_calls=1,max_tokens=2048,response_model=raw.get('response_model'),system_fingerprint=raw.get('system_fingerprint'),input_tokens=u.get('prompt_tokens',0),output_tokens=u.get('completion_tokens',0),cache_hit_tokens=u.get('prompt_cache_hit_tokens',0),cache_miss_tokens=u.get('prompt_cache_miss_tokens',0),latency_ms=raw['latency_ms'],finish_reason=raw.get('payload',{}).get('choices',[{}])[0].get('finish_reason'))
def run():
    target=HERE/'new_predictions.jsonl';done={(r['phase'],r['sample_id'],r['model']) for r in readl(target)}
    with httpx.Client(timeout=70) as client:
        for q in readl(HERE/'request_queue.local.jsonl'):
            if (q['phase'],q['sample_id'],q['arm']) in done:continue
            if (HERE/'STOP.json').exists():break
            cid=q['phase']+'__'+q['sample_id']+'__'+q['arm'];raw=send(q['input'],q['arm'],cid,q['phase'],client);p=prediction(q['row'],q['input'],q['arm'],raw,q['phase']);append(target,p)
            print(json.dumps({'phase':q['phase'],'sample':q['sample_id'],'arm':q['arm'],'prediction':p['prediction'],'error':p['error_code'],'completed':len(readl(target))}),flush=True)
if __name__=='__main__':run()
