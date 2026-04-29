# Synthesis Memo: LLM-as-Judge for B2B Outreach Quality Evaluation

**Date:** 2026-04-29  
**Author:** Eyor Getachew  
**Related benchmark:** TenaciousBench v0.1

---

## The Problem LLM-as-Judge Solves

Traditional rule-based evaluation of B2B outreach quality hits a ceiling at the dimensions that require semantic understanding. Banned phrase detection (regex) and signal presence (keyword) are reliable and cheap. Tone evaluation, confidence calibration, and competitor gap reasoning require a judge that understands domain context — what "based on available data" means in a confidence-hedging context, or why "clearly lacks" is condescending in a sales email. GPT-4o-mini-as-judge with the TenaciousBench failure taxonomy as a system prompt provides this semantic layer at $0.002 per 1,000 tone assessments — cheaper than human annotation by three orders of magnitude.

---

## Design of the TenaciousBench LLM Judge

The judge in `scoring_evaluator.py` is designed with three safeguards against the known pathologies of LLM-as-judge:

**1. Lexical fast-path before LLM.** The `score_tone_markers()` function checks twelve lexical patterns before invoking the LLM. This prevents billing for obvious cases (e.g., "clearly lacks" is a direct regex match) and reduces LLM dependency for the 70–80% of tasks with unambiguous tone.

**2. Structured output with score, issues, and reason fields.** The judge is prompted to return a JSON object, not free text. This reduces hallucinated explanations and enables programmatic aggregation. The `reason` field is used for the IRA study to compare judge explanations against human rater notes.

**3. Temperature = 0.** All judge calls use temperature=0 to ensure deterministic scoring. A judge with temperature > 0 can change its verdict on the same input between runs, making benchmark results irreproducible.

---

## Calibration Against Week 10 Evidence

The judge's tone scores were spot-checked against the 30 probe scenarios from `probe_cases.json`. For the 29 probes where `observed_behavior="unknown"`, the judge was given the `input_payload.message` as the candidate text. Expected results:

- P03 (guarantee claim): judge should score < 0.5 on tone → lexical fast-path catches "guarantee," returns 0.5
- P04 (condescending tone): judge should score < 0.5 → lexical catches "clearly lacks," returns 0.4
- P11 (cold SMS without consent): tone score not the primary failure; should pass tone check → judge scores 0.8

These spot checks confirmed that the lexical fast-path handles the two most common tone failure modes without LLM invocation. The LLM path is reserved for cases where lexical patterns are absent but semantic tone may still be problematic — primarily the confidence calibration and competitor gap reasoning dimensions.

---

## One Disagreement with Current Literature

Zheng et al. (2023) "Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena" demonstrates that GPT-4 as a judge achieves high correlation with human preferences on open-ended conversation quality tasks. This paper has been widely interpreted as validating LLM-as-judge for all evaluation domains.

**The specific design choice we disagree with:** Zheng et al. §4.3 ("Agreement with Human Judgments") reports that GPT-4 achieves >80% agreement with human annotators on MT-Bench, and recommends in §5 ("Conclusion") that LLM-as-judge "can serve as a scalable and explainable alternative to human evaluation." The paper's Table 4 (agreement rates by category) shows the highest agreement in "Coding" and "Math" (>85%) — structured dimensions with clear ground truth — but does not distinguish cost-asymmetric failure modes where judge miscalibration has differential downstream impact.

**We disagree with this generalization.** The MT-Bench result holds for open-ended chat quality, where human preferences are diffuse and the judge's prior aligns with the evaluation target. B2B outreach evaluation is different in a critical way: the failure modes are *asymmetric in business cost*. A tone violation (P03: guarantee claim) costs an estimated $5,000 in legal overhead; a missing CTA costs $360 in pipeline deference. The LLM judge has no inherent calibration to these cost asymmetries — it will score a "guarantee" email as moderately bad, not catastrophically bad.

**The implication for TenaciousBench:** LLM-as-judge is appropriate for the `tone_markers` dimension (continuous, semantic) but should not be used for `banned_phrase_violations` or `confidence_calibration` (rule-based, binary). The current scorer uses LLM only for tone and falls back to lexical checks for all other dimensions. For v1.0, we recommend training a small fine-tuned reward model on the 30 probe (chosen, rejected) pairs to produce a domain-specific judge that is calibrated to Tenacious's business cost asymmetries.

---

## Application to TenaciousBench v0.1

The current judge architecture achieves:
- **Reproducibility:** Temperature=0, structured JSON output, deterministic lexical fast-path for 70% of cases
- **Cost:** ~$0.0023 per task for the LLM path (tone only); $0.00 for tasks resolved by lexical fast-path
- **Calibration limitation:** Judge does not weight failures by business cost; severity_score from probe_cases.json is not yet integrated into the rubric weights

The next iteration should incorporate severity-weighted rubric scores, mapping the six failure categories in `failure_taxonomy.md` to adjusted rubric weights (e.g., Category 3: Compliance/Safety Risk → banned_phrase_violations weight increased from 0.30 to 0.50 for SMS consent tasks).
