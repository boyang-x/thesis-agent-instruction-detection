"""Round2 native baselines and window audit. Reuses cached BERT; no main entry changes."""
import collections
import json
import os
from pathlib import Path
import random
import re
import time
import numpy as np
import torch
from torch import nn
from transformers import AutoTokenizer,AutoModel
import transformers
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
import sklearn
from common import readl,writel,dump,score,make_prediction,quantile,append
from legacy_rule import rule,parse_action

ROOT=Path('/work');CFG=json.loads((ROOT/'config.json').read_text());DATA=readl(ROOT/'data.jsonl')
TOKENIZER=AutoTokenizer.from_pretrained('/models',local_files_only=True)
START=time.time()

def toks(s):return len(TOKENIZER.encode(s,add_special_tokens=False))
def terms(s):return set(re.findall(r'[a-z0-9_@.-]{3,}',s.lower()))
def chunks(s):
    # Preserve every character within chunks; IDs assigned before selection.
    return [s[i:i+800] for i in range(0,len(s),800)]

def pack(r):
    inp=r['input'];name=r['tool_name'];env=inp['env_info']
    blocks=re.split(r'(?m)(?=^[A-Za-z_]\w*:)',env)
    related=[b for b in blocks if name and b.startswith(name+':')]
    relevant='\n'.join(related) if related else env
    mandatory='USER REQUEST\n'+inp['instruction']+'\nCURRENT STEP (untrusted candidate)\n'+inp['current_action']+'\nTOOL SEMANTICS\n'+relevant
    history=chunks(inp['history']);query=terms(inp['instruction']+' '+inp['current_action'])
    rank=sorted(range(len(history)),key=lambda i:(len(query&terms(history[i])),i),reverse=True)
    order=list(dict.fromkeys(list(range(max(0,len(history)-2),len(history)))[::-1]+rank))
    text=mandatory;chosen=[]
    overflow=toks(mandatory)>510
    if not overflow:
        for i in order:
            candidate=text+f'\nHISTORY SEGMENT {i} (flattened, source unverified)\n'+history[i]
            if toks(candidate)<=510:text=candidate;chosen.append(i)
    head='USER REQUEST\n'+inp['instruction']+'\nHISTORY\n'+inp['history']+'\nCURRENT STEP\n'+inp['current_action']+'\nENVIRONMENT\n'+env
    # LLM uses original text with host span IDs and a common larger budget.
    fixed=[{'span_id':'U0','field':'instruction','text':inp['instruction']},{'span_id':'C0','field':'current_action_untrusted','text':inp['current_action']}]
    fixed += [{'span_id':f'T{i}','field':'env_info','text':b} for i,b in enumerate(blocks) if b in related]
    optional=[{'span_id':f'H{i}','field':'history_flattened_unverified','text':history[i]} for i in order]
    optional += [{'span_id':f'T{i}','field':'env_info','text':b} for i,b in enumerate(blocks) if b not in related]
    spans=list(fixed);omitted=[]
    def estimate(ss):
        s=json.dumps(ss,ensure_ascii=False)
        return max(toks(s)*1.25,len(s.encode('utf-8'))/3)+900
    llm_over=estimate(spans)>7500
    if not llm_over:
        for s in optional:
            if estimate(spans+[s])<=7500:spans.append(s)
            else:omitted.append(s['span_id'])
    else:omitted=[s['span_id'] for s in optional]
    return {**r,'field_text':text if not overflow else '', 'head_text':TOKENIZER.decode(TOKENIZER.encode(head,add_special_tokens=False)[:510],skip_special_tokens=True),
            'window':{'mandatory_fields_overflow':overflow,'mandatory_tokens':toks(mandatory),'field_tokens':min(512,toks(text)+2),
                      'history_chunks_total':len(history),'history_chunks_visible':len(chosen),'history_selected_ids':chosen,
                      'head_original_tokens':toks(head)+2,'head_truncated':toks(head)>510,
                      'field_history_incomplete':len(chosen)<len(history),'full_current_step_visible_field':not overflow,
                      'head_current_step_fully_visible':toks(head.split('\nENVIRONMENT')[0])<=510},
            'llm_input':{'spans':spans,'provenance_note':'Upstream instruction/environment fields; history and current step text cannot authenticate their own authority.'},
            'llm_window':{'estimated_tokens_with_prompt':estimate(spans),'estimator':'max(1.25*cached_mBERT_tokens,UTF8_bytes/3)+900; not provider-exact','omitted_span_ids':omitted,'mandatory_fields_overflow':llm_over}}

def seed(s):random.seed(s);np.random.seed(s);torch.manual_seed(s);torch.cuda.manual_seed_all(s)

class Model(nn.Module):
    def __init__(self):
        super().__init__();self.encoder=AutoModel.from_pretrained('/models',local_files_only=True,add_pooling_layer=False,attn_implementation='eager');self.head=nn.Linear(self.encoder.config.hidden_size,1)
    def forward(self,x):return self.head(self.encoder(**x).last_hidden_state[:,0]).squeeze(-1)

def tensors(rows,view):
    enc=TOKENIZER([r[view+'_text'] for r in rows],padding=True,truncation=True,max_length=512,return_tensors='pt')
    return {k:v.cuda() for k,v in enc.items()}

def predict(model,rows,view,batch_size=32):
    output=[];losses=[];model.eval()
    with torch.no_grad():
        for offset in range(0,len(rows),batch_size):
            rs=rows[offset:offset+batch_size];x=tensors(rs,view);y=torch.tensor([r['label']=='unsafe' for r in rs],dtype=torch.float32,device='cuda')
            logits=model(x);losses+=nn.functional.binary_cross_entropy_with_logits(logits,y,reduction='none').tolist()
            output+=logits.sigmoid().tolist()
    return output,float(np.mean(losses)) if losses else None

def train_one(packed,s,view='field',debug=False):
    name='debug_fit32' if debug else f'E_{view}_seed{s}'
    out=ROOT/'runs'/name;out.mkdir(parents=True,exist_ok=False)
    eligible=[r for r in packed if not r['window']['mandatory_fields_overflow']]
    train=[r for r in eligible if r['split']=='train'];dev=[r for r in eligible if r['split']=='dev']
    if debug:
        rng=random.Random(42);small=[]
        for y in ('safe','unsafe'):
            rs=[r for r in train if r['label']==y];rng.shuffle(rs);small+=rs[:16]
        train=small
    seed(s);model=Model().cuda();initial_head=model.head.weight.detach().double().sum().item()
    optimizer=torch.optim.AdamW(model.parameters(),lr=5e-5 if debug else CFG['lr'],weight_decay=.01)
    epochs=60 if debug else CFG['epochs'];best=-1;curves=[];began=time.time();qualified=False
    for epoch in range(epochs):
        assert time.time()-START<CFG['max_gpu_seconds']
        if debug and time.time()-began>1200:break
        order=list(range(len(train)));random.Random(s+epoch).shuffle(order);model.train()
        for i in range(0,len(order),16):
            rs=[train[j] for j in order[i:i+16]];x=tensors(rs,view);y=torch.tensor([r['label']=='unsafe' for r in rs],dtype=torch.float32,device='cuda')
            optimizer.zero_grad(set_to_none=True);logits=model(x);loss=nn.functional.binary_cross_entropy_with_logits(logits,y);assert torch.isfinite(loss)
            loss.backward();torch.nn.utils.clip_grad_norm_(model.parameters(),1.);optimizer.step()
        record={'epoch':epoch+1}
        for split,rs in [('train',train),('dev',dev)]:
            probs,vl=predict(model,rs,view)
            ps=[make_prediction(r,name,'unsafe' if p>=.5 else 'safe',p) for r,p in zip(rs,probs)]
            record[split]={'loss':vl,'metrics':score(ps),'positive_fraction':sum(p>=.5 for p in probs)/len(probs),'probability_quantiles':{str(q):quantile(probs,q) for q in (0,.1,.5,.9,1)}}
        append(out/'curves.jsonl',record);curves.append(record)
        if debug:
            acc=record['train']['metrics']['correct_decisions/N_total']['value']
            if acc>=.95 and record['train']['loss']<=.2:qualified=True;break
        else:
            objective=record['dev']['metrics']['macro_F1_covered']
            if objective>best:
                best=objective;torch.save(model.state_dict(),out/'best.pt');best_epoch=epoch+1
        print(json.dumps({'run':name,'epoch':epoch+1,'train_loss':record['train']['loss'],'train_f1':record['train']['metrics']['macro_F1_covered'],'dev_f1':record['dev']['metrics']['macro_F1_covered']}),flush=True)
    if debug:
        probs,_=predict(model,train,view)
        writel(out/'train_predictions.jsonl',[make_prediction(r,name,'unsafe' if p>=.5 else 'safe',p,debug_only=True) for r,p in zip(train,probs)])
        dump(out/'status.json',{'status':'COMPLETED','learning_chain_qualified':qualified,'train_rows':len(train),'epochs':len(curves),'seconds':time.time()-began,'first_train_loss':curves[0]['train']['loss'],'last_train_loss':curves[-1]['train']['loss'],'train_final':curves[-1]['train']['metrics'],'all_encoder_parameters_trainable':all(p.requires_grad for p in model.encoder.parameters())})
        del model,optimizer;torch.cuda.empty_cache();return qualified
    model.load_state_dict(torch.load(out/'best.pt',weights_only=True));dp,_=predict(model,dev,view)
    thresholds=[]
    for t in CFG['threshold_grid']:
        m=score([make_prediction(r,name,'unsafe' if p>=t else 'safe',p) for r,p in zip(dev,dp)])
        thresholds.append((m['macro_F1_covered'],-abs(t-.5),t))
    threshold=max(thresholds)[2]
    gate_thresholds={str(b):quantile([abs(p-.5) for p in dp],b) for b in CFG['gate_budgets']}
    predictions=[]
    model.eval()
    with torch.no_grad():
        for r in packed:
            if r['window']['mandatory_fields_overflow']:
                predictions.append(make_prediction(r,name,'abstain',None,seed=s,error_code='mandatory_fields_overflow',latency_ms=0,window=r['window']));continue
            x=tensors([r],view);torch.cuda.synchronize();t0=time.perf_counter();p=float(model(x).sigmoid()[0]);torch.cuda.synchronize()
            predictions.append(make_prediction(r,name,'unsafe' if p>=.5 else 'safe',p,seed=s,latency_ms=(time.perf_counter()-t0)*1000,window=r['window']))
    writel(out/'predictions.jsonl',predictions)
    dump(out/'status.json',{'status':'COMPLETED','seed':s,'view':view,'best_epoch':best_epoch,'dev_best_macro_F1':best,'threshold_dev':threshold,'gate_thresholds_dev':gate_thresholds,'initial_head_sum':initial_head,'epochs':epochs,'train_rows':len(train),'training_steps':epochs*((len(train)+15)//16),'seconds':time.time()-began,'learning_chain_qualified':True,'max_memory_allocated':torch.cuda.max_memory_allocated()})
    del model,optimizer;torch.cuda.empty_cache()

def simple(packed):
    rules=[]
    for r in packed:
        t0=time.perf_counter()
        try:
            a=parse_action(r['input']['current_action']);decision,reason=rule({'messages':[{'source':'upstream_instruction_assumed_user','text':r['input']['instruction']}],'candidate':a,'tool_semantics':r['input']['env_info']})
        except (ValueError,KeyError,json.JSONDecodeError):decision,reason='abstain','candidate_parse_failure'
        rules.append(make_prediction(r,'R0',decision,1. if decision=='unsafe' else 0. if decision=='safe' else None,error_code=reason if decision=='abstain' else None,rule_reason=reason,latency_ms=(time.perf_counter()-t0)*1000,input_scope='legacy_rule_full_task_candidate_not_full_step_reasoning'))
    writel(ROOT/'R0_predictions.jsonl',rules)
    train=[r for r in packed if r['split']=='train' and not r['window']['mandatory_fields_overflow']]
    vector=TfidfVectorizer(ngram_range=(1,2),min_df=1,max_features=30000,sublinear_tf=True)
    x=vector.fit_transform([r['field_text'] for r in train]);y=[r['label']=='unsafe' for r in train]
    for s in CFG['seeds']:
        model=LogisticRegression(C=1.,solver='liblinear',max_iter=2000,random_state=s);model.fit(x,y)
        ps=[]
        for r in packed:
            t0=time.perf_counter()
            if r['window']['mandatory_fields_overflow']:p=None;decision='abstain'
            else:p=float(model.predict_proba(vector.transform([r['field_text']]))[0,1]);decision='unsafe' if p>=.5 else 'safe'
            ps.append(make_prediction(r,'R1',decision,p,seed=s,error_code='mandatory_fields_overflow' if p is None else None,latency_ms=(time.perf_counter()-t0)*1000))
        writel(ROOT/f'R1_seed{s}_predictions.jsonl',ps)
    majority='unsafe' if sum(y)>len(y)/2 else 'safe'
    writel(ROOT/'majority_predictions.jsonl',[make_prediction(r,'majority',majority,float(majority=='unsafe')) for r in packed])

def main():
    torch.set_num_threads(4);torch.backends.cudnn.benchmark=False;torch.use_deterministic_algorithms(True)
    dump(ROOT/'environment.json',{'torch':torch.__version__,'transformers':transformers.__version__,'sklearn':sklearn.__version__,'gpu':torch.cuda.get_device_name(0),'cuda':torch.version.cuda,'model_id':CFG['model_id'],'gpu_count':1})
    packed=[pack(r) for r in DATA];writel(ROOT/'packed.jsonl',packed)
    dump(ROOT/'window_audit.json',[{'sample_id':r['sample_id'],'split':r['split'],**r['window'],'llm_window':r['llm_window']} for r in packed]);print('PACK_READY',flush=True)
    simple(packed)
    qualified=train_one(packed,42,debug=True)
    if qualified:
        for s in CFG['seeds']:train_one(packed,s)
        train_one(packed,42,view='head')
    dump(ROOT/'server_complete.json',{'learning_chain_qualified':qualified,'seconds':time.time()-START,'gpu_seconds_limit':7200,'status':'COMPLETED' if qualified else 'E_BLOCKED_DEBUG_FAILURE','P3':'NOT_RUN'})

if __name__=='__main__':main()
