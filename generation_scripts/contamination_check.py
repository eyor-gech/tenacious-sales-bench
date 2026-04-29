#!/usr/bin/env python3
"""
TenaciousBench Contamination Check

Verifies that the three splits are clean:
  1. N-gram overlap (character 6-gram Jaccard) between held_out × (train + dev)
  2. Embedding cosine similarity between held_out × (train + dev)
  3. Time-shift: held_out signal_dates >= 2026-04-01
  4. Company ID isolation: no company_id in both held_out and train/dev
  5. Case-insensitive task ID uniqueness

Writes results to contamination_check.json.

Usage:
    python contamination_check.py \
        --train tenacious_bench_v0.1/train/train.jsonl \
        --dev   tenacious_bench_v0.1/dev/dev.jsonl \
        --held  tenacious_bench_v0.1/held_out/held_out.jsonl \
        --out   contamination_check.json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any


NGRAM_THRESHOLD = 0.30
EMBEDDING_THRESHOLD = 0.85
HELD_OUT_MIN_SIGNAL_DATE = date(2026, 4, 1)
TRAIN_DEV_MIN_SIGNAL_DATE = date(2026, 1, 1)


# ── N-gram utilities ─────────────────────────────────────────────────────────

def char_ngrams(text: str, n: int = 6) -> Counter:
    text = text.lower().strip()
    return Counter(text[i : i + n] for i in range(len(text) - n + 1))


def jaccard_overlap(a: str, b: str, n: int = 6) -> float:
    ca, cb = char_ngrams(a, n), char_ngrams(b, n)
    if not ca or not cb:
        return 0.0
    intersection = sum((ca & cb).values())
    union = sum((ca | cb).values())
    return intersection / union if union else 0.0


def _task_text(task: dict) -> str:
    return (
        task.get("ground_truth", {}).get("ideal_output", "")
        + " "
        + task.get("input", {}).get("task_instruction", "")
    )


# ── Checks ───────────────────────────────────────────────────────────────────

def check_ngram_overlap(
    held: list[dict],
    train_dev: list[dict],
    threshold: float = NGRAM_THRESHOLD,
    n: int = 6,
) -> dict:
    held_texts = [(t["task_id"], _task_text(t)) for t in held]
    td_texts = [(t["task_id"], _task_text(t)) for t in train_dev]

    flagged: list[dict] = []
    max_overlap = 0.0
    max_pair: dict = {}
    pairs_checked = len(held) * len(train_dev)

    for h_id, h_text in held_texts:
        for td_id, td_text in td_texts:
            overlap = jaccard_overlap(h_text, td_text, n)
            if overlap > max_overlap:
                max_overlap = overlap
                max_pair = {"task_a": h_id, "task_b": td_id, "overlap": round(overlap, 4)}
            if overlap >= threshold:
                flagged.append({"held_task": h_id, "train_dev_task": td_id, "overlap": round(overlap, 4)})

    return {
        "method": f"character_{n}gram",
        "pairs_checked": pairs_checked,
        "cross_split_pairs_above_threshold": len(flagged),
        "max_observed_overlap": round(max_overlap, 4),
        "max_overlap_pair": max_pair,
        "verdict": "PASS" if len(flagged) == 0 else "FAIL",
        "flagged_tasks": [f["held_task"] for f in flagged],
        "flagged_pairs": flagged,
    }


def check_embedding_similarity(
    held: list[dict],
    train_dev: list[dict],
    threshold: float = EMBEDDING_THRESHOLD,
) -> dict:
    try:
        from sentence_transformers import SentenceTransformer
        import numpy as np
    except ImportError:
        return {
            "method": "sentence-transformers/all-MiniLM-L6-v2",
            "pairs_checked": 0,
            "pairs_above_threshold": 0,
            "max_observed_similarity": None,
            "verdict": "SKIPPED",
            "note": "sentence-transformers not installed",
            "flagged_tasks": [],
        }

    model = SentenceTransformer("all-MiniLM-L6-v2")

    held_texts = [_task_text(t) for t in held]
    td_texts = [_task_text(t) for t in train_dev]

    import numpy as np
    held_embs = model.encode(held_texts, normalize_embeddings=True, show_progress_bar=False)
    td_embs = model.encode(td_texts, normalize_embeddings=True, show_progress_bar=False)

    sim_matrix = held_embs @ td_embs.T

    flagged: list[dict] = []
    max_sim = float(sim_matrix.max()) if len(sim_matrix) > 0 else 0.0
    max_indices = divmod(int(sim_matrix.argmax()), sim_matrix.shape[1]) if len(sim_matrix) > 0 else (0, 0)

    for i in range(len(held)):
        for j in range(len(train_dev)):
            sim = float(sim_matrix[i, j])
            if sim >= threshold:
                flagged.append({
                    "held_task": held[i]["task_id"],
                    "train_dev_task": train_dev[j]["task_id"],
                    "similarity": round(sim, 4),
                })

    return {
        "method": "sentence-transformers/all-MiniLM-L6-v2",
        "field_scored": "ground_truth.ideal_output + input.task_instruction",
        "pairs_checked": len(held) * len(train_dev),
        "pairs_above_threshold": len(flagged),
        "max_observed_similarity": round(max_sim, 4),
        "max_similarity_pair": {
            "task_a": held[max_indices[0]]["task_id"] if held else "",
            "task_b": train_dev[max_indices[1]]["task_id"] if train_dev else "",
            "similarity": round(max_sim, 4),
        } if held and train_dev else {},
        "verdict": "PASS" if len(flagged) == 0 else "FAIL",
        "flagged_tasks": [f["held_task"] for f in flagged],
    }


def check_time_shift(
    held: list[dict],
    train_dev: list[dict],
    held_min: date = HELD_OUT_MIN_SIGNAL_DATE,
    td_min: date = TRAIN_DEV_MIN_SIGNAL_DATE,
) -> dict:
    held_violations: list[dict] = []
    td_violations: list[dict] = []

    def parse_date(s: str) -> date | None:
        try:
            return date.fromisoformat(s)
        except (ValueError, TypeError):
            return None

    for t in held:
        sig_date_str = t.get("input", {}).get("signal_brief", {}).get("signal_date", "")
        d = parse_date(sig_date_str)
        if d and d < held_min:
            held_violations.append({"task_id": t["task_id"], "signal_date": sig_date_str})

    for t in train_dev:
        sig_date_str = t.get("input", {}).get("signal_brief", {}).get("signal_date", "")
        d = parse_date(sig_date_str)
        if d and d < td_min:
            td_violations.append({"task_id": t["task_id"], "signal_date": sig_date_str})

    held_dates = [
        t.get("input", {}).get("signal_brief", {}).get("signal_date", "")
        for t in held if t.get("input", {}).get("signal_brief", {}).get("signal_date")
    ]
    td_dates = [
        t.get("input", {}).get("signal_brief", {}).get("signal_date", "")
        for t in train_dev if t.get("input", {}).get("signal_brief", {}).get("signal_date")
    ]

    return {
        "method": "signal_date_comparison",
        "rule": f"held_out >= {held_min.isoformat()}; train/dev >= {td_min.isoformat()}",
        "held_out_violations": len(held_violations),
        "train_dev_violations": len(td_violations),
        "held_out_signal_date_range": {
            "min": min(held_dates) if held_dates else None,
            "max": max(held_dates) if held_dates else None,
        },
        "train_dev_signal_date_range": {
            "min": min(td_dates) if td_dates else None,
            "max": max(td_dates) if td_dates else None,
        },
        "verdict": "PASS" if not held_violations and not td_violations else "FAIL",
        "held_violations": held_violations,
        "td_violations": td_violations,
    }


def check_company_id_isolation(
    held: list[dict],
    train_dev: list[dict],
) -> dict:
    held_ids = {
        t["input"]["company_context"]["company_id"]
        for t in held
        if "company_id" in t.get("input", {}).get("company_context", {})
    }
    td_ids = {
        t["input"]["company_context"]["company_id"]
        for t in train_dev
        if "company_id" in t.get("input", {}).get("company_context", {})
    }
    collisions = list(held_ids & td_ids)

    return {
        "method": "exact_match",
        "rule": "No company_id may appear in both held_out and train/dev",
        "cross_split_company_id_collisions": len(collisions),
        "verdict": "PASS" if not collisions else "FAIL",
        "collision_ids": collisions,
    }


def check_task_id_uniqueness(all_tasks: list[dict]) -> dict:
    ids_lower = [t.get("task_id", "").lower() for t in all_tasks]
    seen: set[str] = set()
    collisions: list[str] = []
    for tid in ids_lower:
        if tid in seen:
            collisions.append(tid)
        seen.add(tid)

    return {
        "method": "lowercase_normalisation_then_exact_match",
        "note": "Addresses P19 — case-sensitive task ID deduplication failure from Week 10",
        "total_tasks": len(all_tasks),
        "collisions_detected": len(collisions),
        "verdict": "PASS" if not collisions else "FAIL",
        "collision_ids": collisions,
    }


# ── Main ─────────────────────────────────────────────────────────────────────

def load_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="TenaciousBench Contamination Check")
    p.add_argument("--train", type=Path, required=True)
    p.add_argument("--dev", type=Path, required=True)
    p.add_argument("--held", type=Path, required=True)
    p.add_argument("--out", type=Path, default=Path("contamination_check.json"))
    p.add_argument("--ngram-threshold", type=float, default=NGRAM_THRESHOLD)
    p.add_argument("--embedding-threshold", type=float, default=EMBEDDING_THRESHOLD)
    p.add_argument("--no-embedding", action="store_true")
    args = p.parse_args(argv)

    for path in [args.train, args.dev, args.held]:
        if not path.exists():
            print(f"File not found: {path}", file=sys.stderr)
            return 1

    train_tasks = load_jsonl(args.train)
    dev_tasks = load_jsonl(args.dev)
    held_tasks = load_jsonl(args.held)
    train_dev = train_tasks + dev_tasks
    all_tasks = train_tasks + dev_tasks + held_tasks

    print(f"Checking contamination: {len(train_tasks)} train, {len(dev_tasks)} dev, {len(held_tasks)} held_out")

    report: dict[str, Any] = {
        "version": "0.1.0",
        "run_date": __import__("datetime").datetime.utcnow().isoformat() + "Z",
        "splits_checked": {
            "train": str(args.train),
            "dev": str(args.dev),
            "held_out": str(args.held),
        },
        "thresholds": {
            "ngram_overlap_max": args.ngram_threshold,
            "embedding_similarity_max": args.embedding_threshold,
        },
    }

    # 1. N-gram
    print("Running n-gram overlap check...")
    report["ngram_overlap"] = check_ngram_overlap(held_tasks, train_dev, args.ngram_threshold)
    print(f"  N-gram: {report['ngram_overlap']['verdict']} "
          f"(max overlap: {report['ngram_overlap']['max_observed_overlap']})")

    # 2. Embedding
    if not args.no_embedding:
        print("Running embedding similarity check...")
        report["embedding_similarity"] = check_embedding_similarity(
            held_tasks, train_dev, args.embedding_threshold
        )
        print(f"  Embedding: {report['embedding_similarity']['verdict']} "
              f"(max sim: {report['embedding_similarity'].get('max_observed_similarity')})")

    # 3. Time-shift
    print("Running time-shift verification...")
    report["time_shift_verification"] = check_time_shift(held_tasks, train_dev)
    print(f"  Time-shift: {report['time_shift_verification']['verdict']}")

    # 4. Company ID isolation
    report["company_id_isolation"] = check_company_id_isolation(held_tasks, train_dev)
    print(f"  Company ID isolation: {report['company_id_isolation']['verdict']}")

    # 5. Task ID uniqueness
    report["task_id_case_sensitivity"] = check_task_id_uniqueness(all_tasks)
    print(f"  Task ID uniqueness: {report['task_id_case_sensitivity']['verdict']}")

    # Overall verdict
    verdicts = [
        v["verdict"]
        for v in [
            report["ngram_overlap"],
            report.get("embedding_similarity", {"verdict": "SKIPPED"}),
            report["time_shift_verification"],
            report["company_id_isolation"],
            report["task_id_case_sensitivity"],
        ]
        if v["verdict"] != "SKIPPED"
    ]
    report["overall_verdict"] = "PASS" if all(v == "PASS" for v in verdicts) else "FAIL"
    report["summary"] = (
        f"Overall: {report['overall_verdict']}. "
        f"N-gram: {report['ngram_overlap']['verdict']}. "
        f"Time-shift: {report['time_shift_verification']['verdict']}. "
        f"Company ID: {report['company_id_isolation']['verdict']}. "
        f"Task ID: {report['task_id_case_sensitivity']['verdict']}."
    )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
    print(f"\nReport written to {args.out}")
    print(f"Overall verdict: {report['overall_verdict']}")

    return 0 if report["overall_verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
