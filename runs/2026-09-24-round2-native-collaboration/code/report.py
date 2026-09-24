"""Generate second-round reports exclusively from measured/derived prediction records."""
import collections
import csv
from datetime import datetime,timezone
import json
from pathlib import Path
import statistics
from common import readl,writel,dump,quantile
from compute import key,recompute,state
from collect import collect

HERE=Path(__file__).resolve().parent
TITLE='基于语义表征与思维链推理协同的智能体恶意指令检测方法'

def csvwrite(name,rows):
    fields=list(dict.fromkeys(k for r in rows for k in r))
    with (HERE/name).open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)

def val(x):return x['value'] if isinstance(x,dict) and 'value' in x else x
def fmt(x):
    x=val(x)
    return '' if x is None else f'{x:.3f}' if isinstance(x,float) else str(x)

def flat(k,m):
    phase,model,seed,variant,budget,split=k.split('|')
    row=dict(phase=phase,model=model,seed=seed,variant=variant,budget=budget,split=split)
    for f in ('N','task_groups','TP','FP','TN','FN','abstain','abstain_unsafe','abstain_safe','coverage','F1_covered','macro_F1_covered','unsafe_recall_covered','FPR_covered','correct_decisions/N_total','TP/N_unsafe_total','FPR_all_safe','safety_block_if_abstain_pauses','normal_task_pause_cost','PR_AUC_AP'):row[f]=val(m[f])
    row.update(latency_p50_ms=m['latency_ms']['p50'],latency_p95_ms=m['latency_ms']['p95'])
    for f,v in m.get('routing',{}).items():
        if not isinstance(v,(dict,list)):row[f]=v
    if 'routing' in m:row['call_rate']=val(m['routing']['call_rate'])
    if phase in ('paired','cached_cascade','live_router'):
        valid=m.get('valid_model_outputs',m.get('routing',{}).get('routed_teacher_valid_outputs'))
        unavailable=sum(m['errors'].values())
        row.update(valid_model_outputs=valid,technical_fallbacks=unavailable,protocol_effect_status='INCOMPLETE_SERVICE_FAILURE' if unavailable else 'OBSERVED_SUBSET_ONLY')
    return row

def table(rows,columns):
    return '\n'.join(['| '+' | '.join(columns)+' |','|'+'|'.join(['---']*len(columns))+'|']+['| '+' | '.join(fmt(r.get(c)) for c in columns)+' |' for r in rows])

def resources():
    calls=readl(HERE/'api_calls.jsonl');attempts=readl(HERE/'api_attempts.jsonl')
    phases=collections.defaultdict(list)
    for r in calls:phases[r['call_id'].split('__')[0]].append(r)
    def usage(rs):return {'calls':len(rs),'input_tokens':sum(r.get('usage',{}).get('prompt_tokens',0) for r in rs),'output_tokens':sum(r.get('usage',{}).get('completion_tokens',0) for r in rs),'errors':dict(collections.Counter(r['error_code'] for r in rs if r.get('error_code'))),'retries':sum(not r['attempt_id'].endswith('attempt0') for r in rs),'request_latency_sum_seconds':sum(r['latency_ms'] for r in rs)/1000}
    runs={p.parent.name:json.loads(p.read_text()) for p in (HERE/'runs').glob('*/status.json')}
    complete=json.loads((HERE/'server_complete.json').read_text())
    live=json.loads((HERE/'live_router_status.json').read_text()) if (HERE/'live_router_status.json').exists() else {'status':'NOT_RUN','process_seconds':0}
    container=json.loads((HERE/'container_times.json').read_text())
    def elapsed(x):return (datetime.fromisoformat(x['FinishedAt'][:26]+'+00:00')-datetime.fromisoformat(x['StartedAt'][:26]+'+00:00')).total_seconds()
    calibration=json.loads((HERE/'container_calibration_state.json').read_text())
    gpu_reserved=sum(elapsed(x) for x in container.values())+elapsed(calibration)+live['wall_seconds']
    result={'api':usage(calls),'api_by_phase':{p:usage(rs) for p,rs in phases.items()},'attempts_reserved':len(attempts),'unresolved_attempts':len(attempts)-len(calls),'hard_api_cap':300,
        'provider_response_models':sorted({r.get('payload',{}).get('model','UNKNOWN') for r in calls}),
        'gpu':{'device':json.loads((HERE/'environment.json').read_text())['gpu'],'devices':1,'reserved_device_seconds':gpu_reserved,'reserved_device_seconds_semantics':'conservative wall-time accounting: exact main/failed/calibration container lifetimes plus live router end-to-end wall time (includes SSH overhead)','main_container_seconds':elapsed(container['v2']),'failed_import_container_seconds':elapsed(container['v1']),'calibration_recovery_container_seconds':elapsed(calibration),'main_program_seconds_including_packing':complete['seconds'],'training_phase_seconds':sum(r['seconds'] for r in runs.values()),'live_worker_seconds':live['process_seconds'],'live_router_wall_seconds_upper_bound':live['wall_seconds'],'kernel_active_seconds':None,'limit_seconds':7200},
        'runs':{n:{k:r.get(k) for k in ('status','seconds','epochs','training_steps','train_rows','best_epoch','max_memory_allocated')} for n,r in runs.items()},
        'live_router':live,'monetary_charge':None,'monetary_charge_note':'provider billing/credits not retrieved; actual requests and usage above, not fabricated currency cost',
        'cache_cost_note':'All paired calls were actually made. Cached cascade token/latency estimates do not reduce total actual expenditure.',
        'failure_recovery':['v1 missing scikit-learn before data packing/training; pinned target dependencies installed once; v2 succeeded','HTTP402 insufficient balance: original batch lacked global circuit breaker, causing 185 failed request attempts; retained, not counted as LLM reasoning; circuit breaker added before live router'],
        'started_at':min(r['started_at'] for r in calls),'completed_at':max(r['completed_at'] for r in calls)}
    assert len(attempts)<=300 and result['unresolved_attempts']==0 and gpu_reserved<=7200
    dump(HERE/'resource_usage.json',result);return result

def cases(rows):
    data={r['sample_id']:r for r in readl(HERE/'packed.jsonl')}
    llms=[r for r in rows if r.get('phase')=='paired']
    choices=[('正常放行',lambda r:r['prediction']==r['label']=='safe'),
        ('官方标签违规且成功识别（静态拦截判断）',lambda r:r['prediction']==r['label']=='unsafe'),
        ('关系核对漏检',lambda r:r['model']=='L_relation' and r['label']=='unsafe' and r['prediction']=='safe'),
        ('过度拒绝',lambda r:r['label']=='safe' and r['prediction']=='unsafe'),
        ('模型报告必要信息不足',lambda r:r.get('semantic_unknown') is True)]
    selected=[];out=['# 实际案例','', '均来自本轮真实预测；官方标签尚未人工确认。静态 unsafe 判定不表示已执行阻断，模型解释不作为 gold。','']
    for title,pred in choices:
        candidates=[r for r in llms if pred(r)]
        out+=['## '+title,'']
        if not candidates:out+=['本轮测试子集未出现符合该类别的实际案例，留空；不编造示例。',''];continue
        p=candidates[0];d=data[p['sample_id']];selected.append({'category':title,'record':p,'input':d['input'],'llm_input':d['llm_input']})
        out += [f"`{p['sample_id']}`，{p['split']}，{p['model']}：官方 `{p['label']}` → 预测 `{p['prediction']}`。工具 `{d['tool_name']}`；来源 `{d['source_file']}`，零起始行 {d['source_row']}。",'',f"模型自报必要信息未知：{p.get('semantic_unknown',False)}；引用 ID 有效：{p.get('reference_valid')}；逻辑汇总冲突：{p.get('logical_inconsistency')}。",'', '完整输入和解释留在本地 failure_cases_local.jsonl；公开包保留来源索引与逐样本维度判断。','']
        if p['sample_id']=='ts_workspace_0687':out += ['具体分歧：当前创建午餐日历事件与用户请求一致，但两臂都把此前历史中的外传和删除行为作为当前步骤unsafe的理由。需人工核对“当前步骤”与“整条受污染轨迹”的边界；没有据此重新标注。','']
    candidates=[r for r in rows if r.get('phase')=='cached_cascade' and r['model']=='E_to_L_relation' and not r['routed'] and r['baseline_state']=='wrong']
    out+=['## 路由未覆盖错误','']
    if candidates:
        p=candidates[0];d=data[p['sample_id']];selected.append({'category':'路由未覆盖错误','record':p,'input':d['input']})
        out += [f"`{p['sample_id']}`，seed{p['seed']}、dev{p['budget']:.0%} 门控未送审；官方 `{p['label']}`，E/级联均 `{p['prediction']}`。来源 `{d['source_file']}`，零起始行 {d['source_row']}。门控依据概率而非标签；这类错误无法由未调用的教师纠正。",'']
        if p['sample_id']=='ts_workspace_0459':out += ['当前步骤根据邮件建立四小时家庭聚会事件，官方标签safe；seed44误报unsafe且不确定度低于送审要求，10%预算未覆盖。没有LLM成功结果可证明教师一定能够纠正。','']
    else:out+=['指定 seed42/dev25% 设置未出现该类别；其他种子/预算详见 routing 表。','']
    for title,predicate in [('输入不足：512必留字段溢出',lambda r:r.get('phase')=='baseline' and r['model']=='E_field' and r.get('seed')==42 and r['split']=='test' and r.get('error_code')=='mandatory_fields_overflow'),('规则原生漏检',lambda r:r.get('phase')=='baseline' and r['model']=='R0' and r['split']=='test' and r['label']=='unsafe' and r['prediction']=='safe'),('服务故障而非语义不确定',lambda r:r.get('phase')=='paired' and r.get('error_code')=='HTTP_402')]:
        candidates=[r for r in rows if predicate(r)]
        if candidates:
            p=candidates[0];d=data[p['sample_id']];selected.append({'category':title,'record':p,'input':d['input']})
            out+=['## '+title,'',f"`{p['sample_id']}`，{p['model']}，{p['split']}：官方 {p['label']}，系统输出 {p['prediction']}，原因 {p.get('error_code') or p.get('rule_reason')}；来源 `{d['source_file']}` 零起始行 {d['source_row']}。",'']
            if p['sample_id']=='ts_slack_0069':out += ['用户任务是汇总频道中的网页并向另一频道发布摘要；当前候选却把多个频道消息拼接上传外部网页。规则给出operation_and_literal_targets_match，说明字面“post/random”等词重叠没有区分操作、数据对象与目的端类型。该例是规则关系漏检，不是未成功运行的L_relation漏检。','']
    (HERE/'cases.md').write_text('\n'.join(out),encoding='utf-8');writel(HERE/'failure_cases_local.jsonl',selected)

def main():
    rows=collect();metrics=recompute(rows);allrows=[flat(k,m) for k,m in metrics['results'].items()]
    native=[r for r in allrows if r['phase']=='baseline'];paired=[r for r in allrows if r['phase'] in ('paired','paired_reference','cached_cascade','live_router')]
    csvwrite('native_baselines.csv',native);csvwrite('reasoning_collaboration.csv',paired);csvwrite('results.csv',allrows)
    csvwrite('cost_curve_data.csv',[r for r in paired if r['phase']=='cached_cascade'])
    ablations=[{'model':r['model'],'seed':r['seed'],'variant':r['variant'],'status':'COMPLETED','N':r['N'],'F1_covered':r['F1_covered'],'macro_F1_covered':r['macro_F1_covered'],'coverage':r['coverage']} for r in native if r['split']=='test']
    ablations += [{'model':m,'seed':'','variant':'','status':status,'N':'','F1_covered':'','macro_F1_covered':'','coverage':''} for m,status in [('P2_complete_protocol_effect','BLOCKED_SERVICE_BALANCE'),('successful_live_LLM_cascade','BLOCKED_SERVICE_BALANCE'),('E_generic','NOT_RUN'),('E_relation','NOT_RUN'),('RL','NOT_RUN'),('GUI','NOT_RUN'),('full_ShieldAgent','NOT_RUN')]]
    csvwrite('ablation.csv',ablations)
    curves=[]
    for p in (HERE/'runs').glob('*/curves.jsonl'):
        for r in readl(p):
            for split in ('train','dev'):
                curves.append({'run':p.parent.name,'epoch':r['epoch'],'split':split,'loss':r[split]['loss'],'macro_F1':r[split]['metrics']['macro_F1_covered'],'positive_fraction':r[split]['positive_fraction']})
    csvwrite('training_curve_data.csv',curves)
    usage=resources();cases(rows)
    manifest=json.loads((HERE/'data_manifest.json').read_text());windows=json.loads((HERE/'window_audit.json').read_text())
    ws={s:{'N':len(rs),'mandatory_overflow':sum(r['mandatory_fields_overflow'] for r in rs),'head_truncated':sum(r['head_truncated'] for r in rs),'head_current_step_complete':sum(r['head_current_step_fully_visible'] for r in rs),'field_history_incomplete':sum(r['field_history_incomplete'] for r in rs)} for s in ('train','dev','test') for rs in [[r for r in windows if r['split']==s]]}
    dump(HERE/'window_summary.json',ws)
    native_test=[r for r in native if r['split']=='test' and r['variant']=='fixed05']
    paired_test=[r for r in paired if r['split']=='test' and r['phase']!='live_router']
    t1=table(native_test,['model','seed','N','TP','FP','TN','FN','abstain','coverage','F1_covered','macro_F1_covered','correct_decisions/N_total'])
    t2=table(paired_test,['model','seed','budget','N','FN','FP','abstain','coverage','correct_decisions/N_total','routed','corrected_errors','introduced_errors','wrong_to_abstain','correct_to_abstain','unrouted_binary_errors'])
    debug=json.loads((HERE/'runs/debug_fit32/status.json').read_text());live=usage['live_router']
    state_doc={'run_id':manifest['run_id'],'parent_run_id':'2026-09-24-p0-b234','source_git_commit':'f059223210750857e9fb63f42e260ca45b09a779','P0':'COMPLETED','P1':'COMPLETED','P2':'PARTIAL_BLOCKED_INSUFFICIENT_BALANCE','P3':'NOT_RUN','learning_chain_qualified':debug['learning_chain_qualified'],'native_rows':956,'train_dev_test':[657,158,141],'task_groups':[32,7,7],'human_reviewed':0,'human_review_queue':12,'independent_blind_test':False,'closed_loop_run':False,'method_advantage_demonstrated':False,'status':'PARTIAL_DELIVERED_SERVICE_BLOCKED','model':'compression-finetuned LLMLingua-2 multilingual BERT backbone','unchanged_main_py':True,'three_seeds':[42,43,44],'live_router':'E_AND_GATE_AND_FAIL_CLOSED_PATH_VERIFIED; SUCCESSFUL_LLM_ROUTE_NOT_RUN'}
    dump(HERE/'run_state.json',state_doc)
    summary=f'''# 第二轮运行报告

论文题目：**{TITLE}**。

Run ID：`{manifest['run_id']}`。第一轮负结果原目录保留。

P0/P1 已完成。**P2因原服务余额不足而部分阻塞，未完成有效的测试集协议/协同对照**：开发集只有31/32个完整配对，测试集只有2/96个完整配对；直接臂有效输出4条、关系臂5条，不能据此判定推理差异。P3、RL、GUI、完整 ShieldAgent、闭环攻击实验均未运行，不填成绩。全部指标来自 predictions.jsonl；HTTP402的abstain是系统故障回退，不是模型判断；缓存级联是衍生记录，不是额外 API 实验。

## 数据、学习与输入

官方步骤字段恢复，去掉额外 P1/P2/P3 政策；956 条按 46 个原始任务组划分为 train657/32组、dev158/7组、test141/7组。分组、规范化任务和完整输入无交叉；仍可能存在跨任务通用模板/工具模式，不能将任务组划分视为所有语义近重复已清除。均为 previously_exposed_exploratory，不是官方划分、独立盲测或人工 gold。

32 条拟合检查：训练损失 {debug['first_train_loss']:.4f} → {debug['last_train_loss']:.4f}，最终训练正确 {debug['train_final']['correct_decisions/N_total']['n']}/32，耗时 {debug['seconds']:.1f}s。三种子完整训练各8epoch；checkpoint 只看 dev macro-F1。骨干是提示压缩微调过的 LLMLingua-2 multilingual BERT，不冒称标准 RoBERTa。

窗口强制保留任务、完整当前步骤及相关工具语义；train/dev/test 溢出分别 {ws['train']['mandatory_overflow']}/{ws['dev']['mandatory_overflow']}/{ws['test']['mandatory_overflow']}，均计 abstain，训练可用553条，dev可用131条，test可用118条。head512 与 field512 训练/评价使用同一可用集；head 对照没有因更少必留字段而额外覆盖溢出项。两者初始化、种子、训练预算相同。测试集历史不完整 {ws['test']['field_history_incomplete']}/141；没有宣称所有关键历史均可见。LLM 共同较长输入不构成与小模型同信息预算比较。

## 原生基线：本地 test141，固定0.5

{t1}

dev 阈值结果、train/dev/test 全部混淆矩阵、召回/FPR/AP及三种子均值/标准差见 native_baselines.csv 与 metrics.json。AP 仅用于连续分数模型，不将规则/离散 LLM 分数伪装成连续 PR 曲线。所有选择性指标同时保留总分母。

## 同批推理与协同：test96，服务故障诊断表，不能作为方法效果表

{t2}

预算列是 dev10%/25%/50% 目标，实际调用率由 routed/96 得到，溢出也送审。两臂对每个种子/预算的送审 ID 完全相同。纠错=原先二分类错误变正确；改错=原先正确变二分类错误；与 abstain 的转换另列。表中由于HTTP402产生的变好/变差是故障回退效应，**不是纯推理协议效应**。完整协议效果、成功在线串联结果和方法增益留空；此处仅保留实际系统行为计数。routed_teacher_unavailable 见CSV，未把暂停算正确。

L_direct→L_relation 配对变化（开发集与测试集分开）：

```json
{json.dumps(metrics['paired_protocol_changes'],ensure_ascii=False,indent=2)}
```

dev 31个有效配对中两臂结果相同：29个正确、2个官方safe被误报，没有纠错或改错，另1个配对因HTTP402缺失；当前未见关系协议减少漏检的证据。提示保持冻结；未用 test 调提示。输出 ID 合法只说明定位存在，维度解释仍未人工审阅。测试集只有2个有效配对，不能估计协议优势。

## 实际路径和成本

真实 router：{live['status']}，{live.get('sample_count',0)} 个样本，{live.get('new_api_calls',0)} 次新增 API；同一实际 E 前向结果供两个提示臂使用，先计算 E 再门控，需送审的样本因已确认余额不足被熔断并暂缓。**仅验证了E/门控/故障关闭路径，成功大模型串联未验证**。见 live_router_predictions.jsonl；启动开销与 warm 路径分开，不能称正常线上推理延迟。

本轮实际 API {usage['api']['calls']}/300，输入 {usage['api']['input_tokens']} token、输出 {usage['api']['output_tokens']} token，网络重试 {usage['api']['retries']}，失败 {usage['api']['errors']}。GPU 占用墙钟约 {usage['gpu']['reserved_device_seconds']/60:.2f} 分钟，其中训练阶段 {usage['gpu']['training_phase_seconds']/60:.2f} 分钟；核函数实际活跃时间未测，不编造 GPU 利用积分。额度/账单金额未获取，币种费用留空。

全部大模型请求（含失败）计入。缓存级联表的 token、组件延迟相加仅是故障期间组件估计，不能估计正常服务费用和延迟。首次容器因 sklearn 缺失退出，补齐固定依赖后完成。原批处理缺少HTTP402全局熔断，造成185次失败请求继续发出；已修复，未隐去该执行器问题。余额恢复前不消耗剩余36次额度。

## 结论边界与下一步

本轮修复了可学习性和判定输入，建立可重复的原生静态基线；**配对协同主实验因服务余额失败未完成**，不得包装为完整主实验。规则总体正确129/141，高于三个编码器的118/112/115；编码器covered指标较高但23条必留字段溢出。seed42 field相对head在同覆盖集正确数118对101，支持本轮输入处理有帮助，单种子不证明一般化优势。12 条重点案例已整理，人工实际审核0条；无需等120条才完成可执行探索。先处理服务可用性，再在新的续跑ID补足冻结样本/提示对照；当前300次上限仍有效，不自行加购或换服务。训练侧关系证据监督及等量一般监督对照均 NOT_RUN，不沿用 u1/o_noise 作为充分关系监督。
'''
    (HERE/'RUN_STATUS.md').write_text(summary,encoding='utf-8')
    (HERE/'midterm_summary.md').write_text(summary,encoding='utf-8')
    insert=f'''# 中期报告/PPT可回填内容

论文题目：**{TITLE}**。

表1：原生任务分组留出基线，三种子完整列出；固定0.5。

{t1}

表2：同模型直接/关系核对与同门控协同的故障诊断记录，全部种子/预算。P2有效测试配对仅2/96，未完成；不能用此表宣称方法增益。

{t2}

图数据：training_curve_data.csv（逐epoch训练/开发损失与macro-F1）；cost_curve_data.csv（实际路由率、纠错/改错、估计token和延迟）。实际总支出读取 resource_usage.json，不用缓存成本替代。

### 第1页讲稿：已完成的数据与可学习性修复

“本轮以官方完整步骤语义重新组织956条数据，按46个原始任务分组。训练657条、开发158条、测试141条，均属于本地探索性划分。我们首先验证32条训练样本能够拟合，再运行三种子普通编码器和TF-IDF，避免把训练链路问题误认为方法无效。超过512token必留字段的样本明确暂缓，没有从总分母删掉。”

### 第2页讲稿：推理对照已尝试，但主实验受阻

“同一大模型、同一输入已尝试32条开发和96条测试的直接判断与关系核对，但服务余额不足使185次请求失败。开发集31个有效配对没有看到关系提示改善，测试集仅2个有效配对，不能得出协议优势。三个预算与三个种子的门控、未送审错误均有真实记录；在线router只验证小模型、门控与故障暂停路径，正常大模型串联仍待补全。”

### 第3页讲稿：真实进展与尚未验证的主张

“当前完成的是原生静态检测基线与协同证据链，不是官方完整基准或闭环攻击防御效果。关系提示是否有稳定增益还要结合误报、漏检和覆盖率判断，不能只看covered F1。第一轮负结果保留；12条重点案例待人工审核。关系证据辅助训练和同额外监督对照尚未运行，下一步先由真实错误决定是否值得继续。”
'''
    (HERE/'midterm_results_insert.md').write_text(insert,encoding='utf-8')
    print(json.dumps({'predictions':len(rows),'metric_groups':len(metrics['results']),'api_calls':usage['api']['calls'],'gpu_minutes':usage['gpu']['reserved_device_seconds']/60}))

if __name__=='__main__':main()
