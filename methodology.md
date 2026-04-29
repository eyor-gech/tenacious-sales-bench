# TenaciousBench v0.1 Methodology

**Version:** 0.1  
**Date:** 2026-04-29  
**Author:** Eyor Getachew

---

## 1. Path Declaration

**Recommended path: Path B — Judge/Critic via DPO/SimPO/ORPO.**

### 1.1 Analytical Justification from Week 10 Evidence

Week 10 produced three classes of evidence that collectively rule out Paths A and C and select Path B:

**Against Path A (SFT generation):**  
SFT requires a volume of high-quality reference outputs sufficient to cover the input distribution. The held-out evaluation produced 17 passing traces across 20 tasks — a corpus too small to train a generalising generation model. The nine-company prospect set further narrows diversity. Spending Week 11 generating synthetic SFT data is valid, but it defers the actual alignment contribution until after data collection is complete, leaving no time for training and evaluation.

**Against Path C (PRM — Process Reward Model):**  
PRM requires per-step quality labels over the agent's reasoning chain. Week 10 trace logs record input/output pairs and pass/fail verdicts but carry no intermediate quality annotations. The `act4_held_out_traces.jsonl` file contains model inputs, outputs, classification decisions, and final labels — not the per-step rubric scores a PRM trainer requires. Adding a step-level annotation pass is a new, multi-day effort, not a conversion of existing data.

**For Path B (Judge/Critic):**  
Five converging signals from Week 10 point to Path B:

1. **Ablation as ranked preference data.** The three-mode ablation produced `confidence_aware` (0.76) > `binary_threshold` (0.70) > `no_confidence` (0.66). This is a ranked preference triple over the same 20 held-out inputs — the DPO/SimPO training format, verbatim.

2. **30 probe triples are DPO pairs by construction.** Each probe in `probe_cases.json` defines (`input_payload`, `expected_failure`, implicit expected_behavior). The `expected_failure` branch is the rejected response; a compliant system output is the chosen response. Converting these to (prompt, chosen, rejected) tuples requires only one annotated run under each mode.

3. **Failure taxonomy is the critic's label schema.** Six categories — Revenue Leakage, Brand/Reputation Harm, Operational Blind Spots, Compliance/Safety Risk, Economic Inefficiency, Evaluation Distortion — provide a structured, coverage-complete rubric for a judge model. Training a critic on these labels is tractable; building a new taxonomy from scratch is not.

4. **Week 11 framing is "evaluation bench."** The deliverable is a system that *scores outreach quality*, not one that *generates outreach*. A judge model is the natural implementation of a scoring system.

5. **Cost-efficiency.** GPT-4o-mini-as-judge with the failure taxonomy as a system prompt can score 100 outreach examples in under $0.10 and under 30 minutes. A calibrated prompted judge with documented Spearman ρ against pass@1 is publishable; a small fine-tuned reward model is also feasible via `trl` ORPO on an adapter.

---

## 2. Benchmark Design Rationale

### 2.1 Why 220 Tasks

The 220-task total was derived from three requirements:

- **Statistical power:** A held-out split of 44 tasks gives a 95 % CI of ±14 pp on pass@1 at a 50 % base rate (standard normal approximation). This is comparable to the 20-task held-out used in Week 10 (±22 pp CI) but tighter — the improvement in CI width from √(20/44) ≈ 0.67 is material given the pilot decision stakes.
- **Dimension coverage at 3× oversampling:** Ten dimensions × 6 tasks each × 3 splits = 180 minimum. The 40-task surplus (220 − 180) is allocated to the three highest-failure dimensions from Week 10 (ICP accuracy, confidence calibration, tone safety) at 8 tasks per dimension × 3 splits.
- **Training signal for judge model:** 110 training tasks provide enough (chosen, rejected) pairs, when combined with 30 probe pairs, to fill an 80–140 pair DPO dataset — the practical minimum for SimPO/ORPO on a small adapter.

### 2.2 Dimension Selection

The ten dimensions map directly to failure modes documented in `probe_cases.json` and `failure_taxonomy.md`:

| Dimension | Primary Probes | Failure Category |
|-----------|---------------|-----------------|
| Signal-grounded personalization | P05, P06, P27, P28 | Evaluation Distortion |
| Confidence-aware phrasing | P23, P24 | Brand/Reputation Harm |
| Hallucination avoidance | P03, P23 | Brand/Reputation Harm |
| Brand-safe tone | P03, P04 | Brand/Reputation Harm |
| Multi-turn objection handling | P14 | Compliance/Safety Risk |
| Correct CTA behavior | P08 | Revenue Leakage |
| ICP targeting accuracy | P01, P02 | Revenue Leakage |
| Competitor gap reasoning | P05, P27 | Evaluation Distortion |
| Pricing discipline | (programmatic) | Brand/Reputation Harm |
| Thread continuation coherence | P07, P08, P14 | Compliance/Safety Risk |

---

## 3. Partitioning Protocol

### 3.1 Split Ratios

| Split | Tasks | Fraction |
|-------|-------|----------|
| train | 110 | 50 % |
| dev | 66 | 30 % |
| held_out | 44 | 20 % |

### 3.2 Stratification Variables

Stratification was performed simultaneously on:
- `dimension` (10 levels)
- `source_mode` (4 levels: trace_derived, programmatic, multi_llm_synthesis, hand_authored_adversarial)
- `difficulty` (4 levels: easy, medium, hard, adversarial)

The split uses a deterministic hash-based assignment: `hash(task_id) % 10 < 5 → train; % 10 in {5,6,7} → dev; % 10 in {8,9} → held_out`. This ensures reproducibility without requiring a random seed.

### 3.3 Held-Out Isolation

`held_out.jsonl` was written before `train.jsonl` and `dev.jsonl`. No task in `held_out` shares:
- A company_id with any train/dev task
- An n-gram overlap > 30 % with any train/dev task (verified by `generation_scripts/contamination_check.py`)
- An embedding cosine similarity > 0.85 with any train/dev task

This directly addresses the P19 failure mode (case-sensitive task-ID leakage) documented in Week 10.

---

## 4. Source Mode Mix

| Source Mode | Target % | Actual Tasks | Description |
|-------------|----------|-------------|-------------|
| trace_derived | 30 % | 66 | Derived from `act4_held_out_traces.jsonl` and `act2_sample_thread.json`; company contexts anonymised |
| programmatic | 30 % | 66 | Template-generated with random variable substitution from `sample_companies.json` schema |
| multi_llm_synthesis | 25 % | 55 | Two-LLM pipeline: GPT-4o-mini generates, Claude-3-haiku reviews; tasks where both agree are kept |
| hand_authored_adversarial | 15 % | 33 | Directly derived from probe_cases.json; each probe → 1 task per split |

Trace-derived tasks are the most grounded but least diverse; adversarial tasks are the most targeted but require manual validation. The 30/30/25/15 mix was chosen to prevent overfit to either extreme.

---

## 5. Judge Filtering Design

All programmatic and multi-LLM synthesis tasks pass through `generation_scripts/judge_filter.py` before inclusion. The judge filter:

1. **Completeness check:** Task must have non-empty `outreach_text`, at least one `required_signal`, and a non-empty `banned_phrases` list.
2. **Rubric coherence:** `pass_threshold` must be in [0.5, 0.95]; weights must sum to 1.0 ± 0.01.
3. **LLM quality gate:** GPT-4o-mini is asked: "Is this a valid B2B outreach evaluation task? Does it test exactly one of the ten TenaciousBench dimensions? Answer YES or NO." Tasks receiving NO are discarded.
4. **Difficulty calibration:** Tasks where the oracle scorer returns 1.0 on the `ideal_output` are flagged as `easy` and capped at 20 % of each split.

Adversarial and trace-derived tasks bypass the LLM quality gate (they were hand-validated at source).

---

## 6. Contamination Protocol

### 6.1 N-gram Overlap

Character-level 6-gram overlap between all pairs of tasks across splits. Tasks with > 30 % overlap are flagged; the train/dev copy is removed (held_out is preserved).

### 6.2 Embedding Similarity

`sentence-transformers/all-MiniLM-L6-v2` embeddings computed on `outreach_text` of `ideal_output`. Cosine similarity > 0.85 between held_out and train/dev tasks triggers removal.

### 6.3 Time-Shift Verification

All `signal_date` values in held_out tasks must be ≥ 2026-04-01 (post-Week 10). Train/dev tasks may use signals from 2026-01-01 onward. This prevents temporal leakage where a held_out task's buying signal was observable at training time.

### 6.4 Company ID Isolation

No `company_id` appears in both held_out and train/dev. Company IDs from `week10_final/data/sample_companies.json` (cmp_001 – cmp_009) appear only in train/dev, never in held_out.

Results are logged to `contamination_check.json`.

---

## 7. Week 10 Evidence References

| Claim | Evidence File | Key Value |
|-------|--------------|-----------|
| Path B justified by ablation ordering | `results/act4_ablation_results.json` | 0.76 > 0.70 > 0.66 |
| 30 probes define DPO pairs | `probes/probe_cases.json` | P01–P30 |
| Failure taxonomy = critic label schema | `probes/failure_taxonomy.md` | 6 categories, 30 mappings |
| Held-out baseline for critic alignment | `results/act4_heldout_summary.json` | pass@1 = 0.85 |
| Dev baseline | `results/act1_score.json` | pass@1 = 0.5333 |
| Statistical validity | `results/act5_evidence_graph.json` | p = 0.0001, 10k bootstrap |
| P19 contamination risk | `probes/probe_cases.json` (P19) | Case-sensitive ID leakage |
