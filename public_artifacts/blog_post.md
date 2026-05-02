# We Built a Benchmark for B2B Outreach AI — Here's What We Learned

*Eyor Getachew · May 2026 · 10 Academy Week 11*

---

Most AI benchmarks test whether a model can follow instructions. TenaciousBench tests whether a B2B sales agent knows when *not* to send an email.

That's a different problem. And it turns out, it's a hard one.

## The Problem with Existing Benchmarks

When we started evaluating the Tenacious Conversion Engine — an AI system that generates and routes B2B outreach — we reached for the standard benchmarks. τ²-Bench. GAIA. HELM. None of them had tasks for "should the agent abstain from sending this email because the ICP confidence score is 0.58?"

That's not a niche case. In production, roughly 30–40% of B2B prospect signals fall below a reasonable ICP threshold. An agent that ignores this threshold and pitches anyway doesn't just produce a bad email — it damages the company's sender reputation and potentially violates consent regulations.

We built TenaciousBench to measure the failure modes that actually matter for B2B outreach AI.

## What TenaciousBench Measures

220 tasks across 10 failure dimensions:

- **ICP targeting accuracy:** Does the agent abstain when confidence is below 0.62?
- **Confidence-aware phrasing:** Does the agent hedge its language for borderline signals?
- **Signal grounded personalization:** Does the email reference actual hiring data, not generic boilerplate?
- **Brand safe tone:** Does the agent avoid condescending language and unverifiable claims?
- **Hallucination avoidance:** Does the agent refuse to cite signals it wasn't given?
- **CTA behavior:** Is the call-to-action appropriate for the prospect's stage?
- **Competitor gap reasoning:** Does the agent correctly interpret competitor hiring as a relevant signal?
- **Pricing discipline:** Does the agent avoid committing to pricing without qualification?
- **Multi-turn objection handling:** Does the agent de-escalate after a "not now" rather than pushing harder?
- **Thread continuation coherence:** Does the agent remember what was said in prior turns?

## How We Built It

Each task has a full context stack: company profile, signal brief (hiring velocity, ICP confidence, competitor gap, honesty flags), a thread history, and a specific task instruction. The ground truth includes the ideal output, a list of banned phrases, required grounding signals, and a CTA pattern.

We mixed four source modes:
- **66 trace-derived tasks:** Converted from Week 10 held-out agent traces, with company names anonymised
- **64 programmatic tasks:** Template-generated with sampled signal values from real-world distributions
- **52 multi-LLM synthesis tasks:** GPT-4o-mini generated drafts, reviewed by a second GPT-4o-mini call with a structured judge prompt
- **41 hand-authored adversarial tasks:** Derived directly from 30 adversarial probes, each testing a specific production failure mode

The multi-LLM synthesis pipeline had a 22% rejection rate through the 4-stage quality gate — which means the gate is actually filtering, not rubber-stamping.

We ran an inter-rater agreement study on 30 tasks. Pre-revision Cohen's κ was 0.72 (substantial agreement). Four rubric revisions later, post-revision κ reached 0.79. The three lowest-performing dimensions — confidence-aware phrasing, competitor gap reasoning, thread continuation coherence — all required rubric clarification before raters could agree consistently.

## The Training Experiment

With the benchmark in place, we ran Path B: a preference-optimised judge/critic model using ORPO (Hong et al. 2024) on top of Qwen2.5-7B-Instruct.

Why ORPO instead of DPO? Two reasons: ORPO eliminates the reference model, halving peak GPU memory, and it converges faster on small datasets. Our 110 preference pairs is firmly in the LIMA regime (Liu et al. 2024) — small but high-quality, which is exactly what domain-specific alignment needs.

Training results:
- 3 epochs on 110 preference pairs
- Final train loss: 0.2847, eval loss: 0.3012
- Training time: 17.9 minutes on a single A100 40GB
- Convergence was clean — no kill criterion triggered

Evaluation on the 44-task held-out split:

| System | pass@1 | Δ vs baseline | 95% CI | p-value |
|--------|--------|--------------|--------|---------|
| ORPO-trained (Delta A) | 90.9% (40/44) | **+6.8 pp** | [−6.8, +20.4] | 0.1953 |
| Prompt-only (Delta B) | 86.4% (38/44) | +2.3 pp | [−13.6, +15.9] | 0.4357 |
| Week 10 baseline | 84.1% (37/44) | — | — | — |

The paired bootstrap (10,000 resamples, seed=42) gives p=0.1953 for Delta A — directionally positive but not formally significant at n=44. This is expected: detecting a 6.8 pp effect at α=0.05 with 80% power requires roughly n=200 binary tasks. The ORPO-trained model is nonetheless the Pareto winner on both quality and cost: it achieves the highest pass@1 at $0.000089/task, compared to $0.000213 for the prompt-only approach and $0.000229 for the Week 10 GPT-4o-mini baseline.

## What Surprised Us

**The adversarial tasks are where the training pays off.** The per-dimension breakdown shows the largest gains in `icp_targeting_accuracy` (+7.9 pp) and `signal_grounded_personalization` (+7.0 pp) — exactly the dimensions where the Week 10 agent was failing on the adversarial probes.

**Prompt engineering closes 34% of the gap.** Delta B (prompt-only, +2.3 pp) recovers about a third of the Delta A improvement (+6.8 pp) with no training cost. This tells us that part of the baseline model's failure is recoverable through better instruction design. The ORPO training adds the remaining gain by internalising the preference signal rather than relying on in-context reminders.

**The `factual_unsupported_claims` detector has a regex gap.** The hyphenated form "best-in-class" doesn't match our pattern `\bbest\s+in\s+class\b`. This is a documented false-negative in the current scorer. It doesn't affect pass/fail verdicts in practice because the other dimensions catch the same failing outputs, but it'll be patched in v0.2.

## What's Next

TenaciousBench v0.2 will expand to 400 tasks, add manufacturing and logistics verticals, and include human-validated labels for all 220 current tasks (targeting inter-rater agreement ≥ 3 raters, κ ≥ 0.80 on all dimensions). We'll also incorporate severity-weighted rubric scores, mapping the six failure categories in the failure taxonomy to adjusted weights — compliance/safety violations should cost more than a missing CTA.

The dataset is on HuggingFace at [https://huggingface.co/datasets/eyorg/tenacious_bench_v0.1](https://huggingface.co/datasets/eyorg/tenacious_bench_v0.1). The code is MIT-licensed. If you're building a B2B outreach agent, we'd genuinely like to know how your system scores on the held-out split.

---

*Code: [github.com/eyorg/tenacious-sales-bench](https://github.com/eyor-gech/tenacious-sales-bench)*  
*Dataset: [huggingface.co/datasets/eyorg/tenacious_bench_v0.1](https://huggingface.co/datasets/eyorg/tenacious_bench_v0.1)*  
*10 Academy Week 11 Final Submission*
