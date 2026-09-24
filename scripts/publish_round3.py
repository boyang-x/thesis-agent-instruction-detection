"""Round-three explicit publication adapter; native text remains local."""
import json,shutil
from datetime import datetime,timezone
from publish_experiment import ROOT,TITLE,safe_copy,dump,lines,scan
from publish_round2 import public_prediction
from verify_round3 import verify
def readl(p):return [json.loads(s) for s in p.read_text(encoding='utf-8').splitlines()]
def export(source,run_id):
    cfg=json.loads((source/'config.json').read_text());assert run_id==cfg['run_id']=='2026-09-24-round3-transfer-ablation'
    dest=ROOT/'runs'/run_id;dest.mkdir(parents=True,exist_ok=True)
    files=['PLAN.md','RUN_STATUS.md','mechanism_note.md','mechanism_ablation.csv','transfer_results.csv','information_control.csv','paired_results.csv','random_summary.csv','routes.jsonl','analysis_index.jsonl','sample_index.jsonl','exclusions.jsonl','duplicates.jsonl','data_manifest.json','config.json','request_config.json','information_selection.json','resource_usage.json','server_status.json','run_state.json','cases.md','case_index.jsonl','GPT_PRO_HANDOFF.md']
    for name in files:safe_copy(source/name,dest/name)
    lines(dest/'predictions.jsonl',[{**public_prediction(p),'input_ref':'analysis_index.jsonl#'+p['sample_id']} for p in readl(source/'predictions.jsonl')])
    lines(dest/'sample_index.jsonl',readl(source/'analysis_index.jsonl'))
    lines(dest/'api_usage.jsonl',[{**{k:v for k,v in r.items() if k not in ['payload','error_body','error_message']},'finish_reason':r.get('payload',{}).get('choices',[{}])[0].get('finish_reason')} for r in readl(source/'api_calls.jsonl')])
    for name in ['prepare.py','transfer_server.py','llm_run.py','compare.py','analyze.py','report.py','make_cases.py','case_notes.json']:
        safe_copy(source/name,dest/'code'/name)
    dump(dest/'publication.json',{'publication_schema':'round3','run_id':run_id,'frozen_public_commit':cfg['frozen_public_commit'],'exported_at':datetime.now(timezone.utc).isoformat(),'native_text':'Full input and response payloads, actual case excerpts retained locally; public source indices and AI paraphrases only.','source_repository':'existing agent-guardrail-research; main.py unchanged','original_pack_parser_rules':'unchanged round2 code at frozen public commit, not replaced by this adapter','new_requests':'2048 output tokens; old800 cohort separate','new_training':False})
    scan(dest);result=verify(dest);state=json.loads((dest/'run_state.json').read_text());res=json.loads((dest/'resource_usage.json').read_text())
    ledger=json.loads((ROOT/'experiments.json').read_text());ledger=[r for r in ledger if r['run_id']!=run_id]+[dict(run_id=run_id,path='runs/'+run_id,state=state,verification=result,exported_at=datetime.now(timezone.utc).isoformat())];dump(ROOT/'experiments.json',ledger)
    (ROOT/'EXPERIMENTS.md').write_text('# 实验记录\n\n| 实验 | 原始/衍生预测记录 | 状态 |\n|---|---:|---|\n'+''.join(f"| [{r['run_id']}]({r['path']}/RUN_STATUS.md) | {r['verification']['prediction_rows']} | {r['state'].get('status','见报告')} |\n" for r in ledger),encoding='utf-8')
    prefix='runs/'+run_id
    status=(source/'RUN_STATUS.md').read_text(encoding='utf-8')
    links=f'\n\n[网页GPT Pro事实包]({prefix}/GPT_PRO_HANDOFF.md) · [旧缓存消融]({prefix}/mechanism_ablation.csv) · [迁移完整表]({prefix}/transfer_results.csv) · [同信息]({prefix}/information_control.csv) · [直接/关系配对]({prefix}/paired_results.csv) · [原始预测]({prefix}/predictions.jsonl) · [案例]({prefix}/cases.md) · [资源]({prefix}/resource_usage.json)\n'
    (ROOT/'CURRENT_STATUS.md').write_text(status+links,encoding='utf-8')
    (ROOT/'GPT_PRO_REVIEW.md').write_text('# GPT Pro审阅入口\n\n'+status+links+'''\n## 本轮重点审阅

1. 比较G_uncertainty与G_overflow、同调用量G_random的增量：S_fit真正纠错/改错、正确转暂缓和未送审错误是否分别报告？不要把溢出恢复当作二分类纠错。
2. 三种子、原三预算、20个随机送审重复是否报全？dev10%是否被误写成测试调用10%？按任务组宏平均与逐条结果是否一致？
3. 关系核对相对直接判断是否有稳定净收益？模型主动暂缓、输入溢出、技术故障是否分开？旧800与新2048不可混成同一配置。响应名/服务指纹见资源记录，别名不能证明权重不可变。
4. 64条同信息对照选择在预测前固定。短输入标签未重新人工验证，不夸大为推理能力单因素因果实验。
5. 检查8例，尤其旧0404中工具能力与模型解释是否一致。公开为AI概述，必要原文摘录本地保留；human_review仍pending，不是人工gold。

本轮实验与网页端写作证据包已交付；用户最新要求不在本地生成中期报告/PPT，由网页GPT Pro依据本事实包生成。无论有无增益，本轮结束。请依据已经生成的真实结果给出论文主张边界及建议，不视审阅建议为自动启动新算法的授权。原始历史运行目录全部保留。
''',encoding='utf-8')
    return dest,result
