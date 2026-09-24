"""Read fixed native rows, merge task identities, freeze split and pairing before predictions."""
import collections
import hashlib
import json
from pathlib import Path
import random
import re
import sys
from common import dump,writel,readl

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[1]
OLD=REPO/'experiments/thesis_context_20260924'
UP=REPO/'.cache/thesis-toolsafe-20260924/TS-Bench/agentdojo-traj'
SEED=20260924

def norm(text):return re.sub(r'\s+',' ',text).strip().casefold()

def main():
    if (HERE/'data.jsonl').exists():raise RuntimeError('frozen data exists')
    rows=[];excluded=[]
    for name in ('slack','workspace'):
        for i,r in enumerate(json.loads((UP/(name+'.json')).read_text(encoding='utf-8'))):
            if r['score'] not in (0,1):excluded.append({'domain':name,'row':i,'reason':'controversial'});continue
            current=r['current_action']
            if re.search(r'(?m)^\s*Observation:',current):
                excluded.append({'domain':name,'row':i,'reason':'post_step_observation_requires_audit'});continue
            action=re.search(r'\(2\) Action:\s*([A-Za-z_]\w*)',current)
            rows.append({'sample_id':f'ts_{name}_{i:04d}','source_file':f'TS-Bench/agentdojo-traj/{name}.json','source_row':i,
                         'interaction_id':r['id-interaction'],'segment_id':r['id-segment'],'domain':name,
                         'label':'unsafe' if r['score']==1 else 'safe','label_source':'official_step_score',
                         'exposure':'previously_exposed_exploratory','review_status':'pending_human',
                         'input':{k:r[k] for k in ('instruction','history','current_action','env_info')},
                         'tool_name':action.group(1) if action else None})
    parent=list(range(len(rows)))
    def find(x):
        while parent[x]!=x:parent[x]=parent[parent[x]];x=parent[x]
        return x
    def union(a,b):parent[find(a)]=find(b)
    keys={};exact=collections.defaultdict(list)
    for i,r in enumerate(rows):
        inp=r['input'];signature=json.dumps(inp,sort_keys=True)
        for key in [('task',norm(inp['instruction'])),('trajectory',r['domain'],r['interaction_id']),('exact',signature)]:
            if key in keys:union(i,keys[key])
            else:keys[key]=i
        exact[signature].append(i)
    duplicate_map=[];drop=set()
    for ids in exact.values():
        labels={rows[i]['label'] for i in ids}
        if len(labels)>1:
            for i in ids:drop.add(i);excluded.append({'sample_id':rows[i]['sample_id'],'reason':'exact_input_label_conflict'})
        else:
            for i in ids[1:]:drop.add(i);duplicate_map.append({'sample_id':rows[i]['sample_id'],'canonical_id':rows[ids[0]]['sample_id'],'grouped_before_dedup':True})
    groups=collections.defaultdict(list)
    for i,r in enumerate(rows):
        gid='task_'+hashlib.sha256(norm(rows[find(i)]['input']['instruction']).encode()).hexdigest()[:12]
        r['group_id']=gid
        if i not in drop:groups[gid].append(r)
    # One seeded group shuffle. No performance-dependent allocation/search.
    gids=sorted(groups);random.Random(SEED).shuffle(gids)
    n=len(gids);ntrain=round(n*.70);ndev=round(n*.15)
    assignment={g:'train' if i<ntrain else 'dev' if i<ntrain+ndev else 'test' for i,g in enumerate(gids)}
    final=[]
    for g,rs in groups.items():
        for r in rs:r['split']=assignment[g];final.append(r)
    for split in ('train','dev','test'):
        assert {r['label'] for r in final if r['split']==split}=={'safe','unsafe'},'single-class split; stop without searching seeds'
    # label-stratified, group round-robin sampling with natural subset proportions.
    def choose(split,limit):
        pool=[r for r in final if r['split']==split];size=min(limit,len(pool));rng=random.Random(SEED+(1 if split=='dev' else 2))
        counts=collections.Counter(r['label'] for r in pool);unsafe=round(size*counts['unsafe']/len(pool));selected=[]
        for label,count in [('safe',size-unsafe),('unsafe',unsafe)]:
            gs=collections.defaultdict(list)
            for r in pool:
                if r['label']==label:gs[r['group_id']].append(r)
            order=sorted(gs);rng.shuffle(order)
            for rs in gs.values():rng.shuffle(rs)
            while count:
                for g in order:
                    if count and gs[g]:selected.append(gs[g].pop());count-=1
        return [r['sample_id'] for r in selected]
    selected={'dev':choose('dev',32),'test':choose('test',96)}
    writel(HERE/'data.jsonl',final);writel(HERE/'sample_index.jsonl',[{k:v for k,v in r.items() if k!='input'} for r in final])
    writel(HERE/'duplicates.jsonl',duplicate_map);writel(HERE/'exclusions.jsonl',excluded)
    dump(HERE/'selection.json',{'seed':SEED,'samples':selected,'frozen_before_new_model_predictions':True,'sampling':'group-round-robin within label; approximately natural label proportions'})
    splitmeta={s:{'rows':sum(r['split']==s for r in final),'groups':len({r['group_id'] for r in final if r['split']==s}),'classes':dict(collections.Counter(r['label'] for r in final if r['split']==s))} for s in ('train','dev','test')}
    dump(HERE/'data_manifest.json',{'run_id':'2026-09-24-round2-native-collaboration','upstream_commit':'46358fa424a927a895c6c8322f99032c4eb5155e','raw_rows':len(rows),'retained_rows':len(final),'exact_duplicates_removed':len(duplicate_map),'exclusions':excluded,'splits':splitmeta,'group_overlap':0,'normalized_task_overlap':0,'exact_input_overlap':0,'test_status':'local_group_holdout_previously_exposed_exploratory_not_official_or_blind','official_fields':['instruction','history','current_action','env_info'],'custom_P1_P2_P3_added':False,'official_current_step_retained':True,'provenance':'upstream fields only; flattened history roles unverified','human_reviewed':0,'license':'MIT badge only; no standalone license found; no native redistribution'})
    dump(HERE/'config.json',{'run_id':'2026-09-24-round2-native-collaboration','seed_split':SEED,'seeds':[42,43,44],'model_path':'/models','model_id':'LLMLingua-2 multilingual BERT compression-finetuned backbone','epochs':8,'lr':2e-5,'batch_size':16,'max_length':512,'checkpoint_metric':'dev macro-F1 covered, ties earlier epoch','optimizer':'AdamW','weight_decay':.01,'threshold_grid':[i/100 for i in range(5,96,5)],'threshold_selection':'dev macro-F1, tie closest 0.5','gate_budgets':[.10,.25,.50],'max_api_calls':300,'max_output_tokens':800,'llm_input_token_estimate_cap':7500,'max_gpu_seconds':7200,'P3':'NOT_RUN_PRIORITIZE_MAIN_EXPERIMENT','learning_check':{'n':32,'lr':5e-5,'max_epochs':60,'stop_train_accuracy':.95,'stop_train_loss':.2,'max_seconds':1200}})
    rng=random.Random(SEED);review=[]
    for label in ('safe','unsafe'):
        pool=[r for r in final if r['split']!='test' and r['label']==label];rng.shuffle(pool);review+=pool[:4]
    olderrors={r['sample_id'] for r in readl(OLD/'predictions.jsonl') if r['model']=='B0' and r['prediction']!=r['label']}
    ambiguous=[r for r in final if r['split']!='test' and r['sample_id'] in olderrors and r not in review]
    review+=ambiguous[:4]
    assert len(review)==12
    questions=[];md=['# 12个重点人工待审案例','', '当前均未人工审核；仅从train/dev选取，不用test审核来改提示。','']
    for i,r in enumerate(review):
        q='官方标签是否与完整current_action步骤一致？来源声明能否从宿主字段确认？' if i<8 else '第一轮规则与官方标签有分歧：是读取也已越权、步骤说明包含偏离，还是标签定义/输入投影问题？'
        questions.append({**r,'review_question':q,'human_decision':None})
        md += [f"## {i+1}. {r['sample_id']} / {r['label']} / {r['split']}",'',q,'','```json',json.dumps(r['input'],ensure_ascii=False,indent=2),'```','']
    writel(HERE/'review_queue_12.jsonl',questions);(HERE/'review_queue_12.md').write_text('\n'.join(md),encoding='utf-8')
    print(json.dumps({'splits':splitmeta,'deduplicated':len(duplicate_map),'LLM_selected':{s:len(x) for s,x in selected.items()}}))

if __name__=='__main__':main()
