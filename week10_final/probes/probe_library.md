# Probe Library

Total probes: 
30

- P01 | ICP | Mid-market fintech appears enterprise due funding mention. | expected: False segment_2 assignment | cost: $8k ACV delay | severity: 4
- P02 | ICP | Low-confidence lead receives assertive outreach. | expected: Missed abstention | cost: 2% reply drop | severity: 4
- P03 | Tone | Email says guarantee results. | expected: Overclaim not blocked | cost: Brand risk on legal review | severity: 5
- P04 | Tone | Message sounds condescending to target team. | expected: Tone drift | cost: Thread stall 1 week | severity: 4
- P05 | Signal Reliability | Layoff signal outdated by 1 year. | expected: Stale signal use | cost: Wrong pitch path | severity: 4
- P06 | Signal Reliability | Jobs snapshot empty due parser issue. | expected: False low hiring intent | cost: Missed warm lead | severity: 3
- P07 | Scheduling | Booking timezone missing. | expected: Incorrect slot confirmation | cost: No-show risk | severity: 4
- P08 | Scheduling | Reply asks for meeting but route stays email-only. | expected: No schedule trigger | cost: Lower conversion | severity: 3
- P09 | CRM | Prospect has two emails same ID. | expected: Identity split | cost: Duplicate outreach | severity: 4
- P10 | CRM | Booking event not logged to HubSpot. | expected: Missing timeline event | cost: SDR blind handoff | severity: 5
- P11 | SMS | Cold lead receives SMS without email engagement. | expected: Warm-lead guard bypass | cost: Compliance risk | severity: 5
- P12 | SMS | Inbound SMS has malformed payload. | expected: Silent drop | cost: Lost response | severity: 4
- P13 | Email | Bounce webhook payload missing event field. | expected: No structured error | cost: Retry storm | severity: 4
- P14 | Email | Reply intent 'not now' misread as positive. | expected: Aggressive follow-up | cost: Unsubscribe risk | severity: 4
- P15 | Observability | Trace write throws exception. | expected: Pipeline crash | cost: Downtime | severity: 5
- P16 | Observability | Trace ID mismatch across booking and CRM. | expected: Broken lineage | cost: Audit failure | severity: 3
- P17 | Cost | LLM retries loop on 429 without backoff. | expected: Cost explosion | cost: Runaway spend | severity: 5
- P18 | Cost | No cache for repeated enrichment calls. | expected: Duplicate token burn | cost: 40% higher run cost | severity: 3
- P19 | Evaluation | Dev/test leakage in held-out run. | expected: Inflated metrics | cost: Bad go-live decision | severity: 5
- P20 | Evaluation | CI computed with too few resamples. | expected: Overconfident CI | cost: Misleading KPI | severity: 3
- P21 | Thread Safety | Lead A context appears in Lead B email. | expected: Cross-thread leakage | cost: Severe trust loss | severity: 5
- P22 | Thread Safety | Shared mutable state in cache overwrite. | expected: Nondeterministic outputs | cost: Debugging overhead | severity: 3
- P23 | Policy | Low-confidence signal phrased assertively. | expected: Confidence policy bypass | cost: Credibility erosion | severity: 4
- P24 | Policy | Binary threshold mode over-abstains. | expected: Missed opportunities | cost: Lower pipeline | severity: 3
- P25 | Integration | Cal.com webhook duplicate event. | expected: Double booking log | cost: CRM noise | severity: 2
- P26 | Integration | HubSpot API intermittent timeout. | expected: Unlogged interaction | cost: Ops blindspot | severity: 4
- P27 | Data Quality | Crunchbase sample missing founded_year. | expected: Partial profile normalization | cost: Lower personalization | severity: 2
- P28 | Data Quality | Leadership changes string malformed. | expected: False negative leadership signal | cost: Timing miss | severity: 3
- P29 | Security | Webhook includes oversized payload. | expected: Parser failure | cost: Endpoint instability | severity: 3
- P30 | Security | Unexpected HTML in inbound message. | expected: Improper sanitization | cost: Potential injection | severity: 4

---

## Rubric Category Coverage (10 Required Categories)

All 30 probes map to one of the 10 rubric-required categories. Each category has at least 2 probes.

| # | Rubric Category | Probes | Count |
|---|---|---|---|
| 1 | ICP Classification | P01, P02 | 2 |
| 2 | Signal Reliability & Grounding | P05, P06, P27, P28 | 4 |
| 3 | Tone & Language Policy | P03, P04, P23, P24 | 4 |
| 4 | Scheduling & Routing | P07, P08 | 2 |
| 5 | CRM & Calendar Integration | P09, P10, P25, P26 | 4 |
| 6 | SMS Compliance & Consent | P11, P12 | 2 |
| 7 | Email Delivery & Webhook Handling | P13, P14 | 2 |
| 8 | Observability & Trace Integrity | P15, P16, P29, P30 | 4 |
| 9 | Cost & Concurrency Safety | P17, P18, P21, P22 | 4 |
| 10 | Evaluation & Test Integrity | P19, P20 | 2 |

**Total: 30 probes across 10 rubric categories.**

### Category Rationale

- **ICP Classification (P01, P02):** Tests whether the segment classifier correctly handles boundary cases — a mid-market company that superficially resembles enterprise, and a low-confidence lead that should trigger abstention.
- **Signal Reliability & Grounding (P05, P06, P27, P28):** Covers stale signals, empty snapshots, and malformed input data that would cause the enrichment pipeline to produce unreliable outputs.
- **Tone & Language Policy (P03, P04, P23, P24):** Verifies the tone guardrail blocks overclaims ("guarantee"), catches condescending phrasing, and ensures confidence-aware conditioning is applied correctly.
- **Scheduling & Routing (P07, P08):** Validates that booking flows handle missing timezone data and correctly escalate meeting requests from email to calendar scheduling.
- **CRM & Calendar Integration (P09, P10, P25, P26):** Tests identity deduplication, booking event logging, duplicate webhook handling, and API timeout resilience.
- **SMS Compliance & Consent (P11, P12):** Ensures the warm-lead gate prevents cold-SMS violations and that malformed inbound SMS payloads are handled without silent drops.
- **Email Delivery & Webhook Handling (P13, P14):** Covers bounce webhook parsing and intent misclassification that would trigger inappropriate follow-ups.
- **Observability & Trace Integrity (P15, P16, P29, P30):** Validates trace write resilience, trace ID consistency across systems, and input sanitization for oversized/malformed payloads.
- **Cost & Concurrency Safety (P17, P18, P21, P22):** Tests retry-storm prevention, cache deduplication, cross-lead context isolation, and shared-state safety under concurrent load.
- **Evaluation & Test Integrity (P19, P20):** Ensures dev/held-out data isolation and that confidence intervals are computed with sufficient bootstrap resamples.
