"""Explicit public export adapter for round2; retains native text and raw API payloads locally."""
import hashlib
import json
from datetime import datetime,timezone
from pathlib import Path
from publish_experiment import ROOT,TITLE,REPO_URL,safe_copy,dump,lines,scan
from verify_round2 import verify

FILES=['RUN_STATUS.md','midterm_summary.md','midterm_results_insert.md','cases.md','native_baselines.csv','reasoning_collaboration.csv','results.csv','ablation.csv','metrics.json','resource_usage.json','run_state.json','data_manifest.json','config.json','selection.json','window_audit.json','window_summary.json','analysis_contract.json','LABEL_INPUT_AUDIT.md','ROUND2_PLAN.md','integrity_checks.json','environment.json','server_complete.json','prompts_frozen.json','live_selection.json','live_router_status.json','training_curve_data.csv','cost_curve_data.csv','service_balance_blocked.json']
CODE=['common.py','compute.py','collect.py','report.py','prepare.py','legacy_rule.py','train_server.py','llm_compare.py','check_integrity.py','live_score.py','live_router.py','enhance_review.py']

def readl(p):return [json.loads(s) for s in p.read_text(encoding='utf-8').splitlines()]
def sha(s):return hashlib.sha256(s.encode('utf-8')).hexdigest()

def public_prediction(r):
    p=dict(r)
    if p.get('analysis'):
        a=p['analysis'];p['analysis']={k:v for k,v in a.items() if k in ('decision','evidence_refs')}
        if 'dimensions' in a:p['analysis']['dimensions']=[{k:v for k,v in d.items() if k in ('dimension','applicable','required','status','evidence_refs')} for d in a['dimensions']]
        p['analysis']['publication_omission']='Free-text explanations retained locally; source text recovered by index, dimensions/IDs unchanged.'
    return p

def export(source,run_id):
    cfg=json.loads((source/'config.json').read_text(encoding='utf-8'))
    assert run_id==cfg['run_id']=='2026-09-24-round2-native-collaboration'
    dest=ROOT/'runs'/run_id;dest.mkdir(parents=True,exist_ok=True)
    for name in FILES+['calibration_recovery.json','live_router_predictions.jsonl']:safe_copy(source/name,dest/name)
    for name in ('sample_index.jsonl','duplicates.jsonl','exclusions.jsonl'):safe_copy(source/name,dest/name)
    rows=readl(source/'predictions.jsonl');published=[public_prediction(r) for r in rows]
    for a,b in zip(rows,published):assert {k:v for k,v in a.items() if k!='analysis'}=={k:v for k,v in b.items() if k!='analysis'}
    lines(dest/'predictions.jsonl',published)
    lines(dest/'error_samples.jsonl',[r for r in published if r['prediction']!=r['label']])
    lines(dest/'debug_llm_predictions.jsonl',[public_prediction(r) for r in readl(source/'debug_llm_predictions.jsonl')])
    lines(dest/'review_queue_12.jsonl',[{k:v for k,v in r.items() if k!='input'} for r in readl(source/'review_queue_12.jsonl')])
    (dest/'review_queue_12.md').write_text('# 12个重点待审案例\n\n人工审核0条；原生全文仅在用户本地 review_queue_12.md 中。公开来源、标签和具体问题见 review_queue_12.jsonl。样本在本轮预测前固定，问题在审阅原文后具体化；未改变样本或标签。\n',encoding='utf-8')
    requests={r['attempt_id']:r for r in readl(source/'api_attempts.jsonl')}
    usages=[]
    for r in readl(source/'api_calls.jsonl'):
        p={k:v for k,v in r.items() if k not in ('payload','error_body','error_message')}
        req=requests[r['attempt_id']]['request'];p['input_sha256']=sha(req['messages'][-1]['content']);p['system_prompt_sha256']=sha(req['messages'][0]['content'])
        p['response_model']=r.get('payload',{}).get('model');p['finish_reason']=(r.get('payload',{}).get('choices') or [{}])[0].get('finish_reason')
        usages.append(p)
    lines(dest/'api_usage.jsonl',usages)
    for p in (source/'runs').glob('*/*'):
        if p.name in ('status.json','curves.jsonl','train_predictions.jsonl','dev_calibration_predictions.jsonl'):safe_copy(p,dest/'training'/p.parent.name/p.name)
    for name in CODE+['save_calibration.py']:safe_copy(source/name,dest/'code'/name)
    (dest/'code/README.md').write_text('本轮算法快照；复用原仓库 provider 与缓存编码器，未重写 main.py。公开重算使用根目录 scripts/verify_run.py，不需模型。live_router 的 infrastructure.local.json 不公开；其中仅含已有SSH目标和运行命令。\n\n执行后修复：llm_compare 增加 HTTP402 全局熔断（原配对批次未有该保护，185次真实失败完整保留）。不重跑或替换原批次。\n',encoding='utf-8')
    dump(dest/'publication.json',{'publication_schema':'round2','run_id':run_id,'exported_at':datetime.now(timezone.utc).isoformat(),'source_repository':'boyang-x/agent-guardrail-research','source_commit':'f059223210750857e9fb63f42e260ca45b09a779','source_code_state':'new experiment subdirectory, code snapshots included; existing main entry unchanged','prediction_numeric_fields_unchanged':True,'raw_native_artifacts_retained_locally':True,'omissions':['full upstream native text','native API request/response payloads and free-text explanations','credentials and infrastructure coordinates','model weights','unrelated historical material'],'native_input_recovery':'upstream commit in data_manifest + source_file/source_row in sample_index','first_round_preserved':True})
    scan(dest);result=verify(dest)
    state=json.loads((dest/'run_state.json').read_text(encoding='utf-8'))
    resource=json.loads((dest/'resource_usage.json').read_text(encoding='utf-8'));gpu_minutes=resource['gpu']['reserved_device_seconds']/60
    ledger=json.loads((ROOT/'experiments.json').read_text(encoding='utf-8'))
    ledger=[r for r in ledger if r['run_id']!=run_id]+[{'run_id':run_id,'path':f'runs/{run_id}','exported_at':datetime.now(timezone.utc).isoformat(),'state':state,'verification':result}]
    dump(ROOT/'experiments.json',ledger)
    (ROOT/'EXPERIMENTS.md').write_text('# 实验记录\n\n| 实验 | 预测记录（含衍生） | 状态 | 方法优势证明 |\n|---|---:|---|---|\n'+''.join(f"| [{r['run_id']}]({r['path']}/RUN_STATUS.md) | {r['verification']['prediction_rows']} | {r['state'].get('status',r['state'].get('P2','见报告'))} | {r['state'].get('method_advantage_demonstrated',False)} |\n" for r in ledger),encoding='utf-8')
    prefix=f'runs/{run_id}'
    (ROOT/'CURRENT_STATUS.md').write_text(f'''# 当前状态

论文题目：**{TITLE}**。

最新实验：[{run_id}]({prefix}/RUN_STATUS.md)。**P0/P1完成，P2因API余额不足部分阻塞；未证明方法优势。**

- 956条、46个任务组；train/dev/test=657/158/141（32/7/7组），均为本地已暴露探索划分。
- 32条训练拟合通过；TF-IDF与编码器三个种子、head512输入消融均完成。
- test141：规则正确129；编码器seed42/43/44正确118/112/115，均abstain23。完整指标含dev校准见表。
- 两种LLM提示有效配对dev31/32、test2/96；无有效完整测试协议/协同结论。真实router仅验证E、门控和余额熔断路径，成功LLM串联未运行。
- 264/300请求，79成功、185个HTTP402失败；131401输入、18466输出token；单卡GPU墙钟保守计数约{gpu_minutes:.2f}分钟（含校准分数恢复及router的SSH开销）。
- 12个重点案例待人工审核，已审核0；P3/RL/GUI/完整ShieldAgent未运行。第一轮负结果原样保留。

[原生基线]({prefix}/native_baselines.csv) · [推理/协同故障诊断表]({prefix}/reasoning_collaboration.csv) · [案例]({prefix}/cases.md) · [中期回填材料]({prefix}/midterm_results_insert.md) · [原始及衍生预测]({prefix}/predictions.jsonl)

公开重算验证：{result['prediction_rows']}条记录、{result['metric_groups_recomputed']}组指标；9组同门控和128组同输入检查通过。记录数包含阈值变体和缓存级联，不是独立样本数或API次数。
''',encoding='utf-8')
    (ROOT/'GPT_PRO_REVIEW.md').write_text(f'''# GPT Pro 审阅入口

论文题目：**{TITLE}**。

本轮 `{run_id}`。固定上游数据提交 `46358fa424a927a895c6c8322f99032c4eb5155e`；实现原仓库基底 `f059223210750857e9fb63f42e260ca45b09a779`。GitHub本轮固定发布提交见运行目录 PUBLISHED_COMMIT.md 或仓库提交历史（不要把第一轮基准提交当成本轮结果）。

请先读 [当前状态](CURRENT_STATUS.md)、[运行报告]({prefix}/RUN_STATUS.md)、[口径审计]({prefix}/LABEL_INPUT_AUDIT.md)、[中期回填]({prefix}/midterm_results_insert.md)。核查 [原生逐种子表]({prefix}/native_baselines.csv)、[协同诊断表]({prefix}/reasoning_collaboration.csv)、[预测]({prefix}/predictions.jsonl)、[代码]({prefix}/code)、[成本]({prefix}/resource_usage.json)、[案例]({prefix}/cases.md)、[12条审核索引]({prefix}/review_queue_12.jsonl)。

关键实情：956条/46任务组；657/158/141行对应32/7/7组。普通编码器32条拟合通过，主线三种子各8epoch，训练实际可用553条。test141的编码器正确数118/112/115，暂缓均23；规则129正确、8暂缓，简单规则在总分母上仍强。不得只引用seed42 covered F1=1。

P2未完成：同一模型直接/关系提示共尝试256次；含旧开发debug总请求264，成功79，185次因余额不足失败。批处理当时没有HTTP402全局熔断，已补上并保留全部失败。dev31个有效配对结果相同（29正确、2误报，纠错0/改错0），另1对缺失；test仅2个有效配对。缓存级联的“正确变暂缓”多数是服务故障，不能说成关系推理发现未知。三种子、三预算同门控路由记录存在，但**协议收益留待补足，未证明增益**。在线router只有E/门控/故障关闭路径验证，成功LLM串联缺失。

资源：264/300请求；输入131401、输出18466token；单4090墙钟保守计数约{gpu_minutes:.2f}分钟（训练阶段约6.57分钟）。包含冻结检查点的dev校准分数恢复，以及router的SSH开销；没有重训或改门控，校准分数重现阈值差为0。剩余36次额度未消耗；未自行充值或换服务。P3 E_generic/E_relation、RL、GUI、完整ShieldAgent均NOT_RUN，人工审核0/12。

请检查：1）官方步骤标签与授权关系主张能否对齐；2）任务分组是否仍受跨任务模板和当前thought线索影响；3）mandatory溢出使选择性指标偏高的风险；4）field/head单种子对照支持多强结论；5）如何在服务恢复后，沿用冻结样本/提示补足主实验且保留已有故障；6）是否先用12条重点人工审核修正任务定义，而不是立即扩大证据损失训练。给出一个有限预算、可执行的下一步；不要改论文题目或重写主入口。

本轮执行来源与采纳见 [第二轮指令](reviews/2026-09-24-round2-instructions.md) 和 [采纳记录](reviews/2026-09-24-round2-adoption.md)。这些是用户提供并授权执行的材料，不冒称本轮已获GPT Pro认可。第一轮负结果见 runs/2026-09-24-p0-b234/。

仓库：{REPO_URL}
''',encoding='utf-8')
    return dest,result
