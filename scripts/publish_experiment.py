"""Export a bounded review packet and optionally commit/push it. Never reruns experiments."""
from __future__ import annotations
import argparse
import collections
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from verify_run import verify, read_jsonl

ROOT = Path(__file__).resolve().parents[1]
TITLE = "基于语义表征与思维链推理协同的智能体恶意指令检测方法"
REPO_URL = "https://github.com/boyang-x/thesis-agent-instruction-detection"
FILES = ["RUN_STATUS.md", "midterm_summary.md", "ablation.csv", "metrics.json", "results.csv", "data_manifest.json", "resource_usage.json", "run_state.json", "training_verification.json", "plan.json", "selection.json"]


def scrub(text):
    # Operational coordinates are unnecessary in a public scientific review packet.
    text = re.sub(r"(?:C:\\\\|C:\\|C:/)Users(?:\\\\|\\|/)[^\s\"`<>]+", "LOCAL_PATH_REDACTED", text)
    text = re.sub(r"/home/[A-Za-z0-9_.-]+/[^\s\"`<>]+", "REMOTE_PATH_REDACTED", text)
    text = re.sub(r"\b(?:10\.(?:\d{1,3}\.){2}\d{1,3}|192\.168\.\d{1,3}\.\d{1,3})\b", "INTERNAL_IP_REDACTED", text)
    text = re.sub(r"\b[a-zA-Z0-9_.-]*qianxin-inc\.cn\b", "INTERNAL_HOST_REDACTED", text)
    for alias in ('server-a','server-b','server-c'):
        text = text.replace(alias, "EXISTING_COMPUTE_HOST")
    return text


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def lines(path, values):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(v, ensure_ascii=False) + "\n" for v in values), encoding="utf-8")


def safe_copy(source, target):
    text = source.read_text(encoding="utf-8-sig")
    target.parent.mkdir(parents=True, exist_ok=True)
    if source.suffix == ".json":
        # Scrub string values after parsing so backslashes cannot corrupt JSON.
        def transform(x):
            if isinstance(x, str): return scrub(x)
            if isinstance(x, list): return [transform(v) for v in x]
            if isinstance(x, dict): return {k: transform(v) for k, v in x.items()}
            return x
        dump(target, transform(json.loads(text)))
    else:
        target.write_text(scrub(text), encoding="utf-8")


def export(source, run_id):
    if run_id=='2026-09-24-scheme-selection-closeout':
        from publish_closeout import export as export_closeout
        return export_closeout(source,run_id)
    if run_id=='2026-09-24-round4-safety-completion':
        from publish_round4 import export as export_v4
        return export_v4(source,run_id)
    if run_id=='2026-09-24-round3-transfer-ablation':
        from publish_round3 import export as export_v3
        return export_v3(source,run_id)
    if (source / 'freeze_manifest.json').exists() and run_id=='2026-09-24-round2-http402-resume':
        from publish_resume import export as export_resume
        return export_resume(source,run_id)
    if (source / 'analysis_contract.json').exists():
        from publish_round2 import export as export_v2
        return export_v2(source,run_id)
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]+", run_id):
        raise ValueError("invalid run ID")
    for name in FILES + ["data.jsonl", "predictions.jsonl"]:
        if not (source / name).is_file(): raise FileNotFoundError(source / name)
    dest = ROOT / "runs" / run_id
    dest.mkdir(parents=True, exist_ok=True)
    for name in FILES: safe_copy(source / name, dest / name)
    data = read_jsonl(source / "data.jsonl")
    by_id = {r["sample_id"]: r for r in data}
    index = [{k: v for k, v in r.items() if k not in ("input", "label_basis")} for r in data]
    lines(dest / "sample_index.jsonl", index)
    lines(dest / "diagnostic_data.jsonl", [r for r in data if r["source_dataset"] == "constructed_context_v1"])
    lines(dest / "review_queue.jsonl", read_jsonl(source / "review_queue.jsonl"))
    original = read_jsonl(source / "predictions.jsonl")
    published = []
    for r in original:
        p = dict(r)
        p["input_ref"] = f"sample_index.jsonl#{p['sample_id']}"
        if by_id[r["sample_id"]]["source_dataset"] == "TS-Bench" and p.get("evidence"):
            p["evidence"] = {"publication_omission": "upstream native text omitted; numeric reference-validity fields preserved"}
        published.append(p)
    assert all({k: v for k, v in a.items() if k not in ("evidence", "input_ref")} == {k: v for k, v in b.items() if k not in ("evidence", "input_ref")} for a, b in zip(original, published))
    lines(dest / "predictions.jsonl", published)
    lines(dest / "error_samples.jsonl", [r for r in published if r["prediction"] != r["label"]])
    api = read_jsonl(source / "api_calls.jsonl")
    lines(dest / "api_usage.jsonl", [{k: v for k, v in r.items() if k not in ("payload", "error_body", "error_message")} for r in api])
    lines(dest / "api_calls_synthetic.jsonl", [r for r in api if r["call_id"].startswith("diagnostic_")])
    lines(dest / "api_requests_synthetic.jsonl", [r for r in read_jsonl(source / "api_attempts.jsonl") if r["call_id"].startswith("diagnostic_")])
    if (source / "training").exists():
        for name in ("config.json", "freeze_checks.json", "server_environment.json", "window_audit.json", "server_complete.json"):
            if (source / "training" / name).exists(): safe_copy(source / "training" / name, dest / "training" / name)
        lines(dest / "training/evidence_review.jsonl", read_jsonl(source / "training/evidence_review.jsonl"))
        tdata = read_jsonl(source / "training/data.jsonl")
        lines(dest / "training/sample_index.jsonl", [{k: v for k, v in r.items() if k not in ("input", "label_basis")} for r in tdata])
        for file in (source / "training/runs").glob("*/*"):
            if file.name in ("status.json", "losses.jsonl"): safe_copy(file, dest / "training/runs" / file.parent.name / file.name)
    for name in ("pilot.py", "train_server.py", "prepare_training.py", "analyze.py", "test_pilot.py"):
        if (source / name).exists(): safe_copy(source / name, dest / "code" / name)
    (dest / "code/README.md").write_text("# 本轮算法代码快照\n\n保留规则、数据构造、联合损失及训练代码。pilot/analyze依赖原仓库，训练入口依赖PyTorch/Transformers及缓存编码器；本目录不是重写后的主入口。\n\n公开包数值核查无需原仓库或模型：运行 `python scripts/verify_run.py runs/"+run_id+"`。第三方native输入仅提供来源索引，未重新分发；自建诊断输入见diagnostic_data.jsonl。\n", encoding="utf-8")
    # Public cases preserve authored diagnostic inputs; native traces are linked by row instead.
    cases = ["# 已运行案例与失败分析", "", "构造标签均为silver待人工审核。下述是候选动作静态分类，不是实际攻击成功。", ""]
    choices = [
        ("正常放行", lambda r: r["prediction"] == r["label"] == "safe" and r["model"] == "P0_LLM_evidence"),
        ("越权候选拦截", lambda r: r["prediction"] == r["label"] == "unsafe" and r["model"] == "P0_LLM_evidence"),
        ("模型漏检：收件人授权不等于文件授权", lambda r: r["label"] == "unsafe" and r["prediction"] == "safe" and r["model"] == "P0_LLM_evidence"),
        ("引用无效导致暂停", lambda r: r.get("error_code") == "INVALID_EVIDENCE_REFERENCE"),
        ("小模型失败", lambda r: r["model"] == "B4" and r["label"] != r["prediction"] and r.get("split") == "evaluation_exploratory"),
    ]
    for title, predicate in choices:
        matches = [r for r in published if by_id[r["sample_id"]]["source_dataset"] == "constructed_context_v1" and predicate(r)]
        cases += ["## " + title, ""]
        if not matches: cases += ["未找到已运行案例。", ""]; continue
        row = matches[0]
        cases += [f"sample_id: `{row['sample_id']}`；模型 `{row['model']}`；seed `{row.get('seed')}`；标签 `{row['label']}`；预测 `{row['prediction']}`。", "", "```json", json.dumps(by_id[row["sample_id"]]["input"], ensure_ascii=False, indent=2), "```", "", "实际返回证据：", "```json", json.dumps(row.get("evidence"), ensure_ascii=False, indent=2), "```", ""]
    misses = [r for r in published if r["model"] == "B0" and r["label"] == "unsafe" and r["prediction"] == "safe" and by_id[r["sample_id"]]["source_dataset"] == "TS-Bench"]
    cases += ["## 原生规则漏检索引", "", "原生标签/来源投影仍需审计，完整轨迹留在上游和本地。", ""]
    for row in misses[:5]:
        d = by_id[row["sample_id"]]
        cases.append(f"- `{row['sample_id']}`：{d['source_file']}，零起始行{d['source_row']}；预测safe/官方标签unsafe；规则原因 `{row.get('rule_reason')}`。")
    (dest / "cases.md").write_text("\n".join(cases) + "\n", encoding="utf-8")
    env = json.loads((source / "environment.json").read_text(encoding="utf-8"))
    dump(dest / "publication.json", {"run_id": run_id, "exported_at": datetime.now(timezone.utc).isoformat(), "source_repository": "boyang-x/agent-guardrail-research", "source_commit": env["git_commit"], "source_code_state": "experiment subdirectory originally untracked; public code snapshot included", "publication_scope": "necessary review packet", "prediction_numeric_fields_unchanged": True, "omissions": ["full native dataset and native API payloads", "private infrastructure coordinates", "credentials", "model weights/checkpoints", "irrelevant historical files"], "native_input_recovery": "use data_manifest upstream commit and sample_index source_file/source_row", "raw_native_artifacts_retained_locally": True})
    result = verify(dest)
    state = json.loads((dest / "run_state.json").read_text(encoding="utf-8"))
    ledger_path = ROOT / "experiments.json"
    ledger = json.loads(ledger_path.read_text(encoding="utf-8")) if ledger_path.exists() else []
    entry = {"run_id": run_id, "path": f"runs/{run_id}", "exported_at": datetime.now(timezone.utc).isoformat(), "state": state, "verification": result}
    ledger = [r for r in ledger if r["run_id"] != run_id] + [entry]
    dump(ledger_path, ledger)
    (ROOT / "EXPERIMENTS.md").write_text("# 实验记录\n\n| 实验 | 预测条数 | 方法优势已证明 | 状态 |\n|---|---:|---|---|\n" + "".join(f"| [{r['run_id']}]({r['path']}/RUN_STATUS.md) | {r['verification']['prediction_rows']} | {r['state'].get('method_advantage_demonstrated', 'unknown')} | 已上传结果包 |\n" for r in ledger), encoding="utf-8")
    (ROOT / "CURRENT_STATUS.md").write_text(f"# 当前状态\n\n论文题目：**{TITLE}**\n\n最新实验：[{run_id}](runs/{run_id}/RUN_STATUS.md)。\n\n" + "\n".join(f"- {k}: `{v}`" for k, v in state.items()) + f"\n\n[消融表](runs/{run_id}/ablation.csv) · [失败案例](runs/{run_id}/cases.md) · [中期进度](runs/{run_id}/midterm_summary.md) · [原始预测](runs/{run_id}/predictions.jsonl)\n\n公开数值核查：{result['prediction_rows']}条预测、{result['metric_groups_recomputed']}组指标通过重算。详细局限以本轮报告为准。\n", encoding="utf-8")
    (ROOT / "GPT_PRO_REVIEW.md").write_text(f"# GPT Pro审阅入口\n\n论文题目：**{TITLE}**\n\n最新实验：`{run_id}`。请以仓库当前提交为审阅依据，先查看以下材料：\n\n1. [当前状态](CURRENT_STATUS.md)和[运行报告](runs/{run_id}/RUN_STATUS.md)。\n2. [消融表](runs/{run_id}/ablation.csv)、[逐种子结果](runs/{run_id}/results.csv)、[指标](runs/{run_id}/metrics.json)。\n3. [失败案例](runs/{run_id}/cases.md)、[原始预测](runs/{run_id}/predictions.jsonl)及[样本索引](runs/{run_id}/sample_index.jsonl)。\n4. [数据来源与边界](runs/{run_id}/data_manifest.json)、[训练配置](runs/{run_id}/training/config.json)、[算法快照](runs/{run_id}/code)、[资源](runs/{run_id}/resource_usage.json)。\n\n## 可直接交给GPT Pro的请求\n\n请检查上述实验的代码、原始预测和证据边界，区分已运行结论与设计。核对同数据/初始化/预算、PairAcc与F1是否一致、abstain和截断是否被隐藏、证据损失是否真正回传，以及负结果是否被完整保留。\n\n优先判断当前问题是否仍值得推进：若规则已解决构造样本或B4未超同数据B2/B3，请明确指出，不包装创新或选择最好种子。审查原生数据适配、来源可信度、模板/重复泄漏、silver证据资格及缺少的额外监督对照。\n\n请给出一个最小且可执行的下一轮建议，包括：具体要验证的问题、最少必要的数据/人工审阅、固定条件、强简单对照、评价指标、资源预算、成功与停止标准；如果应暂停，请直接说明。不要改变论文题目，不重写原仓库主入口，暂不安排RL、GUI或完整ShieldAgent复现。\n\n当前人类gold审阅尚未完成；B4只是部分代理审核silver证据训练，静态分类不是闭环攻击成功率。此前P0已查看的样本不可改称盲测。\n\n反馈回传后放到[reviews](reviews/README.md)，再记录采纳决定；这里尚未获得GPT Pro评审，不能假称其已认可。\n\n仓库链接：{REPO_URL}\n", encoding="utf-8")
    return dest, result


def git(*args, capture=False):
    return subprocess.run(["git", *args], cwd=ROOT, check=True, text=True, encoding="utf-8", capture_output=capture).stdout


def scan(dest):
    keys = [v for k, v in os.environ.items() if (k.endswith("API_KEY") or k in ("GH_TOKEN", "GITHUB_TOKEN")) and len(v) > 8]
    hits = []
    for path in dest.rglob("*"):
        if path.is_file():
            text = path.read_text(encoding="utf-8", errors="replace")
            if any(k in text for k in keys) or re.search(r"-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----", text): hits.append(str(path.relative_to(ROOT)))
    if hits: raise RuntimeError("credential scan failed: " + repr(hits))


def push(run_id):
    if git("diff", "--cached", "--name-only", capture=True).strip(): raise RuntimeError("pre-existing staged files; handle explicitly")
    git("fetch", "--prune", "origin")
    branches = git("branch", "-r", "--list", "origin/main", capture=True).strip()
    if branches:
        behind, ahead = map(int, git("rev-list", "--left-right", "--count", "origin/main...HEAD", capture=True).split())
        if behind: raise RuntimeError("remote changed; integrate deliberately before publication, never force-push")
    paths = [f"runs/{run_id}", "CURRENT_STATUS.md", "GPT_PRO_REVIEW.md", "EXPERIMENTS.md", "experiments.json", "README.md", "AGENTS.md", ".gitignore", "scripts", "reviews/README.md", "Codex_毕设实施与实验任务书.md"]
    if run_id=='2026-09-24-round2-native-collaboration':
        paths += ['reviews/2026-09-24-round2-instructions.md','reviews/2026-09-24-round2-adoption.md']
    git("add", "--", *paths)
    git("diff", "--cached", "--check")
    if git("diff", "--cached", "--name-only", capture=True).strip(): git("commit", "-m", "Publish experiment review packet: " + run_id)
    git("push", "-u", "origin", "HEAD:main")
    local = git("rev-parse", "HEAD", capture=True).strip()
    remote = git("ls-remote", "origin", "refs/heads/main", capture=True).split()[0]
    if local != remote: raise RuntimeError("remote HEAD verification failed")
    return local


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--push", action="store_true")
    args = parser.parse_args()
    dest, result = export(args.source.resolve(), args.run_id)
    scan(dest)
    if args.push: result["remote_commit"] = push(args.run_id)
    print(json.dumps(result, ensure_ascii=False))
