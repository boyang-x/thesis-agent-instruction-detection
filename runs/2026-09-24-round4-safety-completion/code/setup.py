"""Freeze the user-specified bounded fourth round before new requests."""
import json,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;OLD=HERE.with_name('thesis_round2_20260924');R3=HERE.with_name('thesis_round3_20260924')
sys.path.insert(0,str(OLD))
from common import readl,writel,dump
def main():
    assert not (HERE/'config.json').exists()
    cfg=json.loads((R3/'config.json').read_text());cfg.update(run_id='2026-09-24-round4-safety-completion',publication_schema='round4',frozen_public_commit='505c7ac6933bb1eaf8de9e4dbdbd1ade7c58a0dc',selection_split='original_full_source_dev',selection_N=158,minimum_unsafe_recall=.95,maximum_safe_FPR=.05,selection_rule='all 2 arms x 3 seeds pass both constraints; lowest mean actual call rate; tie smaller existing nominal budget; no relaxation',integration_seed=42,integration_cases=12,integration_fallback_budget=.1,integration_selection='3 per branch, stable source order, ignore labels and teacher outputs',new_training=False,new_domains=False,new_prompts=False)
    dump(HERE/'config.json',cfg)
    dev=[r for r in readl(OLD/'packed.jsonl') if r['split']=='dev'];assert len(dev)==158
    writel(HERE/'dev.local.jsonl',dev)
    selection=json.loads((R3/'information_selection.json').read_text());dump(HERE/'information_selection.json',selection)
    short_requests=[r for r in readl(R3/'api_attempts.jsonl') if r['stage']=='short'];assert len(short_requests)==64
    short={r['call_id'].split('__')[1]:json.loads(r['request']['messages'][1]['content']) for r in short_requests}
    assert set(short)==set(selection['sample_ids'])
    rows={r['sample_id']:r for r in readl(R3/'packed.jsonl')}
    queue=[{'phase':'dev','sample_id':r['sample_id'],'arm':a,'input':r['llm_input'],'row':{k:r[k] for k in ['sample_id','group_id','label','split']}} for r in dev for a in ['L_direct','L_relation']]
    queue += [{'phase':'relation_short','sample_id':sid,'arm':'L_relation_short','input':short[sid],'row':{k:rows[sid][k] for k in ['sample_id','group_id','label','split']}} for sid in selection['sample_ids']]
    writel(HERE/'request_queue.local.jsonl',queue)
    (HERE/'PLAN.md').write_text('# 第四轮实验清单\n\n论文：基于语义表征与思维链推理协同的智能体恶意指令检测方法\n\nP0复用第三轮缓存分析安全性和未送审漏检；P1只在完整源域dev158按用户固定95%召回/5%误报规则选共同工作点；补316个2048-token dev臂，不按错误挑选。P2仅补已固定64条relation_short，逐字复用原direct_short输入。P3在选点后预选12条分支案例，seed42在线E前向，两臂共享门控，真实LLM，已有执行前接口接记录替身；若无合格点回退原主10%。不重训、扩域、改提示或主入口，不制作PPT/报告/讲稿。402立即停止新增调用。完成即收尾发布，不追加算法。\n',encoding='utf-8')
    print(json.dumps({'dev_rows':len(dev),'new_dev_arms':316,'new_relation_short':64,'source_dev_labels':{y:sum(r['label']==y for r in dev) for y in ['safe','unsafe']}}))
if __name__=='__main__':main()
