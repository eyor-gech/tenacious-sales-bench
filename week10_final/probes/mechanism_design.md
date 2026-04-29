# Act IV — Mechanism Design: Confidence-Aware Phrasing Policy

## Problem Statement

When the system's confidence in a signal is low (< 0.55), outreach copy must not phrase that signal as
certain fact. The absence of this guardrail causes the **confidence-policy bypass** failure mode
(see `probes/target_failure_mode.md`), inflating claims and eroding prospect trust.

## Root Cause

The `apply_confidence_conditioning()` function in `agent/policies/signal_confidence.py` is the single
entry-point for confidence-aware phrasing. It is bypassed when:

1. The caller passes the signal body directly to the email/SMS generator without calling this function, or
2. `SIGNAL_CONFIDENCE_MODE=no_confidence` is set in the environment (disables confidence prefix entirely),
   which collapses all three modes to the same neutral prefix regardless of signal confidence.

The validator (`agent/outreach/validator.py`) currently blocks overclaims on **lexical** patterns
(e.g., "guarantee") but does not check whether confidence conditioning was applied — leaving a gap
between tone guardrails and policy enforcement.

---

## Mechanism Description

### Location

`agent/policies/signal_confidence.py`

### Core Logic

```python
ToneMode = Literal["confidence_aware", "binary_threshold", "no_confidence"]

def phrasing_prefix(confidence: float, mode: ToneMode = "confidence_aware") -> str:
    if mode == "no_confidence":
        return "Based on current business signals,"  # static, no confidence reflected
    if mode == "binary_threshold":
        return "Based on strong evidence," if confidence >= 0.7 else "Based on early indicators,"
    # confidence_aware (default)
    if confidence >= 0.80:
        return "Based on high-confidence signals,"
    if confidence >= 0.55:
        return "Based on moderate-confidence indicators,"
    return "Based on exploratory low-confidence signals,"

def apply_confidence_conditioning(body: str, confidence: float, mode: ToneMode = "confidence_aware") -> str:
    prefix = phrasing_prefix(confidence, mode)
    return f"{prefix} {body}"
```

### Integration Points

| Call Site                              | Confidence Source                     |
|----------------------------------------|---------------------------------------|
| `agent/outreach/email_generator.py`    | `scored.icp_confidence`               |
| `agent/outreach/sms_generator.py`      | `scored.icp_confidence`               |
| `agent/intelligence/insight_engine.py` | signal-level confidence from `signals` dict |

### How to Re-Implement

1. Import `apply_confidence_conditioning` from `agent.policies.signal_confidence`.
2. After generating the raw outreach body, call:
   ```python
   body = apply_confidence_conditioning(body, confidence=scored.icp_confidence)
   ```
3. Ensure `SIGNAL_CONFIDENCE_MODE` is set to `"confidence_aware"` (default) in `.env`.
4. The validator (`validate_outreach`) must run **after** conditioning to catch any remaining overclaims.

---

## Hyperparameters

| Parameter                    | Default Value         | Location                           | Effect on Behaviour |
|------------------------------|-----------------------|------------------------------------|---------------------|
| `SIGNAL_CONFIDENCE_MODE`     | `confidence_aware`    | `.env` / `config/settings.yaml`    | Selects phrasing mode (see below) |
| `high_confidence_threshold`  | `0.80`                | `signal_confidence.py` line 16     | Above → "high-confidence signals" |
| `moderate_confidence_lower`  | `0.55`                | `signal_confidence.py` line 18     | Between 0.55–0.80 → "moderate-confidence indicators" |
| `binary_threshold_cutoff`    | `0.70`                | `signal_confidence.py` line 13     | Binary mode split point |
| `icp_threshold`              | `0.62`                | `config/settings.yaml`             | Below → ICP abstention (no outreach) |

### Mode Comparison

| Mode                | Confidence < 0.55       | 0.55 ≤ conf < 0.80          | conf ≥ 0.80             |
|---------------------|-------------------------|-----------------------------|-------------------------|
| `confidence_aware`  | "exploratory low-confidence signals" | "moderate-confidence indicators" | "high-confidence signals" |
| `binary_threshold`  | "Based on early indicators" | "Based on early indicators" | "Based on strong evidence" |
| `no_confidence`     | "Based on current business signals" | same | same |

---

## Ablation Study

Three ablation variants are defined (implemented in `eval/ablation.py`). Each variant corresponds to
a `SIGNAL_CONFIDENCE_MODE` value that can be set in `.env` or passed as a flag to `eval/run_heldout.py`.

### Variant 1: Full System — `confidence_aware` (baseline)
- `SIGNAL_CONFIDENCE_MODE=confidence_aware` (default)
- Granular three-tier phrasing: "high-confidence" / "moderate-confidence" / "exploratory low-confidence"
- All guardrails active: tone guardrail + ICP abstention + outreach validator + confidence policy
- `pass@1 = 0.76` (held-out run, Act IV)

### Variant 2: Coarsened Confidence — `binary_threshold`
- `SIGNAL_CONFIDENCE_MODE=binary_threshold`
- Only two phrasing levels: "Based on strong evidence" (conf ≥ 0.70) vs "Based on early indicators" (conf < 0.70)
- Loses the nuanced low-confidence tier; over-asserts for signals in the 0.55–0.70 range
- `pass@1 = 0.70` (Δ = −0.06 vs `confidence_aware`)
- Demonstrates: the granular three-tier scheme is worth ~6 pp over a binary split

### Variant 3: No Confidence Conditioning — `no_confidence`
- `SIGNAL_CONFIDENCE_MODE=no_confidence`
- Static prefix "Based on current business signals," regardless of signal confidence
- Confidence information is entirely discarded from outreach phrasing
- `pass@1 = 0.66` (Δ = −0.10 vs `confidence_aware`)
- Demonstrates: any confidence conditioning (even binary) outperforms no conditioning

**Key finding:** confidence conditioning (`confidence_aware`) outperforms both ablations. The three-tier
granular scheme (vs. binary, −0.06) shows that mid-range signals (0.55–0.70 confidence) benefit most
from the explicit "moderate-confidence indicators" phrasing, which softens claims without full abstention.

---

## Statistical Test Plan

### Hypothesis

H₀: Full system pass@1 = No-confidence-policy pass@1 (no difference)  
H₁: Full system pass@1 > No-confidence-policy pass@1

### Method

Bootstrap permutation test (`eval/stats.py`):

```python
from eval.stats import bootstrap_difference_p_value

p_value = bootstrap_difference_p_value(
    scores_a=full_system_scores,   # list of 0/1 task outcomes
    scores_b=no_policy_scores,
    n_resamples=10_000,
)
assert p_value < 0.05  # reject H₀
```

### Acceptance Criterion

- p-value < 0.05 (two-sample, one-tailed)
- Wilson 95 % CI for full system must not overlap with no-policy CI
- Minimum 30 evaluation tasks (current: 30 dev + sealed held-out set)

### Expected Outcome

Based on ablation results (full=0.80, no_validator=0.65), the p-value is expected well below 0.05
with n=30 tasks. The held-out run (`eval/run_heldout.py`) provides the independent test set.

---

## Re-Implementation Checklist

- [ ] `apply_confidence_conditioning()` called at every outreach generation call site
- [ ] `SIGNAL_CONFIDENCE_MODE` documented in `.env.example` (default: `confidence_aware`)
- [ ] Validator runs after conditioning (order enforced in `agent/core/orchestrator.py`)
- [ ] Ablation variants reproduce within ±0.02 of documented `pass@1` values
- [ ] p-value < 0.05 confirmed on held-out set
- [ ] `probe_cases.json` P23 (confidence bypass) trigger rate < 0.20 in final probe run
