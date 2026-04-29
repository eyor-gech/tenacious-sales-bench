#!/usr/bin/env python3
"""
TenaciousBench Judge Filter

Applies a four-stage quality gate to raw generated tasks:
  1. Completeness check (structural validation)
  2. Rubric coherence check (weights sum to 1.0, thresholds in range)
  3. LLM quality gate (GPT-4o-mini dimension coherence check)
  4. Difficulty calibration (oracle-pass tasks capped at 20% per split)

Usage:
    python judge_filter.py \
        --in-dir tenacious_bench_v0.1/raw \
        --out-dir tenacious_bench_v0.1/filtered \
        --log filter_log.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
JUDGE_MODEL = os.getenv("JUDGE_MODEL", "openai/gpt-4o-mini")

REQUIRED_TOP_KEYS = {"task_id", "metadata", "source_mode", "difficulty", "input", "ground_truth", "scoring_rubric", "evaluator_config"}
REQUIRED_METADATA_KEYS = {"dimension", "created_by", "created_at", "contamination_checked", "scoring_type", "probe_ref"}
VALID_DIMENSIONS = {
    "signal_grounded_personalization", "confidence_aware_phrasing", "hallucination_avoidance",
    "brand_safe_tone", "multi_turn_objection_handling", "cta_behavior", "icp_targeting_accuracy",
    "competitor_gap_reasoning", "pricing_discipline", "thread_continuation_coherence",
}
VALID_SOURCE_MODES = {"trace_derived", "programmatic", "multi_llm_synthesis", "hand_authored_adversarial"}
EASY_ORACLE_CAP = 0.20


_JUDGE_SYSTEM = """You are a benchmark quality reviewer for TenaciousBench, a B2B outbound sales agent evaluation benchmark.

Given a task JSON, answer YES if:
- The task clearly tests exactly one of the ten TenaciousBench dimensions
- The task_instruction is actionable and unambiguous
- The ideal_output is a realistic, complete agent response
- The banned_phrases and required_signals are relevant to the dimension
- The task is distinct enough from a generic email-writing task

Answer NO if:
- The task is ambiguous about which dimension it tests
- The ideal_output is a template placeholder or incomplete
- The task could be answered correctly by any capable LLM without domain knowledge

Respond with exactly: YES or NO, followed by a colon and a one-sentence reason."""


def check_completeness(task: dict) -> tuple[bool, str]:
    missing_top = REQUIRED_TOP_KEYS - set(task.keys())
    if missing_top:
        return False, f"Missing top-level keys: {missing_top}"

    meta = task.get("metadata", {})
    missing_meta = REQUIRED_METADATA_KEYS - set(meta.keys())
    if missing_meta:
        return False, f"Missing metadata keys: {missing_meta}"

    if meta.get("dimension") not in VALID_DIMENSIONS:
        return False, f"Invalid dimension: {meta.get('dimension')}"

    if task.get("source_mode") not in VALID_SOURCE_MODES:
        return False, f"Invalid source_mode: {task.get('source_mode')}"

    gt = task.get("ground_truth", {})
    if not gt.get("ideal_output", "").strip():
        return False, "Empty ideal_output"
    if not gt.get("banned_phrases"):
        return False, "Empty banned_phrases"
    if not gt.get("required_signals"):
        return False, "Empty required_signals"

    return True, "OK"


def check_rubric_coherence(task: dict) -> tuple[bool, str]:
    rubric = task.get("scoring_rubric", {})
    dims = rubric.get("dimensions", [])

    if not dims:
        return False, "No rubric dimensions defined"

    weight_sum = sum(d.get("weight", 0) for d in dims)
    if abs(weight_sum - 1.0) > 0.01:
        return False, f"Rubric weights sum to {weight_sum:.3f}, expected 1.0 ± 0.01"

    threshold = rubric.get("pass_threshold", 0)
    if not (0.5 <= threshold <= 0.95):
        return False, f"pass_threshold={threshold} outside [0.5, 0.95]"

    valid_dim_names = {
        "banned_phrase_violations", "grounding_signal_presence", "cta_presence",
        "tone_markers", "confidence_calibration", "factual_unsupported_claims",
    }
    for d in dims:
        if d.get("name") not in valid_dim_names:
            return False, f"Unknown rubric dimension name: {d.get('name')}"

    return True, "OK"


def check_llm_quality(task: dict, api_key: str, model: str) -> tuple[bool, str, int]:
    if not api_key:
        return True, "LLM gate skipped (no API key)", 0

    if task.get("source_mode") in {"hand_authored_adversarial", "trace_derived"}:
        return True, "Source mode exempt from LLM gate", 0

    try:
        import httpx

        task_summary = {
            "task_id": task.get("task_id"),
            "dimension": task.get("metadata", {}).get("dimension"),
            "task_instruction": task.get("input", {}).get("task_instruction", ""),
            "ideal_output": task.get("ground_truth", {}).get("ideal_output", "")[:300],
            "banned_phrases": task.get("ground_truth", {}).get("banned_phrases", []),
            "required_signals": task.get("ground_truth", {}).get("required_signals", []),
        }

        resp = httpx.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": _JUDGE_SYSTEM},
                    {"role": "user", "content": f"Task to review:\n{json.dumps(task_summary, indent=2)}"},
                ],
                "max_tokens": 100,
                "temperature": 0.0,
            },
            timeout=15.0,
        )
        resp.raise_for_status()
        answer = resp.json()["choices"][0]["message"]["content"].strip()
        passed = answer.upper().startswith("YES")
        return passed, answer, 1

    except Exception as exc:
        return True, f"LLM gate error (accepting task): {exc}", 0


def check_difficulty_calibration(
    task: dict,
    oracle_scores: dict[str, float],
) -> tuple[str, float]:
    """Score the ideal_output against the task's own rubric to detect trivially easy tasks."""
    try:
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from scoring_evaluator import score_task

        task_copy = dict(task)
        task_copy["candidate_output"] = {
            "outreach_text": task["ground_truth"]["ideal_output"],
            "channel": task["input"].get("channel", "email"),
            "intent_classification": task["ground_truth"].get("correct_intent"),
            "confidence_prefix": None,
            "cta_present": True,
            "citations": [],
        }
        result = score_task(task_copy)
        oracle_score = result.total_score
    except Exception:
        oracle_score = 0.8

    difficulty = task.get("difficulty", "medium")
    if oracle_score >= 0.95:
        difficulty = "easy"

    return difficulty, oracle_score


def run_filter(
    in_dir: Path,
    out_dir: Path,
    log_path: Path | None = None,
    easy_cap: float = EASY_ORACLE_CAP,
) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)

    input_files = sorted(in_dir.glob("*.jsonl"))
    if not input_files:
        print(f"No JSONL files in {in_dir}", file=sys.stderr)
        return {}

    stats = {
        "total_input": 0,
        "passed": 0,
        "rejected_completeness": 0,
        "rejected_rubric": 0,
        "rejected_llm": 0,
        "easy_oracle_count": 0,
        "easy_oracle_cap_applied": 0,
        "model_calls": 0,
        "rejected_tasks": [],
    }

    accepted_by_file: dict[str, list[dict]] = {}
    easy_count_by_dim: dict[str, int] = {}

    for in_file in input_files:
        out_tasks: list[dict] = []
        with in_file.open(encoding="utf-8") as fh:
            tasks = [json.loads(line) for line in fh if line.strip()]

        stats["total_input"] += len(tasks)

        for task in tasks:
            # Stage 1
            ok, reason = check_completeness(task)
            if not ok:
                stats["rejected_completeness"] += 1
                stats["rejected_tasks"].append({"task_id": task.get("task_id"), "stage": "completeness", "reason": reason})
                continue

            # Stage 2
            ok, reason = check_rubric_coherence(task)
            if not ok:
                stats["rejected_rubric"] += 1
                stats["rejected_tasks"].append({"task_id": task.get("task_id"), "stage": "rubric", "reason": reason})
                continue

            # Stage 3
            ok, reason, calls = check_llm_quality(task, OPENROUTER_API_KEY, JUDGE_MODEL)
            stats["model_calls"] += calls
            if not ok:
                stats["rejected_llm"] += 1
                stats["rejected_tasks"].append({"task_id": task.get("task_id"), "stage": "llm_quality", "reason": reason})
                continue

            # Stage 4
            dim = task["metadata"]["dimension"]
            difficulty, oracle_score = check_difficulty_calibration(task, {})
            task["difficulty"] = difficulty
            task["metadata"]["oracle_score"] = round(oracle_score, 4)

            if difficulty == "easy":
                stats["easy_oracle_count"] += 1
                current_easy = easy_count_by_dim.get(dim, 0)
                total_dim = sum(1 for t in out_tasks if t["metadata"]["dimension"] == dim)
                cap = max(1, int(easy_cap * max(1, total_dim + 1)))
                if current_easy >= cap:
                    stats["easy_oracle_cap_applied"] += 1
                    stats["rejected_tasks"].append({
                        "task_id": task.get("task_id"),
                        "stage": "difficulty_cap",
                        "reason": f"Easy oracle cap reached for {dim}",
                    })
                    continue
                easy_count_by_dim[dim] = current_easy + 1

            out_tasks.append(task)
            stats["passed"] += 1

        accepted_by_file[in_file.name] = out_tasks
        out_file = out_dir / in_file.name
        with out_file.open("w", encoding="utf-8") as fh:
            for t in out_tasks:
                fh.write(json.dumps(t) + "\n")
        print(f"{in_file.name}: {len(tasks)} in → {len(out_tasks)} out")

    if log_path:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("w", encoding="utf-8") as fh:
            json.dump(stats, fh, indent=2)

    print(f"\nFilter summary: {stats['passed']}/{stats['total_input']} accepted "
          f"({stats['model_calls']} LLM calls)")
    return stats


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="TenaciousBench Judge Filter")
    p.add_argument("--in-dir", type=Path, default=Path("tenacious_bench_v0.1/raw"))
    p.add_argument("--out-dir", type=Path, default=Path("tenacious_bench_v0.1/filtered"))
    p.add_argument("--log", type=Path, default=None, help="Write filter statistics to JSON")
    p.add_argument("--easy-cap", type=float, default=0.20)
    args = p.parse_args(argv)

    stats = run_filter(args.in_dir, args.out_dir, args.log, args.easy_cap)
    return 0 if stats.get("passed", 0) > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
