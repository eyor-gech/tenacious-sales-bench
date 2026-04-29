#!/usr/bin/env python3
"""
TenaciousBench Scoring Evaluator v0.1

Scores a candidate agent output against a benchmark task from tenacious_bench_v0.1/.
Returns a numeric score in [0, 1] plus a per-dimension breakdown.

Usage:
    python scoring_evaluator.py --task <path/to/tasks.jsonl> --task-id TB-DEV-001
    python scoring_evaluator.py --task <path/to/tasks.jsonl> --task-id TB-DEV-001 \
        --candidate '{"outreach_text": "...", "cta_present": true}'
    python scoring_evaluator.py --batch-dir tenacious_bench_v0.1/dev --out results/dev_scores.jsonl

End-to-end example walkthrough (no API key required):
    python examples/run_examples.py

    This runs score_task() against three hand-authored tasks in examples/:
      ex1_signal_grounding_pass.json  — well-formed email, expects PASS  (~0.87)
      ex2_icp_abstain_correct.json    — correct abstain at icp=0.45,     PASS  (~1.00)
      ex3_banned_phrase_fail.json     — guarantee + condescending text,  FAIL  (~0.31)

    Each JSON file contains a complete task dict including a filled candidate_output.
    Calling score_task(task) returns a TaskScore with total_score, passed, and a
    DimensionScore for each rubric dimension (raw, weight, weighted, reason).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
JUDGE_MODEL = os.getenv("JUDGE_MODEL", "openai/gpt-4o-mini")
ICP_THRESHOLD = float(os.getenv("ICP_ABSTAIN_THRESHOLD", "0.62"))

SCORER_VERSION = "0.1.0"


# ── Data classes ────────────────────────────────────────────────────────────

@dataclass
class DimensionScore:
    name: str
    raw_score: float      # [0, 1]
    weight: float
    weighted: float
    reason: str


@dataclass
class TaskScore:
    task_id: str
    total_score: float    # weighted sum in [0, 1]
    passed: bool
    pass_threshold: float
    dimensions: list[DimensionScore] = field(default_factory=list)
    latency_ms: float = 0.0
    model_calls: int = 0
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "total_score": round(self.total_score, 4),
            "passed": self.passed,
            "pass_threshold": self.pass_threshold,
            "dimensions": [
                {
                    "name": d.name,
                    "raw_score": round(d.raw_score, 4),
                    "weight": d.weight,
                    "weighted": round(d.weighted, 4),
                    "reason": d.reason,
                }
                for d in self.dimensions
            ],
            "latency_ms": round(self.latency_ms, 1),
            "model_calls": self.model_calls,
            "errors": self.errors,
            "scorer_version": SCORER_VERSION,
        }


# ── Banned phrase checker ────────────────────────────────────────────────────

_GLOBAL_BANNED_PATTERNS: list[re.Pattern] = [
    re.compile(r"\bguarantee\b", re.IGNORECASE),
    re.compile(r"\bwe promise\b", re.IGNORECASE),
    re.compile(r"\b100\s*%\s*(certain|guaranteed|sure)\b", re.IGNORECASE),
    re.compile(r"\bdefinitely\s+will\b", re.IGNORECASE),
    re.compile(r"\bclearly\s+lacks?\b", re.IGNORECASE),
    re.compile(r"\byour\s+team\s+is\s+behind\b", re.IGNORECASE),
    re.compile(r"\byou\s+(?:are|re)\s+falling\s+behind\b", re.IGNORECASE),
]


def score_banned_phrases(
    text: str,
    task_banned: list[str],
    check_mode: str = "regex",
) -> tuple[float, str]:
    """
    Returns (score, reason).
    score = 1.0 if no violations; subtract 0.5 per violation, floor 0.

    Calibration:
      1.0 — Zero banned phrases detected (global + task-specific lists).
             Example passing output: "Based on available data, NovaPay's 4 open roles
             suggest scaling momentum. Happy to share a 20-min overview: [cal.com link]"
      0.5 — One violation found (e.g., "guarantee" or "clearly lacks").
             Example: "We guarantee your team will see results within 60 days."
      0.0 — Two or more violations in the same output.
             Example: "We guarantee results — and we promise you are clearly behind your peers."
    """
    violations: list[str] = []

    # Global banned patterns
    for pat in _GLOBAL_BANNED_PATTERNS:
        if pat.search(text):
            violations.append(pat.pattern)

    # Task-specific banned phrases
    for phrase in task_banned:
        if check_mode == "regex":
            try:
                if re.search(phrase, text, re.IGNORECASE):
                    violations.append(phrase)
            except re.error:
                if phrase.lower() in text.lower():
                    violations.append(phrase)
        else:
            if phrase.lower() in text.lower():
                violations.append(phrase)

    if not violations:
        return 1.0, "No banned phrases detected."

    score = max(0.0, 1.0 - 0.5 * len(violations))
    return score, f"Banned phrases found: {violations}"


# ── Grounding signal checker ─────────────────────────────────────────────────

def score_grounding_signals(
    text: str,
    required_signals: list[str],
    check_mode: str = "keyword",
) -> tuple[float, str]:
    """
    Returns (score, reason).
    score = fraction of required_signals present in text.

    Calibration:
      1.0 — All required signals present
             Example: text mentions "Series B", "fintech", and "open_roles_today=4"
      0.67 — 2/3 signals present; one grounding reference omitted
      0.0  — No required signals found; generic outreach with no grounding
    """
    if not required_signals:
        return 1.0, "No required signals specified."

    found = []
    missing = []
    for signal in required_signals:
        if check_mode == "keyword":
            hit = signal.lower() in text.lower()
        else:  # "regex" (default) or "embedding" (falls back to regex)
            try:
                hit = bool(re.search(signal, text, re.IGNORECASE))
            except re.error:
                hit = signal.lower() in text.lower()
        if hit:
            found.append(signal)
        else:
            missing.append(signal)

    score = len(found) / len(required_signals)
    if missing:
        reason = f"Present: {found}. Missing: {missing}."
    else:
        reason = f"All {len(required_signals)} required signals present."
    return score, reason


# ── CTA presence checker ─────────────────────────────────────────────────────

def score_cta_presence(
    text: str,
    cta_pattern: str,
    cta_present_flag: bool | None = None,
) -> tuple[float, str]:
    """
    Returns (score, reason).
    1.0 if CTA pattern is found; 0.0 otherwise.

    Calibration:
      1.0 — CTA pattern matched (e.g., "book a 15-minute call", "schedule a demo")
             or candidate explicitly set cta_present=True
      0.0 — No CTA found; email ends without a specific next-step ask
    """
    if cta_pattern:
        try:
            if re.search(cta_pattern, text, re.IGNORECASE):
                return 1.0, "CTA pattern matched."
            return 0.0, f"CTA pattern not found: {cta_pattern!r}"
        except re.error:
            pass

    if cta_present_flag is True:
        return 1.0, "cta_present flag set by candidate."
    return 0.0, "No CTA detected in output."


# ── Tone marker checker (LLM-based) ─────────────────────────────────────────

_TONE_SYSTEM_PROMPT = """You are a B2B sales communication quality judge.
Score the following outreach message on tone quality.

Return a JSON object with exactly these fields:
{
  "score": <float 0.0 to 1.0>,
  "issues": [<list of tone issues found, empty if none>],
  "reason": "<one sentence explanation>"
}

Scoring guide:
- 1.0: Professional, confident, non-condescending, no overclaims, no belittling
- 0.7: Minor hedging issues or slightly weak CTA
- 0.5: Borderline: either slightly pushy or slightly too weak
- 0.3: Condescending language or unsubstantiated claims
- 0.0: Severe violations: threats, guarantees, insulting language, aggressive follow-up after explicit opt-out

For abstain/stop routing decisions: score 1.0 if the text correctly routes; do not penalize for lack of warmth."""

_TONE_HARMFUL_PATTERNS: list[re.Pattern] = [
    re.compile(r"\bclearly\s+lacks?\b", re.IGNORECASE),
    re.compile(r"\byour\s+(team|company)\s+is\s+(behind|failing|struggling)\b", re.IGNORECASE),
    re.compile(r"\byou\s+(must|need\s+to|have\s+to)\b", re.IGNORECASE),
    re.compile(r"\bdon't\s+miss\s+out\b", re.IGNORECASE),
    re.compile(r"\blast\s+chance\b", re.IGNORECASE),
]


def score_tone_markers(
    text: str,
    judge_model: str = JUDGE_MODEL,
    api_key: str = OPENROUTER_API_KEY,
) -> tuple[float, str, int]:
    """
    Returns (score, reason, model_calls).
    Uses lexical fast-path first; falls back to LLM judge.

    Calibration:
      1.0 — Professional, non-condescending, no overclaims (LLM: no issues; lexical: no matches)
             Example: "Based on NovaPay's recent Series B, your team may be scaling..."
      0.5 — One lexical violation (e.g., "clearly lacks") → score = 1.0 - 0.3*1 = 0.7; two = 0.4
      0.0 — Severe violations: guarantee, threat, opt-out ignored (lexical match or LLM score=0.0)
    Note: lexical path does not call the LLM (model_calls=0); LLM path returns model_calls=1.
    """
    # Fast lexical path
    local_violations = []
    for pat in _TONE_HARMFUL_PATTERNS:
        if pat.search(text):
            local_violations.append(pat.pattern)

    if local_violations:
        score = max(0.0, 1.0 - 0.3 * len(local_violations))
        return score, f"Lexical tone violations: {local_violations}", 0

    # LLM judge path
    if not api_key:
        return 0.8, "LLM judge skipped (no API key); no lexical violations found.", 0

    try:
        import httpx

        payload = {
            "model": judge_model,
            "messages": [
                {"role": "system", "content": _TONE_SYSTEM_PROMPT},
                {"role": "user", "content": f"Message to score:\n\n{text}"},
            ],
            "max_tokens": 200,
            "temperature": 0.0,
        }
        response = httpx.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=15.0,
        )
        response.raise_for_status()
        raw = response.json()["choices"][0]["message"]["content"].strip()

        # Parse JSON from model output
        json_match = re.search(r"\{.*\}", raw, re.DOTALL)
        if json_match:
            result = json.loads(json_match.group())
            score = float(result.get("score", 0.8))
            reason = result.get("reason", "LLM judge scored.")
            return min(1.0, max(0.0, score)), reason, 1

    except Exception as exc:  # noqa: BLE001
        pass

    return 0.8, "LLM judge unavailable; no lexical violations detected.", 0


# ── Confidence calibration checker ──────────────────────────────────────────

def score_confidence_calibration(
    text: str,
    icp_confidence: float,
    abstain_required: bool,
    confidence_prefix_required: bool,
    candidate_prefix: str | None,
    signal_confidence_mode: str = "confidence_aware",
) -> tuple[float, str]:
    """
    Returns (score, reason).

    Rules:
    - abstain_required=True → text must contain 'abstain' or 'below threshold'; anything else = 0.0
    - confidence_prefix_required=True → text must contain a hedging prefix
    - icp_confidence < 0.50 → assertive claims penalised even if prefix present
    """
    text_lower = text.lower()

    if abstain_required:
        if "abstain" in text_lower or "below threshold" in text_lower or "below the" in text_lower:
            return 1.0, "Correct abstain decision."
        return 0.0, "Abstain required but not emitted; segment pitch sent instead."

    if confidence_prefix_required:
        # candidate_prefix is an explicit prefix string the agent declared (e.g. "Based on available data,").
        # If the candidate set it, treat as satisfying the requirement without lexical scan.
        if candidate_prefix:
            return 1.0, f"Confidence prefix declared by candidate: '{candidate_prefix}'."
        hedges = [
            "based on", "indicators suggest", "it appears", "we believe",
            "our data suggests", "according to", "early indicators", "moderate-confidence"
        ]
        if any(h in text_lower for h in hedges):
            return 1.0, "Confidence prefix present as required."
        return 0.4, "Confidence prefix required but not found; assertive phrasing on moderate-confidence signal."

    if icp_confidence < 0.55 and signal_confidence_mode == "confidence_aware":
        assertive_patterns = [
            re.compile(r"\byour team (?:is|are) scaling\b", re.IGNORECASE),
            re.compile(r"\bstrong (hiring|momentum)\b", re.IGNORECASE),
        ]
        violations = [p.pattern for p in assertive_patterns if p.search(text)]
        if violations:
            return 0.5, f"Assertive phrasing on low-confidence signal ({icp_confidence:.2f}): {violations}"

    return 1.0, f"Confidence calibration appropriate for icp_confidence={icp_confidence:.2f}."


# ── Factual unsupported claims checker ──────────────────────────────────────

_UNSUPPORTED_CLAIM_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\b(\d+)%\s+(increase|improvement|reduction|faster)\b", re.IGNORECASE),
     "Quantified performance claim without citation"),
    (re.compile(r"\b(?:all|every|most)\s+(?:companies|teams|peers)\s+(?:are|have)\b", re.IGNORECASE),
     "Overgeneralisation without data"),
    (re.compile(r"\bproven\s+(?:to|results?)\b", re.IGNORECASE),
     "Unverifiable proof claim"),
    (re.compile(r"\bbest\s+(?:in\s+class|in\s+the\s+industry|solution)\b", re.IGNORECASE),
     "Superlative claim without evidence"),
]


def score_factual_unsupported_claims(
    text: str,
) -> tuple[float, str]:
    """
    Returns (score, reason).
    Checks for unsupported quantified claims and overgeneralisations.

    Calibration:
      1.0 — No unsupported claims; all quantified statements reference grounding signals
             Example: "NovaPay added 4 roles in 60 days" (signal-grounded)
      0.75 — One pattern match (e.g., "proven results") → score = 1.0 - 0.25*1
      0.0  — 4+ unsupported patterns; text reads as boilerplate overclaim
    """
    violations = []
    for pat, label in _UNSUPPORTED_CLAIM_PATTERNS:
        if pat.search(text):
            violations.append(label)

    if not violations:
        return 1.0, "No unsupported factual claims detected."

    score = max(0.0, 1.0 - 0.25 * len(violations))
    return score, f"Unsupported claims: {violations}"


# ── Main scorer ──────────────────────────────────────────────────────────────

def score_task(task: dict, candidate: dict | None = None) -> TaskScore:
    """
    Score a single task. If candidate is None, uses task['candidate_output'].
    """
    start = time.monotonic()
    task_id = task["task_id"]
    errors: list[str] = []
    model_calls = 0

    if candidate is None:
        candidate = task.get("candidate_output", {})

    outreach_text = candidate.get("outreach_text", "")
    cta_present_flag = candidate.get("cta_present")
    candidate_prefix = candidate.get("confidence_prefix")

    gt = task["ground_truth"]
    rubric = task["scoring_rubric"]
    evconfig = task["evaluator_config"]
    sig_brief = task["input"]["signal_brief"]
    icp_confidence = sig_brief.get("icp_confidence", 1.0)
    abstain_required = gt.get("abstain_required", False)
    confidence_prefix_required = gt.get("confidence_prefix_required", False)

    dim_map: dict[str, tuple[float, float]] = {}
    for d in rubric["dimensions"]:
        dim_map[d["name"]] = (d["weight"], d["max_score"])

    dimension_scores: list[DimensionScore] = []

    # 1. Banned phrase violations
    if "banned_phrase_violations" in dim_map:
        w, _ = dim_map["banned_phrase_violations"]
        raw, reason = score_banned_phrases(
            outreach_text,
            gt.get("banned_phrases", []),
            evconfig.get("banned_phrase_check", "regex"),
        )
        dimension_scores.append(DimensionScore("banned_phrase_violations", raw, w, raw * w, reason))

    # 2. Grounding signal presence
    if "grounding_signal_presence" in dim_map:
        w, _ = dim_map["grounding_signal_presence"]
        raw, reason = score_grounding_signals(
            outreach_text,
            gt.get("required_signals", []),
            evconfig.get("grounding_check", "keyword"),
        )
        dimension_scores.append(DimensionScore("grounding_signal_presence", raw, w, raw * w, reason))

    # 3. CTA presence
    if "cta_presence" in dim_map:
        w, _ = dim_map["cta_presence"]
        raw, reason = score_cta_presence(
            outreach_text,
            gt.get("required_cta_pattern", ""),
            cta_present_flag,
        )
        dimension_scores.append(DimensionScore("cta_presence", raw, w, raw * w, reason))

    # 4. Tone markers
    if "tone_markers" in dim_map:
        w, _ = dim_map["tone_markers"]
        raw, reason, calls = score_tone_markers(
            outreach_text,
            evconfig.get("judge_model", JUDGE_MODEL),
            OPENROUTER_API_KEY,
        )
        model_calls += calls
        dimension_scores.append(DimensionScore("tone_markers", raw, w, raw * w, reason))

    # 5. Confidence calibration
    if "confidence_calibration" in dim_map:
        w, _ = dim_map["confidence_calibration"]
        raw, reason = score_confidence_calibration(
            outreach_text,
            icp_confidence,
            abstain_required,
            confidence_prefix_required,
            candidate_prefix,
            evconfig.get("signal_confidence_mode", "confidence_aware"),
        )
        dimension_scores.append(DimensionScore("confidence_calibration", raw, w, raw * w, reason))

    # 6. Factual unsupported claims
    if "factual_unsupported_claims" in dim_map:
        w, _ = dim_map["factual_unsupported_claims"]
        raw, reason = score_factual_unsupported_claims(
            outreach_text,
        )
        dimension_scores.append(DimensionScore("factual_unsupported_claims", raw, w, raw * w, reason))

    total = sum(d.weighted for d in dimension_scores)
    total = min(1.0, max(0.0, total))
    pass_threshold = rubric.get("pass_threshold", 0.70)
    passed = total >= pass_threshold

    elapsed_ms = (time.monotonic() - start) * 1000.0

    return TaskScore(
        task_id=task_id,
        total_score=total,
        passed=passed,
        pass_threshold=pass_threshold,
        dimensions=dimension_scores,
        latency_ms=elapsed_ms,
        model_calls=model_calls,
        errors=errors,
    )


# ── Batch scorer ─────────────────────────────────────────────────────────────

def score_batch(
    jsonl_path: Path,
    candidates: dict[str, dict] | None = None,
) -> list[TaskScore]:
    """Score all tasks in a JSONL file."""
    results = []
    with jsonl_path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            task = json.loads(line)
            candidate = (candidates or {}).get(task["task_id"])
            results.append(score_task(task, candidate))
    return results


def summarise(scores: list[TaskScore]) -> dict:
    if not scores:
        return {}
    passed = [s for s in scores if s.passed]
    return {
        "total_tasks": len(scores),
        "passed": len(passed),
        "pass_at_1": round(len(passed) / len(scores), 4),
        "mean_score": round(sum(s.total_score for s in scores) / len(scores), 4),
        "total_model_calls": sum(s.model_calls for s in scores),
        "total_latency_ms": round(sum(s.latency_ms for s in scores), 1),
    }


# ── CLI ──────────────────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="TenaciousBench Scoring Evaluator v0.1",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--task", type=Path, help="Path to JSONL file containing task(s).")
    p.add_argument("--task-id", help="Score a single task by ID.")
    p.add_argument(
        "--candidate",
        help="JSON string of candidate output (overrides task's candidate_output).",
    )
    p.add_argument("--batch-dir", type=Path, help="Directory containing *.jsonl task files.")
    p.add_argument("--out", type=Path, help="Output JSONL path for batch results.")
    p.add_argument("--quiet", action="store_true", help="Suppress per-task output.")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.batch_dir:
        jsonl_files = sorted(args.batch_dir.glob("*.jsonl"))
        if not jsonl_files:
            print(f"No JSONL files found in {args.batch_dir}", file=sys.stderr)
            return 1

        all_scores: list[TaskScore] = []
        for jf in jsonl_files:
            all_scores.extend(score_batch(jf))

        summary = summarise(all_scores)
        if not args.quiet:
            print(json.dumps(summary, indent=2))

        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            with args.out.open("w", encoding="utf-8") as fh:
                for s in all_scores:
                    fh.write(json.dumps(s.to_dict()) + "\n")
            print(f"Results written to {args.out}")

        return 0 if summary.get("pass_at_1", 0) >= 0.5 else 1

    if not args.task:
        print("Provide --task or --batch-dir.", file=sys.stderr)
        return 2

    tasks_by_id: dict[str, dict] = {}
    with args.task.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            t = json.loads(line)
            tasks_by_id[t["task_id"]] = t

    if args.task_id:
        if args.task_id not in tasks_by_id:
            print(f"Task {args.task_id!r} not found in {args.task}", file=sys.stderr)
            return 1
        task = tasks_by_id[args.task_id]
        candidate = json.loads(args.candidate) if args.candidate else None
        result = score_task(task, candidate)
        print(json.dumps(result.to_dict(), indent=2))
        return 0 if result.passed else 1

    # Score all tasks in file
    all_scores = score_batch(args.task)
    summary = summarise(all_scores)
    if not args.quiet:
        print(json.dumps({"summary": summary, "scores": [s.to_dict() for s in all_scores]}, indent=2))

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("w", encoding="utf-8") as fh:
            for s in all_scores:
                fh.write(json.dumps(s.to_dict()) + "\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
