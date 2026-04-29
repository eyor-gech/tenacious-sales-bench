from __future__ import annotations

from typing import Literal


ToneMode = Literal["confidence_aware", "binary_threshold", "no_confidence"]


def phrasing_prefix(confidence: float, mode: ToneMode = "confidence_aware") -> str:
    if mode == "no_confidence":
        return "Based on current business signals,"
    if mode == "binary_threshold":
        return "Based on strong evidence," if confidence >= 0.7 else "Based on early indicators,"
    # confidence_aware
    if confidence >= 0.8:
        return "Based on high-confidence signals,"
    if confidence >= 0.55:
        return "Based on moderate-confidence indicators,"
    return "Based on exploratory low-confidence signals,"


def apply_confidence_conditioning(body: str, confidence: float, mode: ToneMode = "confidence_aware") -> str:
    prefix = phrasing_prefix(confidence, mode)
    return f"{prefix} {body}"

