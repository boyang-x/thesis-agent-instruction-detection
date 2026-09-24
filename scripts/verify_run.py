"""Verify published metrics against published per-sample predictions (standard library only)."""
from __future__ import annotations
import argparse
import csv
import json
import math
import statistics
from pathlib import Path
from metric_core import metrics


def read_jsonl(p):
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines()]


def numeric_equal(actual, expected, path):
    if isinstance(actual, dict):
        for key, value in actual.items():
            numeric_equal(value, expected[key], path + "/" + key)
    elif isinstance(actual, list):
        assert len(actual) == len(expected), path
        for i, (a, b) in enumerate(zip(actual, expected)):
            numeric_equal(a, b, path + f"/{i}")
    elif isinstance(actual, (float, int)) and not isinstance(actual, bool):
        assert expected is not None and math.isclose(actual, expected, rel_tol=1e-9, abs_tol=1e-9), (path, actual, expected)
    elif actual is None:
        assert expected is None, (path, expected)


def verify(root):
    publication=root / 'publication.json'
    if publication.exists() and json.loads(publication.read_text(encoding='utf-8')).get('publication_schema')=='round2_resume':
        from verify_resume import verify as verify_r
        return verify_r(root)
    if publication.exists() and json.loads(publication.read_text(encoding='utf-8')).get('publication_schema')=='round2':
        from verify_round2 import verify as verify_v2
        return verify_v2(root)
    preds = read_jsonl(root / "predictions.jsonl")
    data = {r["sample_id"]: r for r in read_jsonl(root / "sample_index.jsonl")}
    selection = set(json.loads((root / "selection.json").read_text(encoding="utf-8"))["sample_ids"])
    stored = json.loads((root / "metrics.json").read_text(encoding="utf-8"))
    assert len(preds) == len({(r["sample_id"], r["model"], r.get("seed")) for r in preds})
    assert all(r["sample_id"] in data and r["label"] == data[r["sample_id"]]["label"] for r in preds)
    eval_ids = {r["sample_id"] for r in preds if r.get("split") == "evaluation_exploratory"}
    for key, expected in stored["results"].items():
        parts = key.split("/")
        model, cohort = parts[0], parts[-1]
        seed = int(parts[1][4:]) if len(parts) == 3 else None
        candidates = [r for r in preds if r["model"] == model and r.get("seed") == seed]
        if seed is not None:
            subset = [r for r in candidates if r["split"] == cohort or (cohort == "native_untruncated_exploratory" and r["split"] == "native_evaluation_exploratory" and not r["truncated"])]
        elif cohort == "diagnostic_development":
            subset = [r for r in candidates if data[r["sample_id"]]["source_dataset"] == "constructed_context_v1"]
        elif cohort == "evaluation_exploratory":
            subset = [r for r in candidates if r["sample_id"] in eval_ids]
        else:
            subset = [r for r in candidates if data[r["sample_id"]]["source_dataset"] == "TS-Bench" and (cohort == "native_static_all" or r["sample_id"] in selection)]
        numeric_equal(metrics(subset, data), expected, key)
    for model, aggregate in stored.get("seed_aggregates", {}).items():
        def values(cohort, field):
            return [m[field]["value"] for key, m in stored["results"].items() if key.startswith(model + "/seed") and key.endswith("/" + cohort)]
        for name, cohort, field in [("PairAcc", "evaluation_exploratory", "PairAcc"), ("F1", "evaluation_exploratory", "f1_unsafe_on_covered"), ("native_F1", "native_evaluation_exploratory", "f1_unsafe_on_covered"), ("invariance", "evaluation_exploratory", "invariance_consistency")]:
            xs = [v for v in values(cohort, field) if v is not None]
            numeric_equal({"mean": statistics.mean(xs) if xs else None, "sd": statistics.stdev(xs) if len(xs)>1 else None, "values": xs}, aggregate[name], model + "/aggregate/" + name)
    if (root / "api_usage.jsonl").exists():
        calls = read_jsonl(root / "api_usage.jsonl")
        resource = json.loads((root / "resource_usage.json").read_text(encoding="utf-8"))
        assert resource["api_calls"] == len(calls)
        assert resource["input_tokens"] == sum(r.get("usage", {}).get("prompt_tokens", 0) for r in calls)
        assert resource["output_tokens"] == sum(r.get("usage", {}).get("completion_tokens", 0) for r in calls)
    for r in csv.DictReader((root / "results.csv").open(encoding="utf-8-sig", newline="")):
        key = f"{r['model']}/" + (f"seed{r['seed']}/" if r["seed"] else "") + r["cohort"]
        m = stored["results"][key]
        assert int(r["n"]) == m["n"]
        for cell in ("TP", "FP", "TN", "FN"):
            assert int(r[cell]) == m["binary_confusion_on_covered"][cell]
    for r in csv.DictReader((root / "ablation.csv").open(encoding="utf-8-sig", newline="")):
        if r["status"] == "NOT_RUN":
            assert all(r[f] == "" for f in ("PairAcc_mean", "F1_mean", "independent_heldout_F1"))
        elif r["model"] in stored.get("seed_aggregates", {}):
            a = stored["seed_aggregates"][r["model"]]
            for field, key in (("PairAcc_mean", "PairAcc"), ("F1_mean", "F1")):
                assert math.isclose(float(r[field]), a[key]["mean"], abs_tol=1e-9)
    result = {"status": "PASS", "prediction_rows": len(preds), "sample_index_rows": len(data), "metric_groups_recomputed": len(stored["results"]), "unrun_results_blank": True}
    (root / "publication_validation.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("run", type=Path)
    print(json.dumps(verify(p.parse_args().run), ensure_ascii=False))
