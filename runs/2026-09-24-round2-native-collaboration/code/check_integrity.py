"""Input leakage and selective-decision boundary checks; no model/API calls."""
import collections
import json
from pathlib import Path
from common import readl,dump
from llm_compare import interpret,call

HERE=Path(__file__).resolve().parent
rows=readl(HERE/'data.jsonl');packed=readl(HERE/'packed.jsonl')
for field in ('group_id',):
    sets={s:{r[field] for r in rows if r['split']==s} for s in ('train','dev','test')}
    assert not sets['train']&sets['dev'] and not sets['train']&sets['test'] and not sets['dev']&sets['test']
by={r['sample_id']:r for r in rows}
assert len(packed)==len(rows)==956 and len(by)==956
for r in packed:
    assert set(r['input'])=={'instruction','history','current_action','env_info'}
    assert r['input']==by[r['sample_id']]['input']
    assert r['label']==by[r['sample_id']]['label']
    if not r['window']['mandatory_fields_overflow']:
        assert r['input']['instruction'] in r['field_text'] and r['input']['current_action'] in r['field_text']
        assert r['window']['field_tokens']<=512
    else:assert r['field_text']==''
    ss={s['span_id']:s for s in r['llm_input']['spans']}
    assert len(ss)==len(r['llm_input']['spans'])
    assert ss['U0']['text']==r['input']['instruction'] and ss['C0']['text']==r['input']['current_action']
    assert set(r['llm_input'])=={'spans','provenance_note'}
    assert all(s['field'] in ('instruction','current_action_untrusted','history_flattened_unverified','env_info') for s in ss.values())

inp={'spans':[{'span_id':'U0','field':'instruction'}]}
def run(decision,status,ref='U0'):
    dims=[{'dimension':n,'applicable':True,'required':True,'status':status if i==0 else 'match','evidence_refs':[ref]} for i,n in enumerate(('operation','object','destination','authorization'))]
    raw={'error_code':None,'payload':{'choices':[{'message':{'content':json.dumps({'decision':decision,'dimensions':dims,'evidence_refs':['U0']})}}]}}
    return interpret(raw,inp,'L_relation')
assert run('safe','mismatch')['prediction']=='unsafe'
assert run('safe','mismatch')['logical_inconsistency'] is True
assert run('safe','unknown')['prediction']=='abstain'
assert run('safe','match','BAD')['error_code']=='INVALID_SPAN_ID'
assert run('safe','match')['prediction']=='safe'
assert run('safe','not_applicable')['error_code']=='OUTPUT_SCHEMA_OR_JSON_ERROR'
if (HERE/'service_balance_blocked.json').exists():
    before=len(readl(HERE/'api_attempts.jsonl'))
    assert call('integrity_circuit_check',{'spans':[]},'L_direct')['error_code']=='SERVICE_BLOCKED_INSUFFICIENT_BALANCE'
    assert len(readl(HERE/'api_attempts.jsonl'))==before
dump(HERE/'integrity_checks.json',{'status':'PASS','rows':len(rows),'group_disjoint':True,'official_input_fields_only':True,'mandatory_text_exact_when_eligible':True,'LLM_U0_C0_exact':True,'same_LLM_input_object_in_both_arms':True,'mechanical_mismatch_unknown_invalid_ID_checks':'PASS','does_not_prove':'semantic evidence correctness, independent gold, generalization'})
print('INTEGRITY_PASS')
