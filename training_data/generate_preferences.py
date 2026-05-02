#!/usr/bin/env python3
"""
Generate ORPO preference pairs from TenaciousBench tasks.

For each task:
  chosen  = ground_truth.ideal_output (verified by judge filter, κ=0.79)
  rejected = degraded variant with one banned-phrase injection OR
             the matching Week 10 probe failure text where available

Run from repo root:
    python training_data/generate_preferences.py
"""
from __future__ import annotations

import json
import random
import re
import sys
from pathlib import Path

random.seed(42)

REPO_ROOT = Path(__file__).parent.parent
BENCH_TRAIN = REPO_ROOT / "tenacious_bench_v0.1" / "train" / "train.jsonl"
BENCH_DEV   = REPO_ROOT / "tenacious_bench_v0.1" / "dev"   / "dev.jsonl"
DPO_PROBES  = REPO_ROOT / "week10_final" / "data" / "dpo_pairs_v1.jsonl"

SYSTEM_PROMPT = (
    "You are Tenacious, an AI-orchestrated B2B outreach system. "
    "Your job is to process an inbound prospect signal and produce a safe, "
    "accurate, and signal-grounded response. You must respect the ICP confidence "
    "threshold (0.62), apply confidence-aware phrasing, enforce tone guardrails, "
    "and never overclaim."
)

# Failure injection patterns: each produces a realistic rejected text
_INJECTION_TEMPLATES = [
    ("guarantee", "We guarantee {industry} results for your team."),
    ("clearly lacks", "Your team clearly lacks the AI capabilities your competitors have built."),
    ("we promise", "We promise this will transform your outbound pipeline in 30 days."),
    ("proven best-in-class", "Our proven best-in-class solution is exactly what you need."),
    ("don't miss out", "Don't miss out — this offer is only available this quarter."),
]


def load_probe_index() -> dict[str, dict]:
    """Load week10 probe pairs indexed by probe_id for reuse in training."""
    index: dict[str, dict] = {}
    if not DPO_PROBES.exists():
        return index
    with DPO_PROBES.open(encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            probe_id = row.get("probe_id", "")
            if probe_id:
                index[probe_id] = row
    return index


def build_prompt(task: dict) -> str:
    inp = task["input"]
    ctx = inp["company_context"]
    sig = inp["signal_brief"]
    instruction = inp.get("task_instruction", "")

    company_block = (
        f"Company: {ctx['company_name']} ({ctx['industry']}, {ctx['funding_stage']}, "
        f"{ctx['employee_count']} employees)\n"
        f"ICP confidence: {sig['icp_confidence']} | "
        f"Hiring velocity: {sig['hiring_velocity_label']} | "
        f"Open roles today: {sig['open_roles_today']} vs 60d ago: {sig['open_roles_60d_ago']}\n"
        f"Competitor gap: {sig.get('competitor_gap_summary', 'N/A')}\n"
        f"Channel: {inp.get('channel', 'email')}"
    )

    thread = inp.get("thread_history", [])
    thread_block = ""
    if thread:
        turns = "\n".join(f"  [{t.get('role','?')}]: {t.get('content','')}" for t in thread)
        thread_block = f"\nThread history:\n{turns}"

    return (
        f"{SYSTEM_PROMPT}\n\n"
        f"Scenario:\n{company_block}{thread_block}\n\n"
        f"Task: {instruction}"
    )


def build_rejected(task: dict) -> str:
    """Create a realistic rejected output by injecting a banned phrase."""
    gt = task["ground_truth"]
    ideal = gt.get("ideal_output", "")
    banned = gt.get("banned_phrases", [])
    industry = task["input"]["company_context"].get("industry", "B2B")
    company = task["input"]["company_context"].get("company_name", "your company")
    dim = task["metadata"].get("dimension", "")

    # Abstain tasks: rejected = sending a pitch anyway
    if gt.get("abstain_required"):
        icp = task["input"]["signal_brief"].get("icp_confidence", 0.5)
        return (
            f"Hi [contact], {company} seems like a strong fit for our AI augmentation platform. "
            f"Based on your {industry} profile, I wanted to share how we've helped similar companies scale. "
            f"Would a 20-minute call make sense this week? [calendar link]  "
            f"[FAILURE: pitch sent despite icp_confidence={icp} < threshold=0.62]"
        )

    # Tone/brand tasks: inject condescending language
    if "brand_safe" in dim or "tone" in dim:
        return (
            f"Hi [contact], your team clearly lacks the operational AI infrastructure that "
            f"your {industry} peers have already built. We guarantee results within 90 days — "
            f"our proven best-in-class platform is exactly what {company} needs right now. "
            f"Don't miss out on this opportunity. Book here: [link]"
        )

    # Signal grounding / thread coherence: send generic (no grounding signals)
    if "signal_grounded" in dim or "thread" in dim or "hallucination" in dim:
        return (
            f"Hi [contact], we work with many {industry} companies and we'd love to show you "
            f"how our AI platform can help {company} scale faster. We promise this will be "
            f"worth your time. Let's connect! [link]  "
            f"[FAILURE: no hiring signal referenced; banned phrase 'we promise' used]"
        )

    # Default: inject first matching banned phrase from the task's list
    for phrase in banned:
        for trigger, template in _INJECTION_TEMPLATES:
            if trigger.lower() in phrase.lower():
                injected = template.format(industry=industry, company=company)
                if ideal:
                    # Append the violation to the otherwise-good ideal output
                    return ideal.rstrip() + f" {injected}  [FAILURE: banned phrase injected]"
                return injected

    # Final fallback: assertive pitch with guarantee
    return (
        f"Hi [contact], we guarantee {company} will see measurable results within 60 days. "
        f"Our AI platform is proven best-in-class for {industry} companies at your scale. "
        f"Don't miss out — book a call: [link]  "
        f"[FAILURE: guarantee + superlative + urgency manipulation]"
    )


def make_preference_pair(task: dict, probe_index: dict[str, dict]) -> dict:
    probe_ref = task["metadata"].get("probe_ref", "")
    probe_pair = probe_index.get(probe_ref)

    prompt = build_prompt(task)

    if probe_pair and probe_pair.get("chosen") and probe_pair.get("rejected"):
        # Reuse the validated week10 probe pair text when available
        chosen = probe_pair["chosen"]
        rejected = probe_pair["rejected"]
        source_trace = probe_ref
    else:
        chosen = task["ground_truth"]["ideal_output"]
        rejected = build_rejected(task)
        source_trace = probe_ref or "benchmark_derived"

    return {
        "id": f"TB-PREF-{task['task_id']}",
        "prompt": prompt,
        "chosen": chosen,
        "rejected": rejected,
        "source_trace_id": source_trace,
        "failure_dimension": task["metadata"]["dimension"],
        "quality_score": round(task["metadata"].get("oracle_score", 0.85), 4),
    }


def generate_split(jsonl_path: Path, out_path: Path, probe_index: dict[str, dict]) -> int:
    tasks = [json.loads(line) for line in jsonl_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for task in tasks:
            pair = make_preference_pair(task, probe_index)
            f.write(json.dumps(pair, ensure_ascii=False) + "\n")
    return len(tasks)


def main() -> None:
    out_dir = REPO_ROOT / "training_data"
    probe_index = load_probe_index()
    print(f"Loaded {len(probe_index)} probe pairs from week10 DPO data.")

    n_train = generate_split(BENCH_TRAIN, out_dir / "train_preferences.jsonl", probe_index)
    n_dev   = generate_split(BENCH_DEV,   out_dir / "dev_preferences.jsonl",   probe_index)
    print(f"Generated {n_train} train preference pairs -> training_data/train_preferences.jsonl")
    print(f"Generated {n_dev} dev preference pairs   -> training_data/dev_preferences.jsonl")


if __name__ == "__main__":
    main()
