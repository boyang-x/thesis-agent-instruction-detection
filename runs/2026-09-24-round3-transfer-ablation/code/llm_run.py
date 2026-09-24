"""Frozen prompts/parser, new 2048-output cohort. Sequential, at most one transport retry."""
import argparse,json,sys,time
from pathlib import Path
import httpx
HERE=Path(__file__).resolve().parent;OLD=HERE.with_name('thesis_round2_20260924')
sys.path.insert(0,str(OLD));sys.path.insert(0,str(HERE.parents[1]/'src'))
from common import readl,append,dump,make_prediction
from llm_compare import interpret
from choiceguard_research.runner import PROVIDERS,read_environment_value,utc_now
F=json.loads((OLD/'prompts_frozen.json').read_text(encoding='utf-8'));PROVIDER=PROVIDERS['deepseek']
def run(stage):
    rows=readl(HERE/'packed.jsonl');assert len(rows)==264
    if stage=='short':
        ids=set(json.loads((HERE/'information_selection.json').read_text())['sample_ids']);rows=[r for r in rows if r['sample_id'] in ids]
        assert len(readl(HERE/'llm_predictions.jsonl'))==528,'finish main experiment first'
    target=HERE/('llm_predictions.jsonl' if stage=='main' else 'short_predictions.jsonl')
    done={(r['sample_id'],r['model']) for r in readl(target)}
    key=read_environment_value(PROVIDER.api_key_env);assert key;assert PROVIDER.base_url==F['base_url']
    assert len(readl(HERE/'api_attempts.jsonl'))==len(readl(HERE/'api_calls.jsonl')),'unresolved attempt must be inspected'
    # Once an HTTP response exists, reuse it even if wrong, abstaining or malformed.
    existing={r['call_id']:r for r in readl(HERE/'api_calls.jsonl')}
    dump(HERE/'request_config.json',{'model':F['model'],'temperature':0,'max_tokens':2048,'thinking':{'type':'disabled'},'system_prompts':{a:F[a] for a in ['L_direct','L_relation']},'parser':'round2 llm_compare.interpret unchanged','short_prompt':'L_direct unchanged; E0 span contains exact E field_text','planned_main':528,'planned_short':len(json.loads((HERE/'information_selection.json').read_text())['sample_ids']),'retry':'one extra only on transport/429/5xx; never model abstain or output parse errors'})
    with httpx.Client(timeout=70) as client:
        for row in rows:
            for model in (['L_direct','L_relation'] if stage=='main' else ['L_direct_short']):
                if (row['sample_id'],model) in done:continue
                if (HERE/'STOP.json').exists():return
                arm='L_relation' if model=='L_relation' else 'L_direct'
                inp=row['llm_input'] if stage=='main' else {'spans':[{'span_id':'E0','field':'exact_encoder_visible_field_text','text':row['field_text']}],'provenance_note':row['llm_input']['provenance_note']}
                cid=stage+'__'+row['sample_id']+'__'+model
                if stage=='main' and row['llm_window']['mandatory_fields_overflow']:
                    append(target,make_prediction(row,model,'abstain',error_code='LLM_MANDATORY_OVERFLOW',actual_api_calls=0));continue
                request={'model':F['model'],'messages':[{'role':'system','content':F[arm]},{'role':'user','content':json.dumps(inp,ensure_ascii=False)}],'temperature':0,'max_tokens':2048,'stream':False,'thinking':{'type':'disabled'}}
                raw=existing.get(cid)
                if raw is None:
                    for retry in [0,1]:
                        aid='round3__'+cid+f'__attempt{retry}';start=time.perf_counter()
                        append(HERE/'api_attempts.jsonl',{'attempt_id':aid,'call_id':cid,'stage':stage,'started_at':utc_now(),'request':request})
                        raw={'attempt_id':aid,'call_id':cid,'stage':stage,'started_at':utc_now(),'request_model':F['model'],'error_code':None,'usage':{}}
                        try:
                            resp=client.post(F['base_url']+'/chat/completions',headers={'Authorization':'Bearer '+key},json=request);raw['http_status']=resp.status_code
                            if resp.status_code==200:
                                raw['payload']=resp.json();raw['usage']=raw['payload'].get('usage',{});raw['response_model']=raw['payload'].get('model');raw['system_fingerprint']=raw['payload'].get('system_fingerprint')
                            else:raw['error_code']='HTTP_'+str(resp.status_code);raw['error_body']=resp.text[:500].replace(key,'[REDACTED]')
                        except Exception as e:raw['error_code']=type(e).__name__;raw['error_message']=str(e)[:250].replace(key,'[REDACTED]')
                        raw['latency_ms']=(time.perf_counter()-start)*1000;raw['completed_at']=utc_now();append(HERE/'api_calls.jsonl',raw)
                        if raw['error_code']=='HTTP_402':dump(HERE/'STOP.json',{'reason':'HTTP_402','attempt_id':aid,'time':utc_now()})
                        if raw['error_code'] not in ['ConnectError','ReadTimeout','ConnectTimeout','RemoteProtocolError','HTTP_429','HTTP_500','HTTP_502','HTTP_503','HTTP_504']:break
                parsed=interpret(raw,inp,arm);decision=parsed.pop('prediction');usage=raw['usage']
                append(target,make_prediction(row,model,decision,phase=stage,**parsed,attempt_id=raw['attempt_id'],actual_api_calls=1,max_tokens=2048,response_model=raw.get('response_model'),system_fingerprint=raw.get('system_fingerprint'),input_tokens=usage.get('prompt_tokens',0),output_tokens=usage.get('completion_tokens',0),cache_hit_tokens=usage.get('prompt_cache_hit_tokens',0),cache_miss_tokens=usage.get('prompt_cache_miss_tokens',0),finish_reason=raw.get('payload',{}).get('choices',[{}])[0].get('finish_reason'),latency_ms=raw['latency_ms']))
                print(json.dumps({'stage':stage,'sample':row['sample_id'],'arm':model,'decision':decision,'error':parsed['error_code'],'calls':len(readl(HERE/'api_calls.jsonl'))}),flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['main','short']);run(p.parse_args().stage)
