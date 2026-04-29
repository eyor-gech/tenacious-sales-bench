# Target Failure Mode

## Selected Failure: Confidence-Policy Bypass → Over-Assertive Language on Low-Confidence Signals

### Why This Is the Primary Target

This failure mode is triggered when the confidence-policy layer (`agent/policies/signal_confidence.py`)
is skipped or misconfigured, causing low-confidence signal values to be phrased as high-certainty claims.
It directly degrades reply rate, erodes trust, and scales across **every** outreach thread — making it
the highest-leverage failure to address.

- Scope: all email and SMS channels
- Root cause: single misconfiguration in `SIGNAL_CONFIDENCE_MODE` env-var or caller bypassing the policy
- Mitigation mechanism: `signal_confidence.py` confidence-aware phrasing (Act IV)

---

## Business Cost Derivation

### Parameters

| Variable              | Value                | Source                                |
|-----------------------|----------------------|---------------------------------------|
| ACV                   | $5,000               | Assumed deal size for target segment  |
| Leads per month       | 400                  | Estimated pipeline throughput         |
| Failure rate          | 12 % (0.12)          | Estimated policy-bypass incident rate |
| Close-rate penalty    | 8 % (0.08)           | Estimated drop in close rate when trust eroded |
| Stalled-thread %      | 18 % (0.18)          | % of outreach threads that stall due to credibility mismatch |
| Thread stall duration | 1 week               | Average delay before prospect disengages |

### Arithmetic

**Monthly exposure (close-rate channel):**

```
affected_leads      = 400 × 0.12 = 48 leads
close_rate_loss     = 48 × $5,000 × 0.08 = $19,200 / month
```

**Monthly exposure (stalled-thread channel):**

```
stalled_threads     = 400 × 0.18 = 72 threads stalled
stall_conversion_loss = 72 × $5,000 × 0.04 (half the normal close-rate) = $14,400 / month
```

**Combined monthly exposure:**

```
total = $19,200 + $14,400 = $33,600 / month
annual_exposure = $33,600 × 12 = $403,200
```

This exposure exceeds the cost of implementing and maintaining the confidence-policy mechanism
(estimated 2 engineer-days, once). ROI is immediate.

---

## Comparison to Alternative Failure Modes

### Alternative 1: ICP Misclassification (P01, P02)

**Description:** Segment-1/2/3/4 assignment is wrong, causing wrong outreach pitch.

**Cost derivation:**
```
misclassification_rate = 8 % (estimated from ICP threshold sensitivity analysis)
affected_leads         = 400 × 0.08 = 32 leads / month
revenue_at_risk        = 32 × $5,000 × 0.05 (conversion delta) = $8,000 / month
```

**Why NOT selected as primary target:**
- Scope is narrower (only mis-classified leads, not the full pipeline)
- Mitigation (raise ICP threshold) has diminishing returns — abstention rate increases
- Fix is already implemented (abstention mechanism + probe P02)
- Monthly exposure ($8,000) is 4× lower than confidence-policy bypass

---

### Alternative 2: Stale Layoff Signal (P05)

**Description:** Layoff flag from > 90 days ago used as a live signal, causing wrong pitch angle
(budget-constrained tone sent to a company that has since recovered).

**Cost derivation:**
```
stale_signal_rate    = 15 % (estimated; layoffs.csv refreshed monthly)
affected_leads       = 400 × 0.15 = 60 leads / month
pitch_angle_mismatch = 60 × $5,000 × 0.03 (lower close-rate when pitch misaligned) = $9,000 / month
```

**Why NOT selected as primary target:**
- Root cause is data freshness, not an algorithm bug — fix is a pipeline refresh schedule
- Cannot be addressed by a code mechanism (Act IV); requires ops process change
- Monthly exposure ($9,000) is 3.7× lower than confidence-policy bypass

---

## Summary Comparison

| Failure Mode               | Monthly Exposure | Scope        | Fix Complexity | Selected? |
|----------------------------|-----------------|--------------|----------------|-----------|
| Confidence-policy bypass   | **$33,600**     | All threads  | Low (code)     | ✅ YES    |
| ICP misclassification      | $8,000          | Subset       | Medium         | ❌ No     |
| Stale layoff signal        | $9,000          | Subset       | Ops (data)     | ❌ No     |

The confidence-policy bypass failure has the highest monthly exposure, broadest scope,
and lowest fix complexity — making it the clear primary target.

---

## Mechanism (Act IV)

Fix implemented in `agent/policies/signal_confidence.py`.
Full re-implementation specification: see `probes/mechanism_design.md`.
