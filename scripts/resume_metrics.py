import collections
from round2_math import key,state

def reason(r):
    if r['prediction']!='abstain':return None
    e=r.get('error_code')
    if e in ('mandatory_fields_overflow','LLM_MANDATORY_OVERFLOW'):return 'input_overflow'
    if r['model']=='R0' and e not in ('HTTP_402',):return 'rule_abstain'
    if e:return 'technical_failure'
    return 'model_abstain'

def extended(rows):
    groups=collections.defaultdict(list)
    for r in rows:groups[key(r)].append(r)
    out={}
    for k,rs in groups.items():
        counts=collections.Counter(reason(r) for r in rs if r['prediction']=='abstain')
        v={'abstention_reasons':dict(counts),'raw_model_abstain':sum(r.get('raw_decision')=='abstain' for r in rs),'mechanically_paused_despite_raw_binary':sum(r['prediction']=='abstain' and r.get('raw_decision') in ('safe','unsafe') and not r.get('error_code') for r in rs)}
        if 'routed' in rs[0]:
            v['input_overflow_sent']=sum(r.get('baseline_input_overflow',False) and r['routed'] for r in rs)
            v['input_overflow_resolved_correct']=sum(r.get('baseline_input_overflow',False) and r['prediction']==r['label'] for r in rs)
            v['baseline_abstain_to_correct']=sum(r['baseline_state']=='abstain' and state(r)=='correct' for r in rs)
            v['baseline_abstain_to_wrong']=sum(r['baseline_state']=='abstain' and state(r)=='wrong' for r in rs)
        out[k]=v
    return out
