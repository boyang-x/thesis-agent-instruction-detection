"""Read frozen checkpoints and reuse original pack/predict; never train."""
import collections,json,sys,time
from pathlib import Path
sys.path.insert(0,'/work')
from train_server import pack,Model,predict,torch
from common import readl,writel,dump,make_prediction
from legacy_rule import rule,parse_action
HERE=Path('/round3');start=time.time()
torch.set_num_threads(4);torch.backends.cudnn.benchmark=False;torch.use_deterministic_algorithms(True)
rows=[pack(r) for r in readl(HERE/'data.jsonl')]
writel(HERE/'packed.jsonl',rows)
# Freeze short-input subset before any new encoder or LLM predictions; no labels inspected.
selected=[]
for domain in ['banking','travel']:
    groups=collections.defaultdict(list)
    for r in rows:
        if r['domain']==domain and not r['train_overlap'] and not r['window']['mandatory_fields_overflow']:groups[r['group_id']].append(r['sample_id'])
    chosen=[]
    while len(chosen)<32 and any(groups.values()):
        for g in sorted(groups):
            if groups[g] and len(chosen)<32:chosen.append(groups[g].pop(0))
    selected+=chosen
dump(HERE/'information_selection.json',{'sample_ids':selected,'selection':'domain up to32, sorted task round-robin, source row order, no labels/predictions','frozen_before_predictions':True,'N':len(selected),'time_epoch':time.time()})
rules=[]
for r in rows:
    try:d,reason=rule({'messages':[{'source':'upstream_instruction_assumed_user','text':r['input']['instruction']}],'candidate':parse_action(r['input']['current_action']),'tool_semantics':r['input']['env_info']})
    except (ValueError,KeyError,json.JSONDecodeError):d,reason='abstain','candidate_parse_failure'
    rules.append(make_prediction(r,'R0',d,error_code=reason if d=='abstain' else None,rule_reason=reason))
writel(HERE/'R0_predictions.jsonl',rules)
fit=[r for r in rows if not r['window']['mandatory_fields_overflow']]
print(json.dumps({'packed':len(rows),'fit':len(fit),'overflow':len(rows)-len(fit),'short_N':len(selected)}),flush=True)
for s in [42,43,44]:
    model=Model().cuda();model.load_state_dict(torch.load(f'/work/runs/E_field_seed{s}/best.pt',weights_only=True));probs,_=predict(model,fit,'field')
    by={r['sample_id']:p for r,p in zip(fit,probs)};ps=[]
    for r in rows:
        p=by.get(r['sample_id']);ps.append(make_prediction(r,f'E_field_seed{s}','abstain' if p is None else 'unsafe' if p>=.5 else 'safe',p,seed=s,error_code='mandatory_fields_overflow' if p is None else None))
    writel(HERE/f'E_field_seed{s}_predictions.jsonl',ps);del model;torch.cuda.empty_cache();print(f'SEED {s} DONE',flush=True)
dump(HERE/'server_status.json',{'status':'COMPLETED','seconds':time.time()-start,'gpu':torch.cuda.get_device_name(0),'peak_memory_bytes':torch.cuda.max_memory_allocated(),'new_training_steps':0,'rows':len(rows),'fit':len(fit),'overflow':len(rows)-len(fit)})
