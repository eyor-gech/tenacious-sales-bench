# Audit Memo: Gaps Between τ²-Bench and Tenacious B2B Outbound Evaluation

**Date:** 2026-04-29 | **Author:** Eyor Getachew

---

## 1. Signal Grounding Fidelity — P05, P06

τ²-Bench has no temporal signal metadata. **P05** documents a 14-month-old layoff event used as a live buying-window signal; **P06** documents a `weak_hiring_velocity_signal` flag silently ignored by the outreach composer. Held-out trace `4f36e1b0` (task_id=5, pass) validated that the signal_date fell within 60 days before the confidence prefix fired — a check τ²-Bench cannot grade.

## 2. ICP Abstention Boundary — P01, P02

**P01** shows false-positive segment assignment at confidence=0.58; **P02** shows a staging misconfiguration that moved the threshold to 0.50, causing below-threshold leads to receive a segment-specific pitch. τ²-Bench has no gating decision where the false-positive carries a documented business cost ($1,200 in pipeline per incident).

## 3. Confidence Calibration — P23, P24

The Week 10 ablation showed `confidence_aware` at 0.76 vs `no_confidence` at 0.66 — a 10 pp gap from hedged language alone. Held-out trace `0e82a222` (task_id=9, fail) failed because an assertive claim was made at confidence=0.63, exactly the boundary where **P24** fires (binary mode under-pitching a warm prospect). τ²-Bench scores instruction-following, not claim calibration.

## 4. Consent-Gated Channel Routing — P11, P12, P14

**P11** tests the warm-lead gate when `prior_email_engagement` is absent from `lead_context`. **P12** tests inbound SMS handling with a missing `msisdn` field. **P14** tests that `intent=not_now` routes to `stop`. Act II thread `thread-cmp_001` demonstrated the live routing path before the SMS channel opened. τ²-Bench has no consent state across channels.

## 5. Tone and Overclaim Detection — P03, P04

**P03** bypasses the tone guardrail via the predicate construction "will be operational" (not caught by lexical "guarantee" match). **P04** tests condescending framing ("clearly lacks"). Held-out trace `3e366b47` (task_id=12, pass) passed because `apply_tone_guardrail()` blocked the guarantee variant. Generic benchmarks score delivery, not content safety.

## 6. Multi-Turn Scheduling Integrity — P07, P08

**P07** exposes timezone extraction failure ("Nairobi time" not resolved to UTC+3). **P08** tests that "Can we book Thursday 2pm?" classifies as `intent=book_meeting`. Held-out trace `1c09a942` (task_id=17, pass) correctly resolved the booking intent and triggered the Cal.com link. τ²-Bench is single-session and stateless.

## 7. CRM and Trace Auditability — P09, P10, P16

The Act IV run produced `[FALLBACK] rate-limited/unavailable` on the HubSpot write (**P10**). **P16** documents trace ID mismatch between the Resend email event and Cal.com booking event. Held-out trace `df2250dc` (task_id=18, pass) closed the loop with a matched trace ID. τ²-Bench has no concept of CRM or cross-service lineage.

## 8. Evaluation Contamination *(non-obvious gap)* — P19, P20

This gap is about benchmark construction integrity, not agent output. **P19** documents case-sensitive task-ID dedup failure that inflates held-out pass@1 from 0.85 to 0.90. **P20** documents bootstrap CI inflation from 100 vs 10,000 resamples. Held-out trace `5f40e1b4` (task_id=39, fail) was a real false-pass at the dev boundary caught only after case-insensitive dedup. τ²-Bench does not audit its own evaluation pipeline.

---

**Summary:** Eight mutually distinct gaps, 18 probe citations, five held-out trace IDs. The non-obvious gap (section 8) distinguishes benchmark construction integrity from agent quality — a dimension generic benchmarks cannot address by design.
