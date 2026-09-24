"""Pure standard-library recomputation shared with the public verifier."""
import collections
import statistics
from common import score,frac,quantile

def key(r):
    return '|'.join(str(r.get(k,'')) for k in ('phase','model','seed','variant','budget','split'))

def state(r):
    return 'abstain' if r['prediction']=='abstain' else 'correct' if r['prediction']==r['label'] else 'wrong'

def summarize(rows):
    out=score(rows)
    times=[r['latency_ms'] for r in rows if r.get('latency_ms') is not None]
    out['latency_ms']={'p50':quantile(times,.5),'p95':quantile(times,.95),'mean':statistics.mean(times) if times else None}
    out['latency_semantics']=rows[0].get('latency_semantics','recorded component inference/request latency') if rows else None
    if rows and 'routed' in rows[0]:
        matrix={a:{b:0 for b in ('correct','wrong','abstain')} for a in ('correct','wrong','abstain')}
        for r in rows:matrix[r['baseline_state']][state(r)]+=1
        routed=[r for r in rows if r['routed']]
        out['routing']={'routed':len(routed),'call_rate':frac(len(routed),len(rows)),
            'routed_teacher_valid_outputs':sum(r.get('routed_teacher_available',r.get('error_code') is None) for r in routed),
            'routed_teacher_unavailable':sum(not r.get('routed_teacher_available',r.get('error_code') is None) for r in routed),
            'matrix_all':matrix,'corrected_errors':matrix['wrong']['correct'],
            'introduced_errors':matrix['correct']['wrong'],
            'correct_to_abstain':matrix['correct']['abstain'],'wrong_to_abstain':matrix['wrong']['abstain'],
            'unrouted_binary_errors':sum(not r['routed'] and r['baseline_state']=='wrong' for r in rows),
            'unrouted_abstentions':sum(not r['routed'] and r['baseline_state']=='abstain' for r in rows),
            'cached_deployment_token_estimate':sum(r.get('input_tokens',0)+r.get('output_tokens',0) for r in routed),
            'routed_sample_ids':[r['sample_id'] for r in routed]}
    if rows and rows[0]['model'] in ('L_direct','L_relation'):
        out['protocol_effect_complete']=all(r.get('error_code') is None for r in rows)
        out['valid_model_outputs']=sum(r.get('error_code') is None for r in rows)
        applicable=sum((r.get('dimension_coverage') or {}).get('applicable',0) for r in rows)
        with_evidence=sum((r.get('dimension_coverage') or {}).get('with_evidence',0) for r in rows)
        attempted=sum(r.get('actual_api_calls',0)>0 for r in rows)
        out['evidence']={'ID_valid_all':frac(sum(r.get('reference_valid') is True for r in rows),len(rows)),
            'ID_valid_attempted':frac(sum(r.get('reference_valid') is True for r in rows),attempted),
            'applicable_dimensions_with_ID':frac(with_evidence,applicable),
            'logical_inconsistencies':sum(r.get('logical_inconsistency') is True for r in rows),
            'semantic_unknown_abstain':sum(r.get('semantic_unknown',False) for r in rows),
            'human_reviewed':0,'semantic_correctness':'NOT_HUMAN_REVIEWED'}
        out['tokens']={'input':sum(r.get('input_tokens',0) for r in rows),'output':sum(r.get('output_tokens',0) for r in rows)}
    return out

def recompute(rows):
    groups=collections.defaultdict(list)
    for r in rows:groups[key(r)].append(r)
    results={k:summarize(rs) for k,rs in sorted(groups.items())}
    aggregates={}
    families=collections.defaultdict(list)
    for k,rs in groups.items():
        r=rs[0]
        if r.get('seed') in (42,43,44) and r['model'] in ('R1','E_field','E_to_L_direct','E_to_L_relation'):
            f='|'.join(str(r.get(n,'')) for n in ('phase','model','variant','budget','split'))
            families[f].append((r['seed'],results[k]))
    for f,items in sorted(families.items()):
        agg={}
        for field in ('F1_covered','macro_F1_covered','coverage','correct_decisions/N_total','TP/N_unsafe_total','FPR_all_safe'):
            vals=[(s,m[field]['value'] if isinstance(m[field],dict) else m[field]) for s,m in sorted(items)]
            xs=[v for _,v in vals if v is not None]
            agg[field]={'seeds':[s for s,_ in vals],'values':[v for _,v in vals],'mean':statistics.mean(xs) if xs else None,'sd':statistics.stdev(xs) if len(xs)>1 else None,'complete_three_seeds':{s for s,_ in vals}=={42,43,44}}
        aggregates[f]=agg
    paired_changes={}
    for split in ('dev','test'):
        arms={arm:{r['sample_id']:r for r in rows if r.get('phase')=='paired' and r['model']==arm and r['split']==split} for arm in ('L_direct','L_relation')}
        if arms['L_direct'] and set(arms['L_direct'])==set(arms['L_relation']):
            matrix={a:{b:0 for b in ('correct','wrong','abstain')} for a in ('correct','wrong','abstain')}
            for sid,d in arms['L_direct'].items():matrix[state(d)][state(arms['L_relation'][sid])]+=1
            valid_ids=[sid for sid in arms['L_direct'] if arms['L_direct'][sid].get('error_code') is None and arms['L_relation'][sid].get('error_code') is None]
            paired_changes[split]={'N':len(arms['L_direct']),'both_arms_valid_N':len(valid_ids),'protocol_effect_complete':len(valid_ids)==len(arms['L_direct']),'direct_to_relation_matrix':matrix,'matrix_note':'includes technical fallbacks; NOT a pure reasoning effect when protocol_effect_complete is false','corrected_errors':matrix['wrong']['correct'],'introduced_errors':matrix['correct']['wrong'],'correct_to_abstain':matrix['correct']['abstain'],'wrong_to_abstain':matrix['wrong']['abstain'],
                'valid_pairs_corrected_errors':sum(state(arms['L_direct'][s])=='wrong' and state(arms['L_relation'][s])=='correct' for s in valid_ids),
                'valid_pairs_introduced_errors':sum(state(arms['L_direct'][s])=='correct' and state(arms['L_relation'][s])=='wrong' for s in valid_ids)}
    return {'results':results,'seed_aggregates':aggregates,'paired_protocol_changes':paired_changes}
