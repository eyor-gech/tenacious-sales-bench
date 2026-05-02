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
SYNTHESIS_MODEL = os.getenv("SYNTHESIS_MODEL", "openai/gpt-4o-mini")

# Two-tier judge separation (see generation_scripts/prompts/routing_policy.md § "Cheap vs Eval-Tier").
# DEV_TIER_JUDGE  — cheap model used for bulk filtering of all tasks (~95% of LLM calls).
# EVAL_TIER_JUDGE — stronger model used on a random calibration subsample (~10% of accepted tasks)
#                   to verify that the dev-tier judge's accept/reject decisions are well-calibrated.
#                   If calibration agreement < CALIBRATION_MIN_AGREEMENT the threshold is flagged.
DEV_TIER_JUDGE = os.getenv("DEV_TIER_JUDGE", "openai/gpt-4o-mini")
EVAL_TIER_JUDGE = os.getenv("EVAL_TIER_JUDGE", "openai/gpt-4o")
CALIBRATION_SAMPLE_RATE = float(os.getenv("CALIBRATION_SAMPLE_RATE", "0.10"))
CALIBRATION_MIN_AGREEMENT = float(os.getenv("CALIBRATION_MIN_AGREEMENT", "0.80"))

# Legacy alias kept for backward compatibility with existing .env files.
JUDGE_MODEL = os.getenv("JUDGE_MODEL", DEV_TIER_JUDGE)

# Guard: generation model and dev-tier judge must differ to prevent preference leakage.
# Li et al. (2025) show self-preferential bias inflates judge scores by 8-14 pp when the
# same model generates and evaluates. See routing_policy.md for full policy.
if SYNTHESIS_MODEL == DEV_TIER_JUDGE and OPENROUTER_API_KEY:
    import warnings
    warnings.warn(
        f"SYNTHESIS_MODEL ({SYNTHESIS_MODEL}) == DEV_TIER_JUDGE ({DEV_TIER_JUDGE}). "
        "This allows a single model to generate and judge the same task, risking preference leakage "
        "(Li et al., 2025). Set SYNTHESIS_MODEL=anthropic/claude-3-haiku in .env to enforce rotation.",
        stacklevel=2,
    )

REQUIRED_TOP_KEYS = {"task_id", "metadata", "source_mode", "difficulty", "input", "ground_truth", "scoring_rubric", "evaluator_config"}
REQUIRED_METADATA_KEYS = {"dimension", "created_by", "created_at", "contamination_checked", "scoring_type", "probe_ref"}
VALID_DIMENSIONS = {
    "signal_grounded_personalization", "confidence_aware_phrasing", "hallucination_avoidance",
    "brand_safe_tone", "multi_turn_objection_handling", "cta_behavior", "icp_targeting_accuracy",
    "competitor_gap_reasoning", "pricing_discipline", "thread_continuation_coherence",
}
VALID_SOURCE_MODES = {"trace_derived", "programmatic", "multi_llm_synthesis", "hand_authored_adversarial"}
EASY_ORACLE_CAP = 0.20

# 3-dimension judge gate thresholds (see prompts/judge_quality_gate.md for full prompt).
# Acceptance rule: total >= JUDGE_ACCEPT_THRESHOLD AND no dimension scored 0.
JUDGE_ACCEPT_THRESHOLD = 4   # out of 6 total (3 dimensions × max 2 each)
JUDGE_DIM_FLOOR = 1          # any dimension scoring 0 → reject regardless of total

# Judge prompt loaded from committed markdown (see prompts/judge_quality_gate.md).
_PROMPT_PATH = Path(__file__).parent / "prompts" / "judge_quality_gate.md"

def _load_judge_system_prompt() -> str:
    """Extract the system prompt block from the committed markdown file."""
    if not _PROMPT_PATH.exists():
        # Fallback inline prompt if markdown file is missing.
        return _JUDGE_SYSTEM_FALLBACK
    text = _PROMPT_PATH.read_text(encoding="utf-8")
    # Extract content between the first ```...``` block after "## System Prompt"
    import re
    match = re.search(r"## System Prompt\s*```\s*(.*?)```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return _JUDGE_SYSTEM_FALLBACK


# Inline fallback in case the prompt file is unavailable.
_JUDGE_SYSTEM_FALLBACK = """You are a benchmark quality reviewer for TenaciousBench, a B2B outbound sales agent evaluation benchmark.

Score the following task on THREE dimensions. Return a JSON object with exactly this structure:
{
  "input_coherence": <integer 0, 1, or 2>,
  "ground_truth_verifiability": <integer 0, 1, or 2>,
  "rubric_application_clarity": <integer 0, 1, or 2>,
  "total": <integer 0-6>,
  "accept": <boolean>,
  "reason": "<one sentence>"
}

Dimension scoring:
1. input_coherence: 2=fully consistent context, 1=minor inconsistency, 0=contradictory
2. ground_truth_verifiability: 2=mechanically verifiable, 1=requires semantic judgment, 0=placeholder or contradictory
3. rubric_application_clarity: 2=all rubric dims apply, 1=one borderline, 0=rubric mismatch

Accept if total >= 4 AND no dimension is 0."""


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
    """
    3-dimension scored quality gate (see prompts/judge_quality_gate.md for full spec).

    Dimensions scored 0–2 each:
      1. input_coherence        (threshold: >= 1)
      2. ground_truth_verifiability (threshold: >= 1)
      3. rubric_application_clarity (threshold: >= 1)

    Acceptance rule: total >= JUDGE_ACCEPT_THRESHOLD (4/6) AND no dimension scored 0.
    Source modes exempt from LLM gate: hand_authored_adversarial, trace_derived.
    """
    if not api_key:
        return True, "LLM gate skipped (no API key)", 0

    if task.get("source_mode") in {"hand_authored_adversarial", "trace_derived"}:
        return True, "Source mode exempt from LLM gate", 0

    system_prompt = _load_judge_system_prompt()

    try:
        import httpx

        task_summary = {
            "task_id": task.get("task_id"),
            "dimension": task.get("metadata", {}).get("dimension"),
            "task_instruction": task.get("input", {}).get("task_instruction", ""),
            "ideal_output": task.get("ground_truth", {}).get("ideal_output", "")[:300],
            "banned_phrases": task.get("ground_truth", {}).get("banned_phrases", []),
            "required_signals": task.get("ground_truth", {}).get("required_signals", []),
            "icp_confidence": task.get("input", {}).get("signal_brief", {}).get("icp_confidence"),
            "rubric_dimensions": [
                d["name"] for d in task.get("scoring_rubric", {}).get("dimensions", [])
            ],
        }

        resp = httpx.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Task to score:\n{json.dumps(task_summary, indent=2)}"},
                ],
                "max_tokens": 250,
                "temperature": 0.0,
            },
            timeout=20.0,
        )
        resp.raise_for_status()
        raw = resp.json()["choices"][0]["message"]["content"].strip()

        # Parse the structured JSON response
        import re
        json_match = re.search(r"\{.*\}", raw, re.DOTALL)
        if json_match:
            result = json.loads(json_match.group())
            scores = {
                "input_coherence": int(result.get("input_coherence", 0)),
                "ground_truth_verifiability": int(result.get("ground_truth_verifiability", 0)),
                "rubric_application_clarity": int(result.get("rubric_application_clarity", 0)),
            }
            total = sum(scores.values())
            any_zero = any(v == 0 for v in scores.values())
            passed = (total >= JUDGE_ACCEPT_THRESHOLD) and not any_zero
            reason = result.get("reason", "structured gate applied")
            detail = f"scores={scores} total={total}/6 accept={passed} | {reason}"
            return passed, detail, 1

        # Fallback: could not parse JSON; accept with warning
        return True, f"Could not parse structured judge response; accepting: {raw[:100]}", 1

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


def calibration_check(
    accepted_tasks: list[dict],
    api_key: str,
    sample_rate: float = CALIBRATION_SAMPLE_RATE,
    min_agreement: float = CALIBRATION_MIN_AGREEMENT,
) -> dict:
    """
    Eval-tier calibration: re-run check_llm_quality() on a random sample of
    accepted tasks using EVAL_TIER_JUDGE, then compare accept/reject decisions
    with the dev-tier result (all sampled tasks were already accepted).

    Returns a dict with: sample_n, agreements, agreement_rate, threshold_ok.
    If agreement_rate < min_agreement, threshold_ok=False — caller should raise
    JUDGE_ACCEPT_THRESHOLD for the next filter run.
    """
    if not api_key or not accepted_tasks:
        return {"sample_n": 0, "agreements": 0, "agreement_rate": 1.0, "threshold_ok": True,
                "note": "Skipped (no API key or no accepted tasks)"}

    import random
    rng = random.Random(42)
    sample_n = max(1, int(len(accepted_tasks) * sample_rate))
    sample = rng.sample(accepted_tasks, min(sample_n, len(accepted_tasks)))

    agreements = 0
    details = []
    for task in sample:
        # Dev-tier already accepted this task; eval-tier verdict is ground truth.
        eval_ok, eval_reason, _ = check_llm_quality(task, api_key, EVAL_TIER_JUDGE)
        agreed = eval_ok  # dev-tier said accept; agreement if eval-tier also accepts
        if agreed:
            agreements += 1
        details.append({
            "task_id": task.get("task_id"),
            "eval_tier_accept": eval_ok,
            "eval_tier_reason": eval_reason[:120],
        })

    agreement_rate = agreements / len(sample) if sample else 1.0
    threshold_ok = agreement_rate >= min_agreement
    result = {
        "sample_n": len(sample),
        "agreements": agreements,
        "agreement_rate": round(agreement_rate, 4),
        "threshold_ok": threshold_ok,
        "eval_tier_model": EVAL_TIER_JUDGE,
        "dev_tier_model": DEV_TIER_JUDGE,
        "details": details,
    }
    if not threshold_ok:
        print(
            f"\n[CALIBRATION] Dev-tier / eval-tier agreement={agreement_rate:.1%} < "
            f"{min_agreement:.0%} threshold. Consider raising JUDGE_ACCEPT_THRESHOLD by 1.",
            file=sys.stderr,
        )
    else:
        print(f"\n[CALIBRATION] Dev/eval-tier agreement={agreement_rate:.1%} on "
              f"{len(sample)}/{len(accepted_tasks)} sampled tasks. threshold_ok={threshold_ok}")
    return result


def run_filter(
    in_dir: Path,
    out_dir: Path,
    log_path: Path | None = None,
    easy_cap: float = EASY_ORACLE_CAP,
    run_calibration: bool = True,
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

            # Stage 3 — bulk filter with dev-tier judge (cheap; all tasks)
            ok, reason, calls = check_llm_quality(task, OPENROUTER_API_KEY, DEV_TIER_JUDGE)
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
        print(f"{in_file.name}: {len(tasks)} in -> {len(out_tasks)} out")

    # Stage 5 — eval-tier calibration on a random sample of accepted tasks.
    # Uses EVAL_TIER_JUDGE (stronger model) to verify dev-tier accept/reject alignment.
    all_accepted = [t for tasks in accepted_by_file.values() for t in tasks]
    if run_calibration and all_accepted:
        cal = calibration_check(all_accepted, OPENROUTER_API_KEY)
        stats["calibration"] = cal
        stats["model_calls"] += cal.get("sample_n", 0)  # one call per sampled task
    else:
        stats["calibration"] = {"note": "Calibration skipped (run_calibration=False or no accepted tasks)"}

    if log_path:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("w", encoding="utf-8") as fh:
            json.dump(stats, fh, indent=2)

    print(f"\nFilter summary: {stats['passed']}/{stats['total_input']} accepted "
          f"({stats['model_calls']} LLM calls, dev_tier={DEV_TIER_JUDGE}, eval_tier={EVAL_TIER_JUDGE})")
    return stats


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="TenaciousBench Judge Filter")
    p.add_argument("--in-dir", type=Path, default=Path("tenacious_bench_v0.1/raw"))
    p.add_argument("--out-dir", type=Path, default=Path("tenacious_bench_v0.1/filtered"))
    p.add_argument("--log", type=Path, default=None, help="Write filter statistics to JSON")
    p.add_argument("--easy-cap", type=float, default=0.20)
    p.add_argument("--no-calibration", action="store_true",
                   help="Skip eval-tier calibration subsample (faster, no gpt-4o calls)")
    args = p.parse_args(argv)

    stats = run_filter(args.in_dir, args.out_dir, args.log, args.easy_cap,
                       run_calibration=not args.no_calibration)
    return 0 if stats.get("passed", 0) > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
