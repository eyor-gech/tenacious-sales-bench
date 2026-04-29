from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent.core.state import CompanyInput
from agent.intelligence.competitor_gap import competitor_gap
from agent.intelligence.icp_classifier import classify_icp
from agent.signals.ai_maturity import score_ai_maturity
from agent.signals.scoring import compute_signals
from pipelines.enrichment.unified_signal_enrichment import build_unified_signal_schema
from pipelines.ingestion.job_scraper import load_job_snapshot
from pipelines.ingestion.leadership_loader import load_leadership_signal

_BASE = Path(__file__).resolve().parents[1]
_JOBS_SNAPSHOT = _BASE / "data" / "jobs_snapshot.json"

_FUNDING_STAGE_MAP = {
    "pre-seed": "seed", "seed": "seed",
    "series a": "series_a", "series b": "series_b", "series c": "series_c",
    "series d": "series_d_plus", "series e": "series_d_plus",
    "series f": "series_d_plus", "growth": "series_d_plus",
    "debt": "debt",
}


def _funding_stage(raw: str | None) -> str:
    if not raw:
        return "none"
    return _FUNDING_STAGE_MAP.get(raw.lower().strip(), "other")


def _velocity_label(today: int, ago: int) -> str:
    """Categorical 60-day velocity label per hiring_signal_brief schema."""
    if ago == 0:
        return "insufficient_signal"
    ratio = today / ago
    if ratio >= 3.0:
        return "tripled_or_more"
    if ratio >= 2.0:
        return "doubled"
    if today > ago:
        return "increased_modestly"
    if today == ago:
        return "flat"
    return "declined"


async def run_enrichment(
    company: CompanyInput,
    universe: list[CompanyInput],
    output_dir: Path,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()

    # ── Four signal modules ────────────────────────────────────────────────────
    # 1-4. LLM enrichment (crunchbase, jobPosts, layoffs, leadershipChanges)
    unified = await build_unified_signal_schema(company)

    # Signal 4 also via dedicated ingestion module (structured extraction)
    leadership_raw = load_leadership_signal(company)

    # ── Competitor gap brief ───────────────────────────────────────────────────
    gap = competitor_gap(company, universe)

    # ── AI maturity + ICP scoring ──────────────────────────────────────────────
    ai_score, ai_explanation = score_ai_maturity(company)
    signals, _, _ = compute_signals(company, len(company.open_roles))
    segment, segment_confidence, _ = classify_icp(company, signals, 0.62)

    # ── 60-day hiring velocity delta ───────────────────────────────────────────
    snapshot: dict[str, int] = {}
    snapshot_status = "no_data"
    if _JOBS_SNAPSHOT.exists():
        try:
            snapshot = load_job_snapshot(_JOBS_SNAPSHOT)
            snapshot_status = "success"
        except Exception:
            snapshot_status = "error"

    open_roles_today = len(company.open_roles)
    open_roles_60d_ago = snapshot.get(company.company_id, 0)
    vel_label = _velocity_label(open_roles_today, open_roles_60d_ago)
    vel_confidence = 0.75 if open_roles_60d_ago > 0 else 0.40

    # ── AI maturity justifications (per-signal breakdown) ──────────────────────
    ai_roles_count = sum(
        1 for r in company.open_roles if "ai" in r.lower() or "ml" in r.lower()
    )
    maturity_justifications = [
        {
            "signal": "ai_adjacent_open_roles",
            "status": (
                f"{ai_roles_count} AI/ML-adjacent open role(s) detected in current snapshot"
                if ai_roles_count else "No AI/ML roles in current job snapshot"
            ),
            "weight": "high",
            "confidence": "high" if ai_score >= 2 else ("medium" if ai_roles_count else "low"),
            "source_url": f"https://{company.domain}/careers",
        },
        {
            "signal": "executive_commentary",
            "status": (
                f"{len(company.exec_public_mentions)} exec public AI mention(s): "
                f"{company.exec_public_mentions[0][:80]}"
                if company.exec_public_mentions
                else "No exec AI commentary detected"
            ),
            "weight": "medium",
            "confidence": "medium" if company.exec_public_mentions else "low",
        },
        {
            "signal": "named_ai_ml_leadership",
            "status": (
                leadership_raw["changes_raw"][0]
                if leadership_raw.get("detected") and leadership_raw.get("changes_raw")
                else "No AI-profile leadership change detected"
            ),
            "weight": "high",
            "confidence": "high" if leadership_raw.get("ai_leadership_flag") else "low",
        },
        {
            "signal": "modern_data_ml_stack",
            "status": (
                f"Tech stack: {', '.join(company.tech_stack)}"
                if company.tech_stack else "No tech stack data available"
            ),
            "weight": "medium",
            "confidence": "medium" if company.tech_stack else "low",
        },
        {
            "signal": "github_org_activity",
            "status": (
                f"GitHub activity score: {company.github_activity_score:.2f}"
                if company.github_activity_score else "No GitHub activity data"
            ),
            "weight": "low",
            "confidence": "medium" if company.github_activity_score else "low",
        },
    ]

    # ── Honesty flags ──────────────────────────────────────────────────────────
    honesty_flags: list[str] = []
    if vel_label == "insufficient_signal":
        honesty_flags.append("weak_hiring_velocity_signal")
    if ai_score == 0:
        honesty_flags.append("weak_ai_maturity_signal")

    # ── Schema-compliant hiring_signal_brief ───────────────────────────────────
    hiring_signal_brief: dict[str, Any] = {
        # Required fields per hiring_signal_brief.schema.json
        "prospect_domain": company.domain,
        "prospect_name": company.name,
        "generated_at": now,
        "primary_segment_match": segment,
        "segment_confidence": round(segment_confidence, 3),
        "ai_maturity": {
            "score": ai_score,
            "confidence": round(unified["crunchbase"]["confidence"], 3),
            "justifications": maturity_justifications,
        },
        "hiring_velocity": {
            "open_roles_today": open_roles_today,
            "open_roles_60_days_ago": open_roles_60d_ago,
            "velocity_label": vel_label,
            "signal_confidence": round(vel_confidence, 3),
            "sources": ["builtin"],
        },
        "buying_window_signals": {
            "funding_event": {
                "detected": company.latest_funding_date is not None,
                "stage": _funding_stage(company.latest_funding_round),
                "closed_at": company.latest_funding_date,
            },
            "layoff_event": {
                "detected": company.layoffs_reported,
            },
            "leadership_change": {
                "detected": leadership_raw.get("detected", False),
                "role": leadership_raw.get("inferred_role", "none"),
            },
        },
        "tech_stack": company.tech_stack,
        "data_sources_checked": [
            {
                "source": "crunchbase",
                "status": "success",
                "fetched_at": unified["crunchbase"]["collected_at"],
            },
            {
                "source": "jobs_snapshot",
                "status": snapshot_status,
                "fetched_at": unified["jobPosts"]["collected_at"],
            },
            {
                "source": "layoffs.fyi",
                "status": "success",
                "fetched_at": unified["layoffs"]["collected_at"],
            },
            {
                "source": "news/linkedin",
                "status": "success" if leadership_raw.get("detected") else "no_data",
                "fetched_at": unified["leadershipChanges"]["collected_at"],
            },
        ],
        "honesty_flags": honesty_flags,
        # Backward-compat: signals dict kept for orchestrator.py access
        "signals": unified,
    }

    # gap is already schema-compliant
    competitor_gap_brief = gap

    (output_dir / "hiring_signal_brief.json").write_text(
        json.dumps(hiring_signal_brief, indent=2, default=str),
        encoding="utf-8",
    )
    (output_dir / "competitor_gap_brief.json").write_text(
        json.dumps(competitor_gap_brief, indent=2, default=str),
        encoding="utf-8",
    )
    return {
        "hiring_signal_brief": hiring_signal_brief,
        "competitor_gap_brief": competitor_gap_brief,
    }
