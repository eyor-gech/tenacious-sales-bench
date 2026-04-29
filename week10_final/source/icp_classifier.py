from __future__ import annotations

from agent.core.state import CompanyInput, SignalRecord


SEGMENTS = ("segment_1", "segment_2", "segment_3", "segment_4")


def classify_icp(
    company: CompanyInput,
    signals: dict[str, SignalRecord],
    threshold: float,
) -> tuple[str, float, str]:
    score = 0.0
    rationale: list[str] = []

    if signals["funding_recency"].value:
        score += 0.30
        rationale.append("recent funding")
    if signals["job_velocity"].value > 0:
        score += 0.20
        rationale.append("positive hiring velocity")
    if signals["layoffs"].value:
        score += 0.10
        rationale.append("active transformation after layoffs")
    if signals["tech_stack_match"].value >= 0.2:
        score += 0.20
        rationale.append("compatible data/AI stack")
    if signals["ai_maturity"].value >= 2:
        score += 0.20
        rationale.append("AI maturity 2+")

    confidence = round(min(1.0, score), 3)
    if confidence < threshold:
        return "abstain", confidence, "; ".join(rationale) or "insufficient evidence"

    if company.industry.lower() in {"fintech", "healthtech"}:
        segment = "segment_1"
    elif company.employee_count >= 1000:
        segment = "segment_2"
    elif signals["ai_maturity"].value >= 2:
        segment = "segment_3"
    else:
        segment = "segment_4"

    return segment, confidence, "; ".join(rationale)
