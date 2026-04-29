# Audit Memo: Why τ²-Bench Retail/Generic Benchmarks Fail for Tenacious B2B Outbound Sales Agents

**Date:** 2026-04-29  
**Author:** Eyor Getachew  
**Version:** 1.0  

---

## 1. The Gap in One Sentence

τ²-Bench retail tasks evaluate whether an LLM can complete a browser-based purchase workflow. Tenacious agents must do something categorically harder: synthesize multi-source buying signals, calibrate factual claims to data confidence, route across channels under consent constraints, and produce outreach that survives legal, brand, and competitive scrutiny — none of which appears in the τ²-Bench task distribution.

---

## 2. What τ²-Bench Measures

τ²-Bench (retail/generic split) scores agents on:

- **Task completion rate (pass@1):** Did the agent finish the transaction?
- **Instruction following:** Did the agent respect the structured task description?
- **Grounding to a fixed web state:** Does the output match a deterministic ground truth (cart total, form field value)?

These properties are necessary but insufficient for B2B outbound evaluation. The retail environment has a closed action space (click, type, submit), a single-session context, and a binary pass/fail determined by a verifiable end-state. B2B outbound agents operate in an open, multi-turn, multi-channel environment where the correctness of an action depends on *what the agent claims*, not just *that the agent completed the action*.

---

## 3. The Eight Dimensions τ²-Bench Cannot Score

### 3.1 Signal Grounding Fidelity (Probes P05, P06, P27, P28)

τ²-Bench has no concept of "stale signals." A retail task does not penalize an agent for citing a year-old price; the price is either correct at evaluation time or not. In Tenacious, **P05** shows a ClinixFlow outreach built on a 14-month-old layoff event that the system treated as a live buying-window signal. **P06** demonstrates a hiring-velocity claim fired despite a `weak_hiring_velocity_signal` honesty flag in the brief. Generic benchmarks cannot surface these failures because they have no temporal signal metadata.

**Trace evidence:** Act II NileLedger thread — the `hiring_signal_brief` timestamps on `open_roles_today=3` and `open_roles_60_days_ago=2` were validated to be within 60 days. Without that explicit check, the Week 10 system would have issued a stale-signal outreach identical to the P05 failure mode.

### 3.2 Confidence Calibration (Probe P23, P24; Ablation: 0.76 vs 0.66)

τ²-Bench retail tasks do not require agents to modulate the certainty of their assertions based on upstream data quality. Tenacious's Week 10 ablation (Act IV) showed that `confidence_aware` phrasing achieved 0.76 pass@1 versus 0.66 for `no_confidence` — a 10 pp gap attributable entirely to calibrated hedging. **P23** specifically encodes the failure where a moderate-confidence lead receives an assertive three-peer claim that the data supports for only two. τ²-Bench offers no equivalent rubric.

### 3.3 ICP Boundary Precision (Probes P01, P02)

ICP classifier abstention (threshold = 0.62) is a Tenacious-specific gate with direct pipeline-cost consequences. **P01** documents a false-positive segment assignment at confidence=0.58; **P02** documents a staging misconfiguration that moves the threshold to 0.50. No τ²-Bench task involves a probabilistic gating decision with a business-cost penalty on the false-positive side.

### 3.4 Consent-Gated Channel Routing (Probes P11, P12, P14)

SMS warm-lead consent is a compliance requirement absent from any retail benchmark. **P11** tests whether the warm-lead gate fires correctly when the `prior_email_engagement` key is missing from `lead_context`. **P12** tests inbound SMS webhook handling when the `msisdn` field is absent. **P14** tests whether `intent=not_now` correctly routes to `stop` rather than `email_followup`. τ²-Bench has no multi-channel routing logic and no concept of consent state.

### 3.5 Tone and Brand Safety (Probes P03, P04)

Retail benchmarks score correctness of output fields. They do not evaluate whether the output contains overclaims ("guarantee," P03) or condescending framing ("clearly lacks," P04). A τ²-Bench evaluator that sees the NileLedger guarantee email would score it as task-complete because the email was sent. Tenacious's evaluator must flag it as a severity-5 failure.

### 3.6 Multi-Turn Scheduling Integrity (Probe P07, P08)

**P07** exposes timezone extraction failure (Nairobi time not resolved to UTC+3). **P08** tests whether a "Can we book Thursday 2pm?" message correctly triggers `intent=book_meeting` rather than `intent=unknown`. Neither failure is capturable by τ²-Bench's single-session, stateless task structure.

### 3.7 CRM/Trace Auditability (Probes P09, P10, P16)

The Act II NileLedger run produced a HubSpot `[FALLBACK] rate-limited/unavailable` event for the booking summary write — a real operational failure documented in `act4_invoice_summary.json`. τ²-Bench has no concept of downstream CRM event integrity or trace ID lineage. **P16** encodes the specific failure where the Resend email trace and the Cal.com booking trace carry different IDs, breaking the audit chain.

### 3.8 Evaluation Integrity (Probes P19, P20)

**P19** documents case-sensitive task-ID deduplication failure that would allow dev/held-out leakage. **P20** documents bootstrap CI inflation from 100 vs 10,000 resamples. τ²-Bench does not test the pipeline that *runs* the evaluation — it is the evaluation. A benchmark that evaluates B2B sales agents must itself be auditable; TenaciousBench includes contamination checks and statistical validity probes that τ²-Bench lacks by design.

---

## 4. Summary Gap Table

| Dimension | τ²-Bench (retail) | TenaciousBench |
|-----------|-------------------|----------------|
| Signal staleness detection | ✗ | ✓ (P05, P06) |
| Confidence calibration scoring | ✗ | ✓ (P23, P24) |
| ICP abstention boundary | ✗ | ✓ (P01, P02) |
| Consent-gated channel routing | ✗ | ✓ (P11, P12, P14) |
| Tone and overclaim detection | ✗ | ✓ (P03, P04) |
| Multi-turn scheduling (TZ) | ✗ | ✓ (P07, P08) |
| CRM / trace auditability | ✗ | ✓ (P09, P10, P16) |
| Evaluation contamination checks | ✗ | ✓ (P19, P20) |

---

## 5. Conclusion

The eight dimensions above are not edge cases. They are the principal failure modes documented at 100 % trigger rate across all 30 Week 10 adversarial probes, each with quantified business cost (range: $360–$33,600/month). A benchmark that cannot surface these failures cannot drive alignment toward a production-safe B2B sales agent. TenaciousBench v0.1 is designed to fill this gap.
