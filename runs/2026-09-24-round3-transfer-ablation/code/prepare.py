"""Frozen transfer population; no model-dependent selection and no new hashes."""
import collections,json,re,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
OLD=HERE.with_name('thesis_round2_20260924')
sys.path.insert(0,str(OLD))
from common import readl,writel,dump
def norm(s):return re.sub(r'\s+',' ',s).strip().casefold()
def main():
    assert not (HERE/'data.jsonl').exists()
    train=[r for r in readl(OLD/'data.jsonl') if r['split']=='train']
    tasks={norm(r['input']['instruction']) for r in train};exact_train={json.dumps(r['input'],sort_keys=True) for r in train}
    rows=[];excluded=[];counts={}
    for domain in ['banking','travel']:
        raw=json.loads((HERE.parents[1]/'.cache/thesis-toolsafe-20260924/TS-Bench/agentdojo-traj'/f'{domain}.json').read_text(encoding='utf-8'));counts[domain]=len(raw)
        for i,r in enumerate(raw):
            sid=f'ts_{domain}_{i:04d}'
            reason='controversial_score' if r['score'] not in (0,1) else 'post_step_observation' if re.search(r'(?m)^\s*(?:\(\d+\)\s*)?Observation:',r['current_action']) else None
            if reason:excluded.append({'sample_id':sid,'domain':domain,'source_row':i,'reason':reason});continue
            a=re.search(r'\(2\) Action:\s*([A-Za-z_]\w*)',r['current_action'])
            inp={k:r[k] for k in ['instruction','history','current_action','env_info']}
            rows.append(dict(sample_id=sid,source_file=f'TS-Bench/agentdojo-traj/{domain}.json',source_row=i,domain=domain,interaction_id=r['id-interaction'],segment_id=r['id-segment'],label='unsafe' if r['score']==1 else 'safe',label_source='official_step_score',review_status='pending_human',input=inp,tool_name=a.group(1) if a else None,split='transfer',train_overlap=norm(inp['instruction']) in tasks or json.dumps(inp,sort_keys=True) in exact_train))
    parent=list(range(len(rows)))
    def find(i):
        while i!=parent[i]:parent[i]=parent[parent[i]];i=parent[i]
        return i
    keys={};duplicates=collections.defaultdict(list)
    for i,r in enumerate(rows):
        sig=json.dumps(r['input'],sort_keys=True)
        for key in [('task',norm(r['input']['instruction'])),('trajectory',r['domain'],r['interaction_id']),('exact',sig)]:
            if key in keys:parent[find(i)]=find(keys[key])
            else:keys[key]=i
        duplicates[sig].append(i)
    drop=set();mapping=[]
    for ids in duplicates.values():
        if len({rows[i]['label'] for i in ids})>1:
            for i in ids:drop.add(i);excluded.append({'sample_id':rows[i]['sample_id'],'reason':'exact_input_label_conflict'})
        else:
            for i in ids[1:]:drop.add(i);mapping.append({'sample_id':rows[i]['sample_id'],'canonical_id':rows[ids[0]]['sample_id']})
    roots={root:f'transfer_task_{j:03d}' for j,root in enumerate(sorted({find(i) for i in range(len(rows))}))}
    overlaps={find(i) for i,r in enumerate(rows) if r['train_overlap']}
    final=[]
    for i,r in enumerate(rows):
        r.update(group_id=roots[find(i)],train_overlap=find(i) in overlaps)
        if i not in drop:final.append(r)
    writel(HERE/'data.jsonl',final);writel(HERE/'sample_index.jsonl',[{k:v for k,v in r.items() if k!='input'} for r in final]);writel(HERE/'exclusions.jsonl',excluded);writel(HERE/'duplicates.jsonl',mapping)
    manifest={'upstream_commit':'46358fa424a927a895c6c8322f99032c4eb5155e','raw_rows':counts,'retained_rows':len(final),'excluded_rows':len(excluded),'duplicates_removed':len(mapping),'train_overlap_rows':sum(r['train_overlap'] for r in final),'human_reviewed':0,'selection_before_predictions':True,'domains':{d:{'N':sum(r['domain']==d for r in final),'groups':len({r['group_id'] for r in final if r['domain']==d}),'labels':dict(collections.Counter(r['label'] for r in final if r['domain']==d))} for d in counts}}
    dump(HERE/'data_manifest.json',manifest)
    gates={str(s):json.loads((OLD/f'runs/E_field_seed{s}/status.json').read_text())['gate_thresholds_dev'] for s in [42,43,44]}
    dump(HERE/'config.json',{'run_id':'2026-09-24-round3-transfer-ablation','publication_schema':'round3','frozen_public_commit':'7e2445c6b2e671a5f80b5e1ad2f446d20088fd8a','seeds':[42,43,44],'budgets':[.1,.25,.5],'gate_thresholds':gates,'primary_budget':.1,'primary_budget_disclosure':'chosen before new predictions using old dev budgets; not original preregistration','random_seeds':list(range(20)),'max_tokens_new':2048,'max_tokens_old':800,'short_control_max_N':64,'new_training':False,'R1_transfer_status':'NOT_RUN_no_saved_vectorizer_classifier','planned_main_pairs':len(final)*2})
    (HERE/'PLAN.md').write_text('# 第三轮执行清单\n\n论文：基于语义表征与思维链推理协同的智能体恶意指令检测方法\n\n1. 立即运行旧缓存机制消融：溢出、原不确定性门控、20个固定随机送审重复、全量LLM；三种子三预算。\n2. 固定上游banking/travel合格总体，检查训练任务重叠。复用原pack、三检查点、阈值与提示；新请求统一2048，响应跨种子/门控复用，402即停。\n3. 预测前按领域/任务轮转固定最多64条S_fit；主实验后仅新增直接短输入臂。\n4. 原始预测重算表格；输出8例、完整中期报告、14页PPT内容与3图；更新审阅入口并推送。\n\n不重训、不改提示、不重写main.py、不追加算法；官方标签探索证据，人工审核未完成。\n',encoding='utf-8')
    print(json.dumps(manifest,ensure_ascii=False))
if __name__=='__main__':main()
