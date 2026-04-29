# Failure Taxonomy

## Category Definitions

Six top-level failure categories, each covering specific failure modes detected by the adversarial probe suite.

---

### 1. Revenue Leakage
Wrong routing, missed warm leads, stalled conversion threads.

**Failure modes:**
- ICP false-positive → aggressive outreach to wrong segment → no reply
- ICP false-negative → valid lead not contacted → pipeline miss
- Scheduling route not triggered → meeting never booked
- SMS fallback not sent when email bounces → thread stalls

**Probes mapped:** P01, P02, P07, P08

**Aggregate trigger rate:** computed at runtime (`eval/probe_results.json` → categories: ICP, Scheduling)

---

### 2. Brand / Reputation Harm
Overclaiming, condescending tone, exaggerated or ungrounded confidence language.

**Failure modes:**
- Tone guardrail bypassed → "guarantee results" left in email → legal risk
- Condescending framing detected by prospect → thread abandoned
- Low-confidence signal phrased assertively → credibility erosion
- Binary threshold over-abstains → pipeline starved

**Probes mapped:** P03, P04, P23, P24

**Aggregate trigger rate:** computed at runtime (categories: Tone, Policy)

---

### 3. Operational Blind Spots
Missing CRM events, broken trace lineage, silent drop of inbound messages.

**Failure modes:**
- Booking event not logged to HubSpot → SDR blind handoff
- Duplicate prospect identity → double outreach
- Trace write exception → pipeline crash, unrecoverable
- Trace ID mismatch across services → audit failure

**Probes mapped:** P09, P10, P15, P16, P25, P26

**Aggregate trigger rate:** computed at runtime (categories: CRM, Observability, Integration)

---

### 4. Compliance / Safety Risk
Warm-lead guard bypass, malformed webhook data, injection vectors.

**Failure modes:**
- Cold lead receives SMS without prior email engagement → consent violation
- Malformed inbound SMS silently dropped → lost lead response
- Bounce webhook missing `event` field → no structured error emitted
- Reply intent misclassified (`not_now` → `positive`) → aggressive follow-up
- HTML injection in inbound message not sanitised → potential code execution
- Oversized webhook payload accepted → endpoint instability / DoS vector

**Probes mapped:** P11, P12, P13, P14, P29, P30

**Aggregate trigger rate:** computed at runtime (categories: SMS, Email, Security)

---

### 5. Economic Inefficiency
Token cost overruns, retry storms, duplicate LLM calls, inflated run cost.

**Failure modes:**
- 429 retry loop without exponential backoff → runaway spend
- No cache for repeated enrichment calls → 40 % higher per-run cost
- Shared mutable state in cache overwrite → non-deterministic outputs, debugging overhead
- Lead context leaks across threads → trust loss + data remediation cost

**Probes mapped:** P17, P18, P21, P22

**Aggregate trigger rate:** computed at runtime (categories: Cost, Thread Safety)

---

### 6. Evaluation Distortion
Dev/held-out leakage, weak statistical confidence, misleading KPIs.

**Failure modes:**
- Dev and held-out sets share company samples → inflated pass@1
- Confidence interval computed with too few resamples → overconfident CI
- Stale layoff signal used in scoring → wrong pitch path
- Empty jobs snapshot → false low-hiring-intent

**Probes mapped:** P05, P06, P19, P20

**Aggregate trigger rate:** computed at runtime (categories: Signal Reliability, Evaluation)

---

## Probe → Category Cross-Reference

| Probe ID | Scenario (short)                        | Failure Category         |
|----------|-----------------------------------------|--------------------------|
| P01      | Mid-market fintech mislabelled enterprise | Revenue Leakage          |
| P02      | Low-confidence assertive outreach       | Revenue Leakage          |
| P03      | "Guarantee results" not blocked         | Brand / Reputation Harm  |
| P04      | Condescending tone                      | Brand / Reputation Harm  |
| P05      | Stale layoff signal (1 year old)        | Evaluation Distortion    |
| P06      | Empty jobs snapshot                     | Evaluation Distortion    |
| P07      | Booking timezone missing                | Revenue Leakage          |
| P08      | Meeting request routed email-only       | Revenue Leakage          |
| P09      | Duplicate prospect identity             | Operational Blind Spots  |
| P10      | Booking not logged to HubSpot           | Operational Blind Spots  |
| P11      | Cold SMS without email engagement       | Compliance / Safety Risk |
| P12      | Malformed inbound SMS                   | Compliance / Safety Risk |
| P13      | Bounce webhook missing `event` field    | Compliance / Safety Risk |
| P14      | `not_now` misread as positive           | Compliance / Safety Risk |
| P15      | Trace write throws exception            | Operational Blind Spots  |
| P16      | Trace ID mismatch CRM ↔ booking         | Operational Blind Spots  |
| P17      | 429 retry loop without backoff          | Economic Inefficiency    |
| P18      | No cache for repeated enrichment        | Economic Inefficiency    |
| P19      | Dev/test leakage in held-out run        | Evaluation Distortion    |
| P20      | CI with too few resamples               | Evaluation Distortion    |
| P21      | Lead-A context in Lead-B email          | Economic Inefficiency    |
| P22      | Shared mutable cache overwrite          | Economic Inefficiency    |
| P23      | Low-confidence signal phrased assertive | Brand / Reputation Harm  |
| P24      | Binary threshold over-abstains          | Brand / Reputation Harm  |
| P25      | Cal.com duplicate booking event         | Operational Blind Spots  |
| P26      | HubSpot intermittent timeout            | Operational Blind Spots  |
| P27      | Crunchbase missing `founded_year`       | Evaluation Distortion    |
| P28      | Leadership changes string malformed     | Evaluation Distortion    |
| P29      | Oversized webhook payload               | Compliance / Safety Risk |
| P30      | HTML injection in inbound message       | Compliance / Safety Risk |

All 30 probes are mapped. No orphan probes.

---

## How Trigger Rates Are Computed

Run `eval/probe_runner.py` (or `python -m eval.probe_runner`).
The runner classifies each probe scenario via LLM, computes per-category trigger rates,
and writes `eval/probe_results.json` with the structure:

```json
{
  "total_probes": 30,
  "trigger_rate_by_category": { "ICP": 0.5, "Tone": 0.5, ... },
  "traces": [...]
}
```
