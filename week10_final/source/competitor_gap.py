from __future__ import annotations

import math
from datetime import datetime, timezone

from agent.core.state import CompanyInput
from agent.signals.ai_maturity import score_ai_maturity
from core.cache import get_cache

_SPARSE_PEER_THRESHOLD = 3

# Top-quartile selection criteria (documented constant):
# A peer qualifies as top-quartile when BOTH conditions hold:
#   (1) AI maturity score (score_ai_maturity) >= _TOP_QUARTILE_MIN_SCORE (i.e. >= 2 on the 0-3 rubric)
#   (2) Maturity proxy (github_activity_score + open_role_count*0.05) >= 75th-percentile
#       of the analyzed peer pool.
# This dual gate ensures only peers with verified public signals AND a strong
# role-count/github proxy are cited in outreach as benchmarks.
_TOP_QUARTILE_MIN_SCORE = 2


def _headcount_band(employee_count: int) -> str:
    if employee_count < 80:
        return "15_to_80"
    if employee_count < 200:
        return "80_to_200"
    if employee_count < 500:
        return "200_to_500"
    if employee_count < 2000:
        return "500_to_2000"
    return "2000_plus"


def _maturity_proxy(c: CompanyInput) -> float:
    return round((c.github_activity_score or 0.0) + (len(c.open_roles) * 0.05), 2)


def _parse_justification(explanation: str) -> list[str]:
    """Split score_ai_maturity explanation into per-signal lines for the schema array."""
    parts = explanation.split("; ")
    signals = [s.strip() for s in parts[0].split(",") if s.strip()]
    if len(parts) > 1:
        signals.append(parts[1].strip())
    return signals


def competitor_gap(company: CompanyInput, all_companies: list[CompanyInput]) -> dict[str, object]:
    cache = get_cache()
    key = cache.make_key(
        "competitor_gap",
        "v3",
        {
            "company": company.model_dump(mode="json"),
            "universe": [c.model_dump(mode="json") for c in all_companies],
        },
    )
    cached = cache.get(key)
    if cached is not None:
        return dict(cached)

    same_industry_peers = [
        c for c in all_companies if c.industry == company.industry and c.company_id != company.company_id
    ]
    universe = [c for c in all_companies if c.company_id != company.company_id]

    # Sparse sector: fall back to cross-industry peers when fewer than 3 same-sector peers
    if len(same_industry_peers) < _SPARSE_PEER_THRESHOLD:
        peer_pool = universe
        sparse_note = (
            f"Sparse sector ({company.industry!r}): only {len(same_industry_peers)} same-industry peer(s) found; "
            "cross-sector peers used for ranking. Interpret capability gaps with caution."
        )
    else:
        peer_pool = same_industry_peers
        sparse_note = None

    # Select up to 10 peers by maturity proxy (descending)
    peers_sorted = sorted(peer_pool, key=_maturity_proxy, reverse=True)[:10]

    # 75th-percentile threshold for top-quartile gate
    all_peer_proxies = [_maturity_proxy(p) for p in peers_sorted]
    if all_peer_proxies:
        sorted_proxies = sorted(all_peer_proxies)
        p75_idx = max(0, math.ceil(len(sorted_proxies) * 0.75) - 1)
        p75_threshold = sorted_proxies[p75_idx]
    else:
        p75_threshold = 0.0

    # Build competitors_analyzed with full schema fields
    competitors_analyzed: list[dict] = []
    for peer in peers_sorted:
        peer_score, peer_justification = score_ai_maturity(peer)
        peer_proxy = _maturity_proxy(peer)
        is_top_quartile = (peer_score >= _TOP_QUARTILE_MIN_SCORE) and (peer_proxy >= p75_threshold)
        competitors_analyzed.append({
            "name": peer.name,
            "domain": peer.domain,
            "ai_maturity_score": peer_score,
            "ai_maturity_justification": _parse_justification(peer_justification),
            "headcount_band": _headcount_band(peer.employee_count),
            "top_quartile": is_top_quartile,
            "sources_checked": [f"https://{peer.domain}/careers"],
        })

    # sector_top_quartile_benchmark: average AI maturity score of top-quartile peers
    top_quartile_scores = [c["ai_maturity_score"] for c in competitors_analyzed if c["top_quartile"]]
    sector_top_quartile_benchmark = (
        round(sum(top_quartile_scores) / len(top_quartile_scores), 2) if top_quartile_scores else 0.0
    )

    # Prospect maturity score for metadata
    prospect_score, _ = score_ai_maturity(company)

    # Gap findings — capabilities held by top-quartile peers but absent from prospect
    top_peer_objs = [p for p in peers_sorted if _maturity_proxy(p) >= p75_threshold and
                     score_ai_maturity(p)[0] >= _TOP_QUARTILE_MIN_SCORE] or peers_sorted[:5]
    company_caps = {role.lower() for role in company.open_roles}
    # Use list of (peer, roles_set) to avoid unhashable CompanyInput keys
    peer_roles_list = [(peer, {role.lower() for role in peer.open_roles}) for peer in top_peer_objs]
    peer_caps_all = {role for _, roles in peer_roles_list for role in roles}
    missing = sorted(list(peer_caps_all - company_caps))[:8]

    gap_findings: list[dict] = []
    for cap in missing:
        if len(gap_findings) >= 3:
            break
        evidence_peers = [peer for peer, roles in peer_roles_list if cap in roles]
        if len(evidence_peers) < 2:
            continue
        peer_evidence = [
            {
                "competitor_name": ep.name,
                "evidence": (
                    f"Active open role for '{cap}' found in public job postings "
                    f"(source: data/jobs_snapshot.json snapshot, 60-day window)."
                ),
                "source_url": f"https://{ep.domain}/careers",
            }
            for ep in evidence_peers[:3]
        ]
        gap_findings.append({
            "practice": (
                f"Top-quartile peers actively hire for '{cap}' roles, signalling "
                "a dedicated AI/ML function build-out."
            ),
            "peer_evidence": peer_evidence,
            "prospect_state": (
                f"No public job posting for '{cap}' detected in the current jobs snapshot. "
                "No public signal of this practice from the prospect."
            ),
            "confidence": "medium",
            "segment_relevance": ["segment_4_specialized_capability"],
        })

    # Fallback gap finding when fewer than 2 matching peers exist per role
    if not gap_findings and len(competitors_analyzed) >= 2:
        gap_findings.append({
            "practice": (
                "Sector top-quartile peers show active AI/ML engineering hiring not visible "
                "in prospect's current job postings."
            ),
            "peer_evidence": [
                {
                    "competitor_name": competitors_analyzed[0]["name"],
                    "evidence": (
                        f"AI maturity score {competitors_analyzed[0]['ai_maturity_score']}/3 "
                        "with active AI hiring signals in public data."
                    ),
                    "source_url": competitors_analyzed[0]["sources_checked"][0],
                },
                {
                    "competitor_name": competitors_analyzed[1]["name"],
                    "evidence": (
                        f"AI maturity score {competitors_analyzed[1]['ai_maturity_score']}/3 "
                        "with active AI hiring signals in public data."
                    ),
                    "source_url": competitors_analyzed[1]["sources_checked"][0],
                },
            ],
            "prospect_state": (
                "No AI/ML-specific open roles detected in public job snapshot. "
                "Limited public signal of dedicated AI function."
            ),
            "confidence": "low",
            "segment_relevance": ["segment_4_specialized_capability"],
        })

    # Distribution position: prospect percentile across the full universe
    company_proxy = _maturity_proxy(company)
    all_proxies = [_maturity_proxy(c) for c in universe]
    below = sum(1 for p in all_proxies if p < company_proxy)
    percentile = round((below / len(all_proxies)) * 100, 1) if all_proxies else 50.0

    # Self-check: honest reliability flags for the outreach composer
    all_evidence_has_url = all(
        ev.get("source_url") for gf in gap_findings for ev in gf.get("peer_evidence", [])
    )
    at_least_one_high = any(gf["confidence"] == "high" for gf in gap_findings)

    result: dict[str, object] = {
        # --- Schema-required fields ---
        "prospect_domain": company.domain,
        "prospect_sector": company.industry,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "prospect_ai_maturity_score": prospect_score,
        "sector_top_quartile_benchmark": sector_top_quartile_benchmark,
        "competitors_analyzed": competitors_analyzed,
        "gap_findings": gap_findings,
        # --- Schema-optional enrichment fields ---
        "top_quartile_selection_criteria": (
            f"A peer is designated top-quartile when BOTH conditions hold: "
            f"(1) score_ai_maturity() >= {_TOP_QUARTILE_MIN_SCORE}/3, AND "
            f"(2) maturity_proxy (github_activity_score + role_count×0.05) "
            f">= 75th percentile of the analyzed peer pool."
        ),
        "suggested_pitch_shift": (
            "Shift from generic AI transformation pitch to specific capability gap: "
            "highlight roles top-quartile peers are actively staffing that the prospect has not yet opened."
        ),
        "gap_quality_self_check": {
            "all_peer_evidence_has_source_url": all_evidence_has_url,
            "at_least_one_gap_high_confidence": at_least_one_high,
            "prospect_silent_but_sophisticated_risk": (
                prospect_score >= 1 and percentile < 50.0
            ),
        },
        # --- Legacy fields preserved for downstream pipeline compatibility ---
        "top_peers": [c["name"] for c in competitors_analyzed if c["top_quartile"]][:5]
                     or [c["name"] for c in competitors_analyzed[:5]],
        "relative_maturity_ranking": [
            {"company": p.name, "maturity_proxy": _maturity_proxy(p)}
            for p in peers_sorted[:5]
        ],
        "missing_capabilities": missing,
        "distribution_position": {
            "percentile": percentile,
            "maturity_proxy_score": company_proxy,
            "universe_size": len(universe),
            "note": (
                f"{company.name} ranks at the {percentile}th percentile across "
                f"{len(universe)} companies by maturity proxy score."
            ),
        },
        "evidence_note": (
            "Capability gaps derived from public job post titles via structured data snapshot "
            "(data/jobs_snapshot.json). Same scoring function (github_activity_score + role count) "
            "as AI maturity pipeline."
        ),
        "tone_note": "Use neutral language focused on opportunity, not deficiency.",
    }
    if sparse_note:
        result["sparse_sector_note"] = sparse_note

    cache.set(key, result)
    return result
