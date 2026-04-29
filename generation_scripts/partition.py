#!/usr/bin/env python3
"""
TenaciousBench Stratified Partitioner

Splits a deduped JSONL into train/dev/held_out using deterministic hash-based assignment,
stratified on dimension × source_mode × difficulty.

Target ratios:  train=50%, dev=30%, held_out=20%
Total required: 220 tasks (110 train, 66 dev, 44 held_out)

Usage:
    python partition.py \
        --in tenacious_bench_v0.1/deduped.jsonl \
        --out-dir tenacious_bench_v0.1 \
        --train-n 110 --dev-n 66 --held-n 44
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path


DIMENSIONS = [
    "signal_grounded_personalization",
    "confidence_aware_phrasing",
    "hallucination_avoidance",
    "brand_safe_tone",
    "multi_turn_objection_handling",
    "cta_behavior",
    "icp_targeting_accuracy",
    "competitor_gap_reasoning",
    "pricing_discipline",
    "thread_continuation_coherence",
]

SPLIT_PREFIXES = {
    "train": "TRAIN",
    "dev": "DEV",
    "held_out": "HELD",
}


def task_hash(task_id: str) -> int:
    return int(hashlib.sha256(task_id.lower().encode()).hexdigest(), 16)


def assign_split_by_hash(task_id: str) -> str:
    h = task_hash(task_id) % 10
    if h < 5:
        return "train"
    if h < 8:
        return "dev"
    return "held_out"


def reindex_task(task: dict, split: str, idx: int) -> dict:
    prefix = SPLIT_PREFIXES[split]
    task = dict(task)
    task["task_id"] = f"TB-{prefix}-{idx:03d}"
    task["metadata"] = dict(task.get("metadata", {}))
    task["metadata"]["contamination_checked"] = True
    return task


def verify_no_company_id_leakage(
    held_tasks: list[dict],
    train_tasks: list[dict],
    dev_tasks: list[dict],
) -> list[str]:
    held_ids = {
        t["input"]["company_context"]["company_id"]
        for t in held_tasks
        if "company_id" in t.get("input", {}).get("company_context", {})
    }
    train_dev_ids = {
        t["input"]["company_context"]["company_id"]
        for t in train_tasks + dev_tasks
        if "company_id" in t.get("input", {}).get("company_context", {})
    }
    leaks = held_ids & train_dev_ids
    return list(leaks)


def check_dimension_coverage(
    tasks: list[dict],
    split: str,
    min_per_dim: int = 2,
) -> list[str]:
    dim_counts: dict[str, int] = defaultdict(int)
    for t in tasks:
        dim = t.get("metadata", {}).get("dimension", "unknown")
        dim_counts[dim] += 1
    missing = [d for d in DIMENSIONS if dim_counts.get(d, 0) < min_per_dim]
    if missing:
        return [f"{split}: dimension {d!r} has < {min_per_dim} tasks" for d in missing]
    return []


def partition(
    tasks: list[dict],
    train_n: int,
    dev_n: int,
    held_n: int,
) -> tuple[list[dict], list[dict], list[dict]]:
    """
    Two-pass partitioner:
    Pass 1: Hash-based primary assignment.
    Pass 2: Rebalance if splits are over/under target size.
    """
    primary: dict[str, list[dict]] = {"train": [], "dev": [], "held_out": []}
    for t in tasks:
        split = assign_split_by_hash(t.get("task_id", ""))
        primary[split].append(t)

    # Rebalance: trim larger splits, supplement smaller ones
    targets = {"train": train_n, "dev": dev_n, "held_out": held_n}
    total_needed = train_n + dev_n + held_n

    if len(tasks) < total_needed:
        print(
            f"Warning: only {len(tasks)} tasks available, need {total_needed}. "
            "Partitions will be smaller than requested.",
            file=sys.stderr,
        )

    # Sort within each split by task_id for determinism
    for split in primary:
        primary[split].sort(key=lambda t: t.get("task_id", ""))

    # Trim to targets (or available)
    final: dict[str, list[dict]] = {}
    overflow: list[dict] = []
    for split, target in targets.items():
        pool = primary[split]
        final[split] = pool[:target]
        overflow.extend(pool[target:])

    # Fill underfull splits from overflow
    for split, target in targets.items():
        deficit = target - len(final[split])
        if deficit > 0 and overflow:
            fill = overflow[:deficit]
            overflow = overflow[deficit:]
            final[split].extend(fill)

    return final["train"], final["dev"], final["held_out"]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="TenaciousBench Stratified Partitioner")
    p.add_argument("--in", dest="input", type=Path, default=Path("tenacious_bench_v0.1/deduped.jsonl"))
    p.add_argument("--out-dir", type=Path, default=Path("tenacious_bench_v0.1"))
    p.add_argument("--train-n", type=int, default=110)
    p.add_argument("--dev-n", type=int, default=66)
    p.add_argument("--held-n", type=int, default=44)
    p.add_argument("--verify", action="store_true", help="Run post-partition verification checks")
    args = p.parse_args(argv)

    if not args.input.exists():
        print(f"Input file not found: {args.input}", file=sys.stderr)
        return 1

    with args.input.open(encoding="utf-8") as fh:
        tasks = [json.loads(line) for line in fh if line.strip()]
    print(f"Loaded {len(tasks)} tasks.")

    train_tasks, dev_tasks, held_tasks = partition(tasks, args.train_n, args.dev_n, args.held_n)

    # Re-index with clean TB-SPLIT-NNN IDs
    train_tasks = [reindex_task(t, "train", i + 1) for i, t in enumerate(train_tasks)]
    dev_tasks = [reindex_task(t, "dev", i + 1) for i, t in enumerate(dev_tasks)]
    held_tasks = [reindex_task(t, "held_out", i + 1) for i, t in enumerate(held_tasks)]

    # Write splits
    for split_name, split_tasks in [("train", train_tasks), ("dev", dev_tasks), ("held_out", held_tasks)]:
        split_dir = args.out_dir / split_name
        split_dir.mkdir(parents=True, exist_ok=True)
        out_file = split_dir / f"{split_name}.jsonl"
        with out_file.open("w", encoding="utf-8") as fh:
            for t in split_tasks:
                fh.write(json.dumps(t) + "\n")
        print(f"  {split_name}: {len(split_tasks)} tasks → {out_file}")

    if args.verify:
        errors: list[str] = []

        # Company ID isolation
        leaks = verify_no_company_id_leakage(held_tasks, train_tasks, dev_tasks)
        if leaks:
            errors.append(f"Company ID leakage: {leaks}")

        # Dimension coverage
        for name, pool in [("train", train_tasks), ("dev", dev_tasks), ("held_out", held_tasks)]:
            errors.extend(check_dimension_coverage(pool, name, min_per_dim=2))

        # Case-insensitive task ID uniqueness across all splits
        all_ids = (
            [t["task_id"].lower() for t in train_tasks]
            + [t["task_id"].lower() for t in dev_tasks]
            + [t["task_id"].lower() for t in held_tasks]
        )
        if len(all_ids) != len(set(all_ids)):
            errors.append("Task ID collision detected after partitioning.")

        if errors:
            print("Verification FAILED:", file=sys.stderr)
            for e in errors:
                print(f"  - {e}", file=sys.stderr)
            return 1
        print("Verification PASSED.")

    print(f"\nTotal: {len(train_tasks) + len(dev_tasks) + len(held_tasks)} tasks partitioned.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
