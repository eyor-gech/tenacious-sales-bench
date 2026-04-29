#!/usr/bin/env python3
"""
End-to-end walkthrough: apply score_task to the three example tasks.

Run from the repo root:
    python examples/run_examples.py

No API key required — tone dimension falls back to the lexical fast-path.

Expected results (deterministic, no LLM calls needed):
  TB-EX-001  ~0.88  PASS   signal grounding pass
  TB-EX-002  ~1.00  PASS   correct ICP abstain
  TB-EX-003  ~0.27  FAIL   banned phrase + tone violations
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Allow running from examples/ or repo root.
sys.path.insert(0, str(Path(__file__).parent.parent))
from scoring_evaluator import score_task

EXAMPLES = [
    Path(__file__).parent / "ex1_signal_grounding_pass.json",
    Path(__file__).parent / "ex2_icp_abstain_correct.json",
    Path(__file__).parent / "ex3_banned_phrase_fail.json",
]


def main() -> None:
    for path in EXAMPLES:
        task = json.loads(path.read_text(encoding="utf-8"))
        result = score_task(task)

        status = "PASS" if result.passed else "FAIL"
        print(f"\n{'='*60}")
        print(f"Task:    {result.task_id}  ({status}  {result.total_score:.3f} / threshold {result.pass_threshold})")
        print(f"Latency: {result.latency_ms:.1f} ms   Model calls: {result.model_calls}")
        print("Dimensions:")
        for d in result.dimensions:
            bar = "#" * int(d.raw_score * 20)
            print(f"  {d.name:<30} raw={d.raw_score:.2f}  w={d.weight:.2f}  weighted={d.weighted:.3f}")
            print(f"    {bar:<20}  {d.reason}")
        if result.errors:
            print(f"Errors: {result.errors}")

    print(f"\n{'='*60}")
    print("Done.")


if __name__ == "__main__":
    main()
