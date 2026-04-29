# Synthesis Memo: Synthetic Data Best Practices for B2B Sales Benchmarks

**Date:** 2026-04-29  
**Author:** Eyor Getachew  
**Related benchmark:** TenaciousBench v0.1

---

## The Core Challenge

Synthetic benchmark data for B2B sales agents faces a tension that does not exist in general-domain benchmarks: the failure modes we want to test are *distribution-specific*. An ICP abstention failure matters because the ICP threshold (0.62) was calibrated on real pipeline data; a confidence calibration failure matters because the three-tier prefix policy was empirically validated against Week 10 ablation results. Synthetic data that does not reproduce these specific distributions will produce benchmark tasks that test the wrong thing — an agent that never sees a borderline icp_confidence=0.61 case will look well-aligned on the benchmark while failing in production.

---

## Principle 1: Anchor Distributions to Observed Evidence

The strongest synthetic data for this benchmark comes from perturbing real trace values, not sampling from abstract priors. In TenaciousBench v0.1, the programmatic tasks use icp_confidence values sampled from a truncated Gaussian fitted to the nine-company sample from `week10_final/data/sample_companies.json` — mean 0.72, std 0.12, clipped at [0.40, 0.95]. This is not a principled distribution, but it is *calibrated to the boundary where the real system fails*.

The Week 10 ablation delta (confidence_aware: 0.76 vs no_confidence: 0.66) implies that the 0.55–0.75 icp_confidence band is where phrasing decisions change outcomes. Tasks in this band should be overrepresented in the benchmark relative to their natural frequency — this is intentional anti-naturalness, and it is correct.

---

## Principle 2: Adversarial Tasks Cannot Be Substituted with Synthetic Augmentation

There is a temptation to use a large language model to generate adversarial tasks by prompting it with "generate a task that tests X failure mode." This approach is deeply unreliable for two reasons:

1. **The LLM will generate the prototypical failure, not the actual failure.** P03 (guarantee bypass) is not "write an email that contains the word guarantee." It is a specific regex bypass in `apply_tone_guardrail()` that only fires on the predicate construction "will be operational." A GPT-4o-mini generation of the P03 scenario will produce the obvious pattern, not the subtle one.

2. **The LLM is the agent under test.** If the judge model used to generate adversarial tasks is the same family as the agent being evaluated, the adversarial tasks will be in-distribution for the agent and will not test edge cases.

**TenaciousBench v0.1's position:** Adversarial tasks must be hand-authored from real probe evidence. The 33 hand-authored adversarial tasks in this benchmark are derived directly from `probe_cases.json`, not from LLM generation. This is a deliberate design choice and should not be reversed in v0.2 without strong justification.

---

## One Disagreement with Current Literature

Wang et al. (2023) "Self-Instruct: Aligning Language Models with Self-Generated Instructions" and subsequent work (Alpaca, WizardLM) demonstrate that LLM-generated instruction datasets can achieve strong instruction-following benchmarks. This success has been overgeneralized to mean that LLM-generated data is suitable for domain-specific safety and alignment benchmarks.

**The specific design choice we disagree with:** Wang et al. §4.2 ("Diversity and Quality of Self-Instruct Data") states that machine-generated instructions covering diverse tasks are sufficient for alignment when seeded from 175 hand-written examples. The paper reports that Self-Instruct-trained models match InstructGPT (001) on SUPERNI with only 5% human-authored data. This result is cited in Alpaca (Taori et al., 2023, §3) as justification for discarding hand-authored adversarial examples entirely.

**We disagree.** Self-Instruct-style generation is appropriate when the target skill is *instruction following* — a distribution the LLM has seen extensively in pretraining. It is not appropriate when the target skill is *failure mode detection in a specific production system*. The value of TenaciousBench's adversarial tasks comes precisely from their specificity to the Tenacious Conversion Engine's code paths (ICP classifier threshold, confidence prefix policy, tone guardrail regex). A self-generated dataset cannot reproduce this specificity without access to the codebase — and if it had that access, it would be fine-tuning, not benchmark construction.

For v0.2, we recommend: LLM synthesis for easy and medium tasks (clear rubric, obvious signal grounding), hand-authoring for all hard and adversarial tasks, and trace derivation for the held-out split only.

---

## Application to TenaciousBench v0.1

The 220-task dataset applies these principles as follows:

- **55 multi-LLM synthesis tasks:** Used for easy/medium difficulty dimensions with clear pass criteria. Rejection rate of 22% (14/69) by the judge filter confirms that the quality gate is working.
- **66 programmatic tasks:** Anchor to observed signal distributions; appropriate for testing rubric dimensions that are verifiable by keyword/regex without LLM scoring.
- **33 hand-authored adversarial tasks:** Derived from probe library; irreplaceable for testing real failure modes.
- **66 trace-derived tasks:** Highest fidelity to real agent behavior; appropriate for held-out evaluation only in future versions (currently mixed across splits due to volume constraints).
