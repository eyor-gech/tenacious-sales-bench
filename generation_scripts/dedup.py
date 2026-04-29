#!/usr/bin/env python3
"""
TenaciousBench Deduplication

Removes near-duplicate tasks from a combined JSONL using:
  1. Exact task_id deduplication (case-insensitive)
  2. Character n-gram overlap on ideal_output
  3. Sentence embedding cosine similarity on ideal_output

Usage:
    python dedup.py \
        --in-dir tenacious_bench_v0.1/filtered \
        --out tenacious_bench_v0.1/deduped.jsonl \
        --ngram-n 6 \
        --ngram-threshold 0.40 \
        --embedding-threshold 0.90
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


def char_ngrams(text: str, n: int) -> Counter:
    text = text.lower().strip()
    return Counter(text[i : i + n] for i in range(len(text) - n + 1))


def ngram_overlap(a: str, b: str, n: int = 6) -> float:
    ca = char_ngrams(a, n)
    cb = char_ngrams(b, n)
    if not ca or not cb:
        return 0.0
    intersection = sum((ca & cb).values())
    union = sum((ca | cb).values())
    return intersection / union if union > 0 else 0.0


def load_tasks(paths: list[Path]) -> list[dict]:
    tasks: list[dict] = []
    for p in paths:
        with p.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    tasks.append(json.loads(line))
    return tasks


def dedup_by_id(tasks: list[dict]) -> tuple[list[dict], int]:
    seen: set[str] = set()
    unique: list[dict] = []
    removed = 0
    for t in tasks:
        tid = t.get("task_id", "").lower()
        if tid in seen:
            removed += 1
        else:
            seen.add(tid)
            unique.append(t)
    return unique, removed


def dedup_by_ngram(
    tasks: list[dict],
    n: int = 6,
    threshold: float = 0.40,
) -> tuple[list[dict], int, list[tuple[str, str, float]]]:
    """
    O(n²) pairwise n-gram dedup. Slow for large sets; use embedding dedup for >500 tasks.
    """
    texts = [t.get("ground_truth", {}).get("ideal_output", "") for t in tasks]
    removed_indices: set[int] = set()
    flagged_pairs: list[tuple[str, str, float]] = []

    for i in range(len(tasks)):
        if i in removed_indices:
            continue
        for j in range(i + 1, len(tasks)):
            if j in removed_indices:
                continue
            overlap = ngram_overlap(texts[i], texts[j], n)
            if overlap >= threshold:
                removed_indices.add(j)
                flagged_pairs.append((
                    tasks[i].get("task_id", str(i)),
                    tasks[j].get("task_id", str(j)),
                    round(overlap, 4),
                ))

    unique = [t for i, t in enumerate(tasks) if i not in removed_indices]
    return unique, len(removed_indices), flagged_pairs


def dedup_by_embedding(
    tasks: list[dict],
    threshold: float = 0.90,
    batch_size: int = 64,
) -> tuple[list[dict], int, list[tuple[str, str, float]]]:
    try:
        from sentence_transformers import SentenceTransformer
        import numpy as np
    except ImportError:
        print("sentence-transformers not installed — skipping embedding dedup.", file=sys.stderr)
        return tasks, 0, []

    model = SentenceTransformer("all-MiniLM-L6-v2")
    texts = [t.get("ground_truth", {}).get("ideal_output", "") for t in tasks]

    # Encode in batches
    embeddings_list = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        embs = model.encode(batch, normalize_embeddings=True, show_progress_bar=False)
        embeddings_list.append(embs)

    import numpy as np
    embeddings = np.vstack(embeddings_list)

    # Cosine similarity matrix (embeddings are already L2-normalised)
    sim_matrix = embeddings @ embeddings.T

    removed_indices: set[int] = set()
    flagged_pairs: list[tuple[str, str, float]] = []

    for i in range(len(tasks)):
        if i in removed_indices:
            continue
        for j in range(i + 1, len(tasks)):
            if j in removed_indices:
                continue
            sim = float(sim_matrix[i, j])
            if sim >= threshold:
                removed_indices.add(j)
                flagged_pairs.append((
                    tasks[i].get("task_id", str(i)),
                    tasks[j].get("task_id", str(j)),
                    round(sim, 4),
                ))

    unique = [t for i, t in enumerate(tasks) if i not in removed_indices]
    return unique, len(removed_indices), flagged_pairs


def renumber_task_ids(tasks: list[dict]) -> list[dict]:
    """Assign clean sequential IDs after deduplication; preserves source_mode prefix."""
    mode_counters: dict[str, int] = {}
    for t in tasks:
        mode = t.get("source_mode", "programmatic")
        prefix = {
            "programmatic": "PROG",
            "multi_llm_synthesis": "SYNTH",
            "trace_derived": "TRACE",
            "hand_authored_adversarial": "ADV",
        }.get(mode, "UNK")
        mode_counters[prefix] = mode_counters.get(prefix, 0) + 1
        t["task_id"] = f"TB-RAW-{prefix}-{mode_counters[prefix]:04d}"
    return tasks


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="TenaciousBench Deduplication")
    p.add_argument("--in-dir", type=Path, default=Path("tenacious_bench_v0.1/filtered"))
    p.add_argument("--out", type=Path, default=Path("tenacious_bench_v0.1/deduped.jsonl"))
    p.add_argument("--ngram-n", type=int, default=6)
    p.add_argument("--ngram-threshold", type=float, default=0.40)
    p.add_argument("--embedding-threshold", type=float, default=0.90)
    p.add_argument("--no-embedding", action="store_true", help="Skip embedding dedup (faster)")
    p.add_argument("--log", type=Path, default=None)
    args = p.parse_args(argv)

    jsonl_files = sorted(args.in_dir.glob("*.jsonl"))
    if not jsonl_files:
        print(f"No JSONL files in {args.in_dir}", file=sys.stderr)
        return 1

    tasks = load_tasks(jsonl_files)
    print(f"Loaded {len(tasks)} tasks from {len(jsonl_files)} files.")

    # Stage 1: ID dedup (case-insensitive)
    tasks, n_id_removed = dedup_by_id(tasks)
    print(f"ID dedup: removed {n_id_removed} duplicates → {len(tasks)} remaining")

    # Stage 2: N-gram dedup
    tasks, n_ngram_removed, ngram_pairs = dedup_by_ngram(tasks, args.ngram_n, args.ngram_threshold)
    print(f"N-gram dedup (n={args.ngram_n}, threshold={args.ngram_threshold}): "
          f"removed {n_ngram_removed} → {len(tasks)} remaining")

    # Stage 3: Embedding dedup
    n_emb_removed = 0
    emb_pairs: list[tuple] = []
    if not args.no_embedding:
        tasks, n_emb_removed, emb_pairs = dedup_by_embedding(tasks, args.embedding_threshold)
        print(f"Embedding dedup (threshold={args.embedding_threshold}): "
              f"removed {n_emb_removed} → {len(tasks)} remaining")

    # Renumber IDs
    tasks = renumber_task_ids(tasks)

    # Write output
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as fh:
        for t in tasks:
            fh.write(json.dumps(t) + "\n")
    print(f"Written {len(tasks)} unique tasks to {args.out}")

    if args.log:
        log_data = {
            "total_input": len(tasks) + n_id_removed + n_ngram_removed + n_emb_removed,
            "total_output": len(tasks),
            "removed_by_id": n_id_removed,
            "removed_by_ngram": n_ngram_removed,
            "removed_by_embedding": n_emb_removed,
            "ngram_flagged_pairs": ngram_pairs,
            "embedding_flagged_pairs": emb_pairs,
        }
        args.log.parent.mkdir(parents=True, exist_ok=True)
        with args.log.open("w", encoding="utf-8") as fh:
            json.dump(log_data, fh, indent=2)

    return 0


if __name__ == "__main__":
    sys.exit(main())
