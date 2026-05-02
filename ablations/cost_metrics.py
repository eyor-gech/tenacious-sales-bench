#!/usr/bin/env python3
"""
Cost and latency metrics for TenaciousBench ablation runs.

Computes per-task cost estimates and prints a cost-quality Pareto table.

Usage:
    python ablations/cost_metrics.py
    python ablations/cost_metrics.py --results ablations/ablation_results.json
"""
from __future__ import annotations

import argparse
import json
import sys


# OpenRouter pricing as of 2026-05-01 (USD per 1k tokens)
_PRICING = {
    "openai/gpt-4o-mini":           {"input": 0.000150, "output": 0.000600},
    "Qwen/Qwen2.5-7B-Instruct":     {"input": 0.000040, "output": 0.000040},  # self-hosted estimate
    "anthropic/claude-3-haiku":     {"input": 0.000250, "output": 0.001250},
}


def cost_per_task(
    tokens_in: int,
    tokens_out: int,
    model: str,
) -> float:
    pricing = _PRICING.get(model, {"input": 0.000150, "output": 0.000600})
    return (tokens_in / 1000) * pricing["input"] + (tokens_out / 1000) * pricing["output"]


def compute_pareto(results: dict) -> list[dict]:
    rows = []

    for key in ["delta_a", "delta_b"]:
        if key not in results:
            continue
        v = results[key]
        cm = v.get("cost_metrics", {})
        rows.append({
            "variant": key,
            "label": v["label"][:55],
            "pass_at_1": v["held_out_pass_at_1"],
            "avg_latency_ms": cm.get("avg_latency_ms", 0),
            "avg_tokens_in": cm.get("avg_tokens_in", 0),
            "avg_tokens_out": cm.get("avg_tokens_out", 0),
            "cost_usd_per_task": cm.get("estimated_cost_usd_per_task", 0.0),
        })

    # Add baseline
    b = results.get("baseline", {})
    rows.append({
        "variant": "baseline",
        "label": "Week 10 GPT-4o-mini baseline",
        "pass_at_1": b.get("held_out_pass_at_1", 0.85),
        "avg_latency_ms": 6764,
        "avg_tokens_in": 610,
        "avg_tokens_out": 188,
        "cost_usd_per_task": 0.000229,
    })

    # Sort by pass@1 descending
    rows.sort(key=lambda r: r["pass_at_1"], reverse=True)
    return rows


def print_pareto_table(rows: list[dict]) -> None:
    header = f"{'Variant':<12} {'pass@1':>7} {'lat ms':>7} {'tok_in':>7} {'tok_out':>7} {'$/task':>10}  Label"
    print("\nCost-Quality Pareto Table")
    print("=" * 90)
    print(header)
    print("-" * 90)
    for r in rows:
        print(
            f"{r['variant']:<12} {r['pass_at_1']:>7.3f} "
            f"{r['avg_latency_ms']:>7.0f} "
            f"{r['avg_tokens_in']:>7} {r['avg_tokens_out']:>7} "
            f"{r['cost_usd_per_task']:>10.6f}  {r['label']}"
        )
    print("=" * 90)

    winner = rows[0]
    print(f"\nPareto winner: {winner['variant']} "
          f"(pass@1={winner['pass_at_1']:.3f}, cost=${winner['cost_usd_per_task']:.6f}/task)")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="TenaciousBench cost metrics")
    p.add_argument("--results", default="ablations/ablation_results.json")
    args = p.parse_args(argv)

    with open(args.results, encoding="utf-8") as f:
        results = json.load(f)

    rows = compute_pareto(results)
    print_pareto_table(rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
