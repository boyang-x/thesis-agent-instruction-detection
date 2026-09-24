"""Frozen four-case real E -> original gate -> actual LLM verification, no training."""
import json
import subprocess
import time
from resume import HERE,PARENT,send,prediction
from common import readl,writel,dump,make_prediction
from compute import state

def main():
    assert not (HERE/'STOP.json').exists()
    repaired=readl(HERE/'repair_predictions.jsonl');assert len(repaired)==185
    assert not any(r.get('error_code')=='HTTP_402' for r in repaired),'402 must stop the stage'
    assert not (HERE/'live_router_predictions.jsonl').exists()
    selection=json.loads((PARENT/'live_selection.json').read_text());ids=selection['sample_ids'];threshold=selection['gate_threshold']
    old={r['sample_id']:r for r in readl(PARENT/'runs/E_field_seed42/predictions.jsonl')}
    by={r['sample_id']:r for r in readl(PARENT/'packed.jsonl')}
    requests={r['call_id']:r['request'] for r in readl(PARENT/'api_attempts.jsonl') if r['call_id'].startswith('paired__')}
    infra=json.loads((PARENT/'infrastructure.local.json').read_text());command=infra['remote_command'].replace('wangboyang-thesis-round2-live','wangboyang-thesis-round2-resume-live')
    t0=time.perf_counter();err=(HERE/'live_worker_stderr.log').open('w',encoding='utf-8')
    worker=subprocess.Popen(['ssh','-T','-o','BatchMode=yes',infra['ssh_host'],command],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=err,text=True,encoding='utf-8',bufsize=1)
    def receive(prefix):
        for line in worker.stdout:
            if line.startswith(prefix):return json.loads(line[len(prefix):])
        raise RuntimeError('GPU worker ended before '+prefix)
    ready=receive('ROUTER_READY ');ready['cold_start_wall_seconds']=time.perf_counter()-t0
    rows=[]
    try:
        for sid in ids:
            start=time.perf_counter();worker.stdin.write(json.dumps({'sample_id':sid})+'\n');worker.stdin.flush();small=receive('ROUTER_SCORE ')
            ms=(time.perf_counter()-start)*1000;p=small['unsafe_score'];r=by[sid]
            assert (p is None)==(old[sid]['unsafe_score'] is None)
            if p is not None:assert abs(p-old[sid]['unsafe_score'])<1e-6
            routed=p is None or abs(p-.5)<=threshold
            b=make_prediction(r,'E_field','abstain' if p is None else 'unsafe' if p>=.5 else 'safe',p)
            for arm in ('L_direct','L_relation'):
                start=time.perf_counter()
                if routed:
                    if (HERE/'STOP.json').exists():raise RuntimeError('service/budget circuit open')
                    raw=send(requests['paired__'+sid+'__'+arm],'live__'+sid+'__'+arm,'live')
                    l=prediction(r,arm,raw);l['phase']='live_teacher';append_target=HERE/'live_teacher_predictions.jsonl'
                    from common import append
                    append(append_target,l)
                else:l=b
                row=make_prediction(r,'E_to_'+arm,l['prediction'],None,phase='live_router',seed=42,variant='fixed05',budget=.25,routed=routed,gate_threshold=threshold,baseline_prediction=b['prediction'],baseline_state=state(b),small_probability=p,small_forward_ms=small['small_forward_ms'],worker_roundtrip_ms=ms,latency_ms=ms+(time.perf_counter()-start)*1000,latency_semantics='measured worker roundtrip + actual LLM request; paired arms share one E forward; cold startup separate',error_code=l.get('error_code'),actual_api_calls=1 if routed else 0,input_tokens=l.get('input_tokens',0),output_tokens=l.get('output_tokens',0),routed_teacher_available=l.get('error_code') is None if routed else None,raw_decision=l.get('raw_decision'),semantic_unknown=l.get('semantic_unknown',False),baseline_input_overflow=p is None,new_attempt_id=l.get('new_attempt_id'),cache_probability_difference=None if p is None else abs(p-old[sid]['unsafe_score']))
                rows.append(row);writel(HERE/'live_router_predictions.jsonl',rows)
                print(json.dumps({'sample':sid,'routed':routed,'arm':arm,'prediction':l['prediction'],'error':l.get('error_code')}),flush=True)
    finally:
        worker.stdin.close();end=receive('ROUTER_END ');worker.wait(timeout=30);err.close()
        dump(HERE/'live_router_status.json',{'status':'COMPLETED' if len(rows)==8 and not any(r.get('error_code') for r in rows) else 'PARTIAL','selection_identical_to_parent':True,'samples':len(ids),'sample_ids':ids,'teacher_requests':sum(r['actual_api_calls'] for r in rows),'wall_seconds':time.perf_counter()-t0,**ready,**end,'worker_exit':worker.returncode,'retrained':False})

if __name__=='__main__':main()
