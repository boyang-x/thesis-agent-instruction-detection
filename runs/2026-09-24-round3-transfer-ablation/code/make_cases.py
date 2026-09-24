"""Post-hoc illustrative cases only; no labels/prompts changed from this review."""
import collections,json,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;OLD=HERE.with_name('thesis_round2_20260924')
sys.path.insert(0,str(OLD))
from common import readl,dump,writel
def select():
    packed={r['sample_id']:r for r in readl(OLD/'packed.jsonl')+readl(HERE/'packed.jsonl')};preds=readl(HERE/'predictions.jsonl');by=collections.defaultdict(dict)
    for p in preds:by[p['model']][p['sample_id']]=p
    idx=readl(HERE/'analysis_index.jsonl');gates=json.loads((HERE/'config.json').read_text())['gate_thresholds']
    def sent(sid,s=42):
        e=by[f'E_field_seed{s}'][sid];return e['error_code']=='mandatory_fields_overflow' or abs(e['unsafe_score']-.5)<=gates[str(s)]['0.1']
    new=[r for r in idx if r['cohort']=='transfer_2048'];chosen=[('旧工具语义误推断','ts_workspace_0404',42)]
    def pick(title,condition,seed=42):
        for r in new:
            sid=r['sample_id'];e=by[f'E_field_seed{seed}'][sid];d=by['L_direct'][sid];l=by['L_relation'][sid]
            if sid not in [c[1] for c in chosen] and condition(r,e,d,l):chosen.append((title,sid,seed));return
        raise ValueError('case category unavailable: '+title)
    pick('输入溢出后的恢复',lambda r,e,d,l:r['mandatory_fields_overflow'] and d['prediction']==r['label'])
    pick('被送审的真正二分类纠错',lambda r,e,d,l:not r['mandatory_fields_overflow'] and sent(r['sample_id']) and e['prediction']!=r['label'] and d['prediction']==r['label'])
    pick('复核把正确判断改错',lambda r,e,d,l:not r['mandatory_fields_overflow'] and sent(r['sample_id']) and e['prediction']==r['label'] and d['prediction'] in ['safe','unsafe'] and d['prediction']!=r['label'])
    pick('高置信度错误未送审',lambda r,e,d,l:not r['mandatory_fields_overflow'] and not sent(r['sample_id']) and e['prediction']!=r['label'])
    pick('关系臂纠正直接臂',lambda r,e,d,l:d['prediction']!=r['label'] and l['prediction']==r['label'])
    pick('关系臂主动暂缓',lambda r,e,d,l:l['prediction']=='abstain' and l.get('error_code') is None)
    pick('新增领域两臂共同失败',lambda r,e,d,l:r['domain']=='travel' and d['prediction']!=r['label'] and l['prediction']!=r['label'])
    records=[]
    for title,sid,s in chosen:
        r=packed[sid];d=by['L_direct'][sid];l=by['L_relation'][sid];e=by[f'E_field_seed{s}'][sid]
        refs=set(d.get('analysis',{}).get('evidence_refs',[])+l.get('analysis',{}).get('evidence_refs',[]))
        for dim in l.get('analysis',{}).get('dimensions',[]):refs.update(dim.get('evidence_refs',[]))
        relevant=[span for span in r['llm_input']['spans'] if span['span_id'] in refs or span['field']=='env_info' and span['text'].startswith((r['tool_name'] or '')+':')]
        records.append({'category':title,'sample_id':sid,'domain':r['domain'],'source_file':r['source_file'],'source_row':r['source_row'],'official_label':r['label'],'reviewer':'AI','human_review':'pending','selection':'post-hoc explanation only; no prompt/label updates','seed':s,'routed_primary':sent(sid,s),'gate_reason':'mandatory_fields_overflow' if r['window']['mandatory_fields_overflow'] else 'uncertainty_threshold' if sent(sid,s) else 'outside_uncertainty_threshold','unsafe_probability':e.get('unsafe_score'),'gate_threshold':gates[str(s)]['0.1'],'E':e['prediction'],'L_direct':d['prediction'],'L_relation':l['prediction'],'direct_reason':d.get('analysis',{}).get('short_justification'),'relation_reason':l.get('analysis',{}).get('short_justification'),'input':r['input'],'relevant_spans':relevant,'tool_name':r['tool_name'],'E_visible_text':r['field_text']})
    writel(HERE/'case_selection.local.jsonl',records)
    print(json.dumps([{k:r[k] for k in ['category','sample_id','official_label','E','L_direct','L_relation','gate_reason','direct_reason','relation_reason']} for r in records],ensure_ascii=False,indent=2))
def render():
    rows=readl(HERE/'case_selection.local.jsonl');notes=json.loads((HERE/'case_notes.json').read_text(encoding='utf-8'))
    local=['# 八个审核案例：必要原文摘录','', 'Reviewer=AI；人工审核pending。官方标签不更改。事后案例用于解释，不参与选择实验总体或调提示。','']
    public=['# 八个可读实验案例','', '以下为AI来源与语义初审概述，human_review=pending，标签仍为官方标签。必要原文、当前工具参数、工具说明和历史摘录保存在用户本地cases.local.md；公开包不重发完整第三方轨迹。','']
    indices=[]
    for i,r in enumerate(rows,1):
        sid=r['sample_id'];n=notes[sid];summary=f"官方标签 **{r['official_label']}**；E(seed{r['seed']})={r['E']}，direct={r['L_direct']}，relation={r['L_relation']}。主门控：{r['gate_reason']}；p_unsafe={r['unsafe_probability']}，|p−0.5|阈值={r['gate_threshold']}。"
        heading=f"## {i}. {r['category']}：{sid}"
        content=[heading,'',summary,'','任务与动作（AI概述）：'+n['scenario'],'','解释与边界（AI初审）：'+n['assessment'],'',f"来源：固定上游46358fa424a927a895c6c8322f99032c4eb5155e，{r['source_file']}，0-based row {r['source_row']}。",'']
        public+=content;local+=content+['### 用户任务原文','',r['input']['instruction'],'','### 当前步骤原文（含工具与参数）','',r['input']['current_action'],'','### 相关工具语义与必要历史原文','']
        for span in r['relevant_spans']:
            if span['field'] in ['instruction','current_action_untrusted']:continue
            local += [f"**{span['span_id']} / {span['field']}**",'',span['text'],'']
        local+=['### 完整先前历史（本地审核补充；不替代上述模型引用范围）','',r['input']['history'],'','### 模型实际简短解释','',f"Direct: {r['direct_reason']}",'',f"Relation: {r['relation_reason']}",'']
        indices.append({k:v for k,v in r.items() if k not in ['input','relevant_spans','E_visible_text','direct_reason','relation_reason']}|{'AI_paraphrase':n})
    (HERE/'cases.md').write_text('\n'.join(public),encoding='utf-8');(HERE/'cases.local.md').write_text('\n'.join(local),encoding='utf-8');writel(HERE/'case_index.jsonl',indices)
if __name__=='__main__':render() if len(sys.argv)>1 and sys.argv[1]=='render' else select()
