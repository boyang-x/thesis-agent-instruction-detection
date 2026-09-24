"""Recover frozen-checkpoint batched dev calibration scores; never retrain or change thresholds."""
import json
from pathlib import Path
import time
import torch
from common import readl,writel,dump,make_prediction,quantile
from train_server import Model,predict
began=time.perf_counter();torch.set_num_threads(4);torch.use_deterministic_algorithms(True)
rs=[r for r in readl('/work/packed.jsonl') if r['split']=='dev' and not r['window']['mandatory_fields_overflow']]
checks={}
for name,view in [('E_field_seed42','field'),('E_field_seed43','field'),('E_field_seed44','field'),('E_head_seed42','head')]:
    p=Path('/work/runs')/name;status=json.loads((p/'status.json').read_text())
    model=Model().cuda();model.load_state_dict(torch.load(p/'best.pt',weights_only=True));probs,_=predict(model,rs,view)
    predicted={str(b):quantile([abs(v-.5) for v in probs],b) for b in (.1,.25,.5)}
    delta=max(abs(predicted[k]-status['gate_thresholds_dev'][k]) for k in predicted)
    assert delta<1e-7,(name,delta)
    writel(p/'dev_calibration_predictions.jsonl',[make_prediction(r,name,'unsafe' if v>=.5 else 'safe',v,calibration_recovery=True) for r,v in zip(rs,probs)])
    checks[name]={'max_gate_difference':delta,'thresholds_unchanged':True,'checkpoint_unchanged':True}
    del model;torch.cuda.empty_cache()
dump('/work/calibration_recovery.json',{'status':'COMPLETED','seconds':time.perf_counter()-began,'checks':checks,'reason':'Original gates used batch32 dev probabilities; per-item exported predictions differ by floating-point rounding. Persist recovered raw dev scores from unchanged checkpoint.'})
