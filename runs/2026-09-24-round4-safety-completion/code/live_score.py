"""Round2 persistent router worker, extended only to read frozen transfer rows."""
import sys,time,json
sys.path.insert(0,'/work')
import torch
from common import readl
from train_server import Model,tensors
start=time.perf_counter();torch.set_num_threads(4)
by={r['sample_id']:r for r in readl('/work/packed.jsonl')+readl('/transfer/packed.jsonl')}
model=Model().cuda();model.load_state_dict(torch.load('/work/runs/E_field_seed42/best.pt',weights_only=True));model.eval();forwards=0
print('ROUTER_READY '+json.dumps({'startup_seconds':time.perf_counter()-start,'gpu':torch.cuda.get_device_name(0)}),flush=True)
for line in sys.stdin:
    sid=json.loads(line)['sample_id'];r=by[sid]
    if r['window']['mandatory_fields_overflow']:p=None;ms=0
    else:
        with torch.no_grad():
            x=tensors([r],'field');torch.cuda.synchronize();began=time.perf_counter();p=float(model(x).sigmoid()[0]);torch.cuda.synchronize();ms=(time.perf_counter()-began)*1000;forwards+=1
    print('ROUTER_SCORE '+json.dumps({'sample_id':sid,'unsafe_score':p,'small_forward_ms':ms}),flush=True)
print('ROUTER_END '+json.dumps({'process_seconds':time.perf_counter()-start,'actual_forward_count':forwards,'peak_gpu_memory_bytes':torch.cuda.max_memory_allocated()}),flush=True)
