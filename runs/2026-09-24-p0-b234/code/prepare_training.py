"""Freeze a bounded, explicitly exploratory server pilot after the P0 audit."""
import collections
import json
from pathlib import Path
from pilot import HERE, read_lines, write_lines, dump, utc_now

data = read_lines("data.jsonl")
preds = {r["sample_id"]: r for r in read_lines("predictions.jsonl") if r["model"] == "P0_LLM_evidence"}
root = HERE / "training"
root.mkdir(exist_ok=True)
if (root / "config.json").exists():
    raise RuntimeError("training freeze already exists")
families = {"train": ["f00", "f01", "f02", "f03", "f05", "f07", "f08"], "dev": ["f04"], "evaluation_exploratory": ["f06", "f09"]}
selection = set(json.loads((HERE / "selection.json").read_text(encoding="utf-8"))["sample_ids"])
output, review = [], []
for r in data:
    if r["source_dataset"] == "TS-Bench":
        if r["sample_id"] not in selection:
            continue
        split = "native_evaluation_exploratory"
    else:
        split = next(s for s, fs in families.items() if r["template_family"] in fs)
    row = dict(r, experiment_split=split, evidence_annotations={})
    # Codex actually inspected the exact refs and justifications for these 48 records
    # in the current session. This is NOT human review or gold annotation.
    if split == "train" and r["template_family"] in ("f00", "f01", "f02", "f07"):
        p = preds[r["sample_id"]]
        accepted = p["reference_valid"] and p["teacher_label_agreement"]
        note = "Original user scope, recipient, resource or confidentiality statement supports the decision; u1 is a relevant positive segment. Other teacher refs are not blanket accepted."
        if not accepted:
            note = "Reject: teacher authorizes the wrong resource by reasoning only about recipient/public status; conflicts with independently constructed label."
        if accepted:
            assert any(e["message_id"] == "u1" for e in p["evidence"]["evidence_refs"])
            row["evidence_annotations"]["u1"] = 1
            if any(m["id"] == "o_noise" for m in r["input"]["messages"]):
                row["evidence_annotations"]["o_noise"] = 0
        review.append({"sample_id": r["sample_id"], "reviewer": "Codex_agent_semantic_review", "human_review": False,
                       "status": "accepted_silver_partial_segment_supervision" if accepted else "rejected_label_conflict",
                       "review_note": note, "annotations": row["evidence_annotations"], "teacher_input_had_gold_label": False,
                       "unreviewed_segments": "masked_out_not_negative", "evidence_source": f"../predictions.jsonl#{r['sample_id']}",
                       "label_status": "construction_silver_pending_human_review"})
    output.append(row)
(root / "data.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in output), encoding="utf-8")
(root / "evidence_review.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in review), encoding="utf-8")
config = {
    "experiment_id": "thesis-context-server-pilot-v2", "authorized_by": "2026-09-24 user permits server experiments",
    "prelaunch_correction": "v1 freeze rejected before training: f01/f08 share identical unsafe inputs. f08 moved wholly to train; f06 moved wholly from dev to exploratory evaluation. No model training or tuning took place in v1; original packet preserved.",
    "frozen_at": utc_now(), "seeds": [42, 43, 44], "models": ["B2", "B3", "B4"],
    "model_path": "/models", "model_source": "microsoft/llmlingua-2-bert-base-multilingual-cased-meetingbank cached BertForTokenClassification backbone",
    "backbone_note": "Already compression-tuned multilingual BERT, not a newly downloaded generic DeBERTa; identical backbone for all arms; English only",
    "learning_rate": 2e-5, "epochs": 8, "groups_per_batch": 4, "max_length": 512,
    "margin": 1.0, "lambda_pair": 0.5, "lambda_inv": 0.1, "lambda_evi": 0.2,
    "threshold": 0.5, "threshold_selection": "fixed a priori; no test tuning", "checkpoint": "final epoch, no cherry-picking",
    "precision": "float32", "optimizer": "AdamW", "weight_decay": 0.01,
    "splits": families, "counts": dict(collections.Counter(r["experiment_split"] for r in output)),
    "evidence_reviewed": len(review), "evidence_accepted": sum(bool(r["annotations"]) for r in review),
    "evidence_review_scope": "42 agent-reviewed silver records; only u1 positives and explicitly irrelevant o_noise negatives; no human gold claims",
    "primary_status": "ENGINEERING_AND_EXPLORATORY_ONLY",
    "limitations": ["P0 B0 solved 40/40 pairs; no demonstrated need for learned complexity", "all 40 groups already viewed and model-screened; this split is not blind test", "template-family disjoint; entity names shared; exact-input overlap checked", "native official train split unavailable; native records evaluation only", "B4 is silver partial evidence localization supervision, not qualified human-reviewed complete semantic-CoT claim", "no same-extra-label/generic-evidence control this round"],
    "same_data": True, "same_initialization_within_seed": True, "same_batches_and_steps": True,
    "max_gpu_hours": 1, "max_runs": 9,
}
(root / "config.json").write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
# Check group and exact-input isolation (duplicates within one split remain disclosed).
origin_splits, input_splits = collections.defaultdict(set), collections.defaultdict(set)
for r in output:
    origin_splits[r["origin_id"]].add(r["experiment_split"])
    input_splits[json.dumps(r["input"], sort_keys=True)].add(r["experiment_split"])
assert all(len(v) == 1 for v in origin_splits.values())
assert all(len(v) == 1 for v in input_splits.values())
(root / "freeze_checks.json").write_text(json.dumps({"origin_cross_split": 0, "exact_input_cross_split": 0, "within_split_duplicate_rows": len(output)-len(input_splits), "human_gold": 0}, indent=2), encoding="utf-8")
print(json.dumps(config["counts"]))
