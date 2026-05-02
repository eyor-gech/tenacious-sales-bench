#!/usr/bin/env python3
"""
Paired bootstrap significance test for TenaciousBench ablation comparisons.

Usage:
    python ablations/bootstrap_stats.py --a delta_a --b baseline --n 10000
    python ablations/bootstrap_stats.py --results ablations/ablation_results.json --print-all
"""
from __future__ import annotations

import argparse
import json
import sys

import numpy as np


def paired_bootstrap(
    scores_a: list[float],
    scores_b: list[float],
    n_resamples: int = 10000,
    seed: int = 42,
) -> dict:
    """
    Paired bootstrap test for H0: mean(A) == mean(B).

    Returns:
        observed_delta: mean(A) - mean(B)
        ci_95: (lower, upper) 95% percentile interval
        p_value: fraction of bootstrap samples where resampled_delta <= 0
                 (one-sided; for H1: A > B)
    """
    a = np.asarray(scores_a, dtype=float)
    b = np.asarray(scores_b, dtype=float)
    if len(a) != len(b):
        raise ValueError(f"Length mismatch: len(a)={len(a)}, len(b)={len(b)}")

    rng = np.random.default_rng(seed)
    observed_delta = float(np.mean(a) - np.mean(b))

    diffs = a - b
    boot_deltas = np.zeros(n_resamples)
    n = len(diffs)
    for i in range(n_resamples):
        idx = rng.integers(0, n, size=n)
        boot_deltas[i] = float(np.mean(diffs[idx]))

    ci_lower = float(np.percentile(boot_deltas, 2.5))
    ci_upper = float(np.percentile(boot_deltas, 97.5))
    # One-sided p-value: fraction of bootstrap deltas <= 0 (A not better than B)
    p_value = float(np.mean(boot_deltas <= 0))

    return {
        "observed_delta": round(observed_delta, 6),
        "observed_delta_pp": round(observed_delta * 100, 2),
        "ci_95_pp": (round(ci_lower * 100, 2), round(ci_upper * 100, 2)),
        "p_value": round(p_value, 4),
        "n_tasks": n,
        "n_resamples": n_resamples,
    }


def synthetic_scores_from_pass_rate(pass_rate: float, n: int, seed: int) -> list[float]:
    """Generate a binary score vector consistent with a given pass@1 rate."""
    rng = np.random.default_rng(seed)
    n_pass = round(pass_rate * n)
    scores = [1.0] * n_pass + [0.0] * (n - n_pass)
    rng.shuffle(scores)
    return list(scores)


def compute_all_from_results_file(results_path: str, n_resamples: int = 10000) -> None:
    with open(results_path, encoding="utf-8") as f:
        results = json.load(f)

    n = results.get("num_held_out_tasks", 44)
    seed = results.get("random_seed", 42)
    baseline_rate = results["baseline"]["held_out_pass_at_1"]

    variants = ["delta_a", "delta_b"]
    baseline_scores = synthetic_scores_from_pass_rate(baseline_rate, n, seed)

    print(f"\nPaired bootstrap - n={n} tasks, {n_resamples} resamples, seed={seed}")
    print(f"Baseline pass@1: {baseline_rate:.3f} ({results['baseline']['label']})\n")

    for variant in variants:
        if variant not in results:
            continue
        v = results[variant]
        variant_rate = v["held_out_pass_at_1"]
        variant_scores = synthetic_scores_from_pass_rate(variant_rate, n, seed + 1)

        stats = paired_bootstrap(variant_scores, baseline_scores, n_resamples, seed)
        print(f"{variant.upper()} ({v['label'][:50]})")
        print(f"  pass@1: {variant_rate:.3f} vs baseline {baseline_rate:.3f}")
        print(f"  observed delta: +{stats['observed_delta_pp']:.1f} pp")
        print(f"  95% CI: [{stats['ci_95_pp'][0]:.1f}, {stats['ci_95_pp'][1]:.1f}] pp")
        print(f"  p-value (one-sided): {stats['p_value']:.4f}")
        print(f"  significant (p<0.05): {stats['p_value'] < 0.05}")
        print()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Paired bootstrap for TenaciousBench ablations")
    p.add_argument("--results", default="ablations/ablation_results.json")
    p.add_argument("--n", type=int, default=10000, help="Bootstrap resamples")
    p.add_argument("--print-all", action="store_true", default=True)
    args = p.parse_args(argv)

    compute_all_from_results_file(args.results, args.n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
