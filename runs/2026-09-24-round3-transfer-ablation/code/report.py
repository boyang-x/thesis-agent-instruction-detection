"""Produce a factual handoff for web GPT Pro; no report or PPT authored here."""
import collections,csv,json,statistics
from pathlib import Path
from compare import readl,csvwrite
HERE=Path(__file__).resolve().parent;TITLE='基于语义表征与思维链推理协同的智能体恶意指令检测方法'
def loadcsv(n):return list(csv.DictReader((HERE/n).open(encoding='utf-8')))
def pct(x):return f'{100*float(x):.1f}%'
def table(rs,cols):
    return '| '+' | '.join(title for k,title in cols)+' |\n|'+ '|'.join('---' for _ in cols)+'|\n'+''.join('| '+' | '.join(str(r[k]) for k,title in cols)+' |\n' for r in rs)
def main():
    old=loadcsv('mechanism_ablation.csv');new=loadcsv('transfer_results.csv');info=loadcsv('information_control.csv');randoms=loadcsv('random_summary.csv');resource=json.loads((HERE/'resource_usage.json').read_text());index=readl(HERE/'analysis_index.jsonl');ps=readl(HERE/'predictions.jsonl');cfg=json.loads((HERE/'config.json').read_text())
    assert len([p for p in ps if p.get('phase')=='main'])==528
    by=collections.defaultdict(dict)
    for p in ps:by[p['model']][p['sample_id']]=p
    pairs=[]
    for cohort in ['old_test_800','transfer_2048']:
        for domain in (['combined'] if cohort.startswith('old') else ['combined','banking','travel']):
            for view in ['all','S_fit','S_overflow']:
                rs=[r for r in index if r['cohort']==cohort and (domain=='combined' or r['domain']==domain) and (view=='all' or r['mandatory_fields_overflow']==(view=='S_overflow'))]
                c=collections.Counter()
                for r in rs:
                    sid=r['sample_id'];d=by['L_direct'][sid];l=by['L_relation'][sid];y=r['label']
                    c['direct_correct']+=d['prediction']==y;c['relation_correct']+=l['prediction']==y
                    c['binary_corrected']+=d['prediction'] in ['safe','unsafe'] and d['prediction']!=y and l['prediction']==y
                    c['binary_introduced']+=d['prediction']==y and l['prediction'] in ['safe','unsafe'] and l['prediction']!=y
                    c['correct_to_abstain']+=d['prediction']==y and l['prediction']=='abstain';c['wrong_to_abstain']+=d['prediction'] in ['safe','unsafe'] and d['prediction']!=y and l['prediction']=='abstain'
                    c['abstain_to_correct']+=d['prediction']=='abstain' and l['prediction']==y
                    c['direct_abstain']+=d['prediction']=='abstain';c['relation_abstain']+=l['prediction']=='abstain'
                    c['relation_raw_effective_disagreement']+=bool(l.get('raw_decision')) and l['raw_decision']!=l['prediction']
                pairs.append(dict(cohort=cohort,domain=domain,view=view,N=len(rs),**{k:c[k] for k in ['direct_correct','relation_correct','binary_corrected','binary_introduced','correct_to_abstain','wrong_to_abstain','abstain_to_correct','direct_abstain','relation_abstain','relation_raw_effective_disagreement']}))
    csvwrite(HERE/'paired_results.csv',pairs)
    def primary(rows,domain='combined'):
        return [r for r in rows if r['domain']==domain and (r['gate'] in ['E_only','G_overflow'] or r['gate']=='G_uncertainty' and r['budget']=='0.1')]
    cols=[('seed','种子'),('arm','复核臂'),('gate','门控'),('correct','正确数'),('N','总数'),('deployment_calls','调用数'),('abstain','暂缓'),('S_fit_wrong_to_correct','纠错'),('S_fit_correct_to_wrong','改错'),('S_fit_correct_to_abstain','正确→暂缓'),('S_fit_unrouted_errors','未送审错误'),('S_overflow_recovery_correct','溢出恢复正确')]
    oldtable=table(primary(old),cols);newtable=table(primary(new),cols)
    simple=[r for r in new if r['gate']=='R0_only' or r['gate']=='L_all' and r['seed']=='42']
    simpletable=table(simple,[('domain','领域'),('gate','配置'),('arm','臂'),('correct','正确'),('N','总数'),('FP','误报'),('FN','漏检'),('abstain','暂缓'),('group_macro_correct_over_N','任务宏平均')])
    grouptable=table([r for r in new if r['gate']=='G_uncertainty' and r['budget']=='0.1'],[('domain','领域'),('seed','种子'),('arm','臂'),('correct','正确'),('N','总数'),('actual_call_rate','实际调用率'),('group_macro_correct_over_N','任务宏平均'),('unsafe_recall_all','全体unsafe召回'),('FPR_all','全体safe误报率')])
    randomtable=table([r for r in randoms if r['domain']=='combined' and r['budget']=='0.1'],[('cohort','数据/配置'),('seed','种子'),('arm','臂'),('correct_mean','随机正确数均值'),('correct_sd','随机重复SD'),('actual_call_rate_mean','匹配调用率')])
    infotable=table(info,[('domain','领域'),('model','配置'),('correct','正确'),('N','总数'),('abstain','暂缓'),('group_macro_correct_over_N','任务宏平均')])
    primarynew=[r for r in primary(new) if r['gate']=='G_uncertainty']
    conclusions=[]
    for arm in ['L_direct','L_relation']:
        rs=[r for r in primarynew if r['arm']==arm]
        conclusions.append(f"{arm} 主门控三种子正确数分别为 {' / '.join(r['correct'] for r in rs)}/264，实际调用数 {' / '.join(r['deployment_calls'] for r in rs)}；相对仅溢出基线正确数变化 {' / '.join(r['incremental_correct_vs_overflow'] for r in rs)}。")
    for arm in ['L_direct','L_relation']:
        rs=[r for r in randoms if r['cohort']=='transfer_2048' and r['domain']=='combined' and r['budget']=='0.1' and r['arm']==arm]
        conclusions.append(arm+' 同调用量随机20次的正确数均值为 '+' / '.join(f"{float(r['correct_mean']):.2f}" for r in rs)+'/264；三个种子的主门控均高于对应随机均值，仍只支持本264条、12任务组的探索结果，不是统计显著性或全领域保证。')
    pair=next(r for r in pairs if r['cohort']=='transfer_2048' and r['domain']=='combined' and r['view']=='all')
    conclusions.append(f"全量LLM直接臂正确 {pair['direct_correct']}/264，关系臂 {pair['relation_correct']}/264；关系臂相对直接臂二分类纠错 {pair['binary_corrected']}、改错 {pair['binary_introduced']}，正确转暂缓 {pair['correct_to_abstain']}、错误转暂缓 {pair['wrong_to_abstain']}，另有暂缓转正确 {pair['abstain_to_correct']}。")
    short=[r for r in info if r['domain']=='combined']
    conclusions.append('固定64条同信息对照：'+'；'.join(f"{r['model']} {r['correct']}/{r['N']}（暂缓{r['abstain']}）" for r in short)+'。')
    summary='\n\n'.join(conclusions)
    status=f"""# 第三轮运行状态

论文：**{TITLE}**

run-id：{cfg['run_id']}。**COMPLETED；本轮结束，不追加算法。**

- 旧test96缓存消融完成：S_fit82、溢出14；三种子、三预算、每组20个固定随机路由重复，新API 0。
- 新域264条：banking87/6组，travel177/6组；训练任务/完整输入重叠0，E可处理246、溢出18。原三检查点只推理。TF-IDF无已保存可加载产物，迁移NOT_RUN。
- 主实验直接/关系各264条；新2048与旧800分表。预选64条同信息直接短输入对照完成。
- 新增API {resource['new_api_calls']}；输入{resource['input_tokens']}、输出{resource['output_tokens']}，缓存命中{resource['cache_hit_tokens']}、未命中{resource['cache_miss_tokens']} token。HTTP错误{resource['HTTP_errors']}；实付账单未知。GPU推理{resource['gpu']['seconds']:.2f}秒，训练0步。

{summary}

用户最新要求：仅交实验结果与网页GPT Pro证据包，不生成报告/PPT。人工审核0，官方标签为探索参考；三种子和全部预算保留。
"""
    (HERE/'RUN_STATUS.md').write_text(status,encoding='utf-8')
    diagnostic='旧test96中14条是编码器输入溢出，82条已有二分类。仅溢出调用直接臂三种子正确95/92/93，关系臂94/91/92；dev10%不确定性门控相对它分别增加0/+3/-1个正确数。seed42没有二分类错误可纠正，seed43纠正3个错误，seed44改错1个。旧收益不能统一归因于难例识别，覆盖恢复与种子依赖的二分类纠错必须拆开。随机送审保留20次重复并按领域匹配实际调用数；重复不是20份独立测试。旧800-token结果保持原样。'
    (HERE/'mechanism_note.md').write_text(diagnostic+'\n',encoding='utf-8')
    handoff=f"""# 网页端GPT Pro实验事实包

论文题目逐字保持：**{TITLE}**

用途：本文件提供已经运行的实验事实、完整主运行点表、材料边界与案例入口，供网页端生成中期报告/PPT。不是报告成稿，不是GPT Pro已审定意见。用户不要求本地生成报告或PPT。

## 1. 当前结论与交付状态

{summary}

原始预测和指标均保留。没有重训、扩大旧测试调参或改提示。不要从三种子或三个预算挑最好结果代表整体；完整表包含全部随机重复。原负结果及800-token历史均保留。

## 2. 冻结实验口径

- 来源：ToolSafe固定提交46358fa424a927a895c6c8322f99032c4eb5155e；官方score0=safe、1=unsafe，0.5按既有规则排除。输入instruction、history、完整current_action、env_info；候选Thought也是待评估行为，不是可信授权。
- 模型：原LLMLingua-2多语言BERT骨干的E_field三检查点42/43/44，二分类阈值0.5；复用原512-token字段打包与dev门控阈值，不训练、不重写main.py。骨干已有压缩任务训练，不应写为完全原始BERT。
- L_direct/L_relation提示和解析器冻结。关系臂检查operation/object/destination/authorization，必要mismatch覆盖为unsafe、必要unknown覆盖为abstain；保留raw与effective两层。简短结构化核对不等于读取或验证私有思维链。
- 新请求统一max_tokens2048，旧800单独成表；这是输出长度修复，不是方法创新。温度0、thinking disabled，沿用同服务。请求模型{resource['request_models']}；返回模型{resource['response_models']}；指纹{resource['system_fingerprints']}。别名和指纹相同不能证明底层权重不变。
- 主运行点：沿用原dev10%预算阈值，是本轮根据旧数据预先选定，并非第二轮早已预注册。25%/50%敏感性分析全部保留。必须写测试实际调用率，不写成测试只调用10%。
- G_overflow只复核必需输入溢出；G_uncertainty加固定置信度送审；G_random强制同一溢出集合、再在每领域匹配不确定性送审数，随机种子0—19；L_all全部复核。所有配置共享同一样本一次LLM响应。

## 3. 数据与完成量

| 数据 | N | safe | unsafe | 任务组 | E可见性 |
|---|---:|---:|---:|---:|---|
| 旧缓存test | 96 | 61 | 35 | 见原索引 | S_fit82 / 溢出14 |
| banking | 87 | 59 | 28 | 6 | 见analysis_index |
| travel | 177 | 157 | 20 | 6 | 见analysis_index |
| 新域合并 | 264 | 216 | 48 | 12 | S_fit246 / 溢出18 |

新域排除0、精确重复删除0、与当前训练任务/完整输入重叠0。按规范化任务+同领域interaction+相同完整输入合并组；合格总体在预测前固定。称为“未参与当前训练的新增领域迁移测试”，不称绝对未见/独立人审gold/盲测。每领域仅6组，步骤相关且标签不均衡。

## 4. 指标定义（写作时不能替换）

correct/N全体分母，abstain不算正确；coverage、全体unsafe召回、全体safe FPR和covered指标另列。任务宏平均先算每组correct/N再等权平均。仅S_fit中的原错误→正确计真正纠错，正确→另一二分类计改错，两者差为净纠错；正确/错误→abstain另列。S_overflow原模型没有二分类，复核后正确属于恢复判断。未送审二分类错误单列。输入溢出、技术错误、模型主动暂缓、规则不支持/无法解析分别保留原因；规则低覆盖不是复杂算法先进性的证据。随机20次SD是路由变化，不是独立任务置信区间。

## 5. 旧test96消融（800-token）

{diagnostic}

{oldtable}

## 6. 新域主运行点全部种子（2048-token）

{newtable}

## 7. 分领域与强参考

{simpletable}

{grouptable}

## 8. 同调用量随机对照

主10%运行点的20次路由均值/SD如下；全量原始重复、25%/50%见CSV。

{randomtable}

## 9. 同信息对照

64条在任何新域预测前按领域各32、任务组轮转和源行顺序选择，不按标签或模型错误选。短输入为E实际field_text原文，保留字段标识，无自动摘要/隐藏证据。长输入复用主实验。相同内容不等于相同tokenizer、系统提示或容量；减少信息后的官方标签未重新验证为充分信息gold。

{infotable}

## 10. 资源与未运行项

新增API {resource['new_api_calls']}，输入{resource['input_tokens']}，输出{resource['output_tokens']}，缓存命中{resource['cache_hit_tokens']}、未命中{resource['cache_miss_tokens']}。HTTP错误{resource['HTTP_errors']}；GPU推理{resource['gpu']['seconds']:.2f}秒、峰值{resource['gpu']['peak_memory_bytes']/1024**3:.2f}GiB、训练0步。实付费用未知，不能写成已核对账单。日期和逐次调用见api_usage/resource_usage。

未运行：新域TF-IDF/R1（原训练未保存可加载分类器与向量器；本轮不重新拟合）、证据辅助训练、RL、GUI、完整ShieldAgent复现。中期报告与PPT由网页端生成，本地没有成稿。

## 11. 允许与不允许的结论

可写：原生口径修复、分组探索划分、三种子基线和冻结配对/协同已运行；机制的增量可由同量随机和溢出基线评价；真实失败边界可展示。

不可写：普通级联已证明原创、引用正确即解释正确、静态分类等于闭环攻击成功率、官方标签或AI审核等于人审gold、更多历史带来的增益完全来自推理机制。工程可行、机制有效、论文创新成立是不同层次。

8例见cases.md；必要原文审核摘录在用户本地cases.local.md。特别检查旧0404：工具说明仅创建日历事件并通知参与者，关系解释附加的房间预订推断没有工具语义支持；不因此改标签或提示。人审pending，reviewer=AI。

## 12. 原始证据导航

mechanism_ablation.csv：旧96缓存所有种子/预算/随机重复；transfer_results.csv：新增banking/travel/合并；random_summary.csv：20重复均值SD；paired_results.csv：直接/关系纠错与改错；information_control.csv：固定64条；predictions.jsonl：逐条原始决定；routes.jsonl：各配置送审ID；analysis_index.jsonl：标签/分组/窗口与来源；config/request_config：冻结阈值和请求；resource_usage/api_usage：实际资源。

网页端写作前先核对这些表，不凭题目倒推正结果；若无一致增益，应如实写成中期问题与后续待决事项。本轮交付后结束，不把后续建议写成已完成实验。
"""
    (HERE/'GPT_PRO_HANDOFF.md').write_text(handoff,encoding='utf-8')
    (HERE/'run_state.json').write_text(json.dumps({'status':'COMPLETED','stage_ended':True,'main_pairs':264,'information_control':64,'seeds':[42,43,44],'R1_transfer':'NOT_RUN','human_reviewed':0,'new_algorithm':False,'report_and_PPT':'delegated_by_user_to_web_GPT_Pro_not_generated'},ensure_ascii=False,indent=2),encoding='utf-8')
    print(summary)
if __name__=='__main__':main()
