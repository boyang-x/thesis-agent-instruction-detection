"""Small measured online router; shares each actual E forward between paired protocols."""
import json
from pathlib import Path
import subprocess
import time
from common import readl,writel,dump,make_prediction
from compute import state
from llm_compare import one

HERE=Path(__file__).resolve().parent
def main():
    assert not (HERE/'live_router_predictions.jsonl').exists(),'never silently rerun'
    selected=json.loads((HERE/'selection.json').read_text())['samples']['test']
    old={r['sample_id']:r for r in readl(HERE/'runs/E_field_seed42/predictions.jsonl')}
    threshold=json.loads((HERE/'runs/E_field_seed42/status.json').read_text())['gate_thresholds_dev']['0.25']
    def gate(p):return p is None or abs(p-.5)<=threshold
    ids=[sid for routed in (True,False) for sid in [s for s in selected if gate(old[s]['unsafe_score'])==routed][:2]]
    dump(HERE/'live_selection.json',{'sample_ids':ids,'criterion':'first two routed and first two non-routed in frozen test order; no label selection','seed':42,'budget':.25,'gate_threshold':threshold})
    by={r['sample_id']:r for r in readl(HERE/'packed.jsonl')}
    infra=json.loads((HERE/'infrastructure.local.json').read_text());command=infra['remote_command']
    t0=time.perf_counter();err=(HERE/'live_worker_stderr.log').open('w',encoding='utf-8')
    worker=subprocess.Popen(['ssh','-T','-o','BatchMode=yes',infra['ssh_host'],command],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=err,text=True,encoding='utf-8',bufsize=1)
    def receive(prefix):
        for line in worker.stdout:
            if line.startswith(prefix):return json.loads(line[len(prefix):])
        raise RuntimeError('GPU worker ended before '+prefix)
    ready=receive('ROUTER_READY ');ready['cold_start_wall_seconds']=time.perf_counter()-t0
    predictions=[]
    try:
        for sid in ids:
            before=time.perf_counter();worker.stdin.write(json.dumps({'sample_id':sid})+'\n');worker.stdin.flush();small=receive('ROUTER_SCORE ')
            remote_elapsed=(time.perf_counter()-before)*1000;p=small['unsafe_score'];r=by[sid];routed=gate(p)
            decision='abstain' if p is None else 'unsafe' if p>=.5 else 'safe';b=make_prediction(r,'E_field',decision,p)
            for arm in ('L_direct','L_relation'):
                start=time.perf_counter();l=one(r,arm,'live') if routed else b
                predictions.append(make_prediction(r,'E_to_'+arm,l['prediction'],None,
                    phase='live_router',seed=42,variant='fixed05',budget=.25,routed=routed,gate_threshold=threshold,
                    baseline_prediction=decision,baseline_state=state(b),small_probability=p,small_forward_ms=small['small_forward_ms'],
                    worker_roundtrip_ms=remote_elapsed,latency_ms=remote_elapsed+(time.perf_counter()-start)*1000,
                    latency_semantics='measured warm worker roundtrip + actual API wall time; paired arms share one measured E forward, cold startup reported separately',
                    error_code=l.get('error_code'),actual_api_calls=l.get('actual_api_calls',0) if routed else 0,
                    input_tokens=l.get('input_tokens',0) if routed else 0,output_tokens=l.get('output_tokens',0) if routed else 0,
                    cache_probability_difference=None if p is None else abs(p-old[sid]['unsafe_score'])))
                writel(HERE/'live_router_predictions.jsonl',predictions)
                print(json.dumps({'sample':sid,'routed':routed,'arm':arm,'prediction':l['prediction']}),flush=True)
    finally:
        worker.stdin.close()
        end=receive('ROUTER_END ');worker.wait(timeout=30);err.close()
        dump(HERE/'live_router_status.json',{'status':'PATH_ONLY_SERVICE_BLOCKED' if any(r.get('error_code')=='SERVICE_BLOCKED_INSUFFICIENT_BALANCE' for r in predictions) else 'COMPLETED' if len(predictions)==len(ids)*2 else 'PARTIAL','sample_count':len(ids),'prediction_rows':len(predictions),'wall_seconds':time.perf_counter()-t0,**ready,**end,'worker_exit':worker.returncode,'new_api_calls':sum(r.get('actual_api_calls',0) for r in predictions)})

if __name__=='__main__':main()
