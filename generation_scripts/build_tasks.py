#!/usr/bin/env python3
"""
TenaciousBench Task Builder

Generates raw benchmark tasks for tenacious_bench_v0.1 via three source modes:
  --mode programmatic   : template-based, no LLM
  --mode multi_llm      : two-pass GPT-4o-mini generation + review
  --mode trace_derived  : convert Week 10 trace JSONL to tasks

Usage:
    python build_tasks.py --mode programmatic --n 80 --out-dir tenacious_bench_v0.1/raw
    python build_tasks.py --mode multi_llm --n 60 --out-dir tenacious_bench_v0.1/raw
    python build_tasks.py --mode trace_derived \
        --traces ../../week10_final/traces/act4_held_out_traces.jsonl \
        --out-dir tenacious_bench_v0.1/raw
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import sys
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
SYNTHESIS_MODEL = os.getenv("SYNTHESIS_MODEL", "openai/gpt-4o-mini")

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

INDUSTRIES = ["fintech", "healthtech", "supply_chain", "edtech", "insurtech", "proptech", "legaltech"]
FUNDING_STAGES = ["Seed", "Series A", "Series B", "Series C", "Series D", "Pre-IPO"]
COMPANY_SIZES = [50, 120, 250, 400, 800, 1500]
AI_MATURITY_SCORES = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0]
HIRING_LABELS = ["weak", "moderate", "strong", "very_strong"]
CHANNELS = ["email", "sms", "multi_channel"]

BANNED_PHRASES_POOL = [
    "guarantee", "we promise", "100% certain", "definitely will",
    "clearly lacks", "your team is behind", "you are falling behind",
    "proven results", "best in class", "last chance",
]

CTA_PATTERNS = [
    r"(booking link|calendar|cal\.com|schedule|20.minute)",
    r"(happy to share|let.s connect|quick call|brief conversation)",
    r"(demo|walkthrough|30.minute|15.minute)",
]


def _make_company_id(name: str, idx: int) -> str:
    return f"cmp_tb{idx:04d}"


def _signal_date(days_ago: int = 15) -> str:
    return (date(2026, 4, 28) - timedelta(days=days_ago)).isoformat()


def _random_icp(abstain: bool = False) -> float:
    if abstain:
        return round(random.uniform(0.40, 0.61), 2)
    return round(random.uniform(0.63, 0.95), 2)


def _make_company(idx: int, industry: str | None = None) -> dict:
    industry = industry or random.choice(INDUSTRIES)
    stage = random.choice(FUNDING_STAGES)
    size = random.choice(COMPANY_SIZES)
    maturity = random.choice(AI_MATURITY_SCORES)
    name_base = f"{industry.capitalize()}{idx:03d}Corp"
    return {
        "company_id": _make_company_id(name_base, idx),
        "company_name": name_base,
        "industry": industry,
        "funding_stage": stage,
        "employee_count": size,
        "ai_maturity_score": maturity,
    }


def _make_signal_brief(
    icp_conf: float,
    industry: str,
    stale: bool = False,
    abstain: bool = False,
) -> dict:
    today_roles = random.randint(1, 6)
    ago_roles = max(0, today_roles - random.randint(0, 3))
    velocity = HIRING_LABELS[min(3, max(0, today_roles - ago_roles))]
    flags: list[str] = []
    if icp_conf < 0.62:
        flags.append("weak_icp_confidence")
    if stale:
        flags.append("stale_signal")
    segment = None if abstain else f"segment_{random.randint(1, 4)}"
    gap_summary = (
        "Two fintech peers have active MLOps Platform Engineer roles; company has none."
        if industry == "fintech"
        else f"Competitor analysis incomplete for {industry} vertical."
    )
    return {
        "icp_confidence": icp_conf,
        "icp_segment": segment,
        "hiring_velocity_label": velocity,
        "open_roles_today": today_roles,
        "open_roles_60d_ago": ago_roles,
        "honesty_flags": flags,
        "competitor_gap_summary": gap_summary,
        "signal_date": _signal_date(90 if stale else random.randint(5, 45)),
    }


def _make_rubric(dimension: str, abstain: bool) -> dict:
    if abstain or dimension == "icp_targeting_accuracy":
        return {
            "dimensions": [
                {"name": "banned_phrase_violations", "weight": 0.20, "max_score": 1.0, "description": "Must not send segment pitch"},
                {"name": "grounding_signal_presence", "weight": 0.30, "max_score": 1.0, "description": "Must cite confidence and threshold"},
                {"name": "cta_presence", "weight": 0.10, "max_score": 1.0, "description": "Abstain keyword present"},
                {"name": "tone_markers", "weight": 0.10, "max_score": 1.0, "description": "Professional abstain explanation"},
                {"name": "confidence_calibration", "weight": 0.30, "max_score": 1.0, "description": "Correct abstain decision"},
            ],
            "pass_threshold": 0.80,
        }
    if dimension == "multi_turn_objection_handling":
        return {
            "dimensions": [
                {"name": "banned_phrase_violations", "weight": 0.35, "max_score": 1.0, "description": "Must not follow up after opt-out"},
                {"name": "grounding_signal_presence", "weight": 0.20, "max_score": 1.0, "description": "Acknowledge prospect's stated position"},
                {"name": "cta_presence", "weight": 0.15, "max_score": 1.0, "description": "Stop/suppress action present"},
                {"name": "tone_markers", "weight": 0.10, "max_score": 1.0, "description": "Respectful acknowledgement"},
                {"name": "confidence_calibration", "weight": 0.20, "max_score": 1.0, "description": "Correct intent classification"},
            ],
            "pass_threshold": 0.75,
        }
    return {
        "dimensions": [
            {"name": "banned_phrase_violations", "weight": 0.30, "max_score": 1.0, "description": "No banned phrases"},
            {"name": "grounding_signal_presence", "weight": 0.25, "max_score": 1.0, "description": "Required signals present"},
            {"name": "cta_presence", "weight": 0.20, "max_score": 1.0, "description": "CTA pattern matched"},
            {"name": "tone_markers", "weight": 0.15, "max_score": 1.0, "description": "Professional tone"},
            {"name": "confidence_calibration", "weight": 0.10, "max_score": 1.0, "description": "Appropriate confidence level"},
        ],
        "pass_threshold": 0.70,
    }


def _task_id(split_prefix: str, idx: int) -> str:
    return f"TB-{split_prefix}-{idx:03d}"


def build_programmatic_task(idx: int, dimension: str | None = None) -> dict:
    dimension = dimension or random.choice(DIMENSIONS)
    industry = random.choice(INDUSTRIES)
    abstain = dimension == "icp_targeting_accuracy" and random.random() < 0.4
    icp_conf = _random_icp(abstain=abstain)
    company = _make_company(idx, industry)
    signal = _make_signal_brief(icp_conf, industry, abstain=abstain)
    thread_history: list[dict] = []

    banned = random.sample(BANNED_PHRASES_POOL, k=3)
    required_signals = [industry, company["funding_stage"]]
    if signal["open_roles_today"] > 0:
        required_signals.append("hiring")

    if abstain:
        ideal = f"ABSTAIN: icp_confidence={icp_conf} is below the 0.62 production threshold. Route to exploratory cadence."
        cta_pattern = r"(abstain|below.threshold|exploratory)"
        correct_intent = "abstain"
        required_signals = ["abstain", str(icp_conf), "0.62"]
    else:
        ideal = (
            f"Hi [contact], based on {company['company_name']}'s recent hiring momentum — "
            f"{signal['open_roles_today']} open AI roles versus {signal['open_roles_60d_ago']} "
            f"sixty days ago — and the gap with {industry} peers, I wanted to reach out about "
            f"AI team augmentation. Would a 20-minute call make sense? [booking link]"
        )
        cta_pattern = random.choice(CTA_PATTERNS)
        correct_intent = None

    rubric = _make_rubric(dimension, abstain)

    return {
        "task_id": f"TB-RAW-{idx:04d}",
        "metadata": {
            "dimension": dimension,
            "created_by": "programmatic",
            "created_at": "2026-04-28T09:15:00Z",
            "contamination_checked": False,
            "scoring_type": "binary_pass_fail" if abstain else "rubric_5pt",
            "probe_ref": None,
            "industry": industry,
            "company_size": (
                "startup" if company["employee_count"] < 100
                else "smb" if company["employee_count"] < 300
                else "mid_market" if company["employee_count"] < 1000
                else "enterprise"
            ),
            "icp_confidence": icp_conf,
        },
        "source_mode": "programmatic",
        "difficulty": "easy" if not abstain else "medium",
        "input": {
            "company_context": company,
            "signal_brief": signal,
            "channel": random.choice(CHANNELS),
            "thread_history": thread_history,
            "task_instruction": (
                f"Compose an outbound message to {company['company_name']} "
                f"grounded in the hiring signal and competitor gap brief. "
                "Use the confidence-aware phrasing policy. Include a CTA."
                if not abstain else
                f"Determine whether to send outreach to {company['company_name']}. "
                "If ICP confidence is below 0.62, emit abstain."
            ),
        },
        "candidate_output": {
            "outreach_text": "",
            "channel": signal.get("channel", "email"),
            "intent_classification": None,
            "confidence_prefix": None,
            "cta_present": False,
            "citations": [],
        },
        "ground_truth": {
            "ideal_output": ideal,
            "banned_phrases": banned,
            "required_signals": required_signals,
            "required_cta_pattern": cta_pattern,
            "correct_intent": correct_intent,
            "confidence_prefix_required": 0.55 < icp_conf < 0.75 and not abstain,
            "abstain_required": abstain,
        },
        "scoring_rubric": rubric,
        "evaluator_config": {
            "scorer_version": "0.1.0",
            "icp_threshold": 0.62,
            "signal_confidence_mode": "confidence_aware",
            "judge_model": "openai/gpt-4o-mini",
            "banned_phrase_check": "regex",
            "grounding_check": "keyword",
            "max_latency_ms": 15000,
        },
    }


def build_multi_llm_task(idx: int, dimension: str, api_key: str, model: str) -> dict | None:
    """Two-pass LLM task generation. Returns None if quality gate fails."""
    try:
        import httpx
    except ImportError:
        print("httpx not installed — skipping multi-LLM mode.", file=sys.stderr)
        return None

    if not api_key:
        print("OPENROUTER_API_KEY not set — skipping multi-LLM mode.", file=sys.stderr)
        return None

    industry = random.choice(INDUSTRIES)
    icp_conf = _random_icp()

    gen_prompt = f"""Generate a TenaciousBench evaluation task for the dimension "{dimension}".

The task must:
1. Test a B2B outbound sales agent on exactly the {dimension} dimension.
2. Include a realistic company context (industry: {industry}, icp_confidence: {icp_conf:.2f}).
3. Include a ground_truth.ideal_output that a well-aligned agent would produce.
4. Include 3 banned_phrases the agent must not use.
5. Include 3 required_signals the ideal output must contain.
6. Include a required_cta_pattern regex.

Return ONLY a JSON object matching this structure:
{{
  "company_name": "...",
  "task_instruction": "...",
  "ideal_output": "...",
  "banned_phrases": ["...", "...", "..."],
  "required_signals": ["...", "...", "..."],
  "required_cta_pattern": "...",
  "abstain_required": false
}}"""

    def _call(prompt: str) -> dict | None:
        try:
            resp = httpx.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 600,
                    "temperature": 0.7,
                },
                timeout=20.0,
            )
            resp.raise_for_status()
            raw = resp.json()["choices"][0]["message"]["content"].strip()
            json_match = __import__("re").search(r"\{.*\}", raw, __import__("re").DOTALL)
            if json_match:
                return json.loads(json_match.group())
        except Exception:
            pass
        return None

    draft = _call(gen_prompt)
    if not draft:
        return None

    review_prompt = f"""Is the following a valid TenaciousBench evaluation task for dimension "{dimension}"?
It must test exactly one dimension and have a clear pass/fail criterion.
Answer YES or NO, then one sentence explanation.

Task JSON:
{json.dumps(draft, indent=2)}"""

    review = _call(review_prompt)
    if not review:
        return None

    review_text = str(review).upper()
    if "NO" in review_text[:20]:
        return None

    company = _make_company(idx, industry)
    signal = _make_signal_brief(icp_conf, industry)
    rubric = _make_rubric(dimension, draft.get("abstain_required", False))

    return {
        "task_id": f"TB-SYNTH-{idx:04d}",
        "metadata": {
            "dimension": dimension,
            "created_by": "multi_llm_synthesis",
            "created_at": "2026-04-28T09:45:22Z",
            "contamination_checked": False,
            "scoring_type": "rubric_5pt",
            "probe_ref": None,
            "industry": industry,
            "company_size": "mid_market",
            "icp_confidence": icp_conf,
        },
        "source_mode": "multi_llm_synthesis",
        "difficulty": "medium",
        "input": {
            "company_context": company,
            "signal_brief": signal,
            "channel": "email",
            "thread_history": [],
            "task_instruction": draft.get("task_instruction", ""),
        },
        "candidate_output": {
            "outreach_text": "",
            "channel": "email",
            "intent_classification": None,
            "confidence_prefix": None,
            "cta_present": False,
            "citations": [],
        },
        "ground_truth": {
            "ideal_output": draft.get("ideal_output", ""),
            "banned_phrases": draft.get("banned_phrases", []),
            "required_signals": draft.get("required_signals", []),
            "required_cta_pattern": draft.get("required_cta_pattern", ""),
            "correct_intent": None,
            "confidence_prefix_required": 0.55 < icp_conf < 0.75,
            "abstain_required": draft.get("abstain_required", False),
        },
        "scoring_rubric": rubric,
        "evaluator_config": {
            "scorer_version": "0.1.0",
            "icp_threshold": 0.62,
            "signal_confidence_mode": "confidence_aware",
            "judge_model": "openai/gpt-4o-mini",
            "banned_phrase_check": "regex",
            "grounding_check": "keyword",
            "max_latency_ms": 15000,
        },
    }


def build_trace_derived_task(trace: dict, idx: int) -> dict | None:
    """Convert a Week 10 trace record to a benchmark task."""
    task_id_src = trace.get("task_id", f"trace_{idx}")
    passed = trace.get("success", False)
    company_id = trace.get("company_id", f"cmp_trace_{idx:03d}")
    industry = trace.get("industry", "fintech")
    icp_conf = trace.get("icp_confidence", 0.75)
    output_text = trace.get("outreach_text", trace.get("output", ""))

    if not output_text:
        return None

    dimension = random.choice(DIMENSIONS)
    company = {
        "company_id": f"cmp_td{idx:04d}",
        "company_name": f"TraceCorp{idx:03d}",
        "industry": industry,
        "funding_stage": trace.get("funding_stage", "Series B"),
        "employee_count": trace.get("employee_count", 350),
        "ai_maturity_score": trace.get("ai_maturity_score", 1.5),
    }
    signal = _make_signal_brief(icp_conf, industry)
    rubric = _make_rubric(dimension, False)

    return {
        "task_id": f"TB-TRACE-{idx:04d}",
        "metadata": {
            "dimension": dimension,
            "created_by": "trace_derived",
            "created_at": "2026-04-28T10:00:00Z",
            "contamination_checked": False,
            "scoring_type": "rubric_5pt",
            "probe_ref": None,
            "industry": industry,
            "company_size": "mid_market",
            "icp_confidence": icp_conf,
        },
        "source_mode": "trace_derived",
        "difficulty": "medium",
        "input": {
            "company_context": company,
            "signal_brief": signal,
            "channel": trace.get("channel", "email"),
            "thread_history": [],
            "task_instruction": (
                f"Compose outreach for {company['company_name']} based on available signals. "
                "Apply confidence-aware phrasing. Include CTA."
            ),
        },
        "candidate_output": {
            "outreach_text": output_text if passed else "",
            "channel": trace.get("channel", "email"),
            "intent_classification": None,
            "confidence_prefix": None,
            "cta_present": False,
            "citations": [],
        },
        "ground_truth": {
            "ideal_output": output_text if passed else "",
            "banned_phrases": ["guarantee", "we promise", "clearly lacks"],
            "required_signals": [industry, "hiring"],
            "required_cta_pattern": r"(booking link|calendar|schedule|20.minute)",
            "correct_intent": None,
            "confidence_prefix_required": 0.55 < icp_conf < 0.75,
            "abstain_required": False,
        },
        "scoring_rubric": rubric,
        "evaluator_config": {
            "scorer_version": "0.1.0",
            "icp_threshold": 0.62,
            "signal_confidence_mode": "confidence_aware",
            "judge_model": "openai/gpt-4o-mini",
            "banned_phrase_check": "regex",
            "grounding_check": "keyword",
            "max_latency_ms": 15000,
        },
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="TenaciousBench Task Builder")
    p.add_argument("--mode", choices=["programmatic", "multi_llm", "trace_derived"], required=True)
    p.add_argument("--n", type=int, default=66, help="Number of tasks to generate (programmatic/multi_llm)")
    p.add_argument("--out-dir", type=Path, default=Path("tenacious_bench_v0.1/raw"))
    p.add_argument("--traces", type=Path, help="Path to trace JSONL (trace_derived mode)")
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args(argv)

    random.seed(args.seed)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    out_file = args.out_dir / f"{args.mode}_tasks.jsonl"

    tasks: list[dict] = []

    if args.mode == "programmatic":
        dim_cycle = DIMENSIONS * (args.n // len(DIMENSIONS) + 1)
        for i, dim in enumerate(dim_cycle[: args.n]):
            t = build_programmatic_task(i + 1, dim)
            tasks.append(t)
        print(f"Generated {len(tasks)} programmatic tasks.")

    elif args.mode == "multi_llm":
        dim_cycle = DIMENSIONS * (args.n // len(DIMENSIONS) + 1)
        accepted = 0
        attempted = 0
        for i, dim in enumerate(dim_cycle):
            if accepted >= args.n:
                break
            attempted += 1
            t = build_multi_llm_task(
                i + 1, dim, OPENROUTER_API_KEY, SYNTHESIS_MODEL
            )
            if t:
                tasks.append(t)
                accepted += 1
            time.sleep(0.5)
        print(f"Generated {accepted}/{attempted} multi-LLM tasks (rejection rate: {(attempted-accepted)/max(1,attempted):.1%}).")

    elif args.mode == "trace_derived":
        if not args.traces or not args.traces.exists():
            print(f"Trace file not found: {args.traces}", file=sys.stderr)
            return 1
        with args.traces.open(encoding="utf-8") as fh:
            traces = [json.loads(line) for line in fh if line.strip()]
        for i, tr in enumerate(traces):
            t = build_trace_derived_task(tr, i + 1)
            if t:
                tasks.append(t)
        print(f"Converted {len(tasks)}/{len(traces)} traces to tasks.")

    with out_file.open("w", encoding="utf-8") as fh:
        for t in tasks:
            fh.write(json.dumps(t) + "\n")

    print(f"Written to {out_file}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
