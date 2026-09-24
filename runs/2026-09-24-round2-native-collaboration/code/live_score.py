"""Own persistent GPU worker for measured router path; no LLM calls on server."""
import json
import sys
import time
import torch
from common import readl
from train_server import Model,tensors

began=time.perf_counter()
torch.set_num_threads(4)
by={r['sample_id']:r for r in readl('/work/packed.jsonl')}
model=Model().cuda();model.load_state_dict(torch.load('/work/runs/E_field_seed42/best.pt',weights_only=True));model.eval()
print('ROUTER_READY '+json.dumps({'startup_seconds':time.perf_counter()-began}),flush=True)
for line in sys.stdin:
    sid=json.loads(line)['sample_id'];r=by[sid]
    if r['window']['mandatory_fields_overflow']:p=None;elapsed=0
    else:
        with torch.no_grad():
            x=tensors([r],'field');torch.cuda.synchronize();start=time.perf_counter();p=float(model(x).sigmoid()[0]);torch.cuda.synchronize();elapsed=(time.perf_counter()-start)*1000
    print('ROUTER_SCORE '+json.dumps({'sample_id':sid,'unsafe_score':p,'small_forward_ms':elapsed}),flush=True)
print('ROUTER_END '+json.dumps({'process_seconds':time.perf_counter()-began}),flush=True)
