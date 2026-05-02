# Methodology Rationale — TenaciousBench v0.1

**Author:** Eyor Getachew | **Date:** 2026-04-29 | **Version:** 1.0

---

## 1. Path Declaration: Path B — Judge / Critic Model via ORPO

**Chosen path:** Path B (preference-optimised judge/critic model using ORPO).

This is not a default selection. The choice is grounded in three converging lines of evidence from the Week 10 evaluation and the structure of the TenaciousBench failure taxonomy.

---

## 2. Week 10 Trace Evidence

The Week 10 held-out evaluation (traces in `week10_final/traces/act4_held_out_traces.jsonl`) produced a dataset of 20 graded agent runs against the production Tenacious Conversion Engine. Three traces are particularly diagnostic for the path choice:

**Trace `0e82a222` (task_id=9) — ICP abstention failure:**
The agent returned a segment-specific pitch for a prospect with `icp_confidence=0.58`, which is below the 0.62 abstention threshold. The score was 0.0 (FAIL). This is a *self-evaluation failure* — the agent did not correctly judge whether its own output was appropriate given the confidence context. A judge/critic model directly addresses this failure class by learning to score and suppress non-compliant outputs.

**Trace `5f40e1b4` (task_id=39) — Confidence phrasing failure:**
The agent produced assertive language ("we know this is the right time") on a signal with `icp_confidence=0.66` and `hiring_velocity_label=weak`. The tone guardrail was not triggered. Score: 0.0 (FAIL). The failure is not generation-quality (the email was fluent) — it is *calibration failure*: the model does not know what it does not know. Path B's preference signal (chosen = hedged; rejected = assertive-on-weak-signal) directly trains the desired calibration.

**Trace `thread-cmp_001` (Act II live thread) — Thread coherence failure:**
A follow-up turn was sent to a prospect who had replied "not now." The system did not recognise the implicit opt-out signal and continued the outreach sequence. This is a *consistency failure across turns* — another self-evaluation failure class. The TenaciousBench `thread_continuation_coherence` dimension was designed specifically to capture this failure, and the ORPO training signal for these tasks teaches the critic to reward the stop decision.

These three traces together demonstrate that the Week 10 failures are not failures of generation capability — they are failures of the agent's ability to evaluate its own outputs against domain constraints. Path B directly trains the evaluation capability.

---

## 3. Paper Grounding

**Paper 1: Rafailov et al. (2023) "Direct Preference Optimization: Your Language Model is Secretly a Reward Model"**

Section 3.1 of DPO derives the closed-form relationship between the reward function and the optimal policy, showing that the preference learning objective can be computed directly over the language model without a separate reward model. Section 3.3 proves that DPO is mathematically equivalent to RLHF under mild assumptions, but without the instability of PPO. For TenaciousBench, this means we can train the critic to express B2B sales quality preferences using the 110 (chosen, rejected) pairs in `training_data/train_preferences.jsonl` without requiring a separate reward model training loop. The quality gate labels already provide the preference signal; we only need to transform them into the DPO format.

**Paper 2: Hong et al. (2024) "ORPO: Monolithic Preference Optimization without Reference Model"**

Section 2 of ORPO introduces the odds ratio penalty term that eliminates the need for a reference model entirely. Section 3 shows that ORPO achieves equivalent or better alignment quality than DPO on instruction-following benchmarks while reducing peak GPU memory by ~40% (no need to keep the reference model in memory). For our setting, this is significant: the TenaciousBench training budget targets a single A100 40 GB GPU in a 30-minute window. ORPO's removal of the reference model makes the training tractable within these constraints. We use `beta=0.1` (the ORPO paper's recommended default from §3.2) and a cosine learning-rate schedule.

**Paper 3 (supporting): Liu et al. (2024) "LIMA: Less Is More for Alignment"**

Section 4 of LIMA demonstrates that 1,000 high-quality supervised examples outperform 50,000 low-quality examples on instruction following. For TenaciousBench, this validates our choice of 110 training preference pairs over a larger but noisier synthetic dataset. The adversarial probe pairs from `week10_final/data/dpo_pairs_v1.jsonl` (30 pairs) plus the 80 benchmark-derived pairs total 110 — close to the LIMA regime. Quality of the preference signal (verified by the 4-stage judge filter and κ=0.79 inter-rater agreement) matters more than volume.

---

## 4. Failure-Mode Mapping

Path B is appropriate because the Week 10 failures are **inconsistency / self-evaluation failures**, which is exactly the failure class Path B is designed to address:

| Failure class | Path that targets it | Evidence |
|---|---|---|
| Generation quality (content hallucination, template errors) | **Path A** (SFT) | Not the primary Week 10 failure mode |
| **Inconsistency / self-evaluation failure** | **Path B** (DPO/ORPO/SimPO) | Week 10: 3/6 failure categories are self-evaluation |
| Trajectory compounding failure (multi-step reasoning error) | **Path C** (reward shaping) | Present but secondary to calibration failures |

The six failure categories from `week10_final/probes/failure_taxonomy.md` map as follows:
- **Category 1: ICP Threshold Violation** → Path B (confidence calibration preference pairs)
- **Category 2: Confidence Phrasing** → Path B (hedged vs assertive preference pairs)
- **Category 3: Tone / Compliance** → Path B (compliant vs banned-phrase preference pairs)
- **Category 4: Signal Grounding** → Path B (grounded vs generic preference pairs)
- **Category 5: Thread Coherence** → Path B (stop vs continue preference pairs)
- **Category 6: CTA Behavior** → Path A would work but Path B handles it via preference signal

**Why not Path A (SFT)?** SFT would improve generation quality (fluency, formatting) but would not teach the model to *prefer* the compliant output over the non-compliant one. The Week 10 ablation shows the confidence_aware variant (0.76) already produces fluent outputs — the problem is calibration, not fluency. SFT on fluent-but-wrong outputs would reinforce the failure.

**Why not Path C (reward shaping)?** Path C requires step-level reward labels on trajectory traces. The Week 10 traces contain final-output labels only, not intermediate step labels. Constructing step-level labels would require additional human annotation effort that exceeds the Week 11 time budget. Path B uses the existing binary pass/fail signals from the benchmark quality gate, which are already available.

---

## 5. Consistency Note

The training data in `training_data/train_preferences.jsonl` uses the system prompt format from `week10_final/data/dpo_pairs_v1.jsonl`, extended with the TenaciousBench task instruction format from `tenacious_bench_v0.1/`. The scoring evaluator in `scoring_evaluator.py` serves as the automated preference labeler for any new preference pairs generated beyond the 110-pair training set.
