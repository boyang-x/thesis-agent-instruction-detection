"""Same-data B2/B3/B4 micro-pilot. No network, no provider calls, no tool dispatch."""
from __future__ import annotations
import collections
import json
import os
from pathlib import Path
import random
import time
import platform

import numpy as np
import torch
from torch import nn
from transformers import AutoModel, AutoTokenizer
import transformers

ROOT = Path("/work/training")
CFG = json.loads((ROOT / "config.json").read_text())
DATA = [json.loads(s) for s in (ROOT / "data.jsonl").read_text().splitlines()]
OUT = ROOT / "runs"
OUT.mkdir(exist_ok=True)


def write(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n")


def seed_all(seed):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


def render(inp):
    # Same input selection and order for every arm, without gold or dataset metadata.
    text = "CANDIDATE " + json.dumps(inp["candidate"], sort_keys=True) + "\n"
    spans = []
    for m in inp["messages"]:
        start = len(text)
        text += f"MESSAGE {m['id']} SOURCE {m['source']}\n{m['text']}\n"
        spans.append((m["id"], start, len(text)))
    text += "TOOL SEMANTICS " + inp["tool_semantics"]
    return text, spans


class Detector(nn.Module):
    def __init__(self):
        super().__init__()
        self.encoder = AutoModel.from_pretrained(CFG["model_path"], local_files_only=True, add_pooling_layer=False, attn_implementation="eager")
        h = self.encoder.config.hidden_size
        self.risk = nn.Linear(h, 1)
        self.evidence = nn.Linear(h, 1)

    def forward(self, batch):
        states = self.encoder(input_ids=batch["input_ids"], attention_mask=batch["attention_mask"]).last_hidden_state
        risk = self.risk(states[:, 0]).squeeze(-1)
        weights = batch["segment_mask"]
        pooled = torch.bmm(weights, states) / weights.sum(-1, keepdim=True).clamp_min(1)
        evidence = self.evidence(pooled).squeeze(-1)
        return risk, evidence


def encode(tokenizer, row):
    text, spans = render(row["input"])
    full = tokenizer(text, add_special_tokens=True, truncation=False)
    tokens = tokenizer(text, add_special_tokens=True, truncation=True, max_length=CFG["max_length"], return_offsets_mapping=True)
    offsets = tokens.pop("offset_mapping")
    segs = []
    labels = []
    for mid, start, end in spans:
        mask = [float(b > start and a < end and b > a) for a, b in offsets]
        # A reviewed segment is usable only if fully represented in the encoder window.
        covered = max((b for (a, b), take in zip(offsets, mask) if take), default=0) >= end - 1
        segs.append(mask)
        labels.append(row["evidence_annotations"].get(mid, -1) if covered else -1)
    return {"input_ids": tokens["input_ids"], "attention_mask": tokens["attention_mask"],
            "segment_mask": segs, "evidence_targets": labels,
            "target": float(row["label"] == "unsafe"), "row": row,
            "original_tokens": len(full["input_ids"]), "truncated": len(full["input_ids"]) > CFG["max_length"],
            "segment_ids": [s[0] for s in spans]}


def batchify(rows):
    length = max(len(r["input_ids"]) for r in rows)
    segments = max(len(r["segment_mask"]) for r in rows)
    ids, masks, sm, targets = [], [], [], []
    for r in rows:
        pad = length-len(r["input_ids"])
        ids.append(r["input_ids"] + [0]*pad)
        masks.append(r["attention_mask"] + [0]*pad)
        sm.append([m+[0]*pad for m in r["segment_mask"]]+[[0]*length]*(segments-len(r["segment_mask"])))
        targets.append(r["evidence_targets"]+[-1]*(segments-len(r["evidence_targets"])))
    return {"input_ids": torch.tensor(ids, device="cuda"), "attention_mask": torch.tensor(masks, device="cuda"),
            "segment_mask": torch.tensor(sm, dtype=torch.float32, device="cuda"),
            "evidence_targets": torch.tensor(targets, dtype=torch.float32, device="cuda"),
            "target": torch.tensor([r["target"] for r in rows], device="cuda")}


def losses(logits, evidence, batch, rows):
    cls = nn.functional.binary_cross_entropy_with_logits(logits, batch["target"])
    by_group = collections.defaultdict(dict)
    for i, r in enumerate(rows):
        by_group[r["row"]["origin_id"]][r["row"]["variant"]] = i
    pair_terms, inv_terms = [], []
    for group in by_group.values():
        if "safe" in group and "unsafe" in group:
            pair_terms.append(torch.relu(CFG["margin"]-(logits[group["unsafe"]]-logits[group["safe"]])))
        if "noise" in group:
            n = group["noise"]
            parent = group[rows[n]["row"]["noise_parent"]]
            inv_terms.append((logits[n].sigmoid()-logits[parent].sigmoid()).square())
    pair = torch.stack(pair_terms).mean() if pair_terms else logits.sum()*0
    inv = torch.stack(inv_terms).mean() if inv_terms else logits.sum()*0
    mask = batch["evidence_targets"] >= 0
    evi = nn.functional.binary_cross_entropy_with_logits(evidence[mask], batch["evidence_targets"][mask]) if mask.any() else evidence.sum()*0
    return cls, pair, inv, evi


def run(model_name, seed, encoded):
    run_dir = OUT / f"{model_name}_seed{seed}"
    run_dir.mkdir(exist_ok=False)  # Never overwrite a failed or completed run.
    started = time.time()
    seed_all(seed)
    model = Detector().cuda()
    optimizer = torch.optim.AdamW(model.parameters(), lr=CFG["learning_rate"], weight_decay=CFG["weight_decay"])
    groups = collections.defaultdict(list)
    for r in encoded:
        if r["row"]["experiment_split"] == "train":
            groups[r["row"]["origin_id"]].append(r)
    init_signature = float(model.risk.weight.detach().double().sum())
    steps = 0
    gradient_check = None
    curve = []
    for epoch in range(CFG["epochs"]):
        order = sorted(groups)
        random.Random(seed+epoch).shuffle(order)
        model.train()
        for offset in range(0, len(order), CFG["groups_per_batch"]):
            rows = [r for g in order[offset:offset+CFG["groups_per_batch"]] for r in groups[g]]
            batch = batchify(rows)
            logits, evidence = model(batch)
            cls, pair, inv, evi = losses(logits, evidence, batch, rows)
            loss = cls
            if model_name in ("B3", "B4"):
                loss = loss+CFG["lambda_pair"]*pair+CFG["lambda_inv"]*inv
            if model_name == "B4":
                loss = loss+CFG["lambda_evi"]*evi
                if gradient_check is None and (batch["evidence_targets"] >= 0).any():
                    grad = torch.autograd.grad(evi, model.encoder.embeddings.word_embeddings.weight, retain_graph=True)[0]
                    norm = float(grad.norm())
                    assert norm > 0 and torch.isfinite(grad).all()
                    gradient_check = {"evidence_loss": float(evi.detach()), "encoder_embedding_grad_norm_from_evidence_only": norm,
                                      "supervised_segments": int((batch["evidence_targets"] >= 0).sum())}
            assert torch.isfinite(loss)
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            steps += 1
            curve.append({"epoch": epoch, "step": steps, "cls": float(cls.detach()), "pair": float(pair.detach()), "inv": float(inv.detach()), "evi": float(evi.detach()), "total": float(loss.detach())})
        print(json.dumps({"model": model_name, "seed": seed, "epoch": epoch+1, "loss": curve[-1]}), flush=True)
    if model_name == "B4":
        assert gradient_check is not None
    model.eval()
    predictions = []
    # Single-sample real GPU inference latency; synchronization excludes queued training work.
    with torch.no_grad():
        for r in encoded:
            if r["row"]["experiment_split"] == "train":
                continue
            batch = batchify([r])
            torch.cuda.synchronize()
            start = time.perf_counter()
            logits, evidence = model(batch)
            score = float(logits.sigmoid()[0])
            ev = evidence.sigmoid()[0].tolist()
            torch.cuda.synchronize()
            duration = (time.perf_counter()-start)*1000
            row = r["row"]
            predictions.append({"sample_id": row["sample_id"], "origin_id": row["origin_id"], "model": model_name,
                                "seed": seed, "split": row["experiment_split"], "label": row["label"],
                                "prediction": "unsafe" if score >= CFG["threshold"] else "safe", "unsafe_score": score,
                                "input_ref": "../data.jsonl#"+row["sample_id"], "route": "encoder_only", "latency_ms": duration,
                                "input_tokens": len(r["input_ids"]), "output_tokens": 0, "error_code": None,
                                "truncated": r["truncated"], "original_tokens": r["original_tokens"],
                                "evidence": [{"message_id": mid, "score": s} for mid, s in zip(r["segment_ids"], ev)],
                                "evidence_review_status": "not_human_reviewed", "endpoint": "static_candidate_classification"})
    (run_dir / "predictions.jsonl").write_text("".join(json.dumps(r)+"\n" for r in predictions))
    (run_dir / "losses.jsonl").write_text("".join(json.dumps(r)+"\n" for r in curve))
    # Retain heads and final shared encoder for reproducibility, on remote disk only.
    torch.save(model.state_dict(), run_dir / "checkpoint.pt")
    write(run_dir / "status.json", {"status": "COMPLETED", "model": model_name, "seed": seed, "steps": steps,
                                  "train_rows": sum(len(g) for g in groups.values()), "predictions": len(predictions),
                                  "started_unix": started, "ended_unix": time.time(), "seconds": time.time()-started,
                                  "initial_risk_weight_sum": init_signature, "evidence_gradient_check": gradient_check,
                                  "max_memory_allocated_bytes": torch.cuda.max_memory_allocated()})
    del model, optimizer
    torch.cuda.empty_cache()


def main():
    torch.set_num_threads(4)
    torch.use_deterministic_algorithms(True)
    torch.backends.cudnn.benchmark = False
    torch.backends.cuda.matmul.allow_tf32 = False
    assert torch.cuda.is_available()
    env = {"host": platform.node(), "torch": torch.__version__, "transformers": transformers.__version__,
           "gpu": torch.cuda.get_device_name(0), "cuda": torch.version.cuda, "device_count": torch.cuda.device_count(),
           "start_unix": time.time(), "config": CFG}
    write(ROOT / "server_environment.json", env)
    tokenizer = AutoTokenizer.from_pretrained(CFG["model_path"], local_files_only=True)
    encoded = [encode(tokenizer, r) for r in DATA]
    short = [r for r in encoded if r["row"]["source_dataset"] == "constructed_context_v1"]
    assert not any(r["truncated"] for r in short), "diagnostic evidence outside window; stop before training"
    write(ROOT / "window_audit.json", [{"sample_id": r["row"]["sample_id"], "split": r["row"]["experiment_split"], "tokens": r["original_tokens"], "truncated": r["truncated"], "evidence_targets": r["evidence_targets"]} for r in encoded])
    started = time.time()
    for seed in CFG["seeds"]:
        for name in CFG["models"]:
            assert time.time()-started < CFG["max_gpu_hours"]*3600, "wall-clock hard stop"
            run(name, seed, encoded)
    write(ROOT / "server_complete.json", {"status": "COMPLETED", "runs": len(CFG["seeds"])*len(CFG["models"]), "seconds": time.time()-started, "ended_unix": time.time()})


if __name__ == "__main__":
    main()
