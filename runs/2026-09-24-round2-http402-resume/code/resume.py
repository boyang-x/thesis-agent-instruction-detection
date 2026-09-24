"""Only replay frozen HTTP402 requests; sequential circuit breaker and incremental budget."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
import httpx

HERE=Path(__file__).resolve().parent;PARENT=HERE.with_name('thesis_round2_20260924');REPO=HERE.parents[1]
sys.path.insert(0,str(PARENT));sys.path.insert(0,str(REPO/'src'))
from common import readl,append,dump,make_prediction
from llm_compare import interpret
from choiceguard_research.runner import PROVIDERS,read_environment_value,utc_now
RID='2026-09-24-round2-http402-resume';FROZEN='732834f3f07e508455a108128231a0aba91a5152'
F=json.loads((PARENT/'prompts_frozen.json').read_text(encoding='utf-8'))
PROVIDER=PROVIDERS['deepseek']

def sha(s):return hashlib.sha256(s.encode('utf-8')).hexdigest()
def price(u):
    total=u.get('prompt_tokens',0);hit=u.get('prompt_cache_hit_tokens',u.get('prompt_tokens_details',{}).get('cached_tokens',0))
    return (hit*.04+(total-hit)*2+u.get('completion_tokens',0)*8)/1_000_000
def reserve(request):return ((len(json.dumps(request['messages'],ensure_ascii=False).encode('utf-8'))+512)*2+request['max_tokens']*8)/1_000_000

def setup():
    if (HERE/'freeze_manifest.json').exists():return
    oldcalls=readl(PARENT/'api_calls.jsonl');oldreq={r['attempt_id']:r for r in readl(PARENT/'api_attempts.jsonl')}
    failed=[r for r in oldcalls if r.get('error_code')=='HTTP_402' and r['call_id'].startswith('paired__')]
    assert len(failed)==185
    queue=[]
    for r in failed:
        req=oldreq[r['attempt_id']]['request'];sid,arm=r['call_id'].split('__')[1:]
        assert req['model']==F['model'] and req['temperature']==0 and req['max_tokens']==800
        assert req['messages'][0]['content']==F[arm]
        queue.append({'sample_id':sid,'arm':arm,'parent_attempt_id':r['attempt_id'],'parent_call_id':r['call_id'],'request':req,'request_sha256':sha(json.dumps(req,ensure_ascii=False,sort_keys=True))})
    from common import writel
    writel(HERE/'retry_queue.local.jsonl',queue)
    files=['config.json','selection.json','sample_index.jsonl','packed.jsonl','prompts_frozen.json','live_selection.json','analysis_contract.json','llm_predictions.jsonl','api_calls.jsonl','api_attempts.jsonl']
    files += [str(p.relative_to(PARENT)).replace('\\','/') for p in (PARENT/'runs').glob('*/status.json')]
    dump(HERE/'freeze_manifest.json',{'run_id':RID,'frozen_public_commit':FROZEN,'parent_run_id':json.loads((PARENT/'config.json').read_text())['run_id'],'frozen_at':utc_now(),'sha256':{f:hashlib.sha256((PARENT/f).read_bytes()).hexdigest() for f in files},'request_model':F['model'],'old_response_models':sorted({r['payload']['model'] for r in oldcalls if r.get('payload')}),'old_system_fingerprints':sorted({r['payload'].get('system_fingerprint','') for r in oldcalls if r.get('payload')}),'missing_402_arms':185,'successful_native_arms_to_reuse':71,'new_request_cap':200,'estimated_CNY_cap':10,'sequential_requests':True,'retrain':False,'new_algorithm':False,'normal_model_abstain_retry':False})
    dump(HERE/'pricing.json',{'source':'https://api-docs.deepseek.com/zh-cn/quick_start/pricing/','checked_at':utc_now(),'currency':'CNY','per_million_peak':{'cache_hit_input':.04,'cache_miss_input':2,'output':8},'per_million_offpeak':{'cache_hit_input':.02,'cache_miss_input':1,'output':4},'accounting':'peak-price conservative estimate; not account invoice; unknown-usage transport failures reserve per-request upper estimate','alias_disclosure':'official current docs route legacy deepseek-v4-flash to DeepSeek-V4.1-Flash; parent observed response name deepseek-flash; immutable weights unavailable'})
    (HERE/'PLAN.md').write_text('# 第二轮HTTP402补跑\n\n冻结732834f3；一次探测后仅补185个失败臂，复用71个原生成功响应；200次/预计10元上限；402立即停止后续发出；不重训、不改数据/窗口/提示/门控。最后沿用原4个案例验证router，重算三种子三预算，发布后本阶段结束。\n',encoding='utf-8')

def send(request,call_id,phase,parent_attempt_id=None):
    if (HERE/'STOP.json').exists():raise RuntimeError('run stopped; no further requests')
    calls=readl(HERE/'api_calls.jsonl');attempts=readl(HERE/'api_attempts.jsonl')
    if len(attempts)!=len(calls):raise RuntimeError('unresolved previous attempt; do not silently duplicate')
    amount=sum(r['cost_reserved_or_estimated_CNY'] for r in calls);bound=reserve(request)
    if len(attempts)>=200 or amount+bound>10:
        dump(HERE/'STOP.json',{'reason':'budget_guard','requests':len(attempts),'estimated_CNY':amount});raise RuntimeError('budget guard')
    assert request['model']==F['model'] and request['temperature']==F['temperature'] and request['max_tokens']==F['max_output_tokens']
    assert PROVIDER.base_url==F['base_url']
    aid=RID+'__'+phase+'__'+str(len(attempts)+1).zfill(3)
    key=read_environment_value(PROVIDER.api_key_env)
    if not key:raise RuntimeError('credential unavailable')
    a={'attempt_id':aid,'call_id':call_id,'phase':phase,'parent_attempt_id':parent_attempt_id,'started_at':utc_now(),'request':request,'request_sha256':sha(json.dumps(request,ensure_ascii=False,sort_keys=True)),'input_sha256':sha(request['messages'][-1]['content']),'system_prompt_sha256':sha(request['messages'][0]['content'])}
    append(HERE/'api_attempts.jsonl',a)
    r={k:v for k,v in a.items() if k!='request'};r.update(request_model=request['model'],error_code=None,usage={})
    start=time.perf_counter()
    try:
        with httpx.Client(timeout=55) as client:
            resp=client.post(F['base_url']+'/chat/completions',headers={'Authorization':'Bearer '+key},json=request)
        r['http_status']=resp.status_code
        if resp.status_code==200:
            r['payload']=resp.json();r['usage']=r['payload'].get('usage',{});r['response_model']=r['payload'].get('model');r['system_fingerprint']=r['payload'].get('system_fingerprint')
        else:r['error_code']='HTTP_'+str(resp.status_code);r['error_body']=resp.text[:700].replace(key,'[REDACTED]')
    except Exception as e:r['error_code']=type(e).__name__;r['error_message']=str(e)[:300].replace(key,'[REDACTED]')
    r['latency_ms']=(time.perf_counter()-start)*1000;r['completed_at']=utc_now()
    r['estimated_CNY_peak']=price(r['usage']) if r['usage'] else None
    r['cost_reserved_or_estimated_CNY']=r['estimated_CNY_peak'] if r['usage'] else 0 if r.get('http_status')==402 else bound
    append(HERE/'api_calls.jsonl',r)
    if r['error_code']=='HTTP_402':dump(HERE/'STOP.json',{'reason':'HTTP402_immediate_circuit_breaker','attempt_id':aid,'stopped_at':utc_now()})
    elif r.get('response_model') and r['response_model'] not in json.loads((HERE/'freeze_manifest.json').read_text())['old_response_models']:
        dump(HERE/'STOP.json',{'reason':'response_model_changed_keep_separate','attempt_id':aid,'response_model':r['response_model']})
    return r

def probe():
    assert not any(r['phase']=='probe' for r in readl(HERE/'api_calls.jsonl')),'one probe only'
    request={'model':F['model'],'messages':[{'role':'system','content':'Service connectivity check. Reply OK only.'},{'role':'user','content':'OK'}],'temperature':0,'max_tokens':800,'stream':False,'thinking':{'type':'disabled'}}
    r=send(request,'service_probe','probe');dump(HERE/'probe_status.json',{k:v for k,v in r.items() if k not in ('payload','error_body','error_message')});print(json.dumps({k:r.get(k) for k in ('error_code','response_model','system_fingerprint','usage','estimated_CNY_peak')}),flush=True)

def prediction(row,arm,raw,**extra):
    parsed=interpret(raw,row['llm_input'],arm);p=parsed.pop('prediction');u=raw['usage']
    return make_prediction(row,arm,p,None,phase='paired',input_window=row['llm_window'],latency_ms=raw['latency_ms'],input_tokens=u.get('prompt_tokens',0),output_tokens=u.get('completion_tokens',0),cache_hit_tokens=u.get('prompt_cache_hit_tokens',u.get('prompt_tokens_details',{}).get('cached_tokens',0)),cache_miss_tokens=u.get('prompt_cache_miss_tokens'),actual_api_calls=1,new_attempt_id=raw['attempt_id'],response_model=raw.get('response_model'),system_fingerprint=raw.get('system_fingerprint'),**parsed,**extra)

def run():
    probe_state=json.loads((HERE/'probe_status.json').read_text());assert probe_state['error_code'] is None
    by={r['sample_id']:r for r in readl(PARENT/'packed.jsonl')};done={r['parent_attempt_id'] for r in readl(HERE/'api_calls.jsonl') if r['phase']=='repair'}
    for q in readl(HERE/'retry_queue.local.jsonl'):
        if q['parent_attempt_id'] in done:continue
        if (HERE/'STOP.json').exists():break
        raw=send(q['request'],q['parent_call_id'],'repair',q['parent_attempt_id'])
        p=prediction(by[q['sample_id']],q['arm'],raw,parent_attempt_id=q['parent_attempt_id'])
        append(HERE/'repair_predictions.jsonl',p)
        print(json.dumps({'attempt':raw['attempt_id'],'sample':q['sample_id'],'arm':q['arm'],'prediction':p['prediction'],'error':p['error_code']}),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('stage',choices=['probe','run']);args=parser.parse_args();setup();probe() if args.stage=='probe' else run()
